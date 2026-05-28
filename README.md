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

1. 먼저 인사하고, "제가 화면에서 무엇을 클릭하고 어디에 무엇을 입력하면 되는지 한 단계씩 안내하겠습니다"라고 말합니다.
2. 사용자가 지금 하려는 일이 "Threads 자동 업로드까지 세팅"인지 "수동/반자동만 사용"인지 묻습니다.
3. `.env.template`과 `.env` 존재 여부를 확인합니다.
4. 실제 키 값은 화면에 출력하지 않고, 변수명과 값의 존재 여부만 점검합니다.
5. Gemini API, Threads API, Coupang Partners API를 순서대로 안내합니다.
6. 계정명은 사람 이름이나 브랜드명이 아니라 `1`, `2`, `3` 슬롯으로 안내합니다.
7. `.env`를 수정할 때는 먼저 백업 파일을 만들고 진행합니다.
8. 자동 업로드를 실제로 실행하기 전에는 테스트 모드나 단건 검증부터 권합니다.

설명 방식:

- 사용자가 IT 지식이 없다고 가정하고, 한 번에 한 화면씩 안내합니다.
- `API`, `.env`, `access token`, `app secret`, `access key`, `secret key`처럼 사용자가 실제 사이트나 파일에서 검색해야 하는 필수 용어는 그대로 말합니다.
- 필수 용어를 처음 말할 때는 바로 뒤에 쉬운 설명을 붙입니다. 예: "`API`는 이 프로그램이 Gemini, Threads, Coupang에 요청을 보낼 때 필요한 공식 연결 방식입니다."
- "키를 주세요"처럼 모호하게 말하지 말고, "Google AI Studio 화면에서 `Create API key`를 누르고, 나온 값을 `.env`의 `GEMINI_API_KEY=` 오른쪽에 붙여넣습니다"처럼 말합니다.
- "열쇠", "비밀번호 같은 것" 같은 비유로 API 이름을 바꾸지 않습니다. 실제 화면에 나오는 단어와 파일에 적어야 하는 변수명을 우선합니다.
- 사용자가 직접 해야 하는 행동은 `열기`, `클릭`, `복사`, `붙여넣기`, `저장` 단위로 끊어서 말합니다.
- 사용자가 값 입력을 마치면 Codex는 값을 출력하지 않고 "값이 비어 있지 않은지"만 확인합니다.

사용자에게 처음 건넬 말 예시:

> 안녕하세요. 지금부터 Threads 업로드, Coupang 링크 생성, Gemini 비전 분석을 쓸 수 있게 한 단계씩 도와드릴게요. 어려운 용어는 최소로 쓰되, `API`처럼 사이트에서 직접 찾아야 하는 단어는 그대로 말하겠습니다. 실제 API 키나 토큰 값은 화면에 보여주지 않고, 값이 들어갔는지만 확인하겠습니다. 먼저 자동 업로드까지 세팅하시나요, 아니면 수동/반자동만 쓰실 건가요?

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

`API`는 이 프로그램이 Gemini에 요청을 보낼 때 쓰는 공식 연결 방식입니다. `API key`는 Google AI Studio에서 복사해서 `.env` 파일에 붙여넣는 값입니다.

사용자에게 안내할 순서:

