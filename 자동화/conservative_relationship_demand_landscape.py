from __future__ import annotations

from pathlib import Path
import json
import re
import sys

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill


try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


RUN_DIR = Path(__file__).resolve().parent / "organizer_research_runs"
RAW_INPUT = RUN_DIR / "threads_organizer_ml_discovery_combined_20260514.xlsx"
OUTPUT_XLSX = RUN_DIR / "threads_conservative_relationship_demand_landscape_20260515.xlsx"
OUTPUT_JSONL = RUN_DIR / "threads_conservative_relationship_demand_landscape_20260515.jsonl"
OUTPUT_MD = RUN_DIR / "threads_demand_landscape_summary_20260515.md"


RELATION_TARGET_TERMS = [
    "커피챗",
    "밋업",
    "네트워킹",
    "소셜링",
    "독서모임",
    "책모임",
    "북클럽",
    "북토크",
    "영화모임",
    "영화",
    "대화",
    "친구",
    "관계",
    "취향",
    "담소",
    "교류",
    "연결",
    "동네",
    "느슨한 연대",
    "소규모",
    "모임",
]

TARGET_INTENT_TERMS = [
    "모집",
    "신청",
    "참여",
    "참가",
    "운영",
    "진행",
    "열어",
    "열고",
    "개최",
    "모실",
    "찾",
    "구합니다",
    "있을까",
    "오세요",
    "올래",
    "와볼래",
    "볼래",
    "함께",
    "같이",
    "모여",
    "댓글",
    "DM",
    "디엠",
    "문의",
    "프로필링크",
    "프로필 링크",
    "링크",
    "오픈채팅",
    "장소",
    "일시",
    "참가비",
    "선착순",
    "마감",
]

HOST_STRONG_TERMS = [
    "모집",
    "신청",
    "참여 방법",
    "참여할 사람",
    "참가비",
    "장소",
    "일시",
    "모임 일정",
    "운영",
    "기획",
    "진행",
    "열어",
    "열고",
    "개최",
    "만들었습니다",
    "만들어보려고",
    "모실",
    "멤버",
    "정원",
    "선착순",
    "오픈채팅",
    "프로필링크",
    "프로필 링크",
    "링크",
    "DM",
    "디엠",
    "문의",
    "오세요",
    "올래",
    "와볼래",
    "볼래",
]

LEARNING_EXCLUDE_TERMS = [
    "스터디",
    "강의",
    "클래스",
    "원데이클래스",
    "원데이 클래스",
    "수업",
    "워크숍",
    "세미나",
    "교육",
    "공부",
    "학습",
    "글쓰기",
    "합평",
    "작성 가이드",
    "자기계발",
    "강연",
    "공부법",
    "모각코",
    "코딩",
    "개발",
    "개발자",
    "AI",
    "에이전트",
    "OpenAI",
    "Codex",
    "오픈소스",
    "기술",
    "데이터",
    "자동화",
    "VPS",
    "모델",
    "미국주식",
    "주식",
    "투자",
    "재테크",
    "마케팅",
]

EXERCISE_EXCLUDE_TERMS = [
    "러닝",
    "러닝크루",
    "크루",
    "등산",
    "운동",
    "마라톤",
    "러너",
    "요가",
    "필라테스",
    "한강",
    "100대명산",
]

NOISE_TERMS = [
    "지원금",
    "장려금",
    "보험",
    "제조 대행",
    "ODM",
    "OEM",
    "스마트스토어",
    "판매",
    "쇼핑",
    "광고",
    "쿠폰",
    "할인",
    "채용",
    "구인",
    "알바",
    "릴스",
    "tiktok",
    "브랜드가 설계",
    "포카리스웨트",
    "젠틀몬스터",
    "이벤트 참여",
    "좋아요",
    "리포스트",
    "팔로우",
    "스하리",
    "쓰팔",
    "맞팔",
    "냉면",
    "맛집",
    "맥주",
    "출판사",
    "영풍문고",
    "베스트셀러",
    "팬 싸인회",
    "엠버서더",
    "특별 강연",
]

BOOK_RELATION_TERMS = ["독서모임", "책모임", "북클럽", "북토크", "독서", "책을 읽", "같이 읽", "함께 읽"]

