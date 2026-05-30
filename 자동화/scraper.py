import time
import random
import re
import json
import base64
import tempfile
import os
import io
import urllib.parse
import requests
import sys
from pathlib import Path
from PIL import Image
from concurrent.futures import ThreadPoolExecutor
from seleniumbase import Driver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent

# ── 드라이버 컨텍스트 매니저 (배치 공유 대응) ────────────────────────
class DriverContext:
    def __init__(self, driver=None):
        self.own = driver is None
        self.driver = driver or init_driver()
    def __enter__(self): return self.driver
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.own:
            try: self.driver.quit()
            except: pass

def init_driver():
    """UC 모드 최적화: UA 강제 주입보다 UC 기본 엔진을 신뢰함(Akamai 대응)"""
    try:
        # 2026-04-08: UC 모드만으로 아카마이 챌린지 해결 가능 확인
        driver = Driver(uc=True, headless=False, browser="chrome", page_load_strategy="eager")
        driver.set_page_load_timeout(35)
        return driver
    except Exception as e:
        print(f"    ⚠️ [SB] 초기화 실패: {e}. 기본 모드 시도...", flush=True)
        return Driver(headless=False, page_load_strategy="eager")

# ──Threads 스크래핑 로직 ──────────────────────────────────────────

def dismiss_thread_popup(driver):
    """방해되는 로그인/가입 팝업을 Close 버튼과 ESC 키로 모두 시도하여 닫습니다."""
    try:
        from selenium.webdriver.common.keys import Keys
        # 1. ESC 키 입력 (팝업 다이얼로그 원천 차단 - 가장 효과적)
        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.5)
        
        # 2. Close/닫기 버튼 탐색 후 클릭
        close_btns = driver.find_elements(By.CSS_SELECTOR, 
            'svg[aria-label="Close"], svg[aria-label="닫기"], div[role="button"][aria-label="Close"]')
        for btn in close_btns:
            if btn.is_displayed():
                try: driver.execute_script("arguments[0].click();", btn); time.sleep(0.3)
                except: pass
    except: pass


def open_threads_page(driver, url, wait_seconds=5):
    try:
        driver.get(url)
    except TimeoutException:
        print("    ⚠️ [Threads 로드 지연] renderer timeout. 로드된 DOM 기준으로 수집을 계속합니다.", flush=True)
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass
    time.sleep(wait_seconds)
    try:
        page_text = driver.execute_script("return document.body ? document.body.innerText : ''") or ""
        if "HTTP ERROR 429" in page_text or "페이지가 작동하지 않습니다" in page_text:
            print("    ⚠️ [Threads 429] 새로고침 1회 후 DOM 수집을 재시도합니다.", flush=True)
            driver.refresh()
            time.sleep(wait_seconds)
    except Exception:
        pass


def _unescape_json_url_text(value):
    text = str(value or "")
    text = (
        text.replace("\\/", "/")
        .replace("\\u0026", "&")
        .replace("\\u003d", "=")
        .replace("\\u003D", "=")
        .replace("\\u003f", "?")
        .replace("\\u003F", "?")
        .replace("\\u2026", "…")
    )
    text = re.sub(r"\\u0025", "%", text, flags=re.IGNORECASE)
    for _ in range(2):
        decoded = urllib.parse.unquote(text)
        if decoded == text:
            break
        text = decoded
    return text


def _normalize_coupang_url(raw_url):
    if not raw_url:
        return ""
    raw_value = _unescape_json_url_text(raw_url).strip().strip("()[]{}<>\"'")
    if ("…" in raw_value or "..." in raw_value) and "l.threads.com" not in raw_value:
        return ""
    if "l.threads.com" in raw_value:
        raw_value = raw_value.replace("&amp;", "&")
        q = urllib.parse.parse_qs(urllib.parse.urlparse(raw_value).query)
        value = _unescape_json_url_text(q.get("u", [""])[0])
    else:
        value = _unescape_json_url_text(raw_value)
    match = re.search(r"(?:https?://)?link\.coupang\.com/a/[A-Za-z0-9]+", value)
    if not match:
        match = re.search(r"(?:https?://)?(?:www\.)?coupang\.com/[^\s\"'<>]+", value)
    if not match:
        return ""
    url = match.group(0).strip().strip("()[]{}<>\"'")
    if "…" in url or "..." in url:
        return ""
    if url.startswith("www.coupang.com") or url.startswith("link.coupang.com") or url.startswith("coupang.com"):
        url = "https://" + url
    return url if "coupang.com" in url else ""


def _unique_coupang_urls_from_values(values):
    urls = []
    for value in values or []:
        candidate = _normalize_coupang_url(value)
        if candidate:
            urls.append(candidate)
    return list(dict.fromkeys(urls))


