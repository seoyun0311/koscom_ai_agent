# app_mcp/graph/mcp_flow_interrupt.py

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict

from app_mcp.core.db import get_db
from app_mcp.crud import human_review as crud_hr
from app_mcp.services.notifications import send_slack_human_review_request

logger = logging.getLogger(__name__)


async def _handle_human_review_interrupt_async(
    state: Dict[str, Any],
    thread_id: str | None,
) -> None:
    """
    실제로 DB에 HumanReviewTask 만들고,
    Slack으로 Human Review 요청 보내는 비동기 처리 함수.
    """
    period = state.get("period", "unknown-period")
    summary = state.get("summary") or {}

    # 보고서 경로 (generate_report에서 세팅됨)
    report_path = state.get("report_path") or ""

    # Slack용 summary 가공
    coll = state.get("collateral_monthly", {}) or {}
    peg = state.get("peg_monthly", {}) or {}
    liq = state.get("liquidity_monthly", {}) or {}
    por = state.get("por_monthly", {}) or {}
    cons = state.get("consistency", {}) or {}

    summary_for_slack: Dict[str, Any] = {
        "final_grade": summary.get("final_grade", "N/A"),
        "collateral_grade": coll.get("grade", "N/A"),
        "peg_grade": peg.get("grade", "N/A"),
        "liquidity_grade": liq.get("grade", "N/A"),
        "por_grade": por.get("grade", "N/A"),
        # 일단 consistency 이슈를 risk_flags처럼 넘겨줌
        "risk_flags": cons.get("issues", []),
    }

    # DB에 HumanReviewTask 생성
    async with get_db() as db:
        task = await crud_hr.create_task(
            db,
            period=period,
            report_path=report_path,
            summary_json=json.dumps(summary, ensure_ascii=False),
            flow_run_id=thread_id,
            checkpoint_id=None,  # 필요하면 나중에 체크포인트 ID도 저장 가능
        )

    # Slack에 Human Review 요청 발송
    slack_res = send_slack_human_review_request(
        period=period,
        task_id=task.id,
        summary=summary_for_slack,
        report_path=report_path,
    )

    logger.info(
        "[HumanReviewInterrupt] task_id=%s, period=%s, slack_result=%s",
        task.id,
        period,
        slack_res,
    )


def on_human_review_interrupt(interrupt_event: Any) -> None:
    """
    LangGraph의 on_interrupt 훅.

    compile_mcp_monthly_graph(...).on_interrupt(on_human_review_interrupt)
    로 등록되어 있고,
    'human_review' 직전에 interrupt가 발생하면 이 함수가 호출된다.
    """
    try:
        checkpoint = getattr(interrupt_event, "checkpoint", None) or {}
        state = (checkpoint.get("state") or {}).get("values") or {}
        config = checkpoint.get("config") or {}
        configurable = config.get("configurable") or {}

        thread_id = configurable.get("thread_id")

        # 비동기 처리로 DB + Slack 실행
        asyncio.create_task(
            _handle_human_review_interrupt_async(state, thread_id)
        )

        logger.info(
            "[HumanReviewInterrupt] triggered for period=%s, thread_id=%s",
            state.get("period"),
            thread_id,
        )

    except Exception as e:
        logger.error("[HumanReviewInterrupt] failed: %s", e, exc_info=True)
