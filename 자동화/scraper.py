import time
import random
from seleniumbase import Driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
import json

def check_is_profile_link(el):
    """ 요소가 프로필 관련 링크(아이디, 사진)인지 판별 """
    try:
        el.find_element(By.XPATH, "./ancestor::a")
        return True
    except:
        return False

def init_driver():
    # SeleniumBase UC 모드 사용 (Akamai 차단 우회에 매우 효과적)
    try:
        driver = Driver(uc=True, headless=False, browser="chrome")
        return driver
    except Exception as e:
        print(f"    ⚠️ [SB] 드라이버 초기화 실패: {e}. 기본 드라이버 시도...", flush=True)
        driver = Driver(headless=False)
        return driver

def fetch_and_rehost(image_urls: list, driver=None, video_urls: list = None, cookies: list = None) -> list:

    """
    Selenium 브라우저의 쿠키를 추출하여 Python requests로 scontent 이미지를 다운로드한 후
    catbox.moe에 업로드하여 공개 URL을 반환합니다.
    """
    import requests as req
    import tempfile
    import os

    session = req.Session()
    try:
        if not cookies and driver:
            cookies = driver.get_cookies()
        if cookies:
            for c in cookies:
                session.cookies.set(c['name'], c['value'], domain=c.get('domain', ''))
    except Exception as e:
        print(f"    ⚠️ 쿠키 설정 실패: {e}", flush=True)

    # Threads 브라우저와 동일한 User-Agent 사용
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    # 기본 헤더 설정 (Referer는 URL에 따라 동적 변경)
    session.headers.update({
        "User-Agent": ua,
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    })

    public_urls = []

    for i, url in enumerate(image_urls[:10]):
        try:
            # 쿠팡 CDN 이미지인 경우 Referer를 쿠팡으로 설정 (403 방지)
            if "coupangcdn.com" in url or "coupang.com" in url:
                session.headers.update({"Referer": "https://www.coupang.com/"})
            else:
                session.headers.update({"Referer": "https://www.threads.com/"})

            print(f"    [재호스팅 {i+1}/{min(len(image_urls),10)}] 다운로드 중... ({'Coupang' if 'coupang' in url else 'Threads'})", flush=True)
            resp = session.get(url, timeout=15, stream=True)

            if resp.status_code != 200:
                print(f"    ⚠️ [{i+1}] 다운로드 실패 (HTTP {resp.status_code}) - URL: {url[:60]}...", flush=True)
                continue

            # Content-Type으로 확장자 결정
            ct = resp.headers.get("Content-Type", "")
            if "video" in ct:
                ext = '.mp4'
            elif "png" in ct:
                ext = '.png'
            elif "webp" in ct:
                ext = '.webp'
            else:
                ext = '.jpg'

            raw_bytes = resp.content
            if not raw_bytes:
                print(f"    ⚠️ [{i+1}] 빈 응답", flush=True)
                continue

            # webp → jpg 변환 (Threads API는 webp 미지원, 단 동영상은 제외)
            is_video = (video_urls and url in video_urls) or "video" in ct or ext == '.mp4'
            if not is_video and ("webp" in ct or ext == '.webp'):
                try:
                    from PIL import Image
                    import io
                    img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=90)
                    raw_bytes = buf.getvalue()
                    ext = '.jpg'
                    print(f"    [{i+1}] webp → jpg 변환 완료", flush=True)
                except Exception as conv_e:
                    print(f"    ⚠️ [{i+1}] webp 변환 실패 (건너뜀): {conv_e}", flush=True)
                    continue

            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(raw_bytes)
                tmp_path = tmp.name

            max_retries = 3
            try:
                for attempt in range(max_retries):
                    try:
                        if attempt > 0:
                            print(f"    [{i+1}] tmpfiles 재시도 {attempt}/{max_retries-1}...", flush=True)
                            time.sleep(2)
                        else:
                            print(f"    [{i+1}] tmpfiles 업로드 중 ({len(raw_bytes)//1024}KB)...", flush=True)
                            
                        with open(tmp_path, 'rb') as f:
                            # catbox DNS 차단 및 uguu 불안정 대응: tmpfiles.org 사용
                            resp = req.post(
                                "https://tmpfiles.org/api/v1/upload",
                                files={"file": f},
                                timeout=35
                            )
                        if resp.status_code == 200:
                            data = resp.json()
                            if data.get("status") == "success":
                                # tmpfiles.org/URL -> tmpfiles.org/dl/URL (다이렉트 링크 변환)
                                raw_url = data["data"]["url"]
                                public_url = raw_url.replace("http://tmpfiles.org/", "https://tmpfiles.org/dl/")
                                public_urls.append(public_url)
                                print(f"    ✅ [{i+1}] {public_url}", flush=True)
                                break
                        
                        err_text = resp.text[:80] if hasattr(resp, 'text') else 'Unknown'
                        print(f"    ⚠️ [{i+1}] tmpfiles 실패 (HTTP {resp.status_code}): {err_text}", flush=True)
                    except Exception as e:
                        print(f"    ⚠️ [{i+1}] tmpfiles 오류: {e}", flush=True)
            finally:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

        except Exception as e:
            print(f"    ⚠️ [{i+1}] 재호스팅 오류: {e}", flush=True)

    print(f"    📊 재호스팅 완료: {len(public_urls)}/{min(len(image_urls),10)}개", flush=True)
    return public_urls



