# app_mcp/api/reports.py
from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException

from app_mcp.graph.mcp_flow import run_monthly_mcp_flow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/ping")
async def ping_reports():
    """
    단순 헬스체크용 엔드포인트.
    """
    return {"ok": True, "message": "reports api alive"}


@router.post("/generate/{period}")
async def generate_report(period: str):
    """
    👉 수동으로 월간 MCP 플로우를 실행해서
       해당 기간(YYYY-MM)의 보고서를 생성하는 엔드포인트.

    예시:
      POST /reports/generate/2025-11
    """
    try:
        logger.info("[API] Generating report via MCP flow for period=%s", period)

        # 🔥 run_monthly_mcp_flow 는 '동기 함수'라서 await 하면 안 됨!
        result = run_monthly_mcp_flow(period=period)

        # 안전하게 타입 한 번 체크
        if not isinstance(result, dict):
            logger.error(
                "[API] Unexpected result type from run_monthly_mcp_flow: %r",
                type(result),
            )
            raise RuntimeError("Unexpected result from MCP flow")

        logger.info(
            "[API] Report generated for %s: status=%s, path=%s",
            period,
            result.get("status"),
            result.get("report_path"),
        )
        # MCP 플로우가 만들어준 dict 그대로 반환
        return result

    except Exception as e:
        logger.exception(
            "[API] Failed to generate report for %s: %s", period, e
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate report for {period}: {e}",
        )
