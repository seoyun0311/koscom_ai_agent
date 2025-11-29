# app_mcp/tools/credit.py

from typing import Any, Optional
import httpx

from core.config.dart import get_dart_settings  # ← 전역 Dart Key Loader 사용

DART_BASE = "https://opendart.fss.or.kr/api"
DART_API_KEY = get_dart_settings().api_key     # 🔥 os.getenv 제거, 중앙 설정으로 통일


# ---------------------------------------------------------
# 숫자 변환 (comma 제거 + None 안전처리)
# ---------------------------------------------------------
def _nz(v: Optional[str]) -> float:
    try:
        if isinstance(v, str):
            return float(v.replace(",", "")) if v.strip() else 0.0
        return float(v or 0)
    except Exception:
        return 0.0


# ---------------------------------------------------------
# 파라미터 필터링
# ---------------------------------------------------------
def _params(**kw):
    return {k: v for k, v in kw.items() if v not in (None, "", [], {}, ())}


# ---------------------------------------------------------
# HTTP GET with error handling
# ---------------------------------------------------------
async def _get_json(url: str, params: dict) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------
# 단일회사 주요계정 조회
# ---------------------------------------------------------
async def _fetch_single_account(corp_code: str, bsns_year: str, reprt_code: str):
    url = f"{DART_BASE}/fnlttSinglAcnt.json"
    return await _get_json(url, _params(
        crtfc_key=DART_API_KEY,
        corp_code=corp_code,
        bsns_year=bsns_year,
        reprt_code=reprt_code,
    ))


# ---------------------------------------------------------
# 계정 매핑 사전
# ---------------------------------------------------------
ACCOUNT_KEYS = {
    "asset_total": [
        "자산총계", "총자산", "자산 총계",
        "Assets Total", "Total Assets"
    ],

    "liab_total": [
        "부채총계", "총부채", "부채 총계",
        "Total Liabilities", "Liabilities Total"
    ],

    "equity_total": [
        "자본총계", "총자본", "자본 총계",
        "Equity Total", "Total Equity"
    ],

    "asset_current": [
        "유동자산", "Current Assets"
    ],

    "liab_current": [
        "유동부채", "Current Liabilities"
    ],

    "net_income": [
        "당기순이익", "순이익", "Net Income"
    ],
}


# ---------------------------------------------------------
# DART 표에서 금액 추출
# ---------------------------------------------------------
def _pick_amount(rows: list[dict[str, Any]], keys: list[str]) -> float:
    for row in rows:
        name = (row.get("account_nm") or "").strip().lower()

        for k in keys:
            if k.lower() in name:
                amt = (
                    row.get("thstrm_amount")
                    or row.get("thstrm_add_amount")
                    or row.get("thstrm_dt")
                    or row.get("frmtrm_amount")
                    or row.get("frmtrm_add_amount")
                )
                return _nz(amt)  # 안전 변환
    return 0.0


# ---------------------------------------------------------
# 핵심: 은행 재무비율 계산
# ---------------------------------------------------------
async def calc_bank_ratios(corp_code: str, bsns_year: str, reprt_code="11011"):
    """
    DART 단일회사 주요계정 기반으로 재무비율 계산.
    custody_agent(KSD) 의 경우 즉시 제외.
    """

    # 🔥 KSD 예외 처리 (DART 재무 없음)
    if corp_code in ("00159652", "00159651") or "예탁" in corp_code:
        return {
            "ok": False,
            "error": "custody_agent_excluded",
            "metrics": {},
            "raw": {}
        }

    # 데이터 조회
    single = await _fetch_single_account(corp_code, bsns_year, reprt_code)
    rows = (single or {}).get("list") or []

    if not rows:
        return {
            "ok": False,
            "error": "no_dart_rows",
            "metrics": {},
            "raw": {}
        }

    # 금액 추출
    assets = _pick_amount(rows, ACCOUNT_KEYS["asset_total"])
    equity = _pick_amount(rows, ACCOUNT_KEYS["equity_total"])
    liab = _pick_amount(rows, ACCOUNT_KEYS["liab_total"])
    ca = _pick_amount(rows, ACCOUNT_KEYS["asset_current"])
    cl = _pick_amount(rows, ACCOUNT_KEYS["liab_current"])
    ni = _pick_amount(rows, ACCOUNT_KEYS["net_income"])

    # 비율 계산
    ratios = {
        "equity_ratio": (equity / assets) if assets > 0 else None,
        "leverage": (assets / equity) if equity > 0 else None,
        "current_ratio": (ca / cl) if cl > 0 else None,
        "roe": (ni / equity) if equity > 0 else None,
        "debt_ratio_pct": (liab / equity * 100) if equity > 0 else None,
        "current_ratio_pct": (ca / cl * 100) if cl > 0 else None,
    }

    return {
        "ok": True,
        "corp_code": corp_code,
        "metrics": ratios,
        "raw": {
            "assets_total": assets,
            "equity_total": equity,
            "liabilities_total": liab,
            "current_assets": ca,
            "current_liabilities": cl,
            "net_income": ni,
        },
    }
