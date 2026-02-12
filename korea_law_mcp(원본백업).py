import os
import re
import asyncio
import json
from typing import List, Dict, Any

# --- 외부 라이브러리 ---
import httpx
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import urljoin

# --- MCP 서버 라이브러리 ---
from mcp.server.fastmcp import FastMCP

# --- MCP 서버 초기화 ---
# LLM이 이 도구 모음을 "korea_law_precedent_tool"이라는 이름으로 인식하게 됩니다.
mcp = FastMCP("korea_law_precedent_tool")

# --- 환경 변수에서 OC 값 로드 ---
# 서버 시작 시 한 번만 로드하여 사용합니다.
LAW_API_OC = os.getenv("LAW_API_OC")

# --------------------------------------------------------------------------
# Selenium을 실행하는 동기 함수 (별도 스레드에서 실행될 부분)
# --------------------------------------------------------------------------
def run_selenium_and_get_html(url: str) -> str:
    """[내부용] Selenium을 실행하여 JS 로딩이 완료된 최종 페이지의 HTML을 반환합니다."""
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    
    # --- ★★★ 안정성을 위해 아래 3줄을 추가합니다 ★★★ ---
    # 1. 샌드박스 비활성화: 격리된 환경에서 권한 문제로 인한 충돌을 방지합니다.
    options.add_argument('--no-sandbox')
    # 2. /dev/shm 사용 비활성화: 공유 메모리 공간 부족으로 인한 크롬 충돌을 방지합니다.
    options.add_argument('--disable-dev-shm-usage')
    # 3. GPU 가속 비활성화: 헤드리스 모드에서는 불필요하며, 특정 환경에서 충돌을 유발할 수 있습니다.
    options.add_argument('--disable-gpu')
    # --- ★★★ 여기까지 추가 ★★★ ---
    
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
    base_url = "http://www.law.go.kr"
    wrapper_url = f"{base_url}/DRF/lawService.do"
    params = {'target': 'prec', 'ID': precedent_id, 'type': 'HTML', 'OC': LAW_API_OC}
    
    content_url = "" # url을 미리 선언
    try:
        response_wrapper = await client.get(wrapper_url, params=params)
        response_wrapper.raise_for_status()
        soup_wrapper = BeautifulSoup(response_wrapper.text, 'lxml')
        iframe = soup_wrapper.find('iframe')
        if not iframe or not iframe.has_attr('src'):
            raise ValueError("컨텐츠 iframe을 찾을 수 없습니다.")
        
        content_url = urljoin(base_url, iframe['src'])

        loop = asyncio.get_running_loop()
        final_html = await loop.run_in_executor(None, run_selenium_and_get_html, content_url)

        soup_content = BeautifulSoup(final_html, 'lxml')
        
        # --- ★★★ 여기가 최종 수정의 핵심입니다 ★★★ ---
        # Plan A: 먼저 표준 판례 형식인 #contentBody를 찾습니다.
        content_body = soup_content.find('div', id='contentBody')
        
        if content_body:
            # Plan A 성공 (대법원 판례 등)
            title = content_body.find('h2').get_text(strip=True) if content_body.find('h2') else "제목 없음"
            raw_text = content_body.get_text(separator='\n', strip=True)
        else:
            # Plan B: #contentBody가 없으면, 국세청 판례 형식인 .view_tx 를 찾습니다.
            content_body = soup_content.find('div', class_='view_tx')
            if not content_body:
                # Plan B 마저 실패하면, 페이지 구조를 알 수 없으므로 에러 처리
                raise ValueError("판례 본문 내용을 담고 있는 영역(#contentBody 또는 .view_tx)을 찾을 수 없습니다.")
            
            # Plan B 성공 (국세청 판례 등)
            title = soup_content.find('div', class_='view_tit').get_text(strip=True) if soup_content.find('div', class_='view_tit') else "제목 없음"
            raw_text = content_body.get_text(separator='\n', strip=True)
        # --- ★★★ 수정 끝 ★★★ ---

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
        # 각 ID에 대한 본문 조회 작업을 비동기 태스크로 생성
        tasks = [_fetch_one_detail(pid, client) for pid in precedent_ids]
        # asyncio.gather를 사용하여 모든 태스크를 동시에 실행
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
        # MCP 서버를 표준 입출력(stdio) 모드로 실행합니다.
        # LLM 에이전트와 JSON-RPC 형식으로 통신하게 됩니다.
        mcp.run(transport='stdio')