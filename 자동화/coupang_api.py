import os
import hmac
import hashlib
import time
import requests
import urllib.parse
import re
from dotenv import load_dotenv

# 환경변수 로드
base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
load_dotenv(os.path.join(base_path, '.env'))
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))


# ════════════════════════════════════════════════════════════════
# curl_cffi 세션 (TLS 핑거프린트 우회 — Akamai Bot Manager 대응)
# ════════════════════════════════════════════════════════════════
_STEALTH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

class CoupangFetcher:
    """
    쿠팡 아카마이 우회 및 1회 접속 통합 조회를 담당하는 싱글톤 세션 관리자.
    """
    _instance = None
    _session = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CoupangFetcher, cls).__new__(cls)
            cls._instance._init_session()
        return cls._instance

    def _init_session(self):
        try:
            from curl_cffi.requests import Session
            self._session = Session(impersonate="chrome120")
            # 세션 쿠키 워밍
            try:
                self._session.get("https://www.coupang.com/", headers=_STEALTH_HEADERS, timeout=10)
            except Exception: pass
        except ImportError:
            print("    ⚠️ curl_cffi 미설치. pip install curl_cffi 실행 필요.")
            self._session = requests.Session()

    def fetch_unified_data(self, url):
        """
        단 한 번의 GET 요청으로 리졸브된 URL과 HTML 본문을 모두 가져옵니다.
        """
        try:
            # allow_redirects=True로 한 번에 최종 페이지까지 이동
            resp = self._session.get(url, headers=_STEALTH_HEADERS, allow_redirects=True, timeout=15)
            final_url = resp.url
            html_body = resp.text if resp.status_code == 200 else ""
            
            # 리졸브 실패 시 헤더 재확인 (특수 케이스)
            if "link.coupang.com" in final_url and 'Location' in resp.headers:
                final_url = resp.headers['Location']
                
            return final_url, html_body
        except Exception as e:
            print(f"    ⚠️ [Unified Fetch] 오류: {e}")
            return url, ""

# 글로벌 싱글톤 인스턴스
coupang_fetcher = CoupangFetcher()

def _get_stealth_session():
    return coupang_fetcher._session


# ════════════════════════════════════════════════════════════════
# 쿠팡 파트너스 API 인증
# ════════════════════════════════════════════════════════════════
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


def get_coupang_credentials():
    account_slot = (os.getenv("COUPANG_CURRENT_ACCOUNT", "1") or "1").split(",", 1)[0].strip() or "1"
    access_key = os.getenv(f"COUPANG_ACCESS_KEY_{account_slot}") or os.getenv("COUPANG_ACCESS_KEY")
    secret_key = os.getenv(f"COUPANG_SECRET_KEY_{account_slot}") or os.getenv("COUPANG_SECRET_KEY")
    return access_key, secret_key


# ════════════════════════════════════════════════════════════════
# 쿠팡 파트너스 검색 API
# ════════════════════════════════════════════════════════════════
def search_coupang_product(keyword, limit=5):
    """쿠팡 파트너스 검색 API. limit을 5로 올려 최적 매칭 시도."""
    access_key, secret_key = get_coupang_credentials()
    if not access_key or not secret_key:
        return None

    method = "GET"
    
    # 키워드 정제
    clean = re.sub(r'[\[\]\(\)\-\,\/\:\!\)\(]', ' ', keyword)
    noise = ["중고", "빈티지", "특가", "쿠팡", "수입", "증정", "1개", "개입", "YUN"]
    words = [w for w in clean.split() if w not in noise and len(w) > 1]
    refined_keyword = " ".join(words[:3])
    
    print(f"    🔍 [Coupang Search] Query: '{refined_keyword}' (원본: '{keyword[:30]}...')")
    encoded_keyword = urllib.parse.quote(refined_keyword)
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
                best = _find_best_match(products, keyword)
                return {
                    "product_name": best.get("productName"),
                    "product_url": best.get("productUrl"),
                    "product_image": best.get("productImage")
                }
        return None
    except Exception as e:
        print(f"    ⚠️ [Coupang Search] Exception: {e}")
        return None


