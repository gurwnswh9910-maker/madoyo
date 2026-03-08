import pandas as pd
import time
import os
import random
import requests
import shutil
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- [설정] ---
EXCEL_FILE = "upload_list.xlsx"
TEMP_MEDIA_DIR = "temp_media"
USER_DATA_DIR = r"C:\Users\ding9\AppData\Local\Google\Chrome\User Data"  # 사용자 환경에 맞게 수정 필요할 수 있음
# 프로필 이름 (댓글 달 때 내 글 찾기용, 필요시 수정)
MY_PROFILE_URL = "https://www.threads.net/@YOUR_USERNAME_HERE" 

def setup_driver():
    options = Options()
    options.add_experimental_option("detach", True)
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    # 로그인 세션 유지를 위한 프로필 경로 설정 (기존 asdf.py와 동일하게 설정 권장)
    # options.add_argument(f"user-data-dir={USER_DATA_DIR}") 
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

def download_media(driver, source_url):
    """원본 쓰레드에서 이미지/영상을 다운로드 (단순화된 버전)"""
    print(f"📥 미디어 다운로드 시도: {source_url}")
    if os.path.exists(TEMP_MEDIA_DIR):
        shutil.rmtree(TEMP_MEDIA_DIR)
    os.makedirs(TEMP_MEDIA_DIR)
    
    driver.get(source_url)
    time.sleep(5)
    
    media_paths = []
    
    # 이미지 찾기
    images = driver.find_elements(By.TAG_NAME, "img")
    count = 0
    for img in images:
        src = img.get_attribute("src")
        # 프로필 사진 등 작은 이미지는 제외 (크기 필터링은 실제론 더 복잡할 수 있음)
        if src and "net" in src and "150x150" not in src: 
            try:
                # 고해상도 이미지 찾기 로직은 복잡하므로 여기선 기본 src 다운로드
                res = requests.get(src, stream=True)
                if res.status_code == 200:
                    ext = "jpg"
                    filename = f"{TEMP_MEDIA_DIR}/image_{count}.{ext}"
                    with open(filename, 'wb') as f:
                        shutil.copyfileobj(res.raw, f)
                    media_paths.append(os.path.abspath(filename))
                    count += 1
            except Exception as e:
                print(f"이미지 다운 실패: {e}")
                
    # 영상 찾기 (video 태그)
    videos = driver.find_elements(By.TAG_NAME, "video")
    for vid in videos:
        src = vid.get_attribute("src")
        # poster 이미지가 아닌 실제 영상 소스
        if not src:
            # blob url 등은 추가 처리가 필요하지만 여기선 src가 있는 경우만 처리
            continue
            
        try:
            res = requests.get(src, stream=True)
            if res.status_code == 200:
                filename = f"{TEMP_MEDIA_DIR}/video_{count}.mp4"
                with open(filename, 'wb') as f:
                    shutil.copyfileobj(res.raw, f)
                media_paths.append(os.path.abspath(filename))
                count += 1
        except:
            pass
            
    # 본문 텍스트도 가져오고 싶다면 여기서 추출 가능
    
    return media_paths

