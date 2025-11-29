# app_mcp/tools/dart_financials.py
"""
DART 재무제표를 '은행 리스크 분석용'으로 정규화해서 돌려주는 유틸/툴 모듈.
✨ 개선: 강력한 은행 매핑, 다중 검색어 전략, 공시목록 기반 조회
"""

from __future__ import annotations
from pprint import pprint
import io
import os
import zipfile
from typing import Any, Dict, List, Optional, Tuple

import httpx

from core.config.dart import get_dart_settings
from datetime import datetime

DART_SETTINGS = get_dart_settings()
DART_API_KEY = DART_SETTINGS.api_key
DART_BASE = "https://opendart.fss.or.kr/api"


# ─────────────────────────────────────────────
# HTTP 헬퍼
# ─────────────────────────────────────────────

async def _get_json(url: str, params: dict, timeout: float = 30.0) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json()


async def _get_bytes(url: str, params: dict, timeout: float = 60.0) -> bytes:
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.content


def _to_number(v: Optional[str]) -> Optional[float]:
    """
    DART 금액 문자열을 float로 변환.
    """
    if v is None:
        return None
    s = str(v).strip()
    if not s or s == "-":
        return None
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _match(name: str, keywords: List[str]) -> bool:
    name = name.replace(" ", "")
    return any(kw in name for kw in keywords)


# ─────────────────────────────────────────────
# ✨ 강화된 은행 매핑 레지스트리
# ─────────────────────────────────────────────

BANK_REGISTRY = {
    "신한은행": {
        "corp_code": "00382199",
        "dart_name": "신한지주",
        "search_keywords": ["신한금융", "신한", "shinhan"],
        "stock_code": "055550",
    },
    "국민은행": {
        "corp_code": "00688996",
        "dart_name": "KB금융",
        "search_keywords": ["KB금융", "국민", "kookmin"],
        "stock_code": "105560",
    },

    # 🔥 여기 두 개가 핵심 수정 포인트
    "하나은행": {
        # 예전: "00124428" (잘못된 / 구식 코드)
        "corp_code": "00547583",             # 하나금융지주
        "dart_name": "하나금융지주",
        "search_keywords": [
            "하나은행",
            "하나금융",
            "하나금융지주",
            "Hana",
            "Hana Bank",
            "KEB하나은행",
            "하나지주",
        ],
        "stock_code": "086790",
    },
    "NH투자증권": {
        # 예전: "00388953"
        "corp_code": "00120182",
        "dart_name": "NH투자증권",
        "search_keywords": ["NH투자", "엔에이치"],
        "stock_code": "005940",
    },
    "한국예탁결제원": {
        "corp_code": "00159652",
        "dart_name": "한국예탁결제원",
        "search_keywords": ["예탁", "KSD"],
        "stock_code": None,
    },
}




# 역방향 매핑 (별칭 → 표준명)
BANK_ALIASES = {}
for standard_name, info in BANK_REGISTRY.items():
    # 표준명
    BANK_ALIASES[standard_name.lower()] = standard_name
    # 검색 키워드
    for kw in info["search_keywords"]:
        BANK_ALIASES[kw.lower()] = standard_name


