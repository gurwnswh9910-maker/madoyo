import os
import hmac
import hashlib
import time
import requests
import urllib.parse
from dotenv import load_dotenv

# 환경변수 로드
base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
load_dotenv(os.path.join(base_path, '.env'))
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

def generate_hmac(method, url, secret_key, access_key):
    path, *query = url.split("?")
    datetime_str = time.strftime('%y%m%d', time.gmtime()) + 'T' + time.strftime('%H%M%S', time.gmtime()) + 'Z'
    message = datetime_str + method + path + (query[0] if query else "")
    
    signature = hmac.new(
        bytes(secret_key, "utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={datetime_str}, signature={signature}"

def search_coupang_product(keyword, limit=1):
    access_key = os.getenv("COUPANG_ACCESS_KEY")
    secret_key = os.getenv("COUPANG_SECRET_KEY")
    if not access_key or not secret_key:
        return None

    method = "GET"
    encoded_keyword = urllib.parse.quote(keyword)
    url_path = f"/v2/providers/affiliate_open_api/apis/openapi/products/search?keyword={encoded_keyword}&limit={limit}"
    authorization = generate_hmac(method, url_path, secret_key, access_key)
    headers = {"Authorization": authorization, "Content-Type": "application/json"}
    request_url = "https://api-gateway.coupang.com" + url_path
    
    try:
        response = requests.get(request_url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            products = data.get("data", {}).get("productData", [])
            if products:
                p = products[0]
                return {"product_name": p.get("productName"), "product_url": p.get("productUrl"), "product_image": p.get("productImage")}
        return None
    except Exception:
        return None

def extract_and_convert_coupang_link(threads_or_short_url):
    """
    쓰레드에 있는 단축 URL(link.coupang.com)이나 l.threads.com 마스킹 URL을 받아서
    실제 쿠팡 상품/검색 페이지로 리다이렉트 한 뒤, 내 파트너스 딥링크로 변환하여 반환합니다.
    """
    import urllib.parse
    import requests
    
    # 1. 쓰레드 l.threads.com URL인 경우 u 파라미터에서 원본 링크 추출
    if "l.threads.com" in threads_or_short_url:
        parsed_url = urllib.parse.urlparse(threads_or_short_url)
        qs = urllib.parse.parse_qs(parsed_url.query)
        if 'u' in qs:
            target_url = qs['u'][0]
        else:
            target_url = threads_or_short_url
    else:
        target_url = threads_or_short_url
        
    # 2. link.coupang.com 단축 URL의 실제 도착지(Location) 확인
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    try:
        response = requests.get(target_url, headers=headers, allow_redirects=False, timeout=10)
        actual_url = target_url # 기본값
        if response.status_code in (301, 302) and 'Location' in response.headers:
            actual_url = response.headers['Location']
    except Exception as e:
        print(f"⚠️ URL 리다이렉트 추적 실패: {e}")
        actual_url = target_url
        
    # 만약 도착지가 여전히 쿠팡 링크가 아니거나, 추출 실패했다면 원본 반환
    if "coupang.com" not in actual_url:
        return None
        
    # 3. 실제 쿠팡 URL을 DeepLink API로 변환
    result = generate_deep_links([actual_url])
    if result and len(result) > 0:
        return result[0].get("shortenUrl")
    
    return None

def generate_deep_links(coupang_urls):
    access_key = os.getenv("COUPANG_ACCESS_KEY")
    secret_key = os.getenv("COUPANG_SECRET_KEY")
    if not access_key or not secret_key:
        return None

    method = "POST"
    url_path = "/v2/providers/affiliate_open_api/apis/openapi/v1/deeplink"
    
    # URL 정제 (API가 요구하는 JSON 배열 형태로 준비)
    if not isinstance(coupang_urls, list):
        coupang_urls = [coupang_urls]

    authorization = generate_hmac(method, url_path, secret_key, access_key)
    headers = {"Authorization": authorization, "Content-Type": "application/json"}
    payload = {"coupangUrls": coupang_urls}
    request_url = "https://api-gateway.coupang.com" + url_path
    
    try:
        response = requests.post(request_url, headers=headers, json=payload)
        if response.status_code == 200:
            data = response.json()
            if data.get("rCode") == "0":
                return data.get("data", [])
            else:
                print(f"[Coupang API Error] {data.get('rCode')}: {data.get('rMessage')}")
                return None
        else:
            print(f"[Coupang HTTP Error] {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print(f"[Coupang API Exception] {e}")
        return None
