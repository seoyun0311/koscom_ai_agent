"""
계산 로직
- 담보율 계산
- 리스크 분석
- 권고사항 생성
"""

from datetime import datetime
from typing import List, Tuple

from core.types import (
    OnChainState,
    OffChainReserves,
    CoverageCheck,
    Verdict,
    RiskFactor,
    RiskSummary,
    RiskReport,
)
from core.constants import (
    COVERAGE_CRITICAL,
    COVERAGE_WARNING,
    COVERAGE_OPTIMAL,
    CONCENTRATION_MAX_PRIMARY,
    LIQUIDITY_MIN_RATIO,
    RISK_LEVEL_THRESHOLDS,
)


# ====================================================
# 1. 담보율 계산
# ====================================================
def calculate_coverage(
    on_chain: OnChainState,
    off_chain: OffChainReserves,
) -> CoverageCheck:
    """
    담보율 계산 및 검증

    Args:
        on_chain: 온체인 상태
        off_chain: 오프체인 준비금

    Returns:
        CoverageCheck: 담보 검증 결과
    """
    circulation = on_chain.supply.net_circulation
    reserves = off_chain.total_reserves

    # 담보율 계산
    if circulation > 0:
        coverage_ratio = reserves / circulation * 100
    else:
        coverage_ratio = 0.0

    excess_collateral = reserves - circulation

    # 상태 판정 → Verdict.status ("OK" | "WARNING" | "DEFICIT")
    if coverage_ratio >= COVERAGE_OPTIMAL:
        status = "OK"
        message = f"담보율 {coverage_ratio:.2f}% - 정상 운영 중"
    elif coverage_ratio >= COVERAGE_WARNING:
        status = "WARNING"
        message = f"담보율 {coverage_ratio:.2f}% - 주의 필요 (모니터링 강화 권장)"
    elif coverage_ratio >= COVERAGE_CRITICAL:
        status = "WARNING"
        message = f"담보율 {coverage_ratio:.2f}% - 기준 근접, 추가 담보 확보 검토 필요"
    else:
        status = "DEFICIT"
        message = f"담보율 {coverage_ratio:.2f}% - 긴급 조치 필요 (담보 부족)"

    verdict = Verdict(
        status=status,
        message=message,
    )

    return CoverageCheck(
        coverage_ratio=round(coverage_ratio, 4),
        excess_collateral=excess_collateral,
        verdict=verdict,
        onchain_circulation=circulation,
        offchain_reserves=reserves,
        timestamp=datetime.now().isoformat(),
    )


# ====================================================
# 2. 리스크 분석
# ====================================================
def analyze_risk(
    on_chain: OnChainState,
    off_chain: OffChainReserves,
    coverage: CoverageCheck,
) -> Tuple[str, List[RiskFactor]]:
    """
    리스크 분석

    Returns:
        Tuple[risk_level, risk_factors]
        risk_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    """
    risk_factors: List[RiskFactor] = []

    # 1) 담보 부족 리스크
    if coverage.coverage_ratio < COVERAGE_WARNING:
        severity = "CRITICAL" if coverage.coverage_ratio < COVERAGE_CRITICAL else "HIGH"
        risk_factors.append(
            RiskFactor(
                category="담보 부족",
                severity=severity,
                description=f"담보율 {coverage.coverage_ratio:.2f}%로 기준 미달",
            )
        )

    # 2) 집중도 리스크 (주수탁 비중)
    total_reserves = off_chain.total_reserves
    if total_reserves > 0:
        primary_total = sum(
            c.balance for c in off_chain.institutions.primary_custodians
        )
        primary_share = primary_total / total_reserves * 100
    else:
        primary_share = 0.0

    if primary_share > CONCENTRATION_MAX_PRIMARY:
        risk_factors.append(
            RiskFactor(
                category="집중도 리스크",
                severity="MEDIUM",
                description=f"주수탁은행 집중도 {primary_share:.1f}%",
            )
        )

    # 3) 유동성 리스크 (단순 비율: 준비금 / 유통량)
    if on_chain.supply.net_circulation > 0:
        liquidity_ratio = (
            off_chain.total_reserves / on_chain.supply.net_circulation * 100
        )
    else:
        liquidity_ratio = 0.0

    if liquidity_ratio < LIQUIDITY_MIN_RATIO:
        risk_factors.append(
            RiskFactor(
                category="유동성 리스크",
                severity="HIGH",
                description=f"준비금 대비 유통량 기준 유동성 비율 {liquidity_ratio:.1f}%",
            )
        )

    # 4) coverage_ratio 기반 전체 리스크 레벨 결정
    cr = coverage.coverage_ratio
    thresholds = RISK_LEVEL_THRESHOLDS  # {"LOW": ..., "MEDIUM": ..., "HIGH": ...}

    if cr >= thresholds["LOW"]:
        risk_level = "LOW"
    elif cr >= thresholds["MEDIUM"]:
        risk_level = "MEDIUM"
    elif cr >= thresholds["HIGH"]:
        risk_level = "HIGH"
    else:
        risk_level = "CRITICAL"

    return risk_level, risk_factors


