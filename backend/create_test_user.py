import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Add the backend dir to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.database import SessionLocal, User
from api.auth_middleware import hash_password
import uuid

def create_user():
    db = SessionLocal()
    try:
        email = "test@madoyo.io"
        password = "password123"
        
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            print(f"⚠️ 이미 테스트 계정이 존재합니다.")
            print(f"➡️ 이메일: {email}")
            print(f"➡️ 비밀번호: {password}")
            return
            
        user = User(
            id=uuid.uuid4(),
            email=email,
            hashed_password=hash_password(password),
            plan="enterprise",
            credits=100
        )
        db.add(user)
        db.commit()
        print(f"✅ 테스트 계정 생성 완료!")
        print(f"➡️ 이메일: {email}")
        print(f"➡️ 비밀번호: {password}")
        print(f"➡️ 남은 크레딧: 100")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    create_user()
