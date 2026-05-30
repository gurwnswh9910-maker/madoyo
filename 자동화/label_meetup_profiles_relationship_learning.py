from __future__ import annotations

from pathlib import Path
import json
import sys

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill


try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


RUN_DIR = Path(__file__).resolve().parent / "organizer_research_runs"
PROFILE_INPUT = RUN_DIR / "threads_meetup_profiles_only_20260515.xlsx"
RAW_INPUT = RUN_DIR / "threads_organizer_ml_discovery_combined_20260514.xlsx"
OUTPUT_XLSX = RUN_DIR / "threads_meetup_profiles_relationship_labeled_20260515.xlsx"
OUTPUT_JSONL = RUN_DIR / "threads_meetup_profiles_relationship_labeled_20260515.jsonl"


BOOK_RELATION_TERMS = [
    "독서모임",
    "책모임",
    "북클럽",
    "북토크",
    "책",
    "독서",
    "리딩",
    "읽고",
    "읽는",
    "문장",
    "필사",
]

RELATION_TERMS = [
    "네트워킹",
    "소셜링",
    "커뮤니티",
    "친구",
    "관계",
    "대화",
    "함께",
    "같이",
    "모여",
    "느슨한 연대",
    "인사이트를 나눕",
    "사람들과",
    "연결",
    "교류",
    "동네",
    "취향",
    "영화모임",
    "영화",
    "취미모임",
    "모임",
]

STUDY_TERMS = [
    "스터디",
    "학습",
    "공부",
    "강의",
    "클래스",
    "원데이클래스",
    "수업",
    "워크숍",
    "세미나",
    "교육",
    "코스",
    "커리큘럼",
    "진입장벽",
    "마스터",
]

TECH_TERMS = [
    "기술",
    "AI",
    "에이전트",
    "Codex",
    "OpenAI",
    "Hermes",
    "개발",
    "프로그래밍",
    "코딩",
    "데이터",
    "개발자",
    "모의해킹",
    "IT",
    "VPS",
    "모델",
    "자동화",
    "오픈소스",
    "소프트웨어",
    "앱",
    "쿠팡 강의",
]

EXERCISE_TERMS = [
    "운동",
    "러닝",
    "러너",
    "달리기",
    "마라톤",
    "크루",
    "러닝크루",
    "등산",
    "한강",
    "배곧",
    "시흥",
    "요가",
    "필라테스",
]

LEARNING_CONTEXT_TERMS = STUDY_TERMS + TECH_TERMS + EXERCISE_TERMS

WEAK_LEARNING_TERMS = [
    "글쓰기모임",
    "글쓰기 모임",
    "글쓰기",
    "합평",
    "작성 가이드",
]


def clean(value: object) -> str:
    text = " ".join(str(value or "").split())
    return "" if text.lower() == "nan" else text


def hits(text: str, terms: list[str]) -> list[str]:
    low = text.lower()
    return [term for term in terms if term.lower() in low]


def join_context(row: pd.Series) -> str:
    parts = []
    for col in [
        "검색어",
        "검색어목록",
        "모임근거",
        "행동근거",
        "대표근거",
        "근거요약",
        "본문",
        "본문요약",
        "core_hits",
        "context_hits",
        "strong_host_hits",
        "invite_hits",
        "host_claim_hits",
    ]:
        if col in row.index:
            parts.append(clean(row.get(col)))
    return " ".join(p for p in parts if p)


