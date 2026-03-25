"""
결제 시스템 라우터 (페이앱 PayApp 버전)
- 비사업자용 결제 시스템 (페이앱) 연동
- 결제 요청 생성 및 웹훅 처리
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Form
from pydantic import BaseModel
from typing import Optional, List
from api.database import SessionLocal, User
from api.auth_middleware import get_current_user
from api.credit_guard import add_credit
from api.config import PAYAPP_USERID, PAYAPP_LINKKEY, PAYAPP_LINKVAL, PAYAPP_WEBHOOK_URL
import hmac
import hashlib
import requests

router = APIRouter()

# ════════════════════════════════════════════════════════════════
# 스키마 정의
# ════════════════════════════════════════════════════════════════

class CheckoutRequest(BaseModel):
    plan: str  # "pro_1" | "pro_3" | "pro_12" (예: 결제 개월 수)

class CheckoutResponse(BaseModel):
    payment_url: str  # 페이앱 결제창 URL
    order_id: str

class PlanInfo(BaseModel):
    name: str
    credits: int
    price: int  # KRW
    description: str

# 요금제 정보 (비사업자 타겟으로 현실적인 구성)
PLANS = {
    "pro_1": PlanInfo(name="Pro 1개월", credits=50, price=29900, description="한 달간 부담 없이 사용"),
    "pro_3": PlanInfo(name="Pro 3개월", credits=200, price=79900, description="10% 할인된 가격"),
    "pro_12": PlanInfo(name="Pro 1년", credits=1000, price=299000, description="가장 저렴한 장기 플랜"),
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
# 페이앱 결제 요청 생성
# ════════════════════════════════════════════════════════════════

@router.post("/billing/checkout", response_model=CheckoutResponse)
async def create_checkout(req: CheckoutRequest, current_user=Depends(get_current_user)):
    """페이앱 결제창을 띄우기 위한 URL을 생성합니다."""
    plan = PLANS.get(req.plan)
    if not plan:
        raise HTTPException(status_code=400, detail="존재하지 않는 요금제입니다.")
    
    import uuid
    order_id = f"ORDER-{uuid.uuid4().hex[:12].upper()}"
    
    # 페이앱 API 호출 (결제 요청)
    # 실제 운영 시에는 프론트엔드에서 SDK를 쓰는 것이 편하지만, 
    # 서버 사이드에서 결제를 생성하여 URL을 받아오는 방식이 보안상 더 견고합니다.
    
    payapp_api_url = "https://api.payapp.kr/oapi/api/payment.html"
    
    payload = {
        "cmd": "payrequest",
        "userid": PAYAPP_USERID,
        "linkkey": PAYAPP_LINKKEY,
        "goodname": f"마도요 {plan.name}",
        "price": str(plan.price),
        "recvphone": "01000000000", # 실제 사용자 번호가 있으면 좋으나 필수는 아님
        "memo": f"User: {current_user.email}, Plan: {req.plan}",
        "reqmode": "api",
        "var1": str(current_user.id), # 사용자 ID 전달 (웹훅에서 사용)
        "var2": req.plan,            # 플랜 정보 전달
        "feedbackurl": PAYAPP_WEBHOOK_URL,  # .env 또는 config 기반 웹훅 수신 주소
        "vccode": "KR",
        "currency": "KRW"
    }
    
    try:
        response = requests.post(payapp_api_url, data=payload)
        res_data = response.text
        # 페이앱 응답은 key=value&... 형태의 쿼리 스트링일 수 있음
        import urllib.parse
        parsed_res = dict(urllib.parse.parse_qsl(res_data))
        
        if parsed_res.get("state") != "1":
            error_msg = parsed_res.get("errorMessage", "알 수 없는 오류")
            raise HTTPException(status_code=500, detail=f"페이앱 결제 요청 실패: {error_msg}")
        
        return CheckoutResponse(
            payment_url=parsed_res.get("mul_no"), # 결제 페이지 URL
            order_id=order_id
        )
    except Exception as e:
        print(f"PayApp Error: {e}")
        raise HTTPException(status_code=500, detail="결제 서버 통신 중 오류가 발생했습니다.")

# ════════════════════════════════════════════════════════════════
# 페이앱 결제 승인 Webhook (Feedback URL)
# ════════════════════════════════════════════════════════════════

@router.post("/billing/webhook")
async def payapp_webhook(
    userid: str = Form(...),
    linkkey: str = Form(...),
    state: str = Form(...),
    mul_no: str = Form(...),
    price: str = Form(...),
    var1: str = Form(None), # User ID
    var2: str = Form(None), # Plan ID
    # 기타 페이앱 제공 파라미터들
):
    """
    페이앱 결제 완료 시 호출되는 웹훅.
    결제 상태가 완료(state=4)인 경우 사용자의 크레딧을 업데이트합니다.
    """
    # 1. 시크릿 키 검증 (보안)
    if linkkey != PAYAPP_LINKKEY:
         return {"status": "error", "message": "invalid linkkey"}

    # 2. 결제 성공 여부 확인 (state 4는 결제완료)
    if state != "4":
        return {"status": "ignored", "state": state}

    user_id = var1
    plan_id = var2

    if not user_id or not plan_id:
        return {"status": "error", "message": "missing user_id or plan_id"}

    plan = PLANS.get(plan_id)
    if not plan:
        return {"status": "error", "message": "invalid plan"}

    # 3. DB 업데이트
    new_balance = add_credit(user_id, plan.credits)
    
    # 4. 플랜 업데이트
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.plan = "pro"
            db.commit()
    finally:
        db.close()

    return "SUCCESS" # 페이앱은 성공 시 SUCCESS 문자열을 요구하기도 함

# ════════════════════════════════════════════════════════════════
# 내 결제 정보 조회
# ════════════════════════════════════════════════════════════════

@router.get("/billing/my-credits")
async def get_my_credits(current_user=Depends(get_current_user)):
    """현재 사용자의 크레딧 잔액과 플랜 정보를 반환합니다."""
    return {
        "user_id": str(current_user.id),
        "email": current_user.email,
        "credits": current_user.credits,
        "plan": current_user.plan,
    }
