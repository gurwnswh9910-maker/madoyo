"""
카피 생성기 FastAPI 앱.
기존 카피 생성기 코어를 웹 API로 노출합니다.

실행:
    cd c:\\Users\\ding9\\Desktop\\madoyo\\작동중코드
    python -m uvicorn api.main:app --reload --port 8000

Swagger UI:
    http://localhost:8000/docs
"""
import os
import sys

# 코어 모듈 경로 보장
_code_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _code_dir not in sys.path:
    sys.path.insert(0, _code_dir)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import generation


# ════════════════════════════════════════════════════════════════
# FastAPI 앱 생성
# ════════════════════════════════════════════════════════════════
app = FastAPI(
    title="카피 생성기 API",
    description=(
        "MAB 전략 최적화 + 임베딩 기반 스코어링을 활용한 "
        "고성과 SNS 카피 생성 API입니다.\n\n"
        "**입력**: 참고 카피, 이미지 URL, 레퍼런스 게시물 URL 중 최소 1개\n"
        "**출력**: 상위 3개 카피 + 점수 + 적용 전략"
    ),
    version="1.0.0",
)


# ════════════════════════════════════════════════════════════════
# CORS 미들웨어 (프론트엔드 연동용)
# ════════════════════════════════════════════════════════════════
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 개발 시 전체 허용. 프로덕션에서는 특정 도메인으로 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ════════════════════════════════════════════════════════════════
# 라우터 등록
# ════════════════════════════════════════════════════════════════
app.include_router(generation.router, prefix="/api", tags=["카피 생성"])


# ════════════════════════════════════════════════════════════════
# 루트 엔드포인트
# ════════════════════════════════════════════════════════════════
@app.get("/")
async def root():
    return {
        "message": "카피 생성기 API 서버가 실행 중입니다.",
        "docs": "/docs",
        "health": "/api/health",
    }
