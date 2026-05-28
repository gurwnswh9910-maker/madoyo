
# -*- coding: utf-8 -*-
import sys
import io

# Windows 환경에서 이모지 및 한글 출력을 위한 UTF-8 인코딩 설정
class DummyStd:
    def write(self, *args, **kwargs): pass
    def flush(self, *args, **kwargs): pass

if sys.stdout is None:
    sys.stdout = DummyStd()
else:
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except AttributeError:
        pass

if sys.stderr is None:
    sys.stderr = DummyStd()

import time
import random
import pandas as pd
import traceback
import os
import json
import shutil
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime

# --- [1. 브라우저 환경 설정] ---
# (Main 함수 내부로 이동됨)

def get_views_global(driver):
    """ 본문, 헤더, 댓글 등 모든 위치에서 '조회' 수치를 찾음 (실측 테스트 검증 완료) """
    xpaths = [
        "//*[contains(text(), '조회')]//parent::*",
        "//*[contains(text(), '조회')]",
        "//*[@aria-label[contains(., '조회') or contains(., 'view')]]"
    ]
    
    for xpath in xpaths:
        try:
            elements = driver.find_elements(By.XPATH, xpath)
            for el in elements:
                text = el.text or el.get_attribute("aria-label") or ""
                # 숫자와 '만회/천회/회'가 포함된 패턴 추출
                match = re.search(r'([\d\.]+[만천]*회)', text)
                if match: return match.group(1)
        except: continue
    return "0회"

def get_metric_inside_box(parent_el, label_names):
    """ 본문 패딩 박스 내부의 인터랙션 수치 수집 (좋아요, 답글 등 - 한국어 전용) """
    if isinstance(label_names, str): label_names = [label_names]
    
    for label in label_names:
        try:
            # aria-label 속성에 해당 한국어 텍스트가 포함된 요소 탐색
            xpath = f".//*[contains(@aria-label, '{label}')]//ancestor::div[1]//span"
            element = parent_el.find_element(By.XPATH, xpath)
            val = element.text.strip()
            if val: return val
        except: continue
    return "0"

def check_is_profile_link(el):
    """ 요소가 프로필 관련 링크(아이디, 사진)인지 판별 """
    try:
        el.find_element(By.XPATH, "./ancestor::a")
        return True
    except:
        return False


POST_UI_EXACT_NOISE = {
    "번역하기",
    "See translation",
    "활동 보기",
    "좋아요",
    "답글",
    "리포스트",
    "공유",
    "공유하기",
    "더 보기",
    "팔로우",
}

POST_UI_PHRASE_NOISE = (
    "Log in or sign up for Threads",
    "See what people are talking about and join the conversation.",
    "Instagram으로 계속하기",
    "Continue with Instagram",
)

POST_TIME_ONLY_PATTERN = re.compile(
    r"^(?:약\s*)?\d+\s*(?:초|분|시간|일|주|개월|년|h|m|d)$",
    re.IGNORECASE,
)


def is_noise_text(text):
    """본문 후보에서 UI 잡문/시간 라벨 같은 가짜 텍스트를 제거하기 위한 필터."""
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return True
    if cleaned in POST_UI_EXACT_NOISE:
        return True
    if POST_TIME_ONLY_PATTERN.fullmatch(cleaned):
        return True
    return any(phrase in cleaned for phrase in POST_UI_PHRASE_NOISE)


def normalize_post_text(text):
    """본문에 뒤섞여 들어온 캐러셀/번역/로그인 유도 문구를 정리한다."""
    lines = [line.strip() for line in str(text or "").splitlines()]
    cleaned_lines = []
    for line in lines:
        compact = " ".join(line.split())

        if not compact or is_noise_text(compact):
            continue

        # 1/2 표기는 downstream 파싱에서 유효 신호로 쓰므로 본문에 남긴다.
        cleaned_lines.append(compact)

    normalized = "\n".join(cleaned_lines).strip()
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    normalized = re.sub(r"\s+\n", "\n", normalized)
    normalized = re.sub(r"\n\s+", "\n", normalized)
    return normalized


def extract_post_text(main_padding_box):
    """
    Threads 본문 후보 중 실제 게시물 텍스트에 가장 가까운 조각을 선택한다.
    부모 div 전체를 긁어오면 번역 버튼/캐러셀 표기가 함께 붙을 수 있어,
    anchor 자체의 텍스트를 우선 사용한다.
    """
    best_text = ""
    best_score = -1

    all_autos = main_padding_box.find_elements(By.XPATH, ".//*[@dir='auto']")
    for el in all_autos:
        if check_is_profile_link(el):
            continue

        raw_text = (el.text or "").strip()
        candidate = normalize_post_text(raw_text)
        if not candidate or is_noise_text(candidate):
            continue

        score = len(candidate)
        if "\n" in candidate:
            score += 25
        if re.search(r"[가-힣A-Za-z]{3,}", candidate):
            score += 10

        if score > best_score:
            best_score = score
            best_text = candidate

    return best_text


def is_post_detail_url(url):
    return bool(re.search(r"threads\.(?:net|com)/@[^/]+/post/[^/?#]+", str(url or "")))


def is_saved_list_page(driver):
    """저장됨 리스트 화면인지 감지한다. 상세 페이지 추출 전에 안전장치로 사용."""
    try:
        current_url = driver.current_url or ""
    except:
        current_url = ""

    if is_post_detail_url(current_url):
        return False

    if "/saved" in current_url:
        return True

    try:
        if driver.find_elements(By.XPATH, "//div[contains(@data-pagelet, 'threads_post_page_')]"):
            return False
        if driver.find_elements(By.XPATH, "//div[contains(@data-pagelet, 'threads_saved_posts_')]"):
            return True
    except:
        pass

    return False


def should_keep_media_element(media_el):
    """프로필 사진/아이콘/작은 썸네일 같은 잡 이미지를 제외한다."""
    try:
        alt = (media_el.get_attribute("alt") or "").strip().lower()
    except:
        alt = ""

    if "프로필 사진" in alt or "profile picture" in alt:
        return False

    try:
        rect = media_el.rect or {}
        width = float(rect.get("width", 0) or 0)
        height = float(rect.get("height", 0) or 0)
        if width and height and (width < 150 or height < 150):
            return False
    except:
        pass

    try:
        anchor = media_el.find_element(By.XPATH, "./ancestor::a[1]")
        href = (anchor.get_attribute("href") or "").lower()
        if any(token in href for token in ("/search", "/saved", "/activity")):
            return False
        if re.search(r"threads\.(?:net|com)/@[^/]+/?$", href):
            return False
    except:
        pass

    return True


def expand_main_carousel(driver, scope_el=None, max_clicks=10):
    """메인 게시물의 캐러셀을 끝까지 넘겨 지연 로딩된 미디어를 드러낸다."""
    for _ in range(max_clicks):
        try:
            if scope_el:
                next_btns = scope_el.find_elements(
                    By.XPATH,
                    ".//div[@role='button' and (@aria-label='Next' or @aria-label='다음')]",
                )
            else:
                next_btns = driver.find_elements(
                    By.XPATH,
                    "//div[@role='button' and (@aria-label='Next' or @aria-label='다음')]",
                )
            visible_next = [btn for btn in next_btns if btn.is_displayed()]
            if not visible_next:
                break
            driver.execute_script("arguments[0].click();", visible_next[0])
            time.sleep(1.2)
        except:
            break


def get_json_video_urls(driver):
    """Threads page_source 메타데이터에서 video URL을 보조적으로 추출한다."""
    video_urls = []
    try:
        found_vids = re.findall(
            r'"video_versions":\s*\[\s*\{\s*"type":\s*\d+,\s*"width":\s*\d+,\s*"height":\s*\d+,\s*"url":\s*"(https://[^"]+)"',
            driver.page_source,
        )
        for video_url in found_vids:
            clean_url = video_url.replace("\\u0026", "&")
            if clean_url not in video_urls:
                video_urls.append(clean_url)
    except:
        pass
    return video_urls


def collect_post_media_urls(driver, main_padding_box):
    """메인 게시물 박스 안의 실제 이미지/동영상만 순서대로 수집한다."""
    media_scope = main_padding_box
    try:
        pagelet_scope = driver.find_element(
            By.XPATH,
            "//div[contains(@data-pagelet, 'threads_post_page_0')]//*[@data-pressable-container='true'][1]",
        )
        if pagelet_scope:
            media_scope = pagelet_scope
    except:
        try:
            scoped_pressable = main_padding_box.find_element(By.XPATH, ".//*[@data-pressable-container='true'][1]")
            if scoped_pressable:
                media_scope = scoped_pressable
        except:
            pass

    expand_main_carousel(driver, media_scope)

    media_items = []
    try:
        media_items = driver.execute_script(
            """
            const root = arguments[0];
            const items = [];
            const videoRects = [];

            for (const vid of root.querySelectorAll('video')) {
                const rect = vid.getBoundingClientRect();
                let src = vid.getAttribute('src') || '';
                if (!src) {
                    const source = vid.querySelector('source');
                    if (source) src = source.getAttribute('src') || '';
                }
                if (!src) continue;
                items.push({src, type: 'video', y: rect.y, x: rect.x});
                videoRects.push({y: rect.y, x: rect.x});
            }

            for (const img of root.querySelectorAll('img')) {
                const rect = img.getBoundingClientRect();
                const src = img.getAttribute('src') || '';
                const alt = (img.getAttribute('alt') || '').toLowerCase();
                if (!src) continue;
                if (!src.includes('scontent') && !src.includes('fbcdn')) continue;
                if (rect.width < 150 || rect.height < 150) continue;
                if (alt.includes('profile picture') || alt.includes('프로필 사진')) continue;

                const anchor = img.closest('a');
                const href = ((anchor && anchor.getAttribute('href')) || '').toLowerCase();
                if (href.includes('/saved') || href.includes('/search') || href.includes('/activity')) continue;
                if (/threads\\.(?:net|com)\\/@[^/]+\\/?$/.test(href)) continue;

                let isVideoThumbnail = false;
                for (const item of videoRects) {
                    if (Math.abs(item.y - rect.y) < 5 && Math.abs(item.x - rect.x) < 5) {
                        isVideoThumbnail = true;
                        break;
                    }
                }
                if (isVideoThumbnail) continue;

                const inVideoPlayer =
                    img.closest('[aria-label*="Video"],[aria-label*="video"],[aria-label*="동영상"],[aria-label*="비디오"]') !== null;
                if (inVideoPlayer) continue;

                items.push({src, type: 'image', y: rect.y, x: rect.x});
            }

            items.sort((a, b) => (a.y === b.y ? a.x - b.x : a.y - b.y));
            return items;
            """,
            media_scope,
        ) or []
    except:
        media_items = []

    collected_items = []
    seen_urls = set()
    for item in media_items:
        src = item.get("src")
        media_type = item.get("type")
        if not src or src in seen_urls:
            continue
        seen_urls.add(src)
        collected_items.append((src, media_type))

    for video_url in get_json_video_urls(driver):
        if video_url not in seen_urls:
            seen_urls.add(video_url)
            collected_items.append((video_url, "video"))

    return collected_items


