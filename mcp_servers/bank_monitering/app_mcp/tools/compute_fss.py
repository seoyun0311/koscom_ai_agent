# app_mcp/tools/compute_fss.py

from __future__ import annotations
from typing import Any, Dict
import json
from core.db.pool import get_pool   # ← 올바른 import


# ─────────────────────────────────────────────
# FSS 최신 스냅샷 조회 (신규 Tool)
# ─────────────────────────────────────────────

async def get_latest_fss(params: Dict[str, Any]) -> Dict[str, Any]:
    bank_id = params.get("bank_id")
    if not bank_id:
        return {"success": False, "error": "bank_id is required"}

    pool = await get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT fss_score, created_at
            FROM stablecoin.fss_snapshots
            WHERE bank_id = $1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            bank_id
        )

    if not row:
        return {"success": True, "bank_id": bank_id, "fss_score": None}

    return {
        "success": True,
        "bank_id": bank_id,
        "fss_score": float(row["fss_score"]),
        "timestamp": row["created_at"].isoformat()
    }


# ─────────────────────────────────────────────
# DB INSERT / UPSERT
# ─────────────────────────────────────────────

async def upsert_bank_master(bank_id: str, name: str, group_id: str, region: str):
    """stablecoin.bank_master에 UPSERT"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO stablecoin.bank_master (bank_id, name, group_id, region, updated_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (bank_id)
            DO UPDATE SET
                name = EXCLUDED.name,
                group_id = EXCLUDED.group_id,
                region = EXCLUDED.region,
                updated_at = NOW()
            """,
            bank_id, name, group_id, region
        )


async def upsert_fss_snapshot(bank_id: str, fss_score: float, raw_json: Dict[str, Any]):
    """stablecoin.fss_snapshots에 스냅샷 INSERT"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO stablecoin.fss_snapshots (bank_id, fss_score, raw_json, created_at)
            VALUES ($1, $2, $3, NOW())
            """,
            bank_id, fss_score, json.dumps(raw_json, ensure_ascii=False)
        )


# ─────────────────────────────────────────────
# FSS 점수 계산
# ─────────────────────────────────────────────

async def compute_fss_for_bank(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    통합 FSS 계산:
    - compute_fss_for_bank(bank_id, ...)
    - compute_fss_for_bank(bank_name="신한은행")
    둘 다 지원
    """

    # 1) bank_name-only 자동 처리 모드
    if "bank_id" not in params:
        bank_name = params.get("bank_name")
        if not bank_name:
            raise ValueError("bank_id 또는 bank_name 중 하나 필요")

        bank_id = bank_name.upper()
        name = bank_name
        group_id = None
        region = "KR"

        # 기본 점수(임시): 원하면 bank_monitoring 엔진에서 자동 계산 가능
        score_income = 70
        score_capital = 70
        score_liquidity = 70
        score_asset = 70

    else:
        # 2) 상세 계산 요청 모드
        bank_id = params["bank_id"]
        name = params["name"]
        group_id = params.get("group_id")
        region = params.get("region", "KR")

        score_income = float(params["score_income"])
        score_capital = float(params["score_capital"])
        score_liquidity = float(params["score_liquidity"])
        score_asset = float(params["score_asset"])

    print(">>> compute_fss_for_bank called:", bank_id, name)

    # 계산 방식 조정 가능
    fss_score = (
        score_income * 0.25 +
        score_capital * 0.25 +
        score_liquidity * 0.25 +
        score_asset * 0.25
    )

    # DB 저장
    print(">>> upsert_bank_master")
    await upsert_bank_master(bank_id, name, group_id, region)

    print(">>> upsert_fss_snapshot")
    await upsert_fss_snapshot(bank_id, fss_score, {
        "score_income": score_income,
        "score_capital": score_capital,
        "score_liquidity": score_liquidity,
        "score_asset": score_asset,
    })

    return {
        "bank_id": bank_id,
        "name": name,
        "fss_score": fss_score,
    }


# ─────────────────────────────────────────────
# MCP Tool 등록
# ─────────────────────────────────────────────

def register(mcp):
    # 1) FSS 계산
    mcp.add_tool(
        compute_fss_for_bank,
        name="compute_fss_for_bank",
        description="재무·건전성 점수(FSS) 계산 후 DB 스냅샷 저장",
    )

    # 2) 최신 FSS 조회
    mcp.add_tool(
        get_latest_fss,
        name="get_latest_fss",
        description="가장 최근 저장된 FSS 점수를 반환합니다.",
    )


# ─────────────────────────────────────────────
# 참고용 점수 계산 (현재 사용 안함)
# ─────────────────────────────────────────────

def _fss_from_normalized(normalized: dict) -> float:
    """
    DART normalized dict 기반 간단 FSS 계산(참고)
    """
    score = 0.0

    er = normalized.get("equity_ratio")
    if er is not None:
        if er >= 0.08:
            score += 40
        elif er >= 0.05:
            score += 25
        else:
            score += 10

    lev = normalized.get("leverage")
    if lev is not None:
        if lev <= 12:
            score += 20
        elif lev <= 20:
            score += 10
        else:
            score += 5

    cr = normalized.get("current_ratio")
    if cr is not None:
        if cr >= 1.1:
            score += 20
        elif cr >= 1.0:
            score += 10
        else:
            score += 5

    return min(score, 100.0)
