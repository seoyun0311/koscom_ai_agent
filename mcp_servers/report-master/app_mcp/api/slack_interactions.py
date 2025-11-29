# app_mcp/api/slack_interactions.py

from __future__ import annotations

import json
import logging
from typing import Optional

import requests
from fastapi import APIRouter, Form

from app_mcp.core.db import async_session
from app_mcp.crud import human_review as crud_hr
from app_mcp.services.human_review_service import resume_human_review_flow
from app_mcp.services.mail_service import send_approval_email  # ✅ 메일은 여기서

from app_mcp.services.notifications import send_slack_human_review_request


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/slack", tags=["slack"])


@router.post("/interactions")
async def slack_interactions(payload: str = Form(...)):
    """
    Slack Interactivity 엔드포인트
    - 버튼 클릭(block_actions) 처리
    """
    logger.info("=== Slack Interaction Received ===")
    logger.info(f"[raw payload] {payload!r}")

    if not payload:
        logger.warning("[slack_interactions] Empty payload received")
        return {"ok": False, "error": "empty_payload"}

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as e:
        logger.error(f"❌ Error in slack_interactions: {e}", exc_info=True)
        return {"ok": False, "error": "invalid_json"}

    logger.info(f"[payload.type] {data.get('type')}")

    # URL Verification
    if data.get("type") == "url_verification":
        challenge = data.get("challenge")
        logger.info(f"[url_verification] challenge={challenge}")
        return {"challenge": challenge}

    # ----- 버튼 클릭 처리 (block_actions) -----
    if data.get("type") == "block_actions":
        try:
            actions = data.get("actions") or []
            if not actions:
                logger.error("[slack_interactions] No actions in payload")
                return {"ok": False, "error": "no_actions"}

            action = actions[0]
            action_id = action.get("action_id")
            value = action.get("value")
            response_url = data.get("response_url")  # ✅ Slack 답글용

            logger.info(f"[block_actions] action_id={action_id}, value={value}")

            try:
                task_id = int(value)
            except (TypeError, ValueError):
                logger.error(f"[slack_interactions] Invalid task_id value: {value}")
                return {"ok": False, "error": "invalid_task_id"}

            # ✅ 승인
            if action_id == "approve_button":
                await handle_approval(task_id, "Approved via Slack", response_url)
                return {"ok": True}

            # ❌ 반려
            if action_id == "reject_button":
                await handle_rejection(task_id, "Rejected via Slack", response_url)
                return {"ok": True}

            # 🔄 재생성
            if action_id == "revise_button":
                await handle_revision(task_id, "Revise via Slack", response_url)
                return {"ok": True}

            logger.warning(f"[slack_interactions] Unknown action_id={action_id}")
            return {"ok": False, "error": f"unknown_action:{action_id}"}

        except Exception as e:
            logger.error(f"❌ Error handling block_actions: {e}", exc_info=True)
            return {"ok": False, "error": str(e)}

    # 그 외 타입은 그냥 OK
    logger.info(f"[slack_interactions] Unsupported type: {data.get('type')}")
    return {"ok": True}


# ─────────────────────────────────────────────
# ✅ 버튼별 처리 함수들
# ─────────────────────────────────────────────

