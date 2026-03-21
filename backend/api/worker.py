import os
import sys
from celery import Celery
from dotenv import load_dotenv

load_dotenv()


# Redis URL 설정 (기본값: localhost:6379/0)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Celery 앱 인스턴스 생성
celery_app = Celery(
    "copy_worker",
    broker=REDIS_URL,
    backend=REDIS_URL
)

# Celery 설정 최적화
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Seoul",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600, # 최대 1시간
)

# 코어 모듈 경로 추가 (backend 상위 디렉토리)
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

@celery_app.task(name="optimize_copy_task", bind=True)
def optimize_copy_task(self, original_copy, product_focus, api_key=None, model_name=None, user_id=None):
    """
    카피 생성 최적화 작업을 수행하는 비동기 태스크
    """
    from optimize_copy_v2 import run_optimization
    
    # 작업 상태 업데이트 (시작 알림)
    self.update_state(state="PROGRESS", meta={"status": "분석 및 전략 추출 시작..."})
    
    try:
        # 실제 최적화 엔진 실행
        results = run_optimization(
            original_copy=original_copy,
            product_focus=product_focus,
            api_key=api_key,
            model_name=model_name,
            user_id=user_id
        )
        
        # 결과 포맷팅 (schemas.py의 CopyResult 형식에 맞춤)
        formatted_copies = []
        for i, res in enumerate(results):
            formatted_copies.append({
                "rank": i + 1,
                "copy_text": res.get("copy", ""),
                "strategy": res.get("strategy", "전략"),
                "score": res.get("score_data", {}).get("mss_score_estimate", 0),
                "reason": res.get("score_data", {}).get("reason", "")
            })
            
        return {"status": "SUCCESS", "results": {"copies": formatted_copies}}
    except Exception as e:
        # 에러 발생 시 상세 내용 반환
        import traceback
        error_msg = f"에러 발생: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        return {"status": "FAILED", "error": str(e)}

@celery_app.task(name="process_excel_task", bind=True)
def process_excel_task(self, file_path, uploader_id=None, is_global=True, bulk_job_id=None):
    """
    업로드된 엑셀 파일을 파싱하여 URL 목록을 추출하고 각각 비동기 태스크로 분배합니다.
    """
    import pandas as pd
    import uuid as uuid_pkg
    
    print(f"[Worker] Starting process_excel_task for {file_path}, Job: {bulk_job_id}")
    
    try:
        if file_path.endswith('.csv'):
             df = pd.read_csv(file_path)
        else:
             df = pd.read_excel(file_path)
             
        print(f"[Worker] File loaded. Rows: {len(df)}, Columns: {df.columns.tolist()}")
        urls_to_process = []
        
        # '링크' 또는 'URL' 칼럼 찾기
        url_col = None
        for col in df.columns:
            if '링크' in str(col) or 'url' in str(col).lower():
                url_col = col
                break
                
        if url_col:
            urls_to_process = df[url_col].dropna().tolist()
            print(f"[Worker] Found {len(urls_to_process)} URLs in column '{url_col}'")
        else:
            print(f"[Worker] FAILED: No '링크' or 'URL' column found.")
            return {"status": "FAILED", "error": "엑셀에 '링크' 혹은 'URL' 컬럼이 없습니다."}
            
        from api.database import SessionLocal, Generation
        db = SessionLocal()
        try:
            # uploader_id를 UUID 객체로 변환 (DB 저장용)
            user_uuid = None
            if uploader_id:
                try:
                    user_uuid = uuid_pkg.UUID(uploader_id)
                except:
                    user_uuid = uploader_id
                    
            # URL마다 DB에 pending (대기중) 상태로 껍데기 저장 후 워커 생성
            for url in urls_to_process:
                url_str = str(url).strip()
                if "http" in url_str:
                    gen = Generation(
                        bulk_job_id=bulk_job_id,
                        user_id=user_uuid,
                        input_config={"url": url_str, "scraped_text": "💡 처리 대기 중..."},
                        results={},
                        status="pending"
                    )
                    db.add(gen)
                    db.commit()
                    db.refresh(gen)
                    print(f"[Worker] Inserted pending gen for {url_str}, GenID: {gen.id}")
                    
                    scrape_and_generate_single_task.delay(
                        url=url_str,
                        bulk_job_id=bulk_job_id,
                        uploader_id=uploader_id, # delay에는 원래값 전달
                        is_global=is_global,
                        generation_id=str(gen.id)
                    )
        finally:
            db.close()
        
        # 임시 파일 삭제
        if os.path.exists(file_path):
            os.remove(file_path)
            
        return {"status": "SUCCESS", "spawned_tasks": len(urls_to_process)}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}

