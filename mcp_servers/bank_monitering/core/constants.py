"""
core/constants.py

bank_monitoring 프로젝트 공통 상수 정의.
(기존 krw-full-reserve/core/constants.py 와는 별도 모듈)
"""

from __future__ import annotations

from typing import Dict

# ──────────────────────────────────────
# 기존 설정값 (예시)
# ──────────────────────────────────────

COVERAGE_CRITICAL: float = 95.0
COVERAGE_WARNING: float = 98.0
COVERAGE_OPTIMAL: float = 100.0
CONCENTRATION_MAX_PRIMARY: float = 60.0
LIQUIDITY_MIN_RATIO: float = 95.0

# ──────────────────────────────────────
# Policy Engine 관련 설정
# ──────────────────────────────────────

# 1) 기관당 익스포저 한도 (비율, 0~1)
EXPOSURE_LIMITS: Dict[str, float] = {
    # 단일 은행/증권사 등 개별 기관 한도 (예: 25%)
    "single_institution": 0.25,
    # 동일 금융그룹(지주사 기준) 합산 한도 (예: 40%)
    "group": 0.40,
    # 정책금융기관 (KDB, IBK 등) 개별 한도 (예: 30%)
    "policy_bank": 0.30,
}

# 2) 신용등급별 한도 multiplier
#    - 기본 한도(예: 25%)에 곱해져 실제 적용 한도로 사용
CREDIT_RATING_MULTIPLIERS: Dict[str, float] = {
    # 100% 한도 허용
    "AAA": 1.00,
    # AA 등급군: 90%
    "AA+": 0.90,
    "AA": 0.90,
    "AA-": 0.90,
    # A+ / A: 70%
    "A+": 0.70,
    "A": 0.70,
    # A- 이하: 50% (fallback key)
    "A-": 0.50,
    "BBB+": 0.50,
    "BBB": 0.50,
    "BBB-": 0.50,
    "BB+": 0.50,
    "BB": 0.50,
    "BB-": 0.50,
    "B+": 0.50,
    "B": 0.50,
    "B-": 0.50,
    "CCC": 0.50,
    "CC": 0.50,
    "C": 0.50,
    "D": 0.50,
    # 범주형 키 (명시적 사용)
    "A-이하": 0.50,
}

# 3) 만기 버킷 목표 비중 (0~1)
#    key 값은 PolicyEngine에서 사용하는 maturity_bucket 문자열과 맞춰야 함
MATURITY_BUCKETS: Dict[str, Dict[str, float]] = {
    # Overnight (당일)
    "OVERNIGHT": {
        "min_pct": 0.30,
        "max_pct": 0.40,
    },
    # 7일 이내
    "WITHIN_7D": {
        "min_pct": 0.20,
        "max_pct": 0.30,
    },
    # 1개월 이내
    "WITHIN_1M": {
        "min_pct": 0.20,
        "max_pct": 0.30,
    },
    # 3개월 이내
    "WITHIN_3M": {
        "min_pct": 0.10,
        "max_pct": 0.20,
    },
}
