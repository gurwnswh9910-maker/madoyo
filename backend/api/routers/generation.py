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

from fastapi import APIRouter, HTTPException

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
from api.config import GEMINI_API_KEY, MODEL_NAME, FALLBACK_MODEL_NAME, BASE_PATH
from api.services.context_builder import build_context

router = APIRouter()


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
async def generate_copy(request: GenerateRequest):
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
        )

        # original_copy 보정
        if not original_copy or not original_copy.strip():
            if isinstance(product_focus, dict):
                original_copy = product_focus.get("marketing_insight", "제품 홍보 카피")
            else:
                original_copy = str(product_focus)

        # Step 2: 비동기 태스크 호출
        from api.worker import optimize_copy_task
        task = optimize_copy_task.delay(
            original_copy=original_copy,
            product_focus=product_focus,
            api_key=GEMINI_API_KEY,
            model_name=MODEL_NAME,
            user_id=None # 현재는 단일 유저
        )

        return TaskResponse(task_id=task.id, status="PENDING")

    except Exception as e:
        print(f"\n[API] ❌ 카피 생성 요청 중 오류: {e}")
        raise HTTPException(status_code=500, detail=f"작업 접수 중 오류 발생: {str(e)}")


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """
    비동기 작업의 진행 상태 및 결과를 조회합니다 (Polling).
    """
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


# ════════════════════════════════════════════════════════════════
# 카피 수정 (챗봇)
# ════════════════════════════════════════════════════════════════

@router.post("/refine", response_model=RefineResponse)
async def refine_copy(request: RefineRequest):
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
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"LLM 수정 실패: {str(e)}")

        return RefineResponse(refined_copy=refined)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"카피 수정 중 오류 발생: {str(e)}")
