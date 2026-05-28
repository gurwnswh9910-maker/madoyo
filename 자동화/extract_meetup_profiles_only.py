from __future__ import annotations

from pathlib import Path
import json
import math
import sys

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill


try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


RUN_DIR = Path(__file__).resolve().parent / "organizer_research_runs"
INPUT_XLSX = RUN_DIR / "threads_organizer_ml_discovery_combined_20260514.xlsx"
OUTPUT_XLSX = RUN_DIR / "threads_meetup_profiles_only_20260515.xlsx"
OUTPUT_JSONL = RUN_DIR / "threads_meetup_profiles_only_20260515.jsonl"


MEETUP_CORE_TERMS = [
    "모임",
    "북클럽",
    "책모임",
    "독서모임",
    "글쓰기모임",
    "글쓰기 모임",
    "스터디모임",
    "스터디 모임",
    "러닝모임",
    "러닝 모임",
    "러닝크루",
    "러닝 크루",
    "등산모임",
    "등산 모임",
    "운동모임",
    "운동 모임",
    "취미모임",
    "취미 모임",
    "보드게임",
    "영화모임",
    "영화 모임",
    "커피챗",
    "밋업",
    "소셜링",
    "원데이클래스",
    "원데이 클래스",
    "북토크",
    "살롱",
    "코워킹",
]

CONTEXT_MEETUP_TERMS = [
    "커뮤니티",
    "네트워킹",
    "영화",
    "전시",
    "전시회",
    "와인",
]

HOST_TERMS = [
    "운영",
    "모집",
    "신청",
    "참여",
    "참가",
    "진행",
    "열어",
    "열립",
    "개최",
    "주최",
    "멤버",
    "정원",
    "선착순",
    "마감",
    "오픈채팅",
    "모실",
    "구합니다",
    "찾습니다",
    "함께",
    "같이",
    "모여",
    "볼래",
    "올래",
    "와볼래",
    "관심",
    "댓글",
    "DM",
    "디엠",
    "프로필",
    "링크",
    "개설",
    "초대",
    "게스트",
    "오세요",
    "만들었습니다",
    "만들어보려고",
    "홍보",
    "프리뷰",
]

STRONG_HOST_TERMS = [
    "운영",
    "모집",
    "신청",
    "진행",
    "열어",
    "열립",
    "개최",
    "주최",
    "정원",
    "선착순",
    "마감",
    "오픈채팅",
    "개설",
    "홍보",
    "멤버",
    "모실",
    "와볼래",
    "올래",
]

BAD_TERMS = [
    "지원금",
    "장려금",
    "자격증취득",
    "문화누리카드",
    "뉴스, 메신저",
    "쇼핑",
    "광고",
    "포카리스웨트",
    "젠틀몬스터",
    "링크드인",
    "포브스",
    "두바이 정부",
    "특별 강연",
    "과학고",
    "해군",
    "게임 개발",
    "입학",
    "채용",
    "구인",
    "알바",
    "공구",
    "팔아요",
    "판매",
    "쿠폰",
    "할인",
    "릴스",
    "tiktok",
    "보험설계사",
    "보험대리점",
    "손해사정사",
    "약관",
    "조직검사",
    "제조 대행",
    "ODM",
    "OEM",
    "스마트스토어",
    "스토어",
    "상품",
    "공장",
    "매출",
    "오픈채팅 자동화",
    "자동 메시지",
    "정보성 블로그",
    "명함",
    "포트폴리오 QR",
    "브랜드가 설계",
    "외주",
    "대행",
    "재계약",
    "이벤트",
    "아디다스",
    "가민",
    "실패하는 이유",
    "망하는 패턴",
    "설계를 안",
    "브랜드",
    "TOP ",
]

INVITE_TERMS = [
    "모집",
    "신청",
    "장소",
    "일시",
    "정원",
    "참가비",
    "선착순",
    "마감",
    "오세요",
    "올래",
    "와볼래",
    "프로필링크",
    "프로필 링크",
    "오픈채팅방 링크",
    "링크 보내",
    "2명정도",
    "모실",
]

HOST_CLAIM_TERMS = [
    "운영자",
    "운영되는",
    "운영하는",
    "기획하고 운영",
    "리더",
    "만들었습니다",
    "만들어보려고",
    "진행해볼까",
    "준비한 공간",
]

