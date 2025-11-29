"""Minimal MCP server for koscom audit demo.
Provides tools to inspect sync status and recent USDT transfer events,
and to trigger batching/anchoring and proof-pack generation.
Run (STDIO): python -m servers.mcp_koscom
Register in Claude Desktop config with command + args above.
"""
from __future__ import annotations
import json
import sqlite3
import sys
from pathlib import Path
import os
import hashlib
import zipfile
from datetime import datetime, timezone
from typing import Optional
try:
    from zoneinfo import ZoneInfo  # py3.9+
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore
from typing import Any, List, Dict
import requests
from mcp.server.fastmcp import FastMCP
from sqlalchemy import func

# Ensure repo root is importable even if PYTHONPATH is not set by the host
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.config.settings import settings
from core.db.database import get_session, AuditEvent, get_last_block, EventProof, MerkleBatch, AnchorRecord
from apps.api.collector import collect_usdt_transactions_once
from apps.api.merkle import create_merkle_batch
from core.utils.hash_utils import details_hash_from_tx


SOURCE_REMOTE = "etherscan_usdt"
SOURCE_LOCAL = "local_sfiat"
USE_LOCAL_SFIAT = bool(getattr(settings, "USE_LOCAL_SFIAT", False))
LOCAL_TOKEN = (getattr(settings, "LOCAL_TOKEN", "") or "").lower()
SOURCE_NAME = SOURCE_LOCAL if USE_LOCAL_SFIAT else SOURCE_REMOTE
CONTRACT_FILTER = LOCAL_TOKEN if (USE_LOCAL_SFIAT and LOCAL_TOKEN) else None

app = FastMCP("koscom")

