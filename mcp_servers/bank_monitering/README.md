bank_monitering/
├─ README.md                # 프로젝트 개요/빠른 시작/엔드포인트 정리
├─ .gitignore               # 커밋 제외 목록(.env, __pycache__ 등)
├─ .env                     # 환경변수 샘플(API_PORT, LOG_LEVEL 등)
├─ pyproject.toml           # uv/poetry 스타일 의존성 정의(범위)
├─ uv.lock                  # 의존성 '잠금' 스냅샷(정확 버전 목록)
│
├─ config/
│  └─ settings.yaml         # 정책/가중치/컷오프/밴드/제약 등 런타임 설정
│
├─ data/
│  ├─ banks.yaml            # 은행 메타(이름/그룹/D-SIB 여부)
│  └─ samples/
│     └─ metrics.csv        # 샘플 지표 데이터(점수·분산 테스트용)
│
├─ apps/
│  ├─ api/           # FastAPI 엔트리포인트(app 생성, 라우터 등록)
│  ├─ crud/
│  ├─ models/
│  ├─ prompts/
│  ├─ schemas/
│  └─ services/
│
├─ core/
│  ├─ config/               # Settings 로더(Pydantic), config.yaml 파서
│  ├─ db/                   # DB 연결/세션팩토리(SQLAlchemy 등)
│  ├─ logging/              # 구조적 로깅/포맷터/핸들러
│  └─ utils/                # 공용 유틸(시간, 검증, 변환 함수)
│
├─ dags/
│  ├─ ingest_daily.py       # 일일 수집 DAG(데이터 ETL)
│  └─ report_monthly.py     # 월간 리포팅 DAG(요약 리포트 생성)
│
├─ docs/
│  ├─ ARCHITECTURE.md       # 아키텍처 다이어그램/컴포넌트 설명
│  └─ RUNBOOK.md            # 장애 대응/운영 가이드(선택)
│
├─ infra/
│  └─ docker/
│     ├─ Dockerfile.api     # API 컨테이너 빌드 정의(uv sync --frozen)
│     └─ docker-compose.yml # 로컬 실행(포트/볼륨/의존 서비스)
│
├─ scripts/                 # 자동화 스크립트(개발·배포·테스트)
│  ├─ build.sh              # 도커 빌드(.env 생성 포함)
│  ├─ up.sh                 # docker compose up -d
│  ├─ down.sh               # docker compose down -v
│  └─ test_smoke.sh         # /health, /banks 등 스모크 테스트
│
└─ examples/                # 데모/샘플 코드(선택)
   └─ weather.py            # (기존 weather.py는 여기로 이동 권장)
# Bank-Credit-Risk-Management
