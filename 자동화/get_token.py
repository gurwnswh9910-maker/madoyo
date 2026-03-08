import os
import requests
import sys
import io
from dotenv import load_dotenv, set_key

# Windows 환경에서 이모지 출력을 위한 UTF-8 인코딩 설정
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 현재 스크립트 위치 기준 설정
base_path = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(base_path, '.env')

# 미리 제공받은 정보 (계정: _seheehx_ / 새 앱 적용)
APP_SECRET = "0e51fa759865e761ab3f377a12f68feb"
SHORT_LIVED_TOKEN = "THAAWljTkDMR5BUVNGUWlYWUFuSkZAqTGozbFBIREllMTMtYTlKU1RTRFZAicVNJTGtoMnJmMG1yazE0bWIwVjg0a09nY0o1bTNlZATh4c2NTWkxtLXNmN3ROVHUySVZAoazZA4Vk5aZAmZA4Ukllc2NtRlpBMXRETHFaeE00alphMzl6bUV2cVNfaElpdnYxdG5ZAY3pjUjVJeDlPNy0wbEtvVXFUQXRVb2JRUQZDZD"

def get_long_lived_token():
    url = "https://graph.threads.net/access_token"
    params = {
        "grant_type": "th_exchange_token",
        "client_secret": APP_SECRET,
        "access_token": SHORT_LIVED_TOKEN
    }
    
    print("▶️ 장기 액세스 토큰 발급 요청 중...")
    response = requests.get(url, params=params)
    data = response.json()
    
    if "access_token" in data:
        long_lived_token = data["access_token"]
        print(f"✅ 장기 액세스 토큰 발급 성공!\n{long_lived_token}")
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
    response = requests.get(url, params=params)
    data = response.json()
    
    if "id" in data:
        user_id = data["id"]
        print(f"✅ 사용자 ID 확인 성공: {user_id}")
        return user_id
    else:
        print(f"❌ 사용자 ID 확인 실패: {data}")
        return None

if __name__ == "__main__":
    # 1. 장기 토큰 받기
    long_token = get_long_lived_token()
    
    # 2. 유저 ID 가져오기 (토큰이 성공적으로 발급되었을 경우)
    if long_token:
        user_id = get_user_id(long_token)
        
        # 3. .env 파일에 저장
        if user_id:
            # 작동중코드의 상위 폴더 등에 환경 변수 복사(옵션)
            main_env_path = os.path.join(base_path, '..', '.env')
            
            # .env 파일 생성 또는 덮어쓰기 유틸 (단순화를 위해 직접 기록)
            with open(env_path, 'w') as f:
                f.write(f"THREADS_USER_ID={user_id}\n")
                f.write(f"THREADS_ACCESS_TOKEN={long_token}\n")
                
            print(f"\n🎉 성공적으로 {env_path} 에 자격 증명을 저장했습니다!")
            
            # 상위 폴더의 env 템플릿에도 추가할 수 있도록 안내
            print("\n🚨 기존 작동중코드(Gemini API KEY)가 있는 최상위 .env 파일에도 아래 두 줄을 복사해주세요!")
            print("="*60)
            print(f"THREADS_USER_ID={user_id}")
            print(f"THREADS_ACCESS_TOKEN={long_token}")
            print("="*60)
