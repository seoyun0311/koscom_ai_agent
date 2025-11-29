#!/usr/bin/env python3
"""
KRWS Reserve Verification MCP Server
원화 스테이블코인 1:1 완전 담보 실시간/히스토리 검증 MCP

실행:
    python mcp_server.py
또는:
    uv run mcp_server.py

환경변수:
    PG_DSN        (선택) 전체 DSN. 예: postgres://user:pass@host:5432/dbname
    PG_HOST       기본: localhost
    PG_PORT       기본: 5432
    PG_DB         기본: postgres
    PG_USER       기본: postgres
    PG_PASSWORD   기본: 빈 문자열
"""

import os
import sys
import asyncio
from typing import Optional, Literal, Dict, Any, List

import asyncpg
from mcp.server.stdio import stdio_server
from mcp.server.fastmcp import FastMCP


# -----------------------
# MCP 서버 인스턴스
# -----------------------
server = FastMCP("krws-full-reserve")

Metric = Literal["all", "coverage", "onchain", "offchain"]

_pool: Optional[asyncpg.Pool] = None


# -----------------------
# DB 연결 풀
# -----------------------
async def get_pool() -> asyncpg.Pool:
    """전역 asyncpg 커넥션 풀"""
    global _pool
    if _pool is not None:
        return _pool

    dsn = os.getenv("PG_DSN")
    if dsn:
        _pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
    else:
        _pool = await asyncpg.create_pool(
            host=os.getenv("PG_HOST", "l27.0.0.1"),
            port=int(os.getenv("PG_PORT", "5432")),
            database=os.getenv("PG_DB", "dancom_db"),
            user=os.getenv("PG_USER", "dancom"),
            password=os.getenv("PG_PASSWORD", "1q2w3e4r!"),
            min_size=1,
            max_size=5,
        )
    return _pool

# -----------------------
# 실제 조회 로직
# -----------------------
async def _fetch_full_reserve_history(
    metric: Metric = "all",
    from_ts: Optional[str] = None,
    to_ts: Optional[str] = None,
    limit: int = 1000,
) -> Dict[str, Any]:
    """
    stablecoin.full_reserve_history VIEW 에서 히스토리 조회.
    metric 에 따라 리턴되는 필드가 달라진다.
    """
    # limit 가드
    if limit <= 0:
        limit = 1
    if limit > 5000:
        limit = 5000

    pool = await get_pool()

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

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, from_ts, to_ts, limit)

    points: List[Dict[str, Any]] = []

    for r in rows:
        item: Dict[str, Any] = {
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


# -----------------------
# MCP 툴 정의
# -----------------------
@server.tool()
async def full_reserve_history(
    metric: Metric = "all",
    from_ts: Optional[str] = None,
    to_ts: Optional[str] = None,
    limit: int = 1000,
) -> Dict[str, Any]:
    """
    KRWS 1:1 풀리저브 스테이블코인의 히스토리를 조회합니다.

    Args:
        metric:
            - "all"       : 모든 필드 반환
            - "coverage"  : 담보율 / 준비금 / 오프체인 공급만
            - "onchain"   : 온체인 가격 / 이론가만
            - "offchain"  : 오프체인 공급만
        from_ts: 조회 시작 시각 (ISO8601, 예: "2025-11-26T00:00:00+09:00")
        to_ts:   조회 종료 시각 (포함, ISO8601)
        limit:   최대 포인트 수 (1~5000)
    """
    return await _fetch_full_reserve_history(
        metric=metric,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=limit,
    )


@server.tool()
async def ping() -> str:
    """헬스체크용 간단 툴"""
    return "krws-full-reserve mcp is alive"


# -----------------------
# MCP 서버 엔트리포인트
# -----------------------
async def main():
    """stdio 기반 MCP 서버 시작"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n서버를 종료합니다.", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"오류 발생: {e}", file=sys.stderr)
        sys.exit(1)
