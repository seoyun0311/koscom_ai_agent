# mcp/report_generator_routes.py

from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app_mcp.graph.mcp_flow import run_monthly_mcp_flow
from app_mcp.services.notifications import (
    # send_slack_monthly_summary,   # HIL 구조에서는 사용 X
    # send_email_monthly_report,    # 승인 이후에만 사용
    send_slack_human_review_request,
)
import logging

router = APIRouter(prefix="/mcp", tags=["mcp-generate"])
logger = logging.getLogger(__name__)


class GenerateReportRequest(BaseModel):
    period: Optional[str] = None


class GenerateReportResponse(BaseModel):
    period: str
    status: str
    report_path: str
    generated_at: datetime
    summary: Dict[str, Any]
    notifications: Dict[str, Any]


@router.post("/run_full", response_model=GenerateReportResponse)
def run_full_report(req: GenerateReportRequest):
    """
    LangGraph로 월간 보고서를 생성하고,
    바로 메일을 보내지 않고 'Human Review' Slack 메시지만 보내는 엔드포인트.

    최종 메일 전송은 /mcp/review/submit 에서
    승인(approve)일 때만 수행.
    """
    period = req.period or "2025-10"

    # 1) LangGraph 전체 파이프라인 실행
    try:
        final_state = run_monthly_mcp_flow(period=period)
    except Exception as e:
        logger.exception("[run_full_report] run_monthly_mcp_flow failed")
        raise HTTPException(
            status_code=500,
            detail=f"run_monthly_mcp_flow error: {e}",
        )

    summary = final_state.get("summary", {}) or {}
    report_path = final_state.get("report_path", "")

    now = datetime.utcnow()

    # 2) Human-in-the-loop용 Slack 알림 전송 (승인/반려 버튼 포함)
    human_review_notify: Dict[str, Any] = {"success": False, "error": None}

    try:
        # TODO: 실제로는 DB에서 task_id를 생성해서 저장하는 게 좋음
        task_id = 1

        human_review_notify = send_slack_human_review_request(
            period=period,
            task_id=task_id,
            summary=summary,
            report_path=report_path,
        )
    except Exception as e:
        logger.error("[run_full_report] Human Review Slack notify failed: %s", e)
        human_review_notify = {"success": False, "error": str(e)}

    notify_result = {
        "human_review": human_review_notify,
        # 나중에 필요하면 "summary_slack": ..., "email": ... 도 추가 가능
    }

    return GenerateReportResponse(
        period=period,
        status="waiting_review",  # <- HIL 대기 상태
        report_path=report_path,
        generated_at=now,
        summary=summary,
        notifications=notify_result,
    )
