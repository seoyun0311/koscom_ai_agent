# [bank_monitering/core/config/dart.py]
import os
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv

class DARTSettings(BaseModel):
    api_key: str


def _load_env_recursive():
    """
    현재 파일 위치를 기준으로 상위 폴더를 올라가며 .env 파일을 탐색해 로드한다.
    """
    # 1️⃣ 시작 경로 = 현재 파일 위치
    current = Path(__file__).resolve().parent

    # 2️⃣ 루트까지 반복하면서 .env 탐색
    for parent in [current] + list(current.parents):
        env_file = parent / ".env"
        if env_file.exists():
            load_dotenv(dotenv_path=env_file, override=False)
            # print(f"✅ Loaded .env from: {env_file}")
            return
    # 3️⃣ 못 찾을 경우에도 조용히 통과
    print("⚠️ .env not found in any parent directories.")


def get_dart_settings() -> DARTSettings:
    """
    DART API 키를 환경변수 또는 .env에서 불러와 반환.
    상위 폴더까지 .env 자동 탐색 지원.
    """
    _load_env_recursive()  # ✅ 자동으로 상위 탐색하여 .env 로드

    key = os.getenv("DART_API_KEY", "")
    if not key:
        raise RuntimeError("DART_API_KEY not set (check your .env file)")
    return DARTSettings(api_key=key)
