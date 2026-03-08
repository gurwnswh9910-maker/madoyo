"""
API 서버 전용 설정 모듈.
기존 app_config.py의 하드코딩 입력값(ORIGINAL_COPY, PRODUCT_FOCUS)을 제거하고,
API 요청에서 동적으로 받도록 전환합니다.
"""
import os
from dotenv import load_dotenv

# .env 파일 로드 (프로젝트 루트 또는 자동화 폴더)
# 여러 경로에서 .env를 탐색
_this_dir = os.path.dirname(os.path.abspath(__file__))
_code_dir = os.path.dirname(_this_dir)  # 작동중코드/
_project_root = os.path.dirname(_code_dir)  # madoyo/

for env_path in [
    os.path.join(_project_root, ".env"),
    os.path.join(_project_root, "자동화", ".env"),
    os.path.join(_code_dir, ".env"),
]:
    if os.path.exists(env_path):
        load_dotenv(env_path)
        break

# ════════════════════════════════════════════════════════════════
# API 및 시스템 설정
# ════════════════════════════════════════════════════════════════
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-3-flash-preview"
FALLBACK_MODEL_NAME = "gemini-2.5-flash"
EMBEDDING_MODEL = "gemini-embedding-001"

# 병렬 처리 워커 수
MAX_WORKERS = 25

# 데이터 경로 (프로젝트 루트 기준)
BASE_PATH = _project_root
STORAGE_PATH = os.path.join(BASE_PATH, "embeddings.pkl")
CACHE_PATH = os.path.join(BASE_PATH, "data_cache.pkl")

# 기존 app_config.py의 정적 전략 (카피 생성에 활용)
STATIC_STRATEGIES = [
    (
        "일상 속 비의도적 발견 (진성)",
        "전문가나 셀럽이 아닌 일상 속 인물(가족, 친구 등)의 비의도적인 감탄을 통해 가치를 증명하고, "
        "이모티콘을 활용해 진정성을 부여하세요.",
    ),
    (
        "제3자 검증 통한 우월감 (신뢰)",
        "엄마, 지인 등 제3자의 구체적 반응을 묘사하고, 그 가치가 왜 발생했는지 이유를 설명하여 "
        "똑똑한 소비를 했다는 지적 우월감을 자극하세요.",
    ),
    (
        "트렌드 비교를 통한 사유유도 (참여)",
        "대중에게 인지도가 높은 핫플이나 브랜드를 대조 비교하여 시선을 끈 뒤, "
        "개방형 질문을 던져 독자가 능동적으로 생각하게 유도하세요.",
    ),
]
