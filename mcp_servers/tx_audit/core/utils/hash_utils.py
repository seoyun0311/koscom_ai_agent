
import hashlib
import json
from typing import List, Tuple, Dict


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj) -> str:
    """Deterministic JSON (sorted keys, compact)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def details_hash_from_tx(tx: dict) -> str:
    """Stable hash for an ERC-20 Transfer log (Etherscan fields)."""
    picked = {
        "hash": tx.get("hash"),
        "blockNumber": str(tx.get("blockNumber")),
        "timeStamp": str(tx.get("timeStamp")),
        "from": (tx.get("from") or "").lower(),
        "to": (tx.get("to") or "").lower(),
        "contractAddress": (tx.get("contractAddress") or "").lower(),
        "value": str(tx.get("value")),
        "tokenDecimal": str(tx.get("tokenDecimal")),
    }
    cj = canonical_json(picked)
    return sha256_hex(cj.encode("utf-8"))


def merkle_tree_with_proofs(leaves_hex: List[str]) -> Tuple[str, List[List[Dict[str, str]]]]:
    """Build a SHA-256 Merkle tree; return (root_hex, proofs_by_index).
    Each proof is a list of {pos:'L'|'R', hash:<hex>} nodes from leaf to root.
    """
    if not leaves_hex:
        return "", []

    layers = [[bytes.fromhex(h) for h in leaves_hex]]
    proofs = [[ ] for _ in leaves_hex]

    while len(layers[-1]) > 1:
        curr = layers[-1]
        next_layer = []
        for i in range(0, len(curr), 2):
            left = curr[i]
            right = curr[i + 1] if i + 1 < len(curr) else curr[i]
            parent = hashlib.sha256(left + right).digest()
            next_layer.append(parent)

            li = i
            ri = min(i + 1, len(curr) - 1)
            proofs[li].append({"pos": "R", "hash": right.hex()})
            if ri != li:
                proofs[ri].append({"pos": "L", "hash": left.hex()})

        layers.append(next_layer)

    root_hex = layers[-1][0].hex()
    return root_hex, proofs


def normalize_hex(value: str) -> str:
    """Return a cleaned hex string without '0x' prefix; empty string if invalid.
    Ensures lowercase and even length.
    """
    if not value:
        return ""
    s = str(value).strip()
    if s.startswith("0x") or s.startswith("0X"):
        s = s[2:]
    s = s.lower()
    # validate hex characters
    for ch in s:
        if ch not in "0123456789abcdef":
            return ""
    if len(s) % 2 == 1:
        s = "0" + s
    return s
