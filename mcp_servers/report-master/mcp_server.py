# mcp_server.py
import logging
import os

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.asyncio import AsyncIOScheduler  # ✅ 추가

from app_mcp.core.config import get_settings
from app_mcp.core.db import init_db
from app_mcp.core.scheduler import register_scheduler  # ✅ 스케줄러는 여기서

# API 라우터들
from app_mcp.api import review as review_api
from app_mcp.api.mcp import router as mcp_router
from report_routes import router as report_router
from report_generator_routes import router as generator_router
from app_mcp.api.human_review import router as human_review_router
from app_mcp.api.report_query_routes import router as report_query_router
from app_mcp.api.slack_interactions import router as slack_router
from app_mcp.api.debug_email import router as debug_email_router  # 디버깅용

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# 디렉토리 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = BASE_DIR
ARTIFACT_DIR = os.path.join(ROOT_DIR, "artifacts")

# artifacts 폴더 없으면 생성
os.makedirs(ARTIFACT_DIR, exist_ok=True)

# 전역 APScheduler 인스턴스
scheduler = AsyncIOScheduler()


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Agent MCP - Compliance Report",
        version="0.1.0",
    )

    settings = get_settings()

    logger.info(f"📂 ROOT_DIR      = {ROOT_DIR}")
    logger.info(f"📂 ARTIFACT_DIR = {ARTIFACT_DIR}")

    # artifacts 폴더 static mount
    app.mount(
        "/artifacts",
        StaticFiles(directory=ARTIFACT_DIR),
        name="artifacts",
    )

    # 라우터 등록
    app.include_router(mcp_router)
    app.include_router(review_api.router)
    app.include_router(report_router)
    app.include_router(generator_router)
    app.include_router(human_review_router)
    app.include_router(report_query_router)
    app.include_router(slack_router)
    app.include_router(debug_email_router)

    # -------------------------
    # Startup 이벤트
    # -------------------------
    @app.on_event("startup")
    async def on_startup():
        await init_db()
        logger.info("DB initialized")

        # ✅ 스케줄러에 Job 등록 + 시작
        register_scheduler(scheduler)
        scheduler.start()
        logger.info("APScheduler started")

    # -------------------------
    # Shutdown 이벤트
    # -------------------------
    @app.on_event("shutdown")
    async def on_shutdown():
        if scheduler.running:
            scheduler.shutdown(wait=False)
            logger.info("APScheduler stopped")

    @app.get("/health")
    async def health_check():
        return {"status": "ok"}

    return app


app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "mcp_server:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=True,
    )
