"""
JWT 기반 인증 미들웨어
- 토큰 생성/검증
- FastAPI Depends용 get_current_user()
"""
import os
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Depends, Header
from passlib.context import CryptContext
from api.database import SessionLocal, User

# 비밀 키 (.env에서 가져오거나 기본값 사용)
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "madoyo-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

# 비밀번호 해싱
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: str, email: str) -> str:
    """JWT 액세스 토큰 생성"""
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """JWT 토큰 디코드"""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="토큰이 만료되었습니다.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")


async def get_current_user(authorization: str = Header(None)):
    """
    보호된 라우트에서 사용하는 의존성 함수.
    Authorization: Bearer <token> 헤더에서 사용자 정보를 추출합니다.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="인증 토큰이 필요합니다.")
    
    token = authorization.split(" ")[1]
    payload = decode_token(token)
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
    
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다.")
        return user
    finally:
        db.close()


async def get_optional_user(authorization: str = Header(None)):
    """
    인증이 선택적인 라우트용. 토큰이 없으면 None 반환.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        return await get_current_user(authorization)
    except HTTPException:
        return None
