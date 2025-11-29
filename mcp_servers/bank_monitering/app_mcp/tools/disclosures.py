# disclosures.py
from __future__ import annotations

import io
import zipfile
import xml.etree.ElementTree as ET
from typing import Any, Dict, List

import httpx

from core.config.dart import get_dart_settings

# ─────────────────────────────────────────────
# DART 설정
# ─────────────────────────────────────────────

DART_SETTINGS = get_dart_settings()
DART_API_KEY = DART_SETTINGS.api_key

CORP_CODE_BASE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"

# 🔥 KSD(한국예탁결제원) corp_code (두 코드 모두 제외)
KSD_CORP_CODES = {"00159652", "00159651"}

# ─────────────────────────────────────────────
# 공식명 정규화 매핑
# ─────────────────────────────────────────────

BANK_NAME_MAP: Dict[str, str] = {
    "신한": "신한금융지주",
    "신한은행": "신한금융지주",
    "신한금융": "신한금융지주",
    "신한금융지주": "신한금융지주",

    "국민": "KB금융",
    "국민은행": "KB금융",
    "kb": "KB금융",
    "kb국민": "KB금융",
    "kb국민은행": "KB금융",
    "kb금융": "KB금융",
    "kb금융지주": "KB금융",
    "케이비": "KB금융",

    "kdb": "한국산업은행",
    "kdb은행": "한국산업은행",
    "산업은행": "한국산업은행",

    "nh": "NH투자증권",
    "엔에이치": "NH투자증권",
    "nh투자": "NH투자증권",
    "nh투자증권": "NH투자증권",

    # 🔥 KSD는 정규화만 하고 조회는 차단함
    "예탁": "한국예탁결제원",
    "예탁원": "한국예탁결제원",
    "ksd": "한국예탁결제원",
    "한국예탁결제원": "한국예탁결제원",
}

def normalize_keyword(keyword: str) -> str:
    low = keyword.strip().lower()

    for key, official in BANK_NAME_MAP.items():
        if key.lower() == low or key.lower() in low:
            print(f"🔄 정규화: '{keyword}' → '{official}'")

            # 🔥 예탁결제원이면 여기서 즉시 제외하도록 처리
            if official == "한국예탁결제원":
                print("⚠️ 한국예탁결제원(KSD) 재무제표 조회 제외됨")
                return "KSD_EXCLUDED"

            return official

    return keyword.strip()


# ─────────────────────────────────────────────
# corpCode.xml 다운로드
# ─────────────────────────────────────────────

async def download_corp_code_zip() -> bytes:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(CORP_CODE_BASE_URL, params={"crtfc_key": DART_API_KEY})
        r.raise_for_status()
        return r.content


async def load_corp_code_xml_root() -> ET.Element:
    raw = await download_corp_code_zip()

    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        xml_bytes = zf.read("CORPCODE.xml")

    root = ET.fromstring(xml_bytes)
    return root


# ─────────────────────────────────────────────
# corp_code 검색
# ─────────────────────────────────────────────

async def corp_codes_search(keyword: str) -> List[Dict[str, str]]:
    keyword = (keyword or "").strip()
    if not keyword:
        return []

    print(f"🔍 DART 검색: '{keyword}'")

    # 🔥 KSD는 여기서 즉시 제외
    if keyword == "KSD_EXCLUDED":
        print("⚠️ KSD는 corp_code 검색 제외됨")
        return []

    root = await load_corp_code_xml_root()
    out = []

    keyword_l = keyword.lower()

    for el in root.iter("list"):
        corp_name = (el.findtext("corp_name") or "").strip()
        corp_code = (el.findtext("corp_code") or "").strip()

        # 🔥 한국예탁결제원 제외
        if corp_code in KSD_CORP_CODES:
            continue

        if keyword_l in corp_name.lower():
            out.append({
                "corp_name": corp_name,
                "corp_code": corp_code,
                "stock_code": (el.findtext("stock_code") or "").strip(),
                "modify_date": (el.findtext("modify_date") or "").strip(),
            })

    print(f"📋 검색 결과: {len(out)}개 (KSD 제외됨)")
    return out


# ─────────────────────────────────────────────
# corp_code 선택
# ─────────────────────────────────────────────

async def resolve_corp_code(keyword: str, limit: int = 5) -> Dict[str, Any]:
    normalized = normalize_keyword(keyword)

    # 🔥 KSD 즉시 제외 처리
    if normalized == "KSD_EXCLUDED":
        return {
            "best": None,
            "candidates": [],
            "normalized_keyword": "한국예탁결제원",
            "note": "custody_agent_excluded",
        }

    candidates = await corp_codes_search(normalized)

    if not candidates:
        return {"best": None, "candidates": [], "normalized_keyword": normalized}

    weighted = []

    for c in candidates:
        name = c.get("corp_name", "")
        w = 0

        if name == normalized:
            w += 20
        elif normalized in name:
            w += 10

        for kw in ["금융", "은행", "증권", "산업"]:
            if kw in name:
                w += 3

        if c.get("stock_code"):
            w += 5

        if "지주" in name:
            w -= 2

        weighted.append((w, c))

    weighted.sort(key=lambda x: (-x[0], x[1].get("corp_name", "")))

    best_list = [w[1] for w in weighted[:limit]]
    best = best_list[0] if best_list else None

    return {
        "best": best,
        "candidates": best_list,
        "normalized_keyword": normalized,
    }


# ─────────────────────────────────────────────
# MCP 등록
# ─────────────────────────────────────────────

def register(mcp):
    mcp.add_tool(resolve_corp_code, "resolve_corp_code", "회사명으로 corp_code 검색")
    mcp.add_tool(corp_codes_search, "corp_codes_search", "corpCode.xml 검색")
