# krw-full-reserve/mcp_http_gateway.py
"""
KRW Full Reserve MCP HTTP Gateway
"""

from __future__ import annotations

import asyncio
import json
import traceback
import threading
from typing import Dict, Any

from flask import Flask, request, jsonify

# ─────────────────────────────────────────────
# 글로벌 이벤트 루프 생성 + 백그라운드 스레드에서 실행
# ─────────────────────────────────────────────
loop = asyncio.new_event_loop()
threading.Thread(target=loop.run_forever, daemon=True).start()


# ─────────────────────────────────────────────
# KRW fullreserve 툴 함수들
# ─────────────────────────────────────────────
from app_mcp.tools.onchain import get_onchain_state
from app_mcp.tools.offchain import get_offchain_reserves
from app_mcp.tools.coverage import check_coverage
from app_mcp.tools.report import get_risk_report
from app_mcp.tools.history import get_full_reserve_history


# Flask 앱
app = Flask(__name__)

# MCP 툴 매핑
TOOLS: Dict[str, Any] = {
    "get_onchain_state": get_onchain_state,
    "get_offchain_reserves": get_offchain_reserves,
    "check_coverage": check_coverage,
    "get_risk_report": get_risk_report,
    "get_full_reserve_history": get_full_reserve_history,
}


# ─────────────────────────────────────────────
# async 함수 실행 안전 헬퍼
# ─────────────────────────────────────────────
def _run_async(func, **kwargs):
    """
    모든 async 함수는 글로벌 event loop 에서 thread-safe 로 실행한다.
    """
    if asyncio.iscoroutinefunction(func):
        coro = func(**kwargs)
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result()
    else:
        return func(**kwargs)


# ─────────────────────────────────────────────
# MCP HTTP 진입점
# ─────────────────────────────────────────────
@app.route("/mcp", methods=["POST"])
def mcp_call():
    try:
        payload = request.get_json(silent=True) or {}
        print(f"🛰 KRW HTTP MCP 수신 payload: {payload}")

        method = payload.get("method")
        rpc_id = payload.get("id")
        params = payload.get("params") or {}

        if method != "tools/call":
            return jsonify({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {
                    "code": -32601,
                    "message": f"Unsupported method: {method}"
                }
            }), 400

        tool_name = params.get("name")
        arguments = params.get("arguments") or {}

        if tool_name not in TOOLS:
            return jsonify({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {
                    "code": -32601,
                    "message": f"Unknown tool: {tool_name}"
                }
            }), 400

        func = TOOLS[tool_name]

        print(f"🔧 KRW MCP 호출: {tool_name}({arguments})")

        if tool_name == "get_risk_report" and "format" in arguments:
            arguments.pop("format", None)

        # async 서브루틴 실행
        result = _run_async(func, **arguments)

        return jsonify({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "content": [
                    {
                        "type": "json",
                        "text": json.dumps(
                            result.model_dump() if hasattr(result, "model_dump") else result,
                            ensure_ascii=False
                        )
                    }
                ]
            }
        })

    except Exception as e:
        print("❌ KRW MCP HTTP Gateway 에러:", e)
        traceback.print_exc()
        return jsonify({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {
                "code": -32000,
                "message": str(e),
            }
        }), 500


# ─────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "tools": list(TOOLS.keys())
    })


# ─────────────────────────────────────────────
# 서버 시작
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("🚀 KRW Full Reserve MCP HTTP Gateway 시작")
    print("   - URL: http://0.0.0.0:5400/mcp")
    print("   - Tools:", ", ".join(TOOLS.keys()))
    print("=" * 60)
    app.run(host="0.0.0.0", port=5400, debug=True)