def _normalize_bank_keyword(keyword: str) -> Tuple[Optional[str], Optional[Dict]]:
    """
    사용자 입력을 은행 레지스트리 정보로 변환.
    
    Returns:
        (standard_name, bank_info) 또는 (None, None)
    """

    key_lower = keyword.strip().lower()

    # 🔥 하나은행 → 하나금융지주 강제 매핑 (레지스트리 전에 처리)
    clean = keyword.replace(" ", "").lower()
    if clean in ["하나은행", "keb하나은행", "hanabank", "하나"]:
        print("🔥 하나은행 → 하나금융지주 강제 매핑 (pre-registry)")
        return "하나은행", BANK_REGISTRY["하나은행"]

    
    # 1. 별칭 매핑 확인
    if key_lower in BANK_ALIASES:
        standard_name = BANK_ALIASES[key_lower]
        bank_info = BANK_REGISTRY[standard_name]
        print(f"🔄 은행명 매핑: '{keyword}' → '{standard_name}' (레지스트리)")
        return standard_name, bank_info
    
    # 2. 부분 매칭
    for standard_name, info in BANK_REGISTRY.items():
        if key_lower in standard_name.lower():
            print(f"🔄 은행명 부분 매칭: '{keyword}' → '{standard_name}'")
            return standard_name, info
        for kw in info["search_keywords"]:
            if key_lower in kw.lower() or kw.lower() in key_lower:
                print(f"🔄 은행명 키워드 매칭: '{keyword}' → '{standard_name}' (via '{kw}')")
                return standard_name, info
    
    print(f"⚠️ 은행명 매핑 실패: '{keyword}' - DART 직접 검색으로 전환")
    return None, None


# ─────────────────────────────────────────────
# corp_code 검색
# ─────────────────────────────────────────────

async def _search_corp_codes(keyword: str) -> List[Dict[str, Any]]:
    """
    corpCode.xml을 다운로드하여 keyword 부분검색.
    """
    if not DART_API_KEY:
        return [{"error": "DART_API_KEY not set"}]

    print(f"🔍 DART corpCode.xml 검색: '{keyword}'")

    zbytes = await _get_bytes(f"{DART_BASE}/corpCode.xml", {"crtfc_key": DART_API_KEY})
    
    with zipfile.ZipFile(io.BytesIO(zbytes)) as zf:
        xml = zf.read("CORPCODE.xml")
    
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml)

    out: List[Dict[str, Any]] = []
    key_l = keyword.lower()
    
    for el in root.iter("list"):
        corp = el.findtext("corp_code") or ""

        if (c := el.findtext("corp_code")) in ("00159652", "00159651"):
            continue

        name = (el.findtext("corp_name") or "").strip()
        if key_l in name.lower():
            out.append({
                "corp_code": el.findtext("corp_code") or "",
                "corp_name": name,
                "stock_code": el.findtext("stock_code") or "",
                "modify_date": el.findtext("modify_date") or "",
            })
    
    print(f"📋 검색 결과: {len(out)}개")
    for item in out[:5]:
        print(f"   - {item['corp_name']} ({item['corp_code']})")
    
    return out


