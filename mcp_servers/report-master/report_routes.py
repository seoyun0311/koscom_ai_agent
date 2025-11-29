# report_routes.py
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/mcp", tags=["mcp-report"])


# =========================
#  공통 / 스키마 정의
# =========================

class LatestReport(BaseModel):
    period: str
    final_grade: str
    report_path: str
    summary: Dict[str, Any]
    generated_at: datetime


class HumanReviewTask(BaseModel):
    id: str
    item: str
    reason: str
    required_action: str
    created_at: datetime


class HumanReviewTasksResponse(BaseModel):
    pending_tasks: List[HumanReviewTask]
    count: int


class CollateralStatus(BaseModel):
    period: str
    avg_ratio: float
    min_ratio: float
    volatility: float
    collateral_grade: str
    asset_breakdown: Dict[str, float]


class RiskSummary(BaseModel):
    period: str
    overall_grade: str
    summary: Dict[str, Any]
    key_points: List[str]


class ReportDetail(BaseModel):
    period: str
    final_grade: str
    report_text: str
    report_path: str
    created_at: datetime


class ComplianceAlert(BaseModel):
    type: str
    level: str
    description: str
    occurred_at: datetime


class ComplianceAlertsResponse(BaseModel):
    period: str
    alerts: List[ComplianceAlert]
    count: int


# =========================
#  더미 데이터 헬퍼들
# =========================

def _get_latest_period() -> str:
    # 🚧 나중에 DB에서 "가장 최근 period" 가져오도록 변경 가능
    return "2025-10"


def _get_latest_report_dummy() -> LatestReport:
    """
    🚧 현재는 DB 없이 더미 데이터로만 동작하는 함수.
    나중에 DB가 정해지면 이 함수만 교체하면 됨.
    """
    period = _get_latest_period()
    return LatestReport(
        period=period,
        final_grade="A",
        report_path=rf"C:\mcp\artifacts\REP-{period}.txt",
        summary={
            "final_grade": "A",
            "key_points": [
                "Collateral grade: A",
                "Peg grade: A",
                "Disclosure grade: A",
                "Liquidity grade: A",
                "PoR grade: A",
                "Consistency status: ok",
            ],
        },
        generated_at=datetime(2025, 11, 1, 0, 0, 3),
    )


def _get_human_review_tasks_dummy() -> HumanReviewTasksResponse:
    # 필요하면 여러 개 넣어도 됨
    task = HumanReviewTask(
        id="HR-2025-10-01",
        item="Collateral ratio anomaly",
        reason="Unexpected drop detected on 2025-10-12",
        required_action="Check oracle source data and confirm bank reserve snapshot.",
        created_at=datetime(2025, 10, 12, 15, 22, 0),
    )
    return HumanReviewTasksResponse(
        pending_tasks=[task],
        count=1,
    )


def _get_collateral_status_dummy(period: Optional[str]) -> CollateralStatus:
    if period is None:
        period = _get_latest_period()

    return CollateralStatus(
        period=period,
        avg_ratio=153.2,
        min_ratio=142.1,
        volatility=1.8,
        collateral_grade="A",
        asset_breakdown={
            "KRW_cash": 60.0,
            "KRW_deposit": 20.0,
            "USDT": 10.0,
            "USDC": 10.0,
        },
    )


def _get_risk_summary_dummy(period: Optional[str]) -> RiskSummary:
    if period is None:
        period = _get_latest_period()

    return RiskSummary(
        period=period,
        overall_grade="A",
        summary={
            "collateral": "A",
            "peg": "A",
            "liquidity": "A",
            "disclosure": "A",
            "por": "A",
            "consistency": "ok",
        },
        key_points=[
            "All key indicators are stable.",
            "Peg deviation remained below 0.1%.",
            "No material disclosure issues detected.",
        ],
    )


def _get_report_detail_dummy(period: str) -> ReportDetail:
    # 나중에 TXT/DOCX 파일 읽어와서 텍스트로 변환하는 로직으로 교체 가능
    dummy_text = f"""
    K-WON Monthly Compliance Report ({period})

    1. Overview
    - Final grade: A
    - All key indicators (collateral, peg, liquidity, disclosure, PoR) are stable.

    2. Collateral
    - Average collateral ratio: 153.2%
    - Minimum collateral ratio: 142.1%

    3. Peg
    - Max deviation: 0.08%

    (This is dummy content for development.)
    """

    return ReportDetail(
        period=period,
        final_grade="A",
        report_text=dummy_text.strip(),
        report_path=rf"C:\mcp\artifacts\REP-{period}.txt",
        created_at=datetime(2025, 11, 1, 0, 0, 3),
    )


def _get_compliance_alerts_dummy(period: Optional[str]) -> ComplianceAlertsResponse:
    if period is None:
        period = _get_latest_period()

    alert = ComplianceAlert(
        type="peg_deviation",
        level="warning",
        description="Peg deviation exceeded 0.7% for more than 10 minutes on 2025-10-12.",
        occurred_at=datetime(2025, 10, 12, 14, 22, 0),
    )

    return ComplianceAlertsResponse(
        period=period,
        alerts=[alert],
        count=1,
    )


# =========================
#  실제 FastAPI 엔드포인트
# =========================

@router.get("/report/latest", response_model=LatestReport)
def get_latest_report() -> LatestReport:
    """
    가장 최근 보고서를 반환하는 조회용 엔드포인트.
    지금은 더미 데이터, 나중에 DB 버전으로 교체.
    """
    return _get_latest_report_dummy()


@router.get("/human_review/tasks", response_model=HumanReviewTasksResponse)
def get_human_review_tasks() -> HumanReviewTasksResponse:
    """
    Human Review 대기 중인 작업들을 반환.
    나중에 DB에서 pending 상태인 항목들을 조회하도록 교체.
    """
    return _get_human_review_tasks_dummy()


@router.get("/collateral/status", response_model=CollateralStatus)
def get_collateral_status(period: Optional[str] = None) -> CollateralStatus:
    """
    특정 period(예: '2025-10') 또는 최신 period의 담보 상태를 반환.
    """
    return _get_collateral_status_dummy(period)


@router.get("/risk/summary", response_model=RiskSummary)
def get_risk_summary(period: Optional[str] = None) -> RiskSummary:
    """
    특정 period 또는 최신 period의 리스크 요약을 반환.
    """
    return _get_risk_summary_dummy(period)


@router.get("/report/{period}", response_model=ReportDetail)
def get_report(period: str) -> ReportDetail:
    """
    특정 period(예: '2025-10')의 월간 보고서 상세 내용을 반환.
    """
    return _get_report_detail_dummy(period)


@router.get("/alerts", response_model=ComplianceAlertsResponse)
def get_compliance_alerts(period: Optional[str] = None) -> ComplianceAlertsResponse:
    """
    특정 period 또는 최신 period의 컴플라이언스 경고/위반 내역을 반환.
    """
    return _get_compliance_alerts_dummy(period)
