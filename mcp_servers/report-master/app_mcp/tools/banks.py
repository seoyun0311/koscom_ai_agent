from app_mcp.core.config import get_settings
from app_mcp.utils.http import get_json
from app_mcp.models import BanksPayload

async def fetch_banks(period: str) -> BanksPayload:
    s = get_settings()
    if s.provider_banks_url:
        data = await get_json(f"{s.provider_banks_url}?period={period}")
    else:
        # MOCK
        data = {
            "as_of": f"{period}-01",
            "custodians": [
                {"name":"Bank A","country":"KR","credit_tier":"A","share":0.55},
                {"name":"Bank B","country":"US","credit_tier":"AA","share":0.45}
            ],
            "concentration_index": 0.62,
            "alerts": []
        }
    return BanksPayload(**data)
