import os
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드 (현재 backend 폴더 기준)
BASE_DIR = Path(__file__).resolve().parent
env_path = BASE_DIR / '.env'
# 만약 backend/.env가 없으면 상위 폴더(루트) 체크
if not env_path.exists():
    env_path = BASE_DIR.parent / '.env'

if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

class GlobalConfig:
    """프로젝트 전체의 설정을 중앙 집중 관리하는 클래스"""
    
    # 1. 경로 설정 (pathlib 기반)
    BASE_DIR = BASE_DIR
    WORKING_CODE_DIR = BASE_DIR / "작동중코드"
    AUTOMATION_DIR = BASE_DIR / "자동화"
    
    # 데이터 관련
    STORAGE_PATH = WORKING_CODE_DIR / "embeddings_v2_final.pkl"
    CACHE_PATH = BASE_DIR / "data_cache.pkl"
    PROCESSED_LOG_PATH = AUTOMATION_DIR / "processed_links.log"
    MODEL_DIR = BASE_DIR / "embedding_migration"

    # 2. API 설정
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    THREADS_TOKEN = os.getenv("THREADS_ACCESS_TOKEN")
    THREADS_USER_ID = os.getenv("THREADS_USER_ID")
    MODEL_NAME = "gemini-3-flash-preview"
    EMBEDDING_MODEL = "models/gemini-embedding-2-preview"

    # 3. 성능 및 안정성 (마법의 숫자 제거)
    MAX_WORKERS = 25
    POST_INTERVAL = 15        # 포스팅 간 대기 시간 (초)
    FILE_API_POLL = 2         # Gemini File API 상태 체크 간격 (초)
    FILE_API_TIMEOUT = 60     # Gemini File API 처리 타임아웃 (초)
    SCRAPER_TIMEOUT = 10      # 스크래퍼 로딩 대기 시간 (초)
    
    # 4. 정적 전략 (고정 성공 공식)
    STATIC_STRATEGIES = [
        ('일상 속 비의도적 발견 (진성)', '전문가나 셀럽이 아닌 일상 속 인물(가족, 친구 등)의 비의도적인 감탄을 통해 가치를 증명하고, 이모티콘을 활용해 진정성을 부여하세요.'),
        ('제3자 검증 통한 우월감 (신뢰)', '엄마, 지인 등 제3자의 구체적 반응을 묘사하고, 그 가치가 왜 발생했는지 이유를 설명하여 똑똑한 소비를 했다는 지적 우월감을 자극하세요.'),
        ('트렌드 비교를 통한 사유유도 (참여)', '대중에게 인지도가 높은 핫플이나 브랜드를 대조 비교하여 시선을 끈 뒤, 개방형 질문을 던져 독자가 능동적으로 생각하게 유도하세요.'),
    ]

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
