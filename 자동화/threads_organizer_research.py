import argparse
import json
import re
import sys
import time
import urllib.parse
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd
from seleniumbase import Driver

from scraper import dismiss_thread_popup
from threads_feed_sourcing import extract_feed_cards
from threads_keyword_research import normalize_post_url, scroll_search, select_body_text


try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


DISCOVERY_SEEDS = [
    "모집",
    "참가",
    "참여",
    "신청",
    "함께",
    "독서모임",
    "북클럽",
    "소모임",
    "대화모임",
    "와인모임",
    "러닝크루",
    "등산모임",
    "보드게임",
    "글쓰기모임",
    "취미모임",
    "네트워킹",
    "커뮤니티",
    "소셜링",
    "오프라인",
    "원데이",
]

ML_DISCOVERY_SEEDS = [
    "모임",
    "모집",
    "멤버모집",
    "참가자",
    "참여자",
    "신청링크",
    "오픈채팅",
    "프로필 링크",
    "선착순",
    "마감",
    "독서모임",
    "책모임",
    "북클럽",
    "북토크",
    "글쓰기모임",
    "스터디모임",
    "러닝크루",
    "크루모집",
    "등산모임",
    "보드게임모임",
    "와인모임",
    "영화모임",
    "전시모임",
    "커피챗",
    "네트워킹",
    "밋업",
    "커뮤니티",
    "살롱",
    "소셜링",
    "원데이클래스",
]

ML_REPLACEMENT_SEEDS = [
    "보드게임",
    "와인",
    "와인바",
    "전시",
    "전시회",
    "살롱모임",
    "참가 모집",
    "참여 모집",
    "신청 방법",
    "링크는 프로필",
]

ORGANIZER_TERMS = [
    "모집",
    "참가",
    "참여",
    "신청",
    "신청링크",
    "링크",
    "프로필",
    "댓글",
    "DM",
    "디엠",
    "문의",
    "오픈채팅",
    "함께",
    "같이",
    "열어요",
    "열립니다",
    "진행",
    "운영",
    "호스트",
    "멤버",
    "정원",
    "선착순",
    "마감",
    "무료",
    "유료",
    "참가자",
    "참여자",
    "멤버모집",
    "크루모집",
    "게스트",
    "모실게요",
    "구합니다",
    "찾습니다",
    "오세요",
    "열어요",
    "개설",
    "밋업",
]

MEETUP_TERMS = [
    "모임",
    "소모임",
    "독서",
    "북클럽",
    "대화",
    "와인",
    "러닝",
    "크루",
    "등산",
    "보드게임",
    "글쓰기",
    "취미",
    "스터디",
    "커뮤니티",
    "네트워킹",
    "살롱",
    "소셜링",
    "오프라인",
    "원데이",
    "전시",
    "영화",
    "책모임",
    "북토크",
    "커피챗",
    "밋업",
    "원데이클래스",
    "게스트",
]

NOISE_TERMS = [
    "구인",
    "채용",
    "알바",
    "아르바이트",
    "공구",
    "팔아요",
    "판매",
    "이벤트",
    "릴스",
    "reels",
    "tiktok",
    "explore",
    "지원금",
    "장려금",
    "자격증",
    "입학",
    "할인",
    "쿠폰",
    "공모전",
]


def now_stamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def build_search_url(keyword):
    return "https://www.threads.com/search?q=" + urllib.parse.quote(keyword) + "&serp_type=default"


def safe_handle(handle):
    value = str(handle or "").strip()
    if not value:
        return ""
    return value if value.startswith("@") else "@" + value


def clean_handle_for_url(handle):
    return safe_handle(handle).lstrip("@")


def koreanish_score(text):
    value = str(text or "")
    if not value:
        return 0
    korean = len(re.findall(r"[가-힣]", value))
    latin = len(re.findall(r"[A-Za-z]", value))
    return korean - max(0, latin - korean)


def term_hits(text, terms):
    value = str(text or "").lower()
    return [term for term in terms if term.lower() in value]


