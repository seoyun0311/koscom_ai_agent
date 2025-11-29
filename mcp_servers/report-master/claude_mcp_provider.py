# claude_mcp_provider.py
from __future__ import annotations

import asyncio
import httpx
from mcp.server.fastmcp import FastMCP

# Claude에 표시될 MCP 서버 이름
mcp = FastMCP("k-won-mcp")

# FastAPI 백엔드 주소
MCP_BACKEND_URL = "http://127.0.0.1:8000"


# ─────────────────────────────────────
# 내부 함수: 백엔드 /mcp/run 호출
# ─────────────────────────────────────
async def _call_backend_run(period: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{MCP_BACKEND_URL}/mcp/run",
            params={"period": period},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()


# ─────────────────────────────────────
# Claude MCP Tool: run_monthly_report
# ─────────────────────────────────────
@mcp.tool()
async def run_monthly_report(period: str = "2025-10") -> dict:
    """
    월간 컴플라이언스 보고서를 실행하고 결과를 Claude에 반환.
    Claude에서:
        run_monthly_report {"period": "2025-10"}
    처럼 호출 가능.
    """
    result = await _call_backend_run(period)

    return {
        "period": period,
        "report_path": result.get("report_path"),
        "final_grade": result.get("summary", {}).get("final_grade"),
        "human_review_task_id": result.get("human_review_task_id"),
        "review_url": (
            f"{MCP_BACKEND_URL}/api/review/ui/tasks/{result.get('human_review_task_id')}"
            if result.get("human_review_task_id")
            else None
        ),
    }


# ─────────────────────────────────────
# MCP 서버 실행 (STDIO)
# ─────────────────────────────────────
if __name__ == "__main__":
    mcp.run()
