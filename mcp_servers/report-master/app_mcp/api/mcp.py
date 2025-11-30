# app_mcp/api/mcp.py
import logging  

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession

from app_mcp.core.db import get_db
from app_mcp.graph.mcp_flow import mcp_graph_with_interrupt
from app_mcp.crud import human_review as crud_hr
import json
from app_mcp.api import realtime 

import requests
from app_mcp.core.config import get_settings

logger = logging.getLogger(__name__)  #  추가

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.post("/run")
async def run_mcp(
    period: str = Body(..., embed=True),   # ✅ JSON body { "period": "2025-10" } 로 받기
    db: AsyncSession = Depends(get_db),
):
    """
    월간 MCP 플로우 실행 (Human Review interrupt 포함)
    
    ✅ 초기 state에 필수 필드 포함
    """
    try:
        # ✅ 초기 state 구성 (필수 필드 포함)
        initial_state = {
            "period": period,
            "revision_count": 0,
            "max_revisions": 3,
            "human_decision": "pending",
            "human_feedback": None,
            "retry_counts": {},
            "max_retries": {"data_load": 3},
        }
        
        # human-review interrupt 버전 그래프 실행
        result = await mcp_graph_with_interrupt.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": f"monthly-{period}"}},
        )

        # 보고서 경로 / 요약 추출
        report_path: str = result.get("report_path", "")
        summary: dict = result.get("summary", {})

        # summary JSON 문자열로 저장
        summary_json = json.dumps(summary, ensure_ascii=False)

        # HumanReviewTask 생성 (pending 상태)
        review_task = await crud_hr.create_task(
            db,
            period=period,
            report_path=report_path,
            summary_json=summary_json,
            flow_run_id=f"monthly-{period}",
            checkpoint_id=None,
        )

        # ✅ Slack Human Review 요청 전송
        from app_mcp.services.notifications import send_slack_human_review_request
        
        notification_result = send_slack_human_review_request(
            period=period,
            task_id=review_task.id,
            summary=summary,
            report_path=report_path,
        )

        return {
            "ok": True,
            "period": period,
            "task_id": review_task.id,
            "notification": notification_result,
            "message": "Human review required. Check Slack for approval.",
        }

    except Exception as e:
        logger.exception("[run_mcp] Failed")
        raise HTTPException(status_code=500, detail=str(e))

def run_monthly_report_job():
    """
    APScheduler가 매월 1일 00:00에 실행하는 job
    
    ✅ /mcp/run 엔드포인트 호출 (period 자동 계산)
    """
    from datetime import datetime
    
    settings = get_settings()
    
    # ✅ 현재 월 자동 계산
    period = datetime.now().strftime("%Y-%m")
    
    url = f"http://{settings.app_host}:{settings.app_port}/mcp/run"
    
    try:
        resp = requests.post(
            url,
            json={"period": period},
            timeout=60,
        )
        logger.info(
            "[Scheduler] Monthly report job executed: status=%s, period=%s",
            resp.status_code,
            period,
        )
        logger.info("[Scheduler] Response: %s", resp.text)
    except Exception as e:
        logger.error("[Scheduler] Monthly report job failed: %s", e)
