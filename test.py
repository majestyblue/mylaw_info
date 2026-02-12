import requests
import json

# API 요청에 필요한 파라미터 설정
# OC 값은 사용자 ID로, 제공해주신 'inomeant'를 사용합니다.
# 검색어(query)는 '하자 보수'로 설정합니다.
# 본문까지 검색하기 위해 search 값을 2로 설정하여 더 넓은 범위의 결과를 가져옵니다.
params = {
    'OC': 'inomeant',
    'target': 'prec',
    'type': 'JSON',
    'search': '2',
    'query': '도배 하자 보수'
}

# API 요청을 보낼 URL
url = 'http://www.law.go.kr/DRF/lawSearch.do'

try:
    # GET 방식으로 API 요청 보내기
    response = requests.get(url, params=params)

    # 응답 상태 코드가 200 (성공)일 경우
    if response.status_code == 200:
        # 응답 받은 데이터를 JSON 형식으로 변환
        data = response.json()

        # JSON 데이터를 예쁘게 출력 (들여쓰기 4칸, 한글 깨짐 방지)
        print(json.dumps(data, indent=4, ensure_ascii=False))

    else:
        print(f"API 요청에 실패했습니다. 상태 코드: {response.status_code}")
        print(f"응답 내용: {response.text}")

except requests.exceptions.RequestException as e:
    print(f"오류가 발생했습니다: {e}")