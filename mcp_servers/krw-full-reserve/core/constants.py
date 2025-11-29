"""
상수 정의
- 담보율 임계값
- 금융기관 정보
- 리스크 레벨 기준
"""

# 담보율 임계값
COVERAGE_CRITICAL = 98.0  # 98% 미만: 위험
COVERAGE_WARNING = 100.0  # 100% 미만: 주의
COVERAGE_OPTIMAL = 105.0  # 105% 이상: 최적

# 집중도 리스크 임계값
CONCENTRATION_MAX_SINGLE = 50.0  # 단일 기관 최대 50%
CONCENTRATION_MAX_PRIMARY = 80.0  # 주수탁은행 합계 최대 80%

# 유동성 비율 최소값
LIQUIDITY_MIN_RATIO = 50.0  # 즉시 현금화 가능 자산 최소 50%

# 금융기관 정보
INSTITUTIONS = {
    "primary_custodians": [
        {
            "code": "SH",
            "name": "신한은행",
            "type": "주수탁은행",
            "role": "메인 담보자산 보관"
        },
        {
            "code": "KB",
            "name": "KB국민은행",
            "type": "주수탁은행",
            "role": "서브 담보자산 보관"
        }
    ],
    "secondary_custodian": {
        "code": "KDB",
        "name": "KDB산업은행",
        "type": "보조수탁은행",
        "role": "리스크 분산"
    },
    "asset_manager": {
        "code": "NH",
        "name": "NH투자증권",
        "type": "운용기관",
        "role": "자산 운용 및 수익 창출"
    },
    "depository": {
        "code": "KSD",
        "name": "한국예탁결제원",
        "type": "보관기관",
        "role": "증권 물리적 보관"
    }
}

# 스테이블코인 정보
STABLECOIN_INFO = {
    "name": "Korea Won Stablecoin",
    "symbol": "KRWS",
    "decimals": 18,
    "issuer": "KOSCOM"
}

# 리스크 레벨 기준
RISK_LEVEL_THRESHOLDS = {
    "LOW": 105.0,      # 105% 이상
    "MEDIUM": 100.0,   # 100% ~ 105%
    "HIGH": 98.0,      # 98% ~ 100%
    "CRITICAL": 0.0    # 98% 미만
}