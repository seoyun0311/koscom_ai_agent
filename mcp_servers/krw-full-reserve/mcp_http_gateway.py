# krw-full-reserve/mcp_http_gateway.py
"""
KRW Full Reserve MCP HTTP Gateway

web_chat_app.py 에서 KRW_RESERVE_MCP = "http://localhost:5400/mcp"
로 호출하는 JSON-RPC 형식을 받아서,
내부의 KRWS 툴(get_onchain_state, get_offchain_reserves 등)을 호출해주는 HTTP 서버.
"""
# krw-full-reserve/mcp_http_gateway.py

from __future__ import annotations

import asyncio
import json
import traceback
from typing import Dict, Any

from flask import Flask, request, jsonify

# ─────────────────────────────────────────────
# KRW fullreserve 툴 함수들 임포트
# ─────────────────────────────────────────────
from app_mcp.tools.onchain import get_onchain_state
from app_mcp.tools.offchain import get_offchain_reserves
from app_mcp.tools.coverage import check_coverage
from app_mcp.tools.report import get_risk_report
from app_mcp.tools.history import get_full_reserve_history  # ✅ 추가

app = Flask(__name__)

# 사용할 툴 매핑 (MCP tool name → Python 함수)
TOOLS: Dict[str, Any] = {
    "get_onchain_state": get_onchain_state,
    "get_offchain_reserves": get_offchain_reserves,
    "check_coverage": check_coverage,
    "get_risk_report": get_risk_report,
    "get_full_reserve_history": get_full_reserve_history,  # ✅ 추가
}



def _run_async(func, **kwargs):
    """
    async 함수면 asyncio.run으로 실행하고,
    sync 함수면 바로 실행하는 헬퍼.
    """
    if asyncio.iscoroutinefunction(func):
        return asyncio.run(func(**kwargs))
    else:
        return func(**kwargs)


@app.route("/mcp", methods=["POST"])
def mcp_call():
    """
    web_chat_app.call_krw_reserve_mcp 에서 보내는 JSON-RPC 형식:

    {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "get_offchain_reserves",
            "arguments": { ... }
        },
        "id": 1
    }

    이걸 파싱해서 TOOLS[name](**arguments)를 호출하고,
    다시 JSON-RPC 형식으로 돌려준다.
    """
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

        if not tool_name:
            return jsonify({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {
                    "code": -32602,
                    "message": "Missing tool name"
                }
            }), 400

        func = TOOLS.get(tool_name)
        if not func:
            return jsonify({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {
                    "code": -32601,
                    "message": f"Unknown tool: {tool_name}"
                }
            }), 400

        # 🔧 실제 호출 내용 로그
        print(f"🔧 KRW MCP 호출: {tool_name}({arguments})")

        # 🩹 get_risk_report는 format 인자를 정의하지 않았으므로 방어적으로 제거
        if tool_name == "get_risk_report" and "format" in arguments:
            arguments.pop("format", None)

        # 실제 툴 실행
        result = _run_async(func, **arguments)

        # web_chat_app.call_krw_reserve_mcp 에서 기대하는 MCP 응답 형식:
        # data["result"]["content"][0]["text"] 에 JSON 문자열이 들어가 있음
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
            "id": None,
            "error": {
                "code": -32000,
                "message": str(e),
            }
        }), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "tools": list(TOOLS.keys())
    })


if __name__ == "__main__":
    print("=" * 60)
    print("🚀 KRW Full Reserve MCP HTTP Gateway 시작")
    print("   - URL: http://0.0.0.0:5400/mcp")
    print("   - Tools:", ", ".join(TOOLS.keys()))
    print("=" * 60)
    app.run(host="0.0.0.0", port=5400, debug=True)
