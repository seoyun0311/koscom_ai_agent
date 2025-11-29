from app_mcp.core.config import get_settings
from app_mcp.utils.http import get_json
from app_mcp.models import AuditPayload

async def fetch_audit(target: str) -> AuditPayload:
    s = get_settings()
    if s.provider_audit_url:
        data = await get_json(f"{s.provider_audit_url}?target={target}")
    else:
        # MOCK
        data = {
            "as_of_block": "latest",
            "events": [{"kind":"reserve_update","tx":"0xabc123","timestamp":"2025-07-01T00:00:00Z"}],
            "merkle_root": "0xmerkle...",
            "proof_url": None
        }
    return AuditPayload(**data)
