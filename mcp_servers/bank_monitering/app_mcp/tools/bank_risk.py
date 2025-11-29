# app_mcp/tools/bank_risk.py

from __future__ import annotations

from typing import Any, Dict, List, Optional
import json

# 기존 import 제거
# from core.db import get_fss_for_bank, insert_risk_run

# DB pool만 import
from core.db import get_pool

from core.bank_risk import (
    CreditRating,
    MaturityBucket,
    BankExposure,
    PolicyConfig,
    BankRiskEngine,
    BankRiskScoreInput,
    BankRiskScoreResult,
    StressScenarioConfig,
    StressResult,
    RebalanceSuggestion,
    RATING_RWA_WEIGHT,
)


# ─────────────────────────────────────────────
# 공용 엔진 인스턴스
# ─────────────────────────────────────────────

POLICY = PolicyConfig()
ENGINE = BankRiskEngine(POLICY)


# ─────────────────────────────────────────────
# DB ACCESS FUNCTIONS (중요)
# ─────────────────────────────────────────────

async def get_fss_for_bank(bank_id: str):
    """
    fss_snapshots 에서 bank_id 로 최신 FSS 점수 조회
    """
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT fss_score, bank_id, created_at
        FROM fss_snapshots
        WHERE bank_id = $1
        ORDER BY created_at DESC
        LIMIT 1
        """,
        bank_id,
    )
    return row


async def insert_risk_run(
    total_exposure: float,
    hhi: float,
    top3_share: float,
    top3_breach: bool,
    raw_exposures: Any,
    bank_details: Any,
) -> int:
    """
    risk_runs 테이블에 결과 저장
    """
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO risk_runs (
            total_exposure,
            hhi,
            top3_share,
            top3_breach,
            raw_exposures,
            bank_details
        )
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id
        """,
        total_exposure,
        hhi,
        top3_share,
        top3_breach,
        json.dumps(raw_exposures),
        json.dumps(bank_details),
    )
    return row["id"]


# ─────────────────────────────────────────────
# JSON → BankExposure 변환 헬퍼
# ─────────────────────────────────────────────

def _deserialize_exposure(x: Dict[str, Any]) -> BankExposure:
    """
    웹/MCP에서 넘어온 dict를 BankExposure로 변환.
    """

    credit_raw = (x.get("credit_rating") or "NR").upper()
    if credit_raw in CreditRating.__members__:
        credit_rating = CreditRating[credit_raw]
    else:
        credit_rating = CreditRating.NR

    maturity_raw = x.get("maturity_bucket", "ON")

    try:
        maturity_bucket = MaturityBucket(maturity_raw)
    except Exception:
        try:
            maturity_bucket = MaturityBucket[maturity_raw]
        except Exception:
            maturity_bucket = MaturityBucket.OVERNIGHT

    return BankExposure(
        bank_id=str(x.get("bank_id", "")),
        name=str(x.get("name", "")),
        group_id=str(x.get("group_id", "")),
        region=str(x.get("region", "KR")),
        exposure=float(x.get("exposure", 0.0)),
        credit_rating=credit_rating,
        lcr=x.get("lcr"),
        insured_limit=x.get("insured_limit"),
        maturity_bucket=maturity_bucket,
        rwa_weight=x.get("rwa_weight"),
        cds_spread_bps=x.get("cds_spread_bps"),
        bond_spread_bps=x.get("bond_spread_bps"),
        news_sentiment=x.get("news_sentiment"),
    )


def _deserialize_exposures(items: List[Dict[str, Any]]) -> List[BankExposure]:
    return [_deserialize_exposure(x) for x in items]


# ─────────────────────────────────────────────
# MCP Tool: 은행 리스크 점수 1개
# ─────────────────────────────────────────────

async def get_bank_risk_score(
    exposure: Dict[str, Any],
    lcr_pct: Optional[float] = None,
    insured_ratio: Optional[float] = None,
    cds_spread_bps: Optional[float] = None,
    bond_spread_bps: Optional[float] = None,
    news_sentiment: Optional[float] = None,
) -> Dict[str, Any]:

    name = (exposure.get("name") or "").lower()

    # 🔥 KSD는 risk 평가 제외 (항상 AAA)
    if "예탁" in name or "ksd" in name:
        return {
            "bank_id": exposure.get("bank_id"),
            "name": exposure.get("name"),
            "score": 0.0,
            "detail": {
                "grade": "AAA",
                "excluded": True,
                "reason": "custody_agent_excluded"
            }
        }

    # 정상 은행 risk 계산
    bex = _deserialize_exposure(exposure)
    rwa = exposure.get("rwa_weight")
    if rwa is None:
        rwa = RATING_RWA_WEIGHT.get(bex.credit_rating, 1.0)

    inp = BankRiskScoreInput(
        exposure=bex,
        rwa_weight=rwa,
        lcr_pct=lcr_pct,
        insured_ratio=insured_ratio,
        cds_spread_bps=cds_spread_bps,
        bond_spread_bps=bond_spread_bps,
        news_sentiment=news_sentiment,
    )

    result: BankRiskScoreResult = ENGINE.compute_bank_risk_score(inp)

    return {
        "bank_id": result.bank_id,
        "name": result.name,
        "score": result.score,
        "detail": result.detail
    }


