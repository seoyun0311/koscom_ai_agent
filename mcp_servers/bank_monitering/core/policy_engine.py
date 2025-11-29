from __future__ import annotations

"""
core/policy_engine.py

K-WON 스테이블코인 오프체인 준비금에 대한
Policy 한도 점검 및 위반 리포트 생성을 담당하는 엔진 모듈.
"""

from typing import Any, Dict, List, Optional, Literal
from enum import Enum

import logging
from pydantic import BaseModel, Field

from core.constants import (
    EXPOSURE_LIMITS,
    CREDIT_RATING_MULTIPLIERS,
    MATURITY_BUCKETS,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────
# Enum / Model 정의
# ──────────────────────────────────────


class SeverityLevel(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class ViolationType(str, Enum):
    EXPOSURE_LIMIT = "EXPOSURE_LIMIT"
    CREDIT_RATING_LIMIT = "CREDIT_RATING_LIMIT"
    MATURITY_DISTRIBUTION = "MATURITY_DISTRIBUTION"


class BankExposureInput(BaseModel):
    """
    PolicyEngine이 이해할 수 있는 최소 단위의 은행 익스포저 정보.
    """

    bank_id: str = Field(..., description="은행/기관 고유 ID (예: shinhan, kb, kdb 등)")
    name: str = Field(..., description="표시용 이름")
    group_id: Optional[str] = Field(
        default=None,
        description="동일 금융그룹 식별자 (지주사 기준). 없으면 개별 은행 단위로만 관리.",
    )
    is_policy_bank: bool = Field(
        default=False,
        description="정책금융기관 여부 (KDB, IBK 등)",
    )
    exposure: float = Field(
        ...,
        ge=0,
        description="해당 기관에 예치된 금액 (원화 기준)",
    )
    credit_rating: Optional[str] = Field(
        default=None,
        description="외부 신용등급 (예: AAA, AA+, AA, AA-, A+, A, A-, BBB+ ...)",
    )
    maturity_bucket: Optional[str] = Field(
        default=None,
        description="만기 버킷 식별자 (예: OVERNIGHT, WITHIN_7D, WITHIN_1M, WITHIN_3M)",
    )

    # 🔥🔥🔥 추가해야 하는 필드
    type: str = Field(
        default="other",
        description="기관의 유형 (commercial_bank, broker, policy_bank, custody_agent 등)"
    )



class PolicyViolation(BaseModel):
    """
    단일 Policy 위반 항목에 대한 구조화된 정보.
    """

    type: ViolationType = Field(..., description="위반 종류")
    level: SeverityLevel = Field(..., description="심각도")
    code: str = Field(..., description="내부 식별용 코드 (예: SINGLE_LIMIT, GROUP_LIMIT)")
    message: str = Field(..., description="사람이 읽을 수 있는 설명 (한국어)")
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="프론트/자동화에서 활용할 수 있는 추가 메타데이터",
    )


class PolicyEvaluationResult(BaseModel):
    """
    전체 Policy 점검 결과 요약.
    """

    violations: List[PolicyViolation] = Field(default_factory=list)
    highest_level: SeverityLevel = Field(SeverityLevel.OK)
    summary: Dict[str, Any] = Field(default_factory=dict)


class PolicyConfig(BaseModel):
    """
    Policy 한도 설정값. core.constants 에서 기본값 로드.
    실운영에서는 별도 설정 파일/DB에서 override 가능하도록 설계.
    """

    exposure_limits: Dict[str, float] = Field(
        default_factory=lambda: dict(EXPOSURE_LIMITS)
    )
    credit_rating_multipliers: Dict[str, float] = Field(
        default_factory=lambda: dict(CREDIT_RATING_MULTIPLIERS)
    )
    maturity_buckets: Dict[str, Dict[str, float]] = Field(
        default_factory=lambda: dict(MATURITY_BUCKETS)
    )
    warning_threshold: float = Field(
        default=0.90, description="한도 대비 90% 도달 시 WARNING"
    )
    critical_threshold: float = Field(
        default=1.00, description="한도 초과 시 CRITICAL"
    )


# ──────────────────────────────────────
# Policy Engine 본체
# ──────────────────────────────────────


class PolicyEngine:
    """
    은행별 익스포저, 신용등급, 만기구조를 입력받아
    Policy 위반 여부를 점검하는 엔진.
    """

    def __init__(self, config: Optional[PolicyConfig] = None) -> None:
        self.config = config or PolicyConfig()
        logger.debug("PolicyEngine 초기화 완료: %s", self.config.model_dump())

    # ───────── 한도 계산 유틸 ─────────

    def _calc_total_exposure(self, exposures: List[BankExposureInput]) -> float:
        total = float(sum(e.exposure for e in exposures))
        logger.debug("총 익스포저 계산 완료: %.2f", total)
        return total

    def _severity_from_ratio(self, ratio: float) -> SeverityLevel:
        """
        ratio = 현재값 / 한도
        """
        if ratio >= self.config.critical_threshold:
            return SeverityLevel.CRITICAL
        if ratio >= self.config.warning_threshold:
            return SeverityLevel.WARNING
        return SeverityLevel.OK

    # ─────────────────────────────────
    # 1) 기관당 익스포저 한도 체크
    # ─────────────────────────────────

    async def check_exposure_limits(
        self, exposures: List[BankExposureInput]
    ) -> List[PolicyViolation]:
        """
        - 단일 은행: 최대 25%
        - 동일 금융그룹 합산: 최대 40%
        - 정책금융기관(KDB, IBK): 최대 30%
        """
        if not exposures:
            logger.warning("check_exposure_limits: 입력 익스포저가 비어 있습니다.")
            return []

        total_exposure = self._calc_total_exposure(exposures)
        if total_exposure <= 0:
            logger.warning("check_exposure_limits: 총 익스포저가 0 이하입니다.")
            return []

        violations: List[PolicyViolation] = []

        # 단일 기관 한도 체크
        single_limit = self.config.exposure_limits.get("single_institution", 0.25)
        policy_limit = self.config.exposure_limits.get("policy_bank", 0.30)

        for e in exposures:
            share = e.exposure / total_exposure
            limit = policy_limit if e.is_policy_bank else single_limit
            ratio = share / limit if limit > 0 else 0.0
            level = self._severity_from_ratio(ratio)

            logger.debug(
                "단일기관 체크: bank_id=%s, share=%.4f, limit=%.4f, ratio=%.4f, level=%s",
                e.bank_id,
                share,
                limit,
                ratio,
                level,
            )

            if level is SeverityLevel.OK:
                continue

            excess_pct = max(0.0, share - limit)
            excess_amount = excess_pct * total_exposure

            violations.append(
                PolicyViolation(
                    type=ViolationType.EXPOSURE_LIMIT,
                    level=level,
                    code="SINGLE_LIMIT",
                    message=(
                        f"{e.name} 단일 기관 익스포저 비중이 한도의 "
                        f"{ratio * 100:.1f}% 수준입니다."
                    ),
                    details={
                        "bank_id": e.bank_id,
                        "bank_name": e.name,
                        "is_policy_bank": e.is_policy_bank,
                        "limit_type": "POLICY_BANK" if e.is_policy_bank else "SINGLE",
                        "current_pct": share,
                        "limit_pct": limit,
                        "ratio": ratio,
                        "total_exposure": total_exposure,
                        "current_exposure": e.exposure,
                        "excess_pct": excess_pct,
                        "excess_amount": excess_amount,
                    },
                )
            )

        # 동일 금융그룹 합산 한도 체크
        group_limit = self.config.exposure_limits.get("group", 0.40)
        group_map: Dict[str, float] = {}

        for e in exposures:
            if not e.group_id:
                continue
            group_map.setdefault(e.group_id, 0.0)
            group_map[e.group_id] += e.exposure

        for group_id, group_exp in group_map.items():
            share = group_exp / total_exposure
            ratio = share / group_limit if group_limit > 0 else 0.0
            level = self._severity_from_ratio(ratio)

            logger.debug(
                "그룹 한도 체크: group_id=%s, share=%.4f, limit=%.4f, ratio=%.4f, level=%s",
                group_id,
                share,
                group_limit,
                ratio,
                level,
            )

            if level is SeverityLevel.OK:
                continue

            excess_pct = max(0.0, share - group_limit)
            excess_amount = excess_pct * total_exposure

            violations.append(
                PolicyViolation(
                    type=ViolationType.EXPOSURE_LIMIT,
                    level=level,
                    code="GROUP_LIMIT",
                    message=(
                        f"그룹({group_id}) 합산 익스포저 비중이 한도의 "
                        f"{ratio * 100:.1f}% 수준입니다."
                    ),
                    details={
                        "group_id": group_id,
                        "limit_type": "GROUP",
                        "current_pct": share,
                        "limit_pct": group_limit,
                        "ratio": ratio,
                        "total_exposure": total_exposure,
                        "current_exposure": group_exp,
                        "excess_pct": excess_pct,
                        "excess_amount": excess_amount,
                    },
                )
            )

        return violations

    # ─────────────────────────────────
    # 2) 신용등급 기반 한도 조정 체크
    # ─────────────────────────────────

    async def check_credit_rating_limits(
        self, exposures: List[BankExposureInput]
    ) -> List[PolicyViolation]:
        """
        신용등급 별로 단일기관 한도에 multiplier 적용.
        - AAA: 100%
        - AA+/AA/AA-: 90%
        - A+/A: 70%
        - A- 이하: 50%
        """
        if not exposures:
            logger.warning("check_credit_rating_limits: 입력 익스포저가 비어 있습니다.")
            return []

        total_exposure = self._calc_total_exposure(exposures)
        if total_exposure <= 0:
            logger.warning("check_credit_rating_limits: 총 익스포저가 0 이하입니다.")
            return []

        violations: List[PolicyViolation] = []
        base_single_limit = self.config.exposure_limits.get("single_institution", 0.25)
        base_policy_limit = self.config.exposure_limits.get("policy_bank", 0.30)

        for e in exposures:
            if not e.credit_rating:
                # 신용등급 정보가 없으면 보수적으로 50% multiplier 적용
                rating_key = "A-이하"
                multiplier = self.config.credit_rating_multipliers.get(
                    rating_key, 0.50
                )
            else:
                # 정확한 key가 없으면 등급대별 fallback
                raw = e.credit_rating.upper().replace(" ", "")
                multiplier = self.config.credit_rating_multipliers.get(raw)
                if multiplier is None:
                    if raw.startswith("AAA"):
                        multiplier = self.config.credit_rating_multipliers.get(
                            "AAA", 1.0
                        )
                    elif raw.startswith("AA"):
                        multiplier = self.config.credit_rating_multipliers.get(
                            "AA", 0.90
                        )
                    elif raw.startswith("A+"):
                        multiplier = self.config.credit_rating_multipliers.get(
                            "A+", 0.70
                        )
                    elif raw.startswith("A"):
                        multiplier = self.config.credit_rating_multipliers.get(
                            "A", 0.70
                        )
                    else:
                        multiplier = self.config.credit_rating_multipliers.get(
                            "A-이하", 0.50
                        )

            base_limit = base_policy_limit if e.is_policy_bank else base_single_limit
            limit_pct = base_limit * multiplier
            share = e.exposure / total_exposure
            ratio = share / limit_pct if limit_pct > 0 else 0.0
            level = self._severity_from_ratio(ratio)

            logger.debug(
                "신용등급 한도 체크: bank_id=%s, rating=%s, share=%.4f, limit_pct=%.4f, "
                "multiplier=%.2f, ratio=%.4f, level=%s",
                e.bank_id,
                e.credit_rating,
                share,
                limit_pct,
                multiplier,
                ratio,
                level,
            )

            if level is SeverityLevel.OK:
                continue

            excess_pct = max(0.0, share - limit_pct)
            excess_amount = excess_pct * total_exposure

            violations.append(
                PolicyViolation(
                    type=ViolationType.CREDIT_RATING_LIMIT,
                    level=level,
                    code="RATING_ADJUSTED_LIMIT",
                    message=(
                        f"{e.name} (등급: {e.credit_rating or '미기재'})의 "
                        f"신용등급 조정 한도 대비 익스포저 비중이 "
                        f"{ratio * 100:.1f}% 수준입니다."
                    ),
                    details={
                        "bank_id": e.bank_id,
                        "bank_name": e.name,
                        "credit_rating": e.credit_rating,
                        "multiplier": multiplier,
                        "limit_pct": limit_pct,
                        "current_pct": share,
                        "ratio": ratio,
                        "total_exposure": total_exposure,
                        "current_exposure": e.exposure,
                        "excess_pct": excess_pct,
                        "excess_amount": excess_amount,
                    },
                )
            )

        return violations

    # ─────────────────────────────────
    # 3) 만기 버킷 목표 비중 체크
    # ─────────────────────────────────

    async def check_maturity_distribution(
        self, exposures: List[BankExposureInput]
    ) -> List[PolicyViolation]:
        """
        만기 버킷별 실제 비중을 계산하여 목표 범위와 비교.
        - Overnight (당일): 30-40%
        - 7일 이내: 20-30%
        - 1개월 이내: 20-30%
        - 3개월 이내: 10-20%
        """
        if not exposures:
            logger.warning("check_maturity_distribution: 입력 익스포저가 비어 있습니다.")
            return []

        total_exposure = self._calc_total_exposure(exposures)
        if total_exposure <= 0:
            logger.warning("check_maturity_distribution: 총 익스포저가 0 이하입니다.")
            return []

        # 버킷별 합산
        bucket_sum: Dict[str, float] = {}
        for e in exposures:
            bucket = e.maturity_bucket or "UNKNOWN"
            bucket_sum.setdefault(bucket, 0.0)
            bucket_sum[bucket] += e.exposure

        violations: List[PolicyViolation] = []

        for bucket_key, cfg in self.config.maturity_buckets.items():
            min_pct = cfg.get("min_pct", 0.0)
            max_pct = cfg.get("max_pct", 1.0)
            current = bucket_sum.get(bucket_key, 0.0) / total_exposure
            level: SeverityLevel = SeverityLevel.OK
            direction: Literal["OVER", "UNDER", "OK"] = "OK"
            bound_pct = 0.0

            if current > max_pct:
                ratio = current / max_pct if max_pct > 0 else 0.0
                level = self._severity_from_ratio(ratio)
                direction = "OVER"
                bound_pct = max_pct
            elif current < min_pct:
                # 하한에 대해서도 90%/100% 기준을 동일하게 적용
                ratio = (min_pct - current) / min_pct if min_pct > 0 else 0.0
                if ratio >= (1 - self.config.warning_threshold):
                    level = SeverityLevel.WARNING
                if ratio >= (1 - self.config.critical_threshold):
                    # critical_threshold가 1.0 이므로 min 이하이면 항상 WARNING 수준,
                    # min 대비 과도한 부족분은 CRITICAL 로 간주
                    if current < min_pct * self.config.warning_threshold:
                        level = SeverityLevel.CRITICAL
                direction = "UNDER"
                bound_pct = min_pct
            else:
                ratio = 0.0

            logger.debug(
                "만기 버킷 체크: bucket=%s, current=%.4f, min=%.4f, max=%.4f, "
                "direction=%s, level=%s",
                bucket_key,
                current,
                min_pct,
                max_pct,
                direction,
                level,
            )

            if level is SeverityLevel.OK:
                continue

            diff_pct = abs(current - bound_pct)
            diff_amount = diff_pct * total_exposure

            msg_prefix = {
                "OVER": "목표 상한을 초과",
                "UNDER": "목표 하한을 하회",
                "OK": "정상 범위",
            }[direction]

            violations.append(
                PolicyViolation(
                    type=ViolationType.MATURITY_DISTRIBUTION,
                    level=level,
                    code=f"MATURITY_{direction}",
                    message=(
                        f"{bucket_key} 버킷 비중이 {msg_prefix}하고 있습니다. "
                        f"(현재 {current * 100:.1f}%, 목표 {min_pct * 100:.1f}"
                        f"~{max_pct * 100:.1f}%)"
                    ),
                    details={
                        "bucket": bucket_key,
                        "direction": direction,
                        "current_pct": current,
                        "min_pct": min_pct,
                        "max_pct": max_pct,
                        "diff_pct": diff_pct,
                        "diff_amount": diff_amount,
                        "total_exposure": total_exposure,
                    },
                )
            )

        return violations

    # ─────────────────────────────────
    # 4) 전체 리포트 생성
    # ─────────────────────────────────

    async def generate_violations_report(
        self, exposures: List[BankExposureInput]
    ) -> PolicyEvaluationResult:
        """
        세부 체크 함수들을 실행하고, 전체 위반 리스트와
        최종 심각도 레벨을 취합.
        """
        logger.info("Policy 위반 리포트 생성 시작 (은행 수=%d)", len(exposures))

        v_exposure = await self.check_exposure_limits(exposures)
        v_rating = await self.check_credit_rating_limits(exposures)
        v_maturity = await self.check_maturity_distribution(exposures)

        all_violations: List[PolicyViolation] = [
            *v_exposure,
            *v_rating,
            *v_maturity,
        ]

        # 최종 레벨 산출
        level_order = {
            SeverityLevel.OK: 0,
            SeverityLevel.WARNING: 1,
            SeverityLevel.CRITICAL: 2,
        }
        highest = SeverityLevel.OK
        for v in all_violations:
            if level_order[v.level] > level_order[highest]:
                highest = v.level

        summary = {
            "total_violations": len(all_violations),
            "by_type": {},
            "by_level": {},
        }

        for v in all_violations:
            summary["by_type"].setdefault(v.type.value, 0)
            summary["by_type"][v.type.value] += 1

            summary["by_level"].setdefault(v.level.value, 0)
            summary["by_level"][v.level.value] += 1

        logger.info(
            "Policy 위반 리포트 생성 완료: highest_level=%s, total_violations=%d",
            highest,
            len(all_violations),
        )

        return PolicyEvaluationResult(
            violations=all_violations, highest_level=highest, summary=summary
        )
