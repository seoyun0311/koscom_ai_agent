# 최상위 Dockerfile (final_koscom_ai_agent/Dockerfile)

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# asyncpg, cryptography 등 의존성 빌드용 패키지
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) 파이썬 의존성 설치
#   → 먼저 requirements.txt만 복사해서 캐시 활용
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) 전체 프로젝트 복사
COPY . .

# 주 포트들 (문서용)
EXPOSE 5100 5200 5300 5400 5900 8000 8086

# 기본 엔트리포인트 (compose.yml에서 서비스별 command로 덮어씀)
CMD ["python", "frontend/web_chat_app.py"]
