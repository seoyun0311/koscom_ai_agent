"""
KRWS Core Type Definitions - Final Stable Version
온체인/오프체인/커버리지/리포트 모든 툴이 100% 동작하도록 통합한 타입 정의
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Literal, Optional
from datetime import datetime
from enum import Enum


# ============================================
# 공통 예외 / Credit Rating
# ============================================

class APIError(Exception):
    """KRWS 공통 예외"""
    pass


class CreditRating(str, Enum):
    AAA = "AAA"
    AA_PLUS = "AA+"
    AA = "AA"
    AA_MINUS = "AA-"
    A_PLUS = "A+"
    A = "A"
    A_MINUS = "A-"
    BBB_PLUS = "BBB+"
    BBB = "BBB"
    BBB_MINUS = "BBB-"
    NR = "NR"


# ============================================
# Security
# ============================================

class Security(BaseModel):
    custodian_name: str
    custodian_code: str
    security_type: str
    market_value: int
    book_value: int
    verification_date: str

    @field_validator("market_value", "book_value", mode="before")
    @classmethod
    def fix_values(cls, v):
        if isinstance(v, (int, float)):
            return max(0, int(v))
        return v


# ============================================
# Custodian
# ============================================

class Custodian(BaseModel):
    id: Optional[str] = None       # 내부 식별자
    name: str
    code: Optional[str] = None
    balance: int
    credit_rating: Optional[CreditRating] = None
    risk_weight: Optional[float] = None
    securities: List[Security] = Field(default_factory=list)

    @field_validator("balance", mode="before")
    @classmethod
    def fix_balance(cls, v):
        if isinstance(v, (int, float)):
            return max(0, int(v))
        return v


# ============================================
# InstitutionGroup (기관 그룹)
# ============================================

class InstitutionGroup(BaseModel):
    primary_custodians: List[Custodian]
    secondary_custodians: List[Custodian]


# ============================================
# On-Chain: Supply
# ============================================

class Supply(BaseModel):
    """
    공급량 모델 (구 TokenSupply와 완전 호환)
    """
    total: int = Field(..., ge=0)

    # 신규 필드
    burned: int = 0
    net_circulation: int = 0

    # 구버전 필드 (옵션)
    circulating: Optional[int] = None
    locked: Optional[int] = None

    @field_validator("total", "burned", "net_circulation", "circulating", "locked", mode="before")
    @classmethod
    def fix_int_fields(cls, v):
        if v is None:
            return v
        if isinstance(v, (int, float)):
            return max(0, int(v))
        return v


# TokenSupply 이름을 사용하는 옛 코드 호환용
TokenSupply = Supply


# ============================================
# BlockInfo
# ============================================

class BlockInfo(BaseModel):
    number: int
    timestamp: str
    hash: Optional[str] = None

    @field_validator("number", mode="before")
    @classmethod
    def fix_block_number(cls, v):
        if isinstance(v, (int, float)):
            return max(0, int(v))
        return v

    @field_validator("timestamp", mode="before")
    @classmethod
    def fix_timestamp(cls, v):
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)


# ============================================
# OnChainState
# ============================================

class OnChainState(BaseModel):
    supply: Supply
    block: BlockInfo
    contract_address: str


# ============================================
# OffChainReserves
# ============================================

class OffChainReserves(BaseModel):
    total_reserves: int
    institutions: InstitutionGroup
    timestamp: str

    @field_validator("total_reserves", mode="before")
    @classmethod
    def fix_reserves(cls, v):
        if isinstance(v, (int, float)):
            return max(0, int(v))
        return v

    @field_validator("timestamp", mode="before")
    @classmethod
    def fix_timestamp(cls, v):
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)


# ============================================
# CoverageCheck
# ============================================

class Verdict(BaseModel):
    status: Literal["OK", "WARNING", "DEFICIT"]
    message: str


class CoverageCheck(BaseModel):
    coverage_ratio: float
    excess_collateral: int
    verdict: Verdict
    onchain_circulation: int
    offchain_reserves: int
    timestamp: str

    @field_validator("coverage_ratio", mode="before")
    @classmethod
    def fix_ratio(cls, v):
        if isinstance(v, (int, float)):
            return max(0.0, float(v))
        return v

    @field_validator("onchain_circulation", "offchain_reserves", mode="before")
    @classmethod
    def fix_numbers(cls, v):
        if isinstance(v, (int, float)):
            return max(0, int(v))
        return v

    @field_validator("timestamp", mode="before")
    @classmethod
    def fix_timestamp(cls, v):
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)


# ============================================
# Risk Report
# ============================================

class RiskFactor(BaseModel):
    category: str
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    description: str


class RiskSummary(BaseModel):
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    overall_status: Literal["HEALTHY", "WARNING", "CRITICAL"]
    key_metrics: dict


class RiskReport(BaseModel):
    summary: RiskSummary
    risk_factors: List[RiskFactor]
    recommendations: List[str]
    timestamp: str

    @field_validator("timestamp", mode="before")
    @classmethod
    def fix_timestamp(cls, v):
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)
# core/types.py 파일의 맨 끝에 추가
# 하위 호환성을 위한 별칭
Institutions = InstitutionGroup