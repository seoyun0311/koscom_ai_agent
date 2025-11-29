from __future__ import annotations
from datetime import datetime

from typing import Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from app_mcp.models.realtime_snapshot import RealtimeSnapshot


async def insert_snapshot(
    db: AsyncSession,
    metrics: Dict[str, Any],
    risk: Dict[str, Any],
) -> RealtimeSnapshot:
    """
    실시간 스냅샷을 DB에 저장 (async 버전).
    """
    snapshot = RealtimeSnapshot(
        created_at=datetime.utcnow(),
        tvl=metrics["tvl"],
        reserve_ratio=metrics["reserve_ratio"],
        peg_deviation=metrics["peg_deviation"],
        liquidity_score=metrics["liquidity_score"],
        risk_level=risk["risk_level"],
        raw_payload={"metrics": metrics, "risk": risk},
    )

    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)
    return snapshot
