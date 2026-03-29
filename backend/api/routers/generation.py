"""
카피 생성 API 라우터.
/api/generate — 카피 생성 메인 엔드포인트
/api/refine   — 챗봇 카피 수정 엔드포인트
/api/health   — 헬스체크
"""
import os
import sys
import time
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from api.auth_middleware import get_current_user

# 코어 모듈 경로 추가 (작동중코드/ 디렉토리)
_code_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _code_dir not in sys.path:
    sys.path.insert(0, _code_dir)

from api.schemas import (
    GenerateRequest,
    GenerateResponse,
    CopyResult,
    RefineRequest,
    RefineResponse,
    HealthResponse,
    TaskResponse,
    TaskStatusResponse,
)
from api.config import GEMINI_API_KEY, MODEL_NAME, FALLBACK_MODEL_NAME, BASE_PATH, USE_CELERY, REWARD_COUNTDOWN_SEC
from api.services.context_builder import build_context

router = APIRouter()

# 로컬(윈도우) 환경용 인메모리 태스크 저장소 (Redis 우회)
LOCAL_TASKS = {}


# ════════════════════════════════════════════════════════════════
# 헬스체크
# ════════════════════════════════════════════════════════════════

@router.get("/health", response_model=HealthResponse)
def health_check():
    """서버 상태 확인"""
    data_cache_exists = os.path.exists(os.path.join(BASE_PATH, "data_cache.pkl"))
    embeddings_exist = os.path.exists(os.path.join(BASE_PATH, "embeddings.pkl"))
    return HealthResponse(
        status="ok",
        model=MODEL_NAME,
        data_loaded=data_cache_exists and embeddings_exist,
    )


# ════════════════════════════════════════════════════════════════
# 카피 생성 (★ AI 에이전트 필독: 절대 동기식으로 바꾸지 마시오 ★)
# 이 엔드포인트는 시간(30초 이상)이 걸리는 스크래핑/LLM 로직이 있으므로,
# 무조건 작업(Task_ID)을 먼저 발급하고 백그라운드(`BackgroundTasks`)로 던져야 합니다.
# 로컬 코드(`작동중코드`)를 API에 이식할 때, 응답 대기(Blocking) 형태로 짜면 
# Render 배포 시 100% Timeout 서버 다운이 발생합니다.
# ════════════════════════════════════════════════════════════════

