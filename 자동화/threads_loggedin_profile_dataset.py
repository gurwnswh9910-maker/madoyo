# -*- coding: utf-8 -*-
"""Threads organizer-profile dataset collector.

This script tries a logged-in, fixed Chrome profile first. If the login
session cannot be verified or Threads starts returning blocking signals, it
falls back to a logged-out discovery dataset and marks the output accordingly.

Sensitive login input is never requested in the terminal. The browser is
visible, and the user completes login directly in Chrome.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
import urllib.parse
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from seleniumbase import Driver

from scraper import dismiss_thread_popup
from threads_feed_sourcing import extract_feed_cards
from threads_keyword_research import normalize_post_url, scroll_search, select_body_text


try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_PROFILE_DIR = BASE_DIR / "threads_browser_profile"
DEFAULT_FALLBACK_PROFILE_DIR = BASE_DIR / "threads_logged_out_profile"
DEFAULT_OUTPUT_DIR = BASE_DIR / "organizer_research_runs"

DEFAULT_SEEDS = [
    "커피챗",
    "밋업",
    "네트워킹",
    "북클럽",
    "대화모임",
    "소셜링",
    "친구모임",
    "모임 모집",
    "함께 할 사람",
    "참여자 모집",
    "독서모임",
    "영화모임",
    "와인모임",
    "보드게임 모임",
    "커뮤니티 모집",
    "오프라인 모임",
    "토크 모임",
    "취향 모임",
]

FALLBACK_EXTRA_SEEDS = [
    "커피챗 모집",
    "밋업 모집",
    "네트워킹 모집",
    "북클럽 모집",
    "독서모임 모집",
    "대화모임 모집",
    "친구 만들기 모임",
    "직장인 모임",
    "소규모 모임",
    "참가자 모집",
]

HOST_TERMS = [
    "모집",
    "참여",
    "신청",
    "열어요",
    "엽니다",
    "진행",
    "운영",
    "주최",
    "오세요",
    "함께",
    "같이",
    "구합니다",
    "멤버",
    "정원",
    "마감",
    "예약",
    "신청링크",
    "링크",
    "댓글",
    "DM",
    "디엠",
    "문의",
    "참가",
    "참석",
    "호스트",
    "할 사람",
    "하실 분",
    "하고 싶은",
    "있을까",
    "있나",
    "찾습니다",
    "찾아요",
    "구해요",
    "오실 분",
    "올 사람",
    "올 분",
    "와볼",
    "와 볼",
    "오실래",
    "당해볼래",
    "댓글달아줘",
    "댓글 달아줘",
    "관심 있는",
    "관심있는",
    "관심 있으신",
    "관심있으면",
    "수락할",
]

STRONG_RELATION_TERMS = [
    "커피챗",
    "밋업",
    "네트워킹",
    "북클럽",
    "독서모임",
    "북토크",
    "대화모임",
    "토크모임",
    "소셜링",
    "친구모임",
    "친구 만들기",
    "친구 찾기",
    "친목모임",
    "와인모임",
    "영화모임",
    "보드게임 모임",
    "취향모임",
]

RELATION_TERMS = [
    "커피챗",
    "밋업",
    "네트워킹",
    "북클럽",
    "독서모임",
    "북토크",
    "대화모임",
    "토크",
    "소셜링",
    "친구",
    "친목",
    "만남",
    "교류",
    "커뮤니티",
    "모임",
    "취향",
    "영화모임",
    "와인모임",
    "보드게임",
]

COMMERCIAL_TERMS = [
    "참가비",
    "유료",
    "예약",
    "결제",
    "얼리버드",
    "정가",
    "원",
    "마감",
    "클래스",
    "호스트",
    "티켓",
]

LEARNING_EXCLUDE_TERMS = [
    "스터디",
    "공부",
    "학습",
    "개발",
    "개발자",
    "코딩",
    "프로그래밍",
    "AI",
    "인공지능",
    "생성형",
    "LLM",
    "ChatGPT",
    "Claude",
    "Cursor",
    "MCP",
    "커서",
    "바이브코딩",
    "데이터",
    "교육",
    "강의",
    "수업",
    "멘토링",
    "컨설팅",
    "부트캠프",
    "세미나",
    "컨퍼런스",
    "웨비나",
    "해커톤",
    "자격증",
    "영어",
    "토익",
    "기술",
    "지원사업",
    "지원내용",
    "사업화",
    "예비창업",
    "초기기업",
    "창업",
    "투자",
    "박람회",
    "피칭",
    "수출",
    "비즈니스",
    "커리어",
    "재테크",
    "마케팅",
    "마케터",
    "광고",
    "브랜딩",
    "브랜드",
    "콘텐츠",
    "SNS",
    "웹사이트",
    "웹사이트제작",
    "웹빌더",
    "쇼핑몰운영",
    "자동화",
    "이커머스",
    "커머스",
    "스마트스토어",
    "쇼핑몰",
    "쿠팡",
    "제품",
    "취업",
    "해외취업",
    "링크드인",
    "채용",
]

EXERCISE_EXCLUDE_TERMS = [
    "러닝",
    "운동",
    "헬스",
    "요가",
    "필라테스",
    "등산",
    "클라이밍",
    "풋살",
    "축구",
    "테니스",
    "배드민턴",
]

BRAND_REFERENCE_TERMS = [
    "문토",
    "넷플연가",
    "트레바리",
    "타임레프트",
    "남의집",
    "프립",
]

LOGIN_PROMPTS = [
    "log in to threads",
    "log in or sign up",
    "continue with instagram",
    "log in with instagram",
    "threads에 로그인",
    "로그인하여",
    "로그인 또는 가입",
    "instagram으로 계속",
    "인스타그램으로 계속",
]

BLOCK_PROMPTS = [
    "429",
    "too many requests",
    "try again later",
    "temporarily blocked",
    "challenge",
    "checkpoint",
    "suspicious",
    "잠시 후 다시",
    "나중에 다시",
    "일시적으로",
]


class CrawlBlocked(RuntimeError):
    """Raised when Threads repeatedly returns block/challenge signals."""


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def clean_handle(handle: str) -> str:
    value = str(handle or "").strip()
    if not value:
        return ""
    value = value.split("?")[0].strip("/")
    if value.startswith("https://"):
        match = re.search(r"threads\.(?:net|com)/(@[^/?#]+)", value, re.I)
        value = match.group(1) if match else value
    return value.lstrip("@").strip()


def profile_url_for(handle: str) -> str:
    cleaned = clean_handle(handle)
    return f"https://www.threads.com/@{cleaned}" if cleaned else ""


def build_search_url(keyword: str) -> str:
    return "https://www.threads.com/search?q=" + urllib.parse.quote(keyword) + "&serp_type=default"


def make_driver(profile_dir: Path | None, *, headless: bool = False) -> Any:
    if profile_dir:
        profile_dir.mkdir(parents=True, exist_ok=True)
    driver = Driver(
        uc=True,
        headless=headless,
        browser="chrome",
        user_data_dir=str(profile_dir) if profile_dir else None,
        page_load_strategy="eager",
    )
    driver.set_page_load_timeout(45)
    return driver


def page_state(driver: Any) -> dict[str, Any]:
    try:
        current_url = driver.current_url or ""
    except Exception:
        current_url = ""
    try:
        text = driver.execute_script("return document.body ? document.body.innerText : ''") or ""
    except Exception:
        text = ""
    lowered = text.lower()
    try:
        counts = driver.execute_script(
            """
            return {
              password: document.querySelectorAll('input[type="password"]').length,
              postAnchors: document.querySelectorAll('a[href*="/post/"]').length,
              profileAnchors: document.querySelectorAll('a[href*="/@"]').length,
              dialogs: document.querySelectorAll('[role="dialog"]').length
            };
            """
        ) or {}
    except Exception:
        counts = {}
    login_prompt = (
        int(counts.get("password") or 0) > 0
        or "/login" in current_url.lower()
        or any(prompt in lowered for prompt in LOGIN_PROMPTS)
    )
    blocked = any(prompt in lowered for prompt in BLOCK_PROMPTS)
    return {
        "url": current_url,
        "login_prompt": login_prompt,
        "blocked": blocked,
        "post_anchors": int(counts.get("postAnchors") or 0),
        "profile_anchors": int(counts.get("profileAnchors") or 0),
        "dialogs": int(counts.get("dialogs") or 0),
        "text_len": len(text),
    }


def wait_for_login(driver: Any, timeout_seconds: int) -> dict[str, Any]:
    print("[login] checking existing Threads session first", flush=True)
    driver.get("https://www.threads.com/@threads")
    time.sleep(6)
    state = page_state(driver)
    cards = extract_feed_cards(driver)
    if not state["blocked"] and not state["login_prompt"] and (cards or state["post_anchors"] > 0):
        state["status"] = "logged_in"
        state["cards"] = len(cards)
        print("[login] existing fixed-profile session looks logged in", flush=True)
        return state

    print("[login] opening Threads login page with fixed Chrome profile", flush=True)
    driver.get("https://www.threads.com/login")
    time.sleep(5)
    print("[login] enter credentials/2FA in the visible browser only. Do not paste them into chat.", flush=True)

    deadline = time.time() + timeout_seconds
    next_log = 0.0
    while time.time() < deadline:
        dismiss_thread_popup(driver)
        state = page_state(driver)
        if state["blocked"]:
            state["status"] = "blocked_or_challenge"
            return state
        if not state["login_prompt"] and (state["post_anchors"] > 0 or state["profile_anchors"] > 0):
            state["status"] = "logged_in"
            print("[login] session looks logged in", flush=True)
            return state
        if time.time() >= next_log:
            remain = int(deadline - time.time())
            print(f"[login] waiting for browser login... remaining={remain}s url={state['url']}", flush=True)
            next_log = time.time() + 10
        time.sleep(2)

    state = page_state(driver)
    state["status"] = "timeout"
    return state


def ensure_logged_in_profile_access(driver: Any) -> dict[str, Any]:
    print("[login-check] verifying profile timeline access", flush=True)
    driver.get("https://www.threads.com/@threads")
    time.sleep(6)
    state = page_state(driver)
    if state["blocked"]:
        state["status"] = "blocked_or_challenge"
        state["cards"] = 0
        print(f"[login-check] status={state['status']} cards=0 url={state['url']}", flush=True)
        return state
    if state["login_prompt"]:
        state["status"] = "login_required"
        state["cards"] = 0
        print(f"[login-check] status={state['status']} cards=0 url={state['url']}", flush=True)
        return state
    dismiss_thread_popup(driver)
    cards = extract_feed_cards(driver)
    state["cards"] = len(cards)
    if state["cards"] > 0 or state["post_anchors"] > 0:
        state["status"] = "ok"
    else:
        state["status"] = "uncertain"
    print(f"[login-check] status={state['status']} cards={state['cards']} url={state['url']}", flush=True)
    return state


def term_hits(text: str, terms: list[str]) -> list[str]:
    value = str(text or "")
    lowered = value.lower()
    return [term for term in terms if term.lower() in lowered]


def classify_text(text: str) -> dict[str, Any]:
    strong_relation_hits = term_hits(text, STRONG_RELATION_TERMS)
    relation_hits = term_hits(text, RELATION_TERMS)
    host_hits = term_hits(text, HOST_TERMS)
    commercial_hits = term_hits(text, COMMERCIAL_TERMS)
    learning_hits = term_hits(text, LEARNING_EXCLUDE_TERMS)
    exercise_hits = term_hits(text, EXERCISE_EXCLUDE_TERMS)
    brand_hits = term_hits(text, BRAND_REFERENCE_TERMS)

    has_relation = bool(relation_hits)
    has_strong_relation = bool(strong_relation_hits)
    has_host = bool(host_hits)
    has_learning = bool(learning_hits)
    has_exercise = bool(exercise_hits)
    has_brand = bool(brand_hits)

    has_specific_relation = has_strong_relation or any(
        term in relation_hits for term in ["친목", "만남", "교류", "커뮤니티", "모임", "취향"]
    )
    strict_target = has_specific_relation and has_host and not has_learning and not has_exercise and not has_brand
    if strict_target:
        status = "strict_relationship_host"
    elif has_brand and has_relation:
        status = "brand_reference"
    elif has_learning:
        status = "excluded_learning"
    elif has_exercise:
        status = "excluded_exercise"
    elif has_relation or has_host:
        status = "ambiguous_or_weak"
    else:
        status = "other"

    organizer_type = ""
    if strict_target and commercial_hits:
        organizer_type = "commercial_host"
    elif strict_target:
        organizer_type = "personal_or_small_host"
    elif status == "brand_reference":
        organizer_type = "brand_reference"

    return {
        "relationship_host_label": int(strict_target),
        "commercial_host_label": int(bool(commercial_hits) and strict_target),
        "learning_exclude_label": int(has_learning),
        "exercise_exclude_label": int(has_exercise),
        "brand_reference_label": int(status == "brand_reference"),
        "post_policy_status": status,
        "organizer_type": organizer_type,
        "strong_relation_hits": ", ".join(strong_relation_hits),
        "relation_hits": ", ".join(relation_hits),
        "host_hits": ", ".join(host_hits),
        "commercial_hits": ", ".join(commercial_hits),
        "learning_hits": ", ".join(learning_hits),
        "exercise_hits": ", ".join(exercise_hits),
        "brand_hits": ", ".join(brand_hits),
        "usable_for_copy_scorer": int(strict_target),
    }


def row_from_card(
    card: dict[str, Any],
    *,
    run_id: str,
    crawl_mode: str,
    source: str,
    keyword: str = "",
    search_rank: int = 0,
) -> dict[str, Any]:
    handle = clean_handle(card.get("handle", ""))
    text_blocks = [str(block).strip() for block in (card.get("text_blocks") or []) if str(block).strip()]
    full_context_text = " ".join(dict.fromkeys(text_blocks))
    raw_text = select_body_text(card) or str(card.get("preview_text") or "").strip()
    row = {
        "run_id": run_id,
        "collected_at": now_iso(),
        "crawl_mode": crawl_mode,
        "source": source,
        "source_seed": keyword,
        "search_rank": search_rank,
        "handle": handle,
        "profile_url": profile_url_for(handle),
        "post_url": normalize_post_url(card.get("post_url", "")),
        "posted_text": card.get("time_text", ""),
        "posted_at": card.get("time_datetime", ""),
        "raw_text": raw_text,
        "clean_text": " ".join(str(raw_text or "").split()),
        "full_context_text": " ".join(full_context_text.split()),
        "like_count": int(card.get("likes") or 0),
        "comment_count": int(card.get("replies") or 0),
        "repost_count": int(card.get("reposts") or 0),
        "share_count": int(card.get("shares") or 0),
        "reaction_total": int(card.get("interaction_total") or 0),
        "media_type": "native_media" if card.get("has_native_media") else "text_or_link",
        "native_media_count": int(card.get("native_media_count") or 0),
        "has_external_link": int(bool(card.get("has_external_link"))),
        "text_blocks_json": json.dumps(text_blocks, ensure_ascii=False),
        "external_links_json": json.dumps(card.get("external_links") or [], ensure_ascii=False),
    }
    if source == "search":
        classify_basis = f"{row['full_context_text']} {row['clean_text']} {handle}"
    else:
        classify_basis = f"{row['clean_text']} {handle}"
    row.update(classify_text(classify_basis))
    return row


def collect_search_cards(
    driver: Any,
    *,
    keyword: str,
    run_id: str,
    crawl_mode: str,
    max_cards: int,
    max_scrolls: int,
    idle_limit: int,
    block_counter: dict[str, int],
    max_block_events: int,
) -> list[dict[str, Any]]:
    print(f"[search] keyword={keyword}", flush=True)
    driver.get(build_search_url(keyword))
    time.sleep(6)
    dismiss_thread_popup(driver)

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    idle = 0
    for scroll_index in range(max_scrolls + 1):
        state = page_state(driver)
        cards = extract_feed_cards(driver)
        signal_without_cards = not cards and (state["blocked"] or (state["login_prompt"] and crawl_mode == "logged_in"))
        if signal_without_cards:
            block_counter["count"] += 1
            print(f"[search] block/login signal count={block_counter['count']} keyword={keyword}", flush=True)
            if block_counter["count"] >= max_block_events:
                raise CrawlBlocked(f"block/login signal reached {block_counter['count']}")
        new_count = 0
        for card in cards:
            post_url = normalize_post_url(card.get("post_url", ""))
            if not post_url or post_url in seen:
                continue
            seen.add(post_url)
            rows.append(
                row_from_card(
                    card,
                    run_id=run_id,
                    crawl_mode=crawl_mode,
                    source="search",
                    keyword=keyword,
                    search_rank=len(rows) + 1,
                )
            )
            new_count += 1
            if len(rows) >= max_cards:
                print(f"[search] keyword={keyword} rows={len(rows)}", flush=True)
                return rows
        if new_count == 0:
            idle += 1
            if idle >= idle_limit:
                break
        else:
            idle = 0
        if scroll_index < max_scrolls:
            scroll_search(driver)
    print(f"[search] keyword={keyword} rows={len(rows)}", flush=True)
    return rows


def collect_profile_cards(
    driver: Any,
    *,
    handle: str,
    run_id: str,
    max_cards: int,
    max_scrolls: int,
    idle_limit: int,
    block_counter: dict[str, int],
    max_block_events: int,
) -> list[dict[str, Any]]:
    cleaned = clean_handle(handle)
    if not cleaned:
        return []
    print(f"[profile] handle=@{cleaned}", flush=True)
    driver.get(profile_url_for(cleaned))
    time.sleep(6)
    dismiss_thread_popup(driver)

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    idle = 0
    for scroll_index in range(max_scrolls + 1):
        state = page_state(driver)
        cards = extract_feed_cards(driver)
        signal_without_cards = not cards and (state["blocked"] or state["login_prompt"])
        if signal_without_cards:
            block_counter["count"] += 1
            print(f"[profile] block/login signal count={block_counter['count']} handle=@{cleaned}", flush=True)
            if block_counter["count"] >= max_block_events:
                raise CrawlBlocked(f"block/login signal reached {block_counter['count']}")
        new_count = 0
        for card in cards:
            post_url = normalize_post_url(card.get("post_url", ""))
            card_handle = clean_handle(card.get("handle", ""))
            if not post_url or post_url in seen:
                continue
            if card_handle and card_handle.lower() != cleaned.lower():
                continue
            seen.add(post_url)
            rows.append(
                row_from_card(
                    card,
                    run_id=run_id,
                    crawl_mode="logged_in",
                    source="profile",
                    keyword="",
                    search_rank=len(rows) + 1,
                )
            )
            new_count += 1
            if len(rows) >= max_cards:
                print(f"[profile] handle=@{cleaned} rows={len(rows)}", flush=True)
                return rows
        if new_count == 0:
            idle += 1
            if idle >= idle_limit:
                break
        else:
            idle = 0
        if scroll_index < max_scrolls:
            scroll_search(driver)
    print(f"[profile] handle=@{cleaned} rows={len(rows)}", flush=True)
    return rows


def pick_candidate_handles(search_rows: list[dict[str, Any]], max_handles: int) -> list[dict[str, Any]]:
    scored: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"score": 0, "strict_posts": 0, "max_reaction": 0, "evidence": [], "keywords": set()}
    )
    for row in search_rows:
        handle = clean_handle(row.get("handle", ""))
        if not handle:
            continue
        if int(row.get("relationship_host_label") or 0) != 1:
            continue
        reaction = int(row.get("reaction_total") or 0)
        score = 10 + min(20, reaction // 25) + int(row.get("commercial_host_label") or 0) * 3
        scored[handle]["score"] += score
        scored[handle]["strict_posts"] += 1
        scored[handle]["max_reaction"] = max(scored[handle]["max_reaction"], reaction)
        scored[handle]["keywords"].add(row.get("source_seed", ""))
        if len(scored[handle]["evidence"]) < 3:
            evidence = row.get("full_context_text") or row.get("clean_text", "")
            scored[handle]["evidence"].append(str(evidence)[:350])

    ranked = []
    for handle, data in scored.items():
        ranked.append(
            {
                "handle": handle,
                "profile_url": profile_url_for(handle),
                "candidate_score": data["score"],
                "strict_seed_post_count": data["strict_posts"],
                "max_seed_reaction_total": data["max_reaction"],
                "source_seeds": ", ".join(sorted(data["keywords"])),
                "evidence_text": " / ".join(data["evidence"]),
            }
        )
    ranked.sort(key=lambda item: (item["candidate_score"], item["max_seed_reaction_total"]), reverse=True)
    return ranked[:max_handles]


def add_performance_labels(posts: pd.DataFrame) -> pd.DataFrame:
    if posts.empty:
        return posts
    out = posts.copy()
    out["author_percentile"] = 0.0
    out["performance_bucket"] = "unlabeled"
    for handle, index in out.groupby("handle", dropna=False).groups.items():
        group = out.loc[index].copy()
        if len(group) < 4:
            continue
        percentiles = group["reaction_total"].rank(method="average", pct=True)
        out.loc[index, "author_percentile"] = percentiles
        out.loc[index, "performance_bucket"] = percentiles.apply(
            lambda value: "top" if value >= 0.80 else ("low" if value <= 0.40 else "mid")
        )
    return out


def build_organizers(
    candidate_handles: list[dict[str, Any]],
    search_rows: list[dict[str, Any]],
    profile_rows: list[dict[str, Any]],
    min_profile_posts: int,
    min_strict_evidence: int,
) -> pd.DataFrame:
    candidates = pd.DataFrame(candidate_handles)
    if candidates.empty:
        return candidates
    search_df = pd.DataFrame(search_rows)
    profile_df = pd.DataFrame(profile_rows)
    records = []
    for _, candidate in candidates.iterrows():
        handle = clean_handle(candidate.get("handle", ""))
        search_group = search_df[search_df["handle"].str.lower() == handle.lower()] if not search_df.empty else pd.DataFrame()
        profile_group = profile_df[profile_df["handle"].str.lower() == handle.lower()] if not profile_df.empty else pd.DataFrame()
        strict_count = int(search_group.get("relationship_host_label", pd.Series(dtype=int)).sum()) + int(
            profile_group.get("relationship_host_label", pd.Series(dtype=int)).sum()
        )
        profile_post_count = len(profile_group)
        commercial_count = int(search_group.get("commercial_host_label", pd.Series(dtype=int)).sum()) + int(
            profile_group.get("commercial_host_label", pd.Series(dtype=int)).sum()
        )
        accepted = strict_count >= min_strict_evidence and profile_post_count >= min_profile_posts
        organizer_type = "commercial_host" if commercial_count else "personal_or_small_host"
        if not accepted and profile_post_count < min_profile_posts:
            reject_reason = f"profile_posts_below_{min_profile_posts}"
        elif not accepted and strict_count < min_strict_evidence:
            reject_reason = f"strict_evidence_below_{min_strict_evidence}"
        elif not accepted:
            reject_reason = "no_strict_relationship_evidence"
        else:
            reject_reason = ""
        all_group = pd.concat([search_group, profile_group], ignore_index=True) if not profile_group.empty else search_group
        records.append(
            {
                "organizer_id": f"org_{handle.lower()}",
                "handle": handle,
                "profile_url": profile_url_for(handle),
                "organizer_type": organizer_type,
                "included_primary": int(accepted),
                "excluded_reason": reject_reason,
                "strict_evidence_count": strict_count,
                "commercial_evidence_count": commercial_count,
                "profile_post_count": profile_post_count,
                "max_reaction_total": int(all_group["reaction_total"].max()) if not all_group.empty else 0,
                "median_reaction_total": float(all_group["reaction_total"].median()) if not all_group.empty else 0.0,
                "source_seeds": candidate.get("source_seeds", ""),
                "evidence_post_url": search_group.iloc[0]["post_url"] if not search_group.empty else "",
                "included_reason": "strict relationship host with enough profile posts" if accepted else "",
            }
        )
    return pd.DataFrame(records)


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        create table if not exists posts (
            post_url text primary key,
            run_id text,
            crawl_mode text,
            source text,
            handle text,
            collected_at text,
            raw_json text not null
        )
        """
    )
    conn.execute(
        """
        create table if not exists organizers (
            organizer_id text primary key,
            run_id text,
            handle text,
            included_primary integer,
            raw_json text not null
        )
        """
    )
    conn.commit()
    return conn