@celery_app.task(name="scrape_and_generate_single_task", bind=True)
def scrape_and_generate_single_task(self, url, bulk_job_id, uploader_id=None, is_global=True, generation_id=None):
    """
    [Track 1] 단일 URL 스크래핑 -> DB 학습 -> 카피 대량 생성 로직
    """
    import uuid as uuid_pkg
    print(f"[Worker] Submitting task for {url}, GenID: {generation_id}")
    
    from api.database import SessionLocal, MABEmbedding, Generation
    from embedding_utils import EmbeddingManager
    from api.services.scraper_service import get_threads_full_data, calculate_mss_from_metrics
    from optimize_copy_v2 import run_optimization
    from api.config import GEMINI_API_KEY, MODEL_NAME
    
    db = SessionLocal()
    emb_mgr = EmbeddingManager()
    
    try:
        # 1. 스크래핑 및 지표 추출
        data = get_threads_full_data(url)
        if not data or not data.get("content_text"):
            if generation_id:
                gid = uuid_pkg.UUID(generation_id) if isinstance(generation_id, str) else generation_id
                generation = db.query(Generation).filter(Generation.id == gid).first()
                if generation:
                    generation.input_config = {"url": url, "scraped_text": "스크래핑 실패: 텍스트를 찾을 수 없거나 차단됨"}
                    generation.status = "error"
                    db.commit()
            return {"status": "FAILED", "error": "스크래핑 데이터가 없거나 텍스트를 찾을 수 없습니다."}
            
        content_text = data["content_text"]
        mss = calculate_mss_from_metrics(data)
        
        # 2. 임베딩(학습 데이터 추가)
        vector = emb_mgr.get_embedding(content_text)
        new_entry = MABEmbedding(
            content_text=content_text,
            mss_score=mss,
            embedding=vector,
            uploader_id=uploader_id,
            is_global=is_global,
            metadata_json={"source": "url_bulk", "url": url, "metrics": data}
        )
        db.add(new_entry)
        db.commit() # 학습 데이터 적재 완료
        
        # 3. 마케팅 소구점 및 맥락 분석 (Vision 기반)
        print(f"[Worker] Extracting marketing focus for {url}...")
        from google import genai
        from marketing_focus_extractor import extract_marketing_focus
        
        client = genai.Client(api_key=GEMINI_API_KEY)
        # 스크래핑된 지표와 미디어를 기반으로 소구점 추출
        product_focus = extract_marketing_focus(
            client=client,
            model_name=MODEL_NAME,
            product_name="제품", # 상세 상품명을 모를 경우 placeholder
            original_text=content_text,
            threads_images=data.get("image_urls", [])
        )
        
        # 4. 카피 생성 (최신 MAB 반영)
        results = run_optimization(
            original_copy=content_text,
            product_focus=product_focus, # 분석된 소구점 전달
            api_key=GEMINI_API_KEY,
            model_name=MODEL_NAME,
            user_id=uploader_id
        )
        
        # 결과 포맷팅
        formatted_copies = []
        for i, res in enumerate(results):
            formatted_copies.append({
                "rank": i + 1,
                "copy_text": res.get("copy", ""),
                "strategy": res.get("strategy", "전략"),
                "score": res.get("score_data", {}).get("mss_score_estimate", 0),
                "reason": res.get("score_data", {}).get("reason", "")
            })
        
        # 4. DB 히스토리 업데이트
        if generation_id:
            gid = uuid_pkg.UUID(generation_id) if isinstance(generation_id, str) else generation_id
            generation = db.query(Generation).filter(Generation.id == gid).first()
            if generation:
                print(f"[Worker] Updating Generation record {gid} to completed")
                generation.input_config = {"url": url, "scraped_text": content_text[:100]}
                generation.results = {"copies": formatted_copies}
                generation.status = "completed"
                db.commit()
                return {"status": "SUCCESS", "url": url}
        
        # (Fall-back) uploader_id를 매핑해서 직접 새로 만듦
        user_uuid = None
        if uploader_id:
            try:
                user_uuid = uuid_pkg.UUID(uploader_id) if isinstance(uploader_id, str) else uploader_id
            except:
                user_uuid = uploader_id

        generation = Generation(
            bulk_job_id=bulk_job_id,
            user_id=user_uuid,
            input_config={"url": url, "scraped_text": content_text[:100]},
            results={"copies": formatted_copies},
            status="completed"
        )
        db.add(generation)
        db.commit()
        print(f"[Worker] Success (Fallback ID used) for {url}")
        return {"status": "SUCCESS", "url": url}
        
    except Exception as e:
        db.rollback()
        return {"status": "FAILED", "error": str(e)}
    finally:
        db.close()