def _extract_coupang_urls_from_current_page(driver):
    def unescape_json_url_text(value):
        text = str(value or "")
        text = (
            text.replace("\\/", "/")
            .replace("\\u0026", "&")
            .replace("\\u003d", "=")
            .replace("\\u003D", "=")
            .replace("\\u003f", "?")
            .replace("\\u003F", "?")
            .replace("\\u2026", "…")
        )
        text = re.sub(r"\\u0025", "%", text, flags=re.IGNORECASE)
        for _ in range(2):
            decoded = urllib.parse.unquote(text)
            if decoded == text:
                break
            text = decoded
        return text

    def normalize(raw_url):
        if not raw_url:
            return ""
        raw_value = unescape_json_url_text(raw_url).strip().strip("()[]{}<>\"'")
        if ("…" in raw_value or "..." in raw_value) and "l.threads.com" not in raw_value:
            return ""
        if "l.threads.com" in raw_value:
            raw_value = raw_value.replace("&amp;", "&")
            q = urllib.parse.parse_qs(urllib.parse.urlparse(raw_value).query)
            value = unescape_json_url_text(q.get("u", [""])[0])
        else:
            value = unescape_json_url_text(raw_value)
        match = re.search(r"(?:https?://)?link\.coupang\.com/a/[A-Za-z0-9]+", value)
        if not match:
            match = re.search(r"(?:https?://)?(?:www\.)?coupang\.com/[^\s\"'<>]+", value)
        if not match:
            return ""
        url = match.group(0).strip().strip("()[]{}<>\"'")
        if "…" in url or "..." in url:
            return ""
        if url.startswith("www.coupang.com") or url.startswith("link.coupang.com") or url.startswith("coupang.com"):
            url = "https://" + url
        return url if "coupang.com" in url else ""

    def extract_once():
        urls = []
        try:
            anchors = driver.execute_script(
                """
                return Array.from(document.querySelectorAll('a')).map(a => ({
                    href: a.href || '',
                    text: a.innerText || a.textContent || '',
                    aria: a.getAttribute('aria-label') || ''
                }));
                """
            ) or []
            for anchor in anchors:
                for value in (anchor.get("href"), anchor.get("text"), anchor.get("aria")):
                    candidate = normalize(value)
                    if candidate:
                        urls.append(candidate)

            body_text = driver.execute_script("return document.body ? document.body.innerText : ''") or ""
            pattern = re.compile(r"(?:https?://)?(?:link\.coupang\.com|www\.coupang\.com|coupang\.com)/[^\s\"'<>]+")
            for match in pattern.findall(body_text):
                candidate = normalize(match)
                if candidate:
                    urls.append(candidate)

            page_source = unescape_json_url_text((driver.page_source or "").replace("&amp;", "&"))
            for wrapped in re.findall(r"https://l\.threads\.com/\?u=[^\s\"'<>]+", page_source):
                candidate = normalize(wrapped)
                if candidate:
                    urls.append(candidate)
            decoded_source = unescape_json_url_text(page_source)
            for match in pattern.findall(decoded_source):
                candidate = normalize(match)
                if candidate:
                    urls.append(candidate)
        except Exception:
            return []
        return list(dict.fromkeys(urls))

    deadline = time.time() + 14
    while True:
        coupang_urls = extract_once()
        if coupang_urls or time.time() >= deadline:
            return coupang_urls
        time.sleep(0.5)


def _extract_coupang_urls_from_first_reply_card(driver, target_url=None):
    try:
        result = driver.execute_script(
            """
            return (function(target) {
                function uniq(values) {
                    return Array.from(new Set((values || []).filter(Boolean)));
                }
                function normalizeHref(value) {
                    return (value || '').split('?')[0].replace('threads.net', 'threads.com').replace(/\\/$/, '');
                }
                function extractPostId(value) {
                    let m = normalizeHref(value).match(/\\/(?:post|t)\\/([^/?#]+)/);
                    return m ? m[1] : '';
                }
                const targetHref = normalizeHref(target || window.location.href || '');
                const currentHref = normalizeHref(window.location.href || '');
                const targetPostId = extractPostId(targetHref) || extractPostId(currentHref);
                function buildCard(container) {
                    const postLinks = uniq(
                        Array.from(container.querySelectorAll('a[href*="/post/"], a[href*="/t/"]'))
                            .map((node) => normalizeHref(node.href || node.getAttribute('href') || ''))
                            .filter(Boolean)
                    );
                    if (!postLinks.length) return null;
                    const postIds = uniq(postLinks.map(extractPostId).filter(Boolean));
                    const rect = container.getBoundingClientRect();
                    return {container, post_links: postLinks, post_ids: postIds, y: rect.y};
                }
                const cards = Array.from(document.querySelectorAll('article, div[data-pressable-container="true"]'))
                    .map(buildCard)
                    .filter(Boolean)
                    .sort((a, b) => a.y - b.y);
                let firstReply = null;
                if (targetPostId) {
                    firstReply = cards.find((card) => !card.post_ids.includes(targetPostId));
                }
                if (!firstReply) {
                    firstReply = cards.find((card) => !card.post_links.includes(targetHref) && !card.post_links.includes(currentHref));
                }
                if (!firstReply) {
                    return {values: [], target_post_id: targetPostId, first_reply_url: ''};
                }
                const scope = firstReply.container;
                const anchors = Array.from(scope.querySelectorAll('a')).map(a => ({
                    href: a.href || a.getAttribute('href') || '',
                    text: a.innerText || a.textContent || '',
                    aria: a.getAttribute('aria-label') || ''
                }));
                let values = [];
                for (let a of anchors) {
                    values.push(a.href || '', a.text || '', a.aria || '');
                }
                values.push(scope.innerText || '');
                values.push(scope.outerHTML || '');
                return {
                    values,
                    target_post_id: targetPostId,
                    first_reply_url: (firstReply.post_links || [''])[0] || '',
                    first_reply_text: (scope.innerText || '').slice(0, 240)
                };
            })(arguments[0]);
            """,
            target_url or "",
        ) or {}
        return _unique_coupang_urls_from_values(result.get("values") or [])
    except Exception:
        return []


