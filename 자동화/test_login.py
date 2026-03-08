import time
from seleniumbase import Driver
from selenium.webdriver.common.by import By

driver = Driver(uc=True, headless=False, browser='chrome')
try:
    print('1. 이동: 인스타그램 전용 로그인 페이지 추적')
    driver.get('https://www.threads.net/login')
    time.sleep(3)
    
    print('2. 버튼 탐색: Instagram으로 진행')
    btns = driver.find_elements(By.XPATH, "//div[contains(text(), 'Instagram')] | //button[contains(., 'Instagram')]")
    if btns:
        btns[0].click()
        print(' - 인스타 로그인 버튼 클릭 완료')
        time.sleep(5)
        print(' - 현재 URL:', driver.current_url)
        
        print('3. 아이디/패스워드 입력 시도')
        user_input = driver.find_elements(By.XPATH, "//input[@name='username']")
        pw_input = driver.find_elements(By.XPATH, "//input[@name='password']")
        if user_input and pw_input:
            user_input[0].send_keys('arch_dotori')
            pw_input[0].send_keys('gghyak0616!')
            
            login_btn = driver.find_elements(By.XPATH, "//button[@type='submit']")
            if login_btn:
                login_btn[0].click()
                print(' - 로그인 버튼 클릭')
                time.sleep(10)
                print(' - 로그인 결과 URL:', driver.current_url)
    else:
        print(' - 인스타 로그인 버튼을 찾지 못함')
except Exception as e:
    print('Error:', e)
finally:
    time.sleep(10)
    driver.quit()
