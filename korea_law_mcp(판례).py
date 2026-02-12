import os
import re
import asyncio
import json
from typing import List, Dict, Any, Tuple

# --- 외부 라이브러리 ---
import httpx
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
# ★★★ TimeoutException을 임포트합니다. ★★★
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import urljoin

# --- MCP 서버 라이브러리 ---
from mcp.server.fastmcp import FastMCP

# --- MCP 서버 초기화 ---
mcp = FastMCP("korea_law_precedent_tool")

# --- 환경 변수에서 OC 값 로드 ---
LAW_API_OC = os.getenv("LAW_API_OC")


# --------------------------------------------------------------------------
# Selenium을 실행하는 동기 함수들
# --------------------------------------------------------------------------

def run_selenium_and_get_html(url: str) -> str:
    """[내부용] Selenium을 실행하여 JS 로딩이 완료된 최종 페이지의 HTML을 반환합니다. (기존 함수)"""
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--log-level=3')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')

    service = Service(ChromeDriverManager().install())
    driver = None
    try:
        driver = webdriver.Chrome(service=service, options=options)
        driver.get(url)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "contentBody"))
        )
        return driver.page_source
    finally:
        if driver:
            driver.quit()

# ★★★ 국세청 판례인지 확인하는 동기 함수 (새로 추가) ★★★
def _check_for_nts_redirect_sync(precedent_id: str) -> Tuple[bool, str]:
    """[내부용] 주어진 ID가 국세청 사이트로 리다이렉션되는지 Headless 모드로 확인합니다."""
    initial_url = f"http://www.law.go.kr/LSW/precInfoP.do?precSeq={precedent_id}"
    
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--log-level=3')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    service = Service(ChromeDriverManager().install())
    driver = None
    try:
        driver = webdriver.Chrome(service=service, options=options)
        driver.get(initial_url)
        
        # 5초 안에 국세청 URL로 바뀌는지 확인
        WebDriverWait(driver, 5).until(EC.url_contains("taxlaw.nts.go.kr"))
        final_url = driver.current_url
        print(f"[알림] 국세청 리다이렉션 감지 (ID: {precedent_id}) -> {final_url}")
        return True, final_url
    except TimeoutException:
        # 5초 안에 바뀌지 않으면 일반 판례로 간주
        print(f"[알림] 국세청 리다이렉션 없음 (ID: {precedent_id})")
        return False, initial_url
    finally:
        if driver:
            driver.quit()

# ★★★ 국세청 판례를 새 창으로 여는 동기 함수 (새로 추가) ★★★
def _open_nts_in_browser_sync(url: str) -> None:
    """[내부용] detach 옵션을 사용하여 스크립트가 종료돼도 닫히지 않는 새 창을 엽니다."""
    options = webdriver.ChromeOptions()
    # 핵심: 스크립트가 끝나도 브라우저를 닫지 않음
    options.add_experimental_option("detach", True)
    
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
        
    service = Service(ChromeDriverManager().install())
    # 이 driver 객체는 함수가 끝나면 사라지지만, detach 옵션 덕분에 브라우저 창은 유지됨
    driver = webdriver.Chrome(service=service, options=options)
    driver.get(url)
    print(f"[알림] 새 브라우저 창에 국세청 판례 표시: {url}")


# --------------------------------------------------------------------------
# MCP 도구 1: 판례 목록 검색
# --------------------------------------------------------------------------
@mcp.tool()
async def search_precedent_list(query: str) -> Dict[str, Any]:
    """
    주어진 키워드로 판례를 검색하여, 제목과 고유 ID가 포함된 판례 목록을 반환합니다.
    이 도구를 먼저 사용하여 판례 목록을 얻은 후, 'get_precedent_details' 도구를 사용해 상세 본문을 조회하세요.
    """
    if not LAW_API_OC:
        return {"error": "서버에 LAW_API_OC 환경 변수가 설정되지 않았습니다."}

    search_url = "http://www.law.go.kr/DRF/lawSearch.do"
    params = {'target': 'prec', 'type': 'HTML', 'query': query, 'OC': LAW_API_OC}
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(search_url, params=params)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            items = soup.select("table.tbl8 td a")
            
            precedents = []
            for index, item in enumerate(items):
                href = item.get('href', '')
                match = re.search(r"ID=(\d+)", href)
                if match:
                    precedents.append({
                        "index": index + 1,
                        "id": match.group(1),
                        "title": item.get_text(strip=True)
                    })
            
            return {
                "search_query": query,
                "count": len(precedents),
                "precedents": precedents
            }
            
    except Exception as e:
        return {"error": f"판례 목록을 검색하는 중 오류가 발생했습니다: {str(e)}"}