def _extract_first_reply_url_from_current_page(driver, target_url=None):
    try:
        return driver.execute_script(
            """
            return (function(target) {
                function uniq(values) {
                    return Array.from(new Set((values || []).filter(Boolean)));
                }
                function normalizeHref(value) {
                    return (value || '').split('?')[0].replace('threads.net', 'threads.com').replace(/\\/$/, '');
                }
                function extractPostId(value) {
                    let m = normalizeHref(value).match(/\\/(?:post|t)\\/([^/?#]+)/);
                    return m ? m[1] : '';
                }
                const targetHref = normalizeHref(target || window.location.href || "");
                const currentHref = normalizeHref(window.location.href || "");
                const targetPostId = extractPostId(targetHref) || extractPostId(currentHref);
                function buildCard(container) {
                    const postLinks = uniq(
                        Array.from(container.querySelectorAll('a[href*="/post/"], a[href*="/t/"]'))
                            .map((node) => normalizeHref(node.href || node.getAttribute('href') || ''))
                            .filter(Boolean)
                    );
                    if (!postLinks.length) return null;
                    const postIds = uniq(postLinks.map(extractPostId).filter(Boolean));
                    const rect = container.getBoundingClientRect();
                    return {post_links: postLinks, post_ids: postIds, y: rect.y};
                }
                const cards = Array.from(document.querySelectorAll('article, div[data-pressable-container="true"]'))
                    .map(buildCard)
                    .filter(Boolean)
                    .sort((a, b) => a.y - b.y);
                let firstReply = null;
                if (targetPostId) {
                    firstReply = cards.find((card) => !card.post_ids.includes(targetPostId));
                }
                if (!firstReply) {
                    firstReply = cards.find((card) => !card.post_links.includes(targetHref) && !card.post_links.includes(currentHref));
                }
                return (firstReply && firstReply.post_links && firstReply.post_links[0]) || "";
            })(arguments[0]);
            """,
            target_url or "",
        ) or ""
    except Exception:
        return ""


def _extract_coupang_urls_from_thread_and_first_reply(driver, target_url=None):
    def wait_scroll(label, scroll_y):
        try:
            time.sleep(1.5)
            driver.execute_script("window.scrollBy(0, arguments[0])", scroll_y)
            time.sleep(2.5)
        except Exception:
            pass

    def collect_first_reply(label):
        urls = _extract_coupang_urls_from_first_reply_card(driver, target_url)
        if urls:
            print(f"    ✅ [Threads DOM] {label} 첫 댓글 카드에서 쿠팡 링크 {len(urls)}개 수집", flush=True)
        return urls

    def collect_visible(label):
        urls = _extract_coupang_urls_from_current_page(driver)
        if urls:
            print(f"    ✅ [Threads DOM] {label}에서 쿠팡 링크 {len(urls)}개 수집", flush=True)
        return urls

    wait_scroll("원문/첫 댓글 로드", 900)

    coupang_urls = collect_first_reply("원문/화면")
    if coupang_urls:
        return coupang_urls

    coupang_urls = collect_visible("현재 화면 폴백")
    if coupang_urls:
        return coupang_urls

    wait_scroll("추가 스크롤", 1200)

    coupang_urls = collect_first_reply("추가 스크롤")
    if coupang_urls:
        return coupang_urls

    coupang_urls = collect_visible("추가 스크롤 폴백")
    if coupang_urls:
        return coupang_urls

    first_reply_url = _extract_first_reply_url_from_current_page(driver, target_url)
    current_url = (getattr(driver, "current_url", "") or "").split("?")[0]
    if first_reply_url and first_reply_url != current_url:
        try:
            open_threads_page(driver, first_reply_url)
            dismiss_thread_popup(driver)
            wait_scroll("첫 댓글 직접 진입", 500)
            coupang_urls = collect_visible("첫 댓글 직접 진입")
            if coupang_urls:
                return coupang_urls
        except Exception:
            return []
    print("    ⚠️ [Threads DOM] 원문/첫 댓글에서 쿠팡 링크를 찾지 못했습니다.", flush=True)
    return []


def _build_media_session(driver=None, cookies: list = None):
    import requests as req

    session = req.Session()
    if not cookies and driver:
        try:
            cookies = driver.get_cookies()
        except:
            cookies = None

    if cookies:
        for c in cookies:
            session.cookies.set(c["name"], c["value"], domain=c.get("domain", ""))

    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            )
        }
    )
    return session


def _fetch_media_bytes(url, driver=None, session=None):
    raw_bytes = None
    if driver:
        try:
            js_fetch = """
            const url = arguments[0];
            const callback = arguments[arguments.length - 1];
            fetch(url).then(r => r.blob()).then(blob => {
                const reader = new FileReader();
                reader.onloadend = () => callback(reader.result.split(',')[1]);
                reader.readAsDataURL(blob);
            }).catch(e => callback("ERROR:" + e.message));
            """
            res = driver.execute_async_script(js_fetch, url)
            if res and not res.startswith("ERROR:"):
                raw_bytes = base64.b64decode(res)
        except Exception:
            raw_bytes = None

    if raw_bytes:
        return raw_bytes

    if session is None:
        session = _build_media_session(driver=driver)
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code == 200:
            return resp.content
    except Exception:
        return None
    return None


def _infer_media_extension(url: str, video_urls: list = None):
    lower = str(url).lower()
    if (video_urls and url in video_urls) or any(ext in lower for ext in [".mp4", ".mov", ".webm", ".avi", ".m4v"]):
        return ".mp4"
    if ".png" in lower:
        return ".png"
    if ".webp" in lower:
        return ".webp"
    if ".gif" in lower:
        return ".gif"
    if ".jpeg" in lower:
        return ".jpeg"
    return ".jpg"


def _normalize_tmpfiles_download_url(raw_url: str) -> str:
    if not raw_url:
        return ""

    normalized = raw_url.strip()
    if normalized.startswith("http://"):
        normalized = "https://" + normalized[len("http://"):]
    elif normalized.startswith("//"):
        normalized = "https:" + normalized
    elif not normalized.startswith("https://"):
        normalized = "https://" + normalized.lstrip("/")

    parsed = urllib.parse.urlparse(normalized)
    path = parsed.path or ""
    if not path.startswith("/dl/"):
        path = "/dl" + path

    return urllib.parse.urlunparse(
        ("https", parsed.netloc, path, parsed.params, parsed.query, parsed.fragment)
    )


