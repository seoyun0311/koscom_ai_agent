# app_mcp/services/snapshot_crud.py
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app_mcp.models.realtime_risk_snapshot import RealtimeRiskSnapshot

async def insert_snapshot(
    db: AsyncSession,
    metrics: Dict[str, Any],
    risk: Dict[str, Any],
) -> RealtimeRiskSnapshot:
    """
    CRIT 이벤트 스냅샷을 stablecoin.realtime_risk_snapshot 테이블에 저장.
    metrics: {
      "tvl": ...,
      "reserve_ratio": ...,
      "peg_deviation": ...,
      "liquidity_score": ...
    }
    risk: {
      "risk_level": "CRIT"
    }
    """
    snapshot = RealtimeRiskSnapshot(
        tvl=int(metrics["tvl"]),
        reserve_ratio=metrics["reserve_ratio"],
        peg_deviation=metrics["peg_deviation"],
        liquidity_score=metrics["liquidity_score"],
        risk_level=risk["risk_level"],
        metrics_json=metrics,  # 원본 메트릭 전체를 JSONB로 보관
    )

    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)
    return snapshot