@celery_app.task(name="update_post_performance_task", bind=True)
def update_post_performance_task(self, url, feedback_id):
    """
    [Track 2] 24시간 뒤 실행되어 URL 성과 수집, 임베딩 추가, 크레딧 환급 처리
    """
    from api.database import SessionLocal, MABFeedback, MABEmbedding, User
    from embedding_utils import EmbeddingManager
    from api.services.scraper_service import get_threads_full_data, calculate_mss_from_metrics
    
    db = SessionLocal()
    emb_mgr = EmbeddingManager()
    
    try:
        feedback = db.query(MABFeedback).filter(MABFeedback.gen_id == feedback_id).first()
        if not feedback:
            return "Feedback entry not found"
            
        if feedback.status != "pending":
            return f"Feedback already processed: {feedback.status}"
            
        data = get_threads_full_data(url)
        if not data or not data.get("content_text"):
            feedback.status = "rejected"
            db.commit()
            return "No data scraped or post deleted"
            
        # (코사인 유사도 대신) 단순히 DB에 있는 URL인지 검증은 프론트/API단에서 사전 차단함
        # 지표 산출
        mss = calculate_mss_from_metrics(data)
        content_text = data["content_text"]
        
        # 임베딩 추가 (지식 최신화)
        vector = emb_mgr.get_embedding(content_text)
        entry = MABEmbedding(
            content_text=content_text,
            mss_score=mss,
            embedding=vector,
            is_global=True,
            metadata_json={"source": "feedback_reward", "url": url, "metrics": data}
        )
        db.add(entry)
        
        # 성과 및 보상 기록
        feedback.performance = data
        feedback.status = "completed"
        feedback.reward_credits = 2  # 보상 2 크레딧
        
        # 유저 크레딧 충전
        generation = feedback.generation # SQLAlchemy relationship needed or join, let's look up user
        from api.database import Generation
        gen = db.query(Generation).filter(Generation.id == feedback_id).first()
        if gen and gen.user_id:
            user = db.query(User).filter(User.id == gen.user_id).first()
            if user:
                user.credits += feedback.reward_credits
        
        db.commit()
        return f"Success: {url} -> Given 2 credits, MSS: {mss}"
        
    except Exception as e:
        db.rollback()
        from api.database import MABFeedback
        feedback = db.query(MABFeedback).filter(MABFeedback.gen_id == feedback_id).first()
        if feedback:
            feedback.status = "error"
            db.commit()
        return f"Error: {e}"
    finally:
        db.close()