def get_post_row_containers(driver):
    """
    현재 화면 종류에 맞는 포스트 row 컨테이너만 반환한다.
    저장됨 화면에서는 saved 영역만, 그 외에는 전체 가상화 row를 사용한다.
    """
    try:
        current_url = driver.current_url or ""
    except:
        current_url = ""

    try:
        if "/saved" in current_url or is_saved_list_page(driver):
            saved_rows = driver.find_elements(
                By.XPATH,
                "//div[contains(@data-pagelet, 'threads_saved_posts_')]//div[@data-virtualized]",
            )
            if saved_rows:
                return saved_rows
    except:
        pass

    return driver.find_elements(By.XPATH, "//div[@data-virtualized]")


def make_debug_run_dir(base_dir):
    debug_dir = os.path.join(base_dir, f"threads_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(debug_dir, exist_ok=True)
    return debug_dir


def append_debug_log(log_path, message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line, flush=True)
    if log_path:
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except:
            pass


def make_temp_cache_paths(output_filename):
    abs_output = os.path.abspath(output_filename)
    output_dir = os.path.dirname(abs_output) or os.getcwd()
    stem = os.path.splitext(os.path.basename(abs_output))[0]
    cache_dir = os.path.join(output_dir, f".{stem}_cache")
    rows_dir = os.path.join(cache_dir, "rows")
    os.makedirs(rows_dir, exist_ok=True)
    return {
        "cache_dir": cache_dir,
        "rows_dir": rows_dir,
        "links_path": os.path.join(cache_dir, "collected_links.json"),
    }


def write_json_cache(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_json_cache(path, default):
    if not path or not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default


def cache_links(cache_paths, links):
    write_json_cache(cache_paths["links_path"], {"links": list(links or [])})


def cache_row_result(cache_paths, row_index, row_data):
    safe_link = str((row_data or {}).get("링크", "")).strip()
    safe_link = re.sub(r"[^A-Za-z0-9._-]+", "_", safe_link)[:80] or f"row_{row_index + 1:05d}"
    row_path = os.path.join(cache_paths["rows_dir"], f"{row_index:05d}_{safe_link}.json")
    write_json_cache(
        row_path,
        {
            "source_row_index": row_index,
            "row": row_data or {},
        },
    )


def finalize_cached_results_to_excel(output_filename, cache_paths):
    cached_links = read_json_cache(cache_paths["links_path"], {}).get("links", [])
    cached_rows = []

    if os.path.isdir(cache_paths["rows_dir"]):
        for name in sorted(os.listdir(cache_paths["rows_dir"])):
            if not name.endswith(".json"):
                continue
            row_payload = read_json_cache(os.path.join(cache_paths["rows_dir"], name), {})
            if row_payload:
                cached_rows.append(row_payload)

    cached_rows.sort(key=lambda item: int(item.get("source_row_index", 0)))
    row_map = {}
    ordered_rows = []

    for item in cached_rows:
        row = dict(item.get("row") or {})
        link = str(row.get("링크", "")).strip()
        if link:
            row_map[link] = row
        ordered_rows.append(row)

    if cached_links:
        merged_rows = []
        used_links = set()
        for link in cached_links:
            link_str = str(link).strip()
            if not link_str:
                continue
            if link_str in row_map:
                merged_rows.append(row_map[link_str])
            else:
                merged_rows.append({"링크": link_str})
            used_links.add(link_str)

        for row in ordered_rows:
            link = str(row.get("링크", "")).strip()
            if link and link not in used_links:
                merged_rows.append(row)

        ordered_rows = merged_rows

    if not ordered_rows:
        return 0

    pd.DataFrame(ordered_rows).to_excel(output_filename, index=False)
    return len(ordered_rows)


def cleanup_temp_cache(cache_paths):
    cache_dir = (cache_paths or {}).get("cache_dir")
    if cache_dir and os.path.isdir(cache_dir):
        shutil.rmtree(cache_dir, ignore_errors=True)


def save_debug_snapshot(driver, debug_dir, label):
    safe_label = re.sub(r"[^A-Za-z0-9._-]+", "_", str(label or "snapshot"))
    html_path = os.path.join(debug_dir, f"{safe_label}.html")
    png_path = os.path.join(debug_dir, f"{safe_label}.png")

    try:
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(driver.page_source or "")
    except:
        html_path = ""

    try:
        driver.save_screenshot(png_path)
    except:
        png_path = ""

    return html_path, png_path


def log_page_state(driver, label, log_path=None):
    try:
        current_url = driver.current_url or ""
    except:
        current_url = ""

    try:
        title = driver.title or ""
    except:
        title = ""

    try:
        window_count = len(driver.window_handles)
    except:
        window_count = 0

    try:
        saved_pagelets = len(driver.find_elements(By.XPATH, "//div[contains(@data-pagelet, 'threads_saved_posts_')]"))
    except:
        saved_pagelets = 0

    try:
        post_pagelets = len(driver.find_elements(By.XPATH, "//div[contains(@data-pagelet, 'threads_post_page_')]"))
    except:
        post_pagelets = 0

    try:
        saved_rows = len(driver.find_elements(By.XPATH, "//div[contains(@data-pagelet, 'threads_saved_posts_')]//div[@data-virtualized]"))
    except:
        saved_rows = 0

    append_debug_log(
        log_path,
        f"[{label}] url={current_url} | title={title} | windows={window_count} | detail={is_post_detail_url(current_url)} | saved_list={is_saved_list_page(driver)} | saved_pagelets={saved_pagelets} | post_pagelets={post_pagelets} | saved_rows={saved_rows}",
    )


def create_chrome_service():
    service = Service(ChromeDriverManager().install())
    if os.getenv("MADOYO_SHOW_CHROMEDRIVER_CONSOLE") != "1":
        service.creation_flags = 0x08000000  # CREATE_NO_WINDOW
    return service


def main():
    print("\n👋 환영합니다! Threads 프로필 데이터 수집 프로그램을 시작합니다.")
    print("⏳ (※ 로딩 중 검은 창이 약 30초간 유지될 수 있습니다. 잠시만 기다려주세요.)\n")
    final_results = []
    # 결과 파일명 설정 (실시간 백업용)
    output_filename = f"threads_live_report_{datetime.now().strftime('%m%d_%H%M')}.xlsx"
    
    # --- [1. 브라우저 환경 설정] ---
    options = Options()
    options.add_experimental_option("detach", True)
    options.add_experimental_option("excludeSwitches", ["enable-logging"])  # 로그 메시지 숨김
    options.add_argument("--disable-blink-features=AutomationControlled")  # 봇 탐지 우회
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    service = create_chrome_service()
    
    driver = webdriver.Chrome(service=service, options=options)

    try:
        driver.get("https://www.threads.net/")
        print("\n🚀 [Step 1] 브라우저 로딩 완료. 로그인을 마친 후 엔터를 누르세요.")
        print("💡 [팁] 프로필 수집 시 '새 탭'으로 이동하셨다면, 마지막으로 활성화된 창을 자동으로 인식합니다.")
        input() 

        # --- 모드 선택 ---
        state = 0
        mode = '1'
        slow_mode = False
        target_hours = 0.0
        target_count = 0
        sleep_time_per_item = 0.0

        while True:
            if state == 0:
                print("\n" + "="*60)
                print("📌 수집 모드 선택")
                print("="*60)
                print("1️⃣  빠른 모드 - 최대한 빠르게 수집 (봇 탐지 위험 있음)")
                print("2️⃣  천천히 모드 - 긴 시간 동안 많은 양 수집 (봇 탐지 방지)")
                print("="*60)
                
                user_input = input("\n▶ 모드 선택 (1 또는 2): ").strip()
                if user_input in ['1', '2']:
                    mode = user_input
                    if mode == '2':
                        print("\n🌙 천천히 모드를 선택하셨습니다.")
                        print("ℹ️  순수 크롤링 시간: 개당 약 15초 소요 (페이지 로딩 + 데이터 추출 + 댓글 확인)")
                    state = 1
                else:
                    print("⚠️ 잘못된 입력입니다. 1 또는 2를 입력해주세요.")
            
            elif state == 1:
                if mode == '2':
                    user_input = input("\n▶ 목표 시간 (시간 단위, 예: 8) (이전 단계로 돌아가려면 'b' 입력): ").strip()
                    if user_input.lower() == 'b':
                        state = 0
                        continue
                    try:
                        target_hours = float(user_input)
                        state = 2
                    except ValueError:
                        print("⚠️ 잘못된 입력입니다. 숫자만 입력해주세요.")
                elif mode == '1':
                    user_input = input("\n▶ 수집 목표 게시글 개수(숫자만 입력) (이전 단계로 돌아가려면 'b' 입력): ").strip()
                    if user_input.lower() == 'b':
                        state = 0
                        continue
                    try:
                        target_count = int(user_input)
                        print(f"\n⚡ 빠른 모드로 {target_count}개 수집을 시작합니다!")
                        slow_mode = False
                        break
                    except ValueError:
                        print("⚠️ 잘못된 입력입니다. 숫자만 입력해주세요.")

            elif state == 2:
                user_input = input("▶ 목표 개수 (예: 500) (이전 단계로 돌아가려면 'b' 입력): ").strip()
                if user_input.lower() == 'b':
                    state = 1
                    continue
                try:
                    target_count = int(user_input)
                    
                    # 순수 크롤링 시간 (개당 약 15초)
                    base_time_per_item = 15
                    total_crawling_time = target_count * base_time_per_item
                    
                    # 링크 수집 시간 추정
                    estimated_link_collection_time = max(30 * 60, target_count * 3)  # 최소 30분 또는 개당 3초
                    
                    # 총 필요 시간
                    total_required_time = total_crawling_time + estimated_link_collection_time
                    
                    # 사용자가 입력한 시간 (초)
                    user_time = target_hours * 3600
                    
                    # 추가 대기 가능 시간
                    extra_time_available = user_time - total_required_time
                    
                    # 개당 추가 대기 시간
                    sleep_time_per_item = extra_time_available / target_count
                    
                    # 속도 검증 (추가 대기 시간이 음수면 불가능)
                    if sleep_time_per_item < 0:
                        required_hours = total_required_time / 3600
                        print(f"\n⚠️ 입력하신 시간이 부족합니다!")
                        print(f"   - 최소 필요 시간: {required_hours:.1f}시간")
                        print(f"   - 입력하신 시간: {target_hours}시간")
                        print(f"   시간을 다시 설정해주세요.")
                        state = 1
                    else:
                        slow_mode = True
                        total_time_per_item = base_time_per_item + sleep_time_per_item
                        
                        print(f"\n✅ 설정 완료!")
                        print(f"   - 목표: {target_hours}시간 동안 {target_count}개 수집")
                        print(f"   - 순수 크롤링 시간: {base_time_per_item}초/개")
                        print(f"   - 추가 대기 시간: {sleep_time_per_item:.1f}초/개 (±10초 랜덤)")
                        print(f"   - 총 소요 시간: {total_time_per_item:.1f}초/개")
                        
                        # 예상 종료 시간 계산
                        from datetime import timedelta
                        end_time = datetime.now() + timedelta(hours=target_hours)
                        print(f"   - 예상 종료: {end_time.strftime('%H시 %M분경')}")
                        
                        confirm = input("\n▶ 이 설정으로 진행할까요? (y 누르면 진행, b 누르면 개수 재입력): ").strip().lower()
                        if confirm == 'b':
                            state = 2
                            continue
                        else:
                            break
                        
                except ValueError:
                    print("⚠️ 잘못된 입력입니다. 숫자만 입력해주세요.")
        
        # 파일명 설정
        mode_prefix = "slow" if slow_mode else "live"
        output_filename = f"threads_{mode_prefix}_report_{datetime.now().strftime('%m%d_%H%M')}.xlsx"
        debug_dir = make_debug_run_dir(os.getcwd())
        debug_log_path = os.path.join(debug_dir, "session.log")
        append_debug_log(debug_log_path, f"디버그 아티팩트 폴더: {debug_dir}")
        print("\n[Checkpoint] 저장됨 탭을 마지막 탭에 띄우고 대상 화면을 맞춘 뒤 엔터를 누르세요.")
        input()

        # --- [Step 2] 메인 피드 링크 수집 (실시간 카운트 표시) ---
        target_links = []
        
        # [자동 창 전환] 여러 창이 열려있을 경우 마지막(최신) 창으로 포커스를 이동합니다.
        try:
            if len(driver.window_handles) > 1:
                driver.switch_to.window(driver.window_handles[-1])
        except:
            pass
        log_page_state(driver, "scan_ready", debug_log_path)
        save_debug_snapshot(driver, debug_dir, "scan_ready")

        # 현재 페이지가 특정 사용자의 프로필인지 확인
        current_url = driver.current_url
        profile_user = None
        # URL 패턴: threads.net 또는 threads.com 지원
        match = re.search(r"threads\.(?:net|com)/(@[\w\.]+)", current_url)
        if match:
            profile_user = match.group(1)
            print(f"\n👤 특정 사용자 프로필 감지됨: {profile_user}")
            print(f"👉 게시물 묶음(Thread) 중 '본문'만 수집하고 댓글/대댓글은 제외합니다.")
        else:
            print(f"\n🌐 메인 피드 또는 검색 결과 페이지로 인식됩니다.")

        print(f"\n[Step 2] 피드 스캔 시작... (목표: {target_count}개)")
        
        while len(target_links) < target_count:
            try:
                # [수정] 부모(virtualized)와 자식(pressable)을 동시에 찾으면 중복/댓글 수집이 발생합니다.
                # 최상위 '줄(Row)' 단위인 data-virtualized 속성만 찾아 그 안에서 첫 번째 링크만 가져옵니다.
                containers = get_post_row_containers(driver)
                
                for container in containers:
                    # 컨테이너 내의 첫 번째 포스트 링크만 추출 (댓글/대댓글 방지)
                    try:
                        # 컨테이너 안에서 /post/ 링크를 찾되, 첫 번째 것만 선택
                        post_anchors = container.find_elements(By.XPATH, ".//a[contains(@href, '/post/')]")
                        if not post_anchors:
                            continue
                            
                        first_post_el = post_anchors[0]
                        link = first_post_el.get_attribute('href').split('?')[0]
                        
                        # 아이디 필터링 (프로필 모드일 때만)
                        if profile_user and f"/{profile_user}/post/" not in link:
                            continue
                            
                        if link not in target_links and "/post/" in link:
                            target_links.append(link)
                            # flush=True를 추가하여 터미널에 즉시 출력되도록 보장
                            print(f"\r🔎 링크 수집 현황: [{len(target_links)}/{target_count}]", end="", flush=True)
                            
                        if len(target_links) >= target_count: break
                    except:
                        continue
                
                if len(target_links) >= target_count: break
                
                # 피드 추가 로딩을 위한 스크롤 (속도 최적화: 2s -> 0.7s)
                driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.PAGE_DOWN)
                time.sleep(0.7)
            except KeyboardInterrupt:
                print("\n🛑 링크 수집 중 사용자가 중단했습니다.")
                break
        
        print(f"\n✅ 링크 확보 완료! 총 {len(target_links)}개의 상세 분석을 시작합니다.")

        # --- [Step 3] 상세 데이터 분석 및 실시간 저장 ---
        try:
            with open(os.path.join(debug_dir, "collected_links.txt"), "w", encoding="utf-8") as f:
                f.write("\n".join(target_links))
        except:
            pass
        append_debug_log(debug_log_path, f"수집 링크 {len(target_links)}개, 샘플={target_links[:3]}")

        for i, url in enumerate(target_links):
            try:
                print(f"\n📊 [{i+1}/{len(target_links)}] 분석 중: {url}", flush=True)
                driver.get(url)
                time.sleep(6) # SPA 렌더링 대기 시간
                log_page_state(driver, f"detail_{i+1}_loaded", debug_log_path)

                current_detail_url = driver.current_url.split('?')[0]
                expected_detail_url = url.split('?')[0]
                if not is_post_detail_url(current_detail_url) or current_detail_url != expected_detail_url:
                    print(f"   ⚠️ 상세 페이지 진입 실패: {current_detail_url}", flush=True)
                    html_path, png_path = save_debug_snapshot(driver, debug_dir, f"detail_{i+1}_entry_failed")
                    append_debug_log(debug_log_path, f"[{i+1}] 진입 실패 스냅샷 html={html_path} png={png_path}")
                    continue
                if is_saved_list_page(driver):
                    print("   ⚠️ 아직 저장됨 리스트 화면에 머물러 있어 본문 추출을 건너뜁니다.", flush=True)
                    html_path, png_path = save_debug_snapshot(driver, debug_dir, f"detail_{i+1}_saved_list")
                    append_debug_log(debug_log_path, f"[{i+1}] 저장됨 화면 스냅샷 html={html_path} png={png_path}")
                    continue

                row = {
                    "링크": url, "본문": "수집실패", "본문조회수": "0", "작성시간": "0",
                    "좋아요": "0", "답글수": "0", "리포스트": "0", "공유수": "0",
                    "첫댓글조회수": "0", "크롤링시간": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }

                # [A] 본문 데이터 추출
                row["본문조회수"] = get_views_global(driver)
                
                activity_btn = driver.find_element(By.XPATH, "//span[contains(text(), '활동 보기')]")
                main_padding_box = activity_btn.find_element(By.XPATH, "./ancestor::div[contains(@style, 'padding')][1]")
                
                extracted_text = extract_post_text(main_padding_box)
                if extracted_text:
                    row["본문"] = extracted_text

                # [B] 인터랙션 수치
                row["작성시간"] = main_padding_box.find_element(By.TAG_NAME, "time").get_attribute("datetime")
                row["좋아요"] = get_metric_inside_box(main_padding_box, ["좋아요", "Like"])
                row["답글수"] = get_metric_inside_box(main_padding_box, ["답글", "Reply"])
                row["리포스트"] = get_metric_inside_box(main_padding_box, ["리포스트", "Repost"])
                row["공유수"] = get_metric_inside_box(main_padding_box, ["보내기", "공유", "Share"])

                # [C] 첫 번째 댓글 영역 탐색 (전체 본문 링크 우회 전략으로 수정됨)
                all_post_links = driver.find_elements(By.XPATH, "//a[contains(@href, '/post/')]")
                main_url_base = url.split('?')[0].replace("threads.net", "threads.com")
                first_comment_url = None
                
                for link_el in all_post_links:
                    try:
                        href = link_el.get_attribute("href")
                        if not href:
                            continue
                        href_base = href.split('?')[0].replace("threads.net", "threads.com")
                        if href_base != main_url_base:
                            first_comment_url = href
                            break
                    except:
                        continue
                
                if first_comment_url:
                    driver.get(first_comment_url)
                    time.sleep(5)
                    row["첫댓글조회수"] = get_views_global(driver)
                
                final_results.append(row)

                # --- [실시간 저장] ---
                # 데이터가 추가될 때마다 즉시 엑셀 파일 갱신
                pd.DataFrame(final_results).to_excel(output_filename, index=False)
                print(f"   💾 실시간 저장 완료 (현재 {len(final_results)}개 보관 중)", flush=True)

                # --- [천천히 모드: Sleep Time 적용] ---
                if slow_mode:
                    # 50개마다 장기 휴식 (Tea Time)
                    if (i + 1) % 50 == 0:
                        long_break = random.uniform(180, 300)  # 3분~5분 휴식
                        print(f"\n☕ [휴식] 403 방지를 위해 {long_break:.1f}초 동안 쉬어갑니다...", flush=True)
                        time.sleep(long_break)
                    else:
                        # 추가 대기 시간 (±10초 랜덤)
                        sleep_min = float(sleep_time_per_item) - 10.0
                        sleep_max = float(sleep_time_per_item) + 10.0
                        actual_sleep = max(0.0, random.uniform(sleep_min, sleep_max))
                        print(f"   💤 안전 대기: {actual_sleep:.1f}초", flush=True)
                        time.sleep(actual_sleep)

            except KeyboardInterrupt:
                print(f"\n🛑 사용자가 중단했습니다. 현재까지 수집된 {len(final_results)}개를 저장합니다.")
                break
            except Exception as e:
                print(f"   ⚠️ 오류 발생(스킵): {e}")
                continue

    except Exception as e:
        print(f"\n❌ 시스템 치명적 오류: {traceback.format_exc()}")
    
    finally:
        # 최종 마감 저장 및 정리
        if final_results:
            pd.DataFrame(final_results).to_excel(output_filename, index=False)
            print(f"\n✅ 수집 완료! 파일 경로: {os.path.abspath(output_filename)}")
        else:
            print("\nℹ️ 저장된 데이터가 없습니다.")
        
        try:
            driver.quit()
        except:
            pass

import customtkinter as ctk
import threading
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
import re
import sys
import time
from datetime import datetime
import pandas as pd
import random
import traceback
import os
import hashlib
import httpx
from tkinter import filedialog


ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class TextboxRedirector:
    """ redirect sys.stdout to a CTkTextbox """
    def __init__(self, textbox):
        self.textbox = textbox

    def write(self, string):
        self.textbox.insert(ctk.END, string)
        self.textbox.see(ctk.END)

    def flush(self):
        # UI 강제 새로고침을 통해 바로바로 텍스트가 표시되도록 함
        self.textbox.update_idletasks()

class ThreadsCrawlerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Threads Profile Collector")
        self.geometry("600x780")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.on_window_close)
        
        self.driver = None
        self.save_images_var = ctk.BooleanVar(value=True) # 기본 이미지 저장 활성화
        
        # --- 추가된 경로 변수 ---
        self.excel_dir_var = ctk.StringVar(value=os.getcwd())
        self.media_dir_var = ctk.StringVar(value=os.path.join(os.getcwd(), "downloaded_files"))
        
        # 타이머 및 상태 변수
        self.current_phase = 0 # 0: 대기, 1: 링크수집, 2: 크롤링
        self.link_start_time = None
        self.crawl_start_time = None
        self.link_elapsed = 0
        self.crawl_elapsed = 0
        self.stop_requested = False
        self.active_output_filename = ""
        self.active_cache_paths = None

        # --- 1페이지: Welcome Frame ---
        self.welcome_frame = ctk.CTkFrame(self, corner_radius=15)
        self.welcome_frame.pack(pady=30, padx=40, fill="both", expand=True)

        self.title_label = ctk.CTkLabel(
            self.welcome_frame, 
            text="👋 환영합니다!", 
            font=ctk.CTkFont(family="Malgun Gothic", size=28, weight="bold")
        )
        self.title_label.pack(pady=(120, 15)) # 상단 여백을 늘려 중앙으로 이동

        self.subtitle_label = ctk.CTkLabel(
            self.welcome_frame, 
            text="스레드 프로필 데이터 수집 프로그램입니다.\n수집을 원하시면 아래 버튼을 클릭해주세요.", 
            font=ctk.CTkFont(family="Malgun Gothic", size=14),
            text_color="gray",
            justify="center"
        )
        self.subtitle_label.pack(pady=(0, 50))

        self.start_button = ctk.CTkButton(
            self.welcome_frame, 
            text="🚀 수집 시작하기", 
            font=ctk.CTkFont(family="Malgun Gothic", size=16, weight="bold"),
            height=50,
            width=220,
            corner_radius=8,
            command=self.on_start_click
        )
        self.start_button.pack(pady=10)
        
        self.status_label = ctk.CTkLabel(
            self.welcome_frame,
            text="",
            font=ctk.CTkFont(family="Malgun Gothic", size=13),
            text_color="#F6C85F"
        )
        self.status_label.pack(pady=10)
        
        # --- 2페이지: Settings Frame ---
        self.settings_frame = ctk.CTkFrame(self, corner_radius=15)
        
        # [상단 헤더 (도움말)]
        self.header_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=20, pady=(15, 0))
        
        self.help_btn = ctk.CTkButton(
            self.header_frame, text="도움말", 
            width=80, height=30, fg_color="#1E90FF", hover_color="#1874CD",
            font=ctk.CTkFont(family="Malgun Gothic", size=12, weight="bold"),
            command=self.show_help
        )
        self.help_btn.pack(side="right")
        
        # [안내 사항]
        self.inst_label1 = ctk.CTkLabel(
            self.settings_frame, 
            text="1. 실행된 크롬 창에서 로그인을 완료해주세요.", 
            font=ctk.CTkFont(family="Malgun Gothic", size=15, weight="bold")
        )
        self.inst_label1.pack(pady=(20, 5), anchor="w", padx=30)
        
        self.inst_label2 = ctk.CTkLabel(
            self.settings_frame, 
            text="팁: 프로필 수집 시 '새 탭'으로 이동하셨다면, 마지막 창을 자동 인식합니다.", 
            font=ctk.CTkFont(family="Malgun Gothic", size=12), 
            text_color="gray"
        )
        self.inst_label2.pack(pady=(0, 20), anchor="w", padx=30)
        
        # [모드 선택: 라디오 및 옵션]
        self.mode_var = ctk.StringVar(value="fast")
        
        self.mode_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.mode_frame.pack(fill="x", padx=30, pady=5)
        
        self.fast_radio = ctk.CTkRadioButton(
            self.mode_frame, text="빠른 모드 (봇 탐지 위험)", 
            variable=self.mode_var, value="fast", command=self.on_mode_change,
            font=ctk.CTkFont(family="Malgun Gothic", size=13)
        )
        self.fast_radio.pack(side="left", padx=(0, 20))
        
        self.slow_radio = ctk.CTkRadioButton(
            self.mode_frame, text="느린 모드 (안전)", 
            variable=self.mode_var, value="slow", command=self.on_mode_change,
            font=ctk.CTkFont(family="Malgun Gothic", size=13)
        )
        self.slow_radio.pack(side="left")
        self.link_only_radio = ctk.CTkRadioButton(
            self.mode_frame,
            text="링크만 수집",
            variable=self.mode_var,
            value="link_only",
            command=self.on_mode_change,
            font=ctk.CTkFont(family="Malgun Gothic", size=13),
        )
        self.link_only_radio.pack(side="left", padx=(20, 0))
        

        # [입력 폼]
        self.input_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.input_frame.pack(fill="x", padx=30, pady=15)
        
        # Grid 설정
        self.input_frame.columnconfigure(0, weight=1)
        self.input_frame.columnconfigure(1, weight=3)
        
        self.count_label = ctk.CTkLabel(self.input_frame, text="목표 개수:", font=ctk.CTkFont(family="Malgun Gothic", size=13, weight="bold"))
        self.count_label.grid(row=0, column=0, pady=10, sticky="w")
        self.count_entry = ctk.CTkEntry(self.input_frame, placeholder_text="예: 500")
        self.count_entry.grid(row=0, column=1, pady=10, sticky="ew")
        
        # 목표 시간 입력창 및 더미 컨테이너 박스 생성
        self.time_container = ctk.CTkFrame(self.input_frame, fg_color="transparent")
        self.time_container.grid(row=1, column=0, columnspan=2, sticky="ew")
        
        self.time_container.columnconfigure(0, weight=1)
        self.time_container.columnconfigure(1, weight=3)
        self.time_container.grid_propagate(False) # 자식 크기에 맞게 자동 조절되는 것을 방지
        self.time_container.configure(height=48)  # 입력창 고정 높이 할당
        
        self.time_label = ctk.CTkLabel(self.time_container, text="목표 시간(시간):", font=ctk.CTkFont(family="Malgun Gothic", size=13, weight="bold"))
        self.time_entry = ctk.CTkEntry(self.time_container, placeholder_text="예: 8 (느린 모드 전용)")
        
        self.time_label.grid_remove()
        self.time_entry.grid_remove()
        
        # [이미지 저장 옵션 프레임 (프로필 검증 위로 이동)]
        self.media_option_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.media_option_frame.pack(fill="x", padx=30, pady=(10, 0))
        
        self.image_save_check = ctk.CTkCheckBox(
            self.media_option_frame, text="📸 이미지 및 미디어 로컬 저장 (MD5 해시 파일명)", 
            variable=self.save_images_var,
            font=ctk.CTkFont(family="Malgun Gothic", size=13, weight="bold")
        )
        self.image_save_check.pack(side="left")
        
        # [저장 경로 설정 섹션 추가]
        self.path_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.path_frame.pack(fill="x", padx=30, pady=(15, 0))
        
        self.path_frame.columnconfigure(0, weight=1)
        self.path_frame.columnconfigure(1, weight=3)
        self.path_frame.columnconfigure(2, weight=0)

        # Excel 경로
        self.excel_path_label = ctk.CTkLabel(self.path_frame, text="엑셀 저장 폴더:", font=ctk.CTkFont(family="Malgun Gothic", size=13, weight="bold"))
        self.excel_path_label.grid(row=0, column=0, pady=5, sticky="w")
        self.excel_path_entry = ctk.CTkEntry(self.path_frame, textvariable=self.excel_dir_var)
        self.excel_path_entry.grid(row=0, column=1, pady=5, padx=(5, 5), sticky="ew")
        self.excel_path_btn = ctk.CTkButton(self.path_frame, text="찾기", width=60, command=self.select_excel_dir)
        self.excel_path_btn.grid(row=0, column=2, pady=5, sticky="e")

        # Media 경로
        self.media_path_label = ctk.CTkLabel(self.path_frame, text="미디어 저장 폴더:", font=ctk.CTkFont(family="Malgun Gothic", size=13, weight="bold"))
        self.media_path_label.grid(row=1, column=0, pady=5, sticky="w")
        self.media_path_entry = ctk.CTkEntry(self.path_frame, textvariable=self.media_dir_var)
        self.media_path_entry.grid(row=1, column=1, pady=5, padx=(5, 5), sticky="ew")
        self.media_path_btn = ctk.CTkButton(self.path_frame, text="찾기", width=60, command=self.select_media_dir)
        self.media_path_btn.grid(row=1, column=2, pady=5, sticky="e")
        
        # [프로필 검증]
        self.verify_frame = ctk.CTkFrame(self.settings_frame, corner_radius=8)
        self.verify_frame.pack(fill="x", padx=30, pady=15)
        
        self.verify_btn = ctk.CTkButton(
            self.verify_frame, text="🔍 프로필 검증", 
            font=ctk.CTkFont(family="Malgun Gothic", size=13, weight="bold"),
            command=self.verify_profile,
            width=120
        )
        self.verify_btn.pack(side="left", padx=15, pady=15)
        
        self.verify_label = ctk.CTkLabel(
            self.verify_frame, text="아직 검증되지 않았습니다.", 
            text_color="gray", font=ctk.CTkFont(family="Malgun Gothic", size=13)
        )
        self.verify_label.pack(side="left", padx=(0, 15), pady=15)
        
        # [다음 버튼]
        self.next_btn = ctk.CTkButton(
            self.settings_frame, text="다음 (Next)", 
            font=ctk.CTkFont(family="Malgun Gothic", size=16, weight="bold"),
            height=45, width=200,
            command=self.on_next_click
        )
        self.next_btn.pack(pady=(15, 20))

        # --- 3페이지: Crawling Execution Frame ---
        self.crawling_frame = ctk.CTkFrame(self, corner_radius=15)
        
        self.crawl_title = ctk.CTkLabel(
            self.crawling_frame, 
            text="🚀 크롤링 진행 중...", 
            font=ctk.CTkFont(family="Malgun Gothic", size=24, weight="bold")
        )
        self.crawl_title.pack(pady=(20, 10))
        self.stop_btn = ctk.CTkButton(
            self.crawling_frame,
            text="중단 후 엑셀 정리",
            font=ctk.CTkFont(family="Malgun Gothic", size=13, weight="bold"),
            fg_color="#B23A48",
            hover_color="#8F2632",
            width=180,
            command=self.request_stop,
        )
        self.stop_btn.pack(pady=(0, 10))

        # [진행 상태 패널 - 1단계: 링크 수집]
        self.phase1_panel = ctk.CTkFrame(self.crawling_frame, fg_color="transparent")
        self.phase1_panel.pack(fill="x", padx=30, pady=(10, 0))
        
        self.p1_label = ctk.CTkLabel(self.phase1_panel, text="1단계: 링크 수집 중...", font=ctk.CTkFont(family="Malgun Gothic", size=15, weight="bold"))
        self.p1_label.pack(anchor="w", pady=(0, 5))
        
        # 파란색 프로필 바
        self.p1_progress_bar = ctk.CTkProgressBar(self.phase1_panel, height=20, corner_radius=10, progress_color="#1E90FF")
        self.p1_progress_bar.pack(fill="x", pady=(0, 5))
        self.p1_progress_bar.set(0)
        
        self.p1_count_label = ctk.CTkLabel(self.phase1_panel, text="수집 현황: (0 / 0)", font=ctk.CTkFont(family="Malgun Gothic", size=13))
        self.p1_count_label.pack(side="left")

        # [진행 상태 패널 - 2단계: 데이터 크롤링]
        self.phase2_panel = ctk.CTkFrame(self.crawling_frame, fg_color="transparent")
        # 초기에는 숨김 처리
        self.phase2_panel.pack(fill="x", padx=30, pady=(10, 0))
        self.phase2_panel.pack_forget()
        
        self.p2_label = ctk.CTkLabel(self.phase2_panel, text="2단계: 데이터 크롤링 중...", font=ctk.CTkFont(family="Malgun Gothic", size=15, weight="bold"))
        self.p2_label.pack(anchor="w", pady=(0, 5))
        
        # 초록색 프로필 바
        self.p2_progress_bar = ctk.CTkProgressBar(self.phase2_panel, height=20, corner_radius=10, progress_color="#2E8B57")
        self.p2_progress_bar.pack(fill="x", pady=(0, 5))
        self.p2_progress_bar.set(0)
        
        self.p2_count_label = ctk.CTkLabel(self.phase2_panel, text="통신 현황: (0 / 0)", font=ctk.CTkFont(family="Malgun Gothic", size=13))
        self.p2_count_label.pack(side="left")

        # [타이머 통합 패널]
        self.timer_panel = ctk.CTkFrame(self.crawling_frame, fg_color="transparent")
        self.timer_panel.pack(fill="x", padx=30, pady=10)
        
        self.link_timer_label = ctk.CTkLabel(
            self.timer_panel, text="링크 수집 소요시간: 00:00:00", 
            font=ctk.CTkFont(family="Malgun Gothic", size=13, weight="bold"),
            text_color="#F6C85F"
        )
        self.link_timer_label.pack(side="left")
        
        self.crawl_timer_label = ctk.CTkLabel(
            self.timer_panel, text="크롤링 소요시간: 대기 중...", 
            font=ctk.CTkFont(family="Malgun Gothic", size=13, weight="bold"),
            text_color="#F6C85F"
        )
        self.crawl_timer_label.pack(side="right")
        
        # 구분선
        self.separator = ctk.CTkFrame(self.crawling_frame, height=2, fg_color="gray30")
        self.separator.pack(fill="x", padx=20, pady=(10, 5))
        
        # [터미널 텍스트 박스 (로그 뷰어)]
        self.log_textbox = ctk.CTkTextbox(
            self.crawling_frame, 
            wrap="word", 
            font=ctk.CTkFont(family="Consolas", size=13),
            fg_color="#1E1E1E", # 터미널스러운 어두운 배경
            text_color="#CCCCCC"
        )
        self.log_textbox.pack(fill="both", expand=True, padx=20, pady=(10, 20))
        
        # 표준 출력(print)을 텍스트박스로 리다이렉트
        # sys.stdout = TextboxRedirector(self.log_textbox) 
        # (실제 크롤링 넘어갈 때만 활성화할 수도 있습니다. 우선 주석 해제하여 활성화)
        sys.stdout = TextboxRedirector(self.log_textbox)
        
    def show_help(self):
        # 도움말 새 창 열기
        help_window = ctk.CTkToplevel(self)
        help_window.title("사용 가이드 및 도움말")
        help_window.geometry("550x450")
        help_window.attributes("-topmost", True)  # 항상 위
        help_window.resizable(False, False)
        
        help_title = ctk.CTkLabel(
            help_window, 
            text="💡 안전한 데이터 수집을 위한 가이드", 
            font=ctk.CTkFont(family="Malgun Gothic", size=18, weight="bold")
        )
        help_title.pack(pady=(20, 10))
        
        # 스크롤 가능한 텍스트 박스 사용
        help_textbox = ctk.CTkTextbox(
            help_window, 
            wrap="word",
            font=ctk.CTkFont(family="Malgun Gothic", size=13),
            fg_color="#2A2D2E"
        )
        help_textbox.pack(padx=20, pady=(0, 20), fill="both", expand=True)
        
        help_text = """
1️⃣ 크롤링 중에는 크롬 창을 조작하지 마세요!
수집(크롤링) 프로세스가 시작되면, 프로그램이 크롬 브라우저를 직접 조종하여 화면을 스크롤하고 데이터를 추출합니다. 이때 마우스로 창을 클릭하거나 다른 페이지로 이동하면 수집의 흐름이 끊기거나 에러가 발생할 수 있습니다. 수집이 끝날 때까지 브라우저는 가만히 두시는 것이 가장 안전합니다!

2️⃣ '느린 모드'는 왜 필요한가요?
짧은 시간 안에 너무 많은 글을 수집하면, 서버 측에서 봇(Bot)으로 의심하여 '요청이 너무 많습니다 (429 에러)' 차단을 걸게 됩니다.
느린 모드는 수면 시간 등 장시간 동안 컴퓨터를 켜두고 대량의 데이터를 수집할 때 사용합니다. 정해진 '목표 시간'에 맞춰 프로그램이 알아서 수집 중간중간 긴 휴식 시간을 가지며, 사람처럼 자연스럽게 행동하여 차단을 완벽하게 방지해 줍니다.

3️⃣ 특정 프로필의 피드만 수집하는 꿀팁!
첫 번째 화면에서 [시작하기]를 누르면 열리는 크롬 창에서, 그냥 평소처럼 원하시는 프로필 페이지로 들어가시면 됩니다. 
그리고 그 프로필의 주소(URL)를 복사한 뒤, 크롬 브라우저 상단에서 '+' 버튼을 눌러 **'새 탭'을 띄우고 그곳에 방금 복사한 주소를 똑같이 붙여넣기** 하세요.
프로그램은 항상 '가장 마지막에 열려있는 화면(새 탭)'을 우선적으로 감지하므로, 이렇게 새 탭에 프로필을 띄워두시면 굳이 프로그램 내에서 프로필 검증 버튼을 누르지 않아도 완벽하게 해당 사람의 글만 쏙쏙 수집합니다. (기존 탭은 닫지 말고 그대로 두시면 됩니다!)
"""
        help_textbox.insert("1.0", help_text.strip())
        help_textbox.configure(state="disabled") # 읽기 전용으로 설정

    def request_stop(self):
        if self.current_phase not in (1, 2):
            return
        self.stop_requested = True
        print("\n🛑 중단 요청을 받았습니다. 현재까지의 캐시를 정리해 엑셀로 마감합니다.")

    def on_window_close(self):
        if self.current_phase in (1, 2):
            self.request_stop()
            self.after(500, self._wait_for_shutdown)
            return
        try:
            if self.driver:
                self.driver.quit()
        except:
            pass
        self.destroy()

    def _wait_for_shutdown(self):
        if self.current_phase in (1, 2):
            self.after(500, self._wait_for_shutdown)
            return
        self.destroy()

    def on_mode_change(self):
        if self.mode_var.get() == "slow":
            self.time_label.grid(row=0, column=0, pady=10, sticky="w")
            self.time_entry.grid(row=0, column=1, pady=10, sticky="ew")
        else:
            self.time_label.grid_remove()
            self.time_entry.grid_remove()
            
    def launch_browser_thread(self):
        # 2페이지 전환 시 크롬 실행 (UI 멈춤 방지를 위해 스레드 사용)
        try:
            options = Options()
            options.add_experimental_option("detach", True)
            options.add_experimental_option("excludeSwitches", ["enable-logging"])
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            
            service = create_chrome_service()
            
            self.driver = webdriver.Chrome(service=service, options=options)
            self.driver.get("https://www.threads.net/")
        except Exception as e:
            print(f"브라우저 실행 오류: {e}")

    def on_start_click(self):
        # 1페이지 숨기고 2페이지 표시
        self.welcome_frame.pack_forget()
        self.settings_frame.pack(pady=20, padx=30, fill="both", expand=True)
        
        # 브라우저 백그라운드 실행
        threading.Thread(target=self.launch_browser_thread, daemon=True).start()

    def verify_profile(self):
        if not self.driver:
            self.verify_label.configure(text="❌ 브라우저가 아직 로딩되지 않았습니다.", text_color="#FF6B6B")
            return
            
        try:
            # 마지막 창으로 포커스
            if len(self.driver.window_handles) > 1:
                self.driver.switch_to.window(self.driver.window_handles[-1])
            
            current_url = self.driver.current_url
            saved_pagelets = len(self.driver.find_elements(By.XPATH, "//div[contains(@data-pagelet, 'threads_saved_posts_')]"))
            feed_pagelets = len(self.driver.find_elements(By.XPATH, "//div[contains(@data-pagelet, 'threads_feed_')]"))

            if "/saved" in current_url or saved_pagelets > 0:
                if feed_pagelets > 0 or "/for_you" in current_url:
                    self.verify_label.configure(
                        text="게시글이 섞일 수 있습니다. 새탭에서 보기를 진행해주세요!",
                        text_color="#FF6B6B",
                    )
                else:
                    self.verify_label.configure(text="저장됨 탭입니다", text_color="#51CF66")
                return

            match = re.search(r"threads\.(?:net|com)/(@[\w\.]+)", current_url)
            
            if match:
                profile_user = match.group(1)
                self.verify_label.configure(text=f"✅ 감지됨: {profile_user}", text_color="#51CF66")
            else:
                self.verify_label.configure(text="❌ 프로필이 검색되지 않았습니다.", text_color="#FCC419")
        except Exception as e:
            self.verify_label.configure(text=f"❌ 검증 중 오류 발생", text_color="#FF6B6B")
            
    def select_excel_dir(self):
        selected = filedialog.askdirectory()
        if selected:
            self.excel_dir_var.set(selected)

    def select_media_dir(self):
        selected = filedialog.askdirectory()
        if selected:
            self.media_dir_var.set(selected)
            
    def update_timer(self):
        if self.current_phase == 1 and self.link_start_time:
            self.link_elapsed = int(time.time() - self.link_start_time)
            h = self.link_elapsed // 3600
            m = (self.link_elapsed % 3600) // 60
            s = self.link_elapsed % 60
            self.link_timer_label.configure(text=f"링크 수집 소요시간: {h:02d}:{m:02d}:{s:02d}")
            self.after(500, self.update_timer)
            
        elif self.current_phase == 2 and self.crawl_start_time:
            self.crawl_elapsed = int(time.time() - self.crawl_start_time)
            h = self.crawl_elapsed // 3600
            m = (self.crawl_elapsed % 3600) // 60
            s = self.crawl_elapsed % 60
            self.crawl_timer_label.configure(text=f"크롤링 소요시간: {h:02d}:{m:02d}:{s:02d}")
            self.after(500, self.update_timer)

    def _legacy_real_crawling_process(self, target_count, slow_mode, target_hours):
        try:
            sleep_time_per_item = 0.0
            if slow_mode:
                base_time_per_item = 15
                total_crawling_time = target_count * base_time_per_item
                estimated_link_collection_time = max(30 * 60, target_count * 3)
                total_required_time = total_crawling_time + estimated_link_collection_time
                user_time = target_hours * 3600
                extra_time_available = user_time - total_required_time
                sleep_time_per_item = extra_time_available / target_count
                
                if sleep_time_per_item < 0:
                    print(f"⚠️ 입력하신 시간이 부족합니다! 최소 조절 후 빠른모드로 강제 전환됩니다.")
                    slow_mode = False
                else:
                    print(f"✅ 느린 모드 설정 완료 (개당 추가 대기: {sleep_time_per_item:.1f}초)")

            mode_prefix = "slow" if slow_mode else "live"
            
            # 사용자가 지정한 경로 사용
            excel_dir = self.excel_dir_var.get()
            media_dir = self.media_dir_var.get()
            
            output_filename = os.path.join(excel_dir, f"threads_{mode_prefix}_report_{datetime.now().strftime('%m%d_%H%M')}.xlsx")
            debug_dir = make_debug_run_dir(excel_dir)
            debug_log_path = os.path.join(debug_dir, "session.log")
            append_debug_log(debug_log_path, f"디버그 아티팩트 폴더: {debug_dir}")
            
            # 이미지 폴더 생성
            if not os.path.exists(media_dir):
                os.makedirs(media_dir)

            final_results = []
            target_links = []
            
            # --- [Step 2] 1단계: 링크 수집 ---
            self.current_phase = 1
            self.link_start_time = time.time()
            self.update_timer()

            if not self.driver:
                print("❌ 브라우저가 연결되지 않았습니다.")
                self.current_phase = 0
                return

            try:
                if len(self.driver.window_handles) > 1:
                    self.driver.switch_to.window(self.driver.window_handles[-1])
            except: pass
            log_page_state(self.driver, "scan_ready", debug_log_path)
            save_debug_snapshot(self.driver, debug_dir, "scan_ready")

            current_url = self.driver.current_url
            profile_user = None
            match = re.search(r"threads\.(?:net|com)/(@[\w\.]+)", current_url)
            if match:
                profile_user = match.group(1)
                print(f"\n👤 특정 사용자 프로필 감지됨: {profile_user}")
            else:
                print(f"\n🌐 메인 피드/검색 결과 페이지로 인식됨")

            print("[Step 2] 피드 스캔 시작...")
            while len(target_links) < target_count:
                if self.current_phase != 1: return # 중단 처리
                try:
                    containers = get_post_row_containers(self.driver)
                    for container in containers:
                        try:
                            post_anchors = container.find_elements(By.XPATH, ".//a[contains(@href, '/post/')]")
                            if not post_anchors: continue
                            
                            link = post_anchors[0].get_attribute('href').split('?')[0]
                            if profile_user and f"/{profile_user}/post/" not in link: continue
                            
                            if link not in target_links and "/post/" in link:
                                target_links.append(link)
                                # UI 업데이트
                                self.p1_count_label.configure(text=f"수집 현황: ({len(target_links)} / {target_count})")
                                self.p1_progress_bar.set(float(len(target_links)) / max(1, target_count))
                                print(f"🔎 링크 수집 현황: [{len(target_links)}/{target_count}]")
                            if len(target_links) >= target_count: break
                        except: continue
                    
                    if len(target_links) >= target_count: break
                    self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.PAGE_DOWN)
                    time.sleep(0.7)
                except Exception as e:
                    print(f"⚠️ 링크 수집 중 오류: {e}")
                    break
                    
            print(f"\n✅ 링크 확보 완료! 총 {len(target_links)}개 수집됨")
            try:
                with open(os.path.join(debug_dir, "collected_links.txt"), "w", encoding="utf-8") as f:
                    f.write("\n".join(target_links))
            except:
                pass
            append_debug_log(debug_log_path, f"수집 링크 {len(target_links)}개, 샘플={target_links[:3]}")
            if len(target_links) == 0:
                print("⚠️ 수집된 링크가 없습니다. 크롤링을 종료합니다.")
                self.current_phase = 0
                return
                
            # 페이즈 전환 (UI 스왑)
            self.current_phase = 2
            self.phase1_panel.pack_forget()
            self.phase2_panel.pack(fill="x", padx=30, pady=(10, 0), before=self.timer_panel)
            self.crawl_start_time = time.time()
            self.update_timer()

            # --- [Step 3] 2단계: 본문 크롤링 ---
            print("\n[Step 3] 상세 데이터 분석 시작...")
            for i, url in enumerate(target_links):
                if self.current_phase != 2: break
                try:
                    print(f"\n📊 [{i+1}/{len(target_links)}] 분석 중: {url}")
                    self.driver.get(url)
                    time.sleep(6) # SPA 대기
                    log_page_state(self.driver, f"detail_{i+1}_loaded", debug_log_path)

                    log_page_state(self.driver, f"detail_{i+1}_loaded", debug_log_path)
                    current_detail_url = self.driver.current_url.split('?')[0]
                    expected_detail_url = url.split('?')[0]
                    if not is_post_detail_url(current_detail_url) or current_detail_url != expected_detail_url:
                        print(f"   ⚠️ 상세 페이지 진입 실패: {current_detail_url}")
                        html_path, png_path = save_debug_snapshot(self.driver, debug_dir, f"detail_{i+1}_entry_failed")
                        append_debug_log(debug_log_path, f"[{i+1}] 진입 실패 스냅샷 html={html_path} png={png_path}")
                        continue
                    if is_saved_list_page(self.driver):
                        print("   ⚠️ 아직 저장됨 리스트 화면에 머물러 있어 본문 추출을 건너뜁니다.")
                        html_path, png_path = save_debug_snapshot(self.driver, debug_dir, f"detail_{i+1}_saved_list")
                        append_debug_log(debug_log_path, f"[{i+1}] 저장됨 화면 스냅샷 html={html_path} png={png_path}")
                        continue
                    
                    row = {
                        "링크": url, "본문": "수집실패", "본문조회수": "0", "작성시간": "0",
                        "좋아요": "0", "답글수": "0", "리포스트": "0", "공유수": "0",
                        "첫댓글조회수": "0", "미디어_해시값": "", "크롤링시간": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    
                    row["본문조회수"] = get_views_global(self.driver)
                    try:
                        # 앵커(Anchor) 탐색 알고리즘 고도화
                        main_padding_box = None
                        
                        # [1순위] 불변의 'Time' 태그 기반 탐색 (가장 안정적)
                        try:
                            time_el = self.driver.find_element(By.TAG_NAME, "time")
                            main_padding_box = time_el.find_element(By.XPATH, "./ancestor::div[contains(@style, 'padding')][1]")
                        except: pass
                        
                        # [2순위] '활동 보기' 버튼 기반 (기존 로직 유지하지만 2순위로 밀림)
                        if not main_padding_box:
                            try:
                                activity_btn = self.driver.find_element(By.XPATH, "//span[contains(text(), '활동 보기') or contains(text(), 'getActivity')]")
                                main_padding_box = activity_btn.find_element(By.XPATH, "./ancestor::div[contains(@style, 'padding')][1]")
                            except: pass
                            
                        # [3순위] Article 태그 기반 (표준 시맨틱 태그)
                        if not main_padding_box:
                            try:
                                main_padding_box = self.driver.find_element(By.TAG_NAME, "article")
                            except: pass

                        if not main_padding_box:
                            raise Exception("본문 컨테이너(padding_box) 포착 실패")

                        extracted_text = extract_post_text(main_padding_box)
                        if extracted_text:
                            row["본문"] = extracted_text
                            
                        # 시간 데이터 추출
                        try:
                            row["작성시간"] = main_padding_box.find_element(By.TAG_NAME, "time").get_attribute("datetime")
                        except: pass
                        
                        # 메트릭 데이터 추출 (다국어 지원)
                        row["좋아요"] = get_metric_inside_box(main_padding_box, ["좋아요", "Like"])
                        row["답글수"] = get_metric_inside_box(main_padding_box, ["답글", "Reply"])
                        row["리포스트"] = get_metric_inside_box(main_padding_box, ["리포스트", "Repost"])
                        row["공유수"] = get_metric_inside_box(main_padding_box, ["보내기", "공유", "Share"])
                        
                        # --- [게시물별 폴더 기반 미디어 수집 로직] ---
                        # 페이지 이동(댓글로 get) 전에 실행해야 StaleElementReferenceException 안 터짐
                        if self.save_images_var.get():
                            try:
                                print(f"   🖼️ 미디어(이미지/영상) 수집 중...", flush=True)
                                post_id = url.split("/post/")[1].split("?")[0]
                                post_media_dir = os.path.join(media_dir, post_id)
                                
                                if not os.path.exists(post_media_dir):
                                    os.makedirs(post_media_dir)

                                collected_items = collect_post_media_urls(self.driver, main_padding_box)
                                
                                # 중복 제거 및 최대 10개 (순서 보존)
                                seen_urls = set()
                                unique_items = []
                                for m_url, m_type in collected_items:
                                    if m_url not in seen_urls:
                                        seen_urls.add(m_url)
                                        unique_items.append((m_url, m_type))
                                unique_items = unique_items[:10]
                                
                                saved_count = 0
                                for idx, (m_url, m_type) in enumerate(unique_items):
                                    # 선제적으로 Content-Type 체크 (확장자 결정)
                                    with httpx.Client() as client:
                                        try:
                                            resp = client.get(m_url, timeout=10)
                                            if resp.status_code == 200:
                                                content_type = resp.headers.get("Content-Type", "")
                                                ext = ".mp4" if "video" in content_type else ".jpg"
                                                
                                                # 순번 기반 파일명 (01.jpg, 02.mp4 등)
                                                filename = f"{idx+1:02d}{ext}"
                                                save_path = os.path.join(post_media_dir, filename)
                                                
                                                with open(save_path, "wb") as f:
                                                    f.write(resp.content)
                                                saved_count += 1
                                        except Exception as e:
                                            print(f"     ⚠️ 다운로드 실패 ({m_url[:30]}...): {e}")
                                
                                row["미디어_해시값"] = post_id # 엑셀에는 폴더명(게시물ID) 저장
                                print(f"   ✅ 미디어 {saved_count}개 저장 완료 (폴더: {post_id})", flush=True)
                            except Exception as img_e:
                                print(f"   ⚠️ 미디어 수집 실패: {img_e}")

                        # [C] 첫 번째 댓글 영역 탐색 (페이지 내 모든 /post/ 링크 중 본문과 다른 첫 번째 링크 찾기)
                        all_post_links = self.driver.find_elements(By.XPATH, "//a[contains(@href, '/post/')]")
                        main_url_base = url.split('?')[0].replace("threads.net", "threads.com")
                        first_comment_url = None
                        
                        for link_el in all_post_links:
                            try:
                                href = link_el.get_attribute("href")
                                if not href: continue
                                href_base = href.split('?')[0].replace("threads.net", "threads.com")
                                if href_base != main_url_base:
                                    first_comment_url = href
                                    break
                            except:
                                continue
                                
                        if first_comment_url:
                            self.driver.get(first_comment_url)
                            time.sleep(5)
                            row["첫댓글조회수"] = get_views_global(self.driver)

                    except Exception as e:
                        print(f"   ⚠️ 세부 추출 오류: {e}")
                        
                    final_results.append(row)
                    pd.DataFrame(final_results).to_excel(output_filename, index=False)
                    print(f"   💾 실시간 저장 완료 ({len(final_results)}개)")
                    
                    self.p2_count_label.configure(text=f"통신 현황: ({i+1} / {len(target_links)})")
                    self.p2_progress_bar.set(float(i+1) / max(1, len(target_links)))
                    
                    if slow_mode:
                        if (i + 1) % 50 == 0:
                            break_sec = random.uniform(180, 300)
                            print(f"\n☕ [휴식] 403 방지를 위해 {break_sec:.1f}초 대기...")
                            time.sleep(break_sec)
                        else:
                            actual_sleep = max(0.0, float(sleep_time_per_item) + random.uniform(-10, 10))
                            print(f"   💤 안전 대기: {actual_sleep:.1f}초")
                            if actual_sleep > 0: time.sleep(actual_sleep)
                            
                except Exception as e:
                    print(f"   ⚠️ 오류 발생(스킵): {e}")
                    
            print(f"\n✅ 모든 수집 완료! 파일: {os.path.abspath(output_filename)}")
            
        except Exception as e:
            print(f"\n❌ 시스템 오류: {traceback.format_exc()}")
        finally:
            self.current_phase = 0
            if getattr(self, "driver", None):
                try: self.driver.quit() 
                except: pass

    def real_crawling_process(self, target_count, mode_value, target_hours):
        output_filename = ""
        cache_paths = None

        try:
            slow_mode = mode_value == "slow"
            link_only_mode = mode_value == "link_only"
            sleep_time_per_item = 0.0

            if slow_mode and target_count > 0:
                base_time_per_item = 15
                total_crawling_time = target_count * base_time_per_item
                estimated_link_collection_time = max(30 * 60, target_count * 3)
                total_required_time = total_crawling_time + estimated_link_collection_time
                user_time = target_hours * 3600
                extra_time_available = user_time - total_required_time
                sleep_time_per_item = extra_time_available / target_count

                if sleep_time_per_item < 0:
                    print("⚠️ 입력한 시간이 부족해서 느린 모드를 빠른 모드로 전환합니다.")
                    slow_mode = False
                    mode_value = "fast"
                else:
                    print(f"✅ 느린 모드 설정 완료 (개당 추가 대기 {sleep_time_per_item:.1f}초)")

            mode_prefix = {
                "fast": "live",
                "slow": "slow",
                "link_only": "links",
            }.get(mode_value, "live")

            excel_dir = self.excel_dir_var.get() or os.getcwd()
            media_dir = self.media_dir_var.get() or os.path.join(excel_dir, "downloaded_files")
            os.makedirs(excel_dir, exist_ok=True)
            os.makedirs(media_dir, exist_ok=True)

            output_filename = os.path.join(
                excel_dir,
                f"threads_{mode_prefix}_report_{datetime.now().strftime('%m%d_%H%M')}.xlsx",
            )
            cache_paths = make_temp_cache_paths(output_filename)
            self.active_output_filename = output_filename
            self.active_cache_paths = cache_paths

            debug_dir = make_debug_run_dir(excel_dir)
            debug_log_path = os.path.join(debug_dir, "session.log")
            append_debug_log(debug_log_path, f"디버그 아티팩트 폴더: {debug_dir}")

            target_links = []
            self.current_phase = 1
            self.link_start_time = time.time()
            self.crawl_start_time = None
            self.update_timer()

            if not self.driver:
                print("⚠️ 브라우저가 아직 준비되지 않았습니다.")
                return

            try:
                if len(self.driver.window_handles) > 1:
                    self.driver.switch_to.window(self.driver.window_handles[-1])
            except:
                pass

            log_page_state(self.driver, "scan_ready", debug_log_path)
            save_debug_snapshot(self.driver, debug_dir, "scan_ready")

            current_url = self.driver.current_url
            profile_user = None
            match = re.search(r"threads\.(?:net|com)/(@[\w\.]+)", current_url)
            if match:
                profile_user = match.group(1)
                print(f"\n🎯 특정 프로필 감지: {profile_user}")
            else:
                print("\n📋 메인 피드 또는 저장됨 화면으로 인식했습니다.")

            print("\n[1단계] 링크 수집을 시작합니다.")
            while len(target_links) < target_count and not self.stop_requested:
                if self.current_phase != 1:
                    break
                try:
                    containers = get_post_row_containers(self.driver)
                    for container in containers:
                        try:
                            post_anchors = container.find_elements(By.XPATH, ".//a[contains(@href, '/post/')]")
                            if not post_anchors:
                                continue

                            link = post_anchors[0].get_attribute("href").split("?")[0]
                            if profile_user and f"/{profile_user}/post/" not in link:
                                continue

                            if link not in target_links and "/post/" in link:
                                target_links.append(link)
                                cache_links(cache_paths, target_links)
                                self.p1_count_label.configure(text=f"수집 현황: ({len(target_links)} / {target_count})")
                                self.p1_progress_bar.set(float(len(target_links)) / max(1, target_count))
                                print(f"🔎 링크 수집 현황: [{len(target_links)}/{target_count}]")

                            if len(target_links) >= target_count or self.stop_requested:
                                break
                        except:
                            continue

                    if len(target_links) >= target_count or self.stop_requested:
                        break

                    self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.PAGE_DOWN)
                    time.sleep(0.7)
                except Exception as e:
                    print(f"⚠️ 링크 수집 중 오류: {e}")
                    break

            cache_links(cache_paths, target_links)
            print(f"\n✅ 링크 확보 완료! 현재까지 {len(target_links)}개 수집했습니다.")

            try:
                with open(os.path.join(debug_dir, "collected_links.txt"), "w", encoding="utf-8") as f:
                    f.write("\n".join(target_links))
            except:
                pass

            append_debug_log(debug_log_path, f"수집 링크 {len(target_links)}개, 샘플={target_links[:3]}")
            if not target_links:
                print("⚠️ 수집된 링크가 없어 종료합니다.")
                return

            if link_only_mode:
                print("🧾 링크만 수집 모드이므로 상세 크롤링 없이 엑셀로 마감합니다.")
                return

            self.current_phase = 2
            self.phase1_panel.pack_forget()
            self.phase2_panel.pack(fill="x", padx=30, pady=(10, 0), before=self.timer_panel)
            self.crawl_start_time = time.time()
            self.update_timer()

            print("\n[2단계] 상세 데이터 크롤링을 시작합니다.")
            for i, url in enumerate(target_links):
                if self.current_phase != 2 or self.stop_requested:
                    break

                try:
                    print(f"\n📊 [{i+1}/{len(target_links)}] 분석 중: {url}")
                    self.driver.get(url)
                    time.sleep(6)
                    log_page_state(self.driver, f"detail_{i+1}_loaded", debug_log_path)

                    current_detail_url = self.driver.current_url.split("?")[0]
                    expected_detail_url = url.split("?")[0]
                    if not is_post_detail_url(current_detail_url) or current_detail_url != expected_detail_url:
                        print(f"   ⚠️ 상세 페이지 진입 실패: {current_detail_url}")
                        html_path, png_path = save_debug_snapshot(self.driver, debug_dir, f"detail_{i+1}_entry_failed")
                        append_debug_log(debug_log_path, f"[{i+1}] 진입 실패 html={html_path} png={png_path}")
                        continue

                    if is_saved_list_page(self.driver):
                        print("   ⚠️ 아직 저장됨 목록 화면이라 본문 추출을 건너뜁니다.")
                        html_path, png_path = save_debug_snapshot(self.driver, debug_dir, f"detail_{i+1}_saved_list")
                        append_debug_log(debug_log_path, f"[{i+1}] saved list html={html_path} png={png_path}")
                        continue

                    row = {
                        "링크": url,
                        "본문": "수집실패",
                        "본문조회수": "0",
                        "작성시간": "0",
                        "좋아요": "0",
                        "답글수": "0",
                        "리포스트": "0",
                        "공유수": "0",
                        "첫댓글조회수": "0",
                        "미디어_해시값": "",
                        "크롤링시간": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }

                    row["본문조회수"] = get_views_global(self.driver)

                    try:
                        main_padding_box = None

                        try:
                            time_el = self.driver.find_element(By.TAG_NAME, "time")
                            main_padding_box = time_el.find_element(By.XPATH, "./ancestor::div[contains(@style, 'padding')][1]")
                        except:
                            pass

                        if not main_padding_box:
                            try:
                                activity_btn = self.driver.find_element(
                                    By.XPATH,
                                    "//span[contains(text(), '활동 보기') or contains(text(), 'getActivity')]",
                                )
                                main_padding_box = activity_btn.find_element(
                                    By.XPATH,
                                    "./ancestor::div[contains(@style, 'padding')][1]",
                                )
                            except:
                                pass

                        if not main_padding_box:
                            try:
                                main_padding_box = self.driver.find_element(By.TAG_NAME, "article")
                            except:
                                pass

                        if not main_padding_box:
                            raise Exception("본문 컨테이너를 찾지 못했습니다.")

                        extracted_text = extract_post_text(main_padding_box)
                        if extracted_text:
                            row["본문"] = extracted_text

                        try:
                            row["작성시간"] = main_padding_box.find_element(By.TAG_NAME, "time").get_attribute("datetime")
                        except:
                            pass

                        row["좋아요"] = get_metric_inside_box(main_padding_box, ["좋아요", "Like"])
                        row["답글수"] = get_metric_inside_box(main_padding_box, ["답글", "Reply"])
                        row["리포스트"] = get_metric_inside_box(main_padding_box, ["리포스트", "Repost"])
                        row["공유수"] = get_metric_inside_box(main_padding_box, ["보내기", "공유", "Share"])

                        if self.save_images_var.get():
                            try:
                                print("   🖼️ 미디어 수집 중...", flush=True)
                                post_id = url.split("/post/")[1].split("?")[0]
                                post_media_dir = os.path.join(media_dir, post_id)
                                os.makedirs(post_media_dir, exist_ok=True)

                                collected_items = collect_post_media_urls(self.driver, main_padding_box)
                                seen_urls = set()
                                unique_items = []
                                for media_url, media_type in collected_items:
                                    if media_url not in seen_urls:
                                        seen_urls.add(media_url)
                                        unique_items.append((media_url, media_type))
                                unique_items = unique_items[:10]

                                saved_count = 0
                                for media_idx, (media_url, media_type) in enumerate(unique_items):
                                    with httpx.Client() as client:
                                        try:
                                            resp = client.get(media_url, timeout=10)
                                            if resp.status_code == 200:
                                                content_type = resp.headers.get("Content-Type", "")
                                                ext = ".mp4" if "video" in content_type else ".jpg"
                                                save_path = os.path.join(post_media_dir, f"{media_idx+1:02d}{ext}")
                                                with open(save_path, "wb") as f:
                                                    f.write(resp.content)
                                                saved_count += 1
                                        except Exception as media_error:
                                            print(f"     ⚠️ 미디어 저장 실패 ({media_url[:30]}...): {media_error}")

                                row["미디어_해시값"] = post_id
                                print(f"   ✅ 미디어 {saved_count}개 저장 완료 (폴더: {post_id})", flush=True)
                            except Exception as img_e:
                                print(f"   ⚠️ 미디어 수집 실패: {img_e}")

                        all_post_links = self.driver.find_elements(By.XPATH, "//a[contains(@href, '/post/')]")
                        main_url_base = url.split("?")[0].replace("threads.net", "threads.com")
                        first_comment_url = None

                        for link_el in all_post_links:
                            try:
                                href = link_el.get_attribute("href")
                                if not href:
                                    continue
                                href_base = href.split("?")[0].replace("threads.net", "threads.com")
                                if href_base != main_url_base:
                                    first_comment_url = href
                                    break
                            except:
                                continue

                        if first_comment_url:
                            self.driver.get(first_comment_url)
                            time.sleep(5)
                            row["첫댓글조회수"] = get_views_global(self.driver)

                    except Exception as e:
                        print(f"   ⚠️ 내부 추출 오류: {e}")

                    cache_row_result(cache_paths, i, row)
                    print(f"   💾 캐시 저장 완료 ({i+1}/{len(target_links)})")

                    self.p2_count_label.configure(text=f"통신 현황: ({i+1} / {len(target_links)})")
                    self.p2_progress_bar.set(float(i+1) / max(1, len(target_links)))

                    if slow_mode and not self.stop_requested:
                        if (i + 1) % 50 == 0:
                            break_sec = random.uniform(180, 300)
                            print(f"\n☕ 장기 대기 {break_sec:.1f}초")
                            time.sleep(break_sec)
                        else:
                            actual_sleep = max(0.0, float(sleep_time_per_item) + random.uniform(-10, 10))
                            print(f"   ⏸️ 다음 처리 전 {actual_sleep:.1f}초 대기")
                            if actual_sleep > 0:
                                time.sleep(actual_sleep)

                except Exception as e:
                    print(f"   ⚠️ 링크 처리 실패: {e}")

            if self.stop_requested:
                print("\n🛑 중단 요청을 반영해 현재까지 결과만 마감합니다.")
            else:
                print(f"\n✅ 모든 수집 단계가 끝났습니다. 엑셀 마감을 진행합니다: {os.path.abspath(output_filename)}")

        except Exception:
            print(f"\n❌ 프로세스 오류: {traceback.format_exc()}")
        finally:
            try:
                if output_filename and cache_paths:
                    finalized_count = finalize_cached_results_to_excel(output_filename, cache_paths)
                    if finalized_count:
                        print(f"\n✅ 엑셀 마감 완료: {os.path.abspath(output_filename)} ({finalized_count}행)")
                    else:
                        print("\n⚠️ 저장할 데이터가 없어 엑셀을 만들지 않았습니다.")
                    cleanup_temp_cache(cache_paths)
            except Exception as finalize_error:
                print(f"\n❌ 엑셀 마감 실패: {finalize_error}")

            self.current_phase = 0
            self.link_start_time = None
            self.crawl_start_time = None
            self.stop_requested = False
            self.active_output_filename = ""
            self.active_cache_paths = None

            if getattr(self, "driver", None):
                try:
                    self.driver.quit()
                except:
                    pass

    def on_next_click(self):
        print("\n▶ [설정 확인]")
        print(f"- 모드: {self.mode_var.get()}")
        try:
            target_count = int(self.count_entry.get() or "0")
            print(f"- 목표 개수: {target_count}")
        except ValueError:
            target_count = 10 # 기본값
            print(f"- 목표 개수: 입력 오류 (기본값 {target_count} 설정)")
            
        mode_value = self.mode_var.get()
        slow_mode = mode_value == "slow"
        
        target_hours = 0.0
        if slow_mode:
            try:
                target_hours = float(self.time_entry.get() or "0")
            except ValueError:
                target_hours = 1.0 # 기본값
        
        # 2페이지 숨기고 3페이지 표시
        self.settings_frame.pack_forget()
        self.crawling_frame.pack(pady=20, padx=20, fill="both", expand=True)
        
        # 진행률 및 타이머 초기화 세팅
        self.p1_count_label.configure(text=f"수집 현황: (0 / {target_count})")
        self.p2_count_label.configure(text=f"통신 현황: (0 / {target_count})")
        
        self.p1_progress_bar.set(0)
        self.p2_progress_bar.set(0)
        
        self.phase2_panel.pack_forget() # 확실히 숨김
        self.phase1_panel.pack(fill="x", padx=30, pady=(10, 0), before=self.timer_panel)
        self.stop_requested = False
        
        self.link_timer_label.configure(text="링크 수집 소요시간: 00:00:00")
        self.crawl_timer_label.configure(text="크롤링 소요시간: 대기 중...")
        
        print("\n🚀 크롤링 프로세스 시작")
        # 진짜 크롤링 스레드 실행
        threading.Thread(target=self.real_crawling_process, args=(target_count, mode_value, target_hours), daemon=True).start()

if __name__ == "__main__":
    app = ThreadsCrawlerApp()
    app.mainloop()
