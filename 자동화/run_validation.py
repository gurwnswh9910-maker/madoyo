import os
import glob
import pandas as pd
import sys
import time
import requests
from pathlib import Path

# 모듈 경로 추가
AUTO_DIR = r"c:\Users\ding9\Desktop\madoyo\자동화"
if AUTO_DIR not in sys.path:
    sys.path.append(AUTO_DIR)

from scraper import scrape_thread_content, scrape_comment_for_coupang, init_driver, fetch_coupang_product_info
from coupang_api import extract_and_convert_coupang_link

# 설정 변수
MEDIA_BASEDIR = r"c:\Users\ding9\Desktop\madoyo\0406_test"
OUTPUT_EXCEL = os.path.join(AUTO_DIR, f"검증결과_{time.strftime('%Y%m%d_%H%M%S')}.xlsx")

def clear_folder(folder_path):
    """폴더는 유지하되 안의 파일들만 모두 삭제합니다."""
    if not os.path.exists(folder_path):
        try:
            os.makedirs(folder_path, exist_ok=True)
        except Exception as e:
            print(f"폴더 생성 실패: {e}")
        return
        
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"  ⚠️ 기존 파일 삭제 실패: {e}")

def get_latest_excel():
    """자동화참조 폴더에서 가장 최신 엑셀 파일을 가져옵니다."""
    files = glob.glob(os.path.join(AUTO_DIR, "자동화참조", "*.xlsx"))
    if not files:
        print("❌ 자동화참조 폴더에 엑셀 파일이 없습니다.")
        sys.exit(1)
    # 최신 파일순 정렬
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]

def download_media(url, folder_path, prefix=""):
    """CDN에서 이미지를 직접 다운로드합니다."""
    try:
        r = requests.get(
            url, 
            timeout=10, 
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"}
        )
        if r.status_code == 200:
            ctype = r.headers.get("Content-Type", "")
            ext = ".mp4" if "video" in ctype or "/mp4" in url else ".jpg"
            if "webp" in ctype or "webp" in url:
                ext = ".webp"
                
            filename = f"{prefix}_{int(time.time() * 1000)}{ext}"
            file_path = os.path.join(folder_path, filename)
            with open(file_path, "wb") as f:
                f.write(r.content)
            return True
    except Exception as e:
        print(f"  ⚠️ 다운로드 에러 ({url[:30]}...): {e}")
    return False

def main():
    excel_path = get_latest_excel()
    print(f"📂 대상 엑셀 파일: {os.path.basename(excel_path)}")
    
    df = pd.read_excel(excel_path, engine="openpyxl")
    results = []
    
    print("\n🚀 크롬 브라우저를 띄웁니다...")
    driver = init_driver()
    
    try:
        for idx, row in df.iterrows():
            url = str(row.get("링크", "")).strip()
            hash_val = str(row.get("미디어_해시값", "")).strip()
            
            if not url.startswith("http") or not hash_val or hash_val.lower() == 'nan':
                continue
                
            print(f"\n{'='*50}")
            print(f"[{idx+1}/{len(df)}] 확인 중: {url}")
            print(f"  👉 연결된 폴더명(해시값): {hash_val}")
            
            # --- 1. 해시 폴더 비우기 ---
            folder_path = os.path.join(MEDIA_BASEDIR, hash_val)
            print("  🧹 폴더 파일 초기화 중...", flush=True)
            clear_folder(folder_path)
            
            # --- 2. Threads 본문 및 미디어 수집 ---
            print("  🔍 쓰레드 본문 & 미디어 분석 중...", flush=True)
            t_info = scrape_thread_content(url, driver=driver)
            content = t_info.get("text", "")
            all_media = t_info.get("all_media", [])
            
            print(f"    - 감지된 본문 길이: {len(content)}자")
            print(f"    - 본문 내용 미리보기: {content[:50]}..." if content else "    - ⚠️ 본문 감지 실패")
            print(f"    - 분리된 쓰레드 미디어: {len(all_media)}개")
            
            # 쓰레드 미디어 물리적 다운로드
            for m_idx, m_url in enumerate(all_media):
                download_media(m_url, folder_path, prefix=f"threads_{m_idx+1}")
            
            # --- 3. 쿠팡 링크 및 상품정보 수집 ---
            print("  🔍 댓글 영역에서 쿠팡 링크 탐색 중...", flush=True)
            c_res = scrape_comment_for_coupang(url, driver=driver)
            c_raw = ""
            c_converted = ""
            pname = ""
            
            if c_res and c_res.get("coupang_urls"):
                c_raw = c_res["coupang_urls"][0]
                print(f"    - 발견된 쿠팡 링크: {c_raw}")
                
                print("  🛒 쿠팡 상품 정보 긁어오기...", flush=True)
                p_page = fetch_coupang_product_info(c_raw, driver=driver)
                pname = p_page.get("product_name", "")
                c_img = p_page.get("image_url", "")
                
                if c_img:
                    download_media(c_img, folder_path, prefix="coupang_product")
                    print("    - 쿠팡 상품 이미지 다운로드 완료")
                
                print("  🔗 쿠팡파트너스 딥링크 변환 중...", flush=True)
                c_converted = extract_and_convert_coupang_link(c_raw, resolved_url=p_page.get("product_url"))
            else:
                print("    - ⚠️ 댓글에서 쿠팡 링크를 찾지 못했습니다.")
            
            # 결과 저장용 Dict
            results.append({
                "URL": url,
                "폴더_해시값": hash_val,
                "추출된_본문내용": content,
                "쓰레드미디어_수집갯수": len(all_media),
                "발견된_원시쿠팡링크": c_raw,
                "변환된_수익화링크": c_converted,
                "추출된_쿠팡상품명": pname
            })
            
    except KeyboardInterrupt:
        print("\n멈춤 신호 수신. 지금까지의 결과를 저장합니다.")
    except Exception as e:
        print(f"\n❌ 에러 발생: {e}")
    finally:
        try: 
            driver.quit()
        except: 
            pass
        
    print("\n💾 엑셀 파일 저장 중...")
    out_df = pd.DataFrame(results)
    out_df.to_excel(OUTPUT_EXCEL, index=False, engine="openpyxl")
    print(f"✅ 검증 완료! 새 엑셀 파일이 생성되었습니다: {os.path.basename(OUTPUT_EXCEL)}")

if __name__ == "__main__":
    main()
