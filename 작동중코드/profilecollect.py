
# -*- coding: utf-8 -*-
import sys
import io

# Windows 환경에서 이모지 및 한글 출력을 위한 UTF-8 인코딩 설정
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

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

if __name__ == "__main__":
    main()