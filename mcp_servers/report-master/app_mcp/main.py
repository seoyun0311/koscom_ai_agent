from fastapi import FastAPI
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app_mcp.services.realtime_monitor import check_and_alert_realtime
from app_mcp.core.db import init_db

app = FastAPI(title="MCP Server")

scheduler = AsyncIOScheduler()

from app_mcp.api import review as review_api
from app_mcp.api import mcp as mcp_api 

app = FastAPI()

app.include_router(review_api.router)
app.include_router(mcp_api.router)

@app.on_event("startup")
async def startup_event():
    # DB 초기화
    await init_db()

    # 1분마다 실시간 스냅샷 + 알림 실행
    scheduler.add_job(
        check_and_alert_realtime,
        "interval",
        minutes=1,   # 테스트에서는 1분, 운영에서는 15분!
        id="realtime_monitor"
    )

    scheduler.start()


@app.get("/")
def root():
    return {"status": "MCP server running"}
