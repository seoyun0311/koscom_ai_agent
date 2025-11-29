import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# Load project-level .env (repo root)
ROOT_DIR = Path(__file__).resolve().parents[4]
ENV_PATH = ROOT_DIR / ".env"
load_dotenv(ENV_PATH)

INFLUX_URL = os.getenv("INFLUX_URL")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN")
INFLUX_ORG = os.getenv("INFLUX_ORG", "dancom")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "my-bucket")

_client = None
_write_api = None

if INFLUX_URL and INFLUX_TOKEN:
    _client = InfluxDBClient(
        url=INFLUX_URL,
        token=INFLUX_TOKEN,
        org=INFLUX_ORG,
    )
    # Use synchronous mode to avoid atexit warnings in short scripts
    _write_api = _client.write_api(write_options=SYNCHRONOUS)
else:
    print("InfluxDB env vars not set; running in no-op mode.")


def write_bank_reserve(bank_name: str, balance: float, currency: str = "KRW") -> None:
    if not _write_api:
        print("InfluxDB not connected - skipping bank_reserves write")
        return

    point = (
        Point("bank_reserves")
        .tag("bank_name", bank_name)
        .tag("currency", currency)
        .field("balance", float(balance))
    )

    _write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)


def write_audit_event(event) -> None:
    """
    Persist a single AuditEvent row to InfluxDB. Safe to call even when
    Influx is not configured; it will no-op and log to stdout.
    """
    if not _write_api:
        print("InfluxDB not connected - skipping audit_events write")
        return

    try:
        point = (
            Point("audit_events")
            .tag("from", event.from_address or "")
            .tag("to", event.to_address or "")
            .tag("contract", event.contract_address or "")
            .field("amount", float(event.amount or 0))
            .field("block_number", int(event.block_number or 0))
            .field("tx_hash", event.tx_hash or "")
            .time(event.timestamp or datetime.utcnow())
        )
        _write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
    except Exception as exc:
        print(f"InfluxDB write_audit_event failed: {exc}")
