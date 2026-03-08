import os
import sys
import io
import time
import glob
import shutil
import argparse
import requests
import pandas as pd

# UTF-8 출력 설정 (Windows 콘솔 이모티콘 깨짐 방지)
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

from dotenv import load_dotenv
from google import genai

# ── 경로 설정 ──────────────────────────────────────────────────
BASE_DIR  = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
AUTO_DIR  = os.path.dirname(__file__)
CODE_DIR  = os.path.join(BASE_DIR, '작동중코드')
REF_DIR   = os.path.join(AUTO_DIR, '자동화참조')           # 입력 엑셀 폴더
DONE_DIR  = os.path.join(REF_DIR, '업로드완료')            # 완료 후 이동 폴더

sys.path.insert(0, AUTO_DIR)
sys.path.insert(0, CODE_DIR)

# .env 로드 (기본값, 실행 시 덮어씌울 수 있음)
load_dotenv(os.path.join(BASE_DIR, '.env'))
load_dotenv(os.path.join(AUTO_DIR, '.env'))

from scraper import scrape_thread_content, scrape_comment_for_coupang, fetch_coupang_product_info, fetch_and_rehost, init_driver
from publisher import upload_to_threads
from coupang_api import generate_deep_links, search_coupang_product
from optimize_copy_v2 import run_optimization
from concurrent.futures import ThreadPoolExecutor
from marketing_focus_extractor import extract_marketing_focus

# ────────────────────────────────────────────────────────────────
# 경로 및 상수
# ────────────────────────────────────────────────────────────────
PROCESSED_LOG = os.path.join(AUTO_DIR, "processed_links.log")
STOP_SIGNAL_FILE = os.path.join(AUTO_DIR, "stop.txt")

def check_stop_signal():
    """stop.txt 파일이 존재할 경우 True 반환."""
    return os.path.exists(STOP_SIGNAL_FILE)

