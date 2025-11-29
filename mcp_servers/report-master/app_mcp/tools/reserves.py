#tools/reserves.py
from app_mcp.core.config import get_settings
from app_mcp.utils.http import get_json
from app_mcp.models import ReservesPayload, ReservesAsset

async def fetch_reserves(period: str) -> ReservesPayload:
    s = get_settings()
    if s.provider_reserves_url:
        data = await get_json(f"{s.provider_reserves_url}?period={period}")
    else:
        # 목업데이터 추후에 민석, 서윤이한테 물어봐서 바꾸기
        data = {
            "as_of": f"{period}-01T00:00:00Z",
            "coverage_ratio": 0.95,
            "valuation_method": "IFRS13/mark",
            "assets_breakdown": [{"type":"UST","amount":1000000.0}],
            "liabilities": {"circulating_supply": 980000.0},
            "flags": []
        }
    return ReservesPayload(**data)