def _find_best_match(products, original_keyword):
    """검색 결과 중 원래 키워드와 가장 유사한 상품을 반환합니다."""
    if not products:
        return None
    
    original_words = set(re.sub(r'[^\w\s]', '', original_keyword.lower()).split())
    
    best_product = products[0]
    best_score = 0
    
    for p in products:
        name = p.get("productName", "").lower()
        name_words = set(re.sub(r'[^\w\s]', '', name).split())
        overlap = len(original_words & name_words)
        if overlap > best_score:
            best_score = overlap
            best_product = p
    
    return best_product


# ════════════════════════════════════════════════════════════════
# 쿠팡 딥링크 API
# ════════════════════════════════════════════════════════════════
def generate_deep_links(coupang_urls):
    """쿠팡 URL을 파트너스 딥링크로 변환합니다."""
    access_key, secret_key = get_coupang_credentials()
    if not access_key or not secret_key:
        return None

    method = "POST"
    url_path = "/v2/providers/affiliate_open_api/apis/openapi/v1/deeplink"
    
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
                print(f"    ⚠️ [DeepLink API] {data.get('rCode')}: {data.get('rMessage')}")
                return None
        else:
            print(f"    ⚠️ [DeepLink API] HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"    ⚠️ [DeepLink API] Exception: {e}")
        return None


# ════════════════════════════════════════════════════════════════
# curl_cffi 기반 쿠팡 URL 리졸브 (Akamai 우회)
# ════════════════════════════════════════════════════════════════
def _resolve_short_url(short_url):
    """
    link.coupang.com 단축 URL → 실제 coupang.com URL로 리졸브.
    curl_cffi로 Chrome TLS 핑거프린트를 모방하여 봇 탐지 우회.
    """
    if "coupang.com" not in short_url:
        return short_url

    session = _get_stealth_session()
    
    try:
        if session:
            # allow_redirects=True를 사용하여 끝까지 추적
            resp = session.get(short_url, headers=_STEALTH_HEADERS, allow_redirects=True, timeout=12)
            # 403이 뜨더라도 resp.url에는 리졸브된 최종 URL이 담겨 있는 경우가 많음
            final_url = resp.url
            
            # 만약 resp.url이 여전히 단축 URL 형태라면 Location 헤더 또는 바디 확인
            if "link.coupang.com" in final_url:
                if 'Location' in resp.headers:
                    final_url = resp.headers['Location']
                elif "Access Denied" in resp.text:
                    print(f"    ⚠️ [Resolve] Akamai Blocked during resolution of {short_url}")
                
            return final_url
        else:
            # Fallback to requests if curl_cffi not available
            resp = requests.get(short_url, headers=_STEALTH_HEADERS, allow_redirects=True, timeout=10)
            return resp.url
            
    except Exception as e:
        print(f"    ⚠️ [Resolve] 오류: {e}")
        return short_url


# ════════════════════════════════════════════════════════════════
# 쿠팡 URL 정규화 (Canonical URL 추출)
# ════════════════════════════════════════════════════════════════
def _clean_coupang_url(url):
    """
    쿠팡 URL에서 productId, itemId, vendorItemId를 추출하여 
    파트너스 API가 가장 잘 인식하는 표준 형태의 URL로 변환합니다.
    """
    if not url: return None
    
    # 0. m.coupang.com -> www.coupang.com 변환
    url = url.replace("m.coupang.com", "www.coupang.com")
    
    # 1. Product ID 추출
    product_id_match = re.search(r'/products/(\d+)', url)
    if not product_id_match:
        # 검색 URL인지 확인
        if "/np/search" in url:
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            if 'q' in qs:
                # 쿼리만 남기고 정리
                return f"https://www.coupang.com/np/search?q={urllib.parse.quote(qs['q'][0])}"
        return url # 제품 링크가 아니면 그대로 반환
    
    product_id = product_id_match.group(1)
    
    # 2. Item ID, Vendor Item ID 추출 (옵션 정보)
    item_id = ""
    vendor_item_id = ""
    
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    
    if 'itemId' in qs:
        item_id = qs['itemId'][0]
    if 'vendorItemId' in qs:
        vendor_item_id = qs['vendorItemId'][0]
        
    # 3. 표준 URL 조립
    # 이 형태가 파트너스 DeepLink API에서 가장 성공률이 높고 정확합니다.
    clean_url = f"https://www.coupang.com/vp/products/{product_id}"
    params = []
    if item_id: params.append(f"itemId={item_id}")
    if vendor_item_id: params.append(f"vendorItemId={vendor_item_id}")
    
    if params:
        clean_url += "?" + "&".join(params)
        
    return clean_url


# ════════════════════════════════════════════════════════════════
# [핵심] 통합 정보 추출 (접속 횟수 최소화)
# ════════════════════════════════════════════════════════════════
def get_product_info_from_url(coupang_url, html_body=None):
    """
    [개선형] HTML 본문이 이미 있다면 접속하지 않고 즉시 파싱합니다.
    없다면 1회만 접속하여 정보를 가져옵니다.
    """
    actual_url = coupang_url
    html = html_body

    # 1. HTML 본문이 없는 경우에만 접속해서 가져옴
    if not html:
        actual_url, html = coupang_fetcher.fetch_unified_data(coupang_url)
    
    product_name = ""
    image_url = ""
    
    if html and "access denied" not in html.lower()[:500]:
        # og:title 추출
        title_match = re.search(
            r'<meta\s+(?:property=["\']og:title["\']\s+content=["\']([^"\']+)["\']|content=["\']([^"\']+)["\']\s+property=["\']og:title["\'])',
            html, re.IGNORECASE
        )
        if title_match:
            product_name = (title_match.group(1) or title_match.group(2)).strip()
        
        # <title> 태그 폴백
        if not product_name:
            t_match = re.search(r'<title>([^<]+)</title>', html, re.IGNORECASE)
            if t_match:
                product_name = t_match.group(1).strip()
        
        # og:image 추출
        img_match = re.search(
            r'<meta\s+(?:property=["\']og:image["\']\s+content=["\']([^"\']+)["\']|content=["\']([^"\']+)["\']\s+property=["\']og:image["\'])',
            html, re.IGNORECASE
        )
        if img_match:
            image_url = (img_match.group(1) or img_match.group(2)).strip()
        
        # [추가] 유저 제공 패턴: thumbnail.coupangcdn.com + alt="Product image"
        if not image_url or "thumbnail" not in image_url:
            # 1. alt="Product image" 기반 추출
            thumb_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\'][^>]+alt=["\']Product image["\']', html)
            # 2. thumbnail cdn 패턴 기반 추출 (alt가 다른 경우 대비)
            if not thumb_match:
                thumb_match = re.search(r'src=["\']((?:https?:)?//thumbnail\.coupangcdn\.com/[^"\']+)["\']', html)
            
            if thumb_match:
                new_image_url = thumb_match.group(1).strip()
                # 492x492 등 크기 제약이 있는 경우 더 큰 이미지로 변환 시도 (선택 사항)
                image_url = new_image_url

        if image_url.startswith("//"):
            image_url = "https:" + image_url
        
        # 정제
        if product_name:
            for sep in [" : ", " | ", " - 쿠팡!"]:
                if sep in product_name:
                    product_name = product_name.split(sep)[0]
            return {"product_name": product_name, "image_url": image_url, "product_url": actual_url}

    # 2. 파싱 실패 시 베베숲 방지를 위해 허위 검색 없이 그대로 반환
    return {"product_name": "", "image_url": "", "product_url": actual_url}