def _validate_tmpfiles_media_url(url: str, expected_ext: str) -> bool:
    try:
        response = requests.get(url, timeout=20, stream=True, allow_redirects=True)
        content_type = (response.headers.get("content-type") or "").lower()
        status_ok = response.status_code == 200
        response.close()

        if not status_ok:
            return False

        if "text/html" in content_type:
            return False

        if expected_ext in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            return content_type.startswith("image/")
        if expected_ext in {".mp4", ".mov", ".webm", ".avi", ".m4v"}:
            return content_type.startswith("video/") or content_type == "application/octet-stream"
        return True
    except Exception:
        return False


def cache_media_locally(media_urls: list, target_dir, driver=None, video_urls: list = None, cookies: list = None, prefix: str = "media", max_items: int = 10) -> list:
    if not media_urls:
        return []

    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    session = _build_media_session(driver=driver, cookies=cookies)

    local_paths = []
    for i, url in enumerate(media_urls[:max_items]):
        try:
            raw_bytes = _fetch_media_bytes(url, driver=driver, session=session)
            if not raw_bytes:
                print(f"    ⚠️ [로컬캐시 {i+1}] 미디어 저장 실패", flush=True)
                continue

            ext = _infer_media_extension(url, video_urls=video_urls)
            local_path = target_dir / f"{prefix}_{i+1:02d}{ext}"
            with local_path.open("wb") as f:
                f.write(raw_bytes)
            local_paths.append(str(local_path))
        except Exception as e:
            print(f"    ⚠️ [로컬캐시 {i+1}] 저장 중 오류: {e}", flush=True)
    return local_paths

