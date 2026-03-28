import time
import re
from seleniumbase import Driver
from selenium.webdriver.common.by import By

def get_views_global(driver):
    try:
        view_el = driver.find_element(By.XPATH, "//span[contains(text(), '조회')]")
        return view_el.text.strip()
    except:
        return "0회"

def get_metric_inside_box(parent_el, label_names):
    if isinstance(label_names, str): label_names = [label_names]
    for label in label_names:
        try:
            xpath = f".//*[contains(@aria-label, '{label}')]//ancestor::div[1]//span"
            element = parent_el.find_element(By.XPATH, xpath)
            return element.text.strip()
        except: continue
    return "0"

def check_is_profile_link(el):
    try:
        el.find_element(By.XPATH, "./ancestor::a")
        return True
    except:
        return False

def parse_metric_to_int(val):
    s = str(val).replace('조회', '').replace('회', '').replace(',', '').strip()
    try:
        multiplier = 1
        if '천' in s: multiplier = 1000; s = s.replace('천', '')
        elif '만' in s: multiplier = 10000; s = s.replace('만', '')
        return int(float(s) * multiplier)
    except: return 0

def get_threads_full_data(url):
    """
    [Advanced Research Engine] 
    1. '자동화/scraper.py'의 실전 비기(경계선 탐지, 캐러셀 클릭)
    2. 'makingprogram.py'의 성과 지표(리포스트, 첫댓글조회수)
    두 로직을 결합하여 로그인 없이도 완벽한 데이터를 수집합니다.
    """
    if "threads.com" in url:
        url = url.replace("threads.com", "threads.net")

    import os
    # Render Docker 환경 기준 경로 (자동 설치된 google-chrome)
    chrome_bin = os.environ.get("CHROME_BIN", "/usr/bin/google-chrome")
    
    # [극한의 512MB RAM 생존용 Chrome 최적화 옵션 (이미지 분석 로직 유지)]
    extra_args = [
        "--no-sandbox", 
        "--disable-dev-shm-usage", 
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--single-process",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-client-side-phishing-detection",
        "--disable-default-apps",
        "--disable-extensions",
        "--mute-audio"
    ]
    
    driver = Driver(
        uc=True, 
        headless=True, 
        browser="chrome",
        binary_location=chrome_bin,
        extra_args=extra_args
    )
    try:
        driver.get(url)
        print(f"    [Research] {url} 접속 및 8초 대기...", flush=True)
        time.sleep(8) 
        
        data = {
            "content_text": "",
            "views": 0,
            "likes": 0,
            "replies": 0,
            "reposts": 0,
            "shares": 0,
            "created_at": "",
            "image_urls": [],
            "first_reply_views": 0
        }

        # --- 1. 캐러셀 강제 클릭 (지연 로딩 대응) ---
        try:
            for _ in range(5):
                next_btns = driver.find_elements(By.CSS_SELECTOR, "div[role='button'][aria-label='Next'], div[role='button'][aria-label='다음']")
                visible_next = [b for b in next_btns if b.is_displayed()]
                if visible_next:
                    driver.execute_script("arguments[0].click();", visible_next[0])
                    time.sleep(1.0)
                else: break
        except: pass

        # --- 2. 본문/댓글 경계 Y 탐지 (인기순/Most relevant 기준) ---
        boundary_y = 99999
        try:
            boundary_els = driver.find_elements(By.XPATH, "//*[contains(text(),'인기순') or contains(text(),'Most relevant')]")
            for el in boundary_els:
                y = el.location.get('y', 0)
                if y > 100:
                    boundary_y = y
                    break
        except: pass

        # --- 3. JS 복합 추출 엔진 (자동화/scraper.py 기법 적용) ---
        js_code = """
        function extractResearchData() {
            let heartBtns = Array.from(document.querySelectorAll('svg[aria-label="Like"], svg[aria-label="좋아요"]'));
            let mainHeart = heartBtns.find(btn => btn.getBoundingClientRect().y > 50);
            if (!mainHeart) return {error: "No context"};
            
            // 컨테이너 격리
            let container = mainHeart.closest('article') || mainHeart.closest('div[data-pressable-container="true"]');
            if (!container) {
                let curr = mainHeart;
                for (let i=0; i<15; i++) {
                    if (!curr) break;
                    let r = curr.getBoundingClientRect();
                    if (r.height > 150 && r.width > 200) { container = curr; break; }
                    curr = curr.parentElement;
                }
            }
            if (!container) return {error: "No container"};

            // 지표 추출 ( aria-label )
            function getVal(label) {
                let el = container.querySelector(`[aria-label*="${label}"]`);
                if (el) {
                    let span = el.closest('div').querySelector('span');
                    return span ? span.innerText : "0";
                }
                return "0";
            }

            // 미디어 확보 (썸네일 제외 지능형 필터)
            let videoEls = Array.from(container.querySelectorAll('video'));
            let posterUrls = videoEls.map(v => v.getAttribute('poster')).filter(p => p);
            
            let allImgs = Array.from(container.querySelectorAll('img')).map(img => img.src);
            let validImgs = allImgs.filter(src => src && src.includes('scontent') && !posterUrls.includes(src));
            let validVids = videoEls.map(v => v.src || (v.querySelector('source') ? v.querySelector('source').src : '')).filter(s => s);

            // 본문 텍스트 (dir=auto 중 최장문)
            let textNodes = Array.from(container.querySelectorAll('[dir="auto"]'));
            let validTexts = textNodes.map(n => n.innerText.trim()).filter(t => t.length > 5 && !['좋아요','답글','리포스트','공유'].includes(t));
            let mainText = validTexts.length > 0 ? validTexts.reduce((a,b) => a.length >= b.length ? a : b) : '';

            // 첫 댓글 링크 (Sibling)
            let firstReplyUrl = (function() {
                let parent = container.parentElement;
                let next = parent ? parent.querySelector('a[href*="/post/"]') : null;
                return (next && next.href !== window.location.href) ? next.href : null;
            })();

            return {
                text: mainText,
                likes: getVal("좋아요") || getVal("Like"),
                replies: getVal("답글") || getVal("Reply"),
                reposts: getVal("리포스트") || getVal("Repost"),
                shares: getVal("보내기") || getVal("Share") || getVal("공유"),
                media: [...validVids, ...validImgs],
                createdAt: (container.querySelector('time') || {}).dateTime || "",
                firstReplyUrl: firstReplyUrl
            };
        }
        return extractResearchData();
        """
        
        res = driver.execute_script(js_code)
        if res and "text" in res:
            data["content_text"] = res["text"]
            data["created_at"] = res.get("createdAt", "")
            data["likes"] = parse_metric_to_int(res["likes"])
            data["replies"] = parse_metric_to_int(res["replies"])
            data["reposts"] = parse_metric_to_int(res["reposts"])
            data["shares"] = parse_metric_to_int(res["shares"])
            data["image_urls"] = res.get("media", [])
            data["views"] = parse_metric_to_int(get_views_global(driver))

            # --- 4. [비기] 첫댓글 조회수 심층 추적 ---
            first_reply_url = res.get("firstReplyUrl")
            if first_reply_url:
                print(f"    [Research] 첫댓글 발견: {first_reply_url} 탐색 중...")
                driver.get(first_reply_url)
                time.sleep(5)
                data["first_reply_views"] = parse_metric_to_int(get_views_global(driver))
                print(f"    [Research] 첫댓글 조회수 확보: {data['first_reply_views']}")

        return data
    except Exception as e:
        print(f"Scraping error: {e}")
        return None
    finally:
        driver.quit()

def calculate_mss_from_metrics(metrics):
    """
    대표님의 마스터 공식 적용: (첫댓글조회수^2 / 본문조회수)
    """
    if not metrics: return 0.0
    
    views = metrics.get("views", 0)
    first_reply_views = metrics.get("first_reply_views", 0)
    
    if views > 0 and first_reply_views > 0:
        # 공식: 첫댓글조회수^2 / 본문조회수
        raw_mss = (first_reply_views ** 2) / views
        # 0~100 정규화 (10.0은 데이터 분포에 따른 가중치)
        mss = min(raw_mss * 10.0, 100.0)
        return round(float(mss), 2)
    else:
        # 백업 지표 (좋아요/답글 기반)
        likes = metrics.get("likes", 0)
        replies = metrics.get("replies", 0)
        reposts = metrics.get("reposts", 0)
        raw_score = (likes * 1) + (replies * 5) + (reposts * 10)
        return min(raw_score / 15.0, 100.0)
