# app_mcp/main.py
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app_mcp.core.db import init_db
from app_mcp.core.config import ensure_artifacts_dir
from app_mcp.services.realtime_monitor import check_and_alert_realtime
from app_mcp.graph.mcp_flow import run_monthly_mcp_flow

# ---- API Routers ----
from app_mcp.api import slack_interactions
from app_mcp.api import review as review_api
from app_mcp.api import mcp as mcp_api
from app_mcp.api import realtime as realtime_api
from app_mcp.api import reports as reports_api

logger = logging.getLogger(__name__)

# FastAPI 앱 & 스케줄러 생성
app = FastAPI(title="MCP Server")
scheduler = AsyncIOScheduler()

# ---------------------------
# artifacts 정적 파일 서빙
# ---------------------------
# PROJECT_ROOT / "artifacts" 디렉터리 보장
artifacts_dir = ensure_artifacts_dir()

# /artifacts/REP-2025-10.docx 이런 식으로 접근 가능해짐
app.mount(
    "/artifacts",
    StaticFiles(directory=str(artifacts_dir)),
    name="artifacts",
)

# ---------------------------
# 라우터 등록
# ---------------------------
app.include_router(slack_interactions.router)
app.include_router(review_api.router)
app.include_router(mcp_api.router)
app.include_router(realtime_api.router)
app.include_router(reports_api.router)


# ---------------------------
# 월간 보고서 자동 실행 Job
# ---------------------------
async def monthly_report_job():
    """
    매일 00:10에 실행되지만,
    실제 보고서 생성은 '매달 1일'에만 수행되도록 안전하게 구성.
    """
    kst = timezone(timedelta(hours=9))
    today = datetime.now(tz=kst).date()

    if today.day != 1:
        return  # 1일이 아니면 실행하지 않음

    period = today.strftime("%Y-%m")

    try:
        logger.info(f"[scheduler] Running monthly MCP flow for {period}")
        # run_monthly_mcp_flow가 동기 함수라면 그냥 이렇게 호출
        result = run_monthly_mcp_flow(period=period)
        logger.info(f"[scheduler] Monthly MCP flow done: {result}")
    except Exception as e:
        logger.exception(f"[scheduler] Monthly report job failed: {e}")


# ---------------------------
# 앱 라이프사이클
# ---------------------------
@app.on_event("startup")
async def startup_event():
    logger.info("Starting MCP server - init DB & scheduler")

    # 1) DB 초기화
    await init_db()

    # 2) 실시간 모니터링 스케줄러 등록
    if scheduler.get_job("realtime_monitor"):
        scheduler.remove_job("realtime_monitor")

    scheduler.add_job(
        check_and_alert_realtime,
        "interval",
        minutes=1,      # 테스트: 1분, 실전: 15분
        id="realtime_monitor",
    )

    # 3) 월간 보고서 스케줄러 등록 (매일 00:10)
    if scheduler.get_job("monthly_report"):
        scheduler.remove_job("monthly_report")

    scheduler.add_job(
        monthly_report_job,
        "cron",
        hour=0,
        minute=10,
        id="monthly_report",
    )

    scheduler.start()
    logger.info("Scheduler started.")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down MCP server - stop scheduler")
    scheduler.shutdown(wait=False)


@app.get("/")
async def root():
    return {"status": "MCP server running"}
