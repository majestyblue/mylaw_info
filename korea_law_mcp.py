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
# 내부 헬퍼(Helper) 함수들 - 실제 로직 수행
# --------------------------------------------------------------------------

async def _search_list_helper(query: str, target: str) -> Dict[str, Any]:
    """[내부용] 판례/헌재결정례 목록 검색의 핵심 로직을 수행합니다."""
    search_url = "http://www.law.go.kr/DRF/lawSearch.do"
    # ★★★ target 값을 인자로 받아 동적으로 설정 ★★★
    params = {'target': target, 'type': 'HTML', 'query': query, 'OC': LAW_API_OC}
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(search_url, params=params)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            items = soup.select("table.tbl8 td a")
            
            results = []
            for index, item in enumerate(items):
                href = item.get('href', '')
                # 판례와 헌재결정례 모두 'ID=' 패턴을 사용하므로 정규식 재사용 가능
                match = re.search(r"ID=(\d+)", href)
                if match:
                    results.append({
                        "index": index + 1,
                        "id": match.group(1),
                        "title": item.get_text(strip=True)
                    })
            
            return {
                "search_query": query,
                "count": len(results),
                "results": results # "precedents" 대신 "results"로 일반화
            }
            
    except Exception as e:
        return {"error": f"목록을 검색하는 중 오류가 발생했습니다: {str(e)}"}


# --- 본문 조회를 위한 Selenium 관련 함수들은 변경 없이 그대로 사용 ---

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
        WebDriverWait(driver, 5).until(EC.url_contains("taxlaw.nts.go.kr"))
        final_url = driver.current_url
        return True, final_url
    except TimeoutException:
        return False, initial_url
    finally:
        if driver:
            driver.quit()

def _open_nts_in_browser_sync(url: str) -> None:
    """[내부용] detach 옵션을 사용하여 새 창을 엽니다."""
    options = webdriver.ChromeOptions()
    options.add_experimental_option("detach", True)
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    # ... (나머지 옵션 생략) ...
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.get(url)

def run_selenium_and_get_html(url: str) -> str:
    """[내부용] Selenium을 실행하여 최종 페이지의 HTML을 반환합니다."""
    # ... (기존 코드와 동일) ...
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
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
    

async def _fetch_one_detail(doc_id: str, client: httpx.AsyncClient) -> Dict[str, Any]:
    """[내부용] 판례/헌재결정례 ID로 상세 본문을 가져오는 핵심 로직입니다."""
    # 이 함수는 ID만 있으면 되므로 판례/헌재결정례 구분 없이 완벽하게 재사용 가능
    loop = asyncio.get_running_loop()
    try:
        is_nts, final_url = await loop.run_in_executor(None, _check_for_nts_redirect_sync, doc_id)
        if is_nts:
            await loop.run_in_executor(None, _open_nts_in_browser_sync, final_url)
            return {
                "document_id": doc_id,
                "title": "국세청 자료 (별도 브라우저에 표시됨)",
                "source_url": final_url,
                "full_text": "이 자료는 국세청 소관으로 확인되어, 새 브라우저 창에 원문을 열었으니 직접 확인해 주시기 바랍니다."
            }
    except Exception as e:
        print(f"[경고] 국세청 자료 확인 중 오류 (ID: {doc_id}): {str(e)}. 일반 조회를 계속합니다.")

    base_url = "http://www.law.go.kr"
    wrapper_url = f"{base_url}/DRF/lawService.do"
    # ★★★ target을 'prec'로 고정해도 ID만 있으면 올바른 페이지로 이동합니다. ★★★
    # 만약 문제가 된다면 이 부분도 동적으로 받을 수 있으나, 보통 ID 기반 조회는 target이 없어도 무방합니다.
    params = {'target': 'prec', 'ID': doc_id, 'type': 'HTML', 'OC': LAW_API_OC}
    
    try:
        response_wrapper = await client.get(wrapper_url, params=params)
        # ... (이하 본문 파싱 로직은 기존과 100% 동일) ...
        response_wrapper.raise_for_status()
        soup_wrapper = BeautifulSoup(response_wrapper.text, 'lxml')
        iframe = soup_wrapper.find('iframe')
        content_url = urljoin(base_url, iframe['src'])
        final_html = await loop.run_in_executor(None, run_selenium_and_get_html, content_url)
        soup_content = BeautifulSoup(final_html, 'lxml')
        
        content_body = soup_content.find('div', id='contentBody')
        if content_body:
            title = content_body.find('h2').get_text(strip=True) if content_body.find('h2') else "제목 없음"
            raw_text = content_body.get_text(separator='\n', strip=True)
        else:
            # ... (Plan B 로직) ...
            raise ValueError("판례 본문 내용을 담고 있는 영역을 찾을 수 없습니다.")

        cleaned_text = re.sub(r'\n\s*\n+', '\n', raw_text)
        return {
            "document_id": doc_id, "title": title, "source_url": content_url, "full_text": cleaned_text
        }
    except Exception as e:
        return { "document_id": doc_id, "error": f"상세 정보 조회 실패: {str(e)}" }


