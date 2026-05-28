# Madoyo Threads Automation

Threads + Coupang + Gemini 기반의 로컬 자동화 도구입니다.
Threads에서 콘텐츠를 수집하거나 업로드하고, Coupang Partners 링크를 생성하며, Gemini Vision으로 이미지와 상품 맥락을 읽어 카피 생성을 돕습니다.

## 빠른 시작

1. 이 저장소를 내려받습니다.
2. Git LFS 파일을 받습니다.

```powershell
git lfs pull
```

3. `.env.template`을 기준으로 `.env`를 만듭니다.

```powershell
Copy-Item .env.template .env
```

4. `.env`에 아래 값을 채웁니다.

```dotenv
GEMINI_API_KEY=
OPENAI_API_KEY=

THREADS_CURRENT_ACCOUNT=1
THREADS_ACCOUNT_1_USER_ID=
THREADS_ACCOUNT_1_ACCESS_TOKEN=
THREADS_ACCOUNT_1_APP_SECRET=

COUPANG_CURRENT_ACCOUNT=1
COUPANG_ACCESS_KEY_1=
COUPANG_SECRET_KEY_1=
```

5. 의존성 파일이 있으면 필요한 패키지를 설치합니다.

```powershell
if (Test-Path requirements.txt) {
    pip install -r requirements.txt
}
```

`requirements.txt`가 없는 환경에서는 Codex에게 "현재 코드 기준으로 requirements.txt 만들어줘"라고 요청하면 됩니다. 이 경우 Codex가 실제 import 경로를 확인한 뒤 설치 목록을 만들어야 합니다.

## Codex 온보딩

Codex 앱에서 이 저장소 또는 이 README를 열고 `/온보딩` 또는 `온보딩`이라고 말하면, Codex는 아래 방식으로 친절하게 도와야 합니다.

1. 먼저 인사하고, 사용자가 지금 하려는 일이 "내 계정으로 Threads 자동 업로드 세팅"인지 "수동/반자동만 사용"인지 묻습니다.
2. `.env.template`과 `.env` 존재 여부를 확인합니다.
3. 실제 키 값은 화면에 출력하지 않고, 변수명과 값의 존재 여부만 점검합니다.
4. Gemini API, Threads API, Coupang Partners API를 순서대로 안내합니다.
5. 계정명은 사람 이름이나 브랜드명이 아니라 `1`, `2`, `3` 슬롯으로 안내합니다.
6. `.env`를 수정할 때는 먼저 백업 파일을 만들고 진행합니다.
7. 자동 업로드를 실제로 실행하기 전에는 테스트 모드나 단건 검증부터 권합니다.

사용자에게 처음 건넬 말 예시:

> 안녕하세요. 이 저장소는 Threads 업로드, Coupang 링크 생성, Gemini 기반 카피/비전 분석을 같이 쓰는 로컬 자동화 도구예요. 제가 민감한 키는 화면에 보여주지 않고, `.env` 형식과 연결 상태만 차근차근 확인해드릴게요. 먼저 Gemini, Threads, Coupang 중 어디까지 준비되어 있나요?

## 환경변수 구조

공유용 계정은 이름 대신 번호 슬롯을 씁니다.

```dotenv
THREADS_CURRENT_ACCOUNT=1
THREADS_REFRESH_ACCOUNTS=1,2,3
THREADS_ACCOUNT_1_USER_ID=
THREADS_ACCOUNT_1_ACCESS_TOKEN=
THREADS_ACCOUNT_1_APP_SECRET=
THREADS_ACCOUNT_2_USER_ID=
THREADS_ACCOUNT_2_ACCESS_TOKEN=
THREADS_ACCOUNT_2_APP_SECRET=
THREADS_ACCOUNT_3_USER_ID=
THREADS_ACCOUNT_3_ACCESS_TOKEN=
THREADS_ACCOUNT_3_APP_SECRET=
```

Coupang도 같은 방식입니다.