def load_processed_links():
    """처리 완료된 링크 목록 로드."""
    if not os.path.exists(PROCESSED_LOG):
        return set()
    with open(PROCESSED_LOG, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def log_processed_link(url):
    """처리 완료된 링크 기록."""
    with open(PROCESSED_LOG, "a", encoding="utf-8") as f:
        f.write(url + "\n")

# ────────────────────────────────────────────────────────────────
# API 키 입력 (실행 시 대화형 입력 또는 .env 우선)
# ────────────────────────────────────────────────────────────────
def prompt_api_keys():
    """
    실행 시 누락된 API 키를 대화형으로 입력받습니다.
    .env나 환경변수에 이미 값이 있으면 그대로 사용합니다.
    """
    keys = {
        "GEMINI_API_KEY":       ("Gemini API Key",               False),
        "THREADS_USER_ID":      ("Threads User ID",              False),
        "THREADS_ACCESS_TOKEN": ("Threads Access Token",         True),
        "COUPANG_ACCESS_KEY":   ("Coupang Partners Access Key",  False),
        "COUPANG_SECRET_KEY":   ("Coupang Partners Secret Key",  True),
    }
    updated = False
    for env_key, (label, is_secret) in keys.items():
        current = os.getenv(env_key, "")
        if not current:
            if is_secret:
                import getpass
                val = getpass.getpass(f"  {label}: ")
            else:
                val = input(f"  {label}: ").strip()
            if val:
                os.environ[env_key] = val
                updated = True
            else:
                print(f"  ⚠️ {label} 미입력 (건너뜀)")
    return updated


# ────────────────────────────────────────────────────────────────
# 헬퍼
# ────────────────────────────────────────────────────────────────
def shorten_url_isgd(long_url):
    """is.gd API를 사용하여 URL을 단축합니다."""
    try:
        api_url = f"https://is.gd/create.php?format=simple&url={requests.utils.quote(long_url)}"
        resp = requests.get(api_url, timeout=5)
        if resp.status_code == 200:
            return resp.text.strip()
    except Exception as e:
        print(f"    ⚠️ URL 단축 실패 (is.gd): {e}")
    return None

def get_gemini_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY가 설정되어 있지 않습니다.")
    return genai.Client(api_key=api_key)



def shorten_url(long_url: str) -> str:
    """is.gd API를 사용하여 URL을 단축합니다."""
    import requests as req
    try:
        api_url = f"https://is.gd/create.php?format=json&url={long_url}"
        r = req.get(api_url, timeout=5)
        if r.status_code == 200:
            return r.json().get("shorturl", long_url)
    except Exception:
        pass
    return long_url


def build_affiliate_comment(product_name: str, product_url: str) -> str:
    """사용자 지정 템플릿 적용 (수수료 멘트 최상단 + 단축 링크)"""
    # 제품명 대신 '제품명' 문자열을 그대로 사용하여 궁금증 유발 (사용자 요청)
    return (
        f"이 포스팅은 쿠팡파트너스 활동의\n"
        f"일정액 수수료를 제공받습니다.\n"
        f"=-=-=-=-=-=-=-=-=-=-=-=-=\n"
        f"😆진짜 넘 좋다ㅋㅋ\n\n"
        f"✅️안사도 되니까 한번 보구가~~\n"
        f"🔻아래에서 제품명 자세히보기\n"
        f"{product_url}\n"
        f"{product_url}"
    )


def filter_public_image_urls(urls: list) -> list:
    """scontent 등 로그인 필요 CDN 제거 후 공개 이미지 URL만 반환."""
    import requests as req
    BLOCKED = ["scontent", "cdninstagram"]
    public = []
    for url in urls:
        if any(d in url for d in BLOCKED):
            continue
        try:
            r = req.head(url, timeout=5, allow_redirects=True)
            if r.status_code == 200 and ("image" in r.headers.get("Content-Type", "") or
                                          "video" in r.headers.get("Content-Type", "")):
                public.append(url)
        except Exception:
            pass
    return public


def collect_links_from_excel(excel_path: str) -> list:
    """엑셀 파일에서 링크와 (선택적) 본문 목록을 추출합니다."""
    # 임시 파일이나 권한 문제 방지
    try:
        df = pd.read_excel(excel_path, engine='openpyxl')
    except Exception:
        return []
        
    link_col = None
    body_col = None
    
    for col in df.columns:
        col_name = str(col).strip()
        sample = str(df[col].dropna().iloc[0]) if not df[col].dropna().empty else ""
        
        # 링크 칼럼 탐색: 정확한 '링크' 선호
        if col_name == "링크":
            link_col = col
        elif link_col is None and (sample.startswith("http") or "링크" in col_name):
            link_col = col
            
        # 본문 칼럼 탐색: 정확한 '본문' 선호
        if col_name == "본문":
            body_col = col
        elif body_col is None and "본문" in col_name and "조회수" not in col_name:
            body_col = col
            
    if link_col is None:
        link_col = df.columns[0]
        
    records = []
    # 중복 링크를 방지하기 위해 집합 사용
    seen = set()
    for _, row in df.iterrows():
        l = str(row[link_col])
        if l.startswith("http") and l not in seen:
            seen.add(l)
            body_text = str(row[body_col]) if body_col and pd.notna(row[body_col]) else ""
            records.append({"url": l, "body": body_text})
            
    return records


def move_to_done(excel_path: str):
    """처리 완료된 엑셀 파일을 업로드완료 폴더로 이동합니다."""
    os.makedirs(DONE_DIR, exist_ok=True)
    fname = os.path.basename(excel_path)
    dest = os.path.join(DONE_DIR, fname)
    # 이미 같은 이름 있으면 타임스탬프 추가
    if os.path.exists(dest):
        base, ext = os.path.splitext(fname)
        dest = os.path.join(DONE_DIR, f"{base}_{int(time.time())}{ext}")
    shutil.move(excel_path, dest)
    print(f"  📁 파일 이동 완료: {fname} → 업로드완료/", flush=True)


# ────────────────────────────────────────────────────────────────
# 링크 1개 처리 핵심 로직
# ────────────────────────────────────────────────────────────────
def process_single_link(url_data: dict, client, threads_user_id: str,
                         threads_token: str, dry_run: bool) -> bool:
    """단일 Threads 링크를 처리합니다. 성공 시 True, SKIP/실패 시 False 반환."""

    url = url_data.get("url")
    excel_body = url_data.get("body", "")
    
    driver = init_driver()
    try:
        # STEP 1: 댓글 쿠팡 링크 탐색
        print("  [1/5] 댓글 쿠팡 링크 탐색 중...", flush=True)
        coupang_result = scrape_comment_for_coupang(url, driver=driver)
        if not coupang_result:
            print("  ⏭️  쿠팡 링크 없음 → SKIP", flush=True)
            return False

        raw_coupang_url = coupang_result['coupang_urls'][0]
        print(f"  ✅ 쿠팡 링크: {raw_coupang_url[:70]}", flush=True)

        # STEP 2: 쿠팡 링크 → 상품명 + 이미지
        print("  [2/5] 쿠팡 상품 정보 수집 중...", flush=True)
        product_page = fetch_coupang_product_info(raw_coupang_url, driver=driver)
        product_name = product_page.get('product_name', '') or '상품'
        comment_image_url = product_page.get('image_url', '')
        print(f"    > 상품명: {product_name[:40]}", flush=True)
        if comment_image_url:
            print(f"    ✅ 쿠팡 상품 이미지 발견: {comment_image_url[:60]}...", flush=True)
        else:
            print(f"    ⚠️  쿠팡 상품 이미지 수집 실패 (상세 페이지에서 추출할 수 없음)", flush=True)

        # STEP 3: 내 파트너스 링크 생성 (새로운 Deeplink 변환/추적 로직 적용)
        print("  [3/5] 내 파트너스 링크 생성 중 (DeepLink 변환)...", flush=True)
        from coupang_api import extract_and_convert_coupang_link
        
        my_coupang_url = extract_and_convert_coupang_link(product_page.get('product_url', raw_coupang_url))
        
        if my_coupang_url:
            print(f"    > 내 파트너스 링크 (DeepLink 매칭 성공): {my_coupang_url}", flush=True)
        else:
            print("    ⚠️  딥링크 생성 실패 -> 검색 방식으로 보완 시도합니다...", flush=True)
            product_info = search_coupang_product(product_name)
            if product_info and product_info.get('product_url'):
                raw_search_url = product_info['product_url']
                # 긴 링크 압축 (is.gd 사용)
                print(f"    > 긴 링크 발견, 압축 진행 중...", flush=True)
                my_coupang_url = shorten_url_isgd(raw_search_url) or raw_search_url
                
                if not comment_image_url and product_info.get('product_image'):
                    comment_image_url = product_info['product_image']
                print(f"    > 내 파트너스 링크 (Search API 기반 + 압축): {my_coupang_url}", flush=True)
            else:
                print("    ⚠️  쿠팡 API 변환 및 검색 모두 실패 → SKIP", flush=True)
                return False

        # STEP 4: 본문+이미지 스크래핑 + 카피 최적화
        print("  [4/5] 본문 스크래핑 및 카피 최적화 중...", flush=True)
        scraped = scrape_thread_content(url, driver=driver)
        scraped_text = scraped.get('text', '')
        
        # 엑셀 본문 1순위, DOM 스크래핑 2순위
        if excel_body:
            original_text = excel_body
            print(f"  ℹ️  엑셀 '본문' 칼럼 적용 ({len(excel_body)}자)", flush=True)
        elif scraped_text:
            original_text = scraped_text
            print(f"  ℹ️  DOM 스크래핑 본문 적용 ({len(scraped_text)}자)", flush=True)
        else:
            original_text = ''
            
        post_image_urls = scraped.get('images', [])
        all_media = scraped.get('all_media', [])
        video_urls_list = scraped.get('video_urls', [])
        
        if not original_text:
            print("  ⚠️  본문 추출 및 엑셀 백업 모두 실패 → SKIP", flush=True)
            return False
        print(f"    > 본문 {len(original_text)}자 / 이미지 {len(post_image_urls)}개 / 전체 미디어 {len(all_media)}개", flush=True)

        try:
            cookies = driver.get_cookies()
        except:
            cookies = []
    finally:
        driver.quit()

    # ── 병렬 처리 (MAB 최적화 & 이미지 재호스팅) ──
    print("  [4.5/5] 마케팅 소구점 전처리 중...", flush=True)
    
    # 분석용 미디어 후보군 구성 (스레드 본문 미디어 전체 + 쿠팡 상세 이미지)
    # 이제 extractor 내부에서 threads 미디어를 우선순위로 두고 분석합니다.
    threads_media = all_media if all_media else []
    coupang_imgs = [comment_image_url] if comment_image_url else []
    
    marketing_focus = product_name
    if threads_media or coupang_imgs:
        # extract_marketing_focus 내부에서 '본문 사진'과 '본문 텍스트'의 관계를 메인으로 분석합니다.
        extracted = extract_marketing_focus(client, "gemini-3-flash-preview", product_name, original_text, threads_media, coupang_imgs)
        if isinstance(extracted, dict):
            marketing_focus = extracted
            print(f"    🌟 마케팅 구조화 분석 완료: {str(marketing_focus.get('marketing_insight', ''))[:40]}...", flush=True)
        elif extracted and extracted != product_name:
            marketing_focus = extracted
            print(f"    🌟 마케팅 소구점 적용 완료: {marketing_focus[:40]}...", flush=True)
    
    print("  [5/5] 이미지 호스팅 및 카피 최적화 병렬 처리 중... (수십 초 대기)", flush=True)
    affiliate_comment = build_affiliate_comment(product_name, my_coupang_url)
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        # product_name 대신 marketing_focus를 인자로 전달합니다!
        future_copy = executor.submit(run_optimization, original_text, marketing_focus)
        future_main_imgs = executor.submit(fetch_and_rehost, all_media, None, video_urls_list, cookies) if all_media else None
        future_comment_img = executor.submit(fetch_and_rehost, [comment_image_url], None, None, None) if comment_image_url else None
        
        # 결과 수집
        try:
            top_3 = future_copy.result()
            if top_3:
                optimized_copy = top_3[0]['copy']
                print(f"    > 🏆 1위 최적화 카피 채택: {optimized_copy[:50].replace(chr(10), ' ')}...", flush=True)
            else:
                raise ValueError("최적화된 카피가 없습니다.")
        except Exception as e:
            print(f"  ❌ 카피 최적화 실패: {e} → 원본 사용", flush=True)
            optimized_copy = original_text

        public_images = future_main_imgs.result() if future_main_imgs else []
        reply_image_hosted = future_comment_img.result() if future_comment_img else []
        reply_image_public_url = reply_image_hosted[0] if reply_image_hosted else None
        
        if reply_image_public_url:
            print(f"    > 🎉 댓글 이미지 재호스팅 성공: {reply_image_public_url}", flush=True)
        elif comment_image_url:
            print(f"    > ❌ 댓글 이미지 재호스팅 실패 (수집은 되었으나 업로드 오류)", flush=True)
        else:
            print(f"    > ℹ️  댓글 이미지 없음 (수집 단계에서 누락됨)", flush=True)

    print("  [업로드 준비] 완료, 쓰레드에 게시합니다...", flush=True)

    if dry_run:
        print("\n  ━━━━━━━━━━ [DRY-RUN] ━━━━━━━━━━")
        print(f"📝 최적화 카피:\n{optimized_copy}\n")
        print(f"💬 파트너스 댓글:\n{affiliate_comment}\n")
        print(f"🖼️ 댓글 이미지: {reply_image_public_url if reply_image_public_url else '없음'}\n")
        return True

    try:
        ok = upload_to_threads(
            threads_user_id, threads_token,
            optimized_copy, public_images,
            reply_text=affiliate_comment,
            reply_image_url=reply_image_public_url
        )
        if ok:
            print("  🎉 업로드 완료!", flush=True)
            return True
        else:
            print("  ❌ 업로드 실패", flush=True)
            return False
    except Exception as e:
        print(f"  ❌ 업로드 오류: {e}", flush=True)
        return False


# ────────────────────────────────────────────────────────────────
# 메인 파이프라인
# ────────────────────────────────────────────────────────────────
def main(dry_run: bool = False, limit: int = None, skip_api_prompt: bool = False):
    print("=" * 65)
    print("🤖 Threads 자동화 파이프라인 v4.0")
    print(f"   📂 입력 폴더: {REF_DIR}")
    print(f"   📁 완료 폴더: {DONE_DIR}")
    print("=" * 65)

    # API 키 입력
    if not skip_api_prompt:
        print("\n🔑 API 키 확인 (이미 설정된 항목은 Enter로 건너뜁니다):")
        prompt_api_keys()

    # 환경변수 체크
    threads_user_id = os.getenv("THREADS_USER_ID")
    threads_token   = os.getenv("THREADS_ACCESS_TOKEN")
    if not dry_run and (not threads_user_id or not threads_token):
        print("❌ THREADS_USER_ID / THREADS_ACCESS_TOKEN 미설정")
        return

    # 자동화참조 폴더의 엑셀 파일 목록
    os.makedirs(REF_DIR, exist_ok=True)
    all_files = glob.glob(os.path.join(REF_DIR, "*.xlsx")) + \
                glob.glob(os.path.join(REF_DIR, "*.xls"))
    excel_files = [f for f in all_files if "~$" not in os.path.basename(f)]

    if not excel_files:
        print(f"⚠️ '{REF_DIR}' 폴더에 엑셀 파일이 없습니다.")
        print("   처리할 엑셀 파일(.xlsx)을 자동화참조 폴더에 넣어주세요.")
        return

    # 처리 이력 로드
    processed_links = load_processed_links()
    
    # 기존 중단 신호 제거
    if check_stop_signal():
        os.remove(STOP_SIGNAL_FILE)

    # Gemini 클라이언트 초기화
    client = get_gemini_client()

    total_success = 0
    total_skip    = 0
    total_already = 0

    for excel_path in excel_files:
        excel_name = os.path.basename(excel_path)
        print(f"\n{'═'*65}")
        print(f"📄 처리 중: {excel_name}")
        print(f"{'═'*65}")

        # 링크 추출
        try:
            links = collect_links_from_excel(excel_path)
        except Exception as e:
            print(f"❌ 엑셀 읽기 실패: {e}")
            continue

        if limit:
            links = links[:limit]

        print(f"▶️  {len(links)}개 링크 처리 예정 (완료된 링크 자동 스킵)", flush=True)

        file_success = 0
        file_already = 0
        file_fail    = 0

        for i, item in enumerate(links):
            # 1. 중단 신호 확인
            if check_stop_signal():
                print(f"\n🛑 [STOP] 중단 신호(stop.txt) 감지. 프로그램을 안전하게 종료합니다.", flush=True)
                os.remove(STOP_SIGNAL_FILE)
                return

            url = item['url']
            
            # 2. 중복 처리 확인
            if url in processed_links:
                print(f"\n{'─'*65}")
                print(f"[{i+1}/{len(links)}] {url} -> ⏭️  이미 처리됨 (Skip)", flush=True)
                file_already += 1
                total_already += 1
                continue

            print(f"\n{'─'*65}")
            print(f"[{i+1}/{len(links)}] {url}", flush=True)

            ok = process_single_link(item, client, 
                                     threads_user_id, threads_token, dry_run)
            if ok:
                file_success += 1
                total_success += 1
                log_processed_link(url) # 완료 기록
            else:
                file_fail += 1
                total_skip += 1

            if not dry_run and ok:
                print("  ⏳ 15초 대기...", flush=True)
                time.sleep(15)

        print(f"\n📊 [{excel_name}] 완료: 성공 {file_success} / 중복스킵 {file_already} / 실패 {file_fail}")

        # 엑셀 파일 업로드완료 폴더로 이동 (dry_run이 아닐 때만)
        # 모든 링크가 (성공 + 이미완료) 처리되었을 때만 이동
        if not dry_run and (file_success + file_already) == len(links):
            move_to_done(excel_path)
        elif dry_run:
            print("  ℹ️ [DRY-RUN] 파일 이동 생략")

    print(f"\n{'='*65}")
    print(f"🏁 전체 완료! 성공: {total_success} / 스킵(중복): {total_already} / 실패: {total_skip}")
    print(f"{'='*65}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Threads 자동 포스팅 파이프라인 v4")
    parser.add_argument('--dry-run',        action='store_true', help='업로드 없이 결과만 출력')
    parser.add_argument('--limit',          type=int, default=None, help='파일당 처리할 링크 수 제한')
    parser.add_argument('--skip-api-prompt', action='store_true', help='API 키 대화형 입력 생략 (.env만 사용)')
    args = parser.parse_args()
    main(dry_run=args.dry_run, limit=args.limit, skip_api_prompt=args.skip_api_prompt)
