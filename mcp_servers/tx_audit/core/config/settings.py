from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    # External API keys (allowing .env)
    DART_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None

    # API / network configuration
    ETHERSCAN_API_KEY: str = "8MI7GGZVPGE46PUCSVATRWTM8EYW7IKF4Y"
    USDT_CONTRACT: str = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
    ETHERSCAN_BASE_URL: str = "https://api.etherscan.io/api"

    # Local dancom sFIAT backend (default in this project)
    USE_LOCAL_SFIAT: bool = True
    LOCAL_API_BASE: str = "http://175.45.205.39:4000/api"
    LOCAL_TOKEN: str = "0x5FbDB2315678afecb367f032d93F642f64180aa3"
    LOCAL_ADDRESS_FILTER: str | None = None

    # Collector options
    ETHERSCAN_OFFSET: int = 500
    ETHERSCAN_RATE_SLEEP: float = 0.05
    POLL_INTERVAL_SEC: int = 15
    COLLECT_MAX_PAGES: int | None = 60
    COLLECT_MAX_SECONDS: int | None = 100

    # Data paths
    DATA_PATH: Path = BASE_DIR / "data"
    EVENT_PATH: Path = DATA_PATH / "events"
    PROOF_PATH: Path = DATA_PATH / "proofs"
    EVIDENCE_PATH: Path = DATA_PATH / "evidence"

    # Database
    DB_PATH: Path = BASE_DIR / "data" / "audit.db"
    DB_URL: str = f"sqlite:///{DB_PATH}"

    # Merkle/anchor defaults
    NETWORK: str = "Dancom Hardhat (Ncloud)"
    LOG_LEVEL: str = "INFO"
    MERKLE_POLL_INTERVAL_SEC: int = 300
    MERKLE_MIN_PENDING_EVENTS: int = 100
    MERKLE_BATCH_LIMIT: int = 1000
    MERKLE_BATCH_MODE: str = "oldest"
    ANCHOR_CHAIN: str = "mock"
    ANCHOR_TX_PREFIX: str = "mock-"

    # Optional batch interval
    BATCH_INTERVAL: int | None = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