async def handle_approval(
    task_id: int,
    comment: str,
    response_url: Optional[str] = None,
):
    """
    승인 처리:
    - DB 업데이트
    - LangGraph 재개 (approve)
    - 이메일 발송
    - Slack에 '승인 완료' 안내
    """
    logger.info(f"[handle_approval] ✅ Approving task {task_id}")

    try:
        async with async_session() as db:
            task = await crud_hr.get_task(db, task_id)
            if not task:
                logger.error(f"[handle_approval] Task {task_id} not found")
                return

            # 1) DB 상태 업데이트
            await crud_hr.decide_task(
                db,
                task_id=task_id,
                decision="approved",
                comment=comment,
            )
            logger.info(f"[handle_approval] DB updated for task {task_id}")

            # 2) LangGraph 재개 (approve 브랜치 → finalize_report → notify_approved_report)
            try:
                logger.info(
                    f"[handle_approval] Resuming LangGraph with thread_id={task.flow_run_id}"
                )
                await resume_human_review_flow(
                    thread_id=task.flow_run_id,
                    decision="approve",
                    comment=comment,
                )
                logger.info("[handle_approval] LangGraph resumed successfully")
            except Exception as e:
                logger.error(
                    f"[handle_approval] LangGraph error: {e}",
                    exc_info=True,
                )

            # 3) 이메일 발송
            try:
                logger.info(
                    f"[handle_approval] Sending email for task={task_id}, period={task.period}"
                )
                await send_approval_email(
                    task_id=task_id,
                    period=task.period,
                    decision="approved",
                    comment=comment,
                    report_path=task.report_path,
                )
                logger.info("[handle_approval] ✉️ Email sent!")
            except Exception as e:
                logger.error(f"[handle_approval] Email error: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"[handle_approval] Approval failed: {e}", exc_info=True)
        return

    # 4) Slack ephemeral 메시지
    if response_url:
        try:
            text = (
                f"✅ *승인 완료*\n"
                f"- Task ID: {task_id}\n"
                f"- 기간: {task.period}\n"
                f"- 결정: approved"
            )
            payload = {
                "response_type": "ephemeral",
                "text": text,
            }
            requests.post(response_url, json=payload, timeout=3)
            logger.info("[handle_approval] Slack follow-up sent")
        except Exception as e:
            logger.error(
                f"[handle_approval] Slack follow-up error: {e}",
                exc_info=True,
            )


async def handle_rejection(
    task_id: int,
    reason: str,
    response_url: Optional[str] = None,
):
    """
    반려 처리:
    - DB 업데이트
    - 이메일 발송
    - LangGraph 재개 없음
    - Slack에 '반려 완료' 안내
    """
    logger.info(f"[handle_rejection] ❌ Rejecting task {task_id}")

    try:
        async with async_session() as db:
            task = await crud_hr.get_task(db, task_id)
            if not task:
                logger.error(f"[handle_rejection] Task {task_id} not found")
                return

            await crud_hr.decide_task(
                db,
                task_id=task_id,
                decision="rejected",
                comment=reason,
            )
            logger.info(f"[handle_rejection] DB updated for task {task_id}")

            # 이메일 발송
            try:
                await send_approval_email(
                    task_id=task_id,
                    period=task.period,
                    decision="rejected",
                    comment=reason,
                    report_path=task.report_path,
                )
                logger.info("[handle_rejection] ✉️ Email sent!")
            except Exception as e:
                logger.error(f"[handle_rejection] Email error: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"[handle_rejection] Rejection failed: {e}", exc_info=True)
        return

    # Slack ephemeral 메시지
    if response_url:
        try:
            text = (
                f"❌ *반려 완료*\n"
                f"- Task ID: {task_id}\n"
                f"- 기간: {task.period}\n"
                f"- 결정: rejected"
            )
            payload = {"response_type": "ephemeral", "text": text}
            requests.post(response_url, json=payload, timeout=3)
            logger.info("[handle_rejection] Slack follow-up sent")
        except Exception as e:
            logger.error(
                f"[handle_rejection] Slack follow-up error: {e}",
                exc_info=True,
            )

async def handle_revision(
    task_id: int,
    feedback: str,
    response_url: Optional[str] = None,
):
    """
    보수적 재생성 처리:
    - DB 업데이트 (decision='revised')
    - LangGraph 재개 → summarize_conclusion → generate_report → human_review 앞에서 interrupt
    - 새로 생성된 summary/report_path 기반으로 Human Review 카드 다시 전송
    - Slack에 '재생성 완료 + 재생성 횟수/새 등급' 안내(ephemeral)
    """
    logger.info(f"[handle_revision] 🔄 Revising task {task_id}")

    updated_state: dict | None = None
    task = None

    try:
        async with async_session() as db:
            task = await crud_hr.get_task(db, task_id)
            if not task:
                logger.error(f"[handle_revision] Task {task_id} not found")
                return

            # 1) DB 업데이트
            await crud_hr.decide_task(
                db,
                task_id=task_id,
                decision="revised",
                comment=feedback,
            )
            logger.info(f"[handle_revision] DB updated for task {task_id}")

            # 2) LangGraph 재개
            try:
                updated_state = await resume_human_review_flow(
                    thread_id=task.flow_run_id,
                    decision="revise",
                    comment=feedback,
                )
                logger.info("[handle_revision] LangGraph resume success")
            except Exception as e:
                logger.error(
                    f"[handle_revision] LangGraph error: {e}",
                    exc_info=True,
                )

    except Exception as e:
        logger.error(f"[handle_revision] Revision failed: {e}", exc_info=True)
        return

    # 3) 재생성된 보고서 기준으로 Human Review 카드 다시 전송
    if isinstance(updated_state, dict) and task is not None:
        period = (updated_state.get("period") or task.period)
        summary = (updated_state.get("summary") or {})
        report_path = (updated_state.get("report_path") or task.report_path)
        revision_count = updated_state.get("revision_count")

        try:
            send_slack_human_review_request(
                period=period,
                task_id=task_id,
                summary=summary,
                report_path=report_path,
                revision_count=revision_count,
            )
            logger.info(
                "[handle_revision] Sent new Human Review Slack card "
                "(task_id=%s, rev=%s)",
                task_id,
                revision_count,
            )
        except Exception as e:
            logger.error(
                f"[handle_revision] Failed to send new HR Slack card: {e}",
                exc_info=True,
            )

    # 4) Slack ephemeral 메시지 (재생성 결과 간단 요약)
    if response_url:
        try:
            lines = [f"🔄 *보수적 재생성 완료* (task_id={task_id})"]

            if isinstance(updated_state, dict):
                rev = updated_state.get("revision_count")
                summary = (updated_state.get("summary") or {})
                final_grade = summary.get("final_grade")

                if rev is not None:
                    lines.append(f"- 현재 재생성 횟수: {rev}")
                if final_grade:
                    lines.append(f"- 재계산된 최종 등급: {final_grade}")

            payload = {
                "response_type": "ephemeral",
                "text": "\n".join(lines),
            }
            requests.post(response_url, json=payload, timeout=3)
            logger.info("[handle_revision] Slack follow-up sent")
        except Exception as e:
            logger.error(
                f"[handle_revision] Slack follow-up error: {e}",
                exc_info=True,
            )
