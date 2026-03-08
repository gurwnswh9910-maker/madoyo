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

@router.post("/generate", response_model=GenerateResponse)
async def generate_copy(request: GenerateRequest):
    """
    카피 생성 메인 엔드포인트.
    
    입력: 참고 카피 / 이미지 URL / 레퍼런스 URL 중 최소 1개
    출력: 상위 3개 카피 + 점수 + 전략 정보
    """
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY가 설정되지 않았습니다.")
    
    t_start = time.time()

    try:
        # Step 1: 입력 → product_focus 변환
        print(f"\n{'='*60}")
        print(f"[API] 카피 생성 요청 수신")
        print(f"  - 참고 카피: {'있음' if request.reference_copy else '없음'}")
        print(f"  - 이미지:    {len(request.image_urls) if request.image_urls else 0}개")
        print(f"  - URL:       {'있음' if request.reference_url else '없음'}")
        print(f"{'='*60}")

        product_focus, original_copy = build_context(
            api_key=GEMINI_API_KEY,
            model_name=MODEL_NAME,
            reference_copy=request.reference_copy,
            image_urls=request.image_urls,
            reference_url=request.reference_url,
        )

        # original_copy가 비어있으면 product_focus의 insight를 사용
        if not original_copy or not original_copy.strip():
            if isinstance(product_focus, dict):
                original_copy = product_focus.get("marketing_insight", "제품 홍보 카피")
            else:
                original_copy = str(product_focus)

        print(f"\n[API] Context 변환 완료:")
        if isinstance(product_focus, dict):
            print(f"  - 객관적 묘사: {product_focus.get('objective_description', '')[:50]}...")
            print(f"  - 마케팅 인사이트: {product_focus.get('marketing_insight', '')[:50]}...")
        print(f"  - 원본 카피: {original_copy[:50]}...")

        # Step 2: 코어 엔진 호출
        from optimize_copy_v2 import run_optimization
        top_3 = run_optimization(
            original_copy=original_copy,
            product_focus=product_focus,
            api_key=GEMINI_API_KEY,
            model_name=MODEL_NAME,
            base_path=BASE_PATH,
        )

        # Step 3: 원본 점수 (top_3에서 Original이 있으면 추출, 없으면 0)
        original_score = 0

        # Step 4: 응답 포맷팅
        copies = []
        for rank, item in enumerate(top_3, 1):
            sd = item.get("score_data", {})
            copies.append(
                CopyResult(
                    rank=rank,
                    copy_text=item.get("copy", ""),
                    strategy=item.get("strategy", "unknown"),
                    score=sd.get("mss_score_estimate", 0),
                    reason=sd.get("reason", ""),
                )
            )

        processing_time = round(time.time() - t_start, 1)
        print(f"\n[API] 카피 생성 완료: {processing_time}초 소요, {len(copies)}개 결과")

        return GenerateResponse(
            copies=copies,
            original_score=original_score,
            processing_time=processing_time,
        )

    except Exception as e:
        print(f"\n[API] ❌ 카피 생성 중 오류: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"카피 생성 중 오류 발생: {str(e)}")


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
