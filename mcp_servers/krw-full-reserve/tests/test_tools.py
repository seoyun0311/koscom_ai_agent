"""
4개 Tool 테스트
"""

import pytest
from app_mcp.tools import (
    get_onchain_state,
    get_offchain_reserves,
    check_coverage,
    get_risk_report
)
from core.types import CoverageStatus, RiskLevel


class TestOnChainTool:
    """Tool 1: get_onchain_state 테스트"""
    
    def test_get_onchain_state_normal(self):
        """정상 시나리오 테스트"""
        result = get_onchain_state(scenario="normal")
        
        assert result is not None
        assert result.token_info.symbol == "KRWS"
        assert result.supply.total == 10_000_000_000
        assert result.issuer == "KOSCOM"
    
    def test_get_onchain_state_with_refresh(self):
        """캐시 갱신 테스트"""
        result1 = get_onchain_state(scenario="normal")
        result2 = get_onchain_state(scenario="normal", refresh=True)
        
        # 둘 다 유효한 데이터여야 함
        assert result1.supply.total == result2.supply.total


class TestOffChainTool:
    """Tool 2: get_offchain_reserves 테스트"""
    
    def test_get_offchain_reserves_normal(self):
        """정상 시나리오 테스트"""
        result = get_offchain_reserves(scenario="normal")
        
        assert result is not None
        assert result.total_reserves == 10_500_000_000
        assert len(result.institutions.primary_custodians) == 2
        assert result.institutions.primary_custodians[0].name == "신한은행"
    
    def test_get_offchain_reserves_warning(self):
        """주의 시나리오 테스트"""
        result = get_offchain_reserves(scenario="warning")
        
        assert result.total_reserves == 9_900_000_000  # 1억 부족


class TestCoverageTool:
    """Tool 3: check_coverage 테스트"""
    
    def test_check_coverage_normal(self):
        """정상 시나리오 - 105% 담보"""
        result = check_coverage(scenario="normal")
        
        assert result.coverage_ratio == 105.0
        assert result.status == CoverageStatus.OVER_COLLATERALIZED
        assert result.verdict.is_compliant is True
        assert result.surplus == 500_000_000  # 5억 초과
    
    def test_check_coverage_warning(self):
        """주의 시나리오 - 99% 담보"""
        result = check_coverage(scenario="warning")
        
        assert result.coverage_ratio == 99.0
        assert result.status == CoverageStatus.FULLY_BACKED
        assert result.verdict.is_compliant is True
        assert "주의 필요" in result.verdict.message
    
    def test_check_coverage_critical(self):
        """위험 시나리오 - 97% 담보"""
        result = check_coverage(scenario="critical")
        
        assert result.coverage_ratio == 97.0
        assert result.status == CoverageStatus.UNDER_COLLATERALIZED
        assert result.verdict.is_compliant is False
        assert "긴급 조치" in result.verdict.message
        assert result.verdict.required_action is not None


class TestRiskReportTool:
    """Tool 4: get_risk_report 테스트"""
    
    def test_get_risk_report_normal(self):
        """정상 시나리오 리포트"""
        result = get_risk_report(scenario="normal", format_type="detailed")
        
        assert result.report_id.startswith("KRWS-AUDIT-")
        assert result.summary.risk_level == RiskLevel.LOW
        assert result.summary.coverage_ratio == 105.0
        assert result.compliance_status.regulatory_compliance is True
        assert len(result.recommendations) > 0
    
    def test_get_risk_report_critical(self):
        """위험 시나리오 리포트"""
        result = get_risk_report(scenario="critical", format_type="detailed")
        
        assert result.summary.risk_level == RiskLevel.CRITICAL
        assert len(result.risk_factors) > 0
        
        # 담보 부족 리스크가 있어야 함
        has_collateral_risk = any(
            rf.category == "담보 부족" for rf in result.risk_factors
        )
        assert has_collateral_risk is True
    
    def test_get_risk_report_summary_format(self):
        """요약 형식 테스트"""
        result = get_risk_report(scenario="normal", format_type="summary")
        
        assert result.summary is not None
        assert result.risk_factors is not None
        assert result.recommendations is not None


class TestFullFlow:
    """전체 플로우 테스트"""
    
    def test_full_verification_flow(self):
        """Tool 1 → 2 → 3 → 4 순차 실행"""
        scenario = "normal"
        
        # Step 1: 온체인 데이터 조회
        on_chain = get_onchain_state(scenario=scenario)
        assert on_chain.supply.total == 10_000_000_000
        
        # Step 2: 오프체인 데이터 조회
        off_chain = get_offchain_reserves(scenario=scenario)
        assert off_chain.total_reserves == 10_500_000_000
        
        # Step 3: 담보율 검증
        coverage = check_coverage(on_chain=on_chain, off_chain=off_chain)
        assert coverage.coverage_ratio == 105.0
        assert coverage.verdict.is_compliant is True
        
        # Step 4: 리스크 리포트 생성
        report = get_risk_report(
            on_chain=on_chain,
            off_chain=off_chain,
            coverage=coverage
        )
        assert report.summary.risk_level == RiskLevel.LOW
        assert report.compliance_status.regulatory_compliance is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])