@router.post("/generate", response_model=TaskResponse)
def generate_copy(request: GenerateRequest, background_tasks: BackgroundTasks, current_user=Depends(get_current_user)):
    """
    카피 생성 요청 접수 (비동기).
    
    [MVP V7] 로그인 및 크레딧(1차감) 필수.
    입력: 참고 카피 / 이미지 URL / 레퍼런스 URL 중 최소 1개
    출력: task_id (결과 조회를 위해 필요)
    """
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY가 설정되지 않았습니다.")
    
    from api.database import SessionLocal, Generation, User
    db = SessionLocal()
    
    try:
        # [MVP V7] 크레딧 체크 및 차감
        user = db.query(User).filter(User.id == current_user.id).first()
        if not user or user.credits < 1:
            raise HTTPException(status_code=403, detail="크레딧이 부족합니다. (필요: 1)")
        
        user.credits -= 1
        db.commit()

        # Step 1: 비동기 태스크 호출 (스크래핑/분석 포함)
        if USE_CELERY:
            from api.worker import optimize_copy_task
            # Celery 사용 시에도 DB 레코드를 먼저 생성하여 일관성 유지
            gen = Generation(
                status="pending",
                input_config={
                    "reference_copy": request.reference_copy,
                    "image_urls": request.image_urls,
                    "reference_url": request.reference_url,
                    "appeal_point": request.appeal_point
                }
            )
            db.add(gen)
            db.commit()
            db.refresh(gen)
            
            task = optimize_copy_task.delay(
                reference_copy=request.reference_copy,
                image_urls=request.image_urls,
                reference_url=request.reference_url,
                appeal_point=request.appeal_point,
                api_key=GEMINI_API_KEY,
                model_name=MODEL_NAME,
                user_id=None # 현재는 단일 유저
            )
            return TaskResponse(task_id=str(gen.id), status="PENDING")
        else:
            # [ONLINE-ISOLATION] 환경 변수에 따른 엔진 스위칭
            import uuid
            # DB 레코드 생성 (Task ID 역할)
            gen = Generation(
                status="processing",
                input_config={
                    "reference_copy": request.reference_copy,
                    "image_urls": request.image_urls,
                    "reference_url": request.reference_url,
                    "appeal_point": request.appeal_point
                }
            )
            db.add(gen)
            db.commit()
            db.refresh(gen)
            task_id = str(gen.id)

            # 대표님 지침에 따라 로컬 테스트(오프라인 모드)를 완전히 제거하고 무조건 Supabase 모드 사용
            def run_local_task(t_id, req, api_key, m_name, u_id):
                from api.database import SessionLocal, Generation
                import uuid as uuid_pkg
                _db = SessionLocal()
                
                print("🚀 [클라우드 전용 아키텍처] 무조건 Supabase DB 네이티브 가동 (optimize_copy_online)")
                from optimize_copy_online import run_optimization_online as run_optimized_engine
                
                try:
                    # [MVP V7] Selenium(Chrome) 임시 비활성화하여 512MB RAM OOM 방지
                    # reference_url이 있어도 스크래핑을 건너뛰고 텍스트/이미지만으로 분석합니다.
                    product_focus = None
                    original_copy = req.reference_copy or ""

                    if req.reference_url:
                        print(f"[MVP V7] URL Scraping Bypassed: {req.reference_url}")
                        # URL 정보는 나중에 로컬에서 처리할 수 있도록 로그로 남기고 기본 컨텍스트 구성
                        if not original_copy:
                            original_copy = "URL 분석 대기 중 (텍스트를 입력해 주세요)"

                    # 이미지 분석은 Chrome을 쓰지 않으므로 정상 유지
                    from api.services.context_builder import build_context
                    product_focus, build_copy = build_context(
                        api_key=api_key,
                        model_name=m_name,
                        reference_copy=req.reference_copy,
                        image_urls=req.image_urls,
                        reference_url=None, # URL 스크래핑 건너뜀
                        appeal_point=req.appeal_point,
                    )
                    
                    if build_copy:
                        original_copy = build_copy

                    # original_copy 보정
                    if not original_copy or not original_copy.strip():
                        if isinstance(product_focus, dict):
                            original_copy = product_focus.get("marketing_insight", "제품 홍보 카피")
                        else:
                            original_copy = str(product_focus)

                    results = run_optimized_engine(
                        original_copy=original_copy,
                        product_focus=product_focus,
                        api_key=api_key,
                        model_name=m_name,
                        user_id=u_id
                    )
                    formatted_copies = []
                    for i, res in enumerate(results["copies"]):
                        formatted_copies.append({
                            "rank": i + 1,
                            "copy_text": res.get("copy", ""),
                            "strategy": res.get("strategy", "전략"),
                            "score": res.get("score_data", {}).get("mss_score_estimate", 0),
                            "reason": res.get("score_data", {}).get("reason", "")
                        })
                    
                    # DB 업데이트 (UUID 변환 최적화)
                    task_uuid = uuid_pkg.UUID(t_id)
                    gen_record = _db.query(Generation).filter(Generation.id == task_uuid).first()
                    if gen_record:
                        gen_record.status = "completed"
                        gen_record.results = {
                            "copies": formatted_copies,
                            "original_rank": results.get("original_rank", -1),
                            "total_candidates": results.get("total_candidates", 0)
                        }
                        _db.commit()
                except Exception as e:
                    import traceback
                    print(traceback.format_exc())
                    # 에러 상태 기록
                    task_uuid = uuid_pkg.UUID(t_id)
                    gen_record = _db.query(Generation).filter(Generation.id == task_uuid).first()
                    if gen_record:
                        gen_record.status = "error"
                        gen_record.results = {"error": str(e)}
                        _db.commit()
                finally:
                    _db.close()

            background_tasks.add_task(
                run_local_task,
                t_id=task_id,
                req=request,
                api_key=GEMINI_API_KEY,
                m_name=MODEL_NAME,
                u_id=str(current_user.id)
            )
            return TaskResponse(task_id=task_id, status="PENDING")

    except Exception as e:
        print(f"\n[API] ❌ 카피 생성 요청 중 오류: {e}")
        raise HTTPException(status_code=500, detail=f"작업 접수 중 오류 발생: {str(e)}")
    finally:
        db.close()


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str):
    """
    비동기 작업의 진행 상태 및 결과를 조회합니다 (Polling).
    """
    if not USE_CELERY:
        from api.database import SessionLocal, Generation
        import uuid
        db = SessionLocal()
        try:
            try:
                gid = uuid.UUID(task_id)
            except:
                return {"task_id": task_id, "status": "FAILURE", "error": "Invalid Task ID format"}
                
            gen = db.query(Generation).filter(Generation.id == gid).first()
            if gen:
                # DB 상태 -> TaskStatusResponse 맵핑
                status_map = {
                    "processing": "PROGRESS",
                    "completed": "SUCCESS",
                    "error": "FAILURE",
                    "pending": "PENDING"
                }
                status = status_map.get(gen.status, "PROGRESS")
                response = {"task_id": task_id, "status": status}
                if gen.status == "completed":
                    response["result"] = gen.results
                elif gen.status == "error":
                    response["error"] = gen.results.get("error", "Unknown error")
                return response
            else:
                return {"task_id": task_id, "status": "FAILURE", "error": "Task not found in database"}
        finally:
            db.close()

    from api.worker import celery_app
    from celery.result import AsyncResult
    
    res = AsyncResult(task_id, app=celery_app)
    
    response = {
        "task_id": task_id,
        "status": res.status,
    }
    
    if res.ready():
        if res.successful():
            result_data = res.result
            if isinstance(result_data, dict) and result_data.get("status") == "SUCCESS":
                response["result"] = result_data.get("results")
            else:
                response["status"] = "FAILURE"
                response["error"] = result_data.get("error") if isinstance(result_data, dict) else str(res.result)
        else:
            response["status"] = "FAILURE"
            response["error"] = str(res.result)
            
    return response