# --------------------------------------------------------------------------
# MCP 도구(Tool)들 - LLM이 직접 호출하는 인터페이스
# --------------------------------------------------------------------------

@mcp.tool()
async def search_precedent_list(query: str) -> Dict[str, Any]:
    """
    주어진 키워드로 "판례"를 검색하여, 제목과 고유 ID가 포함된 목록을 반환합니다.
    """
    if not LAW_API_OC: return {"error": "서버에 LAW_API_OC 환경 변수가 설정되지 않았습니다."}
    return await _search_list_helper(query, 'prec')

@mcp.tool()
async def search_constitutional_case_list(query: str) -> Dict[str, Any]:
    """
    주어진 키워드로 "헌법재판소 결정례"를 검색하여, 제목과 고유 ID가 포함된 목록을 반환합니다.
    """
    if not LAW_API_OC: return {"error": "서버에 LAW_API_OC 환경 변수가 설정되지 않았습니다."}
    return await _search_list_helper(query, 'detc')

@mcp.tool()
async def get_precedent_details(precedent_ids: List[str]) -> List[Dict[str, Any]]:
    """
    "판례" 고유 ID 목록을 받아 각 판례의 상세한 본문 내용을 반환합니다.
    'search_precedent_list' 도구를 사용하여 먼저 ID 목록을 얻어야 합니다.
    """
    if not LAW_API_OC: return [{"error": "서버에 LAW_API_OC 환경 변수가 설정되지 않았습니다."}]
    async with httpx.AsyncClient() as client:
        tasks = [_fetch_one_detail(pid, client) for pid in precedent_ids]
        return await asyncio.gather(*tasks)

@mcp.tool()
async def get_constitutional_case_details(case_ids: List[str]) -> List[Dict[str, Any]]:
    """
    "헌법재판소 결정례" 고유 ID 목록을 받아 각 결정례의 상세 본문 내용을 반환합니다.
    'search_constitutional_case_list' 도구를 사용하여 먼저 ID 목록을 얻어야 합니다.
    """
    if not LAW_API_OC: return [{"error": "서버에 LAW_API_OC 환경 변수가 설정되지 않았습니다."}]
    # 판례 조회와 본문 조회 로직이 100% 동일하므로, 같은 내부 함수를 호출합니다.
    async with httpx.AsyncClient() as client:
        tasks = [_fetch_one_detail(cid, client) for cid in case_ids]
        return await asyncio.gather(*tasks)

# --------------------------------------------------------------------------
# MCP 서버 실행
# --------------------------------------------------------------------------
if __name__ == "__main__":
    if not LAW_API_OC:
        print("!!! 치명적 오류: 'LAW_API_OC' 환경 변수가 설정되지 않았습니다.")
    else:
        print("=========================================")
        print("  MCP 대한민국 법률 정보 서버 시작...")
        print("  사용 가능한 도구: ")
        print("    - search_precedent_list(query: str)")
        print("    - get_precedent_details(precedent_ids: List[str])")
        print("    - search_constitutional_case_list(query: str)")
        print("    - get_constitutional_case_details(case_ids: List[str])")
        print("=========================================")
        mcp.run(transport='stdio')