1. 브라우저에서 [Google AI Studio API Keys](https://aistudio.google.com/apikey)를 엽니다.
2. Google 계정으로 로그인합니다.
3. 약관 동의 화면이 나오면 내용을 확인하고 동의 버튼을 클릭합니다.
4. `API keys` 화면에서 `Create API key` 또는 `Get API key` 버튼을 클릭합니다.
5. 프로젝트를 고르라는 창이 나오면 기본 프로젝트를 선택합니다. 프로젝트가 없으면 화면에서 새 프로젝트 생성 버튼을 클릭합니다.
6. API key가 만들어지면 복사 버튼을 클릭합니다.
7. 이 저장소의 `.env` 파일을 엽니다.
8. `GEMINI_API_KEY=` 줄을 찾습니다.
9. `=` 오른쪽에 복사한 값을 붙여넣고 저장합니다.

```dotenv
GEMINI_API_KEY=발급받은_키
```

10. Codex에게 "Gemini API 값이 들어갔는지만 확인해줘"라고 말합니다. Codex는 값을 화면에 출력하지 않고 비어 있는지만 확인합니다.

보안 권장:

- 키를 GitHub에 올리지 않습니다.
- 가능하면 Google AI Studio 또는 Google Cloud Console에서 키 제한을 설정합니다.
- 브라우저 클라이언트 코드에 직접 넣지 않습니다.

공식 문서: [Gemini API keys](https://ai.google.dev/gemini-api/docs/api-key)

## Threads API 만들기

Threads 업로드에는 단순 API key가 아니라 Meta 앱과 사용자 access token이 필요합니다.

`access token`은 이 프로그램이 사용자 Threads 계정으로 게시물을 올릴 수 있게 허가받았다는 표시입니다. `app secret`은 Meta 앱 설정 화면에서 복사하는 값입니다.

사용자에게 안내할 순서:

1. 브라우저에서 [Meta for Developers](https://developers.facebook.com/)를 엽니다.
2. Threads를 사용할 Meta 계정으로 로그인합니다.
3. 오른쪽 위 또는 상단 메뉴에서 `My Apps`를 클릭합니다.
4. `Create App` 버튼을 클릭합니다.
5. 앱 생성 화면에서 `Threads` 또는 `Threads API` 사용 목적이 보이면 선택합니다.
6. 앱 이름을 입력합니다. 예: `madoyo-threads-1`
7. 생성이 끝나면 앱 대시보드로 들어갑니다.
8. 왼쪽 메뉴에서 `App settings`를 클릭하고 `Basic`을 클릭합니다.
9. `Threads App ID`와 `Threads App secret` 위치를 확인합니다.
10. `Threads App secret` 값을 복사해서 `.env`의 아래 줄에 붙여넣습니다.

```dotenv
THREADS_TOKEN_EXCHANGE_APP_SECRET=복사한_threads_app_secret
THREADS_ACCOUNT_1_APP_SECRET=복사한_threads_app_secret
```

11. Meta 또는 Postman의 Threads 인증 화면에서 아래 권한을 선택합니다.

주요 권한:

- `threads_basic`
- `threads_content_publish`

12. 인증 화면에서 Threads 계정 접근을 허용합니다.
13. 발급된 short-lived access token을 복사합니다.
14. `.env`에서 아래 줄을 찾고 값을 붙여넣습니다.

```dotenv
THREADS_TOKEN_ACCOUNT=1
THREADS_SHORT_LIVED_TOKEN=복사한_short_lived_access_token
```

15. PowerShell에서 아래 명령을 실행합니다.

```powershell
python 자동화/get_token.py
```

16. 스크립트가 성공하면 `.env`에 아래 값이 자동으로 저장됩니다.

```dotenv
THREADS_CURRENT_ACCOUNT=1
THREADS_ACCOUNT_1_USER_ID=자동_저장됨
THREADS_ACCOUNT_1_ACCESS_TOKEN=자동_저장됨
THREADS_ACCOUNT_1_APP_SECRET=자동_저장됨
```

17. Codex에게 "Threads 값이 들어갔는지만 확인해줘"라고 말합니다. Codex는 실제 token 값을 출력하지 않고 비어 있는지만 확인합니다.

토큰 갱신은 아래 스크립트를 씁니다.

```powershell
python refresh_threads_tokens.py
```

Threads 업로드는 보통 게시물 컨테이너를 만들고 publish 하는 흐름입니다. 이미지와 영상은 Threads가 접근 가능한 공개 URL이어야 합니다.

Meta 공식 Postman collection을 쓰는 경우:

1. [Meta Threads API Postman collection](https://www.postman.com/meta/threads/documentation/dht3nzz/threads-api)을 엽니다.
2. `Sign In`을 클릭해서 Postman에 로그인합니다.
3. `Fork` 또는 `View collection`을 클릭합니다.
4. `Authorization` 탭에서 `Grant type`을 `Authorization Code`로 선택합니다.
5. `Client ID`에는 Meta 앱의 `Threads App ID`를 입력합니다.
6. `Client Secret`에는 Meta 앱의 `Threads App secret`을 입력합니다.
7. `Scope`에는 `threads_basic,threads_content_publish`를 입력합니다.
8. `Get New Access Token`을 클릭합니다.
9. Meta 로그인/허용 화면이 뜨면 계속 진행합니다.
10. 발급된 access token을 복사해서 `.env`의 `THREADS_SHORT_LIVED_TOKEN=`에 붙여넣습니다.

참고:

- [Meta Threads API Postman collection](https://www.postman.com/meta/threads/documentation/dht3nzz/threads-api)
- [Meta for Developers](https://developers.facebook.com/docs/threads/)

## Coupang Partners API 만들기

이 프로젝트는 쿠팡 상품 검색과 딥링크 생성을 위해 Coupang Partners API 키를 사용합니다.

`Access Key`와 `Secret Key`는 쿠팡 화면에서 같이 발급되는 두 값입니다. 이 프로젝트에서는 쿠팡 상품 검색과 딥링크 생성을 위해 두 값이 모두 필요합니다.

사용자에게 안내할 순서:

1. 브라우저에서 [쿠팡 파트너스](https://partners.coupang.com/)를 엽니다.
2. 쿠팡 파트너스 계정으로 로그인합니다.
3. 상단 메뉴에서 `Tools`, `추가기능`, 또는 `파트너스 API`와 비슷한 메뉴를 찾습니다.
4. `파트너스 API` 화면으로 들어갑니다.
5. `API Key 발급`, `API Key 생성`, `발급` 버튼이 보이면 클릭합니다.
6. `Access Key`와 `Secret Key`가 보이면 각각 복사합니다.
7. `.env` 파일을 엽니다.
8. 아래 줄을 찾고 `=` 오른쪽에 값을 붙여넣습니다.

```dotenv
COUPANG_CURRENT_ACCOUNT=1
COUPANG_ACCESS_KEY_1=발급받은_access_key
COUPANG_SECRET_KEY_1=발급받은_secret_key
```

9. 저장한 뒤 PowerShell에서 아래 검증 명령을 실행합니다.

```powershell
python 자동화/verify_new_coupang_api.py
```

10. 실행 결과에 `[Success] API 요청 성공!`이 나오면 Coupang API 연결이 된 것입니다.

쿠팡 WING 화면으로 안내되는 계정이라면:

1. [Coupang WING](https://wing.coupang.com)에 로그인합니다.
2. 오른쪽 위의 판매자 이름을 클릭합니다.
3. `추가판매정보` 또는 `판매자정보`를 클릭합니다.
4. `OPEN API 키 발급` 또는 `API KEY 발급` 버튼을 클릭합니다.
5. 약관 동의 체크박스를 클릭합니다.
6. `발급` 버튼을 클릭합니다.
7. 팝업에서 `OPEN API`를 선택하고 `확인`을 클릭합니다.
8. 화면 하단에 나온 `Access Key`와 `Secret Key`를 `.env`에 붙여넣습니다.

주의:

- Coupang API는 HMAC 서명이 맞지 않으면 인증 오류가 납니다.
- 시스템 시간이 크게 어긋나면 서명 만료 오류가 날 수 있습니다.
- 키는 `.env`에만 보관하고 코드에 직접 적지 않습니다.
- 파트너스 API는 계정 승인 상태에 따라 발급 버튼이 안 보일 수 있습니다.

공식 문서:

- [Coupang Open API authentication](https://developers.coupangcorp.com/hc/en-us/sections/360004301613-API-authentication-Key)
- [Coupang Partners](https://partners.coupang.com/)

## 다른 AI 쓰는 법

현재 기본 경로는 Gemini입니다.

```dotenv
GEMINI_API_KEY=
```

OpenAI를 함께 쓰고 싶으면 `.env`에 키를 추가합니다.

사용자에게 안내할 순서:

1. 브라우저에서 [OpenAI API keys](https://platform.openai.com/api-keys)를 엽니다.
2. OpenAI 계정으로 로그인합니다.
3. `Create new secret key` 또는 새 키 생성 버튼을 클릭합니다.
4. 키 이름을 입력합니다. 예: `madoyo-1`
5. 생성된 값을 복사합니다.
6. `.env` 파일을 엽니다.
7. `OPENAI_API_KEY=` 줄의 `=` 오른쪽에 값을 붙여넣고 저장합니다.

```dotenv
OPENAI_API_KEY=
```

OpenAI 키는 [OpenAI API keys](https://platform.openai.com/api-keys)에서 만들고, 서버 측 환경변수로만 사용합니다. 공식 인증 방식은 `Authorization: Bearer OPENAI_API_KEY`입니다.

다른 AI 제공자를 붙일 때 권장 방식:

1. 해당 AI 서비스의 API key 발급 화면을 엽니다.
2. 새 API key를 생성합니다.
3. `.env`에 서비스 이름이 드러나는 변수명으로 추가합니다.

```dotenv
ANTHROPIC_API_KEY=
OPENROUTER_API_KEY=
```

4. `작동중코드/app_config.py`에 환경변수만 읽도록 추가합니다.
5. `작동중코드/optimize_copy_v2.py` 또는 별도 adapter 파일에서 모델 호출부만 교체합니다.
6. 이미지/비전 입력이 필요한 작업은 Gemini 경로를 유지하거나, 같은 수준의 vision API가 있는 모델로만 바꿉니다.

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