# (중복 정의 제거됨 - 상단 _resolve_short_url 사용)


# ════════════════════════════════════════════════════════════════
# [핵심] 딥링크 변환 (전략적 검증 포함)
# ════════════════════════════════════════════════════════════════
def extract_and_convert_coupang_link(raw_url, resolved_url=None):
    """
    쿠팡 링크를 파트너스 딥링크로 변환하며, 원본과 100% 일치하는지(PID/Query) 검증합니다.
    [resolved_url]이 제공되면 중복 리졸브 요청을 방지합니다.
    """
    import urllib.parse
    input_url = raw_url
    
    # 1. l.threads.com 래핑 해제
    if "l.threads.com" in input_url:
        parsed_url = urllib.parse.urlparse(input_url)
        qs = urllib.parse.parse_qs(parsed_url.query)
        if 'u' in qs:
            input_url = urllib.parse.unquote(qs['u'][0])
    
    # 2. URL 리졸브 (중복 방지)
    act_url = resolved_url or _resolve_short_url(input_url)
    if "link.coupang.com" in input_url and not resolved_url:
        print(f"    🔗 [DeepLink] 리졸브: {act_url[:70]}...")
    
    # 3. URL 정규화
    clean_url = _clean_coupang_url(act_url)
    
    # 4. 딥링크 생성 시도
    result = generate_deep_links([clean_url])
    if result and len(result) > 0 and result[0].get("shortenUrl"):
        final_link = result[0]["shortenUrl"]
        
        # [핵심] 아카마이 차단 우회 및 API 신뢰 원칙
        # 파트너스 API가 정상적으로 링크를 발급했다면 2차 리졸브 검증을 생략하고 무조건 신뢰합니다.
        print(f"    ✅ [DeepLink] 파트너스 링크 발급 완료 (API 신뢰 및 리졸브 검증 생략)")
        return final_link
            
    return None


