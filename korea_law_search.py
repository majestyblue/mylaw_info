import os
import httpx
from mcp.server.fastmcp import FastMCP

# --- 1. MCP 서버 초기화 ---
mcp = FastMCP("korea_law_search")

# --- 2. 환경 변수에서 API 인증 키 로드 ---
LAW_API_OC = os.getenv("LAW_API_OC")
if not LAW_API_OC:
    raise ValueError("환경 변수 'LAW_API_OC'가 설정되지 않았습니다. setting.json 파일을 확인해주세요.")

# --- 3. MCP 도구(Tool) 정의 ---
@mcp.tool()
async def search_law_list(query: str, target: str, search_option: int = 2):
    """
    국가법령정보 API를 사용하여 법령 정보 목록을 검색합니다.

    Args:
        query (str): 검색할 키워드 (예: "손해배상", "임대차").
        target (str): 검색 대상. 'prec'(판례), 'detc'(헌재결정례), 'expc'(법령해석례), 'decc'(행정심판례) 중 하나를 입력합니다.
        search_option (int, optional): 검색 범위. 1은 '제목' 검색, 2는 '본문' 검색입니다. 기본값은 2 (본문)입니다.

    Returns:
        dict: API로부터 받은 JSON 형식의 검색 결과. 오류 발생 시, 원인을 포함한 dict를 반환합니다.
    """
    url = 'http://www.law.go.kr/DRF/lawSearch.do'
    params = {
        'OC': LAW_API_OC,
        'target': target,
        'type': 'JSON',
        'search': str(search_option),
        'query': query
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            error_details = {"error": "API 요청 실패", "status_code": e.response.status_code}
            try:
                error_details["details"] = e.response.json()
            except Exception:
                error_details["details"] = e.response.text
            return error_details
        except httpx.RequestError as e:
            return {"error": "HTTP 요청 중 오류 발생", "details": str(e)}
        
# 도구 2: 상세 본문 조회
@mcp.tool()
async def get_law_content(target: str, serial_number: str, case_name: str | None = None):
    """
    [2단계] 목록 검색에서 얻은 '일련번호'를 사용하여 법령 정보의 '상세 본문'을 조회합니다.

    Args:
        target (str): 조회 대상. 'prec'(판례), 'detc'(헌재결정례), 'expc'(법령해석례), 'decc'(행정심판례) 중 하나를 입력합니다.
        serial_number (str): 조회할 정보의 고유 일련번호. (예: '608445')
        case_name (str | None, optional): 판례명(LM 파라미터). 필수는 아니며, 기본값은 None입니다.

    Returns:
        dict: API로부터 받은 상세 본문 JSON 데이터.
    """
    url = 'http://www.law.go.kr/DRF/lawService.do'
    params = {
        'OC': LAW_API_OC,
        'target': target,
        'type': 'JSON',
        'ID': serial_number,  # API 파라미터 'ID'에 serial_number 값을 전달
    }

    # case_name 인자가 제공된 경우에만 params에 추가
    if case_name:
        params['LM'] = case_name

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            error_details = {"error": "API 요청 실패", "status_code": e.response.status_code}
            try:
                error_details["details"] = e.response.json()
            except Exception:
                error_details["details"] = e.response.text
            return error_details
        except httpx.RequestError as e:
            return {"error": "HTTP 요청 중 오류 발생", "details": str(e)}

# --- 4. MCP 서버 실행 코드 (가장 중요!) ---
# 이 스크립트가 메인으로 실행될 때, 서버를 시작하고 요청을 기다리도록 합니다.
if __name__ == "__main__":
    mcp.run()