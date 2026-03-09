from playwright.sync_api import sync_playwright
import time

def check_naver_ad():
    # Run browser in headed mode (visible)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        print("Navigating to Naver...")
        page.goto("https://www.naver.com")
        time.sleep(2) # Show main page briefly
        
        # Click login button if possible, or go to login URL
        print("Clicking login...")
        try:
            # Common login button selector on Naver main
            page.click(".link_login")
        except:
            page.goto("https://nid.naver.com/nidlogin.login")
            
        print("Login page shown. Waiting for 10 seconds...")
        time.sleep(10) # Keep browser open for user to see

        browser.close()

if __name__ == "__main__":
    check_naver_ad()
