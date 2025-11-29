"""
bank_monitoring MCP HTTP Gateway
FastMCP 대신 표준 HTTP 엔드포인트로 MCP 툴 제공
"""

from flask import Flask, request, jsonify
import asyncio
import threading
import traceback
from app_mcp.tools.compute_fss import compute_fss_for_bank, get_latest_fss
from core.db import init_schema

# =====================================================
# 글로벌 Event Loop (asyncpg, MCP 툴 공용)
# =====================================================

# 하나의 전역 이벤트 루프를 만들고, 별도 스레드에서 run_forever로 돌린다.
GLOBAL_LOOP = asyncio.new_event_loop()


def _run_global_loop(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    loop.run_forever()


# 데몬 스레드로 이벤트 루프 실행
_loop_thread = threading.Thread(target=_run_global_loop, args=(GLOBAL_LOOP,), daemon=True)
_loop_thread.start()


def run_async(coro):
    """
    어느 곳에서든 동일 GLOBAL_LOOP 위에서 코루틴을 실행하고 결과를 동기적으로 반환.
    """
    future = asyncio.run_coroutine_threadsafe(coro, GLOBAL_LOOP)
    return future.result()


# =====================================================
# 기존 MCP Tools Import
# =====================================================

from app_mcp.tools.bank_name_normalizer import normalize_name

from app_mcp.tools.bank_risk import (
    get_bank_risk_score,
    run_bank_stress_test,
    suggest_bank_rebalance,
)

from app_mcp.tools.dart_financials import (
    bank_financials_by_name,
    dart_financials_summary,
)

from app_mcp.tools.credit import calc_bank_ratios

from app_mcp.tools.disclosures import (
    resolve_corp_code,
    corp_codes_search,
)

from app_mcp.tools.policy_check import (
    check_policy_compliance,
    get_rebalancing_suggestions,
)

# 🔥 역할 기반 배분 엔진
from app_mcp.tools.reserve_role_engine import (
    Institution,
    compute_target_allocation,
    compute_rebalance_plan,
)

# 🔥🔥🔥 FSS 계산 툴
from app_mcp.tools.compute_fss import compute_fss_for_bank


# =====================================================
# Flask App
# =====================================================

app = Flask(__name__)


# =====================================================
# 역할 기반 Wrapper
# =====================================================

async def role_based_allocation_http(params):

    # 1) 요청에서 institutions 파싱
    raw_insts = params.get("institutions", [])

    # 2) 각각에 대해 Institution 객체 생성 + fss 값 보존
    insts = []
    fss_map = {}  # bank_id -> fss

    for i in raw_insts:
        bank_id = i.get("bank_id")
        fss = i.get("fss", None)
        if fss is not None:
            fss_map[bank_id] = fss

        insts.append(Institution(
            bank_id=bank_id,
            name=i.get("name"),
            exposure=i.get("exposure"),
            role=i.get("role")
        ))

    # 총 exposure 합계
    total = sum(i.exposure for i in insts)

    # 3) 역할 기반 타깃 비중 계산
    result = compute_target_allocation(insts, total)

    # 4) banks 리스트에 FSS score 주입
    banks_out = []
    for b in result["banks"]:
        data = b.model_dump()
        bank_id = data.get("bank_id")
        if bank_id in fss_map:
            data["fss"] = fss_map[bank_id]
        banks_out.append(data)

    # 5) custody도 그대로 전달
    return {
        "banks": banks_out,
        "custody": result["custody"]
    }



def role_based_rebalance_http(params):
    insts = [Institution(**i) for i in params.get("institutions", [])]
    total = sum(i.exposure for i in insts)
    targets = compute_target_allocation(insts, total)
    plan = compute_rebalance_plan(insts, targets)
    return {
        "targets": [t.model_dump() for t in targets],
        "rebalance_plan": [p.model_dump() for p in plan],
    }


# =====================================================
# TOOL MAP
# =====================================================

TOOL_MAP = {
    # 기본 정규화
    "normalize_bank_name": lambda params: {
        "input": params.get("bank_name"),
        "normalized": normalize_name(params.get("bank_name", "")),
    },

    # 리스크 분석
    "get_bank_risk_score": lambda params: run_async(get_bank_risk_score(**params)),
    "run_bank_stress_test": lambda params: run_async(
        run_bank_stress_test(
            exposures=params.get("exposures", []),
            scenario=params.get("scenario", {
                "bank_liquidity_shock": {},
                "daily_runoff_rate": 0.10,
                "interest_shock_bps": 0.0
            })
        )
    ),
    "suggest_bank_rebalance": lambda params: run_async(suggest_bank_rebalance(**params)),

    # DART 재무제표
    "bank_financials_by_name": lambda params: run_async(bank_financials_by_name(**params)),
    "dart_financials_summary": lambda params: run_async(dart_financials_summary(**params)),
    "calc_bank_ratios": lambda params: run_async(calc_bank_ratios(**params)),

    # 공시 / Corp Code
    "resolve_corp_code": lambda params: run_async(resolve_corp_code(**params)),
    "corp_codes_search": lambda params: run_async(corp_codes_search(**params)),

    # 정책 점검
    "check_policy_compliance": lambda params: run_async(check_policy_compliance(**params)),
    "get_rebalancing_suggestions": lambda params: run_async(get_rebalancing_suggestions(**params)),

    # 역할 기반 엔진
    "role_based_allocation": lambda params: run_async(role_based_allocation_http(params)),
    # "role_based_rebalance": lambda params: role_based_rebalance_http(params),
    "role_based_rebalance": lambda params: run_async(role_based_rebalance_http(params)),
    "compute_fss_for_bank": lambda params: run_async(compute_fss_for_bank(params)),
    "get_latest_fss": lambda params: run_async(get_latest_fss(params)),
    # 🔥🔥🔥 FSS 계산 메인 함수
    # params 예:
    # {
    #   "bank_id": "SHINHAN",
    #   "name": "신한은행",
    #   "group_id": "SHINHAN_GROUP",
    #   "region": "KR",
    #   "score_income": 80,
    #   "score_capital": 70,
    #   "score_liquidity": 85,
    #   "score_asset": 75
    # }
    "compute_fss_for_bank": lambda params: run_async(compute_fss_for_bank(params)),

}


# =====================================================
# HTTP Router
# =====================================================

@app.route("/mcp", methods=["POST"])
def mcp_gateway():
    try:
        data = request.json
        tool_name = data.get("tool")
        params = data.get("params", {}) or {}

        print(f"🔧 MCP 호출: {tool_name}({params})")

        if tool_name not in TOOL_MAP:
            return jsonify({
                "success": False,
                "error": f"Unknown tool: {tool_name}",
            }), 404

        result = TOOL_MAP[tool_name](params)

        print(f"✅ 툴 실행 성공: {tool_name}")

        return jsonify({
            "success": True,
            "result": result,
        })

    except Exception as e:
        print(f"❌ MCP Gateway 에러: {e}")
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "tools": list(TOOL_MAP.keys())
    })


if __name__ == "__main__":
    # DB 스키마 초기화도 같은 GLOBAL_LOOP에서 실행
    run_async(init_schema())

    print("=" * 70)
    print("🚀 Bank Monitoring MCP HTTP Gateway")
    print("=" * 70)
    print("📍 Endpoint: http://localhost:5300/mcp")
    print("🛠 Available Tools:")
    for tool in TOOL_MAP.keys():
        print(f" - {tool}")
    print("=" * 70)

    app.run(host="0.0.0.0", port=5300, debug=True)