def label_context(text: str) -> dict:
    book_hits = hits(text, BOOK_RELATION_TERMS)
    relation_hits = hits(text, RELATION_TERMS)
    study_hits = hits(text, STUDY_TERMS)
    tech_hits = hits(text, TECH_TERMS)
    exercise_hits = hits(text, EXERCISE_TERMS)
    weak_learning_hits = hits(text, WEAK_LEARNING_TERMS)

    learning_hits = []
    for chunk in [study_hits, tech_hits, exercise_hits]:
        for hit in chunk:
            if hit not in learning_hits:
                learning_hits.append(hit)

    # User rule: reading together is relationship even if the book topic is business/finance.
    # Explicit tech/study/exercise still overrides generic meetup wording.
    if book_hits and not tech_hits and not exercise_hits and not any(
        hit in study_hits for hit in ["스터디", "학습", "강의", "클래스", "원데이클래스", "수업", "워크숍", "세미나", "교육", "코스", "커리큘럼"]
    ):
        label = "관계"
        reason = "같이 책을 읽고 대화/교류하는 모임"
        confidence = "high"
    elif tech_hits:
        label = "학습"
        reason = "기술/AI/개발 등 지식 학습 맥락"
        confidence = "high"
    elif exercise_hits:
        label = "학습"
        reason = "운동/러닝/등산 등 활동 학습/실행 맥락"
        confidence = "high"
    elif study_hits and not book_hits:
        label = "학습"
        reason = "스터디/강의/클래스/공부 맥락"
        confidence = "high"
    elif study_hits and book_hits and any(hit in study_hits for hit in ["스터디", "학습", "공부", "강의", "클래스", "원데이클래스"]):
        label = "학습"
        reason = "책 모임보다 스터디/클래스 성격이 우세"
        confidence = "medium"
    elif book_hits:
        label = "관계"
        reason = "같이 책을 읽고 대화/교류하는 모임"
        confidence = "high"
    elif relation_hits:
        label = "관계"
        reason = "네트워킹/소셜링/대화/취향 공유 등 관계 지향"
        confidence = "high"
    elif weak_learning_hits:
        label = "학습"
        reason = "글쓰기/합평 등 산출물 기반 스터디 성격"
        confidence = "medium"
    else:
        label = "검토"
        reason = "관계/학습 목적 신호가 약함"
        confidence = "low"

    return {
        "목적라벨": label,
        "관계라벨": label == "관계",
        "학습라벨": label == "학습",
        "라벨신뢰도": confidence,
        "라벨근거": reason,
        "학습히트": ", ".join(learning_hits),
        "관계히트": ", ".join(dict.fromkeys(book_hits + relation_hits)),
        "약한학습히트": ", ".join(weak_learning_hits),
    }


def add_labels(df: pd.DataFrame, id_prefix: str) -> pd.DataFrame:
    out = df.copy()
    labels = []
    for _, row in out.iterrows():
        labels.append(label_context(join_context(row)))
    label_df = pd.DataFrame(labels)
    out.insert(0, "q_id", [f"{id_prefix}{i:03d}" for i in range(1, len(out) + 1)])
    insert_at = 1
    for col in label_df.columns:
        out.insert(insert_at, col, label_df[col].values)
        insert_at += 1
    return out


def add_profile_level_labels(profile_df: pd.DataFrame, evidence_labeled: pd.DataFrame) -> pd.DataFrame:
    out = add_labels(profile_df, "p")
    if "작성자" not in out.columns or evidence_labeled.empty:
        return out

    evidence_counts = (
        evidence_labeled.groupby("작성자")["목적라벨"]
        .value_counts()
        .unstack(fill_value=0)
        .reset_index()
    )
    for label in ["관계", "학습", "검토"]:
        if label not in evidence_counts.columns:
            evidence_counts[label] = 0
    evidence_counts["근거글_관계수"] = evidence_counts["관계"]
    evidence_counts["근거글_학습수"] = evidence_counts["학습"]
    evidence_counts["근거글_검토수"] = evidence_counts["검토"]
    evidence_counts["근거기반_목적라벨"] = evidence_counts.apply(
        lambda r: "관계"
        if r["근거글_관계수"] > r["근거글_학습수"]
        else ("학습" if r["근거글_학습수"] > r["근거글_관계수"] else "검토"),
        axis=1,
    )

    merged = out.merge(
        evidence_counts[["작성자", "근거글_관계수", "근거글_학습수", "근거글_검토수", "근거기반_목적라벨"]],
        on="작성자",
        how="left",
    )
    for col in ["근거글_관계수", "근거글_학습수", "근거글_검토수"]:
        merged[col] = merged[col].fillna(0).astype(int)

    # Evidence-level labels override ambiguous profile text, but do not erase the raw/profile label.
    merged["최종목적라벨"] = merged["근거기반_목적라벨"].where(
        merged["근거기반_목적라벨"].isin(["관계", "학습"]), merged["목적라벨"]
    )
    merged["최종관계라벨"] = merged["최종목적라벨"].eq("관계")
    return merged


