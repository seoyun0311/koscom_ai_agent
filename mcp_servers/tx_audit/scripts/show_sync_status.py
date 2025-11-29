"""
Show sync status: chain head, local cursor, and lag.

Usage:
  python -m scripts.show_sync_status            # default source 'etherscan_usdt'
  python -m scripts.show_sync_status --source etherscan_usdt
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from typing import Tuple

import requests

from core.config.settings import settings


def get_chain_head() -> int:
    # Prefer Etherscan V2 endpoint
    url_v2 = (
        "https://api.etherscan.io/v2/api"
        f"?chainid=1&module=proxy&action=eth_blockNumber&apikey={settings.ETHERSCAN_API_KEY}"
    )
    r = requests.get(url_v2, timeout=20)
    r.raise_for_status()
    data = r.json()
    res = data.get("result")
    if isinstance(res, str):
        res_str = res.strip()
        if res_str.startswith("0x"):
            return int(res_str, 16)
        # Some gateways may return a decimal string
        return int(res_str)
    # Fallback: try legacy field formats if present
    if "jsonrpc" in data and "result" in data:
        return int(str(data["result"]).strip(), 16)
    raise ValueError(f"unexpected response: {data}")


def get_cursor(db_path: str, source: str) -> int | None:
    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        row = cur.execute(
            "select last_block from sync_state where source=?", (source,)
        ).fetchone()
        return row[0] if row else None
    finally:
        con.close()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="etherscan_usdt")
    args = ap.parse_args(argv)

    try:
        head = get_chain_head()
    except Exception as e:
        print({"error": f"head_fetch_failed: {e}"})
        return 2

    last = get_cursor(str(settings.DB_PATH), args.source)
    if last is None:
        print({"head": head, "cursor": None, "lag": None, "source": args.source})
        return 0

    print({"head": head, "cursor": last, "lag": head - int(last), "source": args.source})
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
