"""
피드백 API 라우터
- 좋아요/별로에요 피드백 수집
- 버그리포트 프론트엔드 전송용
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from api.database import SessionLocal, MABFeedback, BugReport, Generation
from benchmark_recorder import safe_sync_benchmark_record

router = APIRouter()


# ════════════════════════════════════════════════════════════════
# Pydantic 스키마
# ════════════════════════════════════════════════════════════════

class FeedbackRequest(BaseModel):
    gen_id: str
    copy_rank: int = 1
    rating: str  # "good" | "bad"
    reasons: Optional[list[str]] = None

class FrontendBugReport(BaseModel):
    error_type: str
    message: str
    context: Optional[dict] = None


# ════════════════════════════════════════════════════════════════
# 좋아요/별로에요 피드백
# ════════════════════════════════════════════════════════════════

@router.post("/feedback")
async def submit_feedback(req: FeedbackRequest):
    """카피 결과에 대한 사용자 피드백을 저장합니다."""
    db = SessionLocal()
    try:
        benchmark_record_path = ""
        feedback = db.query(MABFeedback).filter(
            MABFeedback.gen_id == req.gen_id
        ).first()
        
        if feedback:
            feedback.user_rating = req.rating
            feedback.rating_reasons = req.reasons
        else:
            # 피드백 레코드가 없으면 새로 생성
            feedback = MABFeedback(
                gen_id=req.gen_id,
                user_rating=req.rating,
                rating_reasons=req.reasons,
            )
            db.add(feedback)

        feedback.performance = {
            **(feedback.performance or {}),
            "feedback_copy_rank": req.copy_rank,
        }

        gen = db.query(Generation).filter(Generation.id == req.gen_id).first()
        if gen and isinstance(gen.results, dict):
            benchmark_record_path = gen.results.get("benchmark_record_path", "")
        
        db.commit()
        safe_sync_benchmark_record(
            benchmark_record_path,
            patch={
                "user_feedback": {
                    "rating": req.rating,
                    "reasons": req.reasons or [],
                    "copy_rank": req.copy_rank,
                }
            },
            event={
                "event_type": "user_feedback_submitted",
                "generation_id": req.gen_id,
                "copy_rank": req.copy_rank,
                "rating": req.rating,
            },
            context="feedback.submit_feedback",
        )
        return {"status": "ok", "message": "피드백 저장 완료"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


# ════════════════════════════════════════════════════════════════
# 프론트엔드 버그리포트 수신
# ════════════════════════════════════════════════════════════════

@router.post("/bug-report")
async def submit_bug_report(req: FrontendBugReport):
    """프론트엔드에서 발생한 JS 에러 등을 수집합니다."""
    db = SessionLocal()
    try:
        report = BugReport(
            layer="frontend",
            error_type=req.error_type,
            message=req.message,
            context=req.context,
        )
        db.add(report)
        db.commit()
        return {"status": "ok"}
    except Exception as e:
        db.rollback()
        return {"status": "error", "detail": str(e)}
    finally:
        db.close()
