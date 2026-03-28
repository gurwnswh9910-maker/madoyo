import sys
import os
import requests
import jwt
from datetime import datetime, timedelta, timezone

# 1. JWT 토큰 생성 (test@madoyo.io)
USER_ID = "0707f6e8-3bd7-4a05-9455-8291b56a727a"
EMAIL = "test@madoyo.io"
# .env에서 SECRET_KEY를 가져옵니다.
from dotenv import load_dotenv
load_dotenv(os.path.join(os.getcwd(), "..", ".env"))
SECRET_KEY = os.getenv("JWT_SECRET_KEY")

payload = {
    "sub": USER_ID,
    "email": EMAIL,
    "exp": datetime.now(timezone.utc) + timedelta(hours=24),
}
token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

# 2. 테스트용 Threads URL
URL = "https://www.threads.net/@_tokkimom_/post/DVEKQpjkmt0"

# 3. API 요청 (/api/generate)
print(f"🚀 API 요청 중... (URL: {URL})")
data = {
    "reference_url": [URL],  # Wrap in list as per schema
    "reference_copy": "진짜 좋음 ㅋㅋ",
    "appeal_point": "가성비 갑"
}

import time
for i in range(5):
    try:
        # Increase timeout to 120s as generation is heavy (scraping + gems + scoring)
        resp = requests.post("http://127.0.0.1:8000/api/generate", json=data, headers=headers, timeout=120)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.json()}")
        break
    except Exception as e:
        print(f"Attempt {i+1} failed: {e}")
        time.sleep(2)
