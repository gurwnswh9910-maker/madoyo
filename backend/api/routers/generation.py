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
async def health_check():
    """서버 상태 확인"""
    data_cache_exists = os.path.exists(os.path.join(BASE_PATH, "data_cache.pkl"))
    embeddings_exist = os.path.exists(os.path.join(BASE_PATH, "embeddings.pkl"))
    return HealthResponse(
        status="ok",
        model=MODEL_NAME,
        data_loaded=data_cache_exists and embeddings_exist,
    )


# ════════════════════════════════════════════════════════════════
# 카피 생성
# ════════════════════════════════════════════════════════════════

@router.post("/generate", response_model=TaskResponse)
async def generate_copy(request: GenerateRequest, background_tasks: BackgroundTasks):
    """
    카피 생성 요청 접수 (비동기).
    
    입력: 참고 카피 / 이미지 URL / 레퍼런스 URL 중 최소 1개
    출력: task_id (결과 조회를 위해 필요)
    """
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY가 설정되지 않았습니다.")
    
    try:
        # Step 1: 입력 → product_focus 변환 (이 과정은 가벼우므로 동기 처리 유지)
        product_focus, original_copy = build_context(
            api_key=GEMINI_API_KEY,
            model_name=MODEL_NAME,
            reference_copy=request.reference_copy,
            image_urls=request.image_urls,
            reference_url=request.reference_url,
            appeal_point=request.appeal_point,
        )

        # original_copy 보정
        if not original_copy or not original_copy.strip():
            if isinstance(product_focus, dict):
                original_copy = product_focus.get("marketing_insight", "제품 홍보 카피")
            else:
                original_copy = str(product_focus)

        # Step 2: 비동기 태스크 호출
        if USE_CELERY:
            from api.worker import optimize_copy_task
            task = optimize_copy_task.delay(
                original_copy=original_copy,
                product_focus=product_focus,
                api_key=GEMINI_API_KEY,
                model_name=MODEL_NAME,
                user_id=None # 현재는 단일 유저
            )
            return TaskResponse(task_id=task.id, status="PENDING")
        else:
            # 로컬 BackgroundTasks 사용 (Redis/Celery 우회)
            import uuid
            task_id = str(uuid.uuid4())
            LOCAL_TASKS[task_id] = {"status": "PENDING", "result": None, "error": None}
            
            def run_local_task(t_id, copy_text, focus_text, api_key, m_name, u_id):
                from optimize_copy_v2 import run_optimization
                try:
                    LOCAL_TASKS[t_id]["status"] = "PROGRESS"
                    results = run_optimization(
                        original_copy=copy_text,
                        product_focus=focus_text,
                        api_key=api_key,
                        model_name=m_name,
                        user_id=u_id
                    )
                    formatted_copies = []
                    for i, res in enumerate(results):
                        formatted_copies.append({
                            "rank": i + 1,
                            "copy_text": res.get("copy", ""),
                            "strategy": res.get("strategy", "전략"),
                            "score": res.get("score_data", {}).get("mss_score_estimate", 0),
                            "reason": res.get("score_data", {}).get("reason", "")
                        })
                    LOCAL_TASKS[t_id] = {"status": "SUCCESS", "result": {"copies": formatted_copies}}
                except Exception as e:
                    import traceback
                    print(traceback.format_exc())
                    LOCAL_TASKS[t_id] = {"status": "FAILURE", "error": str(e)}

            background_tasks.add_task(
                run_local_task,
                t_id=task_id,
                copy_text=original_copy,
                focus_text=product_focus,
                api_key=GEMINI_API_KEY,
                m_name=MODEL_NAME,
                u_id=None
            )
            return TaskResponse(task_id=task_id, status="PENDING")

    except Exception as e:
        print(f"\n[API] ❌ 카피 생성 요청 중 오류: {e}")
        raise HTTPException(status_code=500, detail=f"작업 접수 중 오류 발생: {str(e)}")


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """
    비동기 작업의 진행 상태 및 결과를 조회합니다 (Polling).
    """
    if not USE_CELERY:
        if task_id in LOCAL_TASKS:
            task_info = LOCAL_TASKS[task_id]
            response = {"task_id": task_id, "status": task_info["status"]}
            if task_info["status"] == "SUCCESS":
                response["result"] = task_info.get("result")
            elif task_info["status"] == "FAILURE":
                response["error"] = task_info.get("error")
            return response
        else:
            return {"task_id": task_id, "status": "FAILURE", "error": "Task not found"}

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
async def get_my_generations(current_user=Depends(get_current_user)):
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
async def get_generation_detail(gen_id: str, current_user=Depends(get_current_user)):
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
async def submit_feedback_url(gen_id: str, req: SubmitUrlRequest):
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
        feedback.status = "pending"
        # ✅ Celery 없이 DB에 예약 시각 저장 (24시간 뒤)
        feedback.scheduled_at = datetime.utcnow() + timedelta(seconds=REWARD_COUNTDOWN_SEC)
        db.commit()

        return {
            "status": "success",
            "message": "접수 완료! 24시간 후 검증을 거쳐 크레딧이 지급됩니다.",
            "scheduled_at": feedback.scheduled_at.isoformat()
        }
    finally:
        db.close()


