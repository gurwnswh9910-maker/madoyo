import os
import hashlib
import json
import requests
import tempfile
import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor
from google import genai
from google.genai import types
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from app_config import GlobalConfig

load_dotenv()

def _is_retriable(exc):
    msg = str(exc).lower()
    return any(code in msg for code in ['429', '503', 'resource exhausted', 'unavailable', 'deadline exceeded'])

class EmbeddingManager:
    """[ONLINE VERSION] SQL pgvector 및 Supabase Storage 전용 매니저"""
    def __init__(self, storage_path=None):
        self.api_key = GlobalConfig.GEMINI_API_KEY
        self.model_id = GlobalConfig.EMBEDDING_MODEL 
        self.db_url = os.getenv("DATABASE_URL")
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_ANON_KEY")
        
        print(f"🚀 [EmbeddingManager v7.0-ONLINE] Initialized with model: {self.model_id}")
        
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None
            
        self._file_cache = {} 

    def _get_db_conn(self):
        return psycopg2.connect(self.db_url)

    def save_to_db(self, content_text, embedding, embedding_type="multi", mss_score=0.0, is_global=True, metadata=None):
        """DB에 임베딩 및 메타데이터 저장"""
        conn = self._get_db_conn()
        cur = conn.cursor()
        try:
            # content_text, embedding_type 복합키 제약조건에 따른 UPSERT
            cur.execute(
                """
                INSERT INTO mab_embeddings (content_text, embedding_type, embedding, mss_score, is_global, metadata_json) 
                VALUES (%s, %s, %s, %s, %s, %s) 
                ON CONFLICT (content_text, embedding_type) DO NOTHING
                """,
                (content_text, embedding_type, embedding.tolist() if isinstance(embedding, np.ndarray) else embedding, mss_score, is_global, json.dumps(metadata or {}))
            )
            conn.commit()
        except Exception as e:
            print(f"    ⚠️ DB Save Error: {e}")
            conn.rollback()
        finally:
            cur.close()
            conn.close()

    def save_triple_to_db(self, content_text, text_vec, visual_vec, joint_vec, mss_score=0.0, is_global=True, metadata=None):
        """본문 1개에 대해 3종류(text, visual, multi) 임베딩을 한 번에 저장 (트리플 벡터 완성)"""
        if text_vec is not None:
            self.save_to_db(content_text, text_vec, embedding_type="text", mss_score=mss_score, is_global=is_global, metadata=metadata)
        if visual_vec is not None:
            self.save_to_db(content_text, visual_vec, embedding_type="visual", mss_score=mss_score, is_global=is_global, metadata=metadata)
        if joint_vec is not None:
            self.save_to_db(content_text, joint_vec, embedding_type="multi", mss_score=mss_score, is_global=is_global, metadata=metadata)
        print(f"    ✅ 트리플 벡터 DB 저장 완료: text={'O' if text_vec is not None else 'X'}, visual={'O' if visual_vec is not None else 'X'}, multi={'O' if joint_vec is not None else 'X'}")

    def get_content_hash(self, text: str, image_paths_or_urls: list = None) -> str:
        img_list = []
        if image_paths_or_urls:
            if isinstance(image_paths_or_urls, str): img_list = [image_paths_or_urls]
            else: img_list = [str(u) for u in image_paths_or_urls]
        payload = f"{text or ''}{'|'.join(img_list)}"
        return hashlib.md5(payload.encode()).hexdigest()

    def upload_to_supabase_storage(self, file_path, bucket_name="feedback-images"):
        """이미지를 Supabase Storage에 업로드하고 Public URL 반환"""
        if not self.supabase_url or not self.supabase_key:
            return None
        
        with open(file_path, "rb") as f:
            content = f.read()
            f_hash = hashlib.md5(content).hexdigest()
        
        file_name = f"{f_hash}.jpg"
        upload_url = f"{self.supabase_url}/storage/v1/object/{bucket_name}/{file_name}"
        
        headers = {
            "Authorization": f"Bearer {self.supabase_key}",
            "apikey": self.supabase_key,
            "Content-Type": "image/jpeg"
        }
        r = requests.post(upload_url, headers=headers, data=content)
            
        if r.status_code in [200, 201, 409]: # 409: Already exists
            return f"{self.supabase_url}/storage/v1/object/public/{bucket_name}/{file_name}"
        return None

    def delete_from_supabase_storage(self, file_name, bucket_name="feedback-images"):
        """분석 완료 후 Storage에서 이미지 삭제 (공간 절약)"""
        url = f"{self.supabase_url}/storage/v1/object/{bucket_name}/{file_name}"
        headers = {
            "Authorization": f"Bearer {self.supabase_key}",
            "apikey": self.supabase_key
        }
        requests.delete(url, headers=headers)

    def upload_to_gemini_file_api(self, file_path):
        """이미지를 Gemini File API에 업로드하고 파일 객체 반환"""
        if not self.client: return None
        try:
            print(f"    [Gemini] File API 업로드 중: {file_path}")
            file = self.client.files.upload(path=file_path)
            return file
        except Exception as e:
            print(f"    ❌ File API Upload Error: {e}")
            return None

    def delete_from_gemini_file_api(self, file_name):
        """임베딩 완료 후 Gemini File API에서 파일 삭제"""
        if not self.client or not file_name: return
        try:
            self.client.files.delete(name=file_name)
            print(f"    ✅ Gemini File API 삭제 완료: {file_name}")
        except Exception as e:
            print(f"    ⚠️ File API Delete Error: {e}")

    def _prepare_media_data(self, path_or_url):
        if str(path_or_url).startswith("http"):
            try:
                r = requests.get(path_or_url, timeout=15)
                if r.status_code == 200:
                    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                    tf.write(r.content)
                    tf.close()
                    return tf.name, True
            except: pass
        return path_or_url, False

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception(_is_retriable), reraise=True)
    def get_multimodal_embedding(self, text=None, image_paths_or_urls=None, file_uri=None, use_db=True):
        if not text and not image_paths_or_urls and not file_uri: return None
        
        # SQL 기반 캐시 조회 (텍스트 Only인 경우만)
        if use_db and text and not image_paths_or_urls and not file_uri:
            conn = self._get_db_conn()
            cur = conn.cursor()
            try:
                cur.execute("SELECT embedding FROM mab_embeddings WHERE content_text = %s AND embedding_type IN ('text', 'multi') LIMIT 1", (text,))
                row = cur.fetchone()
                if row: return np.array(row[0])
            except: pass
            finally:
                cur.close()
                conn.close()

        parts = []
        if text: parts.append(text)
        
        temp_file = None
        is_temp = False
        
        # Case A: Gemini File API URI 사용 (지연 임베딩용)
        if file_uri:
            parts.append(types.Part.from_uri(uri=file_uri, mime_type="image/jpeg"))
        
        # Case B: 로컬 경로 또는 URL 사용 (즉시 임베딩용)
        elif image_paths_or_urls:
            target = image_paths_or_urls[0] if isinstance(image_paths_or_urls, list) else image_paths_or_urls
            temp_file, is_temp = self._prepare_media_data(target)
            if temp_file:
                with open(temp_file, 'rb') as f:
                    parts.append(types.Part.from_bytes(data=f.read(), mime_type="image/jpeg"))

        try:
            result = self.client.models.embed_content(model=self.model_id, contents=parts)
            vector = result.embeddings[0].values
            # 지연 임베딩 캐시 저장은 Router 레벨에서 처리
            return np.array(vector)
        except Exception as e:
            msg = str(e).lower()
            if "indexing" in msg or "not ready" in msg:
                print(f"    ⚠️ File API Indexing 중... (1시간 유예 필요): {e}")
            else:
                print(f"    ❌ Embedding Error: {e}")
            return None
        finally:
            if is_temp and temp_file and os.path.exists(temp_file):
                try: os.remove(temp_file)
                except: pass

    def get_text_embedding(self, text, use_db=True):
        return self.get_multimodal_embedding(text=text, use_db=use_db)

    def get_visual_embedding(self, image_paths_or_urls, use_db=True):
        return self.get_multimodal_embedding(image_paths_or_urls=image_paths_or_urls, use_db=use_db)

    def calculate_similarity(self, v1, v2):
        """두 벡터 간의 코사인 유사도 계산 (Numpy 최적화)"""
        if v1 is None or v2 is None: return 0.0
        v1 = np.array(v1)
        v2 = np.array(v2)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0: return 0.0
        return np.dot(v1, v2) / (norm1 * norm2)

    def get_hybrid_top_k(self, query_vec, k=100, alpha=0.3, embedding_type="multi"):
        """[CORE] SQL pgvector를 사용한 실시간 하이브리드 회수"""
        if query_vec is None: return []
        conn = self._get_db_conn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            query = """
                SELECT content_text, mss_score, metadata_json,
                       (1 - (embedding <=> %s::vector)) as similarity
                FROM mab_embeddings
                WHERE embedding_type = %s
                ORDER BY ((1 - (embedding <=> %s::vector)) * %s) + (mss_score / 100.0 * %s) DESC
                LIMIT %s
            """
            cur.execute(query, (query_vec.tolist(), embedding_type, query_vec.tolist(), alpha, 1-alpha, k))
            return cur.fetchall()
        finally:
            cur.close()
            conn.close()
