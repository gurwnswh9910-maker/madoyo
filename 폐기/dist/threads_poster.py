import time
from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        # Launch browser in non-headless mode so user can see and interact
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        print("Navigating to Threads.net...")
        page.goto("https://www.threads.net")

        print("\n" + "="*50)
        print("ACTION REQUIRED: Please log in to your Threads account in the browser window.")
        print("Once you are logged in and on the home feed, press ENTER in this terminal to continue.")
        print("="*50 + "\n")
        
        input("Press Enter to continue after login...")

        print("Attempting to post...")
        
        try:
            # Strategies to find the "Start a thread" area
            # 1. Look for the text "Start a thread..." which is usually the placeholder
            # 2. Or look for the specific div structure if text fails
            
            # Click the "Start a thread..." placeholder to expand the modal/input
            # Note: The text might vary or be inside a shadow DOM, but usually visible text works best in Playwright
            page.get_by_text("Start a thread...", exact=False).first.click()
            time.sleep(1) # Wait for animation
            
            # Type the message
            # Focused element should be the input area now
            page.keyboard.type("안녕하세요!")
            time.sleep(1)
            
            # Click Post button
            # Usually has text "Post"
            page.get_by_text("Post", exact=True).click()
            
            print("Post button clicked!")
            
            # Wait a bit to ensure post goes through
            time.sleep(5)
            print("Done! Closing browser in 3 seconds.")
            time.sleep(3)
            
        except Exception as e:
            print(f"An error occurred: {e}")
            print("Dumping page content for debugging...")
            # In a real scenario we might save a screenshot
            # page.screenshot(path="error.png")
            
        finally:
            browser.close()

if __name__ == "__main__":
    run()
