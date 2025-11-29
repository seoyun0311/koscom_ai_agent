from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from core.config.settings import settings


Base = declarative_base()


# 감사 이벤트 테이블
class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(128), unique=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    block_number = Column(Integer, index=True)
    from_address = Column(String(128))
    to_address = Column(String(128))
    amount = Column(Float)
    tx_hash = Column(String(128))
    contract_address = Column(String(128))
    details_hash = Column(String(128))
    raw_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


# Merkle 배치 테이블
class MerkleBatch(Base):
    __tablename__ = "merkle_batches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String(128), unique=True, nullable=False)
    merkle_root = Column(String(128), nullable=False)
    leaf_count = Column(Integer, default=0)
    anchored_tx = Column(String(128))
    created_at = Column(DateTime, default=datetime.utcnow)


# 앵커링 기록 테이블
class AnchorRecord(Base):
    __tablename__ = "anchor_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String(128))
    chain = Column(String(64), default="Ethereum")
    tx_hash = Column(String(128))
    block_number = Column(Integer)
    status = Column(String(32), default="pending")
    anchored_at = Column(DateTime, default=datetime.utcnow)


class EventProof(Base):
    __tablename__ = "event_proofs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(128), unique=True, nullable=False)
    batch_id = Column(String(128), index=True)
    leaf_index = Column(Integer)
    proof_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


# DB 초기화
def init_db():
    engine = create_engine(settings.DB_URL, echo=True)
    Base.metadata.create_all(engine)
    print(f"✅ Database initialized: {settings.DB_URL}")
    return engine


def get_session():
    engine = create_engine(settings.DB_URL)
    Session = sessionmaker(bind=engine)
    return Session()


class SyncState(Base):
    __tablename__ = "sync_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(64), unique=True, nullable=False)
    last_block = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow)


def get_last_block(source: str) -> int | None:
    session = get_session()
    try:
        state = session.query(SyncState).filter_by(source=source).first()
        return state.last_block if state else None
    finally:
        session.close()


def set_last_block(source: str, last_block: int) -> None:
    session = get_session()
    try:
        state = session.query(SyncState).filter_by(source=source).first()
        if state is None:
            state = SyncState(source=source, last_block=last_block, updated_at=datetime.utcnow())
            session.add(state)
        else:
            state.last_block = last_block
            state.updated_at = datetime.utcnow()
        session.commit()
    finally:
        session.close()

