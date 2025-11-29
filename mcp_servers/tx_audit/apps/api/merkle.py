#KOSCOM/apps/api/merkle.py
import argparse
import json
import time
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import func

from core.config.settings import settings
from core.db.database import AnchorRecord, AuditEvent, EventProof, MerkleBatch, get_session
from core.logging.logger import get_logger
from core.utils.hash_utils import merkle_tree_with_proofs, normalize_hex

logger = get_logger(__name__)


def _make_batch_id() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")


def create_merkle_batch(limit: int = 1000, mode: str = "oldest", min_block: Optional[int] = None) -> Optional[Dict]:
    """Create a Merkle batch from unbatched events.
    Picks up to `limit` AuditEvent rows that don't have an EventProof yet,
    computes a SHA-256 Merkle root and per-leaf proofs, and stores them.
    Returns a summary dict or None if no work.
    """
    sess = get_session()
    try:
        # Find events without proofs
        sub = sess.query(EventProof.event_id)
        q = sess.query(AuditEvent).filter(~AuditEvent.event_id.in_(sub))
        if min_block is not None:
            q = q.filter(AuditEvent.block_number >= int(min_block))
        if str(mode).lower() == "latest":
            q = q.order_by(AuditEvent.block_number.desc(), AuditEvent.id.desc())
        else:
            q = q.order_by(AuditEvent.block_number.asc(), AuditEvent.id.asc())
        events: List[AuditEvent] = q.limit(int(limit)).all()
        if not events:
            return None

        # Prepare leaves (hex without 0x). Fallback to tx_hash for legacy rows.
        cleaned_pairs = []  # (event, leaf_hex)
        for ev in events:
            h = ev.details_hash or ev.tx_hash or ""
            h = normalize_hex(h)
            if h:
                cleaned_pairs.append((ev, h))

        if not cleaned_pairs:
            return None

        leaves = [leaf for (_, leaf) in cleaned_pairs]
        chosen_events = [ev for (ev, _) in cleaned_pairs]
        root_hex, proofs = merkle_tree_with_proofs(leaves)
        batch_id = _make_batch_id()

        mb = MerkleBatch(batch_id=batch_id, merkle_root=root_hex, leaf_count=len(leaves))
        sess.add(mb)
        sess.flush()

        for idx, (ev, proof_nodes) in enumerate(zip(chosen_events, proofs)):
            ep = EventProof(
                event_id=ev.event_id,
                batch_id=batch_id,
                leaf_index=idx,
                proof_json=json.dumps(proof_nodes),
            )
            sess.add(ep)

        sess.commit()
        return {"batch_id": batch_id, "merkle_root": root_hex, "leaf_count": len(leaves)}
    finally:
        sess.close()


def _count_unproven_events(min_block: Optional[int] = None) -> int:
    """Return number of AuditEvents that do not have EventProof rows yet."""
    sess = get_session()
    try:
        q = (
            sess.query(func.count(AuditEvent.id))
            .outerjoin(EventProof, EventProof.event_id == AuditEvent.event_id)
            .filter(EventProof.id == None)  # noqa: E711 - intentional SQL NULL comparison
        )
        if min_block is not None:
            q = q.filter(AuditEvent.block_number >= int(min_block))
        return int(q.scalar() or 0)
    finally:
        sess.close()


def anchor_batch(batch_id: str, chain: Optional[str] = None) -> Optional[Dict]:
    """Record an anchoring event for the given batch (mock chain by default)."""
    sess = get_session()
    chain_name = chain or getattr(settings, "ANCHOR_CHAIN", "mock")
    tx_prefix = getattr(settings, "ANCHOR_TX_PREFIX", "mock-")
    try:
        mb = sess.query(MerkleBatch).filter(MerkleBatch.batch_id == batch_id).first()
        if not mb:
            logger.warning("anchor_batch: batch_id %s not found", batch_id)
            return None
        ar = (
            sess.query(AnchorRecord)
            .filter(AnchorRecord.batch_id == batch_id, AnchorRecord.chain == chain_name)
            .first()
        )
        now = datetime.utcnow()
        tx_hash = mb.anchored_tx or f"{tx_prefix}{batch_id}"
        if ar is None:
            ar = AnchorRecord(
                batch_id=batch_id,
                chain=chain_name,
                tx_hash=tx_hash,
                status="anchored",
                anchored_at=now,
            )
            sess.add(ar)
        else:
            ar.chain = chain_name
            ar.status = "anchored"
            ar.tx_hash = ar.tx_hash or tx_hash
            if not ar.anchored_at:
                ar.anchored_at = now
        if not mb.anchored_tx:
            mb.anchored_tx = tx_hash
        sess.commit()
        return {
            "batch_id": batch_id,
            "chain": chain_name,
            "status": ar.status,
            "tx_hash": ar.tx_hash,
            "anchored_at": ar.anchored_at.isoformat() if ar.anchored_at else None,
            "merkle_root": mb.merkle_root,
            "leaf_count": mb.leaf_count,
        }
    finally:
        sess.close()


