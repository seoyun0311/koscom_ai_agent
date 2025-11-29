# app_mcp/core/scheduler.py
from __future__ import annotations

import logging
import os
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import requests

from app_mcp.services.realtime_monitor import check_and_alert_realtime

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 1) 15분마다 실시간 모니터링 + Slack 알림
# ─────────────────────────────────────────────
def realtime_monitoring_job() -> None:
    """
    15분마다 실행되는 실시간 모니터링 Job.

    - 온체인/오프체인 스냅샷 or mock 데이터 기반으로
    - 위험 구간이면 Slack Webhook으로 알림 보내는 함수(check_and_alert_realtime) 호출
    """
    logger.info("[scheduler] ▶ Running realtime_monitoring_job()")

    try:
        # check_and_alert_realtime 안에서:
        # - DB/외부 API 조회
        # - 리스크 판단
        # - Slack Webhook 호출
        check_and_alert_realtime()
        logger.info("[scheduler] ✅ realtime_monitoring_job completed")
    except Exception as e:
        logger.exception(
            "[scheduler] ❌ realtime_monitoring_job failed: %s",
            e,
        )


# ─────────────────────────────────────────────
# 2) 매달 1일 월간 컴플라이언스 보고서 생성 Job
# ─────────────────────────────────────────────
def run_monthly_mcp_job() -> None:
    """
    매달 1일 00시(또는 지정 시간)에 실행되는 월간 보고서 생성 Job.

    구현 전략:
    - 내부 LangGraph 함수를 직접 부르는 대신,
      이미 잘 만들어 둔 `/mcp/run` HTTP 엔드포인트를 호출한다.
    - 이렇게 하면:
      * LangGraph + HumanReviewTask 생성 + Slack Human Review 카드 전송까지
        한 번에 처리되는 기존 플로우를 그대로 재사용할 수 있다.
    """

    # 이번 달 기준 period 문자열 (예: "2025-10")
    period = datetime.now().strftime("%Y-%m")

    # 자기 자신 FastAPI 서버 주소
    base_url = os.getenv("SCHEDULER_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    url = f"{base_url}/mcp/run"

    payload = {"period": period}

    logger.info(
        "[scheduler] ▶ Running run_monthly_mcp_job: url=%s, payload=%s",
        url,
        payload,
    )

    try:
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code // 100 == 2:
            logger.info(
                "[scheduler] ✅ run_monthly_mcp_job success: status=%s, body=%s",
                resp.status_code,
                resp.text,
            )
        else:
            logger.error(
                "[scheduler] ❌ run_monthly_mcp_job HTTP error: %s %s",
                resp.status_code,
                resp.text,
            )
    except Exception as e:
        logger.exception("[scheduler] ❌ run_monthly_mcp_job failed: %s", e)


# ─────────────────────────────────────────────
# 3) 스케줄러 등록 함수 (mcp_server.py에서 호출)
# ─────────────────────────────────────────────
def register_scheduler(scheduler: AsyncIOScheduler) -> None:
    """
    mcp_server.py의 on_startup에서 호출되는 함수.

    여기서:
    - 15분 간격 실시간 모니터링 Job
    - 매달 1일 00:05 월간 보고서 Job
    을 모두 등록한다.
    """

    logger.info("[scheduler] Registering APScheduler jobs")

    # (1) 15분마다 실시간 모니터링
    scheduler.add_job(
        realtime_monitoring_job,
        "interval",
        minutes=15,
        id="realtime_monitoring_job",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    logger.info("[scheduler] ✔ Added job: realtime_monitoring_job (every 15 min)")

    # (2) 매달 1일 00:05 월간 보고서 Job
    scheduler.add_job(
        run_monthly_mcp_job,
        "cron",
        day=1,
        hour=0,
        minute=5,
        id="monthly_mcp_job",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    logger.info("[scheduler] ✔ Added job: monthly_mcp_job (cron 1st 00:05)")
