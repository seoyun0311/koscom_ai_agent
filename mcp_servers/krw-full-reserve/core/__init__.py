# krw-full-reserve/core/__init__.py
"""
Core 패키지 public interface
"""

# 타입들
from .types import (
    APIError,
    CreditRating,
    Security,
    Custodian,
    InstitutionGroup,  # ← Institutions에서 변경
    Supply,
    TokenSupply,
    BlockInfo,
    OnChainState,
    OffChainReserves,
    Verdict,
    CoverageCheck,
    RiskFactor,
    RiskSummary,
    RiskReport,
)

# 하위 호환성을 위한 별칭
Institutions = InstitutionGroup  # ← import 후에 별칭 생성

# 계산 로직
from .calculator import (
    calculate_coverage,
    analyze_risk,
    generate_recommendations,
    create_risk_report,
)

# 상수들
from .constants import (
    COVERAGE_CRITICAL,
    COVERAGE_WARNING,
    COVERAGE_OPTIMAL,
    CONCENTRATION_MAX_PRIMARY,
    LIQUIDITY_MIN_RATIO,
    RISK_LEVEL_THRESHOLDS,
    INSTITUTIONS,
    STABLECOIN_INFO,
)

__all__ = [
    # Types
    "APIError",
    "CreditRating",
    "Security",
    "Custodian",
    "Institutions",
    "InstitutionGroup",
    "Supply",
    "TokenSupply",
    "BlockInfo",
    "OnChainState",
    "OffChainReserves",
    "Verdict",
    "CoverageCheck",
    "RiskFactor",
    "RiskSummary",
    "RiskReport",
    # Calculator
    "calculate_coverage",
    "analyze_risk",
    "generate_recommendations",
    "create_risk_report",
    # Constants
    "COVERAGE_CRITICAL",
    "COVERAGE_WARNING",
    "COVERAGE_OPTIMAL",
    "CONCENTRATION_MAX_PRIMARY",
    "LIQUIDITY_MIN_RATIO",
    "RISK_LEVEL_THRESHOLDS",
    "INSTITUTIONS",
    "STABLECOIN_INFO",
]