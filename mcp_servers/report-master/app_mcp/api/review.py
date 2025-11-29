# app_mcp/api/review.py
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app_mcp.core.db import get_db
from app_mcp.crud import human_review as crud_hr
from app_mcp.schemas.human_review import (
    HumanReviewTaskListItem,
    HumanReviewTaskDetail,
    HumanReviewDecisionRequest,  # thread_id, decision, comment
  #  HumanReviewSubmit,           # Slack/외부용 단순 submit 용도 (thread_id 없는 버전이면 안 써도 됨)
)
from app_mcp.services.human_review_service import resume_human_review_flow
from app_mcp.services.notifications import send_email_monthly_report

router = APIRouter(
    prefix="/api/review",
    tags=["review"],
)

# ─────────────────────────────────────────────
# 1) API: JSON 기반 관리용 (리스트/상세/결정)
# ─────────────────────────────────────────────

@router.get("/tasks", response_model=List[HumanReviewTaskListItem])
async def list_review_tasks(
    status: Optional[str] = Query(None, description="pending / approved / rejected"),
    db: AsyncSession = Depends(get_db),
):
    tasks = await crud_hr.get_tasks(db, status=status)

    result: List[HumanReviewTaskListItem] = []
    for t in tasks:
        item = HumanReviewTaskListItem(
            id=t.id,
            period=t.period,
            status=t.status,
            report_path=t.report_path,
            created_at=t.created_at,
            final_grade=None,  # TODO: summary_json에서 파싱해도 됨
        )
        result.append(item)
    return result


@router.get("/tasks/{task_id}", response_model=HumanReviewTaskDetail)
async def get_review_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
):
    task = await crud_hr.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Review task not found")

    return HumanReviewTaskDetail.from_orm(task)


@router.post("/tasks/{task_id}/decide")
async def decide_review_task(
    task_id: int,
    body: HumanReviewDecisionRequest,
    db: AsyncSession = Depends(get_db),
):
    # DB 상태 업데이트
    task = await crud_hr.decide_task(
        db,
        task_id=task_id,
        decision=body.decision,
        comment=body.comment,
        reviewer=None,
    )
    if not task:
        raise HTTPException(status_code=404, detail="Review task not found")

    # LangGraph 재개 (flow_run_id 사용)
    if task.flow_run_id:
        try:
            await resume_human_review_flow(
                thread_id=task.flow_run_id,
                decision=body.decision,
                comment=body.comment,
            )
        except Exception as e:
            # 에러는 일단 로그로만
            print(f"[HumanReview] LangGraph resume failed: {e}")

    return {"ok": True, "status": task.status}


# ─────────────────────────────────────────────
# 2) 간단 웹 UI (브라우저에서 수동 승인/반려)
# ─────────────────────────────────────────────

@router.get("/ui", response_class=HTMLResponse)
async def review_ui(
    db: AsyncSession = Depends(get_db),
):
    tasks = await crud_hr.get_tasks(db, status="pending")

    rows = ""
    for t in tasks:
        rows += f"""
        <tr>
          <td>{t.id}</td>
          <td>{t.period}</td>
          <td>{t.status}</td>
          <td><a href="/api/review/ui/tasks/{t.id}">검토</a></td>
        </tr>
        """

    html = f"""
    <html>
    <head><title>Human Review Tasks</title></head>
    <body>
      <h1>Human Review 대기 목록</h1>
      <table border="1" cellspacing="0" cellpadding="4">
        <tr>
          <th>ID</th>
          <th>Period</th>
          <th>Status</th>
          <th>Action</th>
        </tr>
        {rows}
      </table>
    </body>
    </html>
    """
    return html


@router.get("/ui/tasks/{task_id}", response_class=HTMLResponse)
async def review_task_ui(
    task_id: int,
    db: AsyncSession = Depends(get_db),
):
    task = await crud_hr.get_task(db, task_id)
    if not task:
        return HTMLResponse("<h1>Task not found</h1>", status_code=404)

    html = f"""
    <html>
    <head><title>Review Task {task.id}</title></head>
    <body>
      <h1>리뷰 태스크 #{task.id}</h1>
      <p>Period: {task.period}</p>
      <p>Status: {task.status}</p>
      <p>Report: <a href="{task.report_path}">{task.report_path}</a></p>
      <form method="post" action="/api/review/ui/tasks/{task.id}/decide">
        <label>Decision:</label>
        <select name="decision">
          <option value="approve">approve</option>
          <option value="reject">reject</option>
        </select>
        <br/>
        <label>Comment:</label><br/>
        <textarea name="comment" rows="4" cols="50"></textarea>
        <br/>
        <button type="submit">제출</button>
      </form>
    </body>
    </html>
    """
    return html