def persist_rows(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        post_url = row.get("post_url", "")
        if not post_url:
            continue
        conn.execute(
            """
            insert or replace into posts(post_url, run_id, crawl_mode, source, handle, collected_at, raw_json)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                post_url,
                row.get("run_id", ""),
                row.get("crawl_mode", ""),
                row.get("source", ""),
                row.get("handle", ""),
                row.get("collected_at", ""),
                json.dumps(row, ensure_ascii=False),
            ),
        )
    conn.commit()


def persist_organizers(conn: sqlite3.Connection, organizers: pd.DataFrame, run_id: str) -> None:
    for row in organizers.to_dict("records"):
        conn.execute(
            """
            insert or replace into organizers(organizer_id, run_id, handle, included_primary, raw_json)
            values (?, ?, ?, ?, ?)
            """,
            (
                row.get("organizer_id", ""),
                run_id,
                row.get("handle", ""),
                int(row.get("included_primary") or 0),
                json.dumps(row, ensure_ascii=False),
            ),
        )
    conn.commit()


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def autosize_workbook(path: Path) -> None:
    try:
        from openpyxl import load_workbook
    except Exception:
        return
    wb = load_workbook(path)
    for ws in wb.worksheets:
        ws.freeze_panes = "A2"
        for col in ws.columns:
            letter = col[0].column_letter
            width = min(80, max(10, max(len(str(cell.value or "")) for cell in col[:80]) + 2))
            ws.column_dimensions[letter].width = width
    wb.save(path)


def write_logged_in_outputs(
    *,
    output_dir: Path,
    run_id: str,
    search_rows: list[dict[str, Any]],
    candidate_handles: list[dict[str, Any]],
    profile_rows: list[dict[str, Any]],
    organizers: pd.DataFrame,
    config: dict[str, Any],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    all_rows = search_rows + profile_rows
    raw_df = pd.DataFrame(all_rows)
    profile_df = pd.DataFrame(profile_rows)
    organizers_primary = organizers[organizers["included_primary"] == 1].copy() if not organizers.empty else organizers
    accepted_handles = set(organizers_primary["handle"].str.lower()) if not organizers_primary.empty else set()
    if not profile_df.empty and accepted_handles:
        profile_posts_context = profile_df[profile_df["handle"].str.lower().isin(accepted_handles)].copy()
    else:
        profile_posts_context = pd.DataFrame(columns=profile_df.columns)
    profile_posts_context = add_performance_labels(profile_posts_context)
    if not raw_df.empty and accepted_handles:
        posts_primary = raw_df[
            raw_df["handle"].str.lower().isin(accepted_handles) & (raw_df["usable_for_copy_scorer"] == 1)
        ].copy()
        posts_primary = posts_primary.drop_duplicates(subset=["post_url"], keep="last")
    else:
        posts_primary = pd.DataFrame(columns=raw_df.columns)
    if not posts_primary.empty and not profile_posts_context.empty:
        perf_cols = ["post_url", "author_percentile", "performance_bucket"]
        posts_primary = posts_primary.merge(
            profile_posts_context[perf_cols],
            on="post_url",
            how="left",
        )
        posts_primary["author_percentile"] = posts_primary["author_percentile"].fillna(0.0)
        posts_primary["performance_bucket"] = posts_primary["performance_bucket"].fillna("search_evidence")
    for column, default in {"author_percentile": 0.0, "performance_bucket": "search_evidence"}.items():
        if column not in posts_primary.columns:
            posts_primary[column] = default
    excluded_ambiguous = raw_df[raw_df["post_policy_status"].isin(["ambiguous_or_weak"])] if not raw_df.empty else raw_df
    excluded_learning_exercise = (
        raw_df[raw_df["post_policy_status"].isin(["excluded_learning", "excluded_exercise"])]
        if not raw_df.empty
        else raw_df
    )
    brand_reference = raw_df[raw_df["post_policy_status"].eq("brand_reference")] if not raw_df.empty else raw_df

    quality = pd.DataFrame(
        [
            {"metric": "run_id", "value": run_id},
            {"metric": "mode", "value": "logged_in_profile_dataset"},
            {"metric": "search_posts", "value": len(search_rows)},
            {"metric": "candidate_handles", "value": len(candidate_handles)},
            {"metric": "profile_posts_raw", "value": len(profile_rows)},
            {"metric": "organizers_primary", "value": len(organizers_primary)},
            {"metric": "profile_posts_context", "value": len(profile_posts_context)},
            {"metric": "posts_primary_ml", "value": len(posts_primary)},
            {"metric": "strict_relationship_posts_all", "value": int(raw_df["relationship_host_label"].sum()) if not raw_df.empty else 0},
            {"metric": "min_profile_posts", "value": config.get("min_profile_posts")},
            {"metric": "min_strict_evidence", "value": config.get("min_strict_evidence")},
            {"metric": "profile_dir", "value": config.get("profile_dir")},
        ]
    )

    xlsx_path = output_dir / f"threads_loggedin_profile_dataset_{run_id}.xlsx"
    jsonl_path = output_dir / f"threads_loggedin_profile_dataset_{run_id}.jsonl"
    db_path = output_dir / "threads_organizer_dataset.sqlite"

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        quality.to_excel(writer, sheet_name="dataset_quality_summary", index=False)
        organizers_primary.to_excel(writer, sheet_name="organizers_primary", index=False)
        posts_primary.to_excel(writer, sheet_name="posts_primary_ml", index=False)
        profile_posts_context.to_excel(writer, sheet_name="profile_posts_context", index=False)
        raw_df.to_excel(writer, sheet_name="posts_raw_all", index=False)
        pd.DataFrame(candidate_handles).to_excel(writer, sheet_name="candidate_organizers", index=False)
        excluded_ambiguous.to_excel(writer, sheet_name="excluded_ambiguous", index=False)
        excluded_learning_exercise.to_excel(writer, sheet_name="excluded_learning_exercise", index=False)
        brand_reference.to_excel(writer, sheet_name="brand_reference", index=False)
        pd.DataFrame([config]).to_excel(writer, sheet_name="run_config", index=False)
    autosize_workbook(xlsx_path)
    write_jsonl(jsonl_path, all_rows)

    conn = init_db(db_path)
    try:
        persist_rows(conn, all_rows)
        persist_organizers(conn, organizers, run_id)
    finally:
        conn.close()

    return {
        "mode": "logged_in_profile_dataset",
        "xlsx_path": str(xlsx_path),
        "jsonl_path": str(jsonl_path),
        "sqlite_path": str(db_path),
        "organizers_primary": len(organizers_primary),
        "posts_primary_ml": len(posts_primary),
        "profile_posts_raw": len(profile_rows),
    }


def write_fallback_outputs(
    *,
    output_dir: Path,
    run_id: str,
    search_rows: list[dict[str, Any]],
    candidate_handles: list[dict[str, Any]],
    reason: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_df = pd.DataFrame(search_rows)
    strict_df = raw_df[raw_df["relationship_host_label"] == 1].copy() if not raw_df.empty else raw_df
    candidates_df = pd.DataFrame(candidate_handles)
    limits = pd.DataFrame(
        [
            {"metric": "run_id", "value": run_id},
            {"metric": "mode", "value": "logged_out_discovery_raw"},
            {"metric": "fallback_reason", "value": reason},
            {"metric": "raw_posts", "value": len(raw_df)},
            {"metric": "strict_relationship_candidates", "value": len(strict_df)},
            {"metric": "candidate_organizers", "value": len(candidates_df)},
            {"metric": "quality_limit", "value": "not profile-complete; do not train primary scorer directly"},
        ]
    )
    xlsx_path = output_dir / f"threads_loggedout_discovery_fallback_{run_id}.xlsx"
    jsonl_path = output_dir / f"threads_loggedout_discovery_fallback_{run_id}.jsonl"
    db_path = output_dir / "threads_organizer_dataset.sqlite"

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        raw_df.to_excel(writer, sheet_name="logged_out_discovery_raw", index=False)
        strict_df.to_excel(writer, sheet_name="strict_relationship_candidates", index=False)
        candidates_df.to_excel(writer, sheet_name="candidate_organizers", index=False)
        limits.to_excel(writer, sheet_name="fallback_quality_limits", index=False)
        pd.DataFrame([config]).to_excel(writer, sheet_name="run_config", index=False)
    autosize_workbook(xlsx_path)
    write_jsonl(jsonl_path, search_rows)

    conn = init_db(db_path)
    try:
        persist_rows(conn, search_rows)
    finally:
        conn.close()

    return {
        "mode": "logged_out_discovery_raw",
        "xlsx_path": str(xlsx_path),
        "jsonl_path": str(jsonl_path),
        "sqlite_path": str(db_path),
        "raw_posts": len(raw_df),
        "strict_relationship_candidates": len(strict_df),
        "candidate_organizers": len(candidates_df),
        "fallback_reason": reason,
    }


def parse_seeds(args: argparse.Namespace, *, fallback: bool = False) -> list[str]:
    seeds: list[str] = []
    if args.keywords:
        seeds.extend([part.strip() for part in args.keywords.split(",") if part.strip()])
    if args.keywords_file:
        path = Path(args.keywords_file)
        seeds.extend(
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
    if not seeds:
        seeds = list(DEFAULT_SEEDS)
    if fallback:
        seeds = seeds + [seed for seed in FALLBACK_EXTRA_SEEDS if seed not in seeds]
    if args.smoke:
        count = args.fallback_seed_count if fallback else 2
    else:
        count = args.seed_count
    if count and count > 0:
        seeds = seeds[:count]
    return seeds


def run_logged_in_dataset(driver: Any, args: argparse.Namespace, run_id: str) -> dict[str, Any]:
    seeds = parse_seeds(args, fallback=False)
    block_counter = {"count": 0}
    search_rows: list[dict[str, Any]] = []
    for keyword in seeds:
        rows = collect_search_cards(
            driver,
            keyword=keyword,
            run_id=run_id,
            crawl_mode="logged_in",
            max_cards=args.max_search_cards,
            max_scrolls=args.max_search_scrolls,
            idle_limit=args.idle_limit,
            block_counter=block_counter,
            max_block_events=args.max_block_events,
        )
        search_rows.extend(rows)

    candidate_handles = pick_candidate_handles(search_rows, args.max_handles)
    print(f"[candidates] selected={len(candidate_handles)}", flush=True)

    profile_rows: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidate_handles, start=1):
        print(f"[profile] {index}/{len(candidate_handles)} @{candidate['handle']}", flush=True)
        rows = collect_profile_cards(
            driver,
            handle=candidate["handle"],
            run_id=run_id,
            max_cards=args.max_profile_posts,
            max_scrolls=args.max_profile_scrolls,
            idle_limit=args.idle_limit,
            block_counter=block_counter,
            max_block_events=args.max_block_events,
        )
        profile_rows.extend(rows)

    organizers = build_organizers(
        candidate_handles,
        search_rows,
        profile_rows,
        args.min_profile_posts,
        args.min_strict_evidence,
    )
    config = vars(args).copy()
    config.update({"profile_dir": str(Path(args.profile_dir)), "seeds": ", ".join(seeds)})
    return write_logged_in_outputs(
        output_dir=Path(args.output_dir),
        run_id=run_id,
        search_rows=search_rows,
        candidate_handles=candidate_handles,
        profile_rows=profile_rows,
        organizers=organizers,
        config=config,
    )


def run_logged_out_fallback(args: argparse.Namespace, run_id: str, reason: str) -> dict[str, Any]:
    print(f"[fallback] starting logged-out discovery. reason={reason}", flush=True)
    seeds = parse_seeds(args, fallback=True)
    block_counter = {"count": 0}
    driver = make_driver(Path(args.fallback_profile_dir), headless=args.headless)
    search_rows: list[dict[str, Any]] = []
    try:
        for keyword in seeds:
            rows = collect_search_cards(
                driver,
                keyword=keyword,
                run_id=run_id,
                crawl_mode="logged_out",
                max_cards=args.fallback_max_search_cards,
                max_scrolls=args.fallback_max_search_scrolls,
                idle_limit=args.idle_limit,
                block_counter=block_counter,
                max_block_events=args.max_block_events,
            )
            search_rows.extend(rows)
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    candidate_handles = pick_candidate_handles(search_rows, args.max_handles)
    config = vars(args).copy()
    config.update({"fallback_reason": reason, "seeds": ", ".join(seeds)})
    return write_fallback_outputs(
        output_dir=Path(args.output_dir),
        run_id=run_id,
        search_rows=search_rows,
        candidate_handles=candidate_handles,
        reason=reason,
        config=config,
    )


def run_auto(args: argparse.Namespace) -> dict[str, Any]:
    run_id = now_stamp()
    driver = None
    try:
        driver = make_driver(Path(args.profile_dir), headless=args.headless)
        if args.mode == "login-only":
            login_state = wait_for_login(driver, args.login_timeout_seconds)
            check = ensure_logged_in_profile_access(driver) if login_state.get("status") == "logged_in" else {}
            return {"mode": "login-only", "login_state": login_state, "profile_check": check}

        login_state = wait_for_login(driver, args.login_timeout_seconds)
        if login_state.get("status") != "logged_in":
            reason = f"login_not_verified:{login_state.get('status')}"
            print(f"[auto] {reason}", flush=True)
            return run_logged_out_fallback(args, run_id, reason)

        check = ensure_logged_in_profile_access(driver)
        if check.get("status") != "ok":
            reason = f"profile_access_not_ok:{check.get('status')}"
            print(f"[auto] {reason}", flush=True)
            return run_logged_out_fallback(args, run_id, reason)

        return run_logged_in_dataset(driver, args, run_id)
    except CrawlBlocked as exc:
        reason = f"crawl_blocked:{exc}"
        print(f"[auto] {reason}", flush=True)
        return run_logged_out_fallback(args, run_id, reason)
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Threads logged-in organizer profile collector")
    parser.add_argument("--mode", choices=["auto", "login-only", "fallback"], default="auto")
    parser.add_argument("--smoke", action="store_true", help="2 seeds, 3 handles, 20 profile posts")
    parser.add_argument("--profile-dir", default=str(DEFAULT_PROFILE_DIR))
    parser.add_argument("--fallback-profile-dir", default=str(DEFAULT_FALLBACK_PROFILE_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--keywords", default="")
    parser.add_argument("--keywords-file", default="")
    parser.add_argument("--seed-count", type=int, default=0)
    parser.add_argument("--fallback-seed-count", type=int, default=6)
    parser.add_argument("--max-search-cards", type=int, default=45)
    parser.add_argument("--max-search-scrolls", type=int, default=14)
    parser.add_argument("--max-handles", type=int, default=50)
    parser.add_argument("--max-profile-posts", type=int, default=80)
    parser.add_argument("--max-profile-scrolls", type=int, default=28)
    parser.add_argument("--min-profile-posts", type=int, default=15)
    parser.add_argument("--min-strict-evidence", type=int, default=2)
    parser.add_argument("--fallback-max-search-cards", type=int, default=80)
    parser.add_argument("--fallback-max-search-scrolls", type=int, default=20)
    parser.add_argument("--idle-limit", type=int, default=5)
    parser.add_argument("--login-timeout-seconds", type=int, default=600)
    parser.add_argument("--max-block-events", type=int, default=3)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()
    if args.smoke:
        args.max_handles = min(args.max_handles, 3)
        args.max_profile_posts = min(args.max_profile_posts, 20)
        args.max_search_cards = min(args.max_search_cards, 35)
        args.max_search_scrolls = min(args.max_search_scrolls, 10)
        args.fallback_max_search_cards = min(args.fallback_max_search_cards, 50)
        args.fallback_max_search_scrolls = min(args.fallback_max_search_scrolls, 12)
    return args


def main() -> None:
    args = parse_args()
    if args.mode == "fallback":
        result = run_logged_out_fallback(args, now_stamp(), "manual_fallback_mode")
    else:
        result = run_auto(args)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
