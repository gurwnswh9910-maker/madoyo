"""
JWT-based authentication helpers.
- Local access-token creation/verification
- FastAPI dependency: get_current_user()
"""
import os
import jwt
import base64
import logging
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Header
import bcrypt
from api.database import SessionLocal, User
from api.config import SUPABASE_URL, SUPABASE_JWT_SECRET
from jwt import PyJWKClient
from api.logging_utils import get_logger, log_event, preview_text

SUPABASE_ALGORITHM = "HS256"

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    import warnings
    warnings.warn("Missing JWT_SECRET_KEY. Falling back to a temporary dev-only secret.")
    SECRET_KEY = "dev-only-insecure-" + os.urandom(16).hex()

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json" if SUPABASE_URL else None
jwks_client = PyJWKClient(JWKS_URL) if JWKS_URL else None
logger = get_logger(__name__)


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(user_id: str, email: str) -> str:
    """Create a local JWT access token."""
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode a locally-issued JWT token."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise Exception("Token expired")
    except jwt.InvalidTokenError:
        raise Exception("Invalid token")


async def get_current_user(authorization: str = Header(None)):
    """
    Resolve the current user from an Authorization bearer token.
    Supports both locally-issued tokens and Supabase-issued tokens.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication token required")

    token = authorization.split(" ")[1]
    token_preview = preview_text(token, limit=24)
    user_id = None
    email = None

    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        email = payload.get("email")
        log_event(logger, logging.INFO, "auth.token.decoded.local", token_preview=token_preview, user_id=user_id)
    except Exception:
        if jwks_client:
            try:
                signing_key = jwks_client.get_signing_key_from_jwt(token)
                payload = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256", "ES256"],
                    options={"verify_aud": False},
                )
                user_id = payload.get("sub")
                email = payload.get("email")
                log_event(logger, logging.INFO, "auth.token.decoded.jwks", token_preview=token_preview, user_id=user_id)
            except Exception as error:
                logger.warning("auth.token.jwks_failed | token_preview=%r error=%r", token_preview, str(error))
                print(f"JWKS decode error: {error}")
                if SUPABASE_JWT_SECRET:
                    try:
                        secret = SUPABASE_JWT_SECRET
                        try:
                            missing_padding = len(secret) % 4
                            if missing_padding:
                                secret += "=" * (4 - missing_padding)
                            decoded_secret = base64.b64decode(secret)
                        except Exception:
                            decoded_secret = secret

                        payload = jwt.decode(
                            token,
                            decoded_secret,
                            algorithms=[SUPABASE_ALGORITHM],
                            options={"verify_aud": False},
                        )
                        user_id = payload.get("sub")
                        email = payload.get("email")
                        log_event(logger, logging.INFO, "auth.token.decoded.legacy_secret", token_preview=token_preview, user_id=user_id)
                    except Exception as legacy_error:
                        logger.warning("auth.token.legacy_failed | token_preview=%r error=%r", token_preview, str(legacy_error))
                        print(f"Supabase legacy decode error: {legacy_error}")
                        raise HTTPException(status_code=401, detail="Invalid token")
                else:
                    raise HTTPException(status_code=401, detail="Invalid token")
        elif SUPABASE_JWT_SECRET:
            try:
                secret = SUPABASE_JWT_SECRET
                try:
                    missing_padding = len(secret) % 4
                    if missing_padding:
                        secret += "=" * (4 - missing_padding)
                    decoded_secret = base64.b64decode(secret)
                except Exception:
                    decoded_secret = secret

                payload = jwt.decode(
                    token,
                    decoded_secret,
                    algorithms=[SUPABASE_ALGORITHM],
                    options={"verify_aud": False},
                )
                user_id = payload.get("sub")
                email = payload.get("email")
                log_event(logger, logging.INFO, "auth.token.decoded.direct_legacy", token_preview=token_preview, user_id=user_id)
            except Exception as error:
                logger.warning("auth.token.direct_legacy_failed | token_preview=%r error=%r", token_preview, str(error))
                print(f"Direct legacy decode error: {error}")
                raise HTTPException(status_code=401, detail="Invalid token")
        else:
            log_event(logger, logging.ERROR, "auth.config.missing", token_preview=token_preview)
            print("Missing authentication configuration: JWKS and legacy secret are both unavailable.")
            raise HTTPException(status_code=401, detail="Authentication server is misconfigured")

    if not user_id:
        log_event(logger, logging.WARNING, "auth.user_id.missing", token_preview=token_preview)
        raise HTTPException(status_code=401, detail="Invalid token")

    import uuid

    db = SessionLocal()
    try:
        user_uuid = uuid.UUID(user_id)
        user = db.query(User).filter(User.id == user_uuid).first()

        if not user:
            user = User(
                id=user_uuid,
                email=email,
                credits=10,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            log_event(logger, logging.INFO, "auth.user.autocreated", user_id=str(user.id), email=email)
        else:
            log_event(logger, logging.INFO, "auth.user.loaded", user_id=str(user.id), email=user.email)

        return user
    finally:
        db.close()


async def get_optional_user(authorization: str = Header(None)):
    """Return None instead of raising when auth is optional."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        return await get_current_user(authorization)
    except HTTPException:
        return None