SEEKER_TERMS = [
    "들어가고 싶은",
    "있을까요",
    "찾고 있는",
    "찾는 사람",
    "해보고 싶은",
    "하고 싶은",
    "참여할 곳",
]

ATTENDEE_TERMS = [
    "다녀왔",
    "참여하고 있는",
    "참여했",
    "하고 있는",
    "하는 사람",
]


def clean_text(value: object) -> str:
    text = " ".join(str(value or "").split())
    return "" if text.lower() == "nan" else text


def hits(text: str, terms: list[str]) -> list[str]:
    low = text.lower()
    return [term for term in terms if term.lower() in low]


def summarize(value: object, limit: int = 160) -> str:
    text = clean_text(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def profile_url(handle: str) -> str:
    return f"https://www.threads.com/{handle}" if str(handle).startswith("@") else ""


def classify_post(row: pd.Series) -> dict:
    body = clean_text(row.get("본문"))
    keyword = clean_text(row.get("검색어"))
    core_hits = hits(body, MEETUP_CORE_TERMS)
    context_hits = hits(body, CONTEXT_MEETUP_TERMS)
    host_hits = hits(body, HOST_TERMS)
    strong_hits = hits(body, STRONG_HOST_TERMS)
    bad_hits = hits(body, BAD_TERMS)
    invite_hits = hits(body, INVITE_TERMS)
    hard_invite_hits = [hit for hit in invite_hits if hit not in ["모집", "멤버"]]
    host_claim_hits = hits(body, HOST_CLAIM_TERMS)
    seeker_hits = hits(body, SEEKER_TERMS)
    attendee_hits = hits(body, ATTENDEE_TERMS)

    # Context-only terms like "영화", "전시", "커뮤니티" need explicit meetup behavior in the body.
    social_action_context = any(
        t in body
        for t in [
            "함께",
            "같이",
            "모여",
            "볼래",
            "오세요",
            "신청",
            "모집",
            "참여",
            "참가",
            "멤버",
            "일시",
            "장소",
            "참가비",
            "정기",
            "오프라인",
            "코워킹",
        ]
    )
    context_is_meetup = bool(context_hits and host_hits and social_action_context)
    is_meetup = bool(core_hits or context_is_meetup)
    is_advice_only = bool(bad_hits and not invite_hits and not host_claim_hits)
    is_seeker_only = bool(seeker_hits and not hard_invite_hits and not host_claim_hits)
    is_attendee_only = bool(attendee_hits and not invite_hits and not host_claim_hits)
    host_signal = bool(hard_invite_hits or host_claim_hits or (invite_hits and not seeker_hits))
    is_host = bool(is_meetup and host_signal and not is_advice_only and not is_seeker_only)
    is_member = bool(
        is_meetup
        and not is_host
        and (
            seeker_hits
            or attendee_hits
            or any(t in body for t in ["참여", "참가", "다니", "함께", "같이", "좋아"])
        )
        and not is_advice_only
    )

    score = 0
    score += min(8, len(core_hits) * 2)
    score += min(5, len(context_hits))
    score += min(12, len(strong_hits) * 3)
    score += min(6, len(host_hits))
    score += min(8, len(invite_hits) * 3)
    score += min(6, len(host_claim_hits) * 3)
    score += 4 if is_host else 0
    score += 2 if is_member else 0
    score -= 4 if is_seeker_only else 0
    score -= 4 if is_attendee_only else 0
    score += min(4, int(float(row.get("모집점수") or 0) // 4))
    score -= len(bad_hits) * 5
    if not is_meetup:
        score -= 8

    if is_advice_only:
        level = "exclude"
    elif is_seeker_only and score >= 10:
        level = "active_member"
    elif is_attendee_only and score >= 10:
        level = "active_member"
    elif bad_hits and not (is_host and core_hits):
        level = "exclude"
    elif bad_hits and score < 18:
        level = "exclude"
    elif is_host and score >= 18:
        level = "organizer_high"
    elif is_host and score >= 12:
        level = "organizer_medium"
    elif is_member and score >= 10:
        level = "active_member"
    elif is_meetup and score >= 9:
        level = "review"
    else:
        level = "exclude"

    return {
        "post_profile_level": level,
        "post_profile_score": score,
        "core_hits": ", ".join(core_hits),
        "context_hits": ", ".join(context_hits),
        "host_hits": ", ".join(host_hits),
        "strong_host_hits": ", ".join(strong_hits),
        "bad_hits": ", ".join(bad_hits),
        "invite_hits": ", ".join(invite_hits),
        "hard_invite_hits": ", ".join(hard_invite_hits),
        "host_claim_hits": ", ".join(host_claim_hits),
        "seeker_hits": ", ".join(seeker_hits),
        "attendee_hits": ", ".join(attendee_hits),
        "is_meetup": is_meetup,
        "is_host": is_host,
        "is_member": is_member,
    }


def join_unique(values: pd.Series, limit: int = 12) -> str:
    seen = []
    for value in values:
        text = clean_text(value)
        if not text:
            continue
        for part in [p.strip() for p in text.split(",")]:
            if part and part not in seen:
                seen.append(part)
    return ", ".join(seen[:limit])


def join_samples(values: pd.Series, limit: int = 3) -> str:
    clean = [summarize(v, 120) for v in values if clean_text(v)]
    return " / ".join(clean[:limit])


def best_url(group: pd.DataFrame) -> str:
    if group.empty:
        return ""
    row = group.sort_values(["post_profile_score", "반응합계"], ascending=False).iloc[0]
    return clean_text(row.get("게시글링크"))


def best_body(group: pd.DataFrame) -> str:
    if group.empty:
        return ""
    row = group.sort_values(["post_profile_score", "반응합계"], ascending=False).iloc[0]
    return summarize(row.get("본문"), 220)


def build_profiles(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    raw = raw.copy()
    classifications = raw.apply(classify_post, axis=1, result_type="expand")
    raw = pd.concat([raw, classifications], axis=1)
    raw["본문요약"] = raw["본문"].map(lambda v: summarize(v, 180))
    raw["profile_url"] = raw["작성자"].map(profile_url)

    included = raw[raw["post_profile_level"].isin(["organizer_high", "organizer_medium", "active_member", "review"])].copy()
    excluded = raw[raw["post_profile_level"].eq("exclude")].copy()
    if included.empty:
        return pd.DataFrame(), raw, excluded

    profiles = (
        included.groupby("작성자", dropna=False)
        .agg(
            profile_url=("profile_url", "first"),
            후보글수=("게시글링크", "count"),
            organizer_high글수=("post_profile_level", lambda s: int((s == "organizer_high").sum())),
            organizer_medium글수=("post_profile_level", lambda s: int((s == "organizer_medium").sum())),
            active_member글수=("post_profile_level", lambda s: int((s == "active_member").sum())),
            review글수=("post_profile_level", lambda s: int((s == "review").sum())),
            최고프로필점수=("post_profile_score", "max"),
            평균프로필점수=("post_profile_score", "mean"),
            최대반응합계=("반응합계", "max"),
            평균반응합계=("반응합계", "mean"),
            검색어목록=("검색어", join_unique),
            모임근거=("core_hits", join_unique),
            행동근거=("strong_host_hits", join_unique),
            잡음근거=("bad_hits", join_unique),
            대표글링크=("게시글링크", lambda s: ""),
            대표근거=("본문", lambda s: ""),
            근거요약=("본문요약", join_samples),
        )
        .reset_index()
    )

    for idx, profile in profiles.iterrows():
        group = included[included["작성자"].eq(profile["작성자"])]
        profiles.at[idx, "대표글링크"] = best_url(group)
        profiles.at[idx, "대표근거"] = best_body(group)

    profiles["평균프로필점수"] = profiles["평균프로필점수"].round(1)
    profiles["평균반응합계"] = profiles["평균반응합계"].round(1)

    profiles["프로필분류"] = "review"
    profiles.loc[profiles["organizer_high글수"].gt(0), "프로필분류"] = "organizer_high"
    profiles.loc[
        profiles["organizer_high글수"].eq(0) & profiles["organizer_medium글수"].gt(0),
        "프로필분류",
    ] = "organizer_medium"
    profiles.loc[
        profiles["organizer_high글수"].eq(0)
        & profiles["organizer_medium글수"].eq(0)
        & profiles["active_member글수"].gt(0),
        "프로필분류",
    ] = "active_member"

    profiles["우선검수"] = profiles["프로필분류"].isin(["organizer_high", "organizer_medium"])
    profiles = profiles.sort_values(
        ["우선검수", "프로필분류", "후보글수", "최고프로필점수", "최대반응합계"],
        ascending=[False, True, False, False, False],
    )

    return profiles, raw, excluded


def format_workbook(path: Path) -> None:
    wb = load_workbook(path)
    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)
    widths = {
        "profile_only": {"A": 24, "B": 38, "L": 42, "M": 40, "N": 42, "O": 36, "P": 56, "Q": 100, "R": 100},
        "organizer_priority": {"A": 24, "B": 38, "L": 42, "M": 40, "N": 42, "O": 36, "P": 56, "Q": 100, "R": 100},
        "active_member_or_review": {"A": 24, "B": 38, "L": 42, "M": 40, "N": 42, "O": 36, "P": 56, "Q": 100, "R": 100},
        "evidence_posts": {"A": 16, "B": 24, "C": 46, "D": 90, "E": 18, "F": 18},
        "excluded_review": {"A": 16, "B": 24, "C": 46, "D": 90},
        "quality_summary": {"A": 28, "B": 80},
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
    sheets = pd.read_excel(INPUT_XLSX, sheet_name=None)
    raw = sheets["discovery_posts_raw"].copy()
    profiles, evidence, excluded = build_profiles(raw)

    organizer_priority = profiles[profiles["프로필분류"].isin(["organizer_high", "organizer_medium"])].copy()
    review_profiles = profiles[~profiles["프로필분류"].isin(["organizer_high", "organizer_medium"])].copy()

    evidence_cols = [
        "검색어",
        "작성자",
        "profile_url",
        "게시글링크",
        "본문요약",
        "반응합계",
        "모집점수",
        "post_profile_level",
        "post_profile_score",
        "core_hits",
        "context_hits",
        "strong_host_hits",
        "invite_hits",
        "hard_invite_hits",
        "host_claim_hits",
        "seeker_hits",
        "attendee_hits",
        "bad_hits",
    ]
    evidence_out = evidence[evidence["post_profile_level"].ne("exclude")][evidence_cols].copy()
    excluded_out = excluded[evidence_cols].copy()

    quality = pd.DataFrame(
        [
            {"항목": "input", "값": str(INPUT_XLSX)},
            {"항목": "output_excel", "값": str(OUTPUT_XLSX)},
            {"항목": "output_jsonl", "값": str(OUTPUT_JSONL)},
            {"항목": "raw_posts", "값": len(raw)},
            {"항목": "profile_only_rows", "값": len(profiles)},
            {"항목": "organizer_priority_rows", "값": len(organizer_priority)},
            {"항목": "active_member_or_review_rows", "값": len(review_profiles)},
            {"항목": "evidence_posts_used", "값": len(evidence_out)},
            {"항목": "excluded_review_posts", "값": len(excluded_out)},
            {"항목": "기준", "값": "본문/검색어에서 모임 핵심어 + 운영/모집/신청/함께 등 행동 신호가 있는 작성자만 프로필 목록화"},
        ]
    )

    with OUTPUT_JSONL.open("w", encoding="utf-8") as handle:
        for row in profiles.to_dict(orient="records"):
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    with pd.ExcelWriter(OUTPUT_XLSX, engine="openpyxl") as writer:
        quality.to_excel(writer, sheet_name="quality_summary", index=False)
        profiles.to_excel(writer, sheet_name="profile_only", index=False)
        organizer_priority.to_excel(writer, sheet_name="organizer_priority", index=False)
        review_profiles.to_excel(writer, sheet_name="active_member_or_review", index=False)
        evidence_out.to_excel(writer, sheet_name="evidence_posts", index=False)
        excluded_out.to_excel(writer, sheet_name="excluded_review", index=False)

    format_workbook(OUTPUT_XLSX)

    print(f"output_excel={OUTPUT_XLSX}")
    print(f"output_jsonl={OUTPUT_JSONL}")
    print("\nquality_summary")
    print(quality.to_string(index=False))
    print("\norganizer_priority_top")
    if organizer_priority.empty:
        print("(empty)")
    else:
        print(
            organizer_priority[
                [
                    "작성자",
                    "profile_url",
                    "프로필분류",
                    "후보글수",
                    "최고프로필점수",
                    "검색어목록",
                    "대표근거",
                ]
            ]
            .head(30)
            .to_string(index=False)
        )


if __name__ == "__main__":
    main()
