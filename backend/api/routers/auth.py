"""
인증 API 라우터
- 회원가입, 로그인, 토큰 갱신
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from api.database import SessionLocal, User
from api.auth_middleware import (
    hash_password, verify_password, create_access_token, get_current_user
)

router = APIRouter()


class RegisterRequest(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    plan: str
    credits: int

class UserInfoResponse(BaseModel):
    user_id: str
    email: str
    plan: str
    credits: int


@router.post("/auth/register", response_model=TokenResponse)
async def register(req: RegisterRequest):
    """이메일/비밀번호 회원가입"""
    db = SessionLocal()
    try:
        # 중복 체크
        existing = db.query(User).filter(User.email == req.email).first()
        if existing:
            raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.")
        
        # 사용자 생성
        user = User(
            email=req.email,
            hashed_password=hash_password(req.password),
            plan="free",
            credits=10,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        
        # 토큰 발급
        token = create_access_token(str(user.id), user.email)
        return TokenResponse(
            access_token=token,
            user_id=str(user.id),
            email=user.email,
            plan=user.plan,
            credits=user.credits,
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.post("/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    """이메일/비밀번호 로그인"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == req.email).first()
        if not user or not user.hashed_password:
            raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")
        
        if not verify_password(req.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")
        
        token = create_access_token(str(user.id), user.email)
        return TokenResponse(
            access_token=token,
            user_id=str(user.id),
            email=user.email,
            plan=user.plan,
            credits=user.credits,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("/auth/me", response_model=UserInfoResponse)
async def get_me(current_user=Depends(get_current_user)):
    """현재 로그인된 사용자 정보 조회"""
    return UserInfoResponse(
        user_id=str(current_user.id),
        email=current_user.email,
        plan=current_user.plan,
        credits=current_user.credits,
    )