def scrape_thread_content(url, driver=None):
    """
    Threads 게시물 URL에서 본문 텍스트와 본문 이미지/동영상을 추출합니다.
    
    핵심 로직:
    - '인기순' 텍스트 요소를 경계로, 그 위가 본문 / 아래가 댓글
    - 본문 영역에서만 이미지/동영상 추출
    - 동영상(mp4)은 절대 jpg 변환 없이 mp4 그대로 처리
    - '쿠팡파트너스' 포함 텍스트 블록은 댓글로 식별하여 제외
    """
    should_close = False
    if driver is None:
        try:
            print(f"    [ChromeDriver] 브라우저 초기화 시작...", flush=True)
            driver = init_driver()
            driver.set_page_load_timeout(15)
            should_close = True
            print(f"    [ChromeDriver] 브라우저 초기화 완료.", flush=True)
        except Exception as e:
            print(f"    ❌ [ChromeDriver] 브라우저를 띄울 수 없습니다. ({e})", flush=True)
            return {"url": url, "text": "", "images": [], "public_images": [], "all_media": [], "video_urls": []}

    try:
        print(f"    [Scraper] {url} 접속 중...", flush=True)
        driver.get(url)
        print(f"    [Scraper] 페이지 로딩 5초 대기...", flush=True)
        time.sleep(5)

        content = ""
        image_urls = []   # 원본 scontent URL (이미지+동영상 분리)
        video_urls = []   # 동영상만 따로 관리

        try:
            # ── 1. 본문/댓글 경계 찾기 ──────────────────────────────────────
            # 전략 A: '인기순' 요소의 Y위치 (Y>100인 경우만 유효)
            # 전략 B: '쿠팡파트너스' 텍스트 블록의 Y위치
            # 경계가 없으면 본문 이미지만 허용 (전체 사용)
            boundary_y = None
            try:
                # 전략 A: 인기순
                boundary_els = driver.find_elements(
                    By.XPATH, "//*[contains(text(),'인기순') or contains(text(),'Most relevant')]"
                )
                for el in boundary_els:
                    y = el.location.get('y', 0)
                    if y > 100:
                        boundary_y = y
                        print(f"    [Scraper] 본문/댓글 경계 Y={boundary_y} (인기순 기준)", flush=True)
                        break

                # 전략 B: 인기순 못 찾으면 쿠팡파트너스 블록 Y 사용
                if boundary_y is None:
                    cp_els = driver.find_elements(
                        By.XPATH, "//*[contains(text(),'쿠팡파트너스')]"
                    )
                    for el in cp_els:
                        y = el.location.get('y', 0)
                        if y > 100:
                            boundary_y = y
                            print(f"    [Scraper] 본문/댓글 경계 Y={boundary_y} (쿠팡파트너스 기준)", flush=True)
                            break

                if boundary_y is None:
                    print(f"    [Scraper] 경계 미발견 → 전체 이미지 허용", flush=True)
            except Exception:
                pass

            # ── 2. 본문 텍스트 추출 ─────────────────────────────────────────
            # '쿠팡파트너스'가 없는 dir=auto 텍스트 중 가장 긴 것이 본문
            try:
                all_autos = driver.find_elements(By.XPATH, "//*[@dir='auto']")
                valid_texts = []
                for el in all_autos:
                    t = el.text.strip()
                    el_y = el.location.get('y', 9999)
                    # 경계 위쪽에 있고, UI 텍스트가 아니며, 쿠팡파트너스 없는 것만
                    if (len(t) > 5
                            and t not in ["좋아요", "답글", "공유", "리포스트", "보내기", "활동 보기", "Follow", "팔로우", "인기순"]
                            and "쿠팡파트너스" not in t):
                        # 경계가 있으면 경계 위쪽만
                        if boundary_y is None or el_y < boundary_y:
                            valid_texts.append(t)

                if valid_texts:
                    content = max(valid_texts, key=len)
                    import re
                    # '1 / 2' 같은 이미지 넘김 표시가 끝에 붙어 추출되는 것 제거
                    content = re.sub(r'[\r\n\s]*\d+[\r\n\s]*/[\r\n\s]*\d+[\r\n\s]*$', '', content).strip()
                else:
                    content = "본문 텍스트를 찾을 수 없습니다."
            except Exception:
                content = "텍스트 파싱 오류"

            # ── 3. 캐러셀(Carousel) 강제 스캔 (지연 로딩 대응) ────────────────
            try:
                # 다음 버튼(Next)이 있으면 클릭하여 모든 미디어 로딩 유도
                for _ in range(10): # 최대 10장까지 탐색
                    next_btns = driver.find_elements(By.CSS_SELECTOR, "div[role='button'][aria-label='Next'], div[role='button'][aria-label='다음']")
                    visible_next = [b for b in next_btns if b.is_displayed()]
                    if visible_next:
                        driver.execute_script("arguments[0].click();", visible_next[0])
                        time.sleep(1.2)
                    else:
                        break
            except Exception:
                pass

            # ── 4. 본문 이미지 + 동영상 수집 (JSON + DOM 병행) ────────────────
            media_items = []  # (y, src, is_video) 튜플 리스트
            json_video_urls = []
            
            # (A) JSON 메타데이터에서 비디오 추출 (가장 확실한 방법)
            try:
                page_source = driver.page_source
                # 비디오 추출 (scontent CDN 다이렉트 링크)
                # Threads/Instagram 특유의 비디오 데이터 구조 탐색
                found_vids = re.findall(r'"video_versions":\s*\[\s*\{\s*"type":\s*\d+,\s*"width":\s*\d+,\s*"height":\s*\d+,\s*"url":\s*"(https://[^"]+)"', page_source)
                for v_url in found_vids:
                    v_url = v_url.replace('\\u0026', '&')
                    if v_url not in json_video_urls:
                        json_video_urls.append(v_url)
                
                if json_video_urls:
                    print(f"    [Scraper] JSON 메타데이터에서 동영상 {len(json_video_urls)}개 포착!", flush=True)
            except Exception:
                pass

            # (B) DOM 기반 이미지/동영상 수집 (컨테이너/액션바 기반 고립)
            try:
                js_code = """
                function extractMainPostMedia() {
                    // 1. 하트 버튼 찾기 (보통 게시물의 하단 액션바에 위치)
                    let heartBtns = Array.from(document.querySelectorAll('svg[aria-label="Like"], svg[aria-label="좋아요"]'));
                    if (heartBtns.length === 0) return {error: "No like buttons found"};
                    
                    // 2. 상단 네비게이션바 등을 제외하고 본문의 가장 첫 번째 액션바 찾기
                    let mainHeart = heartBtns.find(btn => {
                        let rect = btn.getBoundingClientRect();
                        return rect.y > 50;
                    });
                    if (!mainHeart) return {error: "No valid main heart"};
                    
                    // 3. 상위 컨테이너(게시물 블록) 찾기
                    let container = mainHeart.closest('div[data-pressable-container="true"]');
                    
                    // fallback: 일정 높이 이상의 가장 가까운 상위 div 찾기
                    if (!container) {
                        let curr = mainHeart;
                        for (let i=0; i<15; i++) {
                            if (!curr) break;
                            if (curr.getBoundingClientRect().height > 150) {
                                container = curr;
                                break;
                            }
                            curr = curr.parentElement;
                        }
                    }
                    if (!container) return {error: "No container found"};
                    
                    // 4. 추출 로직: 해당 '고립된' 컨테이너 내부의 비디오/이미지만 추출!
                    let result_items = [];
                    
                    // 동영상
                    let videos = container.querySelectorAll('video');
                    let poster_urls = new Set();
                    for (let vid of videos) {
                        let poster = vid.getAttribute('poster') || "";
                        if (poster) poster_urls.add(poster);
                        
                        let src = vid.getAttribute('src') || "";
                        if (!src) {
                            let source = vid.querySelector('source');
                            if (source) src = source.getAttribute('src') || "";
                        }
                        if (src) {
                            let rect = vid.getBoundingClientRect();
                            result_items.push({y: rect.y, src: src, is_video: true});
                        }
                    }
                    
                    // 이미지
                    let images = container.querySelectorAll('img');
                    for (let img of images) {
                        let src = img.getAttribute('src') || "";
                        if (!src || !src.includes('scontent')) continue;
                        
                        // poster 썸네일 제외
                        if (poster_urls.has(src)) continue;
                        
                        let alt = (img.getAttribute('alt') || "").toLowerCase();
                        if (alt.includes('profile') || alt.includes('프로필')) continue;
                        
                        // 동영상 내부 썸네일 제외 (Threads 구조 대응)
                        let hasPicture = img.closest('picture') !== null;
                        let inVideoPlayer = img.closest('[aria-label*="Video"],[aria-label*="video"]') !== null;
                        
                        // y좌표 겹치는 동영상 썸네일 방어 루틴 (JS 레벨)
                        let rect = img.getBoundingClientRect();
                        let isThumbnail = false;
                        
                        // V1: <picture> 부모가 없고 주변에 비디오 요소와 Y좌표 일치 시
                        let isNearVideo = false;
                        for (let item of result_items) {
                            if (item.is_video && Math.abs(item.y - rect.y) < 5) isNearVideo = true;
                        }
                        
                        if (isNearVideo && !hasPicture) isThumbnail = true;
                        if (inVideoPlayer) isThumbnail = true;
                        
                        if (!isThumbnail) {
                            result_items.push({y: rect.y, src: src, is_video: false});
                        }
                    }
                    
                    // 본문 텍스트도 같은 컨테이너에서 추출
                    let textNodes = container.querySelectorAll('[dir="auto"]');
                    let texts = [];
                    for (let tn of textNodes) {
                        let t = tn.innerText.trim();
                        if (t.length > 5 && !t.includes('쿠팡파트너스') && !['좋아요','답글','공유','리포스트','보내기','활동 보기','Follow','팔로우','인기순'].includes(t)) {
                            texts.push(t);
                        }
                    }
                    let containerText = texts.length > 0 ? texts.reduce((a,b) => a.length >= b.length ? a : b) : '';
                    // 페이지 넘김 표시 제거 (1 / 2, 2/5 등) - g 플래그 추가 및 중복 공백 대응
                    let pageNumRegex = /\\s*\\d+\\s*\\/\\s*\\d+\\s*$/g;
                    containerText = containerText.replace(pageNumRegex, '').trim();
                    
                    return {items: result_items, container_text: containerText};
                }
                return extractMainPostMedia();
                """
                media_res = driver.execute_script(js_code)
                
                if media_res and "items" in media_res:
                    for m in media_res["items"]:
                        media_items.append((m["y"], m["src"], m["is_video"]))
                    # 컨테이너 기반 텍스트 추출 (미디어와 동일 범위)
                    container_text = media_res.get("container_text", "")
                    if container_text:
                        content = container_text
                        print(f"    [Scraper] DOM 컨테이너 기반 고립 추출 완료 (총 {len(media_items)}개 요소, 본문 {len(content)}자)", flush=True)
                    else:
                        print(f"    [Scraper] DOM 컨테이너 기반 고립 추출 완료 (총 {len(media_items)}개 요소, 본문 미발견)", flush=True)
                else:
                    print(f"    [Scraper] 컨테이너 기반 추출 실패: {media_res.get('error', 'unknown')}. 기존 발견된 미디어 없음.", flush=True)

            except Exception as e:
                print(f"    ⚠️ DOM 고립 미디어 추출 실패: {e}", flush=True)


            # Y좌표 오름차순으로 정렬 → 원본 DOM 순서 복원
            media_items.sort(key=lambda x: x[0])

            # 중복 제거 (동일 src가 여러 번 등장할 수 있음)
            seen = set()
            for y_pos, src, is_vid in media_items:
                if src not in seen:
                    seen.add(src)
                    if is_vid:
                        video_urls.append(src)
                    else:
                        image_urls.append(src)

            # JSON에서 찾은 비디오가 DOM에서 누락되었을 경우 보완
            for j_vid in json_video_urls:
                if j_vid not in video_urls:
                    video_urls.append(j_vid)

            # 최종 미디어 리스트 구성 (순서: 비디오 우선 -> 이미지들)
            all_media = video_urls + image_urls

            print(f"    [Scraper] 최종 수집: 이미지={len(image_urls)}개, 동영상={len(video_urls)}개 (동영상 우선 정렬)", flush=True)

            # ── 5. 재호스팅 분리 (파이프라인에서 병렬로 수행) ────────
            # 본문 결과만 반환
            pass

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"    ⚠️ [Scraper] 오류 발생: {e}", flush=True)

        return {
            "url": url,
            "text": content,
            "images": image_urls,
            "all_media": all_media if 'all_media' in locals() else [],
            "video_urls": video_urls if 'video_urls' in locals() else []
        }

    finally:
        if should_close:
            try:
                driver.quit()
            except Exception:
                pass


