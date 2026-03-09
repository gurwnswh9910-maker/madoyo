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
        return {"status": "SUCCESS", "results": results}
    except Exception as e:
        # 에러 발생 시 상세 내용 반환
        import traceback
        error_msg = f"에러 발생: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        return {"status": "FAILED", "error": str(e)}

@celery_app.task(name="process_excel_task", bind=True)
def process_excel_task(self, file_path, uploader_id=None, is_global=True):
    """
    업로드된 엑셀 파일을 파싱하여 DB에 저장하고 임베딩을 생성하는 비동기 태스크
    """
    import pandas as pd
    from api.database import SessionLocal, MABEmbedding
    from embedding_utils import EmbeddingManager
    
    db = SessionLocal()
    emb_mgr = EmbeddingManager()
    
    try:
        df = pd.read_excel(file_path)
        total = len(df)
        processed = 0
        
        for idx, row in df.iterrows():
            content = str(row.get("본문", row.get("내용", ""))).strip()
            mss = float(row.get("MSS", row.get("성과지표", 0)))
            
            if not content: continue
            
            # 임베딩 생성 (Gemini 호출)
            vector = emb_mgr.get_embedding(content)
            
            new_entry = MABEmbedding(
                content_text=content,
                mss_score=mss,
                embedding=vector,
                uploader_id=uploader_id,
                is_global=is_global,
                metadata_json={"source": "excel_upload", "filename": os.path.basename(file_path)}
            )
            db.add(new_entry)
            processed += 1
            
            # 10개마다 상태 업데이트 및 커밋
            if processed % 10 == 0:
                db.commit()
                self.update_state(state="PROGRESS", meta={"current": processed, "total": total})
        
        db.commit()
        # 임시 파일 삭제
        if os.path.exists(file_path):
            os.remove(file_path)
            
        return {"status": "SUCCESS", "processed_count": processed}
    except Exception as e:
        db.rollback()
        return {"status": "FAILED", "error": str(e)}
    finally:
        db.close()

@celery_app.task(name="update_post_performance_task")
def update_post_performance_task(gen_id):
    """
    특정 생성 ID와 연결된 발행 URL의 성과를 수집하고 DB에 반영합니다.
    """
    from api.database import SessionLocal, MABFeedback, MABEmbedding, Generation
    from api.services.scraper_service import get_threads_metrics, calculate_mss_from_metrics
    
    db = SessionLocal()
    try:
        feedback = db.query(MABFeedback).filter(MABFeedback.gen_id == gen_id).first()
        if not feedback or not feedback.published_url:
            return "No URL to track"
        
        # 스크래핑 수행
        metrics = get_threads_metrics(feedback.published_url)
        if metrics:
            feedback.performance = metrics
            new_mss = calculate_mss_from_metrics(metrics)
            
            # 연결된 임베딩(MABEmbedding)의 MSS 점수 업데이트 시도 (정확한 매칭 필요)
            # 일단 피드백 테이블 업데이트만 진행
            db.commit()
            return f"Updated MSS: {new_mss} for {feedback.published_url}"
        return "Failed to fetch metrics"
    finally:
        db.close()

@celery_app.task(name="beat_schedule_performance_checks")
def beat_schedule_performance_checks():
    """
    성과 수집이 필요한 대상들을 찾아 추적 태스크를 예약합니다.
    """
    from api.database import SessionLocal, MABFeedback
    from datetime import datetime, timedelta
    
    db = SessionLocal()
    try:
        # 아직 성과 수집이 안 된 발행물 검색
        pending_feedbacks = db.query(MABFeedback)\
            .filter(MABFeedback.published_url != None)\
            .filter(MABFeedback.performance == {})\
            .all()
        
        for fb in pending_feedbacks:
            update_post_performance_task.delay(fb.gen_id)
            
        return f"Scheduled {len(pending_feedbacks)} performance update tasks"
    finally:
        db.close()

# Celery Beat 스케줄 설정 (6시간마다 실행)
celery_app.conf.beat_schedule = {
    "check-post-performance-every-6-hours": {
        "task": "beat_schedule_performance_checks",
        "schedule": 3600 * 6, # 6시간
    },
}