def organizer_score(text):
    organizer_hits = term_hits(text, ORGANIZER_TERMS)
    meetup_hits = term_hits(text, MEETUP_TERMS)
    noise_hits = term_hits(text, NOISE_TERMS)
    score = len(organizer_hits) * 2 + len(meetup_hits) * 2
    if organizer_hits and meetup_hits:
        score += 4
    score += min(3, max(0, koreanish_score(text) // 20))
    score -= len(noise_hits) * 3
    if len(str(text or "")) < 12:
        score -= 4
    return score, organizer_hits, meetup_hits, noise_hits


def row_from_card(card, seed="", source="search", handle_hint=""):
    handle = safe_handle(card.get("handle") or handle_hint)
    body = select_body_text(card)
    score, organizer_hits, meetup_hits, noise_hits = organizer_score(body)
    return {
        "수집시각": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "수집소스": source,
        "검색어": seed,
        "작성자": handle,
        "게시글링크": normalize_post_url(card.get("post_url", "")),
        "작성시간_표시": card.get("time_text", ""),
        "작성시간_datetime": card.get("time_datetime", ""),
        "본문": body,
        "본문_후보블록": json.dumps(card.get("text_blocks", []), ensure_ascii=False),
        "좋아요수": card.get("likes", 0),
        "댓글수": card.get("replies", 0),
        "리포스트수": card.get("reposts", 0),
        "공유수": card.get("shares", 0),
        "반응합계": card.get("interaction_total", 0),
        "외부링크있음": bool(card.get("has_external_link", False)),
        "외부링크": "\n".join(card.get("external_links", []) or []),
        "네이티브미디어수": card.get("native_media_count", 0),
        "모집점수": score,
        "모집히트": ", ".join(organizer_hits),
        "모임히트": ", ".join(meetup_hits),
        "잡음히트": ", ".join(noise_hits),
        "라벨상태": "",
        "작성자유형": "",
        "글유형": "",
        "모임카테고리": "",
        "성과라벨": "",
        "학습포함": "",
        "제외사유": "",
        "라벨메모": "",
    }


def collect_search_cards(driver, seed, max_cards, max_scrolls):
    driver.get(build_search_url(seed))
    time.sleep(7)
    dismiss_thread_popup(driver)

    rows = []
    seen = set()
    idle = 0
    for _ in range(max_scrolls + 1):
        new_count = 0
        for card in extract_feed_cards(driver):
            post_url = normalize_post_url(card.get("post_url", ""))
            if not post_url or post_url in seen:
                continue
            seen.add(post_url)
            rows.append(row_from_card(card, seed=seed, source="search"))
            new_count += 1
            if len(rows) >= max_cards:
                return rows
        if new_count == 0:
            idle += 1
            if idle >= 4:
                return rows
        else:
            idle = 0
        scroll_search(driver)
    return rows


def collect_profile_cards(driver, handle, max_cards, max_scrolls):
    profile = clean_handle_for_url(handle)
    if not profile:
        return []
    driver.get(f"https://www.threads.com/@{profile}")
    time.sleep(7)
    dismiss_thread_popup(driver)

    rows = []
    seen = set()
    idle = 0
    target_handle = safe_handle(handle).lower()
    for _ in range(max_scrolls + 1):
        new_count = 0
        for card in extract_feed_cards(driver):
            post_url = normalize_post_url(card.get("post_url", ""))
            card_handle = safe_handle(card.get("handle", "")).lower()
            if not post_url or post_url in seen:
                continue
            if target_handle and card_handle and card_handle != target_handle:
                continue
            seen.add(post_url)
            rows.append(row_from_card(card, source="profile", handle_hint=handle))
            new_count += 1
            if len(rows) >= max_cards:
                return rows
        if new_count == 0:
            idle += 1
            if idle >= 5:
                return rows
        else:
            idle = 0
        scroll_search(driver)
    return rows


def pick_candidate_handles(search_rows, max_handles):
    scored = defaultdict(lambda: {"score": 0, "posts": 0, "max_eng": 0, "evidence": []})
    for row in search_rows:
        handle = safe_handle(row.get("작성자"))
        if not handle:
            continue
        score = int(row.get("모집점수", 0) or 0)
        if score < 3:
            continue
        scored[handle]["score"] += score + min(8, int(row.get("반응합계", 0) or 0) // 50)
        scored[handle]["posts"] += 1
        scored[handle]["max_eng"] = max(scored[handle]["max_eng"], int(row.get("반응합계", 0) or 0))
        if len(scored[handle]["evidence"]) < 3:
            scored[handle]["evidence"].append(row.get("본문", ""))

    ranked = sorted(
        (
            {
                "작성자": handle,
                "후보점수": data["score"],
                "검색노출글수": data["posts"],
                "검색최대반응합계": data["max_eng"],
                "근거본문": " / ".join(data["evidence"]),
            }
            for handle, data in scored.items()
        ),
        key=lambda item: (item["후보점수"], item["검색최대반응합계"]),
        reverse=True,
    )
    return ranked[:max_handles]


def add_performance_labels(profile_rows):
    if not profile_rows:
        return profile_rows
    df = pd.DataFrame(profile_rows)
    labeled = []
    for handle, group in df.groupby("작성자", dropna=False):
        group = group.copy()
        if len(group) >= 4:
            q80 = group["반응합계"].quantile(0.8)
            q40 = group["반응합계"].quantile(0.4)
            group["계정내성과라벨"] = group["반응합계"].apply(
                lambda value: "top" if value >= q80 else ("low" if value <= q40 else "mid")
            )
        else:
            group["계정내성과라벨"] = "too_few_posts"
        group["계정내글수"] = len(group)
        group["계정내반응순위"] = group["반응합계"].rank(method="first", ascending=False).astype(int)
        labeled.append(group)
    return pd.concat(labeled, ignore_index=True).to_dict(orient="records")


def write_outputs(output_path, search_rows, handle_rows, profile_rows, seed_summary, config):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_path.with_suffix(".jsonl")

    profile_rows = add_performance_labels(profile_rows)
    profile_df = pd.DataFrame(profile_rows)
    search_df = pd.DataFrame(search_rows)
    handles_df = pd.DataFrame(handle_rows)
    seed_df = pd.DataFrame(seed_summary)

    if not profile_df.empty:
        profile_df = profile_df.drop_duplicates(subset=["게시글링크"], keep="last")
    if not search_df.empty:
        search_df = search_df.drop_duplicates(subset=["게시글링크"], keep="last")

    quality = pd.DataFrame(
        [
            {"항목": "output_excel", "값": str(output_path)},
            {"항목": "output_jsonl", "값": str(jsonl_path)},
            {"항목": "검색 seed 수", "값": len(seed_summary)},
            {"항목": "검색 발견 글 수", "값": len(search_df)},
            {"항목": "후보 작성자 수", "값": len(handles_df)},
            {"항목": "프로필 글 수", "값": len(profile_df)},
            {"항목": "프로필 글 4개 이상 작성자 수", "값": int((profile_df.groupby("작성자").size() >= 4).sum()) if not profile_df.empty else 0},
            {"항목": "상세글 진입 여부", "값": "No. 검색/프로필 카드 DOM만 수집"},
            {"항목": "의도", "값": "모임 작성자/모집자 계정의 잘 터진 글과 안 터진 글을 계정 내 상대 성과로 비교하기 위한 ML용 raw set"},
        ]
    )

    handle_summary = pd.DataFrame()
    if not profile_df.empty:
        handle_summary = (
            profile_df.groupby("작성자", dropna=False)
            .agg(
                프로필글수=("게시글링크", "count"),
                평균반응합계=("반응합계", "mean"),
                최대반응합계=("반응합계", "max"),
                top글수=("계정내성과라벨", lambda s: int((s == "top").sum())),
                low글수=("계정내성과라벨", lambda s: int((s == "low").sum())),
                모집글수=("모집점수", lambda s: int((s >= 3).sum())),
            )
            .reset_index()
        )
        handle_summary["평균반응합계"] = handle_summary["평균반응합계"].round(1)
        handle_summary = handle_summary.sort_values(["프로필글수", "모집글수", "최대반응합계"], ascending=False)

    jsonl_df = profile_df if not profile_df.empty else search_df
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for row in jsonl_df.to_dict(orient="records"):
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        quality.to_excel(writer, sheet_name="quality_summary", index=False)
        seed_df.to_excel(writer, sheet_name="seed_summary", index=False)
        handles_df.to_excel(writer, sheet_name="candidate_handles", index=False)
        handle_summary.to_excel(writer, sheet_name="handle_summary", index=False)
        profile_df.to_excel(writer, sheet_name="profile_posts_ml", index=False)
        search_df.to_excel(writer, sheet_name="discovery_posts", index=False)
        pd.DataFrame([config]).to_excel(writer, sheet_name="run_config", index=False)

    return {
        "output_path": str(output_path),
        "jsonl_path": str(jsonl_path),
        "search_posts": len(search_df),
        "candidate_handles": len(handles_df),
        "profile_posts": len(profile_df),
        "handles_with_4plus_posts": int((profile_df.groupby("작성자").size() >= 4).sum()) if not profile_df.empty else 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-search-cards", type=int, default=35)
    parser.add_argument("--max-search-scrolls", type=int, default=14)
    parser.add_argument("--max-handles", type=int, default=25)
    parser.add_argument("--max-profile-cards", type=int, default=45)
    parser.add_argument("--max-profile-scrolls", type=int, default=16)
    parser.add_argument("--seed-preset", choices=["basic", "ml-expanded", "ml-replacement"], default="basic")
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--seed-count", type=int, default=0)
    parser.add_argument("--skip-profiles", action="store_true")
    parser.add_argument("--output-dir", default=str(Path(__file__).resolve().parent / "organizer_research_runs"))
    args = parser.parse_args()

    if args.seed_preset == "ml-expanded":
        all_seeds = ML_DISCOVERY_SEEDS
    elif args.seed_preset == "ml-replacement":
        all_seeds = ML_REPLACEMENT_SEEDS
    else:
        all_seeds = DISCOVERY_SEEDS
    seed_end = None if args.seed_count <= 0 else args.seed_start + args.seed_count
    seeds = all_seeds[args.seed_start:seed_end]
    if not seeds:
        raise SystemExit(f"No seeds selected: start={args.seed_start} count={args.seed_count} preset={args.seed_preset}")
    output_path = Path(args.output_dir) / f"threads_organizer_research_{now_stamp()}.xlsx"
    config = vars(args).copy()
    config["seeds"] = ", ".join(seeds)

    driver = Driver(uc=True, headless=False, browser="chrome", page_load_strategy="eager")
    driver.set_page_load_timeout(35)
    search_rows = []
    seed_summary = []
    try:
        for index, seed in enumerate(seeds, start=1):
            print(f"[seed {index}/{len(seeds)}] {seed}", flush=True)
            rows = collect_search_cards(driver, seed, args.max_search_cards, args.max_search_scrolls)
            search_rows.extend(rows)
            seed_summary.append(
                {
                    "검색어": seed,
                    "수집글수": len(rows),
                    "후보글수": sum(1 for row in rows if int(row.get("모집점수", 0) or 0) >= 3),
                    "작성자수": len(set(row.get("작성자", "") for row in rows if row.get("작성자"))),
                }
            )
            print(f"    posts={len(rows)} candidates={seed_summary[-1]['후보글수']}", flush=True)

        handle_rows = pick_candidate_handles(search_rows, args.max_handles)
        print(f"[handles] selected={len(handle_rows)}", flush=True)

        profile_rows = []
        if args.skip_profiles:
            print("[profiles] skipped by --skip-profiles", flush=True)
        else:
            for index, handle_row in enumerate(handle_rows, start=1):
                handle = handle_row["작성자"]
                print(f"[profile {index}/{len(handle_rows)}] {handle}", flush=True)
                rows = collect_profile_cards(driver, handle, args.max_profile_cards, args.max_profile_scrolls)
                for row in rows:
                    row["후보점수"] = handle_row.get("후보점수", 0)
                    row["검색근거본문"] = handle_row.get("근거본문", "")
                profile_rows.extend(rows)
                print(f"    profile_posts={len(rows)}", flush=True)
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    result = write_outputs(output_path, search_rows, handle_rows, profile_rows, seed_summary, config)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