@router.get("/generations/me")
def get_my_generations(current_user=Depends(get_current_user)):
    """
    내 카피 생성 히스토리를 반환합니다. (최대 1일 보관)
    """
    from api.database import SessionLocal, Generation, MABFeedback
    from datetime import datetime, timedelta
    
    db = SessionLocal()
    try:
        # 1일 전 데이터까지만 조회 및 자신의 것만
        yesterday = datetime.utcnow() - timedelta(days=1)
        generations = db.query(Generation)\
            .filter(Generation.created_at >= yesterday)\
            .filter(Generation.user_id == current_user.id)\
            .order_by(Generation.created_at.desc())\
            .limit(50).all()
            
        result = []
        for gen in generations:
            # 피드백 제출 상태도 함께 반환
            feedback = db.query(MABFeedback).filter(MABFeedback.gen_id == gen.id).first()
            reward_status = feedback.status if feedback else None
            
            result.append({
                "id": str(gen.id),
                "bulk_job_id": gen.bulk_job_id,
                "created_at": gen.created_at,
                "input_config": gen.input_config,
                "results": gen.results,
                "status": gen.status,
                "reward_status": reward_status
            })
            
        return {"generations": result}
    finally:
        db.close()

@router.get("/generations/{gen_id}")
def get_generation_detail(gen_id: str, current_user=Depends(get_current_user)):
    """
    특정 카피 생성 상세 정보를 조회합니다.
    """
    from api.database import SessionLocal, Generation, MABFeedback
    import uuid
    
    db = SessionLocal()
    try:
        try:
            gid = uuid.UUID(gen_id)
        except:
            raise HTTPException(status_code=400, detail="유효하지 않은 ID 형식입니다.")
            
        gen = db.query(Generation).filter(Generation.id == gid).first()
        if not gen:
            raise HTTPException(status_code=404, detail="해당 기록을 찾을 수 없습니다.")
            
        if gen.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")
            
        feedback = db.query(MABFeedback).filter(MABFeedback.gen_id == gen.id).first()
        
        return {
            "id": str(gen.id),
            "created_at": gen.created_at,
            "input_config": gen.input_config,
            "results": gen.results,
            "status": gen.status,
            "reward_status": feedback.status if feedback else None
        }
    finally:
        db.close()

from pydantic import BaseModel
class SubmitUrlRequest(BaseModel):
    url: str

