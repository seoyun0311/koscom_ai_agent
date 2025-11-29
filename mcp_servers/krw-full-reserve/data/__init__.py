"""
Data 패키지
"""

from data.mock_data import MockDataGenerator, get_mock_data
from data.scenarios import SCENARIOS, SCENARIO_NORMAL, SCENARIO_WARNING, SCENARIO_CRITICAL

__all__ = [
    "MockDataGenerator",
    "get_mock_data",
    "SCENARIOS",
    "SCENARIO_NORMAL",
    "SCENARIO_WARNING",
    "SCENARIO_CRITICAL",
]