import asyncio
from playwright.async_api import async_playwright
import re
import time
import os

async def get_like_count(text):
    """
    Extracts numerical like count from text like '좋아요 1,234개' or '1.2k likes'
    """
    if not text:
        return 0
    # Remove commas
    text = text.replace(',', '')
    # Match numbers
    match = re.search(r'(\d+(\.\d+)?[kK]?)', text)
    if match:
        val = match.group(1).lower()
        if 'k' in val:
            return int(float(val.replace('k', '')) * 1000)
        return int(float(val))
    return 0

async def collect_threads_likes():
    target_url = input("▶ 크롤링할 쓰레드 프로필 URL (예: https://www.threads.net/@user): ").strip()
    try:
        threshold = int(input("▶ 좋아요 최소 개수 (N개 이상만 수집): "))
    except ValueError:
        print("❌ 숫자를 입력해주세요. 기본값 100으로 설정합니다.")
        threshold = 100

    if not target_url.startswith("http"):
        print("❌ 올바른 URL을 입력해주세요.")
        return

    async with async_playwright() as p:
        print("\n🚀 브라우저를 실행합니다. 로그인이 필요하면 창에서 직접 진행해주세요.")
        browser = await p.chromium.launch(headless=False) # 사용자 요청: "같이 보이게"
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        await page.goto(target_url)
        print("💡 로그인이 완료되었거나 페이지가 로드되면 터미널에 'start'를 입력하고 엔터를 누르세요.")
        while True:
            cmd = input("입력 대기 (start 입력 시 수집 시작): ").strip().lower()
            if cmd == 'start':
                break

        print(f"\n✨ {target_url} 에서 좋아요 {threshold}개 이상인 글을 찾습니다...")
        
        collected_links = {} # {url: likes}
        
        # Scrape loop
        for _ in range(20): # 20번 스크롤 (약 100~200개 게시물 대상)
            # Find all post containers
            # Threads often uses specific IDs or dynamic classes
            # Links usually contain /post/
            posts = await page.locator("div[data-virtualized]").all()
            
            for post in posts:
                try:
                    # 1. Get Link
                    link_el = post.locator("a[href*='/post/']").first
                    if await link_el.count() == 0:
                        continue
                        
                    url = await link_el.get_attribute("href")
                    url = "https://www.threads.net" + url if url.startswith("/") else url
                    url = url.split("?")[0]
                    
                    if url in collected_links:
                        continue

                    # 2. Get Likes
                    # Typically in an aria-label like "좋아요 123개" or inside a span near the heart icon
                    # Let's look for "aria-label" containing '좋아요' or 'likes'
                    like_container = post.locator("[aria-label*='좋아요'], [aria-label*='likes'], [aria-label*='Like']").first
                    if await like_container.count() > 0:
                        label = await like_container.get_attribute("aria-label")
                        likes = await get_like_count(label)
                        
                        if likes >= threshold:
                            collected_links[url] = likes
                            print(f"✅ 발견! [{likes}개]: {url}")
                except Exception as e:
                    continue

            # Scroll down
            await page.evaluate("window.scrollBy(0, 800)")
            await asyncio.sleep(2)
            
        print(f"\n🎊 수집 완료! 총 {len(collected_links)}개의 글을 찾았습니다.")
        
        # Save to file
        filename = f"threads_hits_{int(time.time())}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            for url, count in collected_links.items():
                f.write(f"{url} (좋아요: {count})\n")
        
        print(f"💾 결과 저장 완료: {os.path.abspath(filename)}")
        print("브라우저를 종료하려면 터미널에서 아무 키나 누르세요.")
        input()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(collect_threads_likes())
