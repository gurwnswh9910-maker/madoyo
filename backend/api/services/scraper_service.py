import time
import re
from seleniumbase import Driver
from selenium.webdriver.common.by import By

def get_threads_metrics(url):
    """
    Threads 게시물의 좋아요, 답글 수 등을 스크래핑합니다.
    """
    driver = Driver(uc=True, headless=True)
    try:
        driver.get(url)
        time.sleep(5)
        
        # Threads의 좋아요/답글 수는 보통 "좋아요 N개", "답글 N개" 형태의 텍스트로 존재
        page_source = driver.page_source
        
        # 정규표현식으로 숫자 추출 시도
        likes = 0
        replies = 0
        
        like_match = re.search(r'([0-9,]+)\s*(?:likes|좋아요)', page_source)
        if like_match:
            likes = int(like_match.group(1).replace(',', ''))
            
        reply_match = re.search(r'([0-9,]+)\s*(?:replies|답글)', page_source)
        if reply_match:
            replies = int(reply_match.group(1).replace(',', ''))
            
        return {
            "likes": likes,
            "replies": replies,
            "views": likes * 15, # 조회수 미제공 시 추정치 (보통 좋아요의 10~20배)
            "updated_at": time.time()
        }
    except Exception as e:
        print(f"Scraping error: {e}")
        return None
    finally:
        driver.quit()

def calculate_mss_from_metrics(metrics):
    """
    수집된 지표를 바탕으로 MSS 점수(0~100)를 계산합니다.
    """
    if not metrics: return 0.0
    
    likes = metrics.get("likes", 0)
    replies = metrics.get("replies", 0)
    
    # 단순화된 MSS 계산 공식 (예시)
    # 가중치: 좋아요 1, 답글 5
    raw_score = (likes * 1) + (replies * 5)
    
    # 0~100 사이로 정규화 (최대치 1000 기준)
    mss = min(raw_score / 10.0, 100.0)
    return mss
