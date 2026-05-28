import os
import sys
import re
import time
from pathlib import Path
import pandas as pd

# Add AUTO_DIR to sys.path to import scraper
BASE_DIR = Path(__file__).resolve().parent.parent
AUTO_DIR = BASE_DIR / "자동화"
sys.path.insert(0, str(AUTO_DIR))

from scraper import init_driver
from selenium.webdriver.common.by import By

def get_views_global(driver) -> str:
    xpaths = [
        "//*[contains(text(), '조회') or contains(text(), 'view') or contains(text(), 'View')]",
        "//*[contains(@aria-label, '조회') or contains(@aria-label, 'view') or contains(@aria-label, 'View')]",
    ]
    patterns = [
        r"([\d,.]+\s*[만천]?\s*회)",
        r"([\d,.]+\s*(?:views?|Views?))",
    ]

    for xpath in xpaths:
        try:
            elements = driver.find_elements(By.XPATH, xpath)
        except Exception:
            continue
        for element in elements:
            text = (element.text or "") + (element.get_attribute("aria-label") or "")
            if not text:
                continue
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    return " ".join(match.group(1).split())
    return "0회"

def main():
    input_file = Path(
        os.getenv(
            "MADOYO_FIRST_COMMENT_INPUT",
            str(BASE_DIR / "수동화" / "수동화참조" / "threads_links_report_0429_2252.xlsx"),
        )
    )
    output_file = Path(
        os.getenv(
            "MADOYO_FIRST_COMMENT_OUTPUT",
            str(BASE_DIR / "수동화" / "threads_links_first_comments.xlsx"),
        )
    )
    
    print(f"[{input_file}] 읽는 중...")
    df = pd.read_excel(input_file)
    
    # We will put the result in '첫댓글조회수' column
    df["첫댓글조회수"] = ""
    
    driver = init_driver()
    
    try:
        for idx, row in df.iterrows():
            url = str(row.get("링크", ""))
            if not url.startswith("http"):
                continue
            
            print(f"[{idx+1}/{len(df)}] {url} 처리 중...")
            try:
                driver.get(url)
                time.sleep(3)
                
                # 첫 번째 댓글 영역 탐색 (전체 본문 링크 우회 전략)
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
                    views = get_views_global(driver)
                    df.at[idx, "첫댓글조회수"] = views
                    print(f"   => 첫댓글 발견! 조회수: {views}")
                else:
                    df.at[idx, "첫댓글조회수"] = "없음"
                    print("   => 첫댓글을 찾을 수 없습니다.")
                    
            except Exception as e:
                print(f"  오류: {e}")
                
            # Save intermediate
            df.to_excel(output_file, index=False)
            
    finally:
        driver.quit()
        df.to_excel(output_file, index=False)
        print(f"\n완료! 결과 저장됨: {output_file}")

if __name__ == "__main__":
    main()
