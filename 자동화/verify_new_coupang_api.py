import sys
import io

# UTF-8 출력 설정
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

import os
import requests
import hmac
import hashlib
import time
import json
import urllib.parse
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)


def normalize_account_slot(value):
    slot = str(value or "1").split(",", 1)[0].strip()
    if slot.upper().startswith("ACCOUNT_"):
        slot = slot.split("_", 1)[1]
    return slot or "1"


def load_verify_credentials():
    slot = normalize_account_slot(os.getenv("COUPANG_VERIFY_ACCOUNT") or os.getenv("COUPANG_CURRENT_ACCOUNT") or "1")
    access_key = os.getenv("COUPANG_VERIFY_ACCESS_KEY") or os.getenv(f"COUPANG_ACCESS_KEY_{slot}") or os.getenv("COUPANG_ACCESS_KEY")
    secret_key = os.getenv("COUPANG_VERIFY_SECRET_KEY") or os.getenv(f"COUPANG_SECRET_KEY_{slot}") or os.getenv("COUPANG_SECRET_KEY")
    if not access_key or not secret_key:
        raise SystemExit(
            "쿠팡 검증 키가 없습니다. COUPANG_VERIFY_ACCESS_KEY/COUPANG_VERIFY_SECRET_KEY "
            "또는 COUPANG_ACCESS_KEY_<번호>/COUPANG_SECRET_KEY_<번호>를 .env에 넣어주세요."
        )
    return slot, access_key, secret_key


def verify_key(access_key, secret_key, expected_id=None):
    # 검색 API 사용 (유효성 검증용)
    method = "GET"
    keyword = urllib.parse.quote("마스크")
    url_path = f"/v2/providers/affiliate_open_api/apis/openapi/products/search?keyword={keyword}&limit=1"
    
    datetime_str = time.strftime('%y%m%d', time.gmtime()) + 'T' + time.strftime('%H%M%S', time.gmtime()) + 'Z'
    path, *query = url_path.split("?")
    message = datetime_str + method + path + (query[0] if query else "")
    
    signature = hmac.new(
        bytes(secret_key, "utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    
    authorization = f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={datetime_str}, signature={signature}"
    headers = {"Authorization": authorization, "Content-Type": "application/json"}
    request_url = "https://api-gateway.coupang.com" + url_path
    
    print(f"[Search] 새 쿠팡 API 키 검증 시도 중... (Search API)")
    try:
        response = requests.get(request_url, headers=headers, timeout=12)
        print(f"[Status] 응답 코드: {response.status_code}")
        data = response.json()
        print(f"[Data] 전체 응답: {json.dumps(data, indent=2, ensure_ascii=False)}")
        
        if data.get("rCode") == "0":
            print("[Success] API 요청 성공!")
            if expected_id:
                res_str = json.dumps(data)
                if expected_id in res_str:
                    print(f"[Verified] 검증 성공! ID '{expected_id}'가 확인되었습니다.")
                else:
                    print(f"[Warning] 요청은 성공했으나 ID '{expected_id}'를 찾을 수 없습니다.")
        else:
            print(f"[Fail] API 요청 실패: {data.get('rMessage')}")
            
    except Exception as e:
        print(f"[Exception] 예외 발생: {e}")

if __name__ == "__main__":
    account_slot, access, secret = load_verify_credentials()
    expected = os.getenv("COUPANG_VERIFY_EXPECTED_ID")
    print(f"[Info] 쿠팡 {account_slot}번 키를 검증합니다.")
    verify_key(access, secret, expected_id=expected)
