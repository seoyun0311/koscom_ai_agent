"""
시나리오 데이터
- SCENARIO_NORMAL: 담보율 105% (정상)
- SCENARIO_WARNING: 담보율 99% (주의)
- SCENARIO_CRITICAL: 담보율 97% (위험)
"""

# 시나리오 A: 정상 운영 (담보율 105%)
SCENARIO_NORMAL = {
    "name": "정상 운영",
    "coverage_ratio": 105.0,
    "on_chain": {
        "total_supply": 10_000_000_000,      # 100억 KRWS
        "circulating": 9_500_000_000,        # 95억 유통
        "reserved": 500_000_000,             # 5억 예비
    },
    "off_chain": {
        "primary_custodians": [
            {
                "name": "신한은행",
                "balance": 4_500_000_000,    # 45억
                "deposit_type": "요구불예금"
            },
            {
                "name": "KB국민은행",
                "balance": 3_000_000_000,    # 30억
                "deposit_type": "MMF 연계 예금"
            }
        ],
        "secondary_custodian": {
            "name": "KDB산업은행",
            "balance": 1_500_000_000,        # 15억
        },
        "asset_manager": {
            "name": "NH투자증권",
            "portfolio": {
                "short_term_bonds": 800_000_000,      # 8억
                "money_market_fund": 400_000_000,     # 4억
                "cash_equivalent": 100_000_000,       # 1억
            },
            "total_value": 1_300_000_000,    # 13억
            "yield_rate": 3.25,               # 연 3.25%
        },
        "depository": {
            "name": "KSD(한국예탁결제원)",
            "securities": [
                {"type": "국고채권 1년물", "quantity": 100, "market_value": 150_000_000},
                {"type": "통안증권", "quantity": 50, "market_value": 50_000_000},
            ],
            "total_value": 200_000_000,       # 2억
        },
        "total_reserves": 10_500_000_000,     # 105억
    }
}

# 시나리오 B: 주의 상황 (담보율 99%)
SCENARIO_WARNING = {
    "name": "주의 상황",
    "coverage_ratio": 99.0,
    "on_chain": {
        "total_supply": 10_000_000_000,      # 100억 KRWS
        "circulating": 9_500_000_000,
        "reserved": 500_000_000,
    },
    "off_chain": {
        "primary_custodians": [
            {
                "name": "신한은행",
                "balance": 4_200_000_000,    # 42억 (3억 감소)
                "deposit_type": "요구불예금"
            },
            {
                "name": "KB국민은행",
                "balance": 2_800_000_000,    # 28억 (2억 감소)
                "deposit_type": "MMF 연계 예금"
            }
        ],
        "secondary_custodian": {
            "name": "KDB산업은행",
            "balance": 1_400_000_000,        # 14억 (1억 감소)
        },
        "asset_manager": {
            "name": "NH투자증권",
            "portfolio": {
                "short_term_bonds": 750_000_000,      # 7.5억
                "money_market_fund": 380_000_000,     # 3.8억
                "cash_equivalent": 90_000_000,        # 9천만
            },
            "total_value": 1_220_000_000,    # 12.2억
            "yield_rate": 2.85,               # 연 2.85%
        },
        "depository": {
            "name": "KSD(한국예탁결제원)",
            "securities": [
                {"type": "국고채권 1년물", "quantity": 90, "market_value": 135_000_000},
                {"type": "통안증권", "quantity": 45, "market_value": 45_000_000},
            ],
            "total_value": 180_000_000,       # 1.8억
        },
        "total_reserves": 9_900_000_000,     # 99억 (1억 부족)
    }
}

# 시나리오 C: 위험 상황 (담보율 97%)
SCENARIO_CRITICAL = {
    "name": "위험 상황",
    "coverage_ratio": 97.0,
    "on_chain": {
        "total_supply": 10_000_000_000,      # 100억 KRWS
        "circulating": 9_500_000_000,
        "reserved": 500_000_000,
    },
    "off_chain": {
        "primary_custodians": [
            {
                "name": "신한은행",
                "balance": 4_000_000_000,    # 40억 (5억 감소)
                "deposit_type": "요구불예금"
            },
            {
                "name": "KB국민은행",
                "balance": 2_600_000_000,    # 26억 (4억 감소)
                "deposit_type": "MMF 연계 예금"
            }
        ],
        "secondary_custodian": {
            "name": "KDB산업은행",
            "balance": 1_300_000_000,        # 13억 (2억 감소)
        },
        "asset_manager": {
            "name": "NH투자증권",
            "portfolio": {
                "short_term_bonds": 700_000_000,      # 7억
                "money_market_fund": 350_000_000,     # 3.5억
                "cash_equivalent": 80_000_000,        # 8천만
            },
            "total_value": 1_130_000_000,    # 11.3억
            "yield_rate": 1.95,               # 연 1.95% (수익률 하락)
        },
        "depository": {
            "name": "KSD(한국예탁결제원)",
            "securities": [
                {"type": "국고채권 1년물", "quantity": 80, "market_value": 120_000_000},
                {"type": "통안증권", "quantity": 40, "market_value": 40_000_000},
            ],
            "total_value": 160_000_000,       # 1.6억
        },
        "total_reserves": 9_700_000_000,     # 97억 (3억 부족)
    }
}

# 시나리오 매핑
SCENARIOS = {
    "normal": SCENARIO_NORMAL,
    "warning": SCENARIO_WARNING,
    "critical": SCENARIO_CRITICAL,
}