# --------------------------------------------------------------------------
# MCP 도구 2: 판례 상세 본문 조회
# --------------------------------------------------------------------------
async def _fetch_one_detail(precedent_id: str, client: httpx.AsyncClient) -> Dict[str, Any]:
    """[내부용] 단일 판례의 상세 본문을 비동기적으로 가져오는 헬퍼 함수"""
    
    # ★★★ 국세청 판례인지 먼저 확인하는 로직 추가 ★★★
    loop = asyncio.get_running_loop()
    try:
        is_nts, final_url = await loop.run_in_executor(None, _check_for_nts_redirect_sync, precedent_id)
        
        if is_nts:
            # 국세청 판례일 경우, 새 창으로 띄우고 특수 메시지 반환
            await loop.run_in_executor(None, _open_nts_in_browser_sync, final_url)
            return {
                "precedent_id": precedent_id,
                "title": "국세청 판례 (별도 브라우저에 표시됨)",
                "source_url": final_url,
                "full_text": "이 판례는 국세청 자료로 확인되어, 보안 정책으로 인해 본문을 자동으로 가져올 수 없습니다. 대신 새 브라우저 창에 해당 판례 원문을 열었으니 직접 확인해 주시기 바랍니다."
            }
    except Exception as e:
        # 국세청 판례 확인 과정에서 오류가 발생하더라도, 기존 방식으로 조회를 시도하도록 처리
        print(f"[경고] 국세청 판례 확인 중 오류 발생 (ID: {precedent_id}): {str(e)}. 기존 방식으로 조회를 계속합니다.")
    # ★★★ 여기까지가 추가된 로직입니다 ★★★

    # --- 아래는 기존 판례 상세 조회 로직입니다 ---
    base_url = "http://www.law.go.kr"
    wrapper_url = f"{base_url}/DRF/lawService.do"
    params = {'target': 'prec', 'ID': precedent_id, 'type': 'HTML', 'OC': LAW_API_OC}
    
    content_url = ""
    try:
        response_wrapper = await client.get(wrapper_url, params=params)
        response_wrapper.raise_for_status()
        soup_wrapper = BeautifulSoup(response_wrapper.text, 'lxml')
        iframe = soup_wrapper.find('iframe')
        if not iframe or not iframe.has_attr('src'):
            raise ValueError("컨텐츠 iframe을 찾을 수 없습니다.")
        
        content_url = urljoin(base_url, iframe['src'])

        final_html = await loop.run_in_executor(None, run_selenium_and_get_html, content_url)
        soup_content = BeautifulSoup(final_html, 'lxml')
        
        content_body = soup_content.find('div', id='contentBody')
        
        if content_body:
            title = content_body.find('h2').get_text(strip=True) if content_body.find('h2') else "제목 없음"
            raw_text = content_body.get_text(separator='\n', strip=True)
        else:
            content_body = soup_content.find('div', class_='view_tx')
            if not content_body:
                raise ValueError("판례 본문 내용을 담고 있는 영역(#contentBody 또는 .view_tx)을 찾을 수 없습니다.")
            
            title = soup_content.find('div', class_='view_tit').get_text(strip=True) if soup_content.find('div', class_='view_tit') else "제목 없음"
            raw_text = content_body.get_text(separator='\n', strip=True)

        cleaned_text = re.sub(r'\n\s*\n+', '\n', raw_text)

        return {
            "precedent_id": precedent_id,
            "title": title,
            "source_url": content_url,
            "full_text": cleaned_text
        }
    except Exception as e:
        return {
            "precedent_id": precedent_id,
            "error": f"상세 정보를 가져오는 데 실패했습니다: {str(e)}"
        }

@mcp.tool()
async def get_precedent_details(precedent_ids: List[str]) -> List[Dict[str, Any]]:
    """
    판례 고유 ID 목록을 받아 각 판례의 상세한 본문 내용을 반환합니다.
    'search_precedent_list' 도구를 사용하여 먼저 ID 목록을 얻어야 합니다.
    """
    if not LAW_API_OC:
        return [{"error": "서버에 LAW_API_OC 환경 변수가 설정되지 않았습니다."}]
    
    async with httpx.AsyncClient() as client:
        tasks = [_fetch_one_detail(pid, client) for pid in precedent_ids]
        results = await asyncio.gather(*tasks)
        return results

# --------------------------------------------------------------------------
# MCP 서버 실행
# --------------------------------------------------------------------------
if __name__ == "__main__":
    if not LAW_API_OC:
        print("!!! 치명적 오류: 'LAW_API_OC' 환경 변수가 설정되지 않았습니다.")
        print("!!! 서버를 시작하기 전에 터미널에서 환경 변수를 설정해주세요.")
        print("!!! 예시 (PowerShell): $env:LAW_API_OC = \"your_oc_value\"")
    else:
        print("=========================================")
        print("  MCP 대한민국 판례 정보 서버 시작...")
        print("  사용 가능한 도구: ")
        print("    - search_precedent_list(query: str)")
        print("    - get_precedent_details(precedent_ids: List[str])")
        print("=========================================")
        mcp.run(transport='stdio')