```dotenv
COUPANG_CURRENT_ACCOUNT=1
COUPANG_ACCESS_KEY_1=
COUPANG_SECRET_KEY_1=
COUPANG_ACCESS_KEY_2=
COUPANG_SECRET_KEY_2=
COUPANG_ACCESS_KEY_3=
COUPANG_SECRET_KEY_3=
```

런타임 데이터 경로는 기본적으로 repo 안을 참조합니다.

```dotenv
MADOYO_EMBEDDING_STORAGE_PATH=upgrade_final_vector/embeddings_upgrade_final.pkl
MADOYO_DATA_CACHE_PATH=data_cache.pkl
MADOYO_PRACTICAL_SCORER_ARTIFACT=embedding_migration/practical_final_copy_scorer_20260527.pkl
MADOYO_MEDIA_TMP_DIR=tmp/madoyo_temp
```

## Gemini API 만들기

이 프로젝트는 현재 Gemini를 기본 AI로 씁니다. 이유는 상품 이미지, Threads 이미지, 쿠팡 이미지처럼 시각 정보가 중요한 입력을 함께 판단해야 해서입니다. Gemini의 멀티모달/비전 처리가 이 흐름에 잘 맞습니다.

1. [Google AI Studio API Keys](https://aistudio.google.com/apikey)에 접속합니다.
2. Google 계정으로 로그인합니다.
3. 새 API 키를 만듭니다.
4. `.env`에 넣습니다.

```dotenv
GEMINI_API_KEY=발급받은_키
```

보안 권장:

- 키를 GitHub에 올리지 않습니다.
- 가능하면 Google Cloud Console 또는 AI Studio에서 키 제한을 설정합니다.
- 브라우저 클라이언트 코드에 직접 넣지 않습니다.

공식 문서: [Gemini API keys](https://ai.google.dev/gemini-api/docs/api-key)

## Threads API 만들기

Threads 업로드에는 단순 API key가 아니라 Meta 앱과 사용자 access token이 필요합니다.

1. [Meta for Developers](https://developers.facebook.com/)에 로그인합니다.
2. 앱을 만들고 Threads API 사용을 설정합니다.
3. 앱 설정에서 Threads App ID와 App Secret을 확인합니다.
4. 필요한 권한을 준비합니다.

주요 권한:

- `threads_basic`
- `threads_content_publish`

5. OAuth 인증으로 authorization code를 받고 short-lived token을 얻습니다.
6. long-lived token으로 교환합니다.
7. `.env`에 번호 슬롯으로 저장합니다.

```dotenv
THREADS_CURRENT_ACCOUNT=1
THREADS_ACCOUNT_1_USER_ID=내_threads_user_id
THREADS_ACCOUNT_1_ACCESS_TOKEN=long_lived_access_token
THREADS_ACCOUNT_1_APP_SECRET=threads_app_secret
```

이 저장소에는 token 교환 보조 스크립트가 있습니다.

```powershell
python 자동화/get_token.py
```

토큰 갱신은 아래 스크립트를 씁니다.

```powershell
python refresh_threads_tokens.py
```

Threads 업로드는 보통 컨테이너 생성 후 publish 하는 흐름입니다. 이미지와 영상은 공개 URL이어야 Threads가 가져갈 수 있습니다.

참고:

- [Meta Threads API Postman collection](https://www.postman.com/meta/threads/documentation/dht3nzz/threads-api)
- [Meta for Developers](https://developers.facebook.com/docs/threads/)

## Coupang Partners API 만들기

이 프로젝트는 쿠팡 상품 검색과 딥링크 생성을 위해 Coupang Partners API 키를 사용합니다.

1. [쿠팡 파트너스](https://partners.coupang.com/)에 가입합니다.
2. 파트너스 계정에서 API 또는 Open API 사용 메뉴를 찾습니다.
3. Access Key와 Secret Key를 발급받습니다.
4. `.env`에 넣습니다.

```dotenv
COUPANG_CURRENT_ACCOUNT=1
COUPANG_ACCESS_KEY_1=발급받은_access_key
COUPANG_SECRET_KEY_1=발급받은_secret_key
```

검증 스크립트:

```powershell
python 자동화/verify_new_coupang_api.py
```

주의:

- Coupang API는 HMAC 서명이 맞지 않으면 인증 오류가 납니다.
- 시스템 시간이 크게 어긋나면 서명 만료 오류가 날 수 있습니다.
- 키는 `.env`에만 보관하고 코드에 직접 적지 않습니다.

공식 문서:

- [Coupang Open API authentication](https://developers.coupangcorp.com/hc/en-us/sections/360004301613-API-authentication-Key)
- [Coupang Partners](https://partners.coupang.com/)

## 다른 AI 쓰는 법

현재 기본 경로는 Gemini입니다.

```dotenv
GEMINI_API_KEY=
```

OpenAI를 함께 쓰고 싶으면 `.env`에 키를 추가합니다.

```dotenv
OPENAI_API_KEY=
```

OpenAI 키는 [OpenAI API keys](https://platform.openai.com/api-keys)에서 만들고, 서버 측 환경변수로만 사용합니다. 공식 인증 방식은 `Authorization: Bearer OPENAI_API_KEY`입니다.

다른 AI 제공자를 붙일 때 권장 방식:

1. 새 키를 `.env`에 추가합니다.

```dotenv
ANTHROPIC_API_KEY=
OPENROUTER_API_KEY=
```

2. `작동중코드/app_config.py`에 환경변수만 읽도록 추가합니다.
3. `작동중코드/optimize_copy_v2.py` 또는 별도 adapter 파일에서 모델 호출부만 교체합니다.
4. 이미지/비전 입력이 필요한 작업은 Gemini 경로를 유지하거나, 같은 수준의 vision API가 있는 모델로만 바꿉니다.

중요: 현재 이 저장소의 카피 생성과 이미지 맥락 분석은 Gemini Vision 전제에 맞춰져 있습니다. 다른 AI로 바꿀 수는 있지만, 이미지 이해 품질과 입력 형식 차이 때문에 결과가 달라질 수 있습니다.

## 주요 실행 파일

- 자동 업로드: `자동화/threads_auto_pipeline.py`
- 반자동 업로드: `반자동/semi_auto_publish.py`
- 수동 파이프라인: `수동화/manual_pipeline.py`
- Threads 토큰 교환: `자동화/get_token.py`
- Threads 토큰 갱신: `refresh_threads_tokens.py`
- Coupang API 검증: `자동화/verify_new_coupang_api.py`
- 벡터 통합 생성: `작동중코드/build_upgrade_final_vector.py`
- 카피 생성/채점 런타임: `작동중코드/optimize_copy_v2.py`

## 안전 원칙

- `.env`와 `.env.backup_*`는 절대 커밋하지 않습니다.
- 실행 전 `git status --short`로 민감 파일이 staging되지 않았는지 확인합니다.
- 큰 pkl 파일은 Git LFS로 관리합니다.
- 계정별 변수명에는 실제 계정명을 쓰지 않고 `1`, `2`, `3` 슬롯만 씁니다.
- 자동 업로드 전에는 단건 테스트를 먼저 실행합니다.

## 문제 해결

Gemini 키 오류:

- `.env`에 `GEMINI_API_KEY`가 있는지 확인합니다.
- 키가 제한되어 있다면 Generative Language API 사용이 허용되어 있는지 확인합니다.

Threads 업로드 오류:

- `THREADS_ACCOUNT_<번호>_USER_ID`와 `THREADS_ACCOUNT_<번호>_ACCESS_TOKEN`이 모두 있는지 확인합니다.
- access token 권한에 `threads_basic`, `threads_content_publish`가 포함되어 있는지 확인합니다.
- 이미지/영상은 Threads가 접근 가능한 공개 URL이어야 합니다.

Coupang 인증 오류:

- `COUPANG_ACCESS_KEY_<번호>`와 `COUPANG_SECRET_KEY_<번호>`가 같은 계정 쌍인지 확인합니다.
- PC 시간이 크게 틀어져 있지 않은지 확인합니다.
- HMAC 오류가 나면 `자동화/verify_new_coupang_api.py`로 먼저 검증합니다.