def process_merkle_batches_once(
    min_events: Optional[int] = None,
    limit: Optional[int] = None,
    mode: Optional[str] = None,
    min_block: Optional[int] = None,
    chain: Optional[str] = None,
) -> Dict:
    """Single evaluation cycle: create + anchor when pending events reach threshold."""
    threshold = int(min_events or getattr(settings, "MERKLE_MIN_PENDING_EVENTS", 500))
    limit = int(limit or getattr(settings, "MERKLE_BATCH_LIMIT", 1000))
    batch_mode = (mode or getattr(settings, "MERKLE_BATCH_MODE", "oldest")).lower()
    pending = _count_unproven_events(min_block=min_block)
    result: Dict = {"pending_events": pending, "batch": None, "anchor": None}
    if pending < threshold:
        logger.info(
            "Merkle poller skip: pending=%s threshold=%s",
            pending,
            threshold,
        )
        return result

    batch = create_merkle_batch(limit=limit, mode=batch_mode, min_block=min_block)
    if not batch:
        logger.info("Merkle poller: no eligible events despite pending=%s", pending)
        return result

    result["batch"] = batch
    logger.info(
        "Created Merkle batch %s (leaves=%s, pending_before=%s)",
        batch["batch_id"],
        batch["leaf_count"],
        pending,
    )
    anchor_result = anchor_batch(batch["batch_id"], chain=chain)
    if anchor_result:
        logger.info(
            "Anchored batch %s on %s tx=%s",
            batch["batch_id"],
            anchor_result["chain"],
            anchor_result["tx_hash"],
        )
    else:
        logger.warning("Batch %s created but anchor step failed/was skipped", batch["batch_id"])
    result["anchor"] = anchor_result
    return result


def run_merkle_batch_poller(
    interval: Optional[float] = None,
    min_events: Optional[int] = None,
    limit: Optional[int] = None,
    mode: Optional[str] = None,
    min_block: Optional[int] = None,
    chain: Optional[str] = None,
) -> None:
    """Looping poller that periodically attempts to batch + anchor."""
    sleep_interval = float(interval or getattr(settings, "MERKLE_POLL_INTERVAL_SEC", 300))
    logger.info("=== Merkle poller started (interval=%ss) ===", sleep_interval)
    while True:
        try:
            process_merkle_batches_once(
                min_events=min_events,
                limit=limit,
                mode=mode,
                min_block=min_block,
                chain=chain,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("Merkle poller error: %s", exc)
        time.sleep(sleep_interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merkle batch scheduler")
    parser.add_argument("--once", action="store_true", help="Run a single evaluation cycle")
    parser.add_argument("--min-events", type=int, help="Override pending-event threshold")
    parser.add_argument("--limit", type=int, help="Override per-batch leaf limit")
    parser.add_argument("--mode", choices=["oldest", "latest"], help="Event ordering preference")
    parser.add_argument("--interval", type=float, help="Sleep seconds between iterations")
    parser.add_argument("--min-block", type=int, help="Only include events >= this block")
    parser.add_argument("--chain", type=str, help="Anchor chain name override")
    args = parser.parse_args()

    if args.once:
        process_merkle_batches_once(
            min_events=args.min_events,
            limit=args.limit,
            mode=args.mode,
            min_block=args.min_block,
            chain=args.chain,
        )
    else:
        run_merkle_batch_poller(
            interval=args.interval,
            min_events=args.min_events,
            limit=args.limit,
            mode=args.mode,
            min_block=args.min_block,
            chain=args.chain,
        )