def post_to_threads(driver, media_paths, text, coupang_link):
    """쓰레드 작성 로직"""
    print("✍️ 포스팅 시작...")
    driver.get("https://www.threads.net/")
    time.sleep(5)
    
    # 1. '글쓰기' 영역 클릭 
    # (HTML 구조가 자주 바뀌므로 여러 시도 필요. 여기서는 "무슨 생각을 하고 계신가요?" 텍스트나 Create 버튼을 찾음)
    try:
        # 상단 'Start a thread...' 영역 찾기
        create_box = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'Start a thread') or contains(text(), '스레드를 시작하세요')]"))
        )
        create_box.click()
    except:
        # 실패 시 하단/상단 + 버튼 시도
        print("상단 글쓰기 박스를 찾을 수 없어 + 버튼을 시도합니다.")
        btn = driver.find_element(By.CSS_SELECTOR, "div[role='button'][aria-label='Create']") # 혹은 aria-label='만들기'
        btn.click()
        
    time.sleep(2)
    
    # 2. 본문 입력
    # contenteditable div 찾기
    input_div = driver.find_element(By.XPATH, "//div[@contenteditable='true']")
    input_div.send_keys(text)
    time.sleep(1)
    
    # 3. 미디어 업로드
    # input type='file'은 보통 숨겨져 있음.
    if media_paths:
        file_input = driver.find_element(By.XPATH, "//input[@type='file']")
        # 여러 파일을 한 번에 올릴 땐 줄바꿈(\n) 문자로 연결해서 보냄
        paths_string = "\n".join(media_paths)
        file_input.send_keys(paths_string)
        print(f"   📸 미디어 {len(media_paths)}개 업로드 중...")
        time.sleep(5 + len(media_paths)*3) # 업로드 대기
        
    # 4. 게시 버튼 클릭
    # 텍스트가 "Post" 혹은 "게시" 인 버튼
    post_btn = driver.find_element(By.XPATH, "//div[contains(text(), 'Post') or contains(text(), '게시')][not(contains(@aria-disabled,'true'))]")
    post_btn.click()
    print("   🚀 게시 버튼 클릭!")
    
    # 게시 완료 대기 (Toast 메시지나 화면 전환 대기)
    time.sleep(5)
    
    # 5. 댓글 달기 (쿠팡 링크)
    # 가장 확실한 방법: 내 프로필로 가서 방금 쓴 글 찾기
    # (여기서는 간단히 현재 화면에 뜬 'View'를 누르거나, 기다렸다가 댓글 쓰기)
    
    # 간단 버전: 그냥 방금 쓴 글이 피드 최상단에 뜬다고 가정하고 바로 댓글 달기는 위험함.
    # 안전 버전: 내 프로필로 이동
    my_profile_btn = driver.find_element(By.XPATH, "//a[contains(@href, '@')]") # 하단 탭의 내 프로필 아이콘(보통 사람 모양)
    # 정확한 셀렉터가 어렵다면 URL 이동
    # driver.get(MY_PROFILE_URL) 
    # time.sleep(5)
    
    # 방금 쓴 글의 댓글 아이콘 클릭 -> 은 복잡하므로
    # 현재는 '게시' 후 약간 대기만 하고 넘어갑니다. (댓글 기능은 추가 구현 필요)
    print(f"   💬 (To-Do) 다음 링크 댓글 작성 필요: {coupang_link}")
    
def main():
    if not os.path.exists(EXCEL_FILE):
        print(f"❌ {EXCEL_FILE} 파일이 없습니다. 템플릿을 생성합니다.")
        df = pd.DataFrame(columns=["SourceLink", "CoupangLink", "HookingText"])
        df.loc[0] = ["https://www.threads.net/@example/post/123", "https://coupang.com/...", "와 이거 대박이네요"]
        df.to_excel(EXCEL_FILE, index=False)
        return

    df = pd.read_excel(EXCEL_FILE)
    driver = setup_driver()
    
    try:
        # 로그인 (수동 로그인 시간 줌)
        driver.get("https://www.threads.net/")
        print("🔑 로그인이 필요하다면 하시고 엔터를 누르세요.")
        input()
        
        for idx, row in df.iterrows():
            print(f"\n[{idx+1}/{len(df)}] 작업 시작")
            source = row['SourceLink']
            link = row['CoupangLink']
            text = row['HookingText']
            
            # 미디어 다운로드
            paths = download_media(driver, source)
            
            # 포스팅
            post_to_threads(driver, paths, text, link)
            
            # 휴식
            sleep_time = random.randint(30, 60)
            print(f"💤 계정 보호를 위해 {sleep_time}초 대기...")
            time.sleep(sleep_time)
            
    except Exception as e:
        print(f"오류 발생: {e}")
    finally:
        # driver.quit() # 디버깅을 위해 켜둠
        pass
        
if __name__ == "__main__":
    main()
