import os
import sys
import requests
import time
import jwt
import uuid
import io
from datetime import datetime, timedelta, timezone

# Windows UTF-8 Output 처리
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 1. JWT 및 API 설정
SUPABASE_JWT_SECRET = "j0nhA51LhVy0e/9pi/1GHuWDGQGabi4I2rkoBklSgCJ06l1BWhYeWyIrn7B1nZC7ql7kKmmnibWA+5dyQHgAAA=="
API_URL = "https://madoyo-api.onrender.com/api"

def get_test_token():
    import base64
    test_uid = str(uuid.uuid4())
    test_email = f"test_{test_uid[:8]}@madoyo.ai"
    expire = datetime.now(timezone.utc) + timedelta(hours=1)
    payload = {
        "sub": test_uid,
        "email": test_email,
        "role": "authenticated", # Supabase 필드 대응
        "exp": expire,
    }
    
    # 서버의 base64 디코딩 로직과 동일하게 처리
    secret = SUPABASE_JWT_SECRET
    try:
        missing_padding = len(secret) % 4
        if missing_padding: secret += '=' * (4 - missing_padding)
        decoded_secret = base64.b64decode(secret)
    except:
        decoded_secret = secret
        
    return jwt.encode(payload, decoded_secret, algorithm="HS256")

def run_task_test(name, payload, headers):
    print(f"\n[*] Testing: {name}...")
    try:
        r = requests.post(f"{API_URL}/generate", json=payload, headers=headers, timeout=30)
        if r.status_code != 200:
            print(f"    [FAIL] Code: {r.status_code}, Body: {r.text}")
            return False
            
        task_id = r.json().get("task_id")
        print(f"    [OK] Task Created: {task_id}")
        
        for i in range(40):
            time.sleep(3)
            res = requests.get(f"{API_URL}/tasks/{task_id}", headers=headers, timeout=10)
            status_data = res.json()
            status = status_data.get("status")
            print(f"    [{i+1}/40] Status: {status}")
            
            if status == "SUCCESS":
                rank1_copy = status_data.get("result", {}).get("copies", [{}])[0].get("copy_text", "")
                print(f"    [SUCCESS] Content Rank #1: {rank1_copy[:50]}...")
                return True
            if status in ["FAILURE", "ERROR", "error"]:
                print(f"    [FAIL] Result Error: {status_data.get('error')}")
                return False
        
        print(f"    [TIMEOUT] Task took too long.")
        return False
    except Exception as e:
        print(f"    [EXCEPTION] {str(e)}")
        return False

def main():
    token = get_test_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    print(">>> Madoyo Production V9 Final Verification <<<")
    
    # [Test 1] Text-only
    text_payload = {
        "reference_copy": "안정화 최적화 완료! 마도요 AI 텍스트 전용 테스트입니다.",
        "appeal_point": "빠른 속도, 정확한 전략 매칭",
        "image_urls": [],
        "reference_url": None
    }
    t1 = run_task_test("Text-Only Generation", text_payload, headers)
    
    # [Test 2] Multi-Image
    image_payload = {
        "reference_copy": "멀티모달 이미지 분석 테스트입니다.",
        "appeal_point": "시각적 요소와 카피의 조화",
        "image_urls": [
            "https://images.unsplash.com/photo-1542291026-7eec264c27ff",
            "https://images.unsplash.com/photo-1523275335684-37898b6baf30"
        ],
        "reference_url": None
    }
    t2 = run_task_test("Multi-Modal (2 Images)", image_payload, headers)
    
    print("\n" + "="*50)
    print(f"FINAL RESULT Summary:")
    print(f" - Text-Only  : {'PASS' if t1 else 'FAIL'}")
    print(f" - Multi-Modal: {'PASS' if t2 else 'FAIL'}")
    print("="*50)

if __name__ == "__main__":
    main()
