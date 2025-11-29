# app_mcp/crud/human_review.py

from datetime import datetime
from typing import Optional, List
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app_mcp.models.human_review_task import HumanReviewTask

logger = logging.getLogger(__name__)


async def create_task(
    db: AsyncSession,
    *,
    period: str,
    report_path: str,
    summary_json: str,
    flow_run_id: str,
    checkpoint_id: Optional[str] = None,
) -> HumanReviewTask:
    """HumanReviewTask 생성"""
    task = HumanReviewTask(
        period=period,
        status="pending",
        report_path=report_path,
        summary_json=summary_json,
        flow_run_id=flow_run_id,
        checkpoint_id=checkpoint_id,
        revision_count=0,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    
    logger.info(
        "[create_task] Created task_id=%s, period=%s, flow_run_id=%s",
        task.id,
        period,
        flow_run_id,
    )
    
    return task


async def get_task(db: AsyncSession, task_id: int) -> Optional[HumanReviewTask]:
    """ID로 task 조회"""
    result = await db.execute(
        select(HumanReviewTask).where(HumanReviewTask.id == task_id)
    )
    return result.scalar_one_or_none()


async def get_task_by_thread_id(
    db: AsyncSession,
    thread_id: str,
) -> Optional[HumanReviewTask]:
    """flow_run_id(thread_id)로 task 조회 (가장 최근 pending)"""
    result = await db.execute(
        select(HumanReviewTask)
        .where(HumanReviewTask.flow_run_id == thread_id)
        .where(HumanReviewTask.status.in_(["pending", "revised"]))
        .order_by(desc(HumanReviewTask.created_at))
    )
    return result.scalar_one_or_none()


async def get_tasks(
    db: AsyncSession,
    *,
    status: Optional[str] = None,
    period: Optional[str] = None,
) -> List[HumanReviewTask]:
    """task 목록 조회"""
    stmt = select(HumanReviewTask).order_by(desc(HumanReviewTask.created_at))
    
    if status:
        stmt = stmt.where(HumanReviewTask.status == status)
    if period:
        stmt = stmt.where(HumanReviewTask.period == period)
    
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def decide_task(
    db: AsyncSession,
    *,
    task_id: int,
    decision: str,  # "approved" | "rejected" | "revised"
    comment: Optional[str] = None,
    reviewer: Optional[str] = None,
    revision_count: Optional[int] = None,
) -> Optional[HumanReviewTask]:
    """
    task 상태 업데이트 (승인/반려/재생성)
    
    ✅ revision_count를 LangGraph에서 받아서 DB에 반영
    """
    task = await get_task(db, task_id)
    if not task:
        logger.warning("[decide_task] Task not found: task_id=%s", task_id)
        return None

    # 상태 업데이트
    if decision == "approved":
        task.status = "approved"
        task.last_decision = "approve"
        
    elif decision == "rejected":
        task.status = "rejected"
        task.last_decision = "reject"
        
    elif decision == "revised":
        task.status = "revised"
        task.last_decision = "revise"
        
        # ✅ revise 시 revision_count + 메타 정보 업데이트
        if revision_count is not None:
            task.revision_count = revision_count
        task.last_revised_at = datetime.utcnow()
        task.last_revised_by = reviewer
        
    else:
        task.status = decision

    task.comment = comment
    task.reviewer = reviewer
    task.decided_at = datetime.utcnow()

    await db.commit()
    await db.refresh(task)
    
    logger.info(
        "[decide_task] Updated task_id=%s: status=%s, decision=%s, revision_count=%s, reviewer=%s",
        task.id,
        task.status,
        decision,
        task.revision_count,
        reviewer,
    )
    
    return task


async def mark_task_completed(
    db: AsyncSession,
    task_id: int,
) -> Optional[HumanReviewTask]:
    """task를 completed 상태로 변경 (최종 승인 후)"""
    task = await get_task(db, task_id)
    if not task:
        return None
    
    task.status = "completed"
    task.decided_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(task)
    
    logger.info("[mark_task_completed] task_id=%s marked as completed", task_id)
    
    return task


async def get_tasks_by_period(
    db: AsyncSession,
    period: str,
) -> List[HumanReviewTask]:
    """특정 기간의 모든 task 조회 (히스토리용)"""
    result = await db.execute(
        select(HumanReviewTask)
        .where(HumanReviewTask.period == period)
        .order_by(desc(HumanReviewTask.created_at))
    )
    return list(result.scalars().all())