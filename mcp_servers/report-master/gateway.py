"""
K-WON Reports MCP HTTP Gateway (정통 MCP Server 버전)

- 5900 포트에서 MCP Tool Server처럼 동작
- ChatGPT / Claude MCP 클라이언트가 바로 연결 가능
- { "tool": "xxx", "params": {...} } 형식으로 요청
- 내부적으로 FastAPI 백엔드(8000)에 REST 호출
"""

import os
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import traceback

# .env 로드
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(ROOT_DIR, ".env")
load_dotenv(ENV_PATH)

# FastAPI MCP Backend (진짜 데이터/로직은 8000에서 실행됨)
MCP_BACKEND_BASE = os.getenv("MCP_BACKEND_BASE", "http://127.0.0.1:8000").rstrip("/")

app = Flask(__name__)

# -------------------------------
# Helper functions
# -------------------------------

def _proxy_get(path: str, params=None):
    url = f"{MCP_BACKEND_BASE}{path}"
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()

def _proxy_post(path: str, payload=None):
    url = f"{MCP_BACKEND_BASE}{path}"
    resp = requests.post(url, json=payload or {}, timeout=60)
    resp.raise_for_status()
    return resp.json()

# -------------------------------
# TOOL MAP (정통 MCP 스타일)
# -------------------------------

def tool_get_latest_report(params):
    return _proxy_get("/mcp/report/latest")

def tool_get_report(params):
    period = params.get("period")
    return _proxy_get(f"/mcp/report/{period}")

def tool_get_collateral_status(params):
    return _proxy_get("/mcp/collateral/status", params=params)

def tool_get_risk_summary(params):
    return _proxy_get("/mcp/risk/summary", params=params)

def tool_get_compliance_alerts(params):
    return _proxy_get("/mcp/alerts", params=params)

def tool_rerun_monthly_report(params):
    return _proxy_post("/mcp/run_full", params)

def tool_get_human_review_tasks(params):
    return _proxy_get("/mcp/human_review/tasks")


TOOL_MAP = {
    "get_latest_report": tool_get_latest_report,
    "get_report": tool_get_report,
    "get_collateral_status": tool_get_collateral_status,
    "get_risk_summary": tool_get_risk_summary,
    "get_compliance_alerts": tool_get_compliance_alerts,
    "rerun_monthly_report": tool_rerun_monthly_report,
    "get_human_review_tasks": tool_get_human_review_tasks,
}

# -------------------------------
# MCP Root Endpoint
# -------------------------------

@app.route("/mcp", methods=["POST"])
def mcp_root():
    """
    정통 MCP Tool Server Endpoint
    요청 형식:
    {
      "tool": "get_latest_report",
      "params": {}
    }
    """
    try:
        data = request.json or {}
        tool_name = data.get("tool")
        params = data.get("params", {})

        print(f"🔧 MCP Tool 요청: {tool_name} | params={params}")

        if tool_name not in TOOL_MAP:
            return jsonify({
                "success": False,
                "error": f"Unknown tool: {tool_name}"
            }), 404

        result = TOOL_MAP[tool_name](params)

        return jsonify({
            "success": True,
            "result": result
        })

    except Exception as e:
        print(f"❌ MCP Error: {e}")
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc()
        }), 500


# -------------------------------
# Health Check
# -------------------------------

@app.route("/health", methods=["GET"])
def health():
    try:
        backend = requests.get(f"{MCP_BACKEND_BASE}/health", timeout=5).json()
        return jsonify({"status": "ok", "backend": backend})
    except:
        return jsonify({"status": "error"}), 500


# -------------------------------
# Run server
# -------------------------------

if __name__ == "__main__":
    print("=" * 70)
    print("🚀 K-WON Reports MCP TOOL SERVER (정통 MCP 모드)")
    print("=" * 70)
    print(f"🔗 Backend API: {MCP_BACKEND_BASE}")
    print(f"📡 MCP Endpoint: http://localhost:5900/mcp")
    print("=" * 70)

    app.run(host="0.0.0.0", port=5900, debug=True)