# bank.py
from typing import Any, Dict
import httpx

from core.config.dart import get_dart_settings  # API key 로드용

# DART API endpoint
DART_API_BASE = "https://opendart.fss.or.kr/api/fnlttSinglAcnt.json"

# 🔐 DART API KEY 로드
DART_API_KEY = get_dart_settings().api_key


def register(mcp):
    """
    FastMCP 서버에 DART 단일계정 조회 도구를 등록.
    """
    async def get_dart_major_accounts(
        corp_code: str,
        bsns_year: str,
        reprt_code: str = "11011",
    ) -> Dict[str, Any]:
        """
        DART '단일회사 주요계정' API 호출
        Parameters:
            corp_code (str): DART 고유번호
            bsns_year (str): 검색 연도
            reprt_code (str): 보고서 코드 (기본: 사업보고서 11011)
        """
        params = {
            "crtfc_key": DART_API_KEY,
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(DART_API_BASE, params=params)
            response.raise_for_status()
            return response.json()

    # MCP 도구로 등록
    mcp.add_tool(
        get_dart_major_accounts,
        name="get_dart_major_accounts",
        description="DART 단일회계 주요계정(fnlttSinglAcnt) API를 호출합니다."
    )
