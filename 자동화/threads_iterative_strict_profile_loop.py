# -*- coding: utf-8 -*-
"""Iterative Threads strict organizer profile discovery loop.

The loop keeps a durable keyword/profile ledger so future runs can continue
from the last useful frontier instead of starting from scratch.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from threads_loggedin_profile_dataset import (
    CrawlBlocked,
    add_performance_labels,
    autosize_workbook,
    build_organizers,
    collect_profile_cards,
    collect_search_cards,
    ensure_logged_in_profile_access,
    init_db,
    make_driver,
    parse_seeds,
    persist_organizers,
    persist_rows,
    pick_candidate_handles,
    wait_for_login,
    write_jsonl,
)


try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = BASE_DIR / "organizer_research_runs"
DEFAULT_PROFILE_DIR = BASE_DIR / "threads_browser_profile"
DEFAULT_STATE_PATH = DEFAULT_OUTPUT_DIR / "threads_iterative_strict_profile_state.json"

INITIAL_KEYWORDS = [
    "커피챗",
    "밋업",
    "네트워킹",
    "북클럽",
    "친구 만들기",
    "커피챗 할 사람",
    "나랑 커피챗",
    "커피챗 하실 분",
    "네트워킹 주최",
    "네트워킹 모집",
    "밋업 모집",
    "밋업 주최",
    "북클럽 모집",
    "독서모임 모집",
    "친구모임 모집",
    "소셜링 모집",
    "대화모임 모집",
    "취향모임 모집",
    "오프라인 모임 모집",
    "참여자 모집",
]

EXPANSION_SUFFIXES = [
    "모집",
    "주최",
    "열어요",
    "하실 분",
    "할 사람",
    "참여자",
    "신청",
]


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "tested_keywords": [],
            "keyword_stats": {},
            "collected_handles": [],
            "accepted_profiles": {},
            "rejected_profiles": {},
            "keyword_pool": list(INITIAL_KEYWORDS),
            "run_history": [],
        }
    with path.open("r", encoding="utf-8-sig") as handle:
        state = json.load(handle)
    state.setdefault("tested_keywords", [])
    state.setdefault("keyword_stats", {})
    state.setdefault("collected_handles", [])
    state.setdefault("accepted_profiles", {})
    state.setdefault("rejected_profiles", {})
    state.setdefault("keyword_pool", list(INITIAL_KEYWORDS))
    state.setdefault("run_history", [])
    return state


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = now_iso()
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
    tmp.replace(path)


def normalize_handle(handle: Any) -> str:
    return str(handle or "").strip().lstrip("@").lower()


def dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("post_url") or "").strip()
        if key:
            deduped[key] = row
    return list(deduped.values())


def choose_keywords(state: dict[str, Any], batch_size: int) -> list[str]:
    tested = set(state.get("tested_keywords", []))
    pool = list(dict.fromkeys(state.get("keyword_pool", []) + INITIAL_KEYWORDS))
    chosen = [keyword for keyword in pool if keyword not in tested][:batch_size]
    return chosen


def expand_keyword_pool(state: dict[str, Any], batch_keyword_stats: list[dict[str, Any]]) -> None:
    pool = list(state.get("keyword_pool", []))
    for stat in batch_keyword_stats:
        keyword = stat["keyword"]
        if stat["strict_posts"] <= 0:
            continue
        base_parts = [keyword]
        if " " in keyword:
            base_parts.append(keyword.split()[0])
        for base in base_parts:
            for suffix in EXPANSION_SUFFIXES:
                expanded = f"{base} {suffix}".strip()
                if expanded not in pool:
                    pool.append(expanded)
    state["keyword_pool"] = pool


def update_keyword_stats(state: dict[str, Any], batch_keyword_stats: list[dict[str, Any]]) -> None:
    stats = state.setdefault("keyword_stats", {})
    for item in batch_keyword_stats:
        keyword = item["keyword"]
        prev = stats.get(keyword, {})
        merged = dict(prev)
        for key in [
            "raw_posts",
            "strict_posts",
            "candidate_handles",
            "new_candidate_handles",
            "accepted_profiles",
            "rejected_profiles",
        ]:
            merged[key] = int(prev.get(key, 0) or 0) + int(item.get(key, 0) or 0)
        merged["last_run_at"] = now_iso()
        if merged["raw_posts"]:
            merged["strict_rate"] = round(merged["strict_posts"] / merged["raw_posts"], 4)
        else:
            merged["strict_rate"] = 0.0
        merged["status"] = keyword_status(merged)
        stats[keyword] = merged


def keyword_status(stat: dict[str, Any]) -> str:
    if int(stat.get("accepted_profiles", 0) or 0) > 0:
        return "success_profile"
    if int(stat.get("strict_posts", 0) or 0) >= 3:
        return "promising"
    if int(stat.get("raw_posts", 0) or 0) < 5:
        return "low_volume"
    if int(stat.get("strict_posts", 0) or 0) == 0:
        return "failed_no_strict"
    return "weak"


def map_keyword_to_handles(search_rows: list[dict[str, Any]]) -> dict[str, set[str]]:
    mapping: dict[str, set[str]] = defaultdict(set)
    for row in search_rows:
        if int(row.get("relationship_host_label") or 0) != 1:
            continue
        keyword = str(row.get("source_seed") or "").strip()
        handle = normalize_handle(row.get("handle"))
        if keyword and handle:
            mapping[keyword].add(handle)
    return mapping


def build_posts_primary(raw_df: pd.DataFrame, context_df: pd.DataFrame, accepted_handles: set[str]) -> pd.DataFrame:
    if raw_df.empty or not accepted_handles:
        return pd.DataFrame(columns=raw_df.columns)
    primary = raw_df[
        raw_df["handle"].astype(str).str.lower().isin(accepted_handles)
        & (raw_df["usable_for_copy_scorer"] == 1)
    ].copy()
    primary = primary.drop_duplicates(subset=["post_url"], keep="last")
    if not context_df.empty:
        context_df = add_performance_labels(context_df.copy())
        primary = primary.merge(
            context_df[["post_url", "author_percentile", "performance_bucket"]],
            on="post_url",
            how="left",
        )
    if "author_percentile" not in primary.columns:
        primary["author_percentile"] = 0.0
    if "performance_bucket" not in primary.columns:
        primary["performance_bucket"] = "search_evidence"
    primary["author_percentile"] = primary["author_percentile"].fillna(0.0)
    primary["performance_bucket"] = primary["performance_bucket"].fillna("search_evidence")
    return primary


def write_loop_outputs(
    *,
    output_dir: Path,
    db_path: Path,
    run_id: str,
    state: dict[str, Any],
    batch_summaries: list[dict[str, Any]],
    all_search_rows: list[dict[str, Any]],
    all_profile_rows: list[dict[str, Any]],
    organizers: pd.DataFrame,
    args: argparse.Namespace,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    search_df = pd.DataFrame(dedupe_rows(all_search_rows))
    profile_df = pd.DataFrame(dedupe_rows(all_profile_rows))
    raw_df = pd.concat([search_df, profile_df], ignore_index=True) if not search_df.empty or not profile_df.empty else pd.DataFrame()

    strict_profiles = organizers[organizers["included_primary"] == 1].copy() if not organizers.empty else organizers
    accepted_handles = set(strict_profiles["handle"].astype(str).str.lower()) if not strict_profiles.empty else set()
    context_df = (
        profile_df[profile_df["handle"].astype(str).str.lower().isin(accepted_handles)].copy()
        if not profile_df.empty and accepted_handles
        else pd.DataFrame(columns=profile_df.columns)
    )
    if not context_df.empty:
        context_df = add_performance_labels(context_df)
    posts_primary = build_posts_primary(raw_df, context_df, accepted_handles)

    keyword_stats_df = pd.DataFrame(
        [
            {"keyword": keyword, **values}
            for keyword, values in sorted(
                state.get("keyword_stats", {}).items(),
                key=lambda pair: (
                    pair[1].get("accepted_profiles", 0),
                    pair[1].get("strict_posts", 0),
                    pair[1].get("raw_posts", 0),
                ),
                reverse=True,
            )
        ]
    )

    quality = pd.DataFrame(
        [
            {"metric": "run_id", "value": run_id},
            {"metric": "mode", "value": "iterative_strict_profile_loop"},
            {"metric": "strict_profiles_this_run", "value": len(strict_profiles)},
            {"metric": "strict_profiles_state_total", "value": len(state.get("accepted_profiles", {}))},
            {"metric": "target_profiles", "value": args.target_profiles},
            {"metric": "elapsed_minutes_goal", "value": args.min_minutes},
            {"metric": "tested_keywords_state_total", "value": len(state.get("tested_keywords", []))},
            {"metric": "raw_posts_this_run", "value": len(raw_df)},
            {"metric": "profile_posts_this_run", "value": len(profile_df)},
            {"metric": "posts_primary_ml_this_run", "value": len(posts_primary)},
            {"metric": "min_profile_posts", "value": args.min_profile_posts},
            {"metric": "min_strict_evidence", "value": args.min_strict_evidence},
            {"metric": "state_path", "value": str(args.state_path)},
        ]
    )

    rejected = organizers[organizers["included_primary"] != 1].copy() if not organizers.empty else organizers
    excluded_ambiguous = raw_df[raw_df["post_policy_status"].eq("ambiguous_or_weak")] if not raw_df.empty else raw_df
    excluded_learning = (
        raw_df[raw_df["post_policy_status"].isin(["excluded_learning", "excluded_exercise"])]
        if not raw_df.empty
        else raw_df
    )

    xlsx_path = output_dir / f"threads_iterative_strict_profiles_{run_id}.xlsx"
    jsonl_path = output_dir / f"threads_iterative_strict_profiles_{run_id}.jsonl"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        quality.to_excel(writer, sheet_name="loop_quality_summary", index=False)
        strict_profiles.to_excel(writer, sheet_name="strict_profiles", index=False)
        posts_primary.to_excel(writer, sheet_name="posts_primary_ml", index=False)
        context_df.to_excel(writer, sheet_name="profile_posts_context", index=False)
        keyword_stats_df.to_excel(writer, sheet_name="keyword_stats_state", index=False)
        pd.DataFrame(batch_summaries).to_excel(writer, sheet_name="batch_summaries", index=False)
        raw_df.to_excel(writer, sheet_name="posts_raw_all", index=False)
        rejected.to_excel(writer, sheet_name="rejected_profiles", index=False)
        excluded_ambiguous.to_excel(writer, sheet_name="excluded_ambiguous", index=False)
        excluded_learning.to_excel(writer, sheet_name="excluded_learning_exercise", index=False)
    autosize_workbook(xlsx_path)
    write_jsonl(jsonl_path, raw_df.to_dict("records") if not raw_df.empty else [])

    conn = init_db(db_path)
    try:
        persist_rows(conn, raw_df.to_dict("records") if not raw_df.empty else [])
        persist_organizers(conn, organizers, run_id)
    finally:
        conn.close()

    return {
        "xlsx_path": str(xlsx_path),
        "jsonl_path": str(jsonl_path),
        "sqlite_path": str(db_path),
        "strict_profiles_this_run": len(strict_profiles),
        "strict_profiles_state_total": len(state.get("accepted_profiles", {})),
        "posts_primary_ml_this_run": len(posts_primary),
        "keyword_stats_path": str(args.state_path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Iterative strict Threads organizer profile loop")
    parser.add_argument("--profile-dir", default=str(DEFAULT_PROFILE_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--state-path", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--sqlite-path", default="")
    parser.add_argument("--target-profiles", type=int, default=15)
    parser.add_argument("--min-minutes", type=float, default=40.0)
    parser.add_argument("--max-minutes", type=float, default=75.0)
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--max-search-cards", type=int, default=45)
    parser.add_argument("--max-search-scrolls", type=int, default=12)
    parser.add_argument("--handles-per-batch", type=int, default=8)
    parser.add_argument("--max-profile-posts", type=int, default=55)
    parser.add_argument("--max-profile-scrolls", type=int, default=22)
    parser.add_argument("--min-profile-posts", type=int, default=15)
    parser.add_argument("--min-strict-evidence", type=int, default=2)
    parser.add_argument("--idle-limit", type=int, default=5)
    parser.add_argument("--login-timeout-seconds", type=int, default=600)
    parser.add_argument("--max-block-events", type=int, default=3)
    parser.add_argument("--headless", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir = str(Path(args.output_dir))
    args.state_path = str(Path(args.state_path))
    output_dir = Path(args.output_dir)
    state_path = Path(args.state_path)
    sqlite_path = Path(args.sqlite_path) if args.sqlite_path else output_dir / "threads_organizer_dataset.sqlite"
    state = load_state(state_path)

    run_id = now_stamp()
    started = time.time()
    deadline = started + args.max_minutes * 60
    min_until = started + args.min_minutes * 60
    all_search_rows: list[dict[str, Any]] = []
    all_profile_rows: list[dict[str, Any]] = []
    all_candidates: list[dict[str, Any]] = []
    batch_summaries: list[dict[str, Any]] = []
    block_counter = {"count": 0}

    print(f"[loop] run_id={run_id}", flush=True)
    print(f"[loop] state_path={state_path}", flush=True)
    print(f"[loop] target={args.target_profiles} min_minutes={args.min_minutes} max_minutes={args.max_minutes}", flush=True)

    driver = make_driver(Path(args.profile_dir), headless=args.headless)
    try:
        login_state = wait_for_login(driver, args.login_timeout_seconds)
        if login_state.get("status") != "logged_in":
            raise SystemExit(f"login not verified: {login_state}")
        check = ensure_logged_in_profile_access(driver)
        if check.get("status") != "ok":
            raise SystemExit(f"profile access not ok: {check}")

        batch_index = 0
        while time.time() < deadline:
            accepted_total = len(state.get("accepted_profiles", {}))
            if time.time() >= min_until and accepted_total >= args.target_profiles:
                print("[loop] target reached after minimum duration", flush=True)
                break

            keywords = choose_keywords(state, args.batch_size)
            if not keywords:
                print("[loop] keyword pool exhausted; expanding from initial seeds", flush=True)
                state["keyword_pool"] = list(dict.fromkeys(state.get("keyword_pool", []) + INITIAL_KEYWORDS))
                keywords = choose_keywords(state, args.batch_size)
                if not keywords:
                    break

            batch_index += 1
            print(f"[batch {batch_index}] keywords={keywords}", flush=True)
            batch_search: list[dict[str, Any]] = []
            batch_keyword_stats: list[dict[str, Any]] = []
            for keyword in keywords:
                try:
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
                except CrawlBlocked as exc:
                    print(f"[batch {batch_index}] crawl blocked during keyword={keyword}: {exc}", flush=True)
                    rows = []
                    deadline = time.time()
                state["tested_keywords"] = list(dict.fromkeys(state.get("tested_keywords", []) + [keyword]))
                strict_posts = sum(1 for row in rows if int(row.get("relationship_host_label") or 0) == 1)
                candidate_handles = {
                    normalize_handle(row.get("handle"))
                    for row in rows
                    if int(row.get("relationship_host_label") or 0) == 1 and normalize_handle(row.get("handle"))
                }
                known_handles = set(state.get("collected_handles", []))
                batch_keyword_stats.append(
                    {
                        "keyword": keyword,
                        "raw_posts": len(rows),
                        "strict_posts": strict_posts,
                        "candidate_handles": len(candidate_handles),
                        "new_candidate_handles": len(candidate_handles - known_handles),
                        "accepted_profiles": 0,
                        "rejected_profiles": 0,
                    }
                )
                batch_search.extend(rows)
                all_search_rows.extend(rows)
                print(
                    f"[batch {batch_index}] keyword={keyword} raw={len(rows)} strict={strict_posts} candidates={len(candidate_handles)}",
                    flush=True,
                )

            candidates = pick_candidate_handles(batch_search, args.handles_per_batch)
            known_handles = set(state.get("collected_handles", []))
            candidates = [item for item in candidates if normalize_handle(item.get("handle")) not in known_handles]
            all_candidates.extend(candidates)
            print(f"[batch {batch_index}] new_candidate_profiles={len(candidates)}", flush=True)

            batch_profiles: list[dict[str, Any]] = []
            for index, candidate in enumerate(candidates, start=1):
                handle = candidate["handle"]
                print(f"[batch {batch_index}] profile {index}/{len(candidates)} @{handle}", flush=True)
                try:
                    rows = collect_profile_cards(
                        driver,
                        handle=handle,
                        run_id=run_id,
                        max_cards=args.max_profile_posts,
                        max_scrolls=args.max_profile_scrolls,
                        idle_limit=args.idle_limit,
                        block_counter=block_counter,
                        max_block_events=args.max_block_events,
                    )
                except CrawlBlocked as exc:
                    print(f"[batch {batch_index}] crawl blocked during profile=@{handle}: {exc}", flush=True)
                    deadline = time.time()
                    break
                batch_profiles.extend(rows)
                all_profile_rows.extend(rows)
                state["collected_handles"] = list(
                    dict.fromkeys(state.get("collected_handles", []) + [normalize_handle(handle)])
                )

            organizers = build_organizers(
                all_candidates,
                all_search_rows,
                all_profile_rows,
                args.min_profile_posts,
                args.min_strict_evidence,
            )
            accepted_handles = set()
            rejected_handles = set()
            if not organizers.empty:
                accepted = organizers[organizers["included_primary"] == 1].copy()
                rejected = organizers[organizers["included_primary"] != 1].copy()
                for row in accepted.to_dict("records"):
                    handle = normalize_handle(row.get("handle"))
                    accepted_handles.add(handle)
                    state.setdefault("accepted_profiles", {})[handle] = {
                        **row,
                        "last_seen_run_id": run_id,
                        "accepted_at": now_iso(),
                    }
                for row in rejected.to_dict("records"):
                    handle = normalize_handle(row.get("handle"))
                    rejected_handles.add(handle)
                    state.setdefault("rejected_profiles", {})[handle] = {
                        **row,
                        "last_seen_run_id": run_id,
                        "rejected_at": now_iso(),
                    }

            keyword_to_handles = map_keyword_to_handles(batch_search)
            for stat in batch_keyword_stats:
                handles = {normalize_handle(handle) for handle in keyword_to_handles.get(stat["keyword"], set())}
                stat["accepted_profiles"] = len(handles & accepted_handles)
                stat["rejected_profiles"] = len(handles & rejected_handles)

            update_keyword_stats(state, batch_keyword_stats)
            expand_keyword_pool(state, batch_keyword_stats)

            elapsed = round((time.time() - started) / 60, 2)
            batch_summary = {
                "run_id": run_id,
                "batch": batch_index,
                "elapsed_minutes": elapsed,
                "keywords": ", ".join(keywords),
                "search_rows_batch": len(batch_search),
                "profile_rows_batch": len(batch_profiles),
                "candidates_batch": len(candidates),
                "accepted_profiles_state_total": len(state.get("accepted_profiles", {})),
                "tested_keywords_state_total": len(state.get("tested_keywords", [])),
            }
            batch_summaries.append(batch_summary)
            state["run_history"].append(batch_summary)
            save_state(state_path, state)

            result = write_loop_outputs(
                output_dir=output_dir,
                db_path=sqlite_path,
                run_id=run_id,
                state=state,
                batch_summaries=batch_summaries,
                all_search_rows=all_search_rows,
                all_profile_rows=all_profile_rows,
                organizers=organizers,
                args=args,
            )
            print(
                f"[batch {batch_index}] saved accepted_total={result['strict_profiles_state_total']} "
                f"accepted_this_run={result['strict_profiles_this_run']} xlsx={result['xlsx_path']}",
                flush=True,
            )

            if time.time() >= deadline:
                break

        final_organizers = build_organizers(
            all_candidates,
            all_search_rows,
            all_profile_rows,
            args.min_profile_posts,
            args.min_strict_evidence,
        )
        final_result = write_loop_outputs(
            output_dir=output_dir,
            db_path=sqlite_path,
            run_id=run_id,
            state=state,
            batch_summaries=batch_summaries,
            all_search_rows=all_search_rows,
            all_profile_rows=all_profile_rows,
            organizers=final_organizers,
            args=args,
        )
        print(json.dumps(final_result, ensure_ascii=False, indent=2), flush=True)
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
