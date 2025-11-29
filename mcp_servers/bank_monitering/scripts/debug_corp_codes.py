# scripts/debug_corp_codes.py

import asyncio
from app_mcp.tools.dart_financials import _search_corp_codes  # 네가 올린 모듈 기준

TARGETS = [
    "하나금융지주",
    "하나은행",
    "KEB하나은행",
    "NH투자증권",
]

async def main():
    for kw in TARGETS:
        print("\n" + "=" * 60)
        print(f"🔍 검색어: {kw}")
        print("=" * 60)

        candidates = await _search_corp_codes(kw)

        for c in candidates:
            print(
                f"- corp_name={c.get('corp_name')}, "
                f"corp_code={c.get('corp_code')}, "
                f"stock_code={c.get('stock_code')}, "
                f"modify_date={c.get('modify_date')}"
            )

if __name__ == "__main__":
    asyncio.run(main())