async def _resolve_bank_corp_code(keyword: str, limit: int = 5) -> Dict[str, Any]:
    """
    은행/금융기관 이름으로 가장 적절한 corp_code 선택.
    
    개선: 레지스트리 우선, 실패 시 다중 검색어 시도
    """
    if not DART_API_KEY:
        return {"error": "DART_API_KEY not set"}

    # 1) 레지스트리 확인
    standard_name, bank_info = _normalize_bank_keyword(keyword)
    
    if bank_info and bank_info.get("corp_code"):
        # 레지스트리에 corp_code가 있으면 바로 반환
        print(f"✅ 레지스트리에서 corp_code 직접 획득: {bank_info['corp_code']}")
        return {
            "best": {
                "corp_code": bank_info["corp_code"],
                "corp_name": bank_info["dart_name"],
                "stock_code": bank_info.get("stock_code"),
                "source": "registry"
            },
            "candidates": [{
                "corp_code": bank_info["corp_code"],
                "corp_name": bank_info["dart_name"],
                "stock_code": bank_info.get("stock_code"),
            }],
            "normalized_keyword": bank_info["dart_name"]
        }

    # 정책금융기관 등 corp_code가 없는 경우
    if bank_info and not bank_info.get("corp_code"):
        note = bank_info.get("note", "DART 재무제표 미제출")
        print(f"⚠️ {standard_name}: {note}")
        return {
            "best": None,
            "candidates": [],
            "normalized_keyword": bank_info["dart_name"],
            "note": note
        }

    # 2) 레지스트리에 없으면 다중 검색어로 DART 검색
    search_keywords = [keyword]
    if bank_info:
        search_keywords.extend(bank_info["search_keywords"])
    
    all_candidates = []
    
    for search_kw in search_keywords:
        candidates = await _search_corp_codes(search_kw)
        
        if candidates and not any(isinstance(c, dict) and "error" in c for c in candidates):
            all_candidates.extend(candidates)
            
            # 충분한 결과가 나오면 중단
            if len(all_candidates) >= 3:
                break
    
    # 중복 제거
    seen = set()
    unique_candidates = []
    for c in all_candidates:
        corp_code = c.get("corp_code")
        if corp_code and corp_code not in seen:
            seen.add(corp_code)
            unique_candidates.append(c)
    
    if not unique_candidates:
        print(f"⚠️ 모든 검색어로 결과 없음: {search_keywords}")
        return {"best": None, "candidates": []}

    # 3) 가중치 계산
    weighted: List[Tuple[int, Dict[str, Any]]] = []
    
    for c in unique_candidates:
        name = (c.get("corp_name") or "").strip()
        w = 0

        # 레지스트리 dart_name과 정확 일치
        if bank_info and name == bank_info["dart_name"]:
            w += 50
        
        # 검색 키워드 포함
        if bank_info:
            for kw in bank_info["search_keywords"]:
                if kw in name:
                    w += 20

        # 금융/은행/증권 키워드
        for kw in ["금융", "은행", "증권", "예탁", "산업"]:
            if kw in name:
                w += 5

        # 상장사 우대
        if c.get("stock_code"):
            w += 10

        # 지주회사 우대
        if "지주" in name:
            w += 5

        weighted.append((w, c))

    weighted.sort(key=lambda x: (-x[0], x[1].get("corp_name", "")))
    top = [wc[1] for wc in weighted[:limit]]
    best = top[0] if top else None
    
    if best:
        print(f"✅ 최적 매칭: {best['corp_name']} ({best['corp_code']})")
    
    norm_keyword = bank_info["dart_name"] if bank_info else keyword
    
    return {
        "best": best,
        "candidates": top,
        "normalized_keyword": norm_keyword
    }

async def _get_latest_business_year(corp_code: str) -> Optional[int]:
    """
    최신 사업보고서의 '연도'만 추출해서 반환.
    """
    rcept_no, year = await _get_latest_business_report(corp_code)
    if not year:
        return None
    return int(year)


# ─────────────────────────────────────────────
# 재무제표 정규화
# ─────────────────────────────────────────────

def _normalize_single_account(raw: dict[str, Any]) -> Dict[str, Any]:
    """
    재무제표 응답에서 주요 계정 추출 및 비율 계산.
    """
    result: Dict[str, Optional[float]] = {
        "total_assets": None,
        "total_liabilities": None,
        "total_equity": None,
        "cash_and_equivalents": None,
        "current_assets": None,
        "current_liabilities": None,
        "short_term_borrowings": None,
        "long_term_borrowings": None,
        "deposits": None,
    }

    lst = raw.get("list") or []
    
    for row in lst:
        account_nm = (row.get("account_nm") or "").replace(" ", "")
        amount = _to_number(row.get("thstrm_amount"))

        if amount is None:
            continue

        # 자산/부채/자본
        if _match(account_nm, ["자산총계"]):
            result["total_assets"] = amount
        elif _match(account_nm, ["부채총계"]):
            result["total_liabilities"] = amount
        elif _match(account_nm, ["자본총계"]):
            result["total_equity"] = amount

        # 유동자산/유동부채
        elif _match(account_nm, ["유동자산"]):
            result["current_assets"] = amount
        elif _match(account_nm, ["유동부채"]):
            result["current_liabilities"] = amount

        # 현금성
        elif _match(account_nm, ["현금및현금성자산", "현금및현금성"]):
            result["cash_and_equivalents"] = amount

        # 차입금
        elif _match(account_nm, ["단기차입금"]):
            result["short_term_borrowings"] = amount
        elif _match(account_nm, ["장기차입금"]):
            result["long_term_borrowings"] = amount

        # 예수금
        elif _match(account_nm, ["예수금"]):
            result["deposits"] = amount

    # 비율 계산
    total_assets = result["total_assets"]
    total_equity = result["total_equity"]
    total_liabilities = result["total_liabilities"]
    current_assets = result["current_assets"]
    current_liabilities = result["current_liabilities"]

    ratios: Dict[str, Optional[float]] = {
        "equity_ratio": None,
        "leverage": None,
        "debt_ratio": None,
        "current_ratio": None,
    }

    if total_assets and total_equity and total_assets > 0 and total_equity != 0:
        ratios["equity_ratio"] = total_equity / total_assets
        ratios["leverage"] = total_assets / total_equity

    if total_liabilities and total_equity and total_equity != 0:
        ratios["debt_ratio"] = total_liabilities / total_equity

    if current_assets and current_liabilities and current_liabilities != 0:
        ratios["current_ratio"] = current_assets / current_liabilities

    return {**result, **ratios}