DEMAND_CATEGORIES = {
    "관계형_책대화": ["독서모임", "책모임", "북클럽", "북토크", "독서", "책을 읽", "같이 읽", "함께 읽"],
    "관계형_네트워킹커피챗": ["커피챗", "네트워킹", "밋업", "소셜링", "교류", "연결"],
    "관계형_문화취향": ["영화모임", "영화", "전시", "전시회", "취향", "음악", "사진", "그림", "카페"],
    "관계형_일반친구동네": ["친구", "동네", "모임", "함께", "같이", "대화", "사람", "느슨한 연대"],
    "학습형_기술커리어": ["AI", "기술", "개발", "코딩", "모각코", "데이터", "오픈소스", "에이전트", "Codex", "커리어"],
    "학습형_스터디자기계발": ["스터디", "공부", "강의", "클래스", "원데이클래스", "수업", "자기계발", "글쓰기"],
    "활동형_운동": ["러닝", "러닝크루", "등산", "운동", "마라톤", "크루", "러너"],
    "운영형_커뮤니티빌딩": ["커뮤니티", "운영", "멤버", "오픈채팅", "디스코드", "정기", "기수"],
    "상업형_강의클래스": ["유료", "참가비", "모임비", "비용", "만원", "강의", "클래스", "원데이클래스", "대여비"],
    "노이즈_상업정보": NOISE_TERMS,
}

WILLINGNESS_TERMS = [
    "유료",
    "참가비",
    "모임비",
    "회비",
    "비용",
    "대여비",
    "무료 원데이",
    "원데이클래스",
    "강의",
    "클래스",
    "신청",
    "마감",
    "선착순",
    "정원",
    "만원",
    "원!",
]

PAIN_TERMS = {
    "사람찾기": ["찾", "있을까", "구합니다", "손", "같이", "함께", "올래", "볼래", "오세요", "모실"],
    "모집난": ["참여자가 1명", "난항", "안보", "안 보여", "노쇼", "마감", "모집에", "어려"],
    "느슨함/내향": ["느슨", "내향", "조용", "소규모", "편하게", "친목 이런거 없이", "집순이", "집돌이"],
    "운영/지속": ["운영", "정기", "기수", "멤버", "오픈채팅", "리더", "유지중", "계속"],
    "결제/가격": ["참가비", "모임비", "비용", "회비", "만원", "유료", "무료"],
}


def clean(value: object) -> str:
    text = " ".join(str(value or "").split())
    return "" if text.lower() == "nan" else text


def lower_contains(text: str, terms: list[str]) -> list[str]:
    low = text.lower()
    return [term for term in terms if term.lower() in low]


def context_text(row: pd.Series) -> str:
    parts = []
    for col in ["검색어", "본문", "본문요약", "모집히트", "모임히트"]:
        if col in row.index:
            parts.append(clean(row.get(col)))
    return " ".join(p for p in parts if p)


