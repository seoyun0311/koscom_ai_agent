#app_mcp/core/config.py
from __future__ import annotations
from functools import lru_cache
import os
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


# 프로젝트 루트 (…/MCP)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 리포트/산출물 폴더
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"


def ensure_artifacts_dir() -> Path:
    """artifacts 디렉터리를 생성하고 Path를 반환한다."""
    ARTIFACTS_DIR.mkdir(exist_ok=True)
    return ARTIFACTS_DIR

class Settings(BaseSettings):
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)
    env: str = Field(default="dev")

    # DB: MySQL 미사용 → SQLite Async
    database_url: str = Field(..., alias="DATABASE_URL")

    # Provider (없으면 mock)
    provider_reserves_url: str | None = Field(default=None)
    provider_banks_url: str | None = Field(default=None)
    provider_audit_url: str | None = Field(default=None)

    # Slack
    slack_webhook_url: str | None = Field(default=None)

    # Artifacts
    artifact_dir: str = Field(default="./artifacts")

    # pydantic v2 설정
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )
    # app_mcp/core/config.py (Settings 안)
    public_base_url: str = Field(default="http://127.0.0.1:8000")
    slack_signing_secret: str | None = Field(default=None)
    
    #gmail로 보고서 보내는 세팅
    mail_smtp_host: str = "smtp.gmail.com"
    mail_smtp_port: int = 465
    mail_username: str = ""
    mail_password: str = ""
    mail_from: str = ""
    mail_to: str = ""

class Config:
    env_file = ".env"
    env_file_encoding = "utf-8"



@lru_cache
def get_settings() -> Settings:
    s = Settings()
    os.makedirs(s.artifact_dir, exist_ok=True)
    return s