def format_workbook(path: Path) -> None:
    wb = load_workbook(path)
    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)
    widths = {
        "quality_summary": {"A": 28, "B": 90},
        "relationship_profiles": {"A": 12, "B": 14, "J": 24, "K": 38, "V": 90, "W": 90},
        "learning_profiles": {"A": 12, "B": 14, "J": 24, "K": 38, "V": 90, "W": 90},
        "profiles_labeled": {"A": 12, "B": 14, "J": 24, "K": 38, "V": 90, "W": 90},
        "evidence_posts_labeled": {"A": 12, "B": 14, "D": 24, "E": 38, "G": 90},
        "raw_posts_labeled": {"A": 12, "B": 14, "D": 18, "E": 24, "I": 90},
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
    profile_sheets = pd.read_excel(PROFILE_INPUT, sheet_name=None)
    raw_sheets = pd.read_excel(RAW_INPUT, sheet_name=None)

    evidence_labeled = add_labels(profile_sheets["evidence_posts"], "q")
    raw_labeled = add_labels(raw_sheets["discovery_posts_raw"], "r")
    profiles_labeled = add_profile_level_labels(profile_sheets["profile_only"], evidence_labeled)
    organizer_labeled = add_profile_level_labels(profile_sheets["organizer_priority"], evidence_labeled)
    review_labeled = add_profile_level_labels(profile_sheets["active_member_or_review"], evidence_labeled)
    excluded_labeled = add_labels(profile_sheets["excluded_review"], "x")

    relationship_profiles = profiles_labeled[profiles_labeled["최종목적라벨"].eq("관계")].copy()
    learning_profiles = profiles_labeled[profiles_labeled["최종목적라벨"].eq("학습")].copy()
    relationship_raw = raw_labeled[raw_labeled["목적라벨"].eq("관계")].copy()

    quality = pd.DataFrame(
        [
            {"항목": "profile_input", "값": str(PROFILE_INPUT)},
            {"항목": "raw_input", "값": str(RAW_INPUT)},
            {"항목": "output_excel", "값": str(OUTPUT_XLSX)},
            {"항목": "output_jsonl", "값": str(OUTPUT_JSONL)},
            {"항목": "profiles_total", "값": len(profiles_labeled)},
            {"항목": "relationship_profiles", "값": len(relationship_profiles)},
            {"항목": "learning_profiles", "값": len(learning_profiles)},
            {"항목": "evidence_posts_total", "값": len(evidence_labeled)},
            {"항목": "evidence_relationship", "값": int(evidence_labeled["목적라벨"].eq("관계").sum())},
            {"항목": "evidence_learning", "값": int(evidence_labeled["목적라벨"].eq("학습").sum())},
            {"항목": "raw_posts_total", "값": len(raw_labeled)},
            {"항목": "raw_relationship", "값": len(relationship_raw)},
            {
                "항목": "라벨 기준",
                "값": "기술/스터디/운동은 학습, 책/네트워킹/소셜링/대화/취향 공유는 관계. 원본 raw는 유지하고 라벨 컬럼만 추가.",
            },
        ]
    )

    with OUTPUT_JSONL.open("w", encoding="utf-8") as handle:
        for row in profiles_labeled.to_dict(orient="records"):
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    with pd.ExcelWriter(OUTPUT_XLSX, engine="openpyxl") as writer:
        quality.to_excel(writer, sheet_name="quality_summary", index=False)
        relationship_profiles.to_excel(writer, sheet_name="relationship_profiles", index=False)
        learning_profiles.to_excel(writer, sheet_name="learning_profiles", index=False)
        profiles_labeled.to_excel(writer, sheet_name="profiles_labeled", index=False)
        organizer_labeled.to_excel(writer, sheet_name="organizer_priority_labeled", index=False)
        review_labeled.to_excel(writer, sheet_name="review_profiles_labeled", index=False)
        evidence_labeled.to_excel(writer, sheet_name="evidence_posts_labeled", index=False)
        relationship_raw.to_excel(writer, sheet_name="relationship_raw_posts", index=False)
        raw_labeled.to_excel(writer, sheet_name="raw_posts_labeled", index=False)
        excluded_labeled.to_excel(writer, sheet_name="excluded_review_labeled", index=False)

    format_workbook(OUTPUT_XLSX)

    print(f"output_excel={OUTPUT_XLSX}")
    print(f"output_jsonl={OUTPUT_JSONL}")
    print("\nquality_summary")
    print(quality.to_string(index=False))
    print("\nrelationship_profiles")
    print(
        relationship_profiles[
            ["q_id", "작성자", "profile_url", "최종목적라벨", "검색어목록", "대표근거"]
        ]
        .head(40)
        .to_string(index=False)
    )
    print("\nlearning_profiles")
    print(
        learning_profiles[
            ["q_id", "작성자", "profile_url", "최종목적라벨", "검색어목록", "대표근거"]
        ]
        .head(40)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
