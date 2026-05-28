import os
import requests
from dotenv import load_dotenv, set_key

# 프로젝트 루트의 .env 파일 로드
base_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(base_dir, '.env')
load_dotenv(env_path)

def normalize_account_slot(value):
    slot = str(value or "1").strip()
    if slot.upper().startswith("ACCOUNT_"):
        slot = slot.split("_", 1)[1]
    return slot or "1"


def refresh_token(account_slot):
    account_slot = normalize_account_slot(account_slot)
    env_key = f"THREADS_ACCOUNT_{account_slot}_ACCESS_TOKEN"
    token = os.getenv(env_key)
    if not token or "your_" in token:
        print(f"❌ {account_slot}번: 토큰 정보가 없습니다.")
        return None
    
    print(f"▶️ {account_slot}번 토큰 갱신 요청 중...")
    url = "https://graph.threads.net/refresh_access_token"
    params = {
        "grant_type": "th_refresh_token",
        "access_token": token
    }
    
    try:
        response = requests.get(url, params=params, timeout=12)
        data = response.json()
        
        if "access_token" in data:
            new_token = data["access_token"]
            expires_in = data.get("expires_in", 0)
            days = expires_in // (24 * 3600)
            print(f"✅ {account_slot}번 토큰 갱신 성공! (남은 기간: 약 {days}일)")
            
            # .env 파일에 새로운 토큰 저장
            set_key(env_path, env_key, new_token)
            return new_token
        else:
            print(f"❌ {account_slot}번 토큰 갱신 실패: {data}")
            return None
    except Exception as e:
        print(f"❌ {account_slot}번 요청 중 오류 발생: {e}")
        return None

if __name__ == "__main__":
    print("🔄 Threads 장기 액세스 토큰 갱신 시작...\n")
    raw_accounts = os.getenv("THREADS_REFRESH_ACCOUNTS") or os.getenv("THREADS_CURRENT_ACCOUNT") or "1"
    account_slots = [normalize_account_slot(part) for part in raw_accounts.split(",") if part.strip()]
    for index, account_slot in enumerate(account_slots):
        if index:
            print("-" * 40)
        refresh_token(account_slot)
    
    print("\n✨ 모든 작업 완료!")
