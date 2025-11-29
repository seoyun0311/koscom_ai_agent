# app_mcp/utils/scheduler.py
from app_mcp.core.scheduler import scheduler, register_jobs
import logging

from app_mcp.core.db import SessionLocal
from app_mcp.services.realtime_monitor import collect_and_store_snapshot

logger = logging.getLogger(__name__)

def bind_scheduler(app):
    @app.on_event("startup")
    async def _start():
        # 작업 등록
        register_jobs(app)
        # 중복 start 방지
        if not scheduler.running:
            scheduler.start()

    @app.on_event("shutdown")
    async def _shutdown():
        if scheduler.running:
            scheduler.shutdown(wait=False)



def run_realtime_snapshot_job():
    """
    15분(테스트에선 1분)마다 실행되는 실시간 스냅샷 수집 Job.
    """
    logger.info("[scheduler] run_realtime_snapshot_job start")
    db = SessionLocal()
    try:
        snapshot = collect_and_store_snapshot(db)
        logger.info(
            "[scheduler] snapshot stored: id=%s risk_level=%s",
            snapshot.id,
            snapshot.risk_level,
        )
    except Exception as e:
        logger.exception("[scheduler] run_realtime_snapshot_job failed: %s", e)
    finally:
        db.close()