# ─────────────────────────────────────────────
# 🆕 공시목록 기반 조회
# ─────────────────────────────────────────────

def _extract_year(report_nm: str) -> Optional[str]:
    if not report_nm:
        return None
    
    # BOM 제거 + 공백 및 제어문자 제거
    nm = report_nm.replace("\uFEFF","").replace(" ", "").strip()
    
    # 패턴: 2024, 2024.12, 2024.1, 2024.01 모두 대응
    m = re.search(r"(20\d{2})(?:\.\d{1,2})?", nm)
    if m:
        return m.group(1)
    
    # 패턴: (제49기)
    m2 = re.search(r"제(\d+)기", nm)
    if m2:
        # 하나금융지주 = 1991 설립 → 기수 변환 가능 (원하면 구현해주면 됨)
        return None
    
    return None


async def _dart_financials_by_rcept_no(
    rcept_no: str,
    corp_code: str,
    bsns_year: int,
    reprt_code: str = "11011",
) -> dict[str, Any]:
    """
    🔥 접수번호 기반 재무제표 조회 (fnlttMultiAcnt 최신 규격)
    - 2024년 이후 API는 rcept_no + corp_code + bsns_year + reprt_code 모두 필수
    """

    if not DART_API_KEY:
        return {"ok": False, "error": "DART_API_KEY not set"}

    print(f"📊 접수번호 기반 재무제표 조회 시작: {rcept_no}")
    print(f"   corp_code={corp_code}, bsns_year={bsns_year}, reprt_code={reprt_code}")

    url = f"{DART_BASE}/fnlttMultiAcnt.json"
    params = {
        "crtfc_key": DART_API_KEY,
        "rcept_no": rcept_no,
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": reprt_code,
    }

    try:
        raw = await _get_json(url, params)
        status = raw.get("status")

        if status != "000":
            print(f"   ❌ fnlttMultiAcnt 실패: {raw.get('message')}")
            return {
                "ok": False,
                "error": raw.get("message", "fnlttMultiAcnt 조회 오류"),
                "status": status,
            }

        print("   ✅ fnlttMultiAcnt 조회 성공")

        normalized = _normalize_single_account(raw)

        return {
            "ok": True,
            "api_used": "fnlttMultiAcnt",
            "rcept_no": rcept_no,
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
            "normalized": normalized,
            "raw": raw,
        }

    except Exception as e:
        print(f"   ❌ 예외 발생: {e}")
        return {
            "ok": False,
            "error": f"fnlttMultiAcnt 예외: {e}"
        }




# ─────────────────────────────────────────────
# 공개 API 함수
# ─────────────────────────────────────────────

