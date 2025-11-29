"""Incremental transaction collector for dancom sFIAT or Etherscan USDT."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime

import requests
from web3 import Web3

from core.config.settings import settings
from core.db.database import (
    AuditEvent,
    get_last_block,
    get_session,
    set_last_block,
)
from core.db.influx import write_audit_event
from core.logging.logger import get_logger
from core.utils.hash_utils import details_hash_from_tx


logger = get_logger(__name__)


USE_LOCAL_SFIAT = getattr(settings, "USE_LOCAL_SFIAT", False)
LOCAL_API_BASE = getattr(settings, "LOCAL_API_BASE", "http://127.0.0.1:4000/api")
LOCAL_TOKEN = getattr(settings, "LOCAL_TOKEN", "")
LOCAL_ADDRESS_FILTER = getattr(settings, "LOCAL_ADDRESS_FILTER", None) or ""

ETHERSCAN_API_KEY = getattr(settings, "ETHERSCAN_API_KEY", "")
ETHERSCAN_BASE_URL = getattr(settings, "ETHERSCAN_BASE_URL", "https://api.etherscan.io/api")
USDT_CONTRACT = getattr(settings, "USDT_CONTRACT", "")

SOURCE_NAME = "local_sfiat" if USE_LOCAL_SFIAT else "etherscan_usdt"
TRANSFER_SELECTOR = "0xa9059cbb"


def _decode_transfer_input(input_data: str) -> tuple[str | None, float | None]:
    """Return (recipient, amount) if the payload matches ERC-20 transfer."""
    try:
        if not input_data or not input_data.startswith(TRANSFER_SELECTOR):
            return None, None
        raw_to = "0x" + input_data[34:74]
        to_addr = Web3.to_checksum_address(raw_to)
        amount = int(input_data[74:], 16) / (10 ** 18)
        return to_addr, float(amount)
    except Exception:
        return None, None


def _get_chain_head() -> int | None:
    """Fetch the current head block number from Etherscan V2."""
    if USE_LOCAL_SFIAT:
        return None
    try:
        url = (
            "https://api.etherscan.io/v2/api"
            f"?chainid=1&module=proxy&action=eth_blockNumber&apikey={ETHERSCAN_API_KEY}"
        )
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        result = resp.json().get("result")
        if isinstance(result, str) and result.startswith("0x"):
            return int(result, 16)
        if isinstance(result, str):
            return int(result)
    except Exception:
        return None
    return None


def fetch_transactions_incremental(start_block: int, page: int, offset: int):
    """Return transaction rows for the given block/page window."""
    if USE_LOCAL_SFIAT:
        if not LOCAL_TOKEN:
            logger.error("LOCAL_TOKEN is not configured")
            return []
        url = (
            f"{LOCAL_API_BASE}?module=account&action=tokentx"
            f"&contractaddress={LOCAL_TOKEN}"
            f"&startblock={start_block}"
            f"&endblock=99999999"
            f"&sort=asc"
        )
        if LOCAL_ADDRESS_FILTER:
            url += f"&address={LOCAL_ADDRESS_FILTER}"
    else:
        url = (
            f"{ETHERSCAN_BASE_URL}?"
            f"module=account&action=tokentx&contractaddress={USDT_CONTRACT}"
            f"&startblock={start_block}"
            f"&page={page}&offset={offset}&sort=asc&apikey={ETHERSCAN_API_KEY}"
        )

    try:
        resp = requests.get(url, timeout=20)
        data = resp.json()
    except Exception as exc:
        logger.error(f"Failed to fetch data source: {exc}")
        return []

    if data.get("status") != "1":
        logger.debug(json.dumps(data, indent=2))
        return []
    return data.get("result", [])


def store_events(events: list[dict]) -> tuple[int | None, int, int]:
    """Persist events into the database and return stats."""
    session = get_session()
    inserted = 0
    skipped = 0
    max_block = None
    inserted_events: list[AuditEvent] = []

    for tx in events:
        try:
            decoded_to, decoded_amount = _decode_transfer_input(tx.get("input", ""))
            to_address = decoded_to or tx.get("to")
            amount = decoded_amount or float(tx["value"]) / (10 ** int(tx["tokenDecimal"]))

            event = AuditEvent(
                event_id=tx["hash"],
                timestamp=datetime.fromtimestamp(int(tx["timeStamp"]), tz=UTC),
                block_number=int(tx["blockNumber"]),
                from_address=tx.get("from"),
                to_address=to_address,
                amount=amount,
                tx_hash=tx["hash"],
                contract_address=tx.get("contractAddress"),
                details_hash=details_hash_from_tx(tx),
                raw_json=json.dumps(tx),
                created_at=datetime.now(UTC),
            )

            existing = session.query(AuditEvent).filter_by(event_id=event.event_id).first()
            if existing:
                skipped += 1
                continue

            session.add(event)
            inserted += 1
            inserted_events.append(event)
            if max_block is None or event.block_number > max_block:
                max_block = event.block_number
        except Exception as exc:
            session.rollback()
            logger.error(f"DB insert failed ({tx.get('hash')}): {exc}")

    session.commit()
    # After commit, mirror newly inserted rows to InfluxDB (best-effort)
    for ev in inserted_events:
        try:
            write_audit_event(ev)
        except Exception as exc:
            logger.error(f"Influx write failed ({ev.event_id}): {exc}")

    session.close()
    logger.debug(f"stored={inserted} skipped={skipped}")
    return max_block, inserted, skipped


def collect_usdt_transactions_once(
    max_pages: int | None = None,
    max_seconds: float | None = None,
):
    """Run a single incremental collection cycle."""
    logger.info(f"=== Collector start (source={SOURCE_NAME}) ===")

    page_limit = max_pages if max_pages is not None else getattr(settings, "COLLECT_MAX_PAGES", None)
    time_limit = (
        max_seconds
        if max_seconds is not None
        else getattr(settings, "COLLECT_MAX_SECONDS", None)
    )

    last = get_last_block(SOURCE_NAME)
    if last is None:
        session = get_session()
        try:
            row = session.query(AuditEvent).order_by(AuditEvent.block_number.desc()).first()
            last = int(row.block_number) if row and row.block_number is not None else 0
            set_last_block(SOURCE_NAME, last)
            logger.info(f"Initial cursor: {last}")
        finally:
            session.close()

    page = 1
    total_rows = 0
    total_inserted = 0
    total_skipped = 0
    offset = getattr(settings, "ETHERSCAN_OFFSET", 500)
    rate_sleep = getattr(settings, "ETHERSCAN_RATE_SLEEP", 0.05)
    max_block_in_batch = last
    started_at = time.time()

    while True:
        rows = fetch_transactions_incremental(start_block=last + 1, page=page, offset=offset)
        if not rows:
            if not USE_LOCAL_SFIAT and page == 1:
                head = _get_chain_head()
                if head is not None:
                    safe_head = max(head - 12, last)
                    if safe_head > last:
                        set_last_block(SOURCE_NAME, safe_head)
            break

        mb, inserted, skipped = store_events(rows)
        if mb is not None and mb > max_block_in_batch:
            max_block_in_batch = mb
            safe_cursor = max(last, max_block_in_batch - 1)
            set_last_block(SOURCE_NAME, safe_cursor)

        total_rows += len(rows)
        total_inserted += inserted
        total_skipped += skipped
        page += 1

        if page_limit is not None and page - 1 >= page_limit:
            logger.info(f"Page limit reached: {page_limit}")
            break

        if time_limit is not None and (time.time() - started_at) >= time_limit:
            logger.info(f"Time limit reached: {time_limit}s")
            break

        time.sleep(rate_sleep)

    if max_block_in_batch > last:
        set_last_block(SOURCE_NAME, max_block_in_batch)
        logger.info(f"Cursor moved: {last} -> {max_block_in_batch}")

    if total_inserted == 0:
        logger.info("No new transactions")
    logger.info(
        "=== Collector done (stored %s, skipped %s, pages %s) ===",
        total_inserted,
        total_skipped,
        page - 1,
    )


def run_poller():
    """Continuous poller."""
    interval = getattr(settings, "POLL_INTERVAL_SEC", 15)
    while True:
        try:
            collect_usdt_transactions_once()
        except Exception as exc:
            logger.error(f"Recurring collection error: {exc}")
        time.sleep(interval)


def run_until_synced(target_lag: int = 1, max_rounds: int | None = None):
    """Repeat collection until we are close to the head (Etherscan mode)."""
    rounds = 0
    while True:
        collect_usdt_transactions_once()
        head = _get_chain_head() or 0
        last = get_last_block(SOURCE_NAME) or 0
        lag = head - last if head and last else None
        if lag is not None:
            logger.info(f"Sync status: head={head} cursor={last} lag={lag}")
            if lag <= target_lag:
                logger.info("Target lag reached, exiting.")
                return
        if max_rounds is not None and rounds >= max_rounds:
            logger.info("Max rounds reached, exiting.")
            return
        rounds += 1
        time.sleep(getattr(settings, "POLL_INTERVAL_SEC", 15))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run a single cycle")
    parser.add_argument(
        "--until-synced",
        action="store_true",
        help="Loop until head - cursor <= lag",
    )
    parser.add_argument("--lag", type=int, default=1, help="Maximum allowed lag")
    args = parser.parse_args()

    if args.once:
        collect_usdt_transactions_once()
    elif args.until_synced:
        run_until_synced(target_lag=args.lag)
    else:
        run_poller()


if __name__ == "__main__":
    main()