@router.post("/generations/{gen_id}/submit-url")
def submit_feedback_url(gen_id: str, req: SubmitUrlRequest):
    """
    [Track 2] 생성된 카피를 발행한 URL을 제출 → DB에 실행 예약 시각 저장.
    Celery/Redis 없이, cron-job.org의 주기적 호출로 처리합니다.
    """
    import re
    from datetime import datetime, timedelta
    from api.database import SessionLocal, MABFeedback

    if not re.match(r'^https?://(www\.)?threads\.net/.*', req.url):
        raise HTTPException(status_code=400, detail="유효한 Threads URL이 아닙니다.")

    db = SessionLocal()
    try:
        existing = db.query(MABFeedback).filter(MABFeedback.published_url == req.url).first()
        if existing:
            raise HTTPException(status_code=400, detail="이미 보상이 신청된 URL입니다.")

        feedback = db.query(MABFeedback).filter(MABFeedback.gen_id == gen_id).first()
        if not feedback:
            feedback = MABFeedback(gen_id=gen_id)
            db.add(feedback)

        feedback.published_url = req.url
        feedback.status = "completed" # [MVP V7] 즉시 완료 처리
        feedback.scheduled_at = datetime.utcnow()
        feedback.reward_credits = 2
        
        # [MVP V7] 즉시 크레딧 지급
        from api.database import User, Generation
        gen = db.query(Generation).filter(Generation.id == gen_id).first()
        if gen and gen.user_id:
            user = db.query(User).filter(User.id == gen.user_id).first()
            if user:
                user.credits += 2
        
        db.commit()

        return {
            "status": "success",
            "message": "즉시 보상 완료! 2 크레딧이 지급되었습니다.",
            "scheduled_at": feedback.scheduled_at.isoformat()
        }
    finally:
        db.close()


