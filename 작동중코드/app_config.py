import os
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드 (프로젝트 루트 탐색)
BASE_DIR = Path(__file__).parent.parent
env_path = BASE_DIR / '.env'
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()


def resolve_project_path(env_name, default_path):
    raw_path = os.getenv(env_name)
    if not raw_path:
        return Path(default_path)

    resolved = Path(raw_path).expanduser()
    if not resolved.is_absolute():
        resolved = BASE_DIR / resolved
    return resolved


class GlobalConfig:
    """프로젝트 전체의 설정을 중앙 집중 관리하는 클래스"""

    # 1. 경로 설정 (pathlib 기반)
    BASE_DIR = BASE_DIR
    WORKING_CODE_DIR = BASE_DIR / "작동중코드"
    AUTOMATION_DIR = BASE_DIR / "자동화"

    # 데이터 관련
    STORAGE_PATH = resolve_project_path(
        "MADOYO_EMBEDDING_STORAGE_PATH",
        BASE_DIR / "upgrade_final_vector" / "embeddings_upgrade_final.pkl",
    )
    CACHE_PATH = resolve_project_path("MADOYO_DATA_CACHE_PATH", BASE_DIR / "data_cache.pkl")
    PROCESSED_LOG_PATH = AUTOMATION_DIR / "processed_links.log"

    # 2. API 설정
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

    # 봇 탐지 방지용 User-Agent 위장 기종 정보 (사용자 기기: Galaxy S22+ 한국판 SM-S906N)
    MOBILE_USER_AGENT = "Mozilla/5.0 (Linux; Android 14; SM-S906N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.119 Mobile Safari/537.36"

    # [계정 선택 로직] 공유용 번호 슬롯. 예: THREADS_CURRENT_ACCOUNT=1,2,3
    CURRENT_ACCOUNT = os.getenv("THREADS_CURRENT_ACCOUNT", "1").split(",")[0].strip() or "1"

    @classmethod
    def get_account_credentials(cls, account_name):
        account_slot = str(account_name or "1").strip()
        if account_slot.upper().startswith("ACCOUNT_"):
            account_slot = account_slot.split("_", 1)[1]
        user_id = os.getenv(f"THREADS_ACCOUNT_{account_slot}_USER_ID")
        access_token = os.getenv(f"THREADS_ACCOUNT_{account_slot}_ACCESS_TOKEN")
        if account_slot == "1":
            user_id = user_id or os.getenv("THREADS_USER_ID")
            access_token = access_token or os.getenv("THREADS_ACCESS_TOKEN")
        return user_id, access_token

    @classmethod
    def get_account_secret(cls, account_name):
        account_slot = str(account_name or "1").strip()
        if account_slot.upper().startswith("ACCOUNT_"):
            account_slot = account_slot.split("_", 1)[1]
        return os.getenv(f"THREADS_ACCOUNT_{account_slot}_APP_SECRET")

    THREADS_USER_ID, THREADS_ACCESS_TOKEN = get_account_credentials.__func__(None, CURRENT_ACCOUNT)
    THREADS_SECRET = get_account_secret.__func__(None, CURRENT_ACCOUNT)

    # 쿠팡 계정 선택 로직
    COUPANG_CURRENT_ACCOUNT = os.getenv("COUPANG_CURRENT_ACCOUNT", "1").strip() or "1"
    COUPANG_ACCESS_KEY = os.getenv(f"COUPANG_ACCESS_KEY_{COUPANG_CURRENT_ACCOUNT}") or os.getenv("COUPANG_ACCESS_KEY")
    COUPANG_SECRET_KEY = os.getenv(f"COUPANG_SECRET_KEY_{COUPANG_CURRENT_ACCOUNT}") or os.getenv("COUPANG_SECRET_KEY")
    #현재 원활히 작동하는 최신 api 모델입니다. 임베딩 모델은 고칠경우 코드가 동작하지 않습니다.
    MODEL_NAME = "gemini-3-flash-preview"
    EMBEDDING_MODEL = "models/gemini-embedding-2-preview"

    # 3. 성능 및 안정성 (마법의 숫자 제거)
    MAX_WORKERS = 25
    POST_INTERVAL = 7.5       # 포스팅 간 대기 시간 (초)
    FILE_API_POLL = 2         # Gemini File API 상태 체크 간격 (초)
    FILE_API_TIMEOUT = 60     # Gemini File API 처리 타임아웃 (초)
    SCRAPER_TIMEOUT = 10      # 스크래퍼 로딩 대기 시간 (초)

    # 4. 정적 전략 (고정 성공 공식)
    STATIC_STRATEGIES = [
        ('일상 속 비의도적 발견 (진성)', '전문가나 셀럽이 아닌 일상 속 인물(가족, 친구 등)의 비의도적인 감탄을 통해 가치를 증명하고, 이모티콘을 활용해 진정성을 부여하세요.'),
        ('제3자 검증 통한 우월감 (신뢰)', '엄마, 지인 등 제3자의 구체적 반응을 묘사하고, 그 가치가 왜 발생했는지 이유를 설명하여 똑똑한 소비를 했다는 지적 우월감을 자극하세요.'),
        ('트렌드 비교를 통한 사유유도 (참여)', '대중에게 인지도가 높은 핫플이나 브랜드를 대조 비교하여 시선을 끈 뒤, 개방형 질문을 던져 독자가 능동적으로 생각하게 유도하세요.'),
    ]

    # 5. 콘텐츠 양식 (댓글/본문 템플릿)
    REPLY_TEMPLATE = (
        "이 포스팅은 홍보 활동의\n"
        "일정액 수수료를 제공받습니다.\n"
        "=-=-=-=-=-=-=-=-=-=-=-=-=\n"
        "😆진짜 넘 좋다ㅋㅋ\n\n"
        "✅️안사도 되니까 한번 보구가~~\n"
        "🔻아래에서 제품명 자세히보기\n"
        "{s_url}\n{s_url}"
    )

# 레거시 코드 호환을 위한 최상위 변수 노출
GEMINI_API_KEY = GlobalConfig.GEMINI_API_KEY
MODEL_NAME = GlobalConfig.MODEL_NAME
EMBEDDING_MODEL = GlobalConfig.EMBEDDING_MODEL
MAX_WORKERS = GlobalConfig.MAX_WORKERS
STATIC_STRATEGIES = GlobalConfig.STATIC_STRATEGIES
BASE_PATH = str(GlobalConfig.BASE_DIR)

# 예시용 변수 (레거시 코드에서 직접 경로 참조 시 사용)
ORIGINAL_COPY = """셀프 네일 할땐 이만한게 없음☝️
이거하고 한바퀴만 돌려주면
심플하고 고급스럽게 완성됨💕"""
PRODUCT_FOCUS = "자석 네일 전용 회전 장치/키트"
