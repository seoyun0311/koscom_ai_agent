"""
Quick Etherscan connectivity check.

Runs a minimal request against Etherscan V2 "tokentx" for the USDT contract
to confirm API key, network access, and JSON parsing are OK.

Usage:
  python -m scripts.check_etherscan
"""

from __future__ import annotations

import sys
import json
from typing import Any

import requests

from core.config.settings import settings


def check_etherscan() -> int:
    url = (
        "https://api.etherscan.io/v2/api"
        f"?chainid=1"
        f"&module=account"
        f"&action=tokentx"
        f"&contractaddress={settings.USDT_CONTRACT}"
        f"&page=1&offset=1"
        f"&sort=desc"
        f"&apikey={settings.ETHERSCAN_API_KEY}"
    )

    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"[FAIL] HTTP error: {e}")
        return 2

    try:
        data: dict[str, Any] = resp.json()
    except Exception as e:
        print(f"[FAIL] Invalid JSON: {e}")
        return 3

    status = data.get("status")
    message = data.get("message")
    result = data.get("result", [])

    if status == "1" and isinstance(result, list) and result:
        tx = result[0]
        tx_hash = tx.get("hash")
        block = tx.get("blockNumber")
        print("[OK] Etherscan reachable. Latest sample:")
        print(json.dumps({"tx_hash": tx_hash, "blockNumber": block}, ensure_ascii=False))
        return 0

    print("[WARN] Etherscan responded but no transactions found or non-success status.")
    print(json.dumps({"status": status, "message": message}, ensure_ascii=False))
    return 1


if __name__ == "__main__":
    sys.exit(check_etherscan())