def rehost_media_urls(media_urls: list, driver=None) -> list:
    """
    scontent CDN 이미지/동영상 URL을 병렬로 다운로드 후 catbox.moe에 재업로드하여
    Threads API가 접근 가능한 공개 URL 리스트를 반환합니다.
    """
    import requests as req
    import base64
    import tempfile
    import os
    import time
    from concurrent.futures import ThreadPoolExecutor

    if not media_urls:
        return []

    print(f"    ▶️ [재호스팅] {len(media_urls)}개 미디어 처리 시작 (병렬)...", flush=True)

    # Selenium 드라이버가 넘겨지면 이를 사용하여 base64를 따오는 함수
    def get_base64_via_js(idx, url, d):
        try:
            js_script = """
            var url = arguments[0];
            var callback = arguments[1];
            fetch(url, {credentials: 'include'})
                .then(r => r.blob())
                .then(blob => {
                    var reader = new FileReader();
                    reader.onloadend = function() {
                        callback(reader.result);
                    };
                    reader.readAsDataURL(blob);
                })
                .catch(e => callback('ERROR:' + e.message));
            """
            return d.execute_async_script(js_script, url)
        except Exception:
            return None

    def process_single_media(idx_url):
        i, url = idx_url
        if i >= 10: return None
        
        raw_bytes = None
        data_url_prefix = ""

        # 1. 다운로드 시도 (JS fetch)
        if driver:
            res_data_url = get_base64_via_js(i, url, driver)
            if res_data_url and not res_data_url.startswith('ERROR:'):
                if ',' in res_data_url:
                    data_url_prefix, b64_data = res_data_url.split(',', 1)
                    raw_bytes = base64.b64decode(b64_data)

        # 2. fallback (requests)
        if not raw_bytes:
            try:
                r_header = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
                r_res = req.get(url, headers=r_header, timeout=10)
                if r_res.status_code == 200:
                    raw_bytes = r_res.content
            except Exception:
                return None

        if not raw_bytes: return None

        # 확장자 결정
        is_video = any(ext in url.lower() for ext in ['.mp4', '.mov', '.webm'])
        ext = '.mp4' if is_video else '.jpg'
        if "video" in data_url_prefix: ext = '.mp4'
        elif "png" in data_url_prefix: ext = '.png'
        elif "webp" in data_url_prefix: ext = '.webp'

        # 3. tmpfiles 업로드
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(raw_bytes)
            tmp_path = tmp.name

        try:
            with open(tmp_path, 'rb') as f:
                # catbox 차단 대응: tmpfiles.org 사용
                resp = req.post(
                    "https://tmpfiles.org/api/v1/upload",
                    files={"file": f},
                    timeout=35
                )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    raw_url = data["data"]["url"]
                    return raw_url.replace("http://tmpfiles.org/", "https://tmpfiles.org/dl/")
        except Exception:
            pass
        finally:
            if os.path.exists(tmp_path): os.remove(tmp_path)
        return None

    # 병렬 처리 (JS fetch는 드라이버가 하나뿐이므로 순차적으로 수행하되, 업로드는 병렬화)
    # 실제로는 requests 다운로드와 업로드가 병목이므로 map을 사용하여 병렬화함
    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        idx_urls = list(enumerate(media_urls))
        mapped_results = list(executor.map(process_single_media, idx_urls))
        results = [r for r in mapped_results if r]

    print(f"    📊 [재호스팅] {len(results)}/{len(media_urls)}개 성공", flush=True)
    return results


