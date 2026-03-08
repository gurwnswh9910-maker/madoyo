import time
import pandas as pd
import traceback
import os
import random
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime

# --- [1. 브라우저 환경 설정] ---
options = Options()
options.add_experimental_option("detach", True)
options.add_argument("--start-maximized")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# WebDriver 자동 관리 및 서비스 시작
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def get_views_global():
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
    final_results = []
    # 결과 파일명 설정 (실시간 백업용)
    output_filename = f"threads_night_report_{datetime.now().strftime('%m%d_%H%M')}.xlsx"
    
    try:
        driver.get("https://www.threads.net/")
        print("\n🚀 [Step 1] 프로그램 로딩 완료. 로그인을 마친 후 엔터를 누르세요.")
        print("(※ 로딩 중 검은 창이 약 30초간 유지될 수 있습니다.)")
        input() 

        target_count = int(input("▶ 수집 목표 게시글 개수(숫자만 입력, 추천: 500): "))
        
        # 8시간(28800초) 동안 N개를 수집하려면?
        # 예: 500개 -> 개당 약 57.6초 소요 필요
        # 기본 로직 소요 시간 제외하고 추가 Delay를 계산
        print(f"\n🌙 [밤샘 모드] 8시간 동안 {target_count}개 수집을 목표로 속도를 조절합니다.")

        # --- [Step 2] 메인 피드 링크 수집 (실시간 카운트 표시) ---
        target_links = []
        print(f"\n[Step 2] 피드 스캔 시작... (목표: {target_count}개)")
        
        while len(target_links) < target_count:
            try:
                anchors = driver.find_elements(By.XPATH, "//a[contains(@href, '/post/')]")
                for a in anchors:
                    link = a.get_attribute('href').split('?')[0].replace("threads.com", "threads.net")
                    if link not in target_links and "/post/" in link:
                        target_links.append(link)
                        # \r을 사용하여 한 줄에서 카운트 갱신
                        print(f"\r🔎 링크 수집 현황: [{len(target_links)}/{target_count}]", end="")
                        
                    if len(target_links) >= target_count: break
                
                # 피드 추가 로딩을 위한 스크롤
                driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.PAGE_DOWN)
                time.sleep(2)
            except KeyboardInterrupt:
                print("\n🛑 링크 수집 중 사용자가 중단했습니다.")
                break
        
        print(f"\n✅ 링크 확보 완료! 총 {len(target_links)}개의 상세 분석을 시작합니다.")

        # --- [Step 3] 상세 데이터 분석 및 실시간 저장 ---
        for i, url in enumerate(target_links):
            try:
                # 진행률 및 예상 종료 시간
                remaining = target_count - (i + 1)
                print(f"\n📊 [{i+1}/{len(target_links)}] 분석 중: {url}")
                
                driver.get(url)
                # SPA 렌더링 대기 (기본)
                time.sleep(random.uniform(5, 8)) 

                row = {
                    "링크": url, "본문": "수집실패", "본문조회수": "0", "작성시간": "0",
                    "좋아요": "0", "답글수": "0", "리포스트": "0", "공유수": "0",
                    "첫댓글조회수": "0", "크롤링시간": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }

                # [A] 본문 데이터 추출
                row["본문조회수"] = get_views_global()
                
                try:
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
                    try:
                        row["작성시간"] = main_padding_box.find_element(By.TAG_NAME, "time").get_attribute("datetime")
                    except: pass
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
                                row["첫댓글조회수"] = get_views_global()
                                break
                except Exception as e:
                    # 요소를 못 찾았어도 수집된 만큼은 저장
                    pass
                
                final_results.append(row)

                # --- [실시간 저장] ---
                pd.DataFrame(final_results).to_excel(output_filename, index=False)
                print(f"   💾 저장 완료 (현재 {len(final_results)}개)")

                # --- [핵심: 밤샘 안전 모드 딜레이] ---
                # 8시간(28800초) / 500개 = 개당 약 57초.
                # 로직 수행에 약 10~15초 소요됨 -> 추가 대기 시간 40~50초 필요
                # 랜덤성을 부여하여 35초 ~ 55초 대기
                sleep_sec = random.uniform(35, 55)
                
                # 50개마다 장기 휴식 (Tea Time)
                if (i + 1) % 50 == 0:
                    long_break = random.uniform(180, 300) # 3분~5분 휴식
                    print(f"\n☕ [휴식] 403 방지를 위해 {long_break:.1f}초 동안 쉬어갑니다...")
                    time.sleep(long_break)
                else:
                    print(f"   💤 안전 대기: {sleep_sec:.1f}초")
                    time.sleep(sleep_sec)

            except KeyboardInterrupt:
                print(f"\n🛑 사용자가 중단했습니다. 현재까지 수집된 {len(final_results)}개를 저장합니다.")
                break
            except Exception as e:
                print(f"   ⚠️ 오류 발생(스킵): {e}")
                time.sleep(10) # 에러 시에도 잠깐 대기
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
