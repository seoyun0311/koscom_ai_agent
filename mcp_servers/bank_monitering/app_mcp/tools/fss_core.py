# app_mcp/tools/fss_core.py
"""
순수 FSS 계산 공식 (Financial Safety Score)
- 어떤 모듈에서도 import 가능
- MCP Tool 아님
"""

from typing import Dict


def compute_fss(financials: Dict[str, float]) -> float:
    """
    FSS 계산 공식
    financials 예:
    {
        "equity_ratio": 0.092,
        "leverage": 10.8,
        "current_ratio": 1.05,
        "roe": 0.062
    }
    """

    eq = financials.get("equity_ratio") or 0     # 0~1
    lev = financials.get("leverage") or 15       # 자산/자본배수
    cur = financials.get("current_ratio") or 1
    roe = financials.get("roe") or 0

    score = 0

    # 자본비율 (최대 40점)
    score += min(eq * 400, 40)

    # 레버리지 (최대 30점)
    score += max(0, 30 - (lev - 8) * 3)

    # 유동비율 (최대 20점)
    score += min(cur * 20, 20)

    # ROE (최대 10점)
    score += min(roe * 100, 10)

    # 은행 신용평가 특성을 반영한 점수 클램핑
    score = max(20, min(score, 95))

    return score


def compute_fss(financials: Dict[str, float]) -> float:
    """
    Financial Safety Score (FSS)
    """

    # 원본 값 가져오기
    eq = financials.get("equity_ratio")
    lev = financials.get("leverage")
    cur = financials.get("current_ratio")
    roe = financials.get("roe")

    # ──────────────
    # 값 보정 (sanity checks)
    # ──────────────
    eq = eq if eq and eq > 0 else 0
    lev = lev if lev and lev > 0 else 15
    cur = cur if cur and cur > 0 else 1
    roe = roe if roe and roe > 0 else 0

    # leverage sanity clamp (은행권 평균 8~20)
    lev = max(5, min(lev, 50))

    # current ratio clamp
    cur = max(0, min(cur, 3.0))   # 대부분 0.8~1.2

    score = 0

    # 자본비율 (최대 40점)
    score += min(eq * 400, 40)

    # 레버리지 (최대 30점)
    score += max(0, 30 - (lev - 8) * 3)

    # 유동비율 (최대 20점)
    score += min(cur * 20, 20)

    # ROE (최대 10점)
    score += min(roe * 100, 10)

    # 최종 클램핑
    score = max(20, min(score, 95))

    return score
