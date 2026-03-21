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
    Threads 게시물의 본문 텍스트, 조회수, 좋아요, 답글 수 등을 추출합니다.
    [자동화/scraper.py] 로직을 이식하여 '활동 보기' 버튼 없이도 본문을 정확히 추출합니다.
    """
    if "threads.com" in url:
        url = url.replace("threads.com", "threads.net")

    driver = Driver(uc=True, headless=True)
    try:
        driver.get(url)
        time.sleep(8) # 충분한 렌더링 대기
        
        data = {
            "content_text": "",
            "views": 0,
            "likes": 0,
            "replies": 0,
            "image_urls": [],
            "first_reply_views": 0
        }

        # 1. 전역 지표 시도 (조회수 등)
        data["views"] = parse_metric_to_int(get_views_global(driver))

        # 2. [자동화 로직 핵심] JS 기반 본문 및 인터랙션 고립 추출
        js_code = """
        function extractMainPost() {
            // 하트 버튼(Like)은 로그인 여부와 관계없이 게시물 하단에 존재함
            let heartBtns = Array.from(document.querySelectorAll('svg[aria-label="Like"], svg[aria-label="좋아요"]'));
            if (heartBtns.length === 0) return {error: "No like buttons found"};
            
            // 상단 네비게이션 등을 제외하고 Y좌표가 어느 정도 있는 첫 번째 하트 선택
            let mainHeart = heartBtns.find(btn => btn.getBoundingClientRect().y > 50);
            if (!mainHeart) return {error: "No valid main heart"};
            
            // 상위 컨테이너(게시물 블록) 고립
            let container = mainHeart.closest('div[data-pressable-container="true"]');
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
            
            // 본문 텍스트 추출 (dir=auto 중 가장 긴 것)
            let textNodes = container.querySelectorAll('[dir="auto"]');
            let texts = [];
            let likeText = "0", replyText = "0";
            
            for (let tn of textNodes) {
                let t = tn.innerText.trim();
                if (t.length > 5 && !['좋아요','답글','공유','리포스트','보내기','활동 보기','Follow','팔로우','인기순'].includes(t)) {
                    texts.push(t);
                }
            }
            
            // 좋아요/답글 숫자 추출 시도 (컨테이너 내 데이터 기반)
            // 보통 svg 옆의 span에 숫자가 들어있음
            try {
                let spans = container.querySelectorAll('span');
                for (let i=0; i < spans.length; i++) {
                    let s = spans[i].innerText;
                    if (s.includes('좋아요') || s.includes('Like')) likeText = s;
                    if (s.includes('답글') || s.includes('Reply')) replyText = s;
                }
            } catch(e) {}

            // 미디어(이미지/영상) 추출
            let mediaUrls = [];
            let imgEls = container.querySelectorAll('img');
            for (let img of imgEls) {
                if (img.src && !img.src.includes('profile_res') && img.src.startsWith('http')) {
                    mediaUrls.push(img.src);
                }
            }
            
            let videoEls = container.querySelectorAll('video');
            for (let v of videoEls) {
                if (v.src && v.src.startsWith('http')) {
                    mediaUrls.push(v.src);
                }
            }

            let mainText = texts.length > 0 ? texts.reduce((a,b) => a.length >= b.length ? a : b) : '';
            // 페이지 넘김(1/2) 등 제거
            mainText = mainText.replace(/\\s*\\d+\\s*\\/\\s*\\d+\\s*$/g, '').trim();

            return {
                text: mainText,
                likes: likeText,
                replies: replyText,
                media: mediaUrls
            };
        }
        return extractMainPost();
        """
        
        res = driver.execute_script(js_code)
        if res and "text" in res:
            data["content_text"] = res["text"]
            data["image_urls"] = res.get("media", [])
            # 기존 parse_metric_to_int 재활용
            if res.get("likes"): data["likes"] = parse_metric_to_int(res["likes"])
            if res.get("replies"): data["replies"] = parse_metric_to_int(res["replies"])
            print(f"    [Scraper] 고립 추출 성공: {len(data['content_text'])}자 / Media: {len(data['image_urls'])}개 / Likes: {data['likes']}")
        else:
            # Fallback 1: 활동보기 없이 전역 탐색
            print(f"    [Scraper] 고립 추출 실패 ({res.get('error') if res else 'None'}), Fallback 탐색 중...")
            all_spans = driver.find_elements(By.XPATH, "//span[@dir='auto']")
            valid_texts = [s.text.strip() for s in all_spans if len(s.text.strip()) > 30 and not check_is_profile_link(s)]
            if valid_texts:
                data["content_text"] = max(valid_texts, key=len)
            
            # 지표 전역 탐색
            data["likes"] = parse_metric_to_int(get_metric_inside_box(driver, ["좋아요", "Like"]))
            data["replies"] = parse_metric_to_int(get_metric_inside_box(driver, ["답글", "Reply"]))

        return data
    except Exception as e:
        print(f"Scraping error: {e}")
        return None
    finally:
        driver.quit()

def calculate_mss_from_metrics(metrics):
    """
    수집된 지표를 바탕으로 MSS 점수 계산 (댓글조회수^2 / 본문조회수)
    여기서는 원본 공식 대신 단순화 공식을 사용 중이었으나, 원활한 실험을 위해 
    일단 좋아요/답글 기준으로 MSS를 계산합니다 (첫댓글조회수는 별도 크롤링이 필요하므로).
    """
    if not metrics: return 0.0
    
    views = metrics.get("views", 0)
    replies = metrics.get("replies", 0)
    likes = metrics.get("likes", 0)
    first_reply_views = metrics.get("first_reply_views", 0)
    
    # 대표님의 마스터 공식: (첫댓글조회수^2 / 본문조회수)
    if views > 0 and first_reply_views > 0:
        raw_mss = (first_reply_views ** 2) / views
        # 0~100 정규화 (최대치 100 기준 임의 스케일)
        mss = min(raw_mss * 10.0, 100.0)
    else:
        # 백업 공식
        raw_score = (likes * 1) + (replies * 5)
        mss = min(raw_score / 10.0, 100.0)
        
    return mss
