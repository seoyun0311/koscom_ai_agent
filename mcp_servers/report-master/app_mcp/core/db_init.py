# app_mcp/core/db.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text   # ✅ 이 줄 추가
from app_mcp.core.config import get_settings

@asynccontextmanager
async def get_db_session() -> AsyncIterator[AsyncSession]:
    """
    FastAPI 의존성 말고, 일반 async 함수에서 쓸 수 있는 세션 컨텍스트.
    예) LangGraph 서비스, 배치 작업 등에서 사용.
    """
    async with SessionLocal() as session:
        yield session

def normalize_async_sqlite(url: str) -> str:
    """
    sqlite:///... 로 들어오면 sqlite+aiosqlite:///... 로 자동 보정
    이미 +aiosqlite면 그대로 유지
    """
    if url.startswith("sqlite+aiosqlite:///"):
        return url
    if url.startswith("sqlite:///"):
        return "sqlite+aiosqlite://" + url[len("sqlite://"):]
    # 혹시 다른 스킴이면 그대로 사용
    return url

# 1) 설정 로드
settings = get_settings()
db_url = normalize_async_sqlite(settings.database_url)

# 2) 엔진/세션팩토리 생성
engine = create_async_engine(db_url, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
async_session = SessionLocal

# 3) Declarative Base
class Base(DeclarativeBase):
    pass

# 4) DB 초기화
async def init_db():
    """
    - stablecoin 스키마 생성 (PostgreSQL일 때)
    - search_path 를 stablecoin 으로 설정
    - Base.metadata.create_all() 로 테이블 생성
    """
    from app_mcp.models import realtime_risk_snapshot  # 다른 모델 있으면 옆에 추가
    from app_mcp.models import human_review_task

    async with engine.begin() as conn:
        # ✅ PostgreSQL일 때만 스키마 생성 + search_path 설정
        if engine.url.get_backend_name().startswith("postgresql"):
            # stablecoin 스키마 생성
            await conn.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS stablecoin")
            # search_path를 stablecoin으로 설정
            await conn.exec_driver_sql("SET search_path TO stablecoin")

        # 테이블 생성 (지금 search_path 기준으로 생성됨)
        await conn.run_sync(Base.metadata.create_all)

# 5) FastAPI 의존성
async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
