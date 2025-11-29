# bank_monitoring/app_mcp/tools/bank_name_normalizer.py

from mcp.server.fastmcp import FastMCP

BANK_NAME_MAP = {
    # 신한 → 신한금융지주
    "신한은행": "신한금융지주",
    "신한": "신한금융지주",
    "신한금융": "신한금융지주",

    # KB → KB금융지주
    "KB국민은행": "KB금융지주",
    "국민은행": "KB금융지주",
    "KB은행": "KB금융지주",
    "KB": "KB금융지주",
    "케이비": "KB금융지주",

    # 하나은행 → 하나금융지주 (⭐ 새로 추가)
    "하나은행": "하나금융지주",
    "KEB하나은행": "하나금융지주",
    "하나": "하나금융지주",

    # KDB → 산업은행
    "KDB은행": "산업은행",
    "산업은행": "산업은행",
    "KDB": "산업은행",

    # NH투자증권 → NH투자증권
    "NH투자증권": "NH투자증권",
    "엔에이치투자증권": "NH투자증권",

    # KSD (custody_agent, 특수법인) ⭐ 변경포인트
    "KSD": "KSD",
    "한국예탁결제원": "KSD",
    "예탁결제원": "KSD",
}


def normalize_name(name: str):
    name = name.strip()

    # 완전 일치 우선
    if name in BANK_NAME_MAP:
        return BANK_NAME_MAP[name]

    # 부분 매칭 지원
    for key, val in BANK_NAME_MAP.items():
        if key in name:
            return val

    # 매핑 못 찾으면 원본 반환
    return name


def register(mcp: FastMCP):
    @mcp.tool(
        name="normalize_bank_name",
        description="은행명을 가장 적절한 상위기관/지주사명으로 정규화합니다."
                    "예: '신한은행' → '신한금융지주', 'KB국민은행' → 'KB금융지주'"
    )
    def normalize_tool(bank_name: str):
        normalized = normalize_name(bank_name)
        return {
            "input": bank_name,
            "normalized": normalized
        }
