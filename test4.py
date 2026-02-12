import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# --- 설정 ---
# 국세청 판례 (리다이렉션 발생): '304640'
PRECEDENT_ID = '304640' 

driver = None  # driver 변수를 외부에서 초기화

try:
    # 안정적인 URL 구조 사용
    initial_url = f"http://www.law.go.kr/LSW/precInfoP.do?precSeq={PRECEDENT_ID}"

    # 1. 먼저 Headless 브라우저로 리다이렉션 여부 확인
    print("--- 1단계: Headless 모드로 리다이렉션 확인 시작 ---")
    headless_options = webdriver.ChromeOptions()
    headless_options.add_argument('--headless')
    headless_options.add_argument('--no-sandbox')
    headless_options.add_argument('--disable-dev-shm-usage')
    headless_options.add_argument('--disable-gpu')
    headless_options.add_argument('--log-level=3')
    headless_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
    headless_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    headless_options.add_experimental_option('useAutomationExtension', False)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=headless_options)
    
    print(f">> 초기 주소로 접속합니다: {initial_url}")
    driver.get(initial_url)

    is_nts_case = False
    try:
        # 5초 안에 국세청 URL로 바뀌는지 확인
        WebDriverWait(driver, 5).until(EC.url_contains("taxlaw.nts.go.kr"))
        final_url = driver.current_url
        print(f">> 국세청 리다이렉션 감지! 최종 URL: {final_url}")
        is_nts_case = True
    except TimeoutException:
        print(">> 국세청 리다이렉션이 감지되지 않았습니다. 일반 판례로 처리합니다.")
        is_nts_case = False

    # Headless 브라우저의 역할은 여기까지. 일단 종료.
    driver.quit()

    # 2. 확인된 결과에 따라 분기 처리
    if is_nts_case:
        # 국세청 판례일 경우, detach 옵션으로 사용자가 닫지 않는 한 계속 열려있는 새 창을 띄움
        print("\n--- 2단계 (국세청): 새 브라우저 창에 판례 표시 ---")
        
        visible_options = webdriver.ChromeOptions()
        
        # ★★★★★ 핵심: detach 옵션을 True로 설정 ★★★★★
        # 이 옵션으로 스크립트가 종료되어도 브라우저 창이 닫히지 않습니다.
        visible_options.add_experimental_option("detach", True)
        
        # 나머지 안정적인 옵션들 추가
        visible_options.add_argument('--no-sandbox')
        visible_options.add_argument('--disable-dev-shm-usage')
        visible_options.add_argument('--disable-gpu')
        visible_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
        visible_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        visible_options.add_experimental_option('useAutomationExtension', False)
        
        driver = webdriver.Chrome(service=service, options=visible_options)
        driver.get(initial_url) # 처음부터 다시 접속하여 리다이렉션 과정을 거치게 함

        print(">> 브라우저 창이 열렸습니다. 이 스크립트는 이제 종료됩니다.")
        # time.sleep()과 같은 대기 코드가 더 이상 필요 없습니다.

    else:
        # 일반 판례일 경우, 다시 Headless로 본문 파싱
        print("\n--- 2단계 (일반): Headless 모드로 본문 파싱 시작 ---")
        driver = webdriver.Chrome(service=service, options=headless_options)
        driver.get(initial_url)
        
        # iframe으로 전환
        wait = WebDriverWait(driver, 10)
        wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "Iframe")))
        print(">> iframe으로 전환 완료.")
        
        wait.until(EC.presence_of_element_located((By.ID, "contentBody")))
        print(">> 'contentBody' 로딩 확인 완료!")

        final_html = driver.page_source
        
        print("\n--- 3단계: HTML 분석 및 텍스트 추출 ---")
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
finally:
    # is_nts_case가 True일 때는 detach 옵션으로 인해 제어권이 없으므로 quit()을 호출할 필요가 없음
    # driver.quit()은 driver 객체가 제어 중인 브라우저를 닫으므로, detach와 함께 쓰면 안됨
    # 하지만 이 스크립트에서는 분기 처리 후 driver.quit()이 명시적으로 호출되거나 스크립트가 끝나므로
    # finally 블록을 비워두거나 간단한 완료 메시지만 출력하는 것이 안전함.
    print("\n>> 스크립트 실행을 모두 마쳤습니다.")