def scrape_comment_for_coupang(url, driver=None):
    """
    Threads 게시물 댓글에서 link.coupang.com URL을 탐색합니다.
    
    주요 변경: Threads는 링크를 <a href="https://l.threads.com/?u=https%3A%2F%2Flink.coupang.com...">
    형식으로 래핑합니다. dir="auto" 텍스트만 보지 않고 <a> 태그 href를 직접 탐색합니다.
    
    Returns:
        dict | None: {'comment_text': str, 'coupang_urls': list[str]} 또는 None
    """
    from urllib.parse import urlparse, parse_qs, unquote
    import re as _re

    should_close = False
    if driver is None:
        try:
            driver = init_driver()
            driver.set_page_load_timeout(20)
            should_close = True
        except Exception as e:
            print(f"    ❌ [댓글 스크래퍼] 브라우저 초기화 실패: {e}", flush=True)
            return None

    try:
        print(f"    [댓글 스크래퍼] {url} 댓글 탐색 중...", flush=True)
        driver.get(url)
        time.sleep(6)

        # 스크롤로 댓글 렌더링 유도
        try:
            driver.execute_script("window.scrollBy(0, 500)")
            time.sleep(2)
        except Exception:
            pass

        coupang_urls = []
        comment_text = ""

        # ── 방법 1: <a> 태그 href에서 쿠팡 링크 탐색 ────────────────────
        # Threads가 링크를 l.threads.com/?u=<인코딩된URL> 형태로 래핑
        try:
            anchors = driver.find_elements(By.TAG_NAME, "a")
            for anchor in anchors:
                href = anchor.get_attribute("href") or ""
                
                # l.threads.com 래핑 URL에서 실제 coupang URL 추출
                if "l.threads.com" in href and "coupang" in href:
                    try:
                        parsed = urlparse(href)
                        qs = parse_qs(parsed.query)
                        real_url = unquote(qs.get("u", [""])[0])
                        if "coupang.com" in real_url:
                            coupang_urls.append(real_url)
                    except Exception:
                        pass
                
                # 직접 coupang URL인 경우
                elif "link.coupang.com" in href or "coupang.com/vp/products" in href:
                    coupang_urls.append(href)
                
                # 표시 텍스트에 link.coupang.com 포함 (<a> 텍스트는 단축 URL 표시)
                display_text = anchor.text.strip()
                if "link.coupang.com" in display_text and not coupang_urls:
                    coupang_urls.append("https://" + display_text.strip())
        except Exception as e:
            print(f"    ⚠️ [댓글 스크래퍼] a태그 탐색 오류: {e}", flush=True)

        # ── 방법 2: 텍스트에서 직접 URL 패턴 탐색 (보조) ────────────────
        if not coupang_urls:
            try:
                all_autos = driver.find_elements(By.XPATH, "//*[@dir='auto']")
                coupang_pattern = _re.compile(r'https?://(?:link\.coupang\.com|www\.coupang\.com)/\S+')
                simple_pattern = _re.compile(r'link\.coupang\.com/\S+')
                for el in all_autos:
                    t = el.text.strip()
                    found = coupang_pattern.findall(t) or simple_pattern.findall(t)
                    if found:
                        urls = [u if u.startswith("http") else "https://" + u for u in found]
                        coupang_urls.extend(urls)
                        comment_text = t
                        break
            except Exception:
                pass

        if not coupang_urls:
            print(f"    ⚠️ [댓글 스크래퍼] 쿠팡 링크 없음", flush=True)
            return None

        # 중복 제거
        coupang_urls = list(dict.fromkeys(coupang_urls))

        # 댓글 텍스트 추출 (쿠팡링크 주변 텍스트)
        if not comment_text:
            try:
                all_autos = driver.find_elements(By.XPATH, "//*[@dir='auto']")
                for el in all_autos:
                    t = el.text.strip()
                    if "쿠팡파트너스" in t or "coupang" in t.lower() or "link.coupang" in t:
                        comment_text = t
                        break
            except Exception:
                pass

        print(f"    ✅ [댓글 스크래퍼] 쿠팡 링크 발견 ({len(coupang_urls)}개): {coupang_urls[0][:60]}", flush=True)
        return {
            'comment_text': comment_text,
            'coupang_urls': coupang_urls
        }

    except Exception as e:
        print(f"    ❌ [댓글 스크래퍼] 오류: {e}", flush=True)
        return None
    finally:
        if should_close:
            try:
                driver.quit()
            except Exception:
                pass


