FROM python:3.11-slim

WORKDIR /app

# 필수 라이브러리 및 Chrome 설치용 유틸리티 설치
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    wget \
    gnupg \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Google Chrome Stable 버전 설치 (최신 버전 연동용)
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /etc/apt/trusted.gpg.d/google-chrome.gpg \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# SeleniumBase를 이용해 빌드 시점에 ChromeDriver 미리 다운로드 (런타임 지연 및 timeout 방지)
RUN python -c "from seleniumbase import Driver; Driver(browser='chrome', headless=True, install=True)" || true

COPY . .

# 환경 변수 설정
ENV PYTHONUNBUFFERED=1
ENV CHROME_BIN=/usr/bin/google-chrome

# 실행 명령어 (강제로 워커 1개, 타임아웃 10분 고정 - OOM 및 타임아웃 방지)
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "api.main:app", "--bind", "0.0.0.0:10000", "--timeout", "600"]