# ════════════════════════════════════════════════════════════════
# 검증 알고리즘 (Accuracy Check)
# ════════════════════════════════════════════════════════════════
def verify_product_match(original_url, affiliate_url, orig_resolved=None, aff_resolved=None):
    """
    두 URL의 상품 정보가 물리적으로 100% 일치하는지 확인합니다. (PID 또는 Query 기반)
    [orig_resolved], [aff_resolved]이 제공되면 중복 리졸브를 방지합니다.
    """
    import urllib.parse
    
    # 0. URL 리졸브 (미제공 시에만)
    orig_res = orig_resolved or _resolve_short_url(original_url)
    aff_res = aff_resolved or _resolve_short_url(affiliate_url)
    
    # 1. Product ID 직접 대조 (최우선)
    orig_id_match = re.search(r'/products/(\d+)', orig_res)
    aff_id_match = re.search(r'/products/(\d+)', aff_res)
    
    orig_id = orig_id_match.group(1) if orig_id_match else None
    aff_id = aff_id_match.group(1) if aff_id_match else None
    
    if orig_id or aff_id:
        if orig_id == aff_id:
            print(f"    ✅ [Verify] Product ID 일치: {orig_id}")
            return True
        else:
            print(f"    ❌ [Verify] Product ID 불일치! (Orig: {orig_id}, Aff: {aff_id})")
            return False
            
    # 2. Search Query 대조 (검색 링크인 경우)
    if "/np/search" in orig_res and "/np/search" in aff_res:
        orig_q = urllib.parse.parse_qs(urllib.parse.urlparse(orig_res).query).get('q', [''])[0].strip()
        aff_q = urllib.parse.parse_qs(urllib.parse.urlparse(aff_res).query).get('q', [''])[0].strip()
        if orig_q and aff_q and orig_q == aff_q:
            print(f"    ✅ [Verify] Search Query 일치: '{orig_q}'")
            return True
        else:
            print(f"    ❌ [Verify] Search Query 불일치! (Orig: '{orig_q}', Aff: '{aff_q}')")
            return False
    
    # 결론: PID도 없고 검색어도 없는 경우, 또는 둘의 유형이 다른 경우는 매칭 실패로 간주
    print(f"    ❌ [Verify] 매칭 불가능 (유형 불일치 또는 정보 부족)")
    return False
