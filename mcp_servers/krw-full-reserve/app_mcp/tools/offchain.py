"""
Tool 2: get_offchain_reserves
금융기관에서 오프체인 준비금 조회 (백엔드 API 연동)
"""

import requests
from typing import Optional
from datetime import datetime
from config.api_config import API_ENDPOINTS, API_TIMEOUT
from core.types import (
    Custodian,
    OffChainReserves,
    InstitutionGroup,
    APIError,
    CreditRating,
)


def get_offchain_reserves(
    refresh: bool = True,
    scenario: str = "normal",
    institution_filter: Optional[str] = None
) -> Optional[OffChainReserves]:
    """
    오프체인 준비금 조회 
    
    Args:
        refresh: True일 경우 최신 데이터 조회 (기본값: True - 실시간)
        scenario: 시나리오 선택 (API에서는 현재 미사용)
        institution_filter: 특정 기관만 조회 (현재는 전체 조회만 지원)
    
    Returns:
        OffChainReserves: 금융기관 담보 데이터 
    
    Examples:
        >>> reserves = get_offchain_reserves()
        >>> print(f"총 준비금: {reserves.total_reserves:,.0f}원")
        총 준비금: 300,000원
        
        >>> # 은행별 정보
        >>> for custodian in reserves.institutions.primary_custodians:
        ...     print(f"{custodian.name}: {custodian.balance:,.0f}원")
        신한은행: 100,000원
        국민은행: 100,000원
    
    Raises:
        APIError: API 호출 실패 시
    """
    try:
        # /banks 엔드포인트에서 은행 준비금 데이터 가져오기
        response = requests.get(
            API_ENDPOINTS["banks"],
            timeout=API_TIMEOUT
        )
        response.raise_for_status()
        data = response.json()
        
        # 백엔드 응답 구조:
        # {
        #   "ok": true,
        #   "banks": [
        #     {"id": "shinhan", "name": "신한은행", "balance": 100000, "weight": 0.33},
        #     ...
        #   ],
        #   "totalReserves": 300000,
        #   "hhi": 0.3333
        # }
        
        # Custodian 객체 생성
        custodians = []
        for bank in data["banks"]:
            custodian = Custodian(
                id=bank["id"],
                name=bank["name"],
                balance=bank["balance"],
                credit_rating=CreditRating.AA_MINUS,  # 백엔드에 신용등급 없으면 기본값
                risk_weight=bank["weight"]
            )
            custodians.append(custodian)
        
        # OffChainReserves 객체 구성
        off_chain = OffChainReserves(
            total_reserves=data["totalReserves"],
            institutions=InstitutionGroup(
                primary_custodians=custodians,
                secondary_custodians=[]  # 백엔드에 2차 기관 없으면 빈 리스트
            ),
            timestamp=datetime.now().isoformat()  # ← 필수 필드 추가, ISO 형식 문자열
        )
        
        print(f"✅ 오프체인 데이터 조회 성공: 총 준비금 {off_chain.total_reserves:,.0f}원")
        return off_chain
        
    except requests.RequestException as e:
        print(f"❌ API 호출 실패 (/banks): {e}")
        raise APIError(f"오프체인 데이터 조회 실패: {e}")
    except KeyError as e:
        print(f"❌ API 응답 형식 오류: {e}")
        raise APIError(f"API 응답에 필수 필드 누락: {e}")
    except Exception as e:
        print(f"❌ 예상치 못한 오류: {e}")
        raise APIError(f"오프체인 데이터 처리 실패: {e}")