import os
import requests
import sys
import io
from pathlib import Path
from dotenv import load_dotenv, set_key

# Windows 환경에서 이모지 출력을 위한 UTF-8 인코딩 설정
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 현재 스크립트 위치 기준 설정
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH, override=False)


def normalize_account_slot(value):
    slot = str(value or "1").split(",", 1)[0].strip()
    if slot.upper().startswith("ACCOUNT_"):
        slot = slot.split("_", 1)[1]
    return slot or "1"


def get_long_lived_token(app_secret, short_lived_token):
    url = "https://graph.threads.net/access_token"
    params = {
        "grant_type": "th_exchange_token",
        "client_secret": app_secret,
        "access_token": short_lived_token,
    }
    
    print("▶️ 장기 액세스 토큰 발급 요청 중...")
    response = requests.get(url, params=params, timeout=20)
    data = response.json()
    
    if "access_token" in data:
        long_lived_token = data["access_token"]
        print("✅ 장기 액세스 토큰 발급 성공!")
        return long_lived_token
    else:
        print(f"❌ 토큰 발급 실패: {data}")
        return None

def get_user_id(access_token):
    # 액세스 토큰을 사용하여 사용자 ID 가져오기
    # 보통 me 엔드포인트를 호출하면 id를 알 수 있습니다.
    url = "https://graph.threads.net/v1.0/me"
    params = {
        "access_token": access_token
    }
    
    print("▶️ 사용자 정보 가져오는 중...")
    response = requests.get(url, params=params, timeout=20)
    data = response.json()
    
    if "id" in data:
        user_id = data["id"]
        print(f"✅ 사용자 ID 확인 성공: {user_id}")
        return user_id
    else:
        print(f"❌ 사용자 ID 확인 실패: {data}")
        return None

if __name__ == "__main__":
    app_secret = os.getenv("THREADS_TOKEN_EXCHANGE_APP_SECRET")
    short_lived_token = os.getenv("THREADS_SHORT_LIVED_TOKEN")
    account_slot = normalize_account_slot(
        os.getenv("THREADS_TOKEN_ACCOUNT") or os.getenv("THREADS_CURRENT_ACCOUNT") or "1"
    )
    if not app_secret or not short_lived_token:
        raise SystemExit(
            "THREADS_TOKEN_EXCHANGE_APP_SECRET와 THREADS_SHORT_LIVED_TOKEN을 "
            "프로젝트 루트 .env에 넣은 뒤 실행해주세요."
        )

    # 1. 장기 토큰 받기
    long_token = get_long_lived_token(app_secret, short_lived_token)
    
    # 2. 유저 ID 가져오기 (토큰이 성공적으로 발급되었을 경우)
    if long_token:
        user_id = get_user_id(long_token)
        
        # 3. .env 파일에 저장
        if user_id:
            set_key(str(ENV_PATH), f"THREADS_ACCOUNT_{account_slot}_USER_ID", user_id)
            set_key(str(ENV_PATH), f"THREADS_ACCOUNT_{account_slot}_ACCESS_TOKEN", long_token)
            set_key(str(ENV_PATH), f"THREADS_ACCOUNT_{account_slot}_APP_SECRET", app_secret)
            if not os.getenv("THREADS_CURRENT_ACCOUNT"):
                set_key(str(ENV_PATH), "THREADS_CURRENT_ACCOUNT", account_slot)

            print(f"\n🎉 성공적으로 {ENV_PATH} 에 {account_slot}번 계정 자격 증명을 저장했습니다!")
            print("="*60)
            print(f"THREADS_ACCOUNT_{account_slot}_USER_ID=<saved>")
            print(f"THREADS_ACCOUNT_{account_slot}_ACCESS_TOKEN=<saved>")
            print(f"THREADS_ACCOUNT_{account_slot}_APP_SECRET=<saved>")
            print("="*60)