def scrape_thread_content(url, driver=None, body_only=False):
    with DriverContext(driver) as d:
        try:
            open_threads_page(d, url)
            dismiss_thread_popup(d)

            # Threads sometimes keeps the tail of long posts behind "more".
            # Expand it before measuring media/text boundaries.
            try:
                d.execute_script(
                    """
                    Array.from(document.querySelectorAll('div[role="button"], span')).forEach((el) => {
                        const text = ((el.innerText || el.textContent || '') + '').trim();
                        if (text === '더 보기' || text === 'See more') {
                            const button = el.closest('div[role="button"]') || el;
                            try { button.click(); } catch (e) {}
                        }
                    });
                    """
                )
                time.sleep(0.5)
            except Exception:
                pass

            # ── 캐러셀(Carousel) 강제 스캔 (지연 로딩 대응) ────────────────
            try:
                # 다음 버튼(Next)이 있으면 클릭하여 모든 미디어 로딩 유도
                for _ in range(10): # 최대 10장까지 탐색
                    next_btns = d.find_elements(By.CSS_SELECTOR, "div[role='button'][aria-label='Next'], div[role='button'][aria-label='다음']")
                    visible_next = [b for b in next_btns if b.is_displayed()]
                    if visible_next:
                        d.execute_script("arguments[0].click();", visible_next[0])
                        time.sleep(1.2)
                    else:
                        break
            except Exception:
                pass

            # ── JSON 메타데이터에서 비디오 추출 (DOM 유실 대비 가장 확실한 방법) ────────────────
            json_video_urls = []
            try:
                page_source = d.page_source
                import re
                found_vids = re.findall(r'"video_versions":\s*\[\s*\{\s*"type":\s*\d+,\s*"width":\s*\d+,\s*"height":\s*\d+,\s*"url":\s*"(https://[^"]+)"', page_source)
                for v_url in found_vids:
                    v_url = v_url.replace('\\u0026', '&')
                    if v_url not in json_video_urls:
                        json_video_urls.append(v_url)
                if json_video_urls:
                    print(f"    [Scraper] JSON 메타데이터에서 동영상 {len(json_video_urls)}개 포착!", flush=True)
            except Exception:
                pass

            content, image_urls, video_urls = "", [], []
            js_code = """
            function extractMainPostMedia() {
                // 1. 하트 버튼(Like)들을 수집하여 경계를 설정합니다.
                let heartBtns = Array.from(document.querySelectorAll('svg')).filter(svg => {
                    let aria = (svg.getAttribute('aria-label') || '').trim();
                    let title = (svg.querySelector('title')?.textContent || '').trim();
                    return aria === 'Like' || aria === '좋아요' || title === 'Like' || title === '좋아요';
                });
                let visibleHearts = heartBtns.filter(btn => btn.getBoundingClientRect().y > 50);
                
                let mainHeart = visibleHearts[0] || null;
                let mainHeartY = mainHeart ? mainHeart.getBoundingClientRect().y : Number.POSITIVE_INFINITY;
                
                // 본문 하트 버튼(mainHeartY)은 항상 본문 미디어보다 아래에 있습니다.
                // 따라서 종료 경계(maxY)를 첫 번째 하트 버튼 위치로 설정하면 댓글 이미지를 완벽히 차단할 수 있습니다.
                let maxY = mainHeartY;
                
                let result_items = [];
                let poster_urls = new Set();
                
                // 2. 동영상 수집 (전체 DOM에서 위치 기반 필터링)
                let videos = document.querySelectorAll('video');
                for (let vid of videos) {
                    let rect = vid.getBoundingClientRect();
                    // 네비게이션이거나 두 번째 하트보다 아래(댓글 등)면 무시
                    if (rect.y < 0 || rect.y > maxY) continue;
                    
                    let poster = vid.getAttribute('poster') || "";
                    if (poster) poster_urls.add(poster);
                    
                    let src = vid.getAttribute('src') || "";
                    if (!src) {
                        let source = vid.querySelector('source');
                        if (source) src = source.getAttribute('src') || "";
                    }
                    if (src) {
                        result_items.push({y: rect.y, x: rect.x, src: src, is_video: true});
                    }
                }
                
                // 3. 이미지 수집 (위치 & 크기 기반 시각적 필터링)
                let images = document.querySelectorAll('img');
                for (let img of images) {
                    let rect = img.getBoundingClientRect();
                    
                    // 핵심 필터 1: Y축 경계 (본문과 댓글을 시각적으로 분리. 약간의 오차 허용)
                    if (rect.y < 0 || rect.y > maxY + 50) continue;
                    
                    // 핵심 필터 2: 물리적 크기 필터 
                    // 프로필(36x36), 아이콘, 작은 썸네일 등을 원천 차단합니다. 
                    // 실제 포스팅된 마케팅 이미지/영상은 최소 150px 이상입니다.
                    if (rect.width < 150 || rect.height < 150) continue;
                    
                    let src = img.currentSrc || img.getAttribute('src') || "";
                    if (!src || (!src.includes('scontent') && !src.includes('fbcdn'))) continue; // 메타 CDN 외 이미지 제외
                    
                    // 핵심 필터 3: 동영상과 물리적 위치 '완벽히' 일치하는 썸네일만 필터링 (X,Y 동시 대조)
                    // 슬라이드(캐러셀) 게시물에서 영상 보조용 썸네일은 영상과 완전히 같은 좌표에 박혀있습니다.
                    let isVideoThumbnail = false;
                    for (let item of result_items) {
                        if (item.is_video && Math.abs(item.y - rect.y) < 5 && Math.abs(item.x - rect.x) < 5) {
                            isVideoThumbnail = true;
                            break;
                        }
                    }
                    if (isVideoThumbnail) continue;
                    
                    // 비디오 플레이어 내부 찌꺼기 이미지 방어 (aria-label 껍데기 판별)
                    let inVideoPlayer = img.closest('[aria-label*="Video"],[aria-label*="video"]') !== null;
                    if (inVideoPlayer) continue;
                    
                    result_items.push({y: rect.y, x: rect.x, src: src, is_video: false});
                }
                
                // 4. 본문 텍스트 추출
                // 이전 로직은 본문처럼 보이는 조각 하나만 골랐다. 이제는 현재 URL 카드 안에서
                // 텍스트 후보를 앵커로 잡고, 버튼/메트릭이 섞이기 직전의 본문 묶음 부모를 복원한다.
                let containerText = '';
                let firstReplyUrl = '';
                function rawPostText(value) {
                    return (value || '').trim();
                }
                function cleanPostText(value) {
                    return (value || '').replace(/\\s+/g, ' ').trim();
                }
                function numericWeight(value) {
                    let parsed = parseInt(value || '400', 10);
                    return Number.isFinite(parsed) ? parsed : 400;
                }
                function uniq(values) {
                    return Array.from(new Set((values || []).filter(Boolean)));
                }
                function isGrayColor(color) {
                    let m = String(color || '').match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                    if (!m) return false;
                    let r = parseInt(m[1], 10), g = parseInt(m[2], 10), b = parseInt(m[3], 10);
                    return Math.abs(r - g) < 4 && Math.abs(g - b) < 4 && r >= 80 && r <= 190;
                }
                function isNoiseText(text) {
                    text = cleanPostText(text);
                    if (!text) return true;
                    let exactNoise = new Set([
                        '번역하기', 'See translation', '활동 보기', '좋아요', '답글', '리포스트',
                        '공유', '공유하기', '더 보기', '팔로우', 'Follow', '관련 스레드'
                    ]);
                    if (exactNoise.has(text)) return true;
                    if (/^(?:약\\s*)?\\d+\\s*(?:초|분|시간|일|주|개월|년|h|m|d)$/i.test(text)) return true;
                    if (/^\\d{4}-\\d{2}-\\d{2}$/.test(text)) return true;
                    if (/^[\\d.,]+[만천]?(?:회)?$/.test(text)) return true;
                    if (text.includes('쿠팡파트너스')) return true;
                    if (text.includes('Threads에 로그인') || text.includes('Threads에 가입')) return true;
                    if (text.includes('Instagram으로 계속하기')) return true;
                    return false;
                }
                function normalizePostText(value) {
                    let lines = rawPostText(value).split(/\\n+/).map((line) => cleanPostText(line)).filter(Boolean);
                    let cleaned = [];
                    for (let i = 0; i < lines.length; i++) {
                        let line = lines[i];
                        if (isNoiseText(line)) continue;
                        if (/^\\d+\\s*\\/\\s*\\d+$/.test(line)) continue;
                        if (/^\\d+$/.test(line) && lines[i + 1] === '/' && /^\\d+$/.test(lines[i + 2] || '')) {
                            i += 2;
                            continue;
                        }
                        if (line === '/' && cleaned.length && /^\\d+$/.test(cleaned[cleaned.length - 1]) && /^\\d+$/.test(lines[i + 1] || '')) {
                            cleaned.pop();
                            i += 1;
                            continue;
                        }
                        cleaned.push(line);
                    }
                    return cleaned.join('\\n').replace(/\\n{3,}/g, '\\n\\n').trim();
                }
                function normalizeHref(value) {
                    return (value || '').split('?')[0].replace('threads.net', 'threads.com').replace(/\\/$/, '');
                }
                function extractPostId(value) {
                    let m = normalizeHref(value).match(/\\/(?:post|t)\\/([^/?#]+)/);
                    return m ? m[1] : '';
                }
                function buildCard(container) {
                    const postLinks = uniq(
                        Array.from(container.querySelectorAll('a[href*="/post/"], a[href*="/t/"]'))
                            .map((node) => normalizeHref(node.href || node.getAttribute('href') || ''))
                            .filter(Boolean)
                    );
                    if (!postLinks.length) return null;
                    const postIds = new Set(postLinks.map(extractPostId).filter(Boolean));
                    const handleTexts = uniq(
                        Array.from(container.querySelectorAll('a[href*="/@"]'))
                            .map((node) => cleanPostText(node.innerText || node.textContent || ''))
                            .filter(Boolean)
                    );
                    return {container, post_links: postLinks, post_ids: postIds, handle_set: new Set(handleTexts)};
                }
                function collectTextCandidates(scope, handleSet, maxTextY) {
                    let candidates = [];
                    let dirAutos = Array.from(scope.querySelectorAll('[dir="auto"]'));
                    for (let tn of dirAutos) {
                        let raw = rawPostText(tn.innerText || tn.textContent || '');
                        let text = normalizePostText(raw);
                        let inline = cleanPostText(text);
                        let rect = tn.getBoundingClientRect();
                        let style = window.getComputedStyle(tn);
                        let fontSize = parseFloat(style.fontSize || '0');
                        let fontWeight = numericWeight(style.fontWeight);
                        let inTime = tn.closest('time') !== null;
                        let inProfileLink = tn.closest('a[href*="/@"]') !== null;

                        if (!inline || isNoiseText(inline)) continue;
                        if (handleSet && handleSet.has(inline)) continue;
                        if (inTime || inProfileLink) continue;
                        if (fontSize < 12 || fontSize > 20) continue;
                        if (fontWeight >= 700) continue;
                        if (isGrayColor(style.color) && /^[\\d.,]+[만천]?(?:회)?$/.test(inline)) continue;
                        if (rect.y < 40 || rect.y > maxTextY - 8) continue;
                        if (rect.width < 20 || rect.height < 8) continue;

                        let score = inline.length;
                        if (/[가-힣A-Za-z]{3,}/.test(inline)) score += 10;
                        if (text.includes('\\n')) score += 25;
                        candidates.push({node: tn, raw, text, inline, score, y: rect.y, x: rect.x});
                    }
                    candidates.sort((a, b) => (b.score - a.score) || (a.y - b.y) || (a.x - b.x));
                    return candidates;
                }
                function selectTextCluster(candidate, scopeRoot, maxTextY) {
                    let best = candidate.text;
                    let bestChars = best.length;
                    let node = candidate.node;
                    for (let depth = 0; node && depth < 10; depth++, node = node.parentElement) {
                        let rect = node.getBoundingClientRect();
                        if (rect.y < 40 || rect.y > maxTextY - 8) continue;
                        let buttonCount = node.querySelectorAll('[role="button"],button').length;
                        if (buttonCount > 0) continue;
                        let text = normalizePostText(node.innerText || node.textContent || '');
                        let inline = cleanPostText(text);
                        if (!inline || !inline.includes(candidate.inline.slice(0, Math.min(20, candidate.inline.length)))) continue;
                        if (inline.length >= bestChars) {
                            best = text;
                            bestChars = inline.length;
                        }
                        if (node === scopeRoot) break;
                    }
                    return best;
                }
                function joinTextCandidates(candidates) {
                    let sorted = candidates.slice().sort((a, b) => (a.y - b.y) || (a.x - b.x));
                    let out = [];
                    let seen = new Set();
                    for (let cand of sorted) {
                        let text = normalizePostText(cand.text);
                        let inline = cleanPostText(text);
                        if (!inline || seen.has(inline)) continue;
                        if (out.some((prev) => cleanPostText(prev).includes(inline))) continue;
                        out = out.filter((prev) => !inline.includes(cleanPostText(prev)));
                        out.push(text);
                        seen.add(inline);
                    }
                    return normalizePostText(out.join('\\n'));
                }
                function extractStructuredPostText(scope, handleSet, maxTextY) {
                    let candidates = collectTextCandidates(scope, handleSet, maxTextY);
                    if (!candidates.length) return '';
                    let cluster = selectTextCluster(candidates[0], scope, maxTextY);
                    let joined = joinTextCandidates(candidates);
                    let clusterInline = cleanPostText(cluster);
                    let joinedInline = cleanPostText(joined);
                    if (joinedInline.length > clusterInline.length && !joinedInline.includes(clusterInline)) {
                        return joined;
                    }
                    return cluster || joined;
                }

                const targetHref = normalizeHref(arguments[0] || window.location.href || '');
                const targetPostId = extractPostId(targetHref);
                const cards = Array.from(document.querySelectorAll('article, div[data-pressable-container="true"]'))
                    .map(buildCard)
                    .filter(Boolean);
                const currentCard = cards.find((card) => card.post_links.includes(targetHref) || (targetPostId && card.post_ids.has(targetPostId)));
                if (!currentCard && targetPostId) {
                    return {
                        items: [],
                        text: '',
                        first_reply_url: '',
                        poster_urls: Array.from(poster_urls),
                        target_found: false,
                        target_post_id: targetPostId,
                        current_url: window.location.href || ''
                    };
                }
                firstReplyUrl = ((cards.find((card) => !targetPostId || !card.post_ids.has(targetPostId)) || {}).post_links || [''])[0] || '';

                if (currentCard) {
                    let cardRect = currentCard.container.getBoundingClientRect();
                    result_items = result_items.filter((item) => {
                        let y = item.y || 0;
                        return y >= cardRect.y - 10 && y <= cardRect.bottom + 10;
                    });
                    let scopeHeart = Array.from(currentCard.container.querySelectorAll('svg')).filter(svg => {
                        let aria = (svg.getAttribute('aria-label') || '').trim();
                        let title = (svg.querySelector('title')?.textContent || '').trim();
                        return aria === 'Like' || aria === '좋아요' || title === 'Like' || title === '좋아요';
                    }).filter(svg => svg.getBoundingClientRect().y > 40)[0];
                    let scopeMaxY = scopeHeart ? scopeHeart.getBoundingClientRect().y : cardRect.bottom;
                    containerText = extractStructuredPostText(currentCard.container, currentCard.handle_set, scopeMaxY);
                }

                if (!containerText && !targetPostId) {
                    containerText = extractStructuredPostText(document, new Set(), Number.isFinite(mainHeartY) ? mainHeartY : window.innerHeight);
                }

                let pageNumRegex = /\\s*\\d+\\s*\\/\\s*\\d+\\s*$/g;
                containerText = normalizePostText(containerText.replace(/^\\d{4}-\\d{2}-\\d{2}\\s+/, '').replace(pageNumRegex, ''));
                
                return {
                    items: result_items,
                    text: containerText,
                    first_reply_url: firstReplyUrl,
                    poster_urls: Array.from(poster_urls),
                    target_found: Boolean(currentCard),
                    target_post_id: targetPostId,
                    current_url: window.location.href || ''
                };
            }
            return extractMainPostMedia();
            """
            ordered_media = []
            res = d.execute_script(js_code, url)
            if res and res.get("target_found") is False:
                print(f"    ⚠️ [스크래핑] 목표 post 카드를 찾지 못함: {url} (현재: {res.get('current_url', '')})", flush=True)
                return {
                    "url": url,
                    "text": "",
                    "first_reply_url": "",
                    "images": [],
                    "video_urls": [],
                    "all_media": [],
                    "coupang_urls": [],
                    "target_found": False,
                    "target_post_id": res.get("target_post_id", ""),
                    "current_url": res.get("current_url", ""),
                    "error": "target_post_not_found",
                }
            if res and "error" in res:
                print(f"    ⚠️ [스크래핑] JS 에러: {res['error']}", flush=True)
            if res and "items" in res:
                content = res.get("text", "")
                first_reply_url = res.get("first_reply_url", "")
                poster_urls = set(res.get("poster_urls", []) or [])
                pending_json_videos = list(json_video_urls)
                ordered_media = []
                sorted_items = sorted(
                    res["items"],
                    key=lambda x: (round((x.get("y", 0) or 0) / 25), x.get("x", 0) or 0, x.get("y", 0) or 0),
                )
                seen = set()
                for it in sorted_items:
                    src = it.get("src", "")
                    is_video = bool(it.get("is_video"))
                    if (not is_video) and src in poster_urls and pending_json_videos:
                        src = pending_json_videos.pop(0)
                        is_video = True
                    if src and src not in seen:
                        seen.add(src)
                        ordered_media.append(src)
                        if is_video:
                            video_urls.append(src)
                        else:
                            image_urls.append(src)
                
                # JSON에서 찾은 비디오가 DOM에서 누락되었을 경우 보완
                for j_vid in pending_json_videos:
                    if j_vid not in seen:
                        seen.add(j_vid)
                        ordered_media.append(j_vid)
                        video_urls.append(j_vid)

            coupang_urls = []
            if not body_only:
                try:
                    coupang_urls = _extract_coupang_urls_from_thread_and_first_reply(d, url)
                except Exception:
                    pass

            return {
                "url": url,
                "text": content,
                "first_reply_url": first_reply_url if 'first_reply_url' in locals() else "",
                "images": image_urls,
                "video_urls": video_urls,
                "all_media": ordered_media,
                "coupang_urls": coupang_urls,
                "target_found": res.get("target_found") if isinstance(res, dict) else None,
                "target_post_id": res.get("target_post_id", "") if isinstance(res, dict) else "",
                "current_url": res.get("current_url", "") if isinstance(res, dict) else "",
            }
        except Exception as e:
            print(f"    ⚠️ [스크래핑 실패] {url}: {e}", flush=True)
            return {"url": url, "text": "", "images": [], "video_urls": [], "all_media": [], "coupang_urls": []}


