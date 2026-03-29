FROM python:3.11-slim

WORKDIR /app

# 필수 기본 라이브러리 및 DB(PostgreSQL) 연결을 위한 라이브러리 설치
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 의존성 파일 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# [V7-Fix] 컨테이너 내부 구조를 로컬과 동일하게 /app/backend/... 순으로 구성
# 이렇게 하면 backend.api.main:app 접근이 항상 가능해집니다.
COPY . /app/backend/
RUN ls -R /app/backend/embedding_migration/
WORKDIR /app/backend

# 환경 변수 및 PYTHONPATH 설정 (모든 경로에서 모듈을 찾을 수 있도록 함)
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app:/app/backend

# 실행 명령어 (워커 1개, 타임아웃 10분)
# 이제 컨테이너 내부 WORKDIR가 /app/backend이므로 api.main:app으로 실행 가능합니다.
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "api.main:app", "--bind", "0.0.0.0:10000", "--timeout", "600"]
