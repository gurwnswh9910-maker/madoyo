"""
크레딧 가드 - 사용자의 크레딧이 충분한지 확인하고 차감하는 유틸리티
"""
from fastapi import HTTPException, Depends
from api.database import SessionLocal, User
from api.auth_middleware import get_current_user


async def check_credit(current_user=Depends(get_current_user)):
    """
    크레딧이 1 이상인지 확인합니다.
    보호된 라우트에 Depends(check_credit) 형태로 사용합니다.
    """
    if current_user.credits <= 0:
        raise HTTPException(
            status_code=402,
            detail="크레딧이 부족합니다. 충전 후 이용해주세요."
        )
    return current_user


def deduct_credit(user_id, amount=1):
    """크레딧을 차감합니다. 워커/태스크에서 호출."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.credits = max(0, user.credits - amount)
            db.commit()
            return user.credits
        return None
    finally:
        db.close()


def add_credit(user_id, amount):
    """결제 후 크레딧을 충전합니다."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.credits += amount
            db.commit()
            return user.credits
        return None
    finally:
        db.close()
