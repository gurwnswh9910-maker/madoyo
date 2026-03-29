import os
import requests
import time
import jwt
import uuid
import sys
from datetime import datetime, timedelta, timezone

# 1. JWT 관련 설정 (backend/.env 내용 활용)
SECRET_KEY = "dev-only-insecure-" + "temp-antigravity" # auth_middleware의 로직에 맞춰 서명 시 임시 키 사용
ALGORITHM = "HS256"

# 실제 서버의 SECRET_KEY를 모를 경우, auth_middleware가 JWT_SECRET_KEY가 없으면 임시 키를 생성하므로
# 런타임에 주입되거나 환경 변수를 참조해야 하지만, 현재 테스트를 위해 직접 서명 가능한 토큰을 생성 시도
# (또는 Supabase JWT가 있다면 사용 가능)

API_URL = "https://madoyo-api.onrender.com/api"

def get_test_token():
    # 테스트용 UUID
    test_uid = str(uuid.uuid4())
    test_email = "test_ai@madoyo.com"
    
    # auth_middleware.create_access_token() 로직 모방
    expire = datetime.now(timezone.utc) + timedelta(hours=24)
    payload = {
        "sub": test_uid,
        "email": test_email,
        "exp": expire,
    }
    # 실제 서버가 SUPABASE_JWT_SECRET를 사용한다면 그 값으로 서명해야 함
    # .env에서 가져옴
    SUPABASE_JWT_SECRET = "j0nhA51LhVy0e/9pi/1GHuWDGQGabi4I2rkoBklSgCJ06l1BWhYeWyIrn7B1nZC7ql7kKmmnibWA+5dyQHgAAA=="
    return jwt.encode(payload, SUPABASE_JWT_SECRET, algorithm="HS256")

def test_production():
    token = get_test_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"[*] 1. Health Check...")
    r = requests.get(f"{API_URL}/health")
    print(f"    Status: {r.status_code}, Body: {r.text}")
    
    print(f"\n[*] 2. Starting Generation (Text-Only)...")
    payload = {
        "reference_copy": "똥손도 1초만에 샵퀄리티 네일 완성! 가성비 최고 자석 네일 팁",
        "appeal_point": "99.9% 리팩토링 성공, 메모리 최적화 완료",
        "image_urls": None,
        "reference_url": None
    }
    r = requests.post(f"{API_URL}/generate", json=payload, headers=headers)
    
    if r.status_code != 200:
        print(f"    ❌ FAIL! Code: {r.status_code}, Body: {r.text}")
        return
    
    task_id = r.json().get("task_id")
    print(f"    ✅ Task Created! ID: {task_id}")
    
    # Polling
    print(f"\n[*] 3. Polling for results...")
    for i in range(20):
        r = requests.get(f"{API_URL}/tasks/{task_id}", headers=headers)
        status_data = r.json()
        status = status_data.get("status")
        print(f"    [{i+1}/20] Status: {status}")
        
        if status == "SUCCESS":
            print(f"\n    🎉 SUCCESS! Result found!")
            print(f"    Processed Time: {status_data.get('processing_time')}s")
            # 결과 중 하나 출력
            res = status_data.get("result", {}).get("copies", [])
            if res:
                print(f"    First Copy Sample: {res[0]['copy_text'][:50]}...")
            return
        elif status == "FAILURE":
            print(f"    ❌ FAILURE! Error: {status_data.get('error')}")
            return
        
        time.sleep(3)
    
    print(f"    ⚠️ Timeout! Task is still processing.")

if __name__ == "__main__":
    test_production()
