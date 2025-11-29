"""
Mock Data Generator - Fixed Version
음수 market_value 버그 수정
"""

import random
from datetime import datetime
from typing import Literal
from core.types import (
    OnChainState, 
    OffChainReserves, 
    Supply,
    Institutions,
    Custodian,
    Security
)


class MockDataGenerator:
    """
    실시간 Mock 데이터 생성기
    매번 호출 시 다른 값 반환 (시간에 따라 변화)
    """
    
    # 금융기관 목록
    PRIMARY_CUSTODIANS = [
        {"name": "신한은행", "code": "SH", "type": "primary"},
        {"name": "KB국민은행", "code": "KB", "type": "primary"},
    ]
    
    SECONDARY_CUSTODIANS = [
        {"name": "KDB산업은행", "code": "KDB", "type": "secondary"},
        {"name": "NH투자증권", "code": "NH", "type": "secondary"},
        {"name": "한국예탁결제원", "code": "KSD", "type": "secondary"},
    ]
    
    def __init__(self, scenario: str = "normal"):
        """
        Args:
            scenario: "normal", "warning", "critical"
        """
        self.scenario = scenario
    
    def generate_onchain_state(self) -> OnChainState:
        """
        온체인 상태 생성 (실시간 변화)
        
        Returns:
            OnChainState: 블록체인 상태
        """
        # 시나리오별 기본값
        if self.scenario == "critical":
            base_total = 15_000_000_000  # 150억 (과다 발행)
            base_burned = 500_000_000    # 5억 (적은 소각)
        elif self.scenario == "warning":
            base_total = 12_000_000_000  # 120억
            base_burned = 1_000_000_000  # 10억
        else:  # normal
            base_total = 10_000_000_000  # 100억
            base_burned = 1_500_000_000  # 15억
        
        # ✅ 실시간 변동 (항상 양수 보장)
        total_supply = max(0, base_total + random.randint(-100_000_000, 100_000_000))
        burned = max(0, base_burned + random.randint(-50_000_000, 50_000_000))
        net_circulation = max(0, total_supply - burned)
        
        return OnChainState(
            supply=Supply(
                total=total_supply,
                burned=burned,
                net_circulation=net_circulation
            ),
            contract_address="0x1234567890abcdef1234567890abcdef12345678",
            block_number=random.randint(18_000_000, 18_100_000),
            timestamp=datetime.now().isoformat()
        )
    
    def generate_offchain_reserves(self) -> OffChainReserves:
        """
        오프체인 준비금 생성 (실시간 변화)
        
        Returns:
            OffChainReserves: 금융기관 담보 데이터
        """
        # 시나리오별 기본 배분 비율
        if self.scenario == "critical":
            # 담보 부족 시나리오
            primary_base = [3_000_000_000, 2_500_000_000]
            secondary_base = [1_500_000_000, 1_000_000_000, 500_000_000]
        elif self.scenario == "warning":
            # 경고 시나리오
            primary_base = [4_000_000_000, 3_500_000_000]
            secondary_base = [2_000_000_000, 1_500_000_000, 1_000_000_000]
        else:  # normal
            # 정상 시나리오 (충분한 담보)
            primary_base = [4_500_000_000, 4_000_000_000]
            secondary_base = [2_500_000_000, 2_000_000_000, 1_500_000_000]
        
        # 주수탁은행 생성
        primary_custodians = []
        for i, custodian_info in enumerate(self.PRIMARY_CUSTODIANS):
            base = primary_base[i]
            
            # ✅ 실시간 변동 (항상 양수 보장)
            balance = max(0, base + random.randint(-200_000_000, 200_000_000))
            
            securities = self._generate_securities(
                custodian_info["name"],
                custodian_info["code"],
                balance
            )
            
            primary_custodians.append(Custodian(
                name=custodian_info["name"],
                code=custodian_info["code"],
                balance=balance,
                securities=securities
            ))
        
        # 부수탁은행 생성
        secondary_custodians = []
        for i, custodian_info in enumerate(self.SECONDARY_CUSTODIANS):
            base = secondary_base[i]
            
            # ✅ 실시간 변동 (항상 양수 보장)
            balance = max(0, base + random.randint(-100_000_000, 100_000_000))
            
            securities = self._generate_securities(
                custodian_info["name"],
                custodian_info["code"],
                balance
            )
            
            secondary_custodians.append(Custodian(
                name=custodian_info["name"],
                code=custodian_info["code"],
                balance=balance,
                securities=securities
            ))
        
        # 총 준비금 계산
        total_reserves = sum(c.balance for c in primary_custodians + secondary_custodians)
        
        return OffChainReserves(
            total_reserves=total_reserves,
            institutions=Institutions(
                primary_custodians=primary_custodians,
                secondary_custodians=secondary_custodians
            ),
            timestamp=datetime.now().isoformat()
        )
    
    def _generate_securities(
        self, 
        custodian_name: str, 
        custodian_code: str,
        total_balance: int
    ) -> list[Security]:
        """
        보관 증권 생성 (예금, 국채, 회사채)
        
        Args:
            custodian_name: 보관 기관명
            custodian_code: 보관 기관 코드
            total_balance: 총 잔액
        
        Returns:
            list[Security]: 증권 리스트
        """
        securities = []
        
        # 예금 (60-70%)
        deposit_ratio = random.uniform(0.60, 0.70)
        deposit_value = max(0, int(total_balance * deposit_ratio))
        
        securities.append(Security(
            custodian_name=custodian_name,
            custodian_code=custodian_code,
            security_type="deposit",
            market_value=deposit_value,
            book_value=deposit_value,  # 예금은 시가=장부가
            verification_date=datetime.now().isoformat()
        ))
        
        # 국채 (20-30%)
        treasury_ratio = random.uniform(0.20, 0.30)
        treasury_market = max(0, int(total_balance * treasury_ratio))
        # ✅ 국채는 시가와 장부가가 약간 다를 수 있음 (항상 양수)
        treasury_book = max(0, int(treasury_market * random.uniform(0.98, 1.02)))
        
        securities.append(Security(
            custodian_name=custodian_name,
            custodian_code=custodian_code,
            security_type="treasury_bond",
            market_value=treasury_market,
            book_value=treasury_book,
            verification_date=datetime.now().isoformat()
        ))
        
        # 회사채 (5-15%)
        remaining = max(0, total_balance - deposit_value - treasury_market)
        corporate_market = remaining
        # ✅ 회사채는 변동성이 더 큼 (항상 양수)
        corporate_book = max(0, int(corporate_market * random.uniform(0.95, 1.05)))
        
        securities.append(Security(
            custodian_name=custodian_name,
            custodian_code=custodian_code,
            security_type="corporate_bond",
            market_value=corporate_market,
            book_value=corporate_book,
            verification_date=datetime.now().isoformat()
        ))
        
        return securities
    
def get_mock_data(scenario: Literal["normal", "warning", "critical"] = "normal"):
      generator = MockDataGenerator(scenario=scenario)
      onchain = generator.generate_onchain_state()
      offchain = generator.generate_offchain_reserves()
      return {
          "onchain": onchain,
          "offchain": offchain,
  }