# ====================================================
# 3. 권고사항 생성
# ====================================================
def generate_recommendations(
    risk_level: str,
    risk_factors: List[RiskFactor],
    coverage: CoverageCheck,
) -> List[str]:
    """
    권고사항 생성
    """
    recs: List[str] = []

    # 전반적인 리스크 레벨에 따른 기본 권고
    if risk_level in ("HIGH", "CRITICAL"):
        recs.append("긴급 위원회 소집 및 담보 보충 계획 수립")
        recs.append("신규 KRWS 발행 속도 조절 또는 일시 중단 검토")

    # 집중도 리스크가 있으면
    if any(r.category == "집중도 리스크" for r in risk_factors):
        recs.append("주수탁은행 외 보조수탁 및 기타 기관으로 자산 분산 검토")

    # 유동성 리스크가 있으면
    if any(r.category == "유동성 리스크" for r in risk_factors):
        recs.append("단기 국채·MMF 일부를 현금화하여 유동성 비율 개선")

    # 담보율에 따른 모니터링 강도
    if risk_level == "LOW":
        recs.append("현재 운영 체제 유지")
        recs.append("일일 1회 담보율 모니터링")
    elif risk_level == "MEDIUM":
        recs.append("일일 2회 담보율 모니터링 및 경보 시스템 점검")
    else:  # HIGH, CRITICAL
        recs.append("상시(실시간) 모니터링 체제로 전환")

    if not recs:
        recs.append("정상 운영 중 - 현행 유지")

    return recs


# ====================================================
# 4. 리스크 리포트 생성
# ====================================================
def create_risk_report(
    on_chain: OnChainState,
    off_chain: OffChainReserves,
    coverage: CoverageCheck,
    format_type: str = "detailed",
) -> RiskReport:
    """
    종합 리스크 리포트 생성

    Args:
        on_chain: 온체인 상태
        off_chain: 오프체인 준비금
        coverage: 담보 검증 결과
        format_type: "summary" or "detailed" (현재 구조는 동일, 표현만 달리 사용 가능)

    Returns:
        RiskReport: 종합 리스크 리포트
    """
    risk_level, risk_factors = analyze_risk(on_chain, off_chain, coverage)
    recommendations = generate_recommendations(risk_level, risk_factors, coverage)

    # 기관 집중도 계산
    total_reserves = off_chain.total_reserves
    if total_reserves > 0:
        primary_total = sum(
            c.balance for c in off_chain.institutions.primary_custodians
        )
        primary_share = primary_total / total_reserves * 100
    else:
        primary_share = 0.0

    key_metrics = {
        "coverage_ratio": coverage.coverage_ratio,
        "excess_collateral": coverage.excess_collateral,
        "onchain_circulation": coverage.onchain_circulation,
        "offchain_reserves": coverage.offchain_reserves,
        "primary_share": primary_share,
        "total_supply": on_chain.supply.total,
    }

    if risk_level in ("LOW", "MEDIUM"):
        overall_status = "HEALTHY"
    elif risk_level == "HIGH":
        overall_status = "WARNING"
    else:
        overall_status = "CRITICAL"

    summary = RiskSummary(
        risk_level=risk_level,
        overall_status=overall_status,
        key_metrics=key_metrics,
    )

    timestamp = datetime.now().isoformat()

    # format_type이 "summary"여도 구조는 동일하게 두고,
    # 프론트에서 필요한 부분만 선택적으로 사용하면 된다.
    return RiskReport(
        summary=summary,
        risk_factors=risk_factors,
        recommendations=recommendations,
        timestamp=timestamp,
    )