import os, re, time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

PRECEDENT_ID = '304640' 
driver = None
try:
    initial_url = f"http://www.law.go.kr/LSW/precInfoP.do?precSeq={PRECEDENT_ID}&mode=0"

    options = webdriver.ChromeOptions()
    # options.add_argument('--headless') # 반드시 눈으로 확인해야 하므로 주석 처리
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--log-level=3')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 20)

    print("눈에 보이는 브라우저를 실행합니다. 페이지 이동 과정을 확인해주세요...")
    print(f"1. 초기 주소로 접속합니다: {initial_url}")
    driver.get(initial_url)
    
    print("2. 국세청 사이트로 주소가 바뀔 때까지 기다립니다...")
    wait.until(EC.url_contains("taxlaw.nts.go.kr"))
    final_url = driver.current_url
    print(f">> 성공! 최종 도착 주소: {final_url}")
    
    # --- ★★★★★ 여기가 마지막 디버깅 포인트입니다 ★★★★★ ---
    # 3. 에러를 내기 전에, 우리에게 조사할 시간을 줍니다.
    print("\n[수동 확인 요청] 지금부터 60초 동안 브라우저가 멈춥니다.")
    print("화면에 나타난 브라우저 창을 직접 확인해주세요.")
    print("1. 본문 내용이 정상적으로 보이나요?")
    print("2. 화면을 가리는 쿠키 동의 팝업 같은 것이 있나요?")
    print("3. 브라우저 창의 제목은 무엇인가요?")
    time.sleep(60) # 60초 동안 대기
    # --- ★★★★★ 디버깅 포인트 끝 ★★★★★ ---
    
    # 60초 후에 다시 원래 하려던 작업을 시도합니다.
    print("\n다시 본문 영역을 찾아봅니다...")
    wait.until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, "#dcmDetailBox div.top_box")
    ))
    final_html = driver.page_source
    # ... (이하 성공 시 파싱 로직) ...

except Exception as e:
    print(f"\n처리 중 오류가 발생했습니다: {e}")
finally:
    if driver:
        print("\n브라우저를 종료합니다.")
        driver.quit()