@router.post("/ui/tasks/{task_id}/decide", response_class=HTMLResponse)
async def decide_review_task_ui(
    task_id: int,
    decision: str = Form(...),
    comment: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    task = await crud_hr.decide_task(
        db,
        task_id=task_id,
        decision=decision,
        comment=comment,
        reviewer=None,
    )
    if not task:
        return HTMLResponse("<h1>Task not found</h1>", status_code=404)

    return HTMLResponse(f"""
    <html>
    <body>
      <h1>결과 저장 완료</h1>
      <p>Task #{task.id} → {task.status}</p>
      <a href="/api/review/ui">목록으로 돌아가기</a>
    </body>
    </html>
    """)


# ─────────────────────────────────────────────
# 3) Slack 버튼용: GET /mcp/review/submit
#    → 버튼 클릭으로 바로 쓰는 엔드포인트
# ─────────────────────────────────────────────

from fastapi import APIRouter as _AR2
router_mcp = APIRouter(tags=["mcp-review"])


@router_mcp.get("/mcp/review/submit")
async def submit_human_review_get(
    task_id: int,
    decision: str,
    comment: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Slack 버튼에서 호출하는 간단 GET 버전.
    - /mcp/review/submit?task_id=1&decision=approve
    - /mcp/review/submit?task_id=1&decision=reject&comment=...
    """
    raw_decision = decision  # "approve" | "reject" | "approve_with_comment" 등

    if raw_decision not in {"approve", "reject", "revise", "approve_with_comment"}:
        raise HTTPException(status_code=400, detail=f"Invalid decision: {raw_decision}")

    # LangGraph에는 approve / revise만 넘김
    flow_decision = "approve" if raw_decision == "approve" or raw_decision == "approve_with_comment" else "revise"

    task = await crud_hr.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Review task not found")

    if not task.flow_run_id:
        raise HTTPException(status_code=400, detail="Task has no flow_run_id")

    # LangGraph 재개
    final_state = await resume_human_review_flow(
        thread_id=task.flow_run_id,
        decision=flow_decision,
        comment=comment,
    )

    # DB 상태 업데이트
    await crud_hr.decide_task(
        db,
        task_id=task_id,
        decision=raw_decision,
        comment=comment,
        reviewer=None,
    )

    # 승인인 경우에만 메일 발송
    email_result = None
    if flow_decision == "approve":
        summary = final_state.get("summary", {}) if isinstance(final_state, dict) else {}
        email_result = send_email_monthly_report(
            period=task.period,
            report_path=task.report_path,
            summary=summary,
        )

    return {
        "status": "ok",
        "task_id": task_id,
        "decision": raw_decision,
        "flow_decision": flow_decision,
        "email": email_result,
        "final_state": final_state,
    }


# 기존 POST /mcp/review/submit (JSON 버전)은 나중에 쓸 수 있게 남겨둬도 되고,
# 지금은 GET만 써도 충분

# 이 파일을 main에 include할 때:
# app.include_router(router)
# app.include_router(router_mcp)


# app_mcp/api/review.py (기존 코드에 추가)

@router.get("/history/{period}")
async def get_review_history(
    period: str,
    db: AsyncSession = Depends(get_db),
):
    """
    특정 기간의 리뷰 히스토리 조회
    - 누가 언제 승인/재생성/반려했는지
    - 몇 번 재생성되었는지
    """
    tasks = await crud_hr.get_tasks_by_period(db, period)
    
    if not tasks:
        raise HTTPException(status_code=404, detail="No review history found for this period")
    
    # 가장 최근 task 기준
    latest_task = tasks[0]
    
    # revision 히스토리 구성
    revision_history = []
    for task in tasks:
        if task.status in ["revised", "approved", "rejected"]:
            revision_history.append({
                "task_id": task.id,
                "status": task.status,
                "revision_no": task.revision_count,
                "decision": task.last_decision,
                "reviewer": task.reviewer,
                "comment": task.comment,
                "decided_at": task.decided_at.isoformat() if task.decided_at else None,
                "revised_at": task.last_revised_at.isoformat() if task.last_revised_at else None,
                "revised_by": task.last_revised_by,
            })
    
    return {
        "period": period,
        "task_id": latest_task.id,
        "status": latest_task.status,
        "revision_count": latest_task.revision_count,
        "last_decision": latest_task.last_decision,
        "reviewer": latest_task.reviewer,
        "final_comment": latest_task.comment,
        "decided_at": latest_task.decided_at.isoformat() if latest_task.decided_at else None,
        "created_at": latest_task.created_at.isoformat(),
        "revision_history": revision_history,
        "total_tasks": len(tasks),
    }