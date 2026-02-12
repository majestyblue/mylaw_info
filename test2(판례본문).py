import time
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# --- 설정 ---
PRECEDENT_ID = '240583' # 240583 418792, 304640

# 웹 브라우저처럼 보이기 위한 헤더
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# --- 1단계: iframe의 src 주소 가져오기 (이전과 동일) ---
# 이 단계는 requests로도 충분히 빠릅니다.
import requests
print(f"--- 1단계: 판례일련번호 '{PRECEDENT_ID}'의 실제 컨텐츠 주소 얻기 ---")
wrapper_url = 'http://www.law.go.kr/DRF/lawService.do'
params = {
    'OC': 'inomeant',
    'target': 'prec',
    'ID': PRECEDENT_ID,
    'type': 'HTML'
}
try:
    response_wrapper = requests.get(wrapper_url, params=params, headers=headers)
    response_wrapper.raise_for_status()
    soup_wrapper = BeautifulSoup(response_wrapper.text, 'lxml')
    iframe = soup_wrapper.find('iframe')
    if not iframe or not iframe.has_attr('src'):
        raise ValueError("껍데기 페이지에서 컨텐츠 iframe을 찾을 수 없습니다.")
    
    content_path = iframe['src']
    base_url = "http://www.law.go.kr"
    content_url = urljoin(base_url, content_path)
    
    print(f">> 성공! 실제 컨텐츠 주소: {content_url}")

    # --- 2단계: Selenium으로 자바스크립트가 로딩된 최종 페이지 소스 가져오기 ---
    print("\n--- 2단계: Selenium으로 최종 페이지 로딩 및 본문 가져오기 ---")
    
    # 웹 드라이버 자동 설정 및 실행
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')  # 브라우저 창을 화면에 띄우지 않음
    options.add_argument('--log-level=3') # 콘솔 로그 최소화
    options.add_argument(f"user-agent={headers['User-Agent']}") # User-Agent 설정
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    print(">> 가상 브라우저 실행 및 페이지 접속...")
    driver.get(content_url)

    # **핵심**: <div id="contentBody">가 나타날 때까지 최대 10초간 기다림
    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.ID, "contentBody")))
    print(">> 'contentBody' 로딩 확인 완료!")

    # 최종 페이지의 HTML 소스를 가져옴
    final_html = driver.page_source
    
    # 브라우저 종료
    driver.quit()

    # --- 3단계: 최종 HTML 소스를 BeautifulSoup으로 파싱 ---
    print("\n--- 3단계: 최종 HTML 분석 및 텍스트 추출 ---")
    
    soup_content = BeautifulSoup(final_html, 'lxml')
    
    content_body = soup_content.find('div', id='contentBody')
    
    if not content_body:
        raise ValueError("최종 HTML에서도 'contentBody'를 찾지 못했습니다.")

    raw_text = content_body.get_text(separator='\n', strip=True)
    cleaned_text = re.sub(r'\n\s*\n+', '\n', raw_text)

    print("\n--- [최종 판례 본문 텍스트] ---")
    print(cleaned_text)
    print("---------------------------------")

except Exception as e:
    print(f"\n처리 중 오류가 발생했습니다: {e}")
    if 'driver' in locals() and driver:
        driver.quit()