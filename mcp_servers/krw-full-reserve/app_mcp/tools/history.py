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
    - from_ts, to_ts: ISO8601 문자열 (예: "2025-01-20T00:00:00+09:00")
    """

    # 🔹 문자열로 들어온 from_ts/to_ts 를 datetime으로 변환
    dt_from = None
    dt_to = None

    if from_ts:
        # '...Z' 형태도 들어올 수 있으니 방어적으로 처리
        s = from_ts.replace("Z", "+00:00")
        dt_from = datetime.fromisoformat(s)

    if to_ts:
        s = to_ts.replace("Z", "+00:00")
        dt_to = datetime.fromisoformat(s)

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
            FROM stablecoin.full_reserve_history
            WHERE ($1::timestamptz IS NULL OR timestamp >= $1::timestamptz)
              AND ($2::timestamptz IS NULL OR timestamp <= $2::timestamptz)
            ORDER BY timestamp
            LIMIT $3
        """
        # ⬅️ 여기서 이제 datetime 객체 넘김
        rows = await conn.fetch(sql, dt_from, dt_to, limit)

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


async def get_full_reserve_history(
    metric: Metric = "all",
    from_ts: Optional[str] = None,
    to_ts: Optional[str] = None,
    limit: int = 1000,
):
    return await fetch_full_reserve_history(
        metric=metric,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=limit,
    )
