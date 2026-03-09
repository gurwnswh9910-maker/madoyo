FROM python:3.11-slim

WORKDIR /app

# 필수 라이브러리 설치 (컴파일러 등)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 환경 변수 설정
ENV PYTHONUNBUFFERED=1

# 실행 명령어 (Render에서 덮어쓸 수 있음)
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "api.main:app", "--bind", "0.0.0.0:10000"]