@router.post("/process-rewards")
def process_due_rewards(background_tasks: BackgroundTasks):
    """
    [Cron Endpoint] 10분마다 cron-job.org 등 외부 서비스가 POST 호출.
    scheduled_at이 지났고 아직 pending인 피드백을 찾아 성과 수집 + 크레딧 지급 처리.
    Redis/Celery 없이 무료로 동작합니다.
    """
    from datetime import datetime
    from api.database import SessionLocal, MABFeedback, MABEmbedding, Generation, User

    db = SessionLocal()
    try:
        now = datetime.utcnow()
        due_feedbacks = (
            db.query(MABFeedback)
            .filter(MABFeedback.status.in_(["pending", "staged"]))
            .filter(MABFeedback.scheduled_at <= now)
            .filter(MABFeedback.scheduled_at.isnot(None))
            .limit(20)
            .all()
        )

        if not due_feedbacks:
            return {"status": "ok", "processed": 0, "message": "처리할 항목 없음"}

        due_ids = [f.gen_id for f in due_feedbacks]
        # processing 상태로 임시 잠금
        for f in due_feedbacks:
            f.status = "processing"
        db.commit()
        db.close()

        def _run_reward_check(gen_ids):
            from api.database import SessionLocal, MABFeedback, MABEmbedding, Generation, User
            from api.services.scraper_service import get_threads_full_data, calculate_mss_from_metrics
            import os
            import json
            from datetime import datetime, timedelta

            IS_ONLINE = os.getenv("IS_ONLINE", "False").lower() == "true"
            if IS_ONLINE:
                from embedding_utils_online import EmbeddingManager
            else:
                from embedding_utils import EmbeddingManager

            _db = SessionLocal()
            emb_mgr = EmbeddingManager()
            try:
                for gid in gen_ids:
                    feedback = _db.query(MABFeedback).filter(MABFeedback.gen_id == gid).first()
                    if not feedback: continue
                    
                    # ══════════════════════════════════════════════════════════
                    # [Phase 1: pending] 성과 수집 및 Gemini File API 업로드
                    # ══════════════════════════════════════════════════════════
                    if feedback.performance.get("_phase") != "staged":
                        print(f"[Reward Phase 1] 성과 수집 시작: {feedback.published_url}")
                        try:
                            url = feedback.published_url
                            data = get_threads_full_data(url)

                            if not data or not data.get("content_text"):
                                feedback.status = "rejected"
                                _db.commit()
                                continue

                            mss = calculate_mss_from_metrics(data)
                            content_text = data["content_text"]
                            
                            performance_data = {
                                "본문": content_text,
                                "조회수": data["views"],
                                "좋아요": data["likes"],
                                "댓글": data["replies"],
                                "리포스트": data.get("reposts", 0),
                                "공유수": data.get("shares", 0),
                                "첫댓글조회수": data.get("first_reply_views", 0),
                                "작성시간": data.get("created_at", ""),
                                "mss_score": mss,
                                "_phase": "staged"
                            }

                            # 이미지 업로드 (Gemini File API)
                            file_api_info = {}
                            if IS_ONLINE:
                                media_urls = data.get("image_urls", [])
                                if media_urls:
                                    temp_path, is_temp = emb_mgr._prepare_media_data(media_urls[0])
                                    if temp_path:
                                        file_obj = emb_mgr.upload_to_gemini_file_api(temp_path)
                                        if file_obj:
                                            file_api_info = {"name": file_obj.name, "uri": file_obj.uri}
                                        if is_temp: os.remove(temp_path)

                            performance_data["file_api"] = file_api_info
                            feedback.performance = performance_data
                            
                            # ✅ 1시간 유예 상태로 전이
                            feedback.status = "staged"
                            feedback.scheduled_at = datetime.utcnow() + timedelta(hours=1)
                            _db.commit()
                            print(f"[Reward Phase 1] ✅ 수집 완료 및 File API 업로드. 1시간 유예 시작.")
                            continue

                        except Exception as e:
                            feedback.status = "error"
                            _db.commit()
                            print(f"[Reward Phase 1] ❌ 에러: {e}")
                            continue

                    # ══════════════════════════════════════════════════════════
                    # [Phase 2: staged] 지연 임베딩 및 파일 삭제
                    # ══════════════════════════════════════════════════════════
                    else:
                        print(f"[Reward Phase 2] 지연 임베딩 시작: {feedback.published_url}")
                        try:
                            perf = feedback.performance
                            file_info = perf.get("file_api", {})
                            file_uri = file_info.get("uri")
                            file_name = file_info.get("name")
                            content_text = perf.get("본문")
                            mss = perf.get("mss_score", 0.0)

                            if IS_ONLINE and file_uri:
                                # 트리플 벡터 동시 생성
                                text_vec = emb_mgr.get_text_embedding(text=content_text, use_db=False)
                                visual_vec = emb_mgr.get_multimodal_embedding(file_uri=file_uri, use_db=False)
                                joint_vec = emb_mgr.get_multimodal_embedding(text=content_text, file_uri=file_uri, use_db=False)
                                
                                if text_vec is not None and visual_vec is not None and joint_vec is not None:
                                    # ✅ [무결성 검증] 텍스트 벡터와 조인트 벡터가 유의미하게 다른지 자체 체크
                                    similarity = emb_mgr.calculate_similarity(text_vec, joint_vec)
                                    is_distinct = similarity < 0.999
                                    
                                    if not is_distinct:
                                        print(f"[Reward Phase 2] ⚠️ 조인트 벡터 검증 실패 (유사도 {similarity:.6f}). 인덱싱 미완료 가능성. 10분 후 재시도.")
                                        feedback.status = "staged"
                                        feedback.scheduled_at = datetime.utcnow() + timedelta(minutes=10)
                                        _db.commit()
                                        continue
                                    
                                    print(f"[Reward Phase 2] ✨ 트리플 벡터 검증 통과 (유사도 {similarity:.6f}). 보상 마감 진행.")
                                    
                                    # ✅ 응답이 확실히 오면 파일 삭제
                                    emb_mgr.delete_from_gemini_file_api(file_name)
                                    
                                    # 임베딩 학습 데이터 저장
                                    perf["similarity_score"] = float(similarity)
                                    meta_data = {"source": "feedback_reward", "url": feedback.published_url, "metrics": perf}
                                    
                                    # 3종 벡터 한 번에 저장
                                    emb_mgr.save_triple_to_db(
                                        content_text=content_text,
                                        text_vec=text_vec,
                                        visual_vec=visual_vec,
                                        joint_vec=joint_vec,
                                        mss_score=mss,
                                        is_global=True,
                                        metadata=meta_data
                                    )
                                else:
                                    # 임베딩 호출 자체 실패 시 재시도
                                    print(f"[Reward Phase 2] ⚠️ 일부 임베딩 호출 실패. 10분 후 재시도.")
                                    feedback.status = "staged"
                                    feedback.scheduled_at = datetime.utcnow() + timedelta(minutes=10)
                                    _db.commit()
                                    continue
                            else:
                                # 이미지가 없거나 로컬 환경인 경우 즉시 마감
                                text_vec = emb_mgr.get_text_embedding(content_text, use_db=False)
                                if text_vec is not None:
                                    if IS_ONLINE:
                                        meta_data = {"source": "feedback_reward", "url": feedback.published_url, "metrics": perf}
                                        emb_mgr.save_triple_to_db(content_text, text_vec, None, None, mss, True, meta_data)
                                    else:
                                        _db.add(MABEmbedding(content_text=content_text, embedding_type="text", mss_score=mss, embedding=text_vec, is_global=True, metadata_json={"source": "feedback_reward", "metrics": perf}))

                            # 최종 마감 및 크레딧
                            feedback.status = "completed"
                            feedback.reward_credits = 2
                            gen = _db.query(Generation).filter(Generation.id == gid).first()
                            if gen and gen.user_id:
                                user = _db.query(User).filter(User.id == gen.user_id).first()
                                if user: user.credits += 2
                            _db.commit()
                            print(f"[Reward Phase 2] 🏁 보상 지급 완료 및 파일 정리 성공.")

                        except Exception as e:
                            print(f"[Reward Phase 2] ❌ 에러: {e}")
                            feedback.status = "error"
                            _db.commit()
            finally:
                _db.close()

        background_tasks.add_task(_run_reward_check, due_ids)
        return {"status": "ok", "processed": len(due_ids), "gen_ids": [str(i) for i in due_ids]}

    except Exception as e:
        db.close()
        raise HTTPException(status_code=500, detail=str(e))

