
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
    """ 페이지 내 글로벌 탐색을 통한 조회수 수집 """
    try:
        view_el = driver.find_element(By.XPATH, "//span[contains(text(), '조회')]")
        return view_el.text.strip()
    except:
        return "0회"

def get_metric_inside_box(parent_el, label_names):
    """ 본문 패딩 박스 내부의 인터랙션 수치 수집 """
    if isinstance(label_names, str): label_names = [label_names]
    for label in label_names:
        try:
            xpath = f".//*[contains(@aria-label, '{label}')]//ancestor::div[1]//span"
            element = parent_el.find_element(By.XPATH, xpath)
            return element.text.strip()
        except: continue
    return "0"

def check_is_profile_link(el):
    """ 요소가 프로필 관련 링크(아이디, 사진)인지 판별 """
    try:
        el.find_element(By.XPATH, "./ancestor::a")
        return True
    except:
        return False

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

    # WebDriver 서비스 설정 (콘솔 창 숨김)
    service = Service(ChromeDriverManager().install())
    service.creation_flags = 0x08000000  # CREATE_NO_WINDOW - 명령 프롬프트 창 숨김
    
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

        # --- [Step 2] 메인 피드 링크 수집 (실시간 카운트 표시) ---
        target_links = []
        
        # [자동 창 전환] 여러 창이 열려있을 경우 마지막(최신) 창으로 포커스를 이동합니다.
        try:
            if len(driver.window_handles) > 1:
                driver.switch_to.window(driver.window_handles[-1])
        except:
            pass

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
                containers = driver.find_elements(By.XPATH, "//div[@data-virtualized]")
                
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
        for i, url in enumerate(target_links):
            try:
                print(f"\n📊 [{i+1}/{len(target_links)}] 분석 중: {url}", flush=True)
                driver.get(url)
                time.sleep(6) # SPA 렌더링 대기 시간

                row = {
                    "링크": url, "본문": "수집실패", "본문조회수": "0", "작성시간": "0",
                    "좋아요": "0", "답글수": "0", "리포스트": "0", "공유수": "0",
                    "첫댓글조회수": "0", "크롤링시간": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }

                # [A] 본문 데이터 추출
                row["본문조회수"] = get_views_global(driver)
                
                activity_btn = driver.find_element(By.XPATH, "//span[contains(text(), '활동 보기')]")
                main_padding_box = activity_btn.find_element(By.XPATH, "./ancestor::div[contains(@style, 'padding')][1]")
                
                # 본문 텍스트 (프로필 링크 제외 필터링)
                all_autos = main_padding_box.find_elements(By.XPATH, ".//*[@dir='auto']")
                valid_contents = [el for el in all_autos if not check_is_profile_link(el)]
                
                if valid_contents:
                    anchor_el = max(valid_contents, key=lambda x: len(x.text.strip()))
                    content_layer = anchor_el.find_element(By.XPATH, "./parent::span/parent::div | ./parent::div")
                    row["본문"] = content_layer.text.strip()

                # [B] 인터랙션 수치
                row["작성시간"] = main_padding_box.find_element(By.TAG_NAME, "time").get_attribute("datetime")
                row["좋아요"] = get_metric_inside_box(main_padding_box, ["좋아요", "Like"])
                row["답글수"] = get_metric_inside_box(main_padding_box, ["답글", "Reply"])
                row["리포스트"] = get_metric_inside_box(main_padding_box, ["리포스트", "Repost"])
                row["공유수"] = get_metric_inside_box(main_padding_box, ["보내기", "공유", "Share"])

                # [C] 첫 번째 댓글 영역 탐색 (Sibling 전략)
                parent_div = main_padding_box.find_element(By.XPATH, "./..")
                reply_candidates = parent_div.find_elements(By.XPATH, "./following-sibling::div//a[contains(@href, '/post/')]")
                
                for link_el in reply_candidates:
                    l_url = link_el.get_attribute("href").split('?')[0]
                    if l_url != url.split('?')[0]:
                        try:
                            # 이미지/아이콘이 포함된 프로필 링크는 건너뜀
                            link_el.find_element(By.XPATH, ".//img | .//svg")
                            continue
                        except:
                            driver.get(l_url)
                            time.sleep(5)
                            row["첫댓글조회수"] = get_views_global(driver)
                            break
                
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
        self.geometry("600x600")
        self.resizable(False, False)
        
        self.driver = None
        
        # 타이머 및 상태 변수
        self.current_phase = 0 # 0: 대기, 1: 링크수집, 2: 크롤링
        self.link_start_time = None
        self.crawl_start_time = None
        self.link_elapsed = 0
        self.crawl_elapsed = 0

        # --- 1페이지: Welcome Frame ---
        self.welcome_frame = ctk.CTkFrame(self, corner_radius=15)
        self.welcome_frame.pack(pady=30, padx=40, fill="both", expand=True)

        self.title_label = ctk.CTkLabel(
            self.welcome_frame, 
            text="👋 환영합니다!", 
            font=ctk.CTkFont(family="Malgun Gothic", size=28, weight="bold")
        )
        self.title_label.pack(pady=(50, 15))

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
        
        # 처음엔 숨김
        self.time_label.grid_remove()
        self.time_entry.grid_remove()
        
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
            
            service = Service(ChromeDriverManager().install())
            service.creation_flags = 0x08000000
            
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
            match = re.search(r"threads\.(?:net|com)/(@[\w\.]+)", current_url)
            
            if match:
                profile_user = match.group(1)
                self.verify_label.configure(text=f"✅ 감지됨: {profile_user}", text_color="#51CF66")
            else:
                self.verify_label.configure(text="❌ 프로필이 검색되지 않았습니다.", text_color="#FCC419")
        except Exception as e:
            self.verify_label.configure(text=f"❌ 검증 중 오류 발생", text_color="#FF6B6B")
            
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

    def real_crawling_process(self, target_count, slow_mode, target_hours):
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
            output_filename = f"threads_{mode_prefix}_report_{datetime.now().strftime('%m%d_%H%M')}.xlsx"
            
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
                    containers = self.driver.find_elements(By.XPATH, "//div[@data-virtualized]")
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
                    
                    row = {
                        "링크": url, "본문": "수집실패", "본문조회수": "0", "작성시간": "0",
                        "좋아요": "0", "답글수": "0", "리포스트": "0", "공유수": "0",
                        "첫댓글조회수": "0", "크롤링시간": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    
                    row["본문조회수"] = get_views_global(self.driver)
                    try:
                        activity_btn = self.driver.find_element(By.XPATH, "//span[contains(text(), '활동 보기')]")
                        main_padding_box = activity_btn.find_element(By.XPATH, "./ancestor::div[contains(@style, 'padding')][1]")
                        
                        all_autos = main_padding_box.find_elements(By.XPATH, ".//*[@dir='auto']")
                        valid_contents = [el for el in all_autos if not check_is_profile_link(el)]
                        if valid_contents:
                            anchor_el = max(valid_contents, key=lambda x: len(x.text.strip()))
                            content_layer = anchor_el.find_element(By.XPATH, "./parent::span/parent::div | ./parent::div")
                            row["본문"] = content_layer.text.strip()
                            
                        row["작성시간"] = main_padding_box.find_element(By.TAG_NAME, "time").get_attribute("datetime")
                        row["좋아요"] = get_metric_inside_box(main_padding_box, ["좋아요", "Like"])
                        row["답글수"] = get_metric_inside_box(main_padding_box, ["답글", "Reply"])
                        row["리포스트"] = get_metric_inside_box(main_padding_box, ["리포스트", "Repost"])
                        row["공유수"] = get_metric_inside_box(main_padding_box, ["보내기", "공유", "Share"])
                        
                        parent_div = main_padding_box.find_element(By.XPATH, "./..")
                        reply_candidates = parent_div.find_elements(By.XPATH, "./following-sibling::div//a[contains(@href, '/post/')]")
                        for link_el in reply_candidates:
                            l_url = link_el.get_attribute("href").split('?')[0]
                            if l_url != url.split('?')[0]:
                                try:
                                    link_el.find_element(By.XPATH, ".//img | .//svg")
                                except:
                                    self.driver.get(l_url)
                                    time.sleep(5)
                                    row["첫댓글조회수"] = get_views_global(self.driver)
                                    break
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

    def on_next_click(self):
        print("\n▶ [설정 확인]")
        print(f"- 모드: {self.mode_var.get()}")
        try:
            target_count = int(self.count_entry.get() or "0")
            print(f"- 목표 개수: {target_count}")
        except ValueError:
            target_count = 10 # 기본값
            print(f"- 목표 개수: 입력 오류 (기본값 {target_count} 설정)")
            
        slow_mode = self.mode_var.get() == "slow"
        
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
        
        self.link_timer_label.configure(text="링크 수집 소요시간: 00:00:00")
        self.crawl_timer_label.configure(text="크롤링 소요시간: 대기 중...")
        
        print("\n🚀 크롤링 프로세스 시작")
        # 진짜 크롤링 스레드 실행
        threading.Thread(target=self.real_crawling_process, args=(target_count, slow_mode, target_hours), daemon=True).start()

if __name__ == "__main__":
    app = ThreadsCrawlerApp()
    app.mainloop()