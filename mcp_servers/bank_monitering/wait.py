"""
bank_monitoring MCP HTTP Gateway
FastMCP 대신 표준 HTTP 엔드포인트로 MCP 툴 제공
"""

from flask import Flask, request, jsonify
import asyncio
import threading
import traceback

# 🔥 bank_monitoring 내부 app_mcp 모듈 import 경로 수정됨
from app_mcp.tools.compute_fss import (
    compute_fss_for_bank,
    get_latest_fss,
)

from core.db import init_schema


# =====================================================
# 글로벌 Event Loop (asyncpg, MCP 툴 공용)
# =====================================================

GLOBAL_LOOP = asyncio.new_event_loop()


def _run_global_loop(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    loop.run_forever()


# 데몬 스레드 실행
_loop_thread = threading.Thread(target=_run_global_loop, args=(GLOBAL_LOOP,), daemon=True)
_loop_thread.start()


def run_async(coro):
    future = asyncio.run_coroutine_threadsafe(coro, GLOBAL_LOOP)
    return future.result()


# =====================================================
# 기존 MCP Tools Import
# =====================================================

from mcp_servers.bank_monitering.app_mcp.tools.bank_name_normalizer import normalize_name

from mcp_servers.bank_monitering.app_mcp.tools.bank_risk import (
    get_bank_risk_score,
    run_bank_stress_test,
    suggest_bank_rebalance,
)

from mcp_servers.bank_monitering.app_mcp.tools.dart_financials import (
    bank_financials_by_name,
    dart_financials_summary,
)

from mcp_servers.bank_monitering.app_mcp.tools.credit import calc_bank_ratios

from mcp_servers.bank_monitering.app_mcp.tools.disclosures import (
    resolve_corp_code,
    corp_codes_search,
)

from mcp_servers.bank_monitering.app_mcp.tools.policy_check import (
    check_policy_compliance,
    get_rebalancing_suggestions,
)

# 🔥 역할 기반 엔진 (경로 수정됨)
from mcp_servers.bank_monitering.app_mcp.tools.reserve_role_engine import (
    Institution,
    compute_target_allocation,
    compute_rebalance_plan,
    detect_role,
    auto_fill_fss,
)


# =====================================================
# Flask App
# =====================================================

app = Flask(__name__)


# =====================================================
# 역할 기반 Wrapper
# =====================================================

async def role_based_allocation_http(params):

    raw_insts = params.get("institutions", [])

    insts = []
    for i in raw_insts:
        inst = Institution(
            bank_id=i.get("bank_id"),
            name=i.get("name"),
            exposure=i.get("exposure"),
            role=i.get("role"),
            fss=i.get("fss"),
        )
        insts.append(inst)

    # role 자동 설정 + FSS 자동 주입
    for inst in insts:
        inst.role = detect_role(inst.name)
        await auto_fill_fss(inst)

    total = sum(i.exposure for i in insts)
    result = compute_target_allocation(insts, total)

    # Pydantic 객체 → dict 변환
    banks_out = [b.model_dump() for b in result["banks"]]
    custody_out = result["custody"]

    return {
        "banks": banks_out,
        "custody": custody_out,
    }


async def role_based_rebalance_http(params):
    raw_insts = params.get("institutions", [])
    insts = []

    for i in raw_insts:
        inst = Institution(
            bank_id=i.get("bank_id"),
            name=i.get("name"),
            exposure=i.get("exposure"),
            role=i.get("role"),
            fss=i.get("fss"),
        )
        insts.append(inst)

    # role & fss 자동 세팅
    for inst in insts:
        inst.role = detect_role(inst.name)
        await auto_fill_fss(inst)

    total = sum(i.exposure for i in insts)
    allocation = compute_target_allocation(insts, total)
    plan = compute_rebalance_plan(insts, allocation)

    # targets flatten
    targets = []
    for section in ("banks", "custody"):
        for item in allocation.get(section, []):
            if hasattr(item, "model_dump"):
                data = item.model_dump()
            else:
                data = dict(item)
            data["category"] = section
            targets.append(data)

    return {
        "targets": targets,
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
                "interest_shock_bps": 0.0,
            })
        )
    ),
    "suggest_bank_rebalance": lambda params: run_async(suggest_bank_rebalance(**params)),

    # DART 재무제표
    "bank_financials_by_name": lambda params: run_async(bank_financials_by_name(**params)),
    "dart_financials_summary": lambda params: run_async(dart_financials_summary(**params)),
    "calc_bank_ratios": lambda params: run_async(calc_bank_ratios(**params)),

    # 공시
    "resolve_corp_code": lambda params: run_async(resolve_corp_code(**params)),
    "corp_codes_search": lambda params: run_async(corp_codes_search(**params)),

    # 정책 점검
    "check_policy_compliance": lambda params: run_async(check_policy_compliance(**params)),
    "get_rebalancing_suggestions": lambda params: run_async(get_rebalancing_suggestions(**params)),

    # 역할 기반 엔진
    "role_based_allocation": lambda params: run_async(role_based_allocation_http(params)),
    "role_based_rebalance": lambda params: run_async(role_based_rebalance_http(params)),

    # FSS 계산 / 조회
    "compute_fss_for_bank": lambda params: run_async(compute_fss_for_bank(params)),
    "get_latest_fss": lambda params: run_async(get_latest_fss({
        "bank_id": params.get("bank_id")
    })),
}


# =====================================================
# HTTP Router
# =====================================================

@app.route("/mcp", methods=["POST"])
def mcp_gateway():
    try:
        data = request.json
        tool = data.get("tool")
        params = data.get("params", {}) or {}

        print(f"🔧 MCP 호출: {tool}({params})")

        if tool not in TOOL_MAP:
            return jsonify({
                "success": False,
                "error": f"Unknown tool: {tool}",
            }), 404

        result = TOOL_MAP[tool](params)

        print(f"✅ 툴 실행 성공: {tool}")

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


# =====================================================
# MAIN
# =====================================================

if __name__ == "__main__":
    # asyncpg 스키마 초기화
    run_async(init_schema())

    print("=" * 70)
    print("🚀 Bank Monitoring MCP HTTP Gateway")
    print("=" * 70)
    print("📍 Endpoint: http://localhost:5300/mcp")
    print("🛠 Available Tools:")
    for t in TOOL_MAP.keys():
        print(f" - {t}")
    print("=" * 70)

    app.run(host="0.0.0.0", port=5300, debug=True)
