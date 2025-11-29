"""
Tool 1: get_onchain_state
원화스테이블 운영 센터에서 K-WON 온체인 상태 조회 
"""

import requests
from typing import Optional
from datetime import datetime
from core.types import Supply, APIError, BlockInfo, OnChainState
from config.api_config import API_ENDPOINTS, API_TIMEOUT


def get_onchain_state(refresh: bool = True, scenario: str = "normal") -> Optional[OnChainState]:
    """
    온체인 상태 조회 
    
    Args:
        refresh: True일 경우 최신 데이터 조회 (기본값: True - 실시간)
        scenario: 시나리오 선택 (API에서는 현재 미사용)
    
    Returns:
        OnChainState: 온체인 데이터 (백엔드 API에서 가져옴)
    
    Examples:
        >>> state = get_onchain_state()
        >>> print(f"총 발행량: {state.supply.total:,.0f}원")
        총 발행량: 320,000원
    
    Raises:
        APIError: API 호출 실패 시
    """
    try:
        # 1. /status 엔드포인트에서 온체인 기본 정보 가져오기
        status_response = requests.get(
            API_ENDPOINTS["status"],
            timeout=API_TIMEOUT
        )
        status_response.raise_for_status()
        status_data = status_response.json()
        
        # 2. /metrics 엔드포인트에서 발행량 가져오기
        metrics_response = requests.get(
            API_ENDPOINTS["metrics"],
            timeout=API_TIMEOUT
        )
        metrics_response.raise_for_status()
        metrics_data = metrics_response.json()
        
        # 3. OnChainState 객체 구성
        on_chain = OnChainState(
            supply=Supply(
                total=metrics_data["supplyKRW"],
                circulating=metrics_data["supplyKRW"],
                locked=0,
                burned=0,
                net_circulation=metrics_data["supplyKRW"]  # ← 추가
            ),
            block=BlockInfo(
                number=0,  # 블록 번호 (백엔드 API에 없으면 0)
                timestamp=datetime.now().isoformat(),  # ISO 형식 문자열로 변경
                hash="0x" + "0" * 64  # 더미 해시
            ),
            contract_address=status_data.get("tokenAddress", "0x0")  # ← 필드명 수정
        )
        
        print(f"✅ 온체인 데이터 조회 성공: 발행량 {on_chain.supply.total:,.0f}원")
        return on_chain
        
    except requests.RequestException as e:
        print(f"❌ API 호출 실패 (/status, /metrics): {e}")
        raise APIError(f"온체인 데이터 조회 실패: {e}")
    except KeyError as e:
        print(f"❌ API 응답 형식 오류: {e}")
        raise APIError(f"API 응답에 필수 필드 누락: {e}")
    except Exception as e:
        print(f"❌ 예상치 못한 오류: {e}")
        raise APIError(f"온체인 데이터 처리 실패: {e}")