def _format_timestamp(dt: datetime, tz: Optional[str]) -> tuple[str, str]:
    """Return (timestamp_tz, timestamp_utc) ISO8601 strings.
    If dt is naive, assume UTC.
    tz: 'UTC' | 'local' | IANA name (e.g., 'Asia/Seoul')
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_utc = dt.astimezone(timezone.utc)
    if not tz or tz.upper() == "UTC":
        return dt_utc.isoformat(), dt_utc.isoformat()
    if tz.lower() == "local":
        dt_tz = dt_utc.astimezone()  # system local tz
        return dt_tz.isoformat(), dt_utc.isoformat()
    # Named timezone
    if ZoneInfo is not None:
        try:
            dt_tz = dt_utc.astimezone(ZoneInfo(tz))
            return dt_tz.isoformat(), dt_utc.isoformat()
        except Exception:
            pass
    # Fallback
    return dt_utc.isoformat(), dt_utc.isoformat()

def _dictify_event_row(row: Any, tz: Optional[str] = None, include_raw: bool = False) -> Dict[str, Any]:
    # row is SQLAlchemy model instance (via session) or tuple (via sqlite3)
    if isinstance(row, AuditEvent):
        # Ensure ISO8601 with timezone. Treat naive as UTC.
        if isinstance(row.timestamp, datetime):
            ts, ts_utc = _format_timestamp(row.timestamp, tz)
        else:
            # If stored as string, keep as-is and provide utc echo
            ts = str(row.timestamp)
            ts_utc = ts
        if isinstance(getattr(row, "created_at", None), datetime):
            created_ts, created_utc = _format_timestamp(row.created_at, tz)
        else:
            created_ts = created_utc = None
        out = {
            "event_id": row.event_id,
            "block_number": row.block_number,
            "timestamp": ts,
            "timestamp_utc": ts_utc,
            "created_at": created_ts,
            "created_at_utc": created_utc,
            "from": row.from_address,
            "to": row.to_address,
            "amount": row.amount,
            "tx_hash": row.tx_hash,
            "contract": row.contract_address,
        }
        if include_raw:
            try:
                out["raw_json"] = json.loads(row.raw_json) if row.raw_json else None
            except Exception:
                out["raw_json"] = row.raw_json
        return out
    # tuple fallback (not used in current code path)
    return {
        "event_id": row[0],
        "block_number": row[1],
        "timestamp": row[2],
        "from": row[3],
        "to": row[4],
        "amount": row[5],
        "tx_hash": row[6],
        "contract": row[7],
    }

def _latest_db_block() -> int | None:
    session = get_session()
    try:
        row = (
            session.query(AuditEvent.block_number)
            .order_by(AuditEvent.block_number.desc())
            .first()
        )
        if not row:
            return None
        value = getattr(row, "block_number", None)
        if value is None:
            try:
                value = row[0]
            except Exception:
                value = None
        return value
    finally:
        session.close()

def _apply_contract_filter(query):
    if CONTRACT_FILTER:
        return query.filter(func.lower(AuditEvent.contract_address) == CONTRACT_FILTER)
    return query

def _get_chain_head() -> int | None:
    if USE_LOCAL_SFIAT:
        return _latest_db_block()
    try:
        url = (
            "https://api.etherscan.io/v2/api"
            f"?chainid=1&module=proxy&action=eth_blockNumber&apikey={settings.ETHERSCAN_API_KEY}"
        )
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        res = r.json().get("result")
        if isinstance(res, str) and res.startswith("0x"):
            return int(res, 16)
        if isinstance(res, str):
            return int(res)
    except Exception:
        return None
    return None

@app.tool()
def health() -> dict:
    """Return basic health info and DB path."""
    return {
        "status": "ok",
        "db": str(settings.DB_PATH),
        "network": settings.NETWORK,
        "source": SOURCE_NAME,
    }

@app.tool()
def sync_state() -> dict:
    """Return cursor last_block and chain head with lag."""
    head = _get_chain_head()
    last = get_last_block(SOURCE_NAME)
    return {
        "head": head,
        "cursor": last,
        "lag": (head - last) if (head is not None and last is not None) else None,
        "source": SOURCE_NAME,
    }

@app.tool()
def events_recent(limit: int = 50, tz: str = "UTC", include_raw: bool = False) -> List[dict]:
    """Return latest N events from DB (default 50).
    - tz: 'UTC' (default), 'local', or IANA timezone like 'Asia/Seoul'
    """
    session = get_session()
    try:
        # Order by most recent block first; fall back to id desc for stable order
        q = session.query(AuditEvent)
        q = _apply_contract_filter(q)
        q = (
            q.order_by(AuditEvent.block_number.desc(), AuditEvent.id.desc())
            .limit(int(limit))
        )
        rows = list(q)
        return [_dictify_event_row(r, tz, include_raw=include_raw) for r in rows]
    finally:
        session.close()

@app.tool()
def event_detail(tx_hash: str, tz: str = "UTC", include_raw: bool = True) -> dict | None:
    """Return single event by tx hash (event_id)."""
    session = get_session()
    try:
        row = (
            session.query(AuditEvent)
            .filter(AuditEvent.event_id == tx_hash)
            .first()
        )
        return _dictify_event_row(row, tz, include_raw=include_raw) if row else None
    finally:
        session.close()

@app.tool()
def collect_once(max_pages: int = 3, max_seconds: float = 25.0) -> dict:
    """Trigger one incremental collection run with safe limits to avoid timeouts.
    - max_pages: stop after processing this many API pages (default 3)
    - max_seconds: soft time limit in seconds (default 25s)
    Returns updated sync_state.
    """
    collect_usdt_transactions_once(max_pages=max_pages, max_seconds=max_seconds)
    return sync_state()

@app.tool()
def backfill_hashes(limit: int = 1000) -> dict:
    """Compute details_hash for events missing it using raw_json (up to limit)."""
    session = get_session()
    updated = 0
    try:
        rows = (
            session.query(AuditEvent)
            .filter((AuditEvent.details_hash == None) | (AuditEvent.details_hash == ""))
            .order_by(AuditEvent.id.asc())
            .limit(int(limit))
            .all()
        )
        for ev in rows:
            try:
                if ev.raw_json:
                    tx = json.loads(ev.raw_json)
                    ev.details_hash = details_hash_from_tx(tx)
                    updated += 1
            except Exception:
                pass
        session.commit()
        return {"updated": updated}
    finally:
        session.close()

@app.tool()
def make_batch(limit: int = 1000, mode: str = "oldest", min_block: int | None = None) -> dict | None:
    """Create a Merkle batch from unbatched events (up to limit).
    - mode: 'oldest' (default) or 'latest' (pick newest first)
    - min_block: only include events with block_number >= min_block
    """
    return create_merkle_batch(limit=limit, mode=mode, min_block=min_block)

@app.tool()
def batches_recent(limit: int = 10) -> List[dict]:
    session = get_session()
    try:
        rows = (
            session.query(MerkleBatch)
            .order_by(MerkleBatch.id.desc())
            .limit(int(limit))
            .all()
        )
        return [
            {
                "batch_id": r.batch_id,
                "merkle_root": r.merkle_root,
                "leaf_count": r.leaf_count,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    finally:
        session.close()

@app.tool()
def event_proof(tx_hash: str, tz: str = "UTC") -> dict | None:
    """Return event detail with Merkle proof and batch meta."""
    session = get_session()
    try:
        ev = (
            session.query(AuditEvent)
            .filter(AuditEvent.event_id == tx_hash)
            .first()
        )
        if not ev:
            return None
        proof = session.query(EventProof).filter(EventProof.event_id == tx_hash).first()
        out = _dictify_event_row(ev, tz)
        if proof:
            out["batch_id"] = proof.batch_id
            out["leaf_index"] = proof.leaf_index
            try:
                out["proof"] = json.loads(proof.proof_json)
            except Exception:
                out["proof"] = proof.proof_json
            mb = (
                session.query(MerkleBatch)
                .filter(MerkleBatch.batch_id == proof.batch_id)
                .first()
            )
            if mb:
                out["merkle_root"] = mb.merkle_root
        return out
    finally:
        session.close()

@app.tool()
def anchor_batch(batch_id: str, chain: str = "mock") -> dict:
    """Mock-anchor a Merkle batch. Upsert into anchor_records with anchored status.
    Returns the recorded anchor metadata along with the batch merkle_root.
    """
    session = get_session()
    try:
        mb = session.query(MerkleBatch).filter(MerkleBatch.batch_id == batch_id).first()
        if not mb:
            return {"error": f"batch_id not found: {batch_id}"}
        ar = (
            session.query(AnchorRecord)
            .filter(AnchorRecord.batch_id == batch_id, AnchorRecord.chain == chain)
            .first()
        )
        now = datetime.utcnow()
        if ar is None:
            ar = AnchorRecord(
                batch_id=batch_id,
                chain=chain,
                tx_hash=f"mock-{batch_id}",
                status="anchored",
                anchored_at=now,
            )
            session.add(ar)
        else:
            ar.status = "anchored"
            if not ar.tx_hash:
                ar.tx_hash = f"mock-{batch_id}"
            # 멱등성: 이미 anchored_at이 있으면 갱신하지 않음
            if not ar.anchored_at:
                ar.anchored_at = now
        session.commit()
        return {
            "batch_id": batch_id,
            "chain": chain,
            "status": ar.status,
            "tx_hash": ar.tx_hash,
            "anchored_at": ar.anchored_at.isoformat() if ar.anchored_at else None,
            "merkle_root": mb.merkle_root,
            "leaf_count": mb.leaf_count,
        }
    finally:
        session.close()

@app.tool()
def anchor_status(batch_id: str, chain: str = "mock") -> dict:
    """Return anchor status metadata for a batch (mock or real)."""
    session = get_session()
    try:
        mb = session.query(MerkleBatch).filter(MerkleBatch.batch_id == batch_id).first()
        ar = (
            session.query(AnchorRecord)
            .filter(AnchorRecord.batch_id == batch_id, AnchorRecord.chain == chain)
            .first()
        )
        if not mb and not ar:
            return {"error": f"batch_id not found: {batch_id}"}
        out = {
            "batch_id": batch_id,
            "chain": chain,
            "merkle_root": mb and mb.merkle_root,
            "leaf_count": mb and mb.leaf_count,
        }
        if ar:
            out.update(
                {
                    "status": ar.status,
                    "tx_hash": ar.tx_hash,
                    "block_number": ar.block_number,
                    "anchored_at": ar.anchored_at.isoformat() if ar.anchored_at else None,
                }
            )
        else:
            out.update({"status": "not_anchored"})
        return out
    finally:
        session.close()

@app.tool()
def batch_events(batch_id: str, limit: int = 100, tz: str = "UTC") -> List[dict]:
    """Return up to N events included in a given batch ordered by leaf_index.
    Fields include leaf_index along with standard event columns.
    """
    session = get_session()
    try:
        q = (
            session.query(AuditEvent, EventProof.leaf_index)
            .join(EventProof, EventProof.event_id == AuditEvent.event_id)
            .filter(EventProof.batch_id == batch_id)
        )
        q = _apply_contract_filter(q)
        rows = (
            q.order_by(EventProof.leaf_index.asc())
            .limit(int(limit))
            .all()
        )
        out: List[dict] = []
        for ev, leaf_index in rows:
            item = _dictify_event_row(ev, tz)
            item["leaf_index"] = leaf_index
            out.append(item)
        return out
    finally:
        session.close()

@app.tool()
def events_search(
    address: str | None = None,
    role: str = "any",  # any|from|to
    tx_hash: str | None = None,
    tx_prefix_ok: bool = True,
    min_amount: float | None = None,
    max_amount: float | None = None,
    block_min: int | None = None,
    block_max: int | None = None,
    start_iso: str | None = None,
    end_iso: str | None = None,
    limit: int = 50,
    tz: str = "UTC",
    include_raw: bool = False,
) -> List[dict]:
    """Flexible event search with common filters.
    - address: filter by from/to (see role)
    - role: any|from|to
    - tx_hash: exact or prefix (controlled by tx_prefix_ok)
    - amount/block/time ranges supported
    - start_iso/end_iso: ISO8601 timestamps (interpreted as UTC if naive)
    """
    session = get_session()
    try:
        q = _apply_contract_filter(session.query(AuditEvent))
        if tx_hash:
            if tx_prefix_ok and len(tx_hash) < 66:
                q = q.filter(AuditEvent.event_id.like(f"{tx_hash}%"))
            else:
                q = q.filter(AuditEvent.event_id == tx_hash)
        if address:
            addr = address.lower()
            if role == "from":
                q = q.filter(AuditEvent.from_address.ilike(addr))
            elif role == "to":
                q = q.filter(AuditEvent.to_address.ilike(addr))
            else:
                q = q.filter(
                    (AuditEvent.from_address.ilike(addr)) | (AuditEvent.to_address.ilike(addr))
                )
        if min_amount is not None:
            q = q.filter(AuditEvent.amount >= float(min_amount))
        if max_amount is not None:
            q = q.filter(AuditEvent.amount <= float(max_amount))
        if block_min is not None:
            q = q.filter(AuditEvent.block_number >= int(block_min))
        if block_max is not None:
            q = q.filter(AuditEvent.block_number <= int(block_max))
        # time range (best-effort; if timestamp is naive string in DB, this filter may be skipped)
        try:
            if start_iso:
                start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
                q = q.filter(AuditEvent.timestamp >= start_dt)
            if end_iso:
                end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
                q = q.filter(AuditEvent.timestamp <= end_dt)
        except Exception:
            pass
        q = q.order_by(AuditEvent.block_number.desc(), AuditEvent.id.desc()).limit(int(limit))
        rows = q.all()
        return [_dictify_event_row(r, tz, include_raw=include_raw) for r in rows]
    finally:
        session.close()

@app.tool()
def proof_pack(
    tx_hash: str,
    include_raw: bool = True,
    tz: str = "UTC",
    as_zip: bool = True,
) -> dict:
    """Create a self-contained proof package for an event.
    Includes event detail, merkle proof, batch meta, and anchor metadata.
    - Returns file path and summary if zipped, otherwise full JSON document.
    """
    session = get_session()
    try:
        ev = (
            session.query(AuditEvent)
            .filter(AuditEvent.event_id == tx_hash)
            .first()
        )
        if not ev:
            return {"error": f"event not found: {tx_hash}"}
        ev_dict = _dictify_event_row(ev, tz, include_raw=include_raw)
        proof = session.query(EventProof).filter(EventProof.event_id == tx_hash).first()
        proof_dict: dict | None = None
        batch_dict: dict | None = None
        anchors: List[dict] = []
        if proof:
            try:
                proof_dict = json.loads(proof.proof_json)
            except Exception:
                proof_dict = {"raw": proof.proof_json}
            mb = (
                session.query(MerkleBatch)
                .filter(MerkleBatch.batch_id == proof.batch_id)
                .first()
            )
            if mb:
                batch_dict = {
                    "batch_id": mb.batch_id,
                    "merkle_root": mb.merkle_root,
                    "leaf_count": mb.leaf_count,
                    "created_at": mb.created_at.isoformat() if mb.created_at else None,
                }
                # collect anchors for this batch (any chain)
                ars = (
                    session.query(AnchorRecord)
                    .filter(AnchorRecord.batch_id == mb.batch_id)
                    .all()
                )
                for ar in ars:
                    anchors.append(
                        {
                            "chain": ar.chain,
                            "status": ar.status,
                            "tx_hash": ar.tx_hash,
                            "block_number": ar.block_number,
                            "anchored_at": ar.anchored_at.isoformat() if ar.anchored_at else None,
                        }
                    )
        pkg = {
            "version": "1.0",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "event": ev_dict,
            "details_hash": getattr(ev, "details_hash", None),
            "proof": proof_dict,
            "batch": batch_dict,
            "anchors": anchors,
            "verification": {
                "instructions": "Recompute leaf hash from event details, fold proof path to the root, then compare with batch.merkle_root.",
                "leaf_source": "details_hash or canonical serialization of event fields",
            },
        }
        if not as_zip:
            return {"result": pkg}
        # write as zip under data/proof_packs
        out_dir = ROOT / "data" / "proof_packs"
        out_dir.mkdir(parents=True, exist_ok=True)
        zip_path = out_dir / f"{tx_hash}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("proof_pack.json", json.dumps(pkg, ensure_ascii=False, indent=2))
            if include_raw and isinstance(ev_dict.get("raw_json"), (dict, list)):
                zf.writestr("event_raw.json", json.dumps(ev_dict["raw_json"], ensure_ascii=False, indent=2))
            readme = (
                "This archive contains an integrity proof for a single event.\n"
                "Files:\n"
                "- proof_pack.json: All data needed for verification\n"
                "- event_raw.json: Original raw payload (if available)\n"
                "Verification summary: recompute leaf, apply proof to reach merkle_root, compare.\n"
            )
            zf.writestr("README.txt", readme)
        # compute sha256
        sha256 = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        return {
            "path": str(zip_path),
            "sha256": sha256,
            "bytes": zip_path.stat().st_size,
        }
    finally:
        session.close()


@app.tool()
def proof_pack_batch(
    address: str | None = None,
    role: str = "any",
    tx_hash: str | None = None,
    tx_prefix_ok: bool = True,
    min_amount: float | None = None,
    max_amount: float | None = None,
    block_min: int | None = None,
    block_max: int | None = None,
    start_iso: str | None = None,
    end_iso: str | None = None,
    limit: int = 200,
    tz: str = "UTC",
    include_raw: bool = False,
    include_proof: bool = True,
    include_anchor: bool = True,
    as_zip: bool = True,
) -> dict:
    """
    Create a proof package for multiple events matching the given filters.
    Bundles events (and optional proofs/anchors) into a single ZIP.
    Returns path/sha/bytes when zipped, otherwise raw JSON payload.
    """
    session = get_session()
    try:
        q = _apply_contract_filter(session.query(AuditEvent))
        if tx_hash:
            if tx_prefix_ok and len(tx_hash) < 66:
                q = q.filter(AuditEvent.event_id.like(f"{tx_hash}%"))
            else:
                q = q.filter(AuditEvent.event_id == tx_hash)
        if address:
            addr = address.lower()
            if role == "from":
                q = q.filter(AuditEvent.from_address.ilike(addr))
            elif role == "to":
                q = q.filter(AuditEvent.to_address.ilike(addr))
            else:
                q = q.filter(
                    (AuditEvent.from_address.ilike(addr)) | (AuditEvent.to_address.ilike(addr))
                )
        if min_amount is not None:
            q = q.filter(AuditEvent.amount >= float(min_amount))
        if max_amount is not None:
            q = q.filter(AuditEvent.amount <= float(max_amount))
        if block_min is not None:
            q = q.filter(AuditEvent.block_number >= int(block_min))
        if block_max is not None:
            q = q.filter(AuditEvent.block_number <= int(block_max))
        try:
            if start_iso:
                start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
                q = q.filter(AuditEvent.timestamp >= start_dt)
            if end_iso:
                end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
                q = q.filter(AuditEvent.timestamp <= end_dt)
        except Exception:
            pass

        q = q.order_by(AuditEvent.block_number.desc(), AuditEvent.id.desc()).limit(int(limit))
        events = q.all()

        out_events: List[dict] = []
        for ev in events:
            ev_dict = _dictify_event_row(ev, tz, include_raw=include_raw)
            entry: dict = {"event": ev_dict}
            proof = None
            if include_proof:
                proof = session.query(EventProof).filter(EventProof.event_id == ev.event_id).first()
            if proof:
                try:
                    entry["proof"] = json.loads(proof.proof_json)
                except Exception:
                    entry["proof"] = {"raw": proof.proof_json}
                mb = (
                    session.query(MerkleBatch)
                    .filter(MerkleBatch.batch_id == proof.batch_id)
                    .first()
                )
                if mb:
                    entry["batch"] = {
                        "batch_id": mb.batch_id,
                        "merkle_root": mb.merkle_root,
                        "leaf_count": mb.leaf_count,
                        "created_at": mb.created_at.isoformat() if mb.created_at else None,
                    }
                    if include_anchor:
                        anchors: List[dict] = []
                        ars = (
                            session.query(AnchorRecord)
                            .filter(AnchorRecord.batch_id == mb.batch_id)
                            .all()
                        )
                        for ar in ars:
                            anchors.append(
                                {
                                    "chain": ar.chain,
                                    "status": ar.status,
                                    "tx_hash": ar.tx_hash,
                                    "block_number": ar.block_number,
                                    "anchored_at": ar.anchored_at.isoformat() if ar.anchored_at else None,
                                }
                            )
                        entry["anchors"] = anchors
            out_events.append(entry)

        pkg = {
            "version": "1.0",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "criteria": {
                "address": address,
                "role": role,
                "tx_hash": tx_hash,
                "tx_prefix_ok": tx_prefix_ok,
                "min_amount": min_amount,
                "max_amount": max_amount,
                "block_min": block_min,
                "block_max": block_max,
                "start_iso": start_iso,
                "end_iso": end_iso,
                "limit": limit,
            },
            "count": len(out_events),
            "events": out_events,
            "verification": {
                "instructions": "For each event with proof, recompute leaf, fold proof to merkle_root, compare with batch; anchor records are included when available.",
            },
        }

        if not as_zip:
            return {
                "path": None,
                "sha256": None,
                "bytes": None,
                "count": len(out_events),
                "data": pkg
            }


        out_dir = ROOT / "data" / "proof_packs"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        fname = f"proof_pack_batch_{ts}_n{len(out_events)}.zip"
        zip_path = out_dir / fname
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("proof_pack.json", json.dumps(pkg, ensure_ascii=False, indent=2))
            readme = (
                "This archive contains integrity proof data for multiple events matching the criteria.\n"
                "Files:\n"
                "- proof_pack.json: events + optional proofs/batches/anchors\n"
                "Verification: for each event with proof, recompute leaf, apply proof to reach merkle_root, compare; anchor info provided when available.\n"
            )
            zf.writestr("README.txt", readme)
        sha256 = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        return {
            "path": str(zip_path),
            "sha256": sha256,
            "bytes": zip_path.stat().st_size,
            "count": len(out_events),
        }
    finally:
        session.close()

if __name__ == "__main__":
    print("🚀 KOSCOM AUDIT MCP SERVER STARTING...")
    app.run()

