# app_mcp/services/realtime_monitor.py
from __future__ import annotations
import os
import logging
from typing import Dict, Any

import requests

from app_mcp.core.db import SessionLocal  # AsyncSession factory
from app_mcp.services.snapshot_crud import insert_snapshot

# ✅ 공통 리스크 룰 사용 (OK / WARN / CRIT)
from app_mcp.core.risk_rules import overall_risk_level, RiskLevel

# Slack 알림은 선택(에러 나면 noop)
try:
    from app_mcp.tools.slack import send_risk_alert
except Exception:
    def send_risk_alert(*args, **kwargs):
        logging.warning("send_risk_alert 불러오기 실패 (Slack 비활성화).")


logger = logging.getLogger(__name__)

# Node 백엔드 기본 URL (.env BACKEND_BASE_URL 기준)
BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://localhost:4000").rstrip("/")


def collect_current_metrics() -> Dict[str, Any]:
    """
    실시간 메트릭 수집 – Node 백엔드의 기존 API들을 조합해서 사용.

    사용 API:
    - GET /metrics     → reservesKRW, supplyKRW, coverageRatio
    - GET /price-feed  → data.price (→ peg_deviation)
    - GET /banks       → hhi (→ liquidity_score = 1 - hhi)

    반환 형식:
    {
        "tvl": float,
        "reserve_ratio": float,
        "peg_deviation": float,
        "liquidity_score": float,
    }
    """

    # 1) 담보율 / 발행량
    m_resp = requests.get(f"{BACKEND_BASE_URL}/metrics", timeout=5)
    m_resp.raise_for_status()
    m_data = m_resp.json()
    if not m_data.get("ok"):
        raise RuntimeError(f"/metrics error: {m_data}")

    reserves_krw = float(m_data["reservesKRW"])
    supply_krw = float(m_data["supplyKRW"])
    coverage_ratio = float(m_data["coverageRatio"])  # 준비금 / 발행량 비율

    # 2) 가격 피드
    p_resp = requests.get(f"{BACKEND_BASE_URL}/price-feed", timeout=5)
    p_resp.raise_for_status()
    p_data = p_resp.json()
    if not p_data.get("ok"):
        raise RuntimeError(f"/price-feed error: {p_data}")

    price_info = p_data["data"]
    price = float(price_info["price"])
    peg_deviation = price - 1.0  # 1원 기준 편차

    # 3) 은행 분산도(HHI → 유동성/분산 점수)
    b_resp = requests.get(f"{BACKEND_BASE_URL}/banks", timeout=5)
    b_resp.raise_for_status()
    b_data = b_resp.json()
    if not b_data.get("ok"):
        raise RuntimeError(f"/banks error: {b_data}")

    hhi = float(b_data["hhi"])               # 0~1
    liquidity_score = max(0.0, min(1.0, 1.0 - hhi))  # 1 - HHI, 0~1 클램프

    tvl = supply_krw  # 모니터링 기준 규모는 유통량으로 설정

    metrics = {
        "tvl": tvl,
        "reserve_ratio": coverage_ratio,
        "peg_deviation": peg_deviation,
        "liquidity_score": liquidity_score,
    }

    logger.info(
        "[realtime_monitor] Metrics fetched: tvl=%.0f, cov=%.4f, peg=%.4f, liq=%.4f (hhi=%.4f)",
        tvl,
        coverage_ratio,
        peg_deviation,
        liquidity_score,
        hhi,
    )

    return metrics


async def check_and_alert_realtime():
    """
    1회 모니터링 실행:
    - 메트릭 수집
    - 리스크 평가
    - (필요 시) Slack 알림
    - DB 저장
    """
    logger.info("[realtime_monitor] Running realtime check...")

    try:
        # 1) 메트릭 수집
        metrics = collect_current_metrics()

        # 2) 리스크 평가 (OK / WARN / CRIT)
        level_enum = overall_risk_level(
            collateral_ratio=metrics["reserve_ratio"],
            peg_deviation=abs(metrics["peg_deviation"]),
            liquidity_ratio=metrics["liquidity_score"],
        )
        risk_level = level_enum.value  # "OK" / "WARN" / "CRIT"

        # 3) Slack – WARN/CRIT 일 때만 알림
        if level_enum in (RiskLevel.WARN, RiskLevel.CRIT):
            try:
                send_risk_alert({
                    "risk_level": risk_level,
                    "metrics": metrics,
                })
            except Exception as e:
                logger.warning(f"Slack 알림 실패 (무시하고 계속 진행): {e}")

        # 4) DB 저장 (async 세션 사용)
        async with SessionLocal() as db:
            snapshot = await insert_snapshot(
                db=db,
                metrics=metrics,
                risk={"risk_level": risk_level},
                raw_payload={**metrics, "risk_level": risk_level},
            )

        logger.info(
            "[realtime_monitor] Snapshot saved successfully (id=%s, risk=%s)",
            snapshot.id,
            risk_level,
        )

    except Exception as e:
        logger.exception(f"[realtime_monitor] Failed: {e}")
