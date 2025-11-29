# 백엔드 API 설정
BACKEND_BASE_URL = "http://175.45.205.39:4000"  # 실제 서버 주소

# API 엔드포인트 정의
API_ENDPOINTS = {
    # 가격 & 담보율
    "price_feed": f"{BACKEND_BASE_URL}/price-feed",
    "metrics": f"{BACKEND_BASE_URL}/metrics",
    
    # 은행 준비금
    "banks": f"{BACKEND_BASE_URL}/banks",
    "bank_deposit": f"{BACKEND_BASE_URL}/banks/{{bank_id}}/deposit",
    "bank_withdraw": f"{BACKEND_BASE_URL}/banks/{{bank_id}}/withdraw",
    
    # 시스템 상태
    "status": f"{BACKEND_BASE_URL}/status",
    
    # 발행/소각
    "deposit": f"{BACKEND_BASE_URL}/deposit",
    "redeem_request": f"{BACKEND_BASE_URL}/redeem/request",
}

# API 호출 공통 설정
API_TIMEOUT = 5  # 초
API_RETRY_COUNT = 3