def scrape_comment_for_coupang(url, driver=None):
    with DriverContext(driver) as d:
        try:
            open_threads_page(d, url)
            dismiss_thread_popup(d)
            coupang_urls = _extract_coupang_urls_from_thread_and_first_reply(d, url)
            return {"comment_text": "", "coupang_urls": coupang_urls} if coupang_urls else None
        except: return None

# ── 쿠팡 상품 수집 로직 ──────────────────────────────────────────

def fetch_coupang_product_info(coupang_url: str, driver=None) -> dict:
    product_name, image_url, is_blocked = "", "", False
    with DriverContext(driver) as d:
        try:
            # [사용자 도메인 지식: 쿠키 예열 (Warming)] 
            # 배치 내내 드라이버를 공유하며, 메인 페이지를 거쳐 봇 우회 쿠키를 누적합니다.
            if "coupang.com" not in d.current_url:
                print("    🔥 [쿠키 예열] 쿠팡 메인 접속...", flush=True)
                d.get("https://www.coupang.com/"); time.sleep(2)
            
            if "/vp/products/" in coupang_url: d.get(coupang_url)
            else:
                try: d.uc_open_with_reconnect(coupang_url, reconnect_time=3)
                except: d.get(coupang_url)
            
            import random
            time.sleep(random.uniform(4, 6))

            if "Access Denied" in d.title or "Access Denied" in d.page_source:
                is_blocked = True
                print("    ⚠️ [쿠팡] Access Denied! (Akamai에 의해 명시적으로 차단됨)", flush=True)
            else:
                # [완성] 3단계 다중 셀렉터 전략
                # 1. 상품명 (H1 -> Category List 1st -> OG -> Title)
                product_name = d.execute_script("""
                    // A. 상품 상세 페이지 타이틀
                    let name = document.querySelector('h1.prod-buy-header__title, .prod-buy-header__title, .prod-buy-header__info h2')?.innerText;
                    if (name) return name;
                    
                    // B. 카테고리/검색 리스트 1등 상품 (사용자 요청: 선택지 많은 창 대응)
                    let firstItem = document.querySelector('dl.baby-product, .search-product, .product-list li');
                    if (firstItem) {
                        let firstName = firstItem.querySelector('.name, .title, img')?.alt || firstItem.querySelector('.name')?.innerText;
                        if (firstName) return firstName;
                    }

                    return document.querySelector('meta[property="og:title"]')?.content || document.title;
                """)
                
                # 상품명 정제
                if product_name:
                    for sep in [" : ", " | ", " - 쿠팡"]:
                        if sep in product_name: product_name = product_name.split(sep)[0]
                    product_name = product_name.strip()

                # 2. 이미지 (Main Image -> Category List 1st -> OG -> Largest Image)
                image_url = d.execute_script("""
                    // A. 상세 페이지 메인 이미지
                    let main = document.querySelector('#main-image, .prod-image__detail, .prod-main-image img')?.src;
                    if (main && !main.includes('fb_like') && !main.includes('empty')) return main;
                    
                    // B. 카테고리 리스트 1등 이미지
                    let firstItem = document.querySelector('dl.baby-product, .search-product, .product-list li');
                    if (firstItem) {
                        let firstImg = firstItem.querySelector('img.baby-product-img, .image img, img')?.src;
                        if (firstImg) return firstImg;
                    }

                    let og = document.querySelector('meta[property="og:image"]')?.content;
                    if (og && !og.includes('fb_like')) return og;
                    
                    // 폴백: 페이지 내 가장 큰 이미지 탐색
                    let imgs = Array.from(document.querySelectorAll('img')).filter(i => i.width > 200);
                    if (imgs.length > 0) return imgs.sort((a,b) => (b.width * b.height) - (a.width * a.height))[0].src;
                    return null;
                """)
                
                if image_url and image_url.startswith("//"):
                    image_url = "https:" + image_url

        except Exception as e: 
            print(f"    ⚠️ [쿠팡] 수집 에러: {e}", flush=True)
            
        furl = d.current_url
    return {"product_name": product_name, "image_url": image_url, "product_url": furl, "is_blocked": is_blocked}

