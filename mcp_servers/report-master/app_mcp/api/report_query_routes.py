#app_mcp/api/report_query_routes.py
#FastAPI – 지난 보고서 조회용 API 전체 코드
import os
import glob
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any

from datetime import datetime

ARTIFACT_DIR = os.path.join(os.getcwd(), "artifacts")
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp-query"])


# ==============================
# 유틸리티: 가장 최신 보고서 찾기
# ==============================
def _find_latest_report() -> Optional[str]:
    files = glob.glob(os.path.join(ARTIFACT_DIR, "REP-*.docx"))
    if not files:
        return None
    return max(files, key=os.path.getmtime)


# ==============================
# 1) 최신 보고서 조회
# ==============================
@router.get("/report/latest")
def get_latest_report():
    path = _find_latest_report()
    if not path:
        raise HTTPException(status_code=404, detail="No reports found")

    filename = os.path.basename(path)
    period = filename.replace("REP-", "").replace(".docx", "")

    return {
        "period": period,
        "report_path": path,
        "final_grade": "N/A",
        "generated_at": datetime.fromtimestamp(os.path.getmtime(path)),
        "summary": {},
    }


# ==============================
# 2) 특정 월 보고서 조회
# ==============================
@router.get("/report/{period}")
def get_report(period: str):
    filename = f"REP-{period}.docx"
    path = os.path.join(ARTIFACT_DIR, filename)

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Report not found")

    return {
        "period": period,
        "report_path": path,
        "created_at": datetime.fromtimestamp(os.path.getmtime(path)),
        "final_grade": "N/A",
        "summary": {},
        "report_text": "(DOCX content omitted — Claude can download via report_path)"
    }


# ==============================
# 3) 담보 상태 조회
# ==============================
@router.get("/collateral/status")
def get_collateral_status(period: Optional[str] = None):
    return {
        "period": period or "latest",
        "collateral_ratio": 1.52,
        "grade": "A",
        "details": "Mock data — replace with real DB or provider"
    }


# ==============================
# 4) 리스크 요약 조회
# ==============================
@router.get("/risk/summary")
def get_risk_summary(period: Optional[str] = None):
    return {
        "period": period or "latest",
        "risk_flags": [],
        "summary": "No major risks detected",
    }


# ==============================
# 5) 컴플라이언스 알림 조회
# ==============================
@router.get("/alerts")
def get_compliance_alerts(period: Optional[str] = None):
    return {
        "period": period or "latest",
        "alerts": [],
        "count": 0,
    }


# ==============================
# 6) Human Review 작업 조회
# ==============================
@router.get("/human_review/tasks")
def list_human_review_tasks():
    # 지금은 DB 연결 전이라 mock
    return {
        "count": 1,
        "pending_tasks": [
            {
                "task_id": 1,
                "period": "2025-10",
                "status": "pending",
            }
        ],
    }