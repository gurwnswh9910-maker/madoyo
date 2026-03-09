
import os
import hmac
import hashlib
import time
import requests
import json
from dotenv import load_dotenv

# 환경변수 로드
env_path = r'c:\Users\ding9\Desktop\madoyo\자동화\.env'
load_dotenv(env_path)

access_key = os.getenv("COUPANG_ACCESS_KEY")
secret_key = os.getenv("COUPANG_SECRET_KEY")

def generate_hmac(method, url, secret_key, access_key):
    path, *query = url.split("?")
    datetime_str = time.strftime('%y%m%d', time.gmtime()) + 'T' + time.strftime('%H%M%S', time.gmtime()) + 'Z'
    message = datetime_str + method + path + (query[0] if query else "")
    signature = hmac.new(bytes(secret_key, "utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={datetime_str}, signature={signature}"

def test_link(api_path, coupang_url):
    authorization = generate_hmac("POST", api_path, secret_key, access_key)
    headers = {"Authorization": authorization, "Content-Type": "application/json"}
    payload = {"coupangUrls": [coupang_url]}
    request_url = "https://api-gateway.coupang.com" + api_path
    try:
        response = requests.post(request_url, headers=headers, json=payload)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

# 테스트할 URL 조합
urls_to_test = [
    "https://www.coupang.com/vp/products/9329995493", # PC 기본
    "https://www.coupang.com/vp/products/9329995493?itemId=27661830209", # PC + ItemId
    "https://link.coupang.com/a/dS6qaa", # 이미 파트너스 링크인 경우 (재변환 테스트)
]

# 테스트할 API 엔드포인트
endpoints = [
    "/v2/providers/affiliate_open_api/apis/openapi/v1/deeplink",
    "/v2/providers/affiliate_open_api/apis/openapi/v1/deeplinks"
]

results = {}
for ep in endpoints:
    for url in urls_to_test:
        res = test_link(ep, url)
        results[f"{ep} | {url}"] = res

print(json.dumps(results, indent=2, ensure_ascii=False))
