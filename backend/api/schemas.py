"""
Pydantic 모델 정의.
API 요청/응답의 데이터 형식을 정의합니다.
"""
from pydantic import BaseModel, model_validator
from typing import Optional


# ════════════════════════════════════════════════════════════════
# 카피 생성 관련
# ════════════════════════════════════════════════════════════════

class GenerateRequest(BaseModel):
    """카피 생성 요청. 최소 1개 입력이 필요합니다."""
    reference_copy: Optional[str] = None        # 참고 카피 텍스트
    image_urls: Optional[list[str]] = None       # 이미지 URL 목록
    reference_url: Optional[str] = None          # 레퍼런스 게시물 URL

    @model_validator(mode="after")
    def check_at_least_one_input(self):
        has_copy = bool(self.reference_copy and self.reference_copy.strip())
        has_images = bool(self.image_urls and len(self.image_urls) > 0)
        has_url = bool(self.reference_url and self.reference_url.strip())
        if not (has_copy or has_images or has_url):
            raise ValueError("최소 1개의 입력(참고 카피, 이미지, 또는 URL)이 필요합니다.")
        return self


class CopyResult(BaseModel):
    """생성된 카피 1건의 결과"""
    rank: int
    copy_text: str
    strategy: str
    score: int
    reason: str


class GenerateResponse(BaseModel):
    """카피 생성 응답"""
    copies: list[CopyResult]
    original_score: int
    processing_time: float


# ════════════════════════════════════════════════════════════════
# 카피 수정 (챗봇)
# ════════════════════════════════════════════════════════════════

class RefineRequest(BaseModel):
    """카피 미세 수정 요청"""
    original_copy: str
    user_instruction: str
    conversation_history: Optional[list[dict]] = None


class RefineResponse(BaseModel):
    """카피 수정 응답"""
    refined_copy: str


# ════════════════════════════════════════════════════════════════
# 비동기 작업 관련
# ════════════════════════════════════════════════════════════════

class TaskResponse(BaseModel):
    """작업 요청 접수 응답"""
    task_id: str
    status: str


class TaskStatusResponse(BaseModel):
    """작업 상태 조회 응답"""
    task_id: str
    status: str
    result: Optional[dict] = None
    error: Optional[str] = None
    processing_time: Optional[float] = None


# ════════════════════════════════════════════════════════════════
# 헬스체크
# ════════════════════════════════════════════════════════════════

class HealthResponse(BaseModel):
    status: str
    model: str
    data_loaded: bool
