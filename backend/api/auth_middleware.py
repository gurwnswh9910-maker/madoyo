"""
JWT 기반 인증 미들웨어
- 토큰 생성/검증
- FastAPI Depends용 get_current_user()
"""
import os
import jwt
import base64
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Depends, Header
import bcrypt
from api.database import SessionLocal, User
from api.config import SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_JWT_SECRET
from jwt import PyJWKClient

# JWT 검증 설정 (Supabase는 HS256 사용)
SUPABASE_ALGORITHM = "HS256"

# 비밀 키 (.env에서 가져오거나 기본값 사용)
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "madoyo-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

# Supabase JWKS 설정 (ES256 등 공개키 기반 검증용)
JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json" if SUPABASE_URL else None
jwks_client = PyJWKClient(JWKS_URL) if JWKS_URL else None

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

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
        raise Exception("토큰이 만료되었습니다.")
    except jwt.InvalidTokenError:
        raise Exception("유효하지 않은 토큰입니다.")

async def get_current_user(authorization: str = Header(None)):
    """
    보호된 라우트에서 사용하는 의존성 함수.
    Authorization: Bearer <token> 헤더에서 사용자 정보를 추출합니다.
    Supabase 토큰과 자체 발급 토큰을 모두 지원합니다.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="인증 토큰이 필요합니다.")
    
    token = authorization.split(" ")[1]
    
    user_id = None
    email = None
    
    # 1. 먼저 자체 발급 토큰 시도 (FastAPI 전용)
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        email = payload.get("email")
    except Exception:
        # 2. 실패 시 Supabase 토큰 검증 시도
        # 2-1. 먼저 JWKS (ES256 등) 시도
        if jwks_client:
            try:
                signing_key = jwks_client.get_signing_key_from_jwt(token)
                payload = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256", "ES256"],
                    options={"verify_aud": False}
                )
                user_id = payload.get("sub")
                email = payload.get("email")
            except Exception as e:
                print(f"JWKS decode error: {e}")
                # JWKS 실패 시 Legacy Secret (HS256) 시도
                if SUPABASE_JWT_SECRET:
                    try:
                        secret = SUPABASE_JWT_SECRET
                        try:
                            missing_padding = len(secret) % 4
                            if missing_padding: secret += '=' * (4 - missing_padding)
                            decoded_secret = base64.b64decode(secret)
                        except:
                            decoded_secret = secret

                        payload = jwt.decode(
                            token,
                            decoded_secret,
                            algorithms=["HS256"],
                            options={"verify_aud": False}
                        )
                        user_id = payload.get("sub")
                        email = payload.get("email")
                    except Exception as e2:
                        print(f"Supabase Legacy decode error: {e2}")
                        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
                else:
                    raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
        elif SUPABASE_JWT_SECRET:
            # JWKS 설정이 없는 경우 Legacy Secret만 시도
            try:
                secret = SUPABASE_JWT_SECRET
                try:
                    missing_padding = len(secret) % 4
                    if missing_padding: secret += '=' * (4 - missing_padding)
                    decoded_secret = base64.b64decode(secret)
                except:
                    decoded_secret = secret
                
                payload = jwt.decode(token, decoded_secret, algorithms=["HS256"], options={"verify_aud": False})
                user_id = payload.get("sub")
                email = payload.get("email")
            except Exception as e:
                print(f"Direct Legacy decode error: {e}")
                raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
        else:
            print("⚠️ 인증 설정(JWKS 또는 Secret)이 없습니다.")
            raise HTTPException(status_code=401, detail="인증 서버 설정이 불완전합니다.")

    if not user_id:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
    
    import uuid # 로컬 임포트
    db = SessionLocal()
    try:
        # UUID 형식으로 변환하여 검색
        user_uuid = uuid.UUID(user_id)
        user = db.query(User).filter(User.id == user_uuid).first()
        
        # 사용자가 DB에 없으면 자동 생성 (소셜 로그인 최초 진입 시)
        if not user:
            user = User(
                id=user_uuid,
                email=email,
                credits=10 # 가입 축하 10포인트
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            
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
