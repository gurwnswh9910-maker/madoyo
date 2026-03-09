"""
결제 시스템 라우터
- 포트원(PortOne) 결제 검증
- 크레딧 충전 Webhook
- 요금제 조회
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional
from api.database import SessionLocal, User
from api.auth_middleware import get_current_user
from api.credit_guard import add_credit
import hmac
import hashlib

router = APIRouter()


# ════════════════════════════════════════════════════════════════
# 스키마 정의
# ════════════════════════════════════════════════════════════════

class CheckoutRequest(BaseModel):
    plan: str  # "basic_30" | "pro_100" | "enterprise_500"

class CheckoutResponse(BaseModel):
    payment_id: str
    amount: int
    credits_to_add: int

class PlanInfo(BaseModel):
    name: str
    credits: int
    price: int  # KRW
    description: str


# 요금제 정보
PLANS = {
    "basic_30": PlanInfo(name="Basic", credits=30, price=9900, description="소규모 테스트용"),
    "pro_100": PlanInfo(name="Pro", credits=100, price=29900, description="본격 마케팅용"),
    "enterprise_500": PlanInfo(name="Enterprise", credits=500, price=99900, description="대량 생성용"),
}


# ════════════════════════════════════════════════════════════════
# 요금제 목록
# ════════════════════════════════════════════════════════════════

@router.get("/billing/plans")
async def get_plans():
    """사용 가능한 요금제 목록을 반환합니다."""
    return {
        "plans": [
            {"id": k, **v.model_dump()} for k, v in PLANS.items()
        ]
    }


# ════════════════════════════════════════════════════════════════
# 결제 요청 생성
# ════════════════════════════════════════════════════════════════

@router.post("/billing/checkout", response_model=CheckoutResponse)
async def create_checkout(req: CheckoutRequest, current_user=Depends(get_current_user)):
    """포트원 결제를 위한 주문 정보를 생성합니다."""
    plan = PLANS.get(req.plan)
    if not plan:
        raise HTTPException(status_code=400, detail="존재하지 않는 요금제입니다.")
    
    import uuid
    payment_id = f"PAY-{uuid.uuid4().hex[:12].upper()}"
    
    # 결제 정보를 DB에 기록 (PaymentLog 테이블 사용)
    # 실제로는 여기서 포트원 API를 호출하여 결제 세션을 생성합니다.
    
    return CheckoutResponse(
        payment_id=payment_id,
        amount=plan.price,
        credits_to_add=plan.credits,
    )


# ════════════════════════════════════════════════════════════════
# 결제 승인 Webhook (포트원에서 호출)
# ════════════════════════════════════════════════════════════════

@router.post("/billing/webhook")
async def payment_webhook(request: Request):
    """
    포트원 결제 승인 Webhook.
    결제 성공 시 해당 사용자의 크레딧을 충전합니다.
    """
    try:
        body = await request.json()
        
        # 포트원 Webhook 기본 구조
        payment_id = body.get("payment_id") or body.get("imp_uid")
        merchant_uid = body.get("merchant_uid")
        status = body.get("status")
        
        if status != "paid":
            return {"status": "ignored", "reason": f"status={status}"}
        
        # TODO: 포트원 API로 결제 검증 (imp_uid 조회)
        # 실제 구현 시 여기서 포트원 서버에 결제 상태를 재확인합니다.
        
        # merchant_uid에서 user_id와 plan을 파싱
        # 예) merchant_uid = "USER-{user_id}-PLAN-{plan_id}"
        # 현재는 body에서 직접 받는 방식으로 처리
        user_id = body.get("user_id")
        plan_id = body.get("plan_id")
        
        if not user_id or not plan_id:
            return {"status": "error", "detail": "user_id, plan_id 필수"}
        
        plan = PLANS.get(plan_id)
        if not plan:
            return {"status": "error", "detail": "유효하지 않은 요금제"}
        
        # 크레딧 충전
        new_balance = add_credit(user_id, plan.credits)
        
        return {
            "status": "ok",
            "credits_added": plan.credits,
            "new_balance": new_balance,
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


# ════════════════════════════════════════════════════════════════
# 내 결제 내역
# ════════════════════════════════════════════════════════════════

@router.get("/billing/my-credits")
async def get_my_credits(current_user=Depends(get_current_user)):
    """현재 사용자의 크레딧 잔액을 반환합니다."""
    return {
        "user_id": str(current_user.id),
        "credits": current_user.credits,
        "plan": current_user.plan,
    }
