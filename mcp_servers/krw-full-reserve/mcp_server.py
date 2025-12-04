# krw-full-reserve/mcp_http_gateway.py
"""
KRW Full Reserve MCP HTTP Gateway

web_chat_app.py 에서 KRW_RESERVE_MCP = "http://localhost:5400/mcp"
로 호출하는 JSON-RPC 형식을 받아서,
내부의 KRWS 툴(get_onchain_state, get_offchain_reserves 등)을 호출해주는 HTTP 서버.
"""

from __future__ import annotations

import asyncio
import json
import traceback
from typing import Dict, Any
from dateutil.parser import isoparse

import threading
from flask import Flask, request, jsonify

# ─────────────────────────────────────────────
# KRW fullreserve 툴 함수들 임포트
# (함수 이름이 다르면 각 파일 열어서 실제 이름에 맞춰 수정하면 됨)
# ─────────────────────────────────────────────
from app_mcp.tools.onchain import get_onchain_state
from app_mcp.tools.offchain import get_offchain_reserves
from app_mcp.tools.coverage import check_coverage
from app_mcp.tools.report import get_risk_report
from app_mcp.tools.history import get_full_reserve_history  # 히스토리 툴

# ─────────────────────────────────────────────
# Flask 앱 생성
# ─────────────────────────────────────────────
app = Flask(__name__)

# ─────────────────────────────────────────────
# 사용할 툴 매핑 (MCP tool name → Python 함수)
# ─────────────────────────────────────────────
TOOLS: Dict[str, Any] = {
    "get_onchain_state": get_onchain_state,
    "get_offchain_reserves": get_offchain_reserves,
    "check_coverage": check_coverage,
    "get_risk_report": get_risk_report,
    "get_full_reserve_history": get_full_reserve_history,
}

# ─────────────────────────────────────────────
# 전역 asyncio 이벤트 루프
#  - Flask 요청마다 asyncio.run() 쓰면 loop 충돌/블락 → 전역 loop + lock 사용
# ─────────────────────────────────────────────
_global_loop = asyncio.new_event_loop()
_loop_lock = threading.Lock()
asyncio.set_event_loop(_global_loop)


def _run_async(func, **kwargs):
    """
    async 함수면 전역 이벤트 루프에서 실행하고,
    sync 함수면 바로 실행하는 헬퍼.
    """
    if asyncio.iscoroutinefunction(func):
        # 하나의 loop에서 순차적으로 실행되도록 lock
        with _loop_lock:
            return _global_loop.run_until_complete(func(**kwargs))
    else:
        return func(**kwargs)


# ─────────────────────────────────────────────
# JSON-RPC 메인 엔드포인트
# ─────────────────────────────────────────────
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
        print("─────────────────────────────────────────────")
        print(f"🛰 KRW HTTP MCP 수신 payload: {payload}")

        method = payload.get("method")
        rpc_id = payload.get("id")
        params = payload.get("params") or {}

        # JSON-RPC method 검증
        if method != "tools/call":
            err = {
                "code": -32601,
                "message": f"Unsupported method: {method}"
            }
            print("❌ 잘못된 method:", err)
            return jsonify({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": err,
            }), 400

        tool_name = params.get("name")
        arguments = params.get("arguments") or {}

        if not tool_name:
            err = {
                "code": -32602,
                "message": "Missing tool name"
            }
            print("❌ tool_name 누락:", err)
            return jsonify({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": err,
            }), 400

        func = TOOLS.get(tool_name)
        if not func:
            err = {
                "code": -32601,
                "message": f"Unknown tool: {tool_name}"
            }
            print("❌ 알 수 없는 MCP 툴:", err)
            return jsonify({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": err,
            }), 400

        # ─────────────────────────────────────
        # 히스토리 툴: 날짜 문자열 → datetime 으로 변환
        # ─────────────────────────────────────
        if tool_name == "get_full_reserve_history":
            if "from_ts" in arguments and isinstance(arguments["from_ts"], str):
                try:
                    arguments["from_ts"] = isoparse(arguments["from_ts"])
                except Exception:
                    print("⚠ from_ts 파싱 실패, None 으로 처리")
                    arguments["from_ts"] = None

            if "to_ts" in arguments and isinstance(arguments["to_ts"], str):
                try:
                    arguments["to_ts"] = isoparse(arguments["to_ts"])
                except Exception:
                    print("⚠ to_ts 파싱 실패, None 으로 처리")
                    arguments["to_ts"] = None

        # 🩹 get_risk_report는 format 인자를 정의하지 않았으므로 방어적으로 제거
        if tool_name == "get_risk_report" and "format" in arguments:
            print("🩹 get_risk_report arguments에서 format 제거")
            arguments.pop("format", None)

        # 🔧 실제 호출 내용 로그
        print(f"🔧 KRW MCP 호출: {tool_name}({arguments})")

        # ─────────────────────────────────────
        # 실제 툴 실행
        # ─────────────────────────────────────
        try:
            result = _run_async(func, **arguments)
        except Exception as tool_err:
            # MCP 툴 내부에서 예외가 나면 JSON-RPC error 로 보내줌
            print("❌ MCP 툴 실행 중 예외 발생:")
            traceback.print_exc()

            return jsonify({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {
                    "code": -32001,
                    "message": f"Tool execution error in {tool_name}: {tool_err}",
                }
            }), 500

        # web_chat_app.call_krw_reserve_mcp 에서 기대하는 MCP 응답 형식:
        # data["result"]["content"][0]["text"] 에 JSON 문자열이 들어가 있음
        try:
            json_text = json.dumps(result, ensure_ascii=False)
        except TypeError:
            # result 안에 datetime 같은 직렬화 불가능한 타입이 있을 수 있으므로 방어
            print("⚠ result JSON 직렬화 실패, str(result)로 대체")
            json_text = json.dumps(str(result), ensure_ascii=False)

        response_body = {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "content": [
                    {
                        "type": "json",
                        "text": json_text,
                    }
                ]
            }
        }

        print("✅ MCP 응답 전송:", response_body)
        return jsonify(response_body)

    except Exception as e:
        # Gateway 레벨 예외 처리
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


# ─────────────────────────────────────────────
# Health check 엔드포인트
# ─────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "tools": list(TOOLS.keys())
    })


# ─────────────────────────────────────────────
# 메인 실행
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("🚀 KRW Full Reserve MCP HTTP Gateway 시작")
    print("   - URL: http://0.0.0.0:5400/mcp")
    print("   - Tools:", ", ".join(TOOLS.keys()))
    print("=" * 60)
    # debug=True 는 코드 핫리로드 때문에 프로세스 2개 뜨는 구조라
    # 이벤트 루프가 꼬일 수 있음 → 실제 운영에서는 debug=False 권장
    app.run(host="0.0.0.0", port=5400, debug=True)
