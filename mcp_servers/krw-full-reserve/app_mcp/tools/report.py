"""
Tool 4: get_risk_report
종합 리스크 리포트 생성
"""

from typing import Optional
from core.types import OnChainState, OffChainReserves, CoverageCheck, RiskReport
from core.calculator import create_risk_report
from app_mcp.tools.onchain import get_onchain_state
from app_mcp.tools.offchain import get_offchain_reserves
from app_mcp.tools.coverage import check_coverage


def get_risk_report(
    on_chain: Optional[OnChainState] = None,
    off_chain: Optional[OffChainReserves] = None,
    coverage: Optional[CoverageCheck] = None,
    scenario: str = "normal",
    format_type: str = "detailed"
) -> RiskReport:
    """
    종합 리스크 리포트 생성
    
    Args:
        on_chain: 온체인 데이터 (None이면 자동 조회)
        off_chain: 오프체인 데이터 (None이면 자동 조회)
        coverage: 담보 검증 데이터 (None이면 자동 계산)
        scenario: 시나리오 선택 ("normal", "warning", "critical")
        format_type: "summary" (요약) 또는 "detailed" (상세)
    
    Returns:
        RiskReport: 종합 리스크 리포트
    
    Examples:
        >>> # 자동 모드 (모든 데이터 자동 생성)
        >>> report = get_risk_report(scenario="normal")
        >>> print(f"리스크 레벨: {report.summary.risk_level}")
        리스크 레벨: LOW
        
        >>> # 요약 모드
        >>> report = get_risk_report(scenario="critical", format_type="summary")
        >>> for risk in report.risk_factors:
        ...     print(f"- {risk.category}: {risk.description}")
        - 담보 부족: 담보율 97.00%로 기준 미달
        
        >>> # 수동 모드 (데이터 미리 조회)
        >>> on_chain = get_onchain_state()
        >>> off_chain = get_offchain_reserves()
        >>> coverage = check_coverage(on_chain, off_chain)
        >>> report = get_risk_report(on_chain, off_chain, coverage)
        >>> print(report.recommendations)
        ['현재 운영 체제 유지', '일일 1회 담보율 모니터링']
    """
    # 데이터가 제공되지 않으면 자동 조회
    if on_chain is None:
        on_chain = get_onchain_state(scenario=scenario)
    
    if off_chain is None:
        off_chain = get_offchain_reserves(scenario=scenario)
    
    if coverage is None:
        coverage = check_coverage(on_chain, off_chain, scenario=scenario)
    
    if on_chain is None or off_chain is None or coverage is None:
        raise ValueError(
            "필요한 데이터가 없습니다. "
            "get_onchain_state(), get_offchain_reserves(), check_coverage()를 먼저 호출하세요."
        )
    
    # 리스크 리포트 생성
    report = create_risk_report(on_chain, off_chain, coverage, format_type)
    
    return report