async def dart_financials_summary(
    corp_code: str,
    bsns_year: str,
    reprt_code: str = "11011",
) -> dict[str, Any]:
    """
    corp_code + 연도로 재무제표 조회 및 정규화.
    
    전략:
    1. fnlttSinglAcntAll API (연결/별도 재무제표)
    2. 구버전 fnlttSinglAcnt API
    3. 공시목록에서 접수번호 찾아서 fnlttMultiAcnt로 조회
    """
    if not DART_API_KEY:
        return {"ok": False, "error": "DART_API_KEY not set"}

    # === 전략 1 & 2: 기존 API 방식 ===
    attempts = [
        (f"{DART_BASE}/fnlttSinglAcntAll.json", "CFS", "연결재무제표"),
        (f"{DART_BASE}/fnlttSinglAcntAll.json", "OFS", "별도재무제표"),
        (f"{DART_BASE}/fnlttSinglAcnt.json", None, "구버전 API"),
    ]
    
    report_codes = [
        (reprt_code, "요청한 보고서"),
        ("11011", "사업보고서"),     # 3~4월 제출 (연결/별도)
        ("11012", "반기보고서"),     # 8월 제출
        ("11014", "1분기보고서"),   # 4~5월 제출
        ("11013", "3분기보고서"),   # 11월 제출
    ]

    
    for api_url, fs_div, api_desc in attempts:
        for try_reprt_code, reprt_desc in report_codes:
            params = {
                "crtfc_key": DART_API_KEY,
                "corp_code": corp_code,
                "bsns_year": bsns_year,
                "reprt_code": try_reprt_code,
            }
            
            if fs_div:
                params["fs_div"] = fs_div
            
            try:
                print(f"🔍 시도: {api_desc} / {reprt_desc}")
                raw = await _get_json(api_url, params)
                
                if raw.get("status") == "000":
                    print(f"   ✅ 성공!")
                    normalized = _normalize_single_account(raw)
                    
                    return {
                        "ok": True,
                        "corp_code": corp_code,
                        "corp_name": raw.get("corp_name"),
                        "bsns_year": bsns_year,
                        "reprt_code": try_reprt_code,
                        "fs_div": fs_div,
                        "api_used": api_desc,
                        "normalized": normalized,
                        "raw": raw,
                    }
                else:
                    print(f"   ❌ {raw.get('message')}")
            except Exception as e:
                print(f"   ❌ 예외: {e}")
                continue
    
    # === 전략 3: 공시목록 기반 조회 ===
    print(f"\n🔄 전략 3: 공시목록 기반 조회")
    rcept_no = await _get_recent_disclosure_rcept_no(corp_code, bsns_year)
    
    if rcept_no:
        result = await _dart_financials_by_rcept_no(rcept_no, corp_code)
        if result.get("ok"):
            result["bsns_year"] = bsns_year
            result["corp_name"] = result.get("raw", {}).get("corp_name")
            return result
    
    # === 모든 시도 실패 ===
    return {
        "ok": False,
        "error": f"모든 재무제표 조회 시도 실패",
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "suggestion": f"DART에서 직접 확인: https://dart.fss.or.kr/dsab001/main.do"
    }
def _is_business_report(report_nm: str) -> bool:
    if not report_nm:
        return False
    nm = report_nm.replace(" ", "").replace("\uFEFF","")
    if "정정" in nm:
        return False
    # 사업보고서 패턴 완전 커버
    if "사업보고서" in nm:
        return True
    if "정기보고서" in nm:
        return True
    if ("사업" in nm and "보고" in nm):
        return True
    return False


def _is_half_report(report_nm: str) -> bool:
    nm = report_nm.replace(" ", "").replace("\uFEFF","")
    return ("반기" in nm and "보고서" in nm and "정정" not in nm)


def _is_quarter_report(report_nm: str) -> bool:
    nm = report_nm.replace(" ", "").replace("\uFEFF","")
    return ("분기" in nm and "보고서" in nm and "정정" not in nm)