def fetch_coupang_product_info(coupang_url: str, driver=None) -> dict:
    """
    쿠팡 단축 URL에 접속하여 상품명과 이미지를 추출합니다.
    검색 결과 페이지(Listing)인 경우 1위 상품의 상세 페이지로 자동 이동합니다.
    """
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    own_driver = False
    if driver is None:
        driver = init_driver()
        own_driver = True

    product_name = ""
    image_url = ""

    try:
        # 봇 탐지 회피: 메인 페이지 먼저 접속하여 쿠키 생성
        print("    [쿠팡] 메인 페이지 경유 중 (봇 탐지 회피)...", flush=True)
        driver.get("https://www.coupang.com")
        time.sleep(random.uniform(2, 4))

        print(f"    [쿠팡] {coupang_url} 접속 중...", flush=True)
        driver.get(coupang_url)
        time.sleep(random.uniform(3, 5))

        # 1. 검색/카테고리 결과 페이지인지 확인
        current_url = driver.current_url
        if "/np/search" in current_url or "/np/categories" in current_url:
            print("    [쿠팡] 검색 결과 페이지 감지. 1위 상품으로 이동합니다.", flush=True)
            try:
                # 모든 링크 중 /vp/products/ 패턴을 가진 첫 번째 상품 찾기
                all_links = driver.find_elements(By.TAG_NAME, "a")
                product_link_el = None
                for link in all_links:
                    href = link.get_attribute("href")
                    if href and "/vp/products/" in href:
                        product_link_el = link
                        break
                
                if product_link_el:
                    product_link = product_link_el.get_attribute("href")
                    print(f"    [쿠팡] 1위 상품 발견: {product_link[:60]}...", flush=True)
                    driver.get(product_link)
                    time.sleep(random.uniform(3, 5))
                else:
                    print("    ⚠️ [쿠팡] 상품 링크를 찾지 못했습니다.", flush=True)
            except Exception as e:
                print(f"    ⚠️ [쿠팡] 1위 상품 이동 실패: {e}", flush=True)

        # 2. 상세 페이지에서 정보 추출
        try:
            # 상품명 추출 (h1 우선)
            name_selectors = ["h1", "h2.prod-buy-header__title", ".prod-buy-header__title"]
            for sel in name_selectors:
                elements = driver.find_elements(By.CSS_SELECTOR, sel)
                if elements and elements[0].text.strip():
                    product_name = elements[0].text.strip()
                    break
            if not product_name:
                product_name = driver.execute_script("return document.querySelector('meta[property=\"og:title\"]')?.content") or ""

            # 이미지 URL 추출 (다양한 셀렉터 시도)
            img_selectors = [
                "img.prod-image__detail", 
                "img.prod-image-detail", 
                "#repImageContainer img", 
                ".prod-main-img img",
                "img[alt='대표이미지']",
                ".image-item img",
                "img#main-image"
            ]
            for sel in img_selectors:
                elements = driver.find_elements(By.CSS_SELECTOR, sel)
                if elements:
                    for el in elements:
                        src = el.get_attribute("src")
                        if src and "image" in src and "remote" in src:
                            image_url = src
                            break
                if image_url: break
            
            # og:image 백업
            if not image_url:
                image_url = driver.execute_script("return document.querySelector('meta[property=\"og:image\"]')?.content") or ""
            
            # 썸네일 리스트에서 첫 번째 이미지 시도 (위 셀렉터 모두 실패 시)
            if not image_url:
                try:
                    thumbs = driver.find_elements(By.CSS_SELECTOR, ".prod-image__item img")
                    if thumbs:
                        image_url = thumbs[0].get_attribute("src")
                except: pass
            
            if image_url and image_url.startswith("//"):
                image_url = "https:" + image_url
            
            if image_url:
                print(f"    [쿠팡 상품] 수집 성공 - 이름: {product_name[:30]}... / 이미지: {image_url[:60]}...", flush=True)
            else:
                print(f"    ⚠️ [쿠팡 상품] 이미지 추출 실패 (URL: {driver.current_url})", flush=True)

        except Exception as e:
            print(f"    ⚠️ [쿠팡] 정보 추출 오류: {e}", flush=True)
        
        # 상품명 정제 (쿠팡 특유의 뒤에 붙는 정보 제거)
        if " : " in product_name:
            product_name = product_name.split(" : ")[0]
        if " | " in product_name:
            product_name = product_name.split(" | ")[0]
            
        # 에러 메시지 필터링: 'Access Denied', 'Access Denied' 등 무시
        if any(err in product_name.lower() for err in ["access denied", "access denied"]):
            print(f"    ⚠️ [쿠팡] 에러 메시지 감지(Access Denied). 제품명을 공백 처리합니다.", flush=True)
            product_name = ""

        print(f"    [쿠팡 상품] 이름: {product_name[:30]} / 이미지: {'있음' if image_url else '없음'}", flush=True)

        # 최종 상품 URL 확보 (이미 상세 페이지에 있음)
        product_url = driver.current_url
        print(f"    [쿠팡 상품] URL: {product_url[:60]}...", flush=True)

    except Exception as e:
        print(f"    ⚠️ [쿠팡 상품] 정보 추출 실패: {e}", flush=True)
    finally:
        if own_driver:
            driver.quit()

    return {
        "product_name": product_name, 
        "image_url": image_url, 
        "product_url": product_url
    }



def _extract_meta(html: str, property_name: str) -> str:
    """HTML에서 og: 메타태그 content를 추출합니다."""
    import re as _re
    pattern = rf'<meta[^>]+property=["\']?{_re.escape(property_name)}["\']?[^>]+content=["\']([^"\']+)["\']'
    m = _re.search(pattern, html, _re.IGNORECASE)
    if m:
        return m.group(1)
    # 순서 반대인 경우도 체크
    pattern2 = rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']?{_re.escape(property_name)}["\']?'
    m2 = _re.search(pattern2, html, _re.IGNORECASE)
    return m2.group(1) if m2 else ""


if __name__ == "__main__":
    test_url = input("테스트할 Threads 게시물 URL을 입력하세요: ")
    if test_url:
        result = scrape_thread_content(test_url)
        print("======== Scraping Result ========")
        print(f"URL: {result['url']}")
        print(f"Content: {result['text']}")
        print(f"Images: {result['images']}")
        print("=================================")