# ════════════════════════════════════════════════════════════════
# 카피 수정 (챗봇)
# ════════════════════════════════════════════════════════════════

@router.post("/refine", response_model=RefineResponse)
def refine_copy(request: RefineRequest, current_user=Depends(get_current_user)):
    """
    생성된 카피를 유저 요청에 맞게 미세 수정합니다.
    가벼운 단일 LLM 호출로 처리합니다.
    """
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY가 설정되지 않았습니다.")

    try:
        from google import genai

        client = genai.Client(api_key=GEMINI_API_KEY)

        # 대화 히스토리 구성
        history_context = ""
        if request.conversation_history:
            for msg in request.conversation_history[-5:]:  # 최근 5개만
                role = msg.get("role", "user")
                content = msg.get("content", "")
                history_context += f"\n{role}: {content}"

        prompt = f"""당신은 SNS 카피 에디터입니다. 원본 카피를 사용자 요청에 맞게 수정하세요.

[원본 카피]
{request.original_copy}

{f'[이전 수정 내역]{history_context}' if history_context else ''}

[사용자 요청]
{request.user_instruction}

[규칙]
1. 원본의 핵심 메시지와 톤은 유지하세요
2. 사용자 요청에 정확히 맞게만 수정하세요
3. 수정된 카피 텍스트만 출력하세요 (설명/주석 금지)

수정된 카피:"""

        try:
            response = client.models.generate_content(
                model=FALLBACK_MODEL_NAME,  # 수정은 가벼운 모델로 충분
                contents=prompt,
            )
            refined = response.text.strip()
            # 불필요한 마크다운/따옴표 제거
            refined = re.sub(r'^[`"\'\s]+|[`"\'\s]+$', "", refined)
            refined = re.sub(r"^```.*?\n|```$", "", refined, flags=re.MULTILINE).strip()
            
            # DB 저장 로직 추가
            from api.database import SessionLocal, Generation, RefineChat
            import uuid
            
            db = SessionLocal()
            try:
                gid = uuid.UUID(request.gen_id)
                # 소유권 확인
                gen = db.query(Generation).filter(Generation.id == gid).first()
                if not gen or gen.user_id != current_user.id:
                    raise HTTPException(status_code=403, detail="접근 권한이 없거나 존재하지 않는 작업입니다.")
                
                new_refine = RefineChat(
                    gen_id=gid,
                    user_instruction=request.user_instruction,
                    refined_copy=refined
                )
                db.add(new_refine)
                db.commit()
            finally:
                db.close()

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"LLM 수정 또는 저장 실패: {str(e)}")

        return RefineResponse(refined_copy=refined)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"카피 수정 중 오류 발생: {str(e)}")