async def _get_latest_report_rcept_no(corp_code: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    🔥 최신 보고서(사업보고서 → 반기 → 분기 순) 자동 탐색
    Returns: (rcept_no, bsns_year, report_type)
    """

    if not DART_API_KEY:
        return None, None, None

    print("📋 최신 보고서 자동 스캔 중...")

    current_year = datetime.now().year

    # 금융지주는 제출일 기준으로 다음해 3월 ~ 4월에 사업보고서가 올라오므로
    # 최근 3년 정도만 슬라이딩 검색하면 충분함
    search_years = [current_year, current_year - 1, current_year - 2]

    found_reports = []

    for y in search_years:
        params = {
            "crtfc_key": DART_API_KEY,
            "corp_code": corp_code,
            # 제출일 기준으로 검색
            "bgn_de": f"{y}0101",
            "end_de": f"{y}1231",
            "page_count": 100,
            "pblntf_ty": "A",  # 정기공시
        }

        try:
            data = await _get_json(f"{DART_BASE}/list.json", params)
        except:
            continue

        if data.get("status") != "000":
            continue

        for item in data.get("list", []):
            report_nm = item.get("report_nm", "")
            rcept_no = item.get("rcept_no")
            rcept_dt = item.get("rcept_dt")

            # 🔥 1) 사업보고서 (FULL 재무제표 → 최우선)
            if _is_business_report(report_nm):
                # 회계연도 추출
                import re
                m = re.search(r"(20\d{2})", report_nm)
                year = m.group(1) if m else None

                found_reports.append({
                    "type": "사업보고서",
                    "rcept_no": rcept_no,
                    "bsns_year": year,
                    "date": rcept_dt
                })
                continue

            # 🔥 2) 반기보고서 (fallback)
            if "반기보고서" in report_nm and "정정" not in report_nm:
                import re
                m = re.search(r"(20\d{2})", report_nm)
                year = m.group(1) if m else None

                found_reports.append({
                    "type": "반기보고서",
                    "rcept_no": rcept_no,
                    "bsns_year": year,
                    "date": rcept_dt
                })
                continue

            # 🔥 3) 분기보고서 (fallback)
            if "분기보고서" in report_nm and "정정" not in report_nm:
                import re
                m = re.search(r"(20\d{2})", report_nm)
                year = m.group(1) if m else None

                found_reports.append({
                    "type": "분기보고서",
                    "rcept_no": rcept_no,
                    "bsns_year": year,
                    "date": rcept_dt
                })
                continue

    if not found_reports:
        print("⚠️ 최신 보고서 없음 (사업/반기/분기 모두 없음)")
        return None, None, None

    # 🔥 1) 날짜 최신순 정렬
    found_reports.sort(key=lambda x: x["date"], reverse=True)

    # 🔥 2) 우선순위 정렬 (사업보고서 → 반기 → 분기)
    priority = {"사업보고서": 1, "반기보고서": 2, "분기보고서": 3}
    found_reports.sort(key=lambda x: priority[x["type"]])

    best = found_reports[0]
    print(f"   ✅ 최신 발견: {best['type']} / {best['bsns_year']} / {best['rcept_no']}")

    return best["rcept_no"], best["bsns_year"], best["type"]


async def bank_financials_by_name(
    bank_name: str,
    bsns_year: Optional[int] = None,
    reprt_code: str = "11011",
) -> dict[str, Any]:

    # 🔥 1) KSD 차단
    if "예탁" in bank_name or "ksd" in bank_name.lower():
        return {"ok": False, "error": "custody_agent_excluded"}

    if not DART_API_KEY:
        return {"ok": False, "error": "DART_API_KEY not set"}

    print(f"\n{'='*60}")
    print(f"📊 재무제표 조회 시작: {bank_name}")
    print(f"{'='*60}")

    # 🔥 2) corp_code 조회
    resolved = await _resolve_bank_corp_code(bank_name, limit=5)

    if resolved.get("best", {}).get("corp_code") == "00159652":
        return {"ok": False, "error": "custody_agent_excluded"}

    if "note" in resolved:
        return {
            "ok": False,
            "error": resolved["note"],
            "candidates": resolved.get("candidates", []),
            "normalized_keyword": resolved.get("normalized_keyword"),
            "resolved_bank_name": bank_name,
        }

    best = resolved.get("best")
    if not best:
        return {
            "ok": False,
            "error": f"No corp_code found for bank_name={bank_name}",
            "candidates": resolved.get("candidates", [])
        }

    corp_code = best["corp_code"]
    corp_name = best["corp_name"]
    print(f"✅ corp_code 매핑 성공: {corp_name} ({corp_code})")

    # 🔥 3) 최신 보고서 자동 탐색 (bsns_year=None일 때)
    rcept_no = None
    detected_year = None
    report_type = None

    if bsns_year is None:
        rcept_no, detected_year, report_type = await _get_latest_report_rcept_no(corp_code)

        if not rcept_no:
            return {
                "ok": False,
                "error": "최신보고서 탐색 실패",
                "corp_code": corp_code,
            }

        bsns_year = detected_year
        print(f"📅 자동 감지된 최신 연도: {bsns_year} ({report_type})")

    # 🔥 4) rcept_no가 있다면 → 접수번호 기반 조회 (최우선)
    if rcept_no:
        fin = await _dart_financials_by_rcept_no(
            rcept_no,
            corp_code,
            bsns_year,
            reprt_code
        )


        if fin.get("ok"):
            # 메타데이터 추가
            fin["resolved_bank_name"] = bank_name
            fin["resolved_corp_name"] = corp_name
            fin["corp_code"] = corp_code
            fin["corp_candidates"] = resolved.get("candidates", [])
            fin["normalized_keyword"] = resolved.get("normalized_keyword")
            fin["detected_year"] = bsns_year
            fin["report_type"] = report_type
            return fin

        print("⚠️ 접수번호 기반 조회 실패 → 기존 API 전략으로 fallback")

    # 🔥 5) fallback: 기존 API 시도
    base = await dart_financials_summary(
        corp_code=corp_code,
        bsns_year=bsns_year,
        reprt_code=reprt_code
    )

    # 🔥 6) 메타데이터 보강
    base["resolved_bank_name"] = bank_name
    base["resolved_corp_name"] = corp_name
    base["corp_code"] = corp_code
    base["corp_candidates"] = resolved.get("candidates", [])
    base["normalized_keyword"] = resolved.get("normalized_keyword")
    base["detected_year"] = bsns_year

    print(f"{'='*60}\n")
    return base



# ─────────────────────────────────────────────
# MCP Tool 등록
# ─────────────────────────────────────────────

def register(mcp):
    """
    MCP 서버에 툴 등록.
    """
    mcp.add_tool(
        dart_financials_summary,
        name="dart_financials_summary",
        description=(
            "corp_code와 사업연도로 DART 재무제표를 조회하고 정규화합니다."
        ),
    )

    mcp.add_tool(
        bank_financials_by_name,
        name="bank_financials_by_name",
        description=(
            "은행명으로 가장 적절한 corp_code를 찾은 후 재무제표를 조회합니다. "
            "예: '신한은행', '국민은행', 'KB', '하나은행', 'NH투자증권', '한국예탁결제원'"
        ),
    )

async def validate_bank_registry():

    print("\n===== BANK_REGISTRY 검증 시작 =====")

    for bank_name, info in BANK_REGISTRY.items():
        dart_name = info["dart_name"]
        expected = info.get("corp_code")

        if not expected:
            print(f"[SKIP] {bank_name}: corp_code 미설정")
            continue

        candidates = await _search_corp_codes(dart_name)
        ok = any(c.get("corp_code") == expected for c in candidates)

        if ok:
            print(f"[OK] {bank_name}: corp_code={expected} (dart_name={dart_name})")
        else:
            print(
                f"[WARN] {bank_name}: 레지스트리 corp_code={expected} 가 "
                f"corpCode.xml 검색 결과와 불일치 (dart_name={dart_name})"
            )
            print("  -> candidates:")
            pprint(candidates)

    print("===== BANK_REGISTRY 검증 끝 =====\n")


if __name__ == "__main__":
    import asyncio
    asyncio.run(validate_bank_registry())
