import httpx
import json
import asyncio
import os

# --- MCP 서버 라이브러리 ---
from mcp.server.fastmcp import FastMCP

# --- MCP 서버 초기화 ---
mcp = FastMCP("korea_law_search")

# --- 환경 변수에서 OC 값 로드 ---
LAW_API_OC = os.getenv("LAW_API_OC")

async def search_law_list_async(query: str, target: str, search_option: int = 2, oc_key: str = 'inomeant'):
    """
    국가법령정보 API를 사용하여 법령 정보 목록을 비동기적으로 검색합니다.

    Args:
        query (str): 검색할 키워드.
        target (str): 검색 대상 ('prec': 판례, 'detc': 헌재결정례, 'expc': 법령해석례, 'decc': 행정심판례).
        search_option (int, optional): 검색 범위 (1: 제목, 2: 본문). 기본값은 2.
        oc_key (str, optional): API 인증 키. 기본값은 'inomeant'.

    Returns:
        dict: API로부터 받은 JSON 응답 데이터. 오류 발생 시 None을 반환합니다.
    """
    # API 요청을 보낼 URL
    url = 'http://www.law.go.kr/DRF/lawSearch.do'

    # API 요청에 필요한 파라미터 설정
    params = {
        'OC': oc_key,
        'target': target,
        'type': 'JSON',
        'search': str(search_option),  # API는 search 값을 문자열로 받습니다.
        'query': query
    }

    # httpx.AsyncClient를 사용하여 비동기적으로 HTTP 요청을 보냅니다.
    async with httpx.AsyncClient() as client:
        try:
            # GET 방식으로 API 요청 보내기
            response = await client.get(url, params=params)

            # 응답 상태 코드가 200 (성공)일 경우, JSON 데이터를 반환
            if response.status_code == 200:
                return response.json()
            # 실패했을 경우, 오류 메시지를 출력하고 None을 반환
            else:
                print(f"API 요청에 실패했습니다. 상태 코드: {response.status_code}")
                print(f"응답 내용: {response.text}")
                return None

        except httpx.RequestError as e:
            print(f"HTTP 요청 중 오류가 발생했습니다: {e}")
            return None

# --- 함수 사용 예시 ---
async def main():
    # '손해배상' 키워드로 '판례(prec)'의 '본문(2)'을 검색하는 예시
    print("--- '손해배상' 판례 목록 검색 시작 ---")
    search_results = await search_law_list_async(query="손해배상", target="prec")

    # 결과를 성공적으로 받았을 경우
    if search_results:
        # 받아온 JSON 데이터를 보기 좋게 출력
        print(json.dumps(search_results, indent=4, ensure_ascii=False))

        # 다음 단계를 위해 '일련번호'를 추출하는 방법 (예시)
        # 결과 데이터가 리스트 형태이고, 각 항목이 딕셔너리라고 가정
        if isinstance(search_results.get(list(search_results.keys())[0]), list) and len(search_results.get(list(search_results.keys())[0])) > 0:
            first_item = search_results.get(list(search_results.keys())[0])[0]
            serial_number = first_item.get('판례일련번호')
            if serial_number:
                print(f"\n[다음 단계 준비] 첫 번째 결과의 판례일련번호: {serial_number}")

    print("\n--- 검색 종료 ---")


if __name__ == "__main__":
    asyncio.run(main())