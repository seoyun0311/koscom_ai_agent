"""
Tool 3: check_coverage
담보율 계산 및 검증 (최신 Supply 구조 대응)
"""

from typing import Optional
from core.types import OnChainState, OffChainReserves, CoverageCheck
from core.calculator import calculate_coverage
from app_mcp.tools.onchain import get_onchain_state
from app_mcp.tools.offchain import get_offchain_reserves


def check_coverage(
    on_chain: Optional[OnChainState] = None,
    off_chain: Optional[OffChainReserves] = None,
    scenario: str = "normal"
) -> CoverageCheck:
    """
    담보율 계산 및 검증
    
    Args:
        on_chain: 온체인 상태 (없으면 자동 조회)
        off_chain: 오프체인 준비금 (없으면 자동 조회)
        scenario: 시나리오 선택
        
    Returns:
        CoverageCheck: 담보율 검증 결과
    """

    # 1) 데이터가 없으면 자동 조회
    if on_chain is None:
        on_chain = get_onchain_state(scenario=scenario)

    if off_chain is None:
        off_chain = get_offchain_reserves(scenario=scenario)

    if on_chain is None or off_chain is None:
        raise ValueError("온체인 또는 오프체인 데이터가 없습니다.")

    # 2) calculate_coverage 함수에 객체 전체를 전달
    #    (calculator.py의 함수가 OnChainState, OffChainReserves를 받음)
    coverage_result = calculate_coverage(on_chain, off_chain)

    print(f"✅ 담보율 계산 완료: {coverage_result.coverage_ratio:.2f}%")
    
    return coverage_result