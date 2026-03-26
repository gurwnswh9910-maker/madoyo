"""
카피 생성기 FastAPI 앱.
기존 카피 생성기 코어를 웹 API로 노출합니다.

실행:
    cd c:\\Users\\ding9\\Desktop\\madoyo\\backend
    python -m uvicorn api.main:app --reload --port 8000

Swagger UI:
    http://localhost:8000/docs
"""
import os
import sys
import traceback

# 코어 모듈 경로 보장
_code_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _code_dir not in sys.path:
    sys.path.insert(0, _code_dir)

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routers import generation, upload, feedback, auth, billing, media


from api.config import CORS_ALLOWED_ORIGINS

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
    version="2.0.0",
)


# ════════════════════════════════════════════════════════════════
# CORS 미들웨어 (프론트엔드 연동용)
# ════════════════════════════════════════════════════════════════
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.snapthread\.site|https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ════════════════════════════════════════════════════════════════
# 전역 예외 핸들러 (자동 버그리포트)
# ════════════════════════════════════════════════════════════════
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """모든 미처리 예외를 bug_reports DB에 자동 기록합니다."""
    try:
        from api.database import SessionLocal, BugReport
        db = SessionLocal()
        
        # request body 추출 시도
        body = None
        try:
            body = await request.json()
        except Exception:
            pass
        
        try:
            report = BugReport(
                layer="backend",
                error_type=type(exc).__name__,
                message=str(exc),
                traceback=traceback.format_exc(),
                context={
                    "method": request.method,
                    "url": str(request.url),
                    "body": body,
                },
                code_ref=f"{type(exc).__module__}",
            )
            db.add(report)
            db.commit()
        finally:
            db.close()
    except Exception as db_err:
        print(f"⚠️ 버그리포트 DB 저장 실패: {db_err}")
    
    return JSONResponse(
        status_code=500,
        content={"detail": f"서버 내부 오류: {str(exc)}"},
    )


# ════════════════════════════════════════════════════════════════
# 라우터 등록
# ════════════════════════════════════════════════════════════════
app.include_router(generation.router, prefix="/api", tags=["카피 생성"])
app.include_router(upload.router, prefix="/api/upload", tags=["데이터 업로드"])
app.include_router(media.router, prefix="/api", tags=["미디어 업로드"])
app.include_router(feedback.router, prefix="/api", tags=["피드백 & 버그리포트"])
app.include_router(auth.router, prefix="/api", tags=["인증"])
app.include_router(billing.router, prefix="/api", tags=["결제"])

# 정적 파일 서빙 (업로드된 미디어 호스팅)
os.makedirs("temp_uploads/media", exist_ok=True)
app.mount("/media", StaticFiles(directory="temp_uploads/media"), name="media")


# ════════════════════════════════════════════════════════════════
# 루트 엔드포인트
# ════════════════════════════════════════════════════════════════
@app.get("/")
async def root():
    return {
        "message": "카피 생성기 API 서버가 실행 중입니다.",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/api/health",
    }
