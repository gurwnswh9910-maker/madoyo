FROM python:3.11-slim

WORKDIR /app

# 필수 기본 라이브러리 및 DB(PostgreSQL) 연결을 위한 라이브러리만 설치
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# [MVP V7] 서버에서 크롬을 직접 띄우지 않으므로 크롬 설치 및 드라이버 다운로드 과정 삭제 (빌드 에러 및 OOM 방지)

COPY . .

# 환경 변수 설정
ENV PYTHONUNBUFFERED=1

# 실행 명령어 (워커 1개, 타임아웃 10분 고정 - OOM 및 타임아웃 방지용 설정 유지)
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "api.main:app", "--bind", "0.0.0.0:10000", "--timeout", "600"]
