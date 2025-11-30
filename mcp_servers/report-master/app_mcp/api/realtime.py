# app_mcp/api/realtime.py
from __future__ import annotations

import logging
from typing import Literal, Dict, Any

from fastapi import APIRouter

from app_mcp.services.realtime_monitor import collect_current_metrics
from app_mcp.core.risk_rules import overall_risk_level, RiskLevel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/realtime", tags=["realtime"])


def _apply_relaxed_rules(metrics: Dict[str, Any]) -> RiskLevel:
    """
    check_and_alert_realtime()에서 쓰는 완화 로직을
    그대로 재사용해서 최종 RiskLevel을 계산하는 helper.
    """
    level_enum = overall_risk_level(
        collateral_ratio=metrics["reserve_ratio"],
        peg_deviation=abs(metrics["peg_deviation"]),
        liquidity_ratio=metrics["liquidity_score"],
    )

    # 1단계 완화: CRIT → WARN
    if level_enum == RiskLevel.CRIT:
        if (
            metrics["reserve_ratio"] >= 1.0           # 담보 100% 이상
            and abs(metrics["peg_deviation"]) <= 0.10 # 페그 10% 이내
            and metrics["liquidity_score"] >= 0.5     # 유동성 보통 이상
        ):
            logger.info("[realtime_status] CRIT → WARN (relaxed rule)")
            level_enum = RiskLevel.WARN

    # 2단계 완화: WARN → OK
    if level_enum == RiskLevel.WARN:
        if (
            metrics["reserve_ratio"] >= 1.0           # 담보 100% 이상
            and abs(metrics["peg_deviation"]) <= 0.03 # 페그 3% 이내
            and metrics["liquidity_score"] >= 0.7     # 유동성 양호
        ):
            logger.info("[realtime_status] WARN → OK (relaxed rule)")
            level_enum = RiskLevel.OK

    return level_enum


@router.get("/status")
async def get_current_status():
    """
    👉 프론트/심사위원/Claude MCP가 바로 호출해서
       '지금 리스크 상태'를 볼 수 있는 엔드포인트.

    - Node 백엔드에서 실시간 지표 가져오기
    - 리스크 레벨 계산 + 완화 규칙 적용
    - Slack/DB는 건드리지 않고, 결과만 JSON으로 리턴
    """
    logger.info("[realtime_status] /realtime/status called")

    try:
        metrics = collect_current_metrics()
    except Exception as e:
        # Node 백엔드 오류 / 네트워크 문제 등
        logger.exception("[realtime_status] Failed to collect metrics: %s", e)
        return {
            "ok": False,
            "error": "failed_to_collect_metrics",
            "detail": str(e),
        }

    level_enum = _apply_relaxed_rules(metrics)
    risk_level: Literal["OK", "WARN", "CRIT"] = level_enum.value  # type: ignore

    logger.info(
        "[realtime_status] Computed risk_level=%s (tvl=%.0f, cov=%.4f, peg=%.4f, liq=%.4f)",
        risk_level,
        metrics["tvl"],
        metrics["reserve_ratio"],
        metrics["peg_deviation"],
        metrics["liquidity_score"],
    )

    return {
        "ok": True,
        "risk_level": risk_level,
        "metrics": metrics,
    }