def fetch_and_rehost(image_urls: list, driver=None, video_urls: list = None, cookies: list = None) -> list:
    session = _build_media_session(driver=driver, cookies=cookies)
    
    public_urls = []
    if driver:
        driver.set_script_timeout(30) # 🚀 캡처 타임아웃 방지
        
    for i, url in enumerate(image_urls[:10]):
        try:
            raw_bytes = _fetch_media_bytes(url, driver=driver, session=session)

            if not raw_bytes:
                print(f"    ⚠️ [재호스팅 {i+1}] 미디어 데이터 획득 실패", flush=True)
                continue

            print(f"    📦 [재호스팅 {i+1}] 데이터 획득 성공 (상태: {len(raw_bytes)} bytes)", flush=True)

            # [개선] 파일 확장자 및 타입 결정 (URL 기반)
            ext = _infer_media_extension(url, video_urls=video_urls)
            
            tmp_dir = Path(os.getenv("MADOYO_MEDIA_TMP_DIR", BASE_DIR / "tmp" / "madoyo_temp"))
            tmp_dir.mkdir(parents=True, exist_ok=True)

            with tempfile.NamedTemporaryFile(delete=False, suffix=ext, dir=str(tmp_dir)) as tmp:
                tmp.write(raw_bytes); tpath = tmp.name
                tmp.flush() # 물리적 저장 보장

            try:
                    # [방법 1] tmpfiles.org (검증된 단일 엔진으로 최적화)
                    import requests as req_pure
                    with open(tpath, 'rb') as f:
                        up = req_pure.post("https://tmpfiles.org/api/v1/upload", 
                                          files={"file": f}, 
                                          timeout=30)
                        if up.status_code == 200:
                            res_json = up.json()
                            if res_json.get("status") == "success":
                                raw_public_url = res_json["data"]["url"]
                                dl_url = _normalize_tmpfiles_download_url(raw_public_url)
                                if _validate_tmpfiles_media_url(dl_url, ext):
                                    public_urls.append(dl_url)
                                    print(f"    ✅ [재호스팅 {i+1}] Tmpfiles 성공: {dl_url}")
                                    continue
                                print(
                                    f"    ⚠️ [재호스팅 {i+1}] Tmpfiles 업로드는 성공했지만 직접 미디어 URL 검증에 실패했습니다: {dl_url}",
                                    flush=True,
                                )
                        else:
                            print(f"    ⚠️ [재호스팅 {i+1}] Tmpfiles 실패 ({up.status_code})", flush=True)
                    
                    with open(tpath, 'rb') as f:
                        uguu = req_pure.post(
                            "https://uguu.se/upload.php",
                            files={"files[]": (os.path.basename(tpath), f)},
                            timeout=60,
                        )
                        if uguu.status_code == 200:
                            uguu_json = uguu.json()
                            uguu_files = uguu_json.get("files") or []
                            uguu_url = uguu_files[0].get("url", "") if uguu_files else ""
                            if uguu_url and _validate_tmpfiles_media_url(uguu_url, ext):
                                public_urls.append(uguu_url)
                                print(f"    ✅ [재호스팅 {i+1}] Uguu 대체 성공: {uguu_url}", flush=True)
                                continue
                            print(
                                f"    ⚠️ [재호스팅 {i+1}] Uguu 업로드는 응답했지만 직접 미디어 URL 검증에 실패했습니다: {uguu_url}",
                                flush=True,
                            )
                        else:
                            print(f"    ⚠️ [재호스팅 {i+1}] Uguu 실패 ({uguu.status_code})", flush=True)

                    print(f"    ❌ [재호스팅 {i+1}] 모든 호스팅 서버 업로드 실패", flush=True)

            finally:
                if os.path.exists(tpath): os.remove(tpath)
        except Exception as e: print(f"    ⚠️ [재호스팅 {i+1}] 치명적 오류: {e}", flush=True)
    return public_urls
