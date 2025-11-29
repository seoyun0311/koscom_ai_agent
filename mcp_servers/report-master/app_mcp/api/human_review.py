# app_mcp/api/human_review.py
import os
from app_mcp.core.config import ARTIFACTS_DIR

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app_mcp.core.db import async_session, get_db_session
from app_mcp.crud import human_review as crud_hr
from app_mcp.services.human_review_service import resume_human_review_flow
from app_mcp.services.notifications import send_email_monthly_report


class HumanReviewSubmit(BaseModel):
    thread_id: str
    decision: str  # "approve" | "reject"
    comment: str | None = None


router = APIRouter(prefix="/mcp/review", tags=["mcp-review"])


# -------------------------------
# GET /pending  (변경 없음)
# -------------------------------
@router.get("/pending")
async def get_pending_review(
    thread_id: str = Query(...),
    db: AsyncSession = Depends(get_db_session),
):
    task = await crud_hr.get_task_by_thread_id(db, thread_id)
    if not task:
        raise HTTPException(404, "No pending review task for this thread_id")

    return {
        "thread_id": task.flow_run_id,
        "period": task.period,
        "report_path": task.report_path,
        "summary_json": task.summary_json,
        "decision_needed": True,
        "checkpoint_id": task.checkpoint_id,
    }


# =====================================================
# 🔥 POST version — main entrypoint for manual submit
# =====================================================
@router.post("/submit")
async def submit_review(
    body: HumanReviewSubmit,
    db: AsyncSession = Depends(get_db_session),
):
    """
    (POST 버전) thread_id 기준 수동 제출용.
    Slack 모달에서 오는 것도 여기를 타게 할 예정.
    """
    # 0) 들어온 decision 검증
    raw_decision = body.decision  # "approve" | "reject" | "revise"
    if raw_decision not in {"approve", "reject", "revise"}:
        raise HTTPException(status_code=400, detail=f"Invalid decision: {raw_decision}")

    # LangGraph에 넘길 값: approve / revise 두 가지만 사용
    flow_decision = "approve" if raw_decision == "approve" else "revise"

    task = await crud_hr.get_task_by_thread_id(db, body.thread_id)
    if not task:
        raise HTTPException(status_code=404, detail="No pending task for this thread_id")

    # LangGraph resume
    try:
        final_state = await resume_human_review_flow(
            thread_id=body.thread_id,
            decision=flow_decision,   # 🔥 여기서 "revise"로 바꿔서 넘김
            comment=body.comment,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Resume failed: {e}")

    await crud_hr.mark_task_completed(db, task.id)

    return {
        "status": "resumed",
        "thread_id": body.thread_id,
        "decision": raw_decision,     # 바깥엔 사용자가 선택한 값 그대로 보여줌
        "flow_decision": flow_decision,
        "final_state": final_state,
    }
# =====================================================
# 🔥 GET version — Slack button redirect backend
# =====================================================
@router.get("/submit")
async def submit_human_review(
    task_id: int = Query(...),
    decision: str = Query(...),   # Slack: "approve" or "reject"
    comment: Optional[str] = Query(None),
):
    raw_decision = decision
    if raw_decision not in {"approve", "reject"}:
        raise HTTPException(400, f"Invalid decision: {raw_decision}")

    db_decision = "approved" if raw_decision == "approve" else "rejected"
    lg_decision = "approve" if raw_decision == "approve" else "revise"

    try:
        async with async_session() as db:
            task = await crud_hr.get_task(db, task_id)
            if not task:
                raise HTTPException(404, "Invalid task_id")

            # DB 기록
            await crud_hr.decide_task(
                db,
                task_id=task_id,
                decision=db_decision,
                comment=comment,
                reviewer="Slack-User",
            )

            # LangGraph resume
            try:
                final_state = await resume_human_review_flow(
                    thread_id=task.flow_run_id,
                    decision=lg_decision,
                    comment=comment,
                )
            except Exception as e:
                return JSONResponse(
                    status_code=500,
                    content={
                        "ok": False,
                        "task_id": task_id,
                        "decision": raw_decision,
                        "error": f"LangGraph resume failed: {e}",
                    },
                )

        return {
            "ok": True,
            "task_id": task_id,
            "decision_user": raw_decision,
            "decision_db": db_decision,
            "decision_lg": lg_decision,
            "result": "Flow resumed successfully",
        }

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "task_id": task_id,
                "decision": raw_decision,
                "error": f"Internal error: {e}",
            },
        )