def summarize(value: object, limit: int = 180) -> str:
    text = clean(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def classify_strict_target(row: pd.Series) -> dict:
    text = context_text(row)
    relation_hits = lower_contains(text, RELATION_TARGET_TERMS)
    intent_hits = lower_contains(text, TARGET_INTENT_TERMS)
    host_hits = lower_contains(text, HOST_STRONG_TERMS)
    learning_hits = lower_contains(text, LEARNING_EXCLUDE_TERMS)
    exercise_hits = lower_contains(text, EXERCISE_EXCLUDE_TERMS)
    noise_hits = lower_contains(text, NOISE_TERMS)
    book_hits = lower_contains(text, BOOK_RELATION_TERMS)

    has_relation = bool(relation_hits)
    has_intent = bool(intent_hits)
    has_host = bool(host_hits)
    has_learning = bool(learning_hits)
    has_exercise = bool(exercise_hits)
    has_noise = bool(noise_hits)

    # Books are relationship by default unless explicit class/study/tech/exercise dominates.
    explicit_non_relation = bool(
        has_exercise
        or lower_contains(text, ["AI", "에이전트", "개발", "코딩", "모각코", "기술"])
        or lower_contains(text, ["스터디", "강의", "클래스", "원데이클래스", "원데이 클래스", "수업", "세미나"])
    )
    coffee_or_meetup = bool(lower_contains(text, ["커피챗", "밋업", "네트워킹", "소셜링"]))

    soft_social_only = bool(lower_contains(text, ["스하리", "소통할 사람", "소통하쟈", "친해질 친구"]) and not has_host)
    food_or_generic = bool(lower_contains(text, ["냉면", "맛집", "맥주"]) and not has_host)

    if has_noise or soft_social_only or food_or_generic:
        label = "제외_잡음"
    elif explicit_non_relation:
        label = "제외_학습활동"
    elif has_relation and has_host and not has_learning and not has_exercise:
        label = "관계지향_확정"
    elif book_hits and has_host and not explicit_non_relation:
        label = "관계지향_확정"
    elif coffee_or_meetup and has_intent and not explicit_non_relation and (has_host or lower_contains(text, ["찾", "있을까", "함께", "같이"])):
        label = "관계지향_확정"
    elif has_relation and has_intent:
        label = "제외_애매"
    elif has_relation:
        label = "제외_관계신호약함"
    else:
        label = "제외_비관계"

    target = label == "관계지향_확정"
    return {
        "보수관계타깃": target,
        "보수관계판정": label,
        "관계히트_보수": ", ".join(dict.fromkeys(relation_hits + book_hits)),
        "의도히트_보수": ", ".join(intent_hits),
        "개설히트_보수": ", ".join(host_hits),
        "학습제외히트": ", ".join(learning_hits),
        "활동제외히트": ", ".join(exercise_hits),
        "잡음히트_보수": ", ".join(noise_hits),
    }


def categorize_demand(row: pd.Series) -> dict:
    text = context_text(row)
    category_hits = {}
    for category, terms in DEMAND_CATEGORIES.items():
        found = lower_contains(text, terms)
        category_hits[category] = found

    if category_hits["노이즈_상업정보"]:
        primary = "노이즈_상업정보"
    elif category_hits["학습형_기술커리어"]:
        primary = "학습형_기술커리어"
    elif category_hits["활동형_운동"]:
        primary = "활동형_운동"
    elif category_hits["관계형_책대화"]:
        primary = "관계형_책대화"
    elif category_hits["관계형_네트워킹커피챗"]:
        primary = "관계형_네트워킹커피챗"
    elif category_hits["관계형_문화취향"]:
        primary = "관계형_문화취향"
    elif category_hits["학습형_스터디자기계발"]:
        primary = "학습형_스터디자기계발"
    elif category_hits["운영형_커뮤니티빌딩"]:
        primary = "운영형_커뮤니티빌딩"
    elif category_hits["관계형_일반친구동네"]:
        primary = "관계형_일반친구동네"
    elif category_hits["상업형_강의클래스"]:
        primary = "상업형_강의클래스"
    else:
        primary = "미분류"

    willingness_hits = lower_contains(text, WILLINGNESS_TERMS)
    prices = re.findall(r"\d+\s*(?:만\s*)?원|\d+\s*만원|\d+\s*천원", text)
    pain_hits = {name: lower_contains(text, terms) for name, terms in PAIN_TERMS.items()}
    pain_labels = [name for name, found in pain_hits.items() if found]

    return {
        "수요대분류": primary,
        "수요카테고리히트": json.dumps({k: v for k, v in category_hits.items() if v}, ensure_ascii=False),
        "지불의향히트": ", ".join(willingness_hits),
        "가격표현": ", ".join(prices),
        "수요통증라벨": ", ".join(pain_labels),
        "수요통증히트": json.dumps({k: v for k, v in pain_hits.items() if v}, ensure_ascii=False),
        "지불의향신호": bool(willingness_hits or prices),
    }


def add_labels(raw: pd.DataFrame) -> pd.DataFrame:
    out = raw.copy()
    conservative = out.apply(classify_strict_target, axis=1, result_type="expand")
    demand = out.apply(categorize_demand, axis=1, result_type="expand")
    out = pd.concat([conservative, demand, out], axis=1)
    out["본문요약_분석"] = out["본문"].map(lambda v: summarize(v, 220))
    return out


def summarize_by_category(df: pd.DataFrame, scope: str) -> pd.DataFrame:
    rows = []
    for category, group in df.groupby("수요대분류", dropna=False):
        if not category or category == "nan":
            continue
        engagement = pd.to_numeric(group["반응합계"], errors="coerce").fillna(0)
        rows.append(
            {
                "범위": scope,
                "수요대분류": category,
                "글수": len(group),
                "작성자수": group["작성자"].nunique(),
                "지불의향글수": int(group["지불의향신호"].sum()),
                "평균반응합계": round(float(engagement.mean()), 1) if len(group) else 0,
                "중앙반응합계": round(float(engagement.median()), 1) if len(group) else 0,
                "최대반응합계": int(engagement.max()) if len(group) else 0,
                "주요키워드": ", ".join(group["검색어"].value_counts().head(8).index.astype(str)),
                "대표통증": ", ".join(group["수요통증라벨"].dropna().astype(str).str.split(", ").explode().value_counts().head(5).index),
                "대표근거": " / ".join(group.sort_values("반응합계", ascending=False)["본문요약_분석"].head(3).tolist()),
            }
        )
    return pd.DataFrame(rows).sort_values(["글수", "지불의향글수", "평균반응합계"], ascending=False)


def payment_signals(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "검색어",
        "수요대분류",
        "작성자",
        "게시글링크",
        "반응합계",
        "지불의향히트",
        "가격표현",
        "수요통증라벨",
        "본문요약_분석",
    ]
    picked = df[df["지불의향신호"]].copy()
    return picked.sort_values(["반응합계"], ascending=False)[cols]


def evidence_samples(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for category, group in df.groupby("수요대분류", dropna=False):
        sample = group.sort_values(["지불의향신호", "반응합계"], ascending=False).head(8)
        for _, row in sample.iterrows():
            rows.append(
                {
                    "수요대분류": category,
                    "검색어": row.get("검색어"),
                    "작성자": row.get("작성자"),
                    "반응합계": row.get("반응합계"),
                    "지불의향신호": row.get("지불의향신호"),
                    "수요통증라벨": row.get("수요통증라벨"),
                    "본문요약": row.get("본문요약_분석"),
                    "게시글링크": row.get("게시글링크"),
                }
            )
    return pd.DataFrame(rows)


def write_markdown(quality: pd.DataFrame, non_target_summary: pd.DataFrame, target_count: int, payment: pd.DataFrame) -> None:
    top = non_target_summary.head(8)
    lines = [
        "# Threads raw demand landscape - 2026-05-15",
        "",
        "## 라벨 정책 반영",
        "- 애매하면 채택하지 않고 제외한다.",
        "- 커피챗/밋업/네트워킹/소셜링은 다른 사람을 찾는 의도와 관계 지향성이 보이면 관계 타깃으로 살린다.",
        "- 기술/스터디/운동/강의/클래스는 만남 단어가 있어도 학습/활동 수요로 분리한다.",
        f"- 보수 관계 타깃 확정 글수: {target_count}",
        "",
        "## 타깃 제외 raw에서 보이는 수요 지형",
    ]
    for _, row in top.iterrows():
        lines.append(
            f"- {row['수요대분류']}: 글 {row['글수']}개, 작성자 {row['작성자수']}명, "
            f"지불의향 {row['지불의향글수']}개, 주요 키워드 {row['주요키워드']}"
        )
    lines.extend(
        [
            "",
            "## 지불의향 신호",
            f"- 지불의향 신호가 있는 비타깃 raw 글수: {len(payment)}",
            "- 강한 신호는 참가비/모임비/만원/유료/클래스/강의/선착순/마감/정원이다.",
            "",
            "## 해석",
            "- 관계 지향 자체는 책/영화/밋업/네트워킹/소셜링에서 잘 보인다.",
            "- 비타깃에서는 학습/기술/운동/클래스 수요가 많이 섞이며, 이들은 결제 신호는 강하지만 현재 제품의 관계형 타깃과는 다른 시장이다.",
            "- 사람들이 원하는 것은 단순 채팅보다 주제, 장소, 정원, 진행자, 비용이 명확한 작고 안전한 모임이다.",
        ]
    )
    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")


def format_workbook(path: Path) -> None:
    wb = load_workbook(path)
    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)
    widths = {
        "policy_notes": {"A": 28, "B": 110},
        "quality_summary": {"A": 32, "B": 90},
        "demand_clean_non_target": {"A": 16, "B": 26, "I": 50, "J": 38, "K": 120},
        "demand_non_target_summary": {"A": 16, "B": 26, "I": 50, "J": 38, "K": 120},
        "demand_all_raw_summary": {"A": 16, "B": 26, "I": 50, "J": 38, "K": 120},
        "strict_relationship_targets": {"A": 16, "B": 18, "C": 28, "D": 38, "E": 38, "Q": 90},
        "non_target_payment_signals": {"A": 18, "B": 26, "C": 24, "D": 50, "I": 110},
        "non_target_evidence": {"A": 26, "F": 30, "G": 110, "H": 50},
        "raw_labeled_conservative": {"A": 16, "B": 18, "C": 28, "D": 38, "E": 38, "Q": 90},
    }
    for ws in wb.worksheets:
        ws.freeze_panes = "A2"
        if ws.max_row and ws.max_column:
            ws.auto_filter.ref = ws.dimensions
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
        for col, width in widths.get(ws.title, {}).items():
            ws.column_dimensions[col].width = width
    wb.save(path)


def main() -> None:
    raw = pd.read_excel(RAW_INPUT, sheet_name="discovery_posts_raw")
    labeled = add_labels(raw)
    strict_targets = labeled[labeled["보수관계타깃"]].copy()
    non_target = labeled[~labeled["보수관계타깃"]].copy()
    non_target_clean = non_target[non_target["수요대분류"].ne("노이즈_상업정보")].copy()
    ambiguous = labeled[labeled["보수관계판정"].str.contains("애매|약함", na=False)].copy()

    all_summary = summarize_by_category(labeled, "전체raw")
    non_target_summary = summarize_by_category(non_target, "보수타깃제외")
    clean_non_target_summary = summarize_by_category(non_target_clean, "보수타깃제외_노이즈제거")
    pay = payment_signals(non_target_clean)
    evidence = evidence_samples(non_target_clean)

    quality = pd.DataFrame(
        [
            {"항목": "input_raw", "값": str(RAW_INPUT)},
            {"항목": "output_excel", "값": str(OUTPUT_XLSX)},
            {"항목": "output_jsonl", "값": str(OUTPUT_JSONL)},
            {"항목": "output_md", "값": str(OUTPUT_MD)},
            {"항목": "raw_rows", "값": len(labeled)},
            {"항목": "strict_relationship_targets", "값": len(strict_targets)},
            {"항목": "non_target_rows", "값": len(non_target)},
            {"항목": "non_target_clean_rows", "값": len(non_target_clean)},
            {"항목": "discarded_ambiguous_or_weak", "값": len(ambiguous)},
            {"항목": "non_target_payment_signals", "값": len(pay)},
        ]
    )
    policy = pd.DataFrame(
        [
            {"항목": "정책", "값": "애매하면 채택하지 않고 제외한다. 애매한 케이스는 관계 타깃에 넣지 않는다."},
            {"항목": "살리는 신호", "값": "커피챗, 밋업, 네트워킹, 소셜링, 북클럽, 영화모임 등 다른 사람을 찾고 관계를 지향하는 명확한 모임"},
            {"항목": "제외 신호", "값": "기술/스터디/운동/강의/클래스/상업/정보성/광고성 문맥"},
            {"항목": "분석 범위", "값": "demand_clean_non_target_summary는 우리가 향하는 보수 관계 타깃과 명백한 광고/정보 노이즈를 제외한 raw 수요 지형"},
        ]
    )

    with OUTPUT_JSONL.open("w", encoding="utf-8") as handle:
        for row in strict_targets.to_dict(orient="records"):
            handle.write(json.dumps({"level": "strict_relationship_target", **row}, ensure_ascii=False, default=str) + "\n")
        for row in non_target_summary.to_dict(orient="records"):
            handle.write(json.dumps({"level": "non_target_demand_summary", **row}, ensure_ascii=False, default=str) + "\n")

    with pd.ExcelWriter(OUTPUT_XLSX, engine="openpyxl") as writer:
        policy.to_excel(writer, sheet_name="policy_notes", index=False)
        quality.to_excel(writer, sheet_name="quality_summary", index=False)
        clean_non_target_summary.to_excel(writer, sheet_name="demand_clean_non_target", index=False)
        non_target_summary.to_excel(writer, sheet_name="demand_non_target_summary", index=False)
        all_summary.to_excel(writer, sheet_name="demand_all_raw_summary", index=False)
        strict_targets.to_excel(writer, sheet_name="strict_relationship_targets", index=False)
        ambiguous.to_excel(writer, sheet_name="discarded_ambiguous", index=False)
        pay.to_excel(writer, sheet_name="non_target_payment_signals", index=False)
        evidence.to_excel(writer, sheet_name="non_target_evidence", index=False)
        labeled.to_excel(writer, sheet_name="raw_labeled_conservative", index=False)

    format_workbook(OUTPUT_XLSX)
    write_markdown(quality, clean_non_target_summary, len(strict_targets), pay)

    print(f"output_excel={OUTPUT_XLSX}")
    print(f"output_jsonl={OUTPUT_JSONL}")
    print(f"output_md={OUTPUT_MD}")
    print("\nquality_summary")
    print(quality.to_string(index=False))
    print("\ndemand_non_target_summary")
    print(clean_non_target_summary.to_string(index=False))
    print("\nstrict_relationship_targets sample")
    cols = ["검색어", "작성자", "반응합계", "보수관계판정", "수요대분류", "본문요약_분석"]
    print(strict_targets[cols].head(30).to_string(index=False))


if __name__ == "__main__":
    main()