@router.post("/process-rewards")
async def process_due_rewards(background_tasks: BackgroundTasks):
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
            .filter(MABFeedback.status == "pending")
            .filter(MABFeedback.scheduled_at <= now)
            .filter(MABFeedback.scheduled_at.isnot(None))
            .limit(20)  # 한 번에 최대 20개 처리 (타임아웃 방지)
            .all()
        )

        if not due_feedbacks:
            return {"status": "ok", "processed": 0, "message": "처리할 항목 없음"}

        # 처리 중 상태로 먼저 잠금 (중복 처리 방지)
        due_ids = [f.gen_id for f in due_feedbacks]
        for f in due_feedbacks:
            f.status = "processing"
        db.commit()
        db.close()

        # ✅ 실제 성과 수집은 BackgroundTask로 비동기 처리
        def _run_reward_check(gen_ids):
            from api.database import SessionLocal, MABFeedback, MABEmbedding, Generation, User
            from api.services.scraper_service import get_threads_full_data, calculate_mss_from_metrics
            from embedding_utils import EmbeddingManager

            _db = SessionLocal()
            emb_mgr = EmbeddingManager()
            try:
                for gid in gen_ids:
                    feedback = _db.query(MABFeedback).filter(MABFeedback.gen_id == gid).first()
                    if not feedback:
                        continue
                    try:
                        url = feedback.published_url
                        data = get_threads_full_data(url)

                        if not data or not data.get("content_text"):
                            feedback.status = "rejected"
                            _db.commit()
                            continue

                        mss = calculate_mss_from_metrics(data)
                        content_text = data["content_text"]

                        # 임베딩 학습 데이터 추가
                        vector = emb_mgr.get_embedding(content_text)
                        _db.add(MABEmbedding(
                            content_text=content_text,
                            mss_score=mss,
                            embedding=vector,
                            is_global=True,
                            metadata_json={"source": "feedback_reward", "url": url, "metrics": data}
                        ))

                        # 크레딧 지급
                        feedback.performance = data
                        feedback.status = "completed"
                        feedback.reward_credits = 2

                        gen = _db.query(Generation).filter(Generation.id == gid).first()
                        if gen and gen.user_id:
                            user = _db.query(User).filter(User.id == gen.user_id).first()
                            if user:
                                user.credits += 2

                        _db.commit()
                        print(f"[Reward] ✅ 완료: {url} → 2 크레딧 지급")

                    except Exception as e:
                        feedback.status = "error"
                        _db.commit()
                        print(f"[Reward] ❌ 오류 ({gid}): {e}")
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
async def refine_copy(request: RefineRequest, current_user=Depends(get_current_user)):
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
