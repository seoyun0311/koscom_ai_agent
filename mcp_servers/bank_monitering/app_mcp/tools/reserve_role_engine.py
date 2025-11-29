# app_mcp/tools/reserve_role_engine.py

from __future__ import annotations
from typing import List, Dict, Optional
from pydantic import BaseModel
from fastapi import HTTPException

from app_mcp.tools.compute_fss import compute_fss_for_bank
from app_mcp.tools.fss_core import compute_fss


# ───────────────────────────────────
# ROLE 정의 — custody_agent 로 통일
# ───────────────────────────────────

ROLE_WEIGHTS = {
    "policy_bank": 0.5,
    "custody_agent": 0.01,        # 예탁결제원 / 단일관리 출금불가 기관
    "commercial_bank": 1.0,
    "secondary_custodian": 1.2,
    "broker": 1.6,
    "other": 2.0,
}

ROLE_TARGET_LIMIT = {
    "policy_bank": 0.40,
    "custody_agent": 0.00,        # 절대 예치 X
    "commercial_bank": 0.15,
    "secondary_custodian": 0.10,
    "broker": 0.07,
    "other": 0.03,
}


# ───────────────────────────────────
# ROLE 탐지 로직 — 정확도 개선 버전
# ───────────────────────────────────

def detect_role(name: str) -> str:
    n = name.lower()

    # KSD
    if "예탁" in n or "ksd" in n or "예탁결제" in n:
        return "custody_agent"

    # 정책은행
    if "산업은행" in n or "kdb" in n:
        return "policy_bank"
    if "기업은행" in n or "ibk" in n:
        return "policy_bank"

    # 시중은행 (정확 매칭)
    if n.startswith("신한") or "shinhan" in n:
        return "commercial_bank"
    if n.startswith("국민") or n.startswith("kb") or "kbstar" in n:
        return "commercial_bank"
    if n.startswith("우리") or "woori" in n:
        return "commercial_bank"

    # 커스터디(백업 은행)
    if n.startswith("하나") or "hana" in n:
        return "secondary_custodian"

    # 증권사
    if "투자증권" in n or "증권" in n or "nh투자" in n or "futureasset" in n:
        return "broker"

    return "other"


# ───────────────────────────────────
# 데이터 모델
# ───────────────────────────────────

class Institution(BaseModel):
    bank_id: str
    name: str
    exposure: float
    role: Optional[str] = None
    fss: Optional[float] = None


class TargetAllocation(BaseModel):
    bank_id: str
    name: str
    role: str
    fss: float
    target_pct: float
    target_amount: float


# ───────────────────────────────────
# FSS 자동 주입
# ───────────────────────────────────

async def auto_fill_fss(inst: Institution):

    # custody_agent → FSS 없음
    if inst.role == "custody_agent":
        inst.fss = None
        return None

    if inst.fss is not None:
        return inst.fss

    # 정책은행은 고정점수 (공식재무제표 없음)
    if inst.role == "policy_bank":
        inst.fss = 85
        return 85

    # 일반은행/증권
    try:
        res = await compute_fss_for_bank(inst.name)
        inst.fss = res["fss"]
        return inst.fss
    except:
        inst.fss = 70
        return 70


# ───────────────────────────────────
# TARGET ALLOCATION 계산
# ───────────────────────────────────

def compute_target_allocation(
    institutions: List[Institution],
    total_reserve: float,
):
    alloc_pool = []
    custody_pool = []

    # 1) custody_agent 분리
    for inst in institutions:
        role = inst.role

        if role == "custody_agent":
            custody_pool.append(inst)
            continue

        fss = inst.fss if inst.fss is not None else 70
        role_weight = ROLE_WEIGHTS[role]

        base_weight = (fss / 100) / role_weight

        alloc_pool.append({
            "bank_id": inst.bank_id,
            "name": inst.name,
            "role": role,
            "fss": fss,
            "base_weight": base_weight,
            "exposure": inst.exposure,
        })

    total_base = sum(a["base_weight"] for a in alloc_pool)
    if total_base <= 0:
        raise HTTPException(500, "base_weight 계산 실패")

    # 2) 비중 배분
    results = []
    for a in alloc_pool:
        pct = a["base_weight"] / total_base

        # cap 적용
        cap = ROLE_TARGET_LIMIT[a["role"]]
        pct = min(pct, cap)

        a["target_pct"] = pct
        a["target_amount"] = pct * total_reserve
        results.append(TargetAllocation(**a))

    return {
        "banks": results,
        "custody": [
            {
                "bank_id": c.bank_id,
                "name": c.name,
                "role": "custody_agent",
                "exposure": c.exposure,
                "target_pct": 0,
                "target_amount": 0
            }
            for c in custody_pool
        ]
    }


# ───────────────────────────────────
# REBALANCE — (custody 제외)
# ───────────────────────────────────
def compute_rebalance_plan(institutions, target_alloc):

    # custody 제외
    institutions = [i for i in institutions if i.role != "custody_agent"]
    targets_list = [t for t in target_alloc["banks"] if t.role != "custody_agent"]

    custody_ids = {c["bank_id"] for c in target_alloc["custody"]}

    cur_map = {
        i.bank_id: i.exposure
        for i in institutions
        if i.bank_id not in custody_ids
    }

    tgt_map = {t.bank_id: t.target_amount for t in targets_list}

    over = []
    under = []
    for bid, cur in cur_map.items():
        tgt = tgt_map.get(bid, 0)
        diff = cur - tgt

        if diff > 0:
            over.append((bid, diff))
        elif diff < 0:
            under.append((bid, -diff))

    plan = []
    for src, amt_over in over:
        for dst, amt_need in under:
            move = min(amt_over, amt_need)
            if move <= 0:
                continue

            plan.append({"from": src, "to": dst, "amount": move})

            amt_over -= move
            amt_need -= move

    return plan



# ───────────────────────────────────
# MCP 등록
# ───────────────────────────────────

def register(mcp):

    @mcp.tool(name="role_based_allocation")
    async def _alloc(payload: Dict):
        insts = [Institution(**i) for i in payload["institutions"]]

        for i in insts:
            i.role = detect_role(i.name)
            await auto_fill_fss(i)

        total = sum(i.exposure for i in insts)
        result = compute_target_allocation(insts, total)

        return result

    @mcp.tool(name="role_based_rebalance")
    async def _rebalance(payload: Dict):
        insts = [Institution(**i) for i in payload["institutions"]]

        for i in insts:
            i.role = detect_role(i.name)
            await auto_fill_fss(i)

        total = sum(i.exposure for i in insts)
        alloc = compute_target_allocation(insts, total)
        plan = compute_rebalance_plan(insts, alloc)

        return {
            "allocation": alloc,
            "rebalance_plan": plan
        }
