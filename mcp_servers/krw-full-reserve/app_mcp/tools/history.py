# app_mcp/tools/history.py
from typing import Optional, Literal
from datetime import datetime
from core.db import get_pool


Metric = Literal["all", "coverage", "onchain", "offchain"]


async def fetch_full_reserve_history(
    metric: Metric = "all",
    from_ts: Optional[str] = None,
    to_ts: Optional[str] = None,
    limit: int = 1000,
):
    """
    stablecoin.full_reserve_history에서 히스토리 조회.

    - metric:
        "all"       : 모든 필드
        "coverage"  : 담보율/준비금/오프체인 발행량만
        "onchain"   : 온체인 가격/이론가만
        "offchain"  : 오프체인 발행량만
    - from_ts, to_ts: ISO8601 문자열 (예: "2025-11-26T00:00:00Z")
    """

    pool = await get_pool()

    async with pool.acquire() as conn:
        sql = """
                SELECT
                timestamp,
                coverage_ratio,
                reserves_krw,
                offchain_supply_krw,
                onchain_price,
                theoretical_price
                FROM stablecoin.full_reserve_history_mv
                WHERE ($1::timestamptz IS NULL OR timestamp >= $1::timestamptz)
                AND ($2::timestamptz IS NULL OR timestamp <= $2::timestamptz)
                ORDER BY timestamp DESC
                LIMIT $3
            """

        rows = await conn.fetch(sql, from_ts, to_ts, limit)


    points = []
    for r in rows:
        item: dict = {
            "timestamp": r["timestamp"].isoformat(),
        }

        if metric in ("all", "coverage", "offchain"):
            item["coverage_ratio"] = (
                float(r["coverage_ratio"]) if r["coverage_ratio"] is not None else None
            )
            item["reserves_krw"] = (
                float(r["reserves_krw"]) if r["reserves_krw"] is not None else None
            )
            item["offchain_supply_krw"] = (
                float(r["offchain_supply_krw"])
                if r["offchain_supply_krw"] is not None
                else None
            )

        if metric in ("all", "onchain"):
            item["onchain_price"] = (
                float(r["onchain_price"]) if r["onchain_price"] is not None else None
            )
            item["theoretical_price"] = (
                float(r["theoretical_price"])
                if r["theoretical_price"] is not None
                else None
            )

        points.append(item)

    return {
        "metric": metric,
        "from": from_ts,
        "to": to_ts,
        "count": len(points),
        "points": points,
    }


# 🔽🔽🔽 여기부터만 새로 추가 🔽🔽🔽

async def get_full_reserve_history(
    metric: Metric = "all",
    from_ts: Optional[str] = None,
    to_ts: Optional[str] = None,
    limit: int = 1000,
):
    """
    MCP HTTP Gateway에서 직접 호출하는 래퍼 함수.
    내부적으로 fetch_full_reserve_history를 그대로 호출한다.
    """
    return await fetch_full_reserve_history(
        metric=metric,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=limit,
    )
