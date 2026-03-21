import os
import pickle
import hashlib
import requests
import tempfile
import numpy as np
from google import genai
from google.genai import types
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from app_config import GlobalConfig

load_dotenv()

def _is_retriable(exc):
    """429(Rate Limit) / 503(Unavailable) 등 네트워크 에러만 재시도"""
    msg = str(exc).lower()
    return any(code in msg for code in ['429', '503', 'resource exhausted', 'unavailable', 'deadline exceeded'])

class EmbeddingManager:
    def __init__(self, storage_path=None):
        self.storage_path = storage_path or str(GlobalConfig.STORAGE_PATH)
        # migrate_multimodal_v2.py의 구조: {"text": {}, "visual": {}, "multi": {}, "metadata": {}}
        self.embeddings = {"text": {}, "visual": {}, "multi": {}, "metadata": {}}
        self.api_key = GlobalConfig.GEMINI_API_KEY
        self.model_id = GlobalConfig.EMBEDDING_MODEL 
        print(f"🚀 [EmbeddingManager v6.0] Initialized with model: {self.model_id}")
        
        if self.api_key:
            print(f"Initializing Gemini Multimodal Embedding Client (Model: {self.model_id})...")
            self.client = genai.Client(api_key=self.api_key)
        else:
            print("Error: GEMINI_API_KEY not found.")
            self.client = None
            
        self._file_cache = {} # path -> File object
        self.load_storage()

    def load_storage(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "rb") as f:
                    data = pickle.load(f)
                    # 구조 확인 및 병합
                    if isinstance(data, dict) and "text" in data:
                        self.embeddings = data
                    else:
                        # 레거시 데이터가 평면적일 경우 변환
                        self.embeddings["multi"] = data
                print(f"Loaded storage: {len(self.embeddings.get('text', {}))} text, {len(self.embeddings.get('visual', {}))} visual records.")
            except Exception as e:
                print(f"Error loading storage: {e}")

    def save_storage(self):
        try:
            with open(self.storage_path, "wb") as f:
                pickle.dump(self.embeddings, f)
            print(f"Storage saved: {self.storage_path}")
        except Exception as e:
            print(f"Error saving storage: {e}")

    def get_content_hash(self, text: str, image_paths_or_urls: list = None) -> str:
        """migrate_multimodal_v2.py와 동일한 해싱 로직 (Unsorted Join)"""
        img_list = []
        if image_paths_or_urls:
            if isinstance(image_paths_or_urls, str): img_list = [image_paths_or_urls]
            else: img_list = [str(u) for u in image_paths_or_urls] # 정렬안함
        
        # migrate_multimodal_v2.py: f"{text}{'|'.join(media_urls)}"
        payload = f"{text or ''}{'|'.join(img_list)}"
        return hashlib.md5(payload.encode()).hexdigest()

    def _cache_lookup(self, e_type: str, text: str = None, image_paths_or_urls: list = None):
        """2중 조회: MD5 해시 → 원문 텍스트 → 링크 키 순으로 캐시 탐색"""
        bucket = self.embeddings.get(e_type, {})
        if not bucket:
            return None
        
        # 1차: MD5 해시로 조회 (정상 경로)
        c_hash = self.get_content_hash(text, image_paths_or_urls)
        if c_hash in bucket:
            return bucket[c_hash]
        
        # 2차: 원문 텍스트 자체가 키인 경우 (레거시 호환)
        if text and text in bucket:
            return bucket[text]
        
        return None

    def _extract_frame(self, video_path):
        """동영상에서 중간 프레임을 추출하여 임시 이미지 파일로 저장"""
        try:
            import cv2
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened(): return None
            
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            # 중간 지점 프레임 추출
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_count // 2)
            ret, frame = cap.read()
            cap.release()
            
            if ret:
                tf = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                cv2.imwrite(tf.name, frame)
                return tf.name
        except Exception as e:
            print(f"    ⚠️ Frame extraction failed: {e}")
        return None

    def _upload_media(self, path_or_url):
        """File API를 사용하여 미디어를 업로드하고 캐싱함 (URI 재사용용)"""
        if path_or_url in self._file_cache:
            return self._file_cache[path_or_url]

        target_path = path_or_url
        is_temp = False

        if str(path_or_url).startswith("http"):
            try:
                response = requests.get(path_or_url, timeout=15)
                if response.status_code == 200:
                    ct = response.headers.get("Content-Type", "").lower()
                    if "video" in ct or "mp4" in ct or "quicktime" in ct:
                        suffix = ".mp4"
                    elif "png" in ct: suffix = ".png"
                    elif "webp" in ct: suffix = ".webp"
                    else: suffix = ".jpg"
                    
                    tf = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                    tf.write(response.content)
                    tf.close()
                    target_path = tf.name
                    is_temp = True
                else:
                    return None
            except Exception as e:
                print(f"    ⚠️ Download fail: {e}")
                return None

        try:
            if not os.path.exists(target_path):
                return None
            
            # 비디오/이미지 타입 체크
            import mimetypes
            m_type, _ = mimetypes.guess_type(target_path)
            
            # [UPGRADE] 진단 결과: 네이티브 동영상 임베딩은 현재 환경에서 에러 발생
            # 대안: 동영상에서 프레임을 추출하여 이미지로 임베딩 처리
            actual_upload_path = target_path
            is_extracted = False
            
            if m_type and m_type.startswith("video/"):
                extracted_path = self._extract_frame(target_path)
                if extracted_path:
                    actual_upload_path = extracted_path
                    is_extracted = True
                else:
                    return None # 추출 실패 시 스킵

            # [OPTIMIZATION] File API 업로드 대신 바이트 직접 전송 방식으로 변경 (에러 방지)
            with open(actual_upload_path, 'rb') as f:
                img_data = f.read()
            
            # 후처리: 추출된 임시 파일 삭제
            if actual_upload_path != path_or_url and os.path.exists(actual_upload_path):
                try: os.remove(actual_upload_path)
                except: pass
            
            # (data, mime_type) 튜플을 반환하여 직접 Part 생성에 사용
            return img_data, "image/jpeg"
        except Exception as e:
            print(f"    ⚠️ File API Upload Error: {e}")
            return None
        finally:
            if is_temp and os.path.exists(target_path):
                try: os.remove(target_path)
                except: pass

    def _prepare_parts(self, text=None, image_paths_or_urls=None):
        """Prepare Gemini API parts: Text + File API objects."""
        parts = []
        if text:
            parts.append(text)
        
        if image_paths_or_urls:
            # [STABILITY] 멀티모달 임베딩 안정성을 위해 대표 미디어 1개만 사용
            if isinstance(image_paths_or_urls, str):
                image_paths_or_urls = [image_paths_or_urls]
            
            if image_paths_or_urls:
                target_one = image_paths_or_urls[0] 
                res = self._upload_media(target_one) # 이제 (data, mime)을 반환함
                if res:
                    data, m_type = res
                    from google.genai import types
                    p = types.Part.from_bytes(data=data, mime_type=m_type)
                    parts.append(p)
        
        return parts

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(_is_retriable),
        reraise=True
    )
    def get_multimodal_embedding(self, text=None, image_paths_or_urls=None, task_type="RETRIEVAL_DOCUMENT", use_cache=True, only_cache=False):
        if not text and not image_paths_or_urls: return None
        
        c_hash = self.get_content_hash(text, image_paths_or_urls)
        # 검색 타입 결정 (이름 매칭)
        if text and image_paths_or_urls: e_type = "multi"
        elif image_paths_or_urls: e_type = "visual"
        else: e_type = "text"
        
        # 2중 캐시 조회 (해시 → 원문 키 폴백)
        if use_cache:
            cached = self._cache_lookup(e_type, text, image_paths_or_urls)
            if cached is not None:
                return cached
        
        if only_cache: return None

        parts = self._prepare_parts(text, image_paths_or_urls)
        if not parts: return None

        import traceback
        try:
            # 텍스트가 있을 경우 strip() 처리하여 전달 (안전성)
            clean_parts = []
            only_text_part = None
            for p in parts:
                if isinstance(p, str): 
                    s_p = p.strip()
                    clean_parts.append(s_p)
                    only_text_part = s_p
                else: 
                    clean_parts.append(p)

            try:
                result = self.client.models.embed_content(
                    model=self.model_id,
                    contents=clean_parts
                )
            except Exception as inner_e:
                # [SAFE-FALLBACK] 멀티모달 실패 시 텍스트로 전환
                if "400" in str(inner_e) or "INVALID_ARGUMENT" in str(inner_e):
                    if only_text_part:
                        print(f"    ⚠️  Multimodal Embedding 400 Error. Falling back to Text-Only...")
                        result = self.client.models.embed_content(
                            model=self.model_id,
                            contents=only_text_part
                        )
                    else:
                        raise inner_e
                else:
                    raise inner_e

            vector = result.embeddings[0].values
            if use_cache:
                if e_type not in self.embeddings: self.embeddings[e_type] = {}
                self.embeddings[e_type][c_hash] = vector
            return vector
        except Exception as e:
            print(f"    ❌ Embedding API Error: {e}")
            # traceback.print_exc() # 더 상세한 디버깅이 필요할 때만 활성화
            return None
        finally:
            pass

    def get_text_embedding(self, text, task_type="RETRIEVAL_DOCUMENT", use_cache=True, only_cache=False):
        return self.get_multimodal_embedding(text=text, task_type=task_type, use_cache=use_cache, only_cache=only_cache)

    def get_visual_embedding(self, image_paths_or_urls, task_type="RETRIEVAL_DOCUMENT", use_cache=True, only_cache=False):
        return self.get_multimodal_embedding(image_paths_or_urls=image_paths_or_urls, task_type=task_type, use_cache=use_cache, only_cache=only_cache)

    def get_many_text_embeddings(self, texts, task_type="RETRIEVAL_DOCUMENT"):
        results = []
        for t in texts:
            results.append(self.get_text_embedding(t, task_type=task_type))
        self.save_storage()
        return results

    def get_embeddings_matrix(self, texts):
        vectors = self.get_many_text_embeddings(texts)
        valid_vectors = [v for v in vectors if v is not None]
        if not valid_vectors: return np.zeros((0, 3072))
        return np.array(valid_vectors)