# ─────────────────────────────────────────────
# MCP Tool: 스트레스 테스트
# ─────────────────────────────────────────────

async def run_bank_stress_test(
    exposures: List[Dict[str, Any]],
    scenario: Dict[str, Any],
) -> Dict[str, Any]:

    ex_list = _deserialize_exposures(exposures)

    sc = StressScenarioConfig(
        bank_liquidity_shock=scenario.get("bank_liquidity_shock", {}) or {},
        daily_runoff_rate=float(scenario.get("daily_runoff_rate", 0.10)),
        interest_rate_shock_bps=float(scenario.get("interest_shock_bps", 0.0)),
    )

    res: StressResult = ENGINE.run_stress(ex_list, sc)

    return {
        "total_exposure": res.total_exposure,
        "unavailable_amount": res.unavailable_amount,
        "run_off_amount": res.run_off_amount,
        "net_liquid_assets": res.net_liquid_assets,
        "coverage_ratio": res.coverage_ratio,
        "detail_by_bank": res.detail_by_bank,
    }


# ─────────────────────────────────────────────
# MCP Tool: 자동 재예치 (재밸런싱)
# ─────────────────────────────────────────────

async def suggest_bank_rebalance(
    exposures: List[Dict[str, Any]],
    scores_override: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:

    ex_list = _deserialize_exposures(exposures)
    score_map: Dict[str, BankRiskScoreResult] = {}

    if scores_override:
        for e in ex_list:
            score = float(scores_override.get(e.bank_id, 70.0))
            score_map[e.bank_id] = BankRiskScoreResult(
                bank_id=e.bank_id,
                name=e.name,
                score=score,
                detail={"override": score},
            )
    else:
        for e in ex_list:

            # 🔥 custody_agent(KSD)는 rebalance 대상 제외
            lname = e.name.lower()
            if "예탁" in lname or "ksd" in lname:
                continue

            inp = BankRiskScoreInput(
                exposure=e,
                rwa_weight=RATING_RWA_WEIGHT.get(e.credit_rating, 1.0),
            )
            r = ENGINE.compute_bank_risk_score(inp)
            score_map[e.bank_id] = r

    sug: RebalanceSuggestion = ENGINE.suggest_rebalance(ex_list, score_map)

    return {
        "comment": sug.comment,
        "actions": [
            {
                "from_bank_id": a.from_bank_id,
                "to_bank_id": a.to_bank_id,
                "amount": a.amount,
                "reason": a.reason,
            }
            for a in sug.actions
        ],
    }


# ─────────────────────────────────────────────
# 실시간 위험 계산
# ─────────────────────────────────────────────

def _compute_realtime_risk(banks: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = sum(b["exposure"] for b in banks) or 1.0

    for b in banks:
        share = b["exposure"] / total
        b["share"] = share
        b["share_pct"] = share * 100
        b["single_limit_breach"] = share > 0.30
        b["realtime_risk_score"] = b["fss_score"] * share

    shares_sorted = sorted((b["share"] for b in banks), reverse=True)
    top3_share = sum(shares_sorted[:3])
    top3_breach = top3_share > 0.70

    hhi = sum((b["share"] * 100) ** 2 for b in banks)

    return {
        "banks": banks,
        "total_exposure": total,
        "top3_share": top3_share,
        "top3_breach": top3_breach,
        "hhi": hhi,
    }


# ─────────────────────────────────────────────
# MCP Tool: 실시간 리스크 + DB 저장
# ─────────────────────────────────────────────

async def get_realtime_risk_dashboard(exposures: str) -> Dict[str, Any]:
    """
    exposures: JSON string
    [
      { "bank_id": "SHINHAN", "name": "신한은행", "role": "commercial_bank", "exposure": 20000000 },
      ...
    ]
    """
    data = json.loads(exposures)

    banks: List[Dict[str, Any]] = []
    for e in data:
        # 🔥 DB에서 최신 FSS score 가져오기
        fss_row = await get_fss_for_bank(e["bank_id"])
        if fss_row:
            fss_score = float(fss_row["fss_score"])
        else:
            fss_score = 50.0  # fallback 값

        banks.append({
            "bank_id": e["bank_id"],
            "name": e["name"],
            "role": e.get("role", "commercial_bank"),
            "exposure": float(e["exposure"]),
            "fss_score": fss_score,
        })

    # 계산 수행
    risk = _compute_realtime_risk(banks)

    # 🔥 DB 저장
    run_id = await insert_risk_run(
        total_exposure=risk["total_exposure"],
        hhi=risk["hhi"],
        top3_share=risk["top3_share"],
        top3_breach=risk["top3_breach"],
        raw_exposures=data,
        bank_details=risk["banks"],
    )

    risk["run_id"] = run_id
    return risk


# ─────────────────────────────────────────────
# MCP Tool Registry
# ─────────────────────────────────────────────

def register(mcp):
    mcp.add_tool(
        get_realtime_risk_dashboard,
        name="get_realtime_risk_dashboard",
        description=(
            "현재 예치액(exposures)과 DB에 저장된 FSS 점수를 이용해 "
            "예치은행 신용위험(HHI, 한도위반, 실시간 위험점수)을 계산하고 DB에 스냅샷을 저장합니다."
        ),
    )