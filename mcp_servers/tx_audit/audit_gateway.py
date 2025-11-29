"""
Simple HTTP gateway for koscom audit MCP tools.
"""

import asyncio
import traceback
from flask import Flask, request, jsonify

from servers.mcp_koscom import (
    health as audit_health,
    sync_state as audit_sync_state,
    events_recent,
    event_detail,
    collect_once,
    backfill_hashes,
    make_batch,
    batches_recent,
    event_proof,
    anchor_batch,
    anchor_status,
    batch_events,
    events_search,
    proof_pack,
    proof_pack_batch,
)

app = Flask(__name__)


def run_async(coro):
    """Run async functions from sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# Tool registry
TOOL_MAP = {
    # koscom_audit basic
    "health": lambda params: audit_health(),
    "sync_state": lambda params: audit_sync_state(),

    # events
    "events_recent": lambda params: events_recent(**params),
    "event_detail": lambda params: event_detail(**params),
    "events_search": lambda params: events_search(**params),

    # collect / backfill
    "collect_once": lambda params: collect_once(**params),
    "backfill_hashes": lambda params: backfill_hashes(**params),

    # merkle / batches
    "make_batch": lambda params: make_batch(**params),
    "batches_recent": lambda params: batches_recent(**params),
    "batch_events": lambda params: batch_events(**params),
    "event_proof": lambda params: event_proof(**params),

    # anchoring
    "anchor_batch": lambda params: anchor_batch(**params),
    "anchor_status": lambda params: anchor_status(**params),

    # proof packs
    "proof_pack": lambda params: proof_pack(**params),
    "proof_pack_batch": lambda params: proof_pack_batch(**params),
}


@app.route("/mcp", methods=["POST"])
def mcp_gateway():
    """
    MCP Tool HTTP Gateway
    Request: {"tool": "tool_name", "params": {...}}
    Response: {"success": true, "result": {...}} or {"success": false, "error": "..."}
    """
    try:
        data = request.json or {}
        tool_name = data.get("tool")
        params = data.get("params", {}) or {}

        print(f"[MCP gateway] call: {tool_name}({params})")

        if tool_name not in TOOL_MAP:
            return jsonify({"success": False, "error": f"Unknown tool: {tool_name}"}), 404

        result = TOOL_MAP[tool_name](params)
        print(f"[MCP gateway] success: {tool_name}")

        return jsonify({"success": True, "result": result})

    except Exception as e:
        print(f"[MCP gateway] error: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@app.route("/health", methods=["GET"])
def http_health():
    """Simple health check."""
    return jsonify({"status": "healthy", "tools": list(TOOL_MAP.keys())})


if __name__ == "__main__":
    print("=" * 70)
    print("tx_AUDIT MCP HTTP Gateway")
    print("=" * 70)
    print(" Endpoint: http://localhost:5200/mcp")
    print(" Available Tools:")
    for tool in TOOL_MAP.keys():
        print(f"   - {tool}")
    print("=" * 70)

    app.run(host="0.0.0.0", port=5200, debug=True)
