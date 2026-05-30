import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd


DEFAULT_CACHE_ROOT = Path(os.getenv("MADOYO_POST_CACHE_ROOT", "E:/madoyo_cache"))
POSTS_DIR = DEFAULT_CACHE_ROOT / "posts"
INDEX_PATH = DEFAULT_CACHE_ROOT / "post_index.xlsx"
STRONG_ORIGINAL_RANK_THRESHOLD = 10
INDEX_SYNC_MODE = os.getenv("MADOYO_POST_INDEX_SYNC_MODE", "never").strip().lower()

TERMINAL_INDEX_STATUSES = {
    "posted",
    "partial_post_failure",
    "dry_run_completed",
    "text_missing",
    "coupang_missing",
    "deeplink_failed",
    "rehost_failed",
    "error",
}

INDEX_COLUMNS = [
    "post_hash",
    "threads_url",
    "status",
    "last_stage",
    "error_message",
    "target_accounts",
    "success_accounts",
    "failed_accounts",
    "original_copy",
    "original_copy_path",
    "original_rank",
    "is_original_strong",
    "strong_reason",
    "candidate_count_before_filter",
    "candidate_count_after_filter",
    "duplicate_similarity_threshold",
    "duplicate_rejection_count",
    "duplicate_rejected_pairs",
    "duplicate_filter_log_path",
    "embedding_cache_hits",
    "embedding_cache_misses",
    "embedding_cache_size",
    "rerank_reused_embedding_count",
    "generation_sibling_count",
    "generation_output_mode",
    "static_strategy_count",
    "dynamic_strategy_count",
    "static_generation_task_count",
    "dynamic_generation_task_count",
    "scheduled_generation_tasks",
    "completed_generation_tasks",
    "successful_generation_tasks",
    "failed_generation_tasks",
    "expected_generated_copy_count",
    "returned_generated_copy_count",
    "accepted_generated_copy_count",
    "undersized_generation_tasks",
    "undersized_generation_details",
    "generation_failures",
    "final_copy",
    "selected_copy_source",
    "product_name",
    "coupang_raw_url",
    "coupang_deep_link",
    "coupang_product_url",
    "product_image_url",
    "product_image_local_path",
    "source_media_count",
    "cached_media_count",
    "rehosted_media_count",
    "source_media_urls",
    "source_media_files",
    "rehosted_media_urls",
    "rehosted_media_path",
    "marketing_focus_path",
    "optimization_path",
    "cache_dir",
    "media_dir",
    "last_processed_at",
    "output_views",
]


def build_post_hash(threads_url: str) -> str:
    normalized = (threads_url or "").strip().lower()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def prepare_post_cache(threads_url: str):
    post_hash = build_post_hash(threads_url)
    post_dir = POSTS_DIR / post_hash
    media_dir = post_dir / "media"
    artifacts_dir = post_dir / "artifacts"

    for path in (DEFAULT_CACHE_ROOT, POSTS_DIR, post_dir, artifacts_dir):
        path.mkdir(parents=True, exist_ok=True)

    return {
        "post_hash": post_hash,
        "threads_url": threads_url,
        "post_dir": post_dir,
        "media_dir": media_dir,
        "artifacts_dir": artifacts_dir,
        "metadata_path": post_dir / "metadata.json",
    }


def write_text_file(path, text: str):
    if text is None:
        return None
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(text), encoding="utf-8")
    return str(path)


def write_json_file(path, data):
    def _json_default(value):
        if isinstance(value, Path):
            return str(value)
        if hasattr(value, "item"):
            try:
                return value.item()
            except Exception:
                pass
        return str(value)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=_json_default)
    return str(path)


def _load_metadata(path: Path):
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _normalize_index_value(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value


def _build_index_row(record):
    row = {}
    for column in INDEX_COLUMNS:
        row[column] = _normalize_index_value(record.get(column, ""))
    return row


def _should_write_index(record, force=None):
    if force is not None:
        return bool(force)

    if INDEX_SYNC_MODE == "always":
        return True
    if INDEX_SYNC_MODE == "never":
        return False

    status = str((record or {}).get("status", "")).strip().lower()
    return status in TERMINAL_INDEX_STATUSES


def rebuild_index_from_metadata():
    rows = []
    if POSTS_DIR.exists():
        for metadata_path in POSTS_DIR.glob("*/metadata.json"):
            record = _load_metadata(metadata_path)
            if not record:
                continue
            rows.append(_build_index_row(record))

    posts_df = pd.DataFrame(rows, columns=INDEX_COLUMNS)
    if not posts_df.empty and "last_processed_at" in posts_df.columns:
        posts_df = posts_df.sort_values("last_processed_at", ascending=False, na_position="last")

    _write_index_workbook(posts_df)
    return len(posts_df)


def _load_posts_sheet():
    if not INDEX_PATH.exists():
        return pd.DataFrame(columns=INDEX_COLUMNS)
    try:
        df = pd.read_excel(INDEX_PATH, sheet_name="posts")
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame(columns=INDEX_COLUMNS)
    except Exception:
        return pd.DataFrame(columns=INDEX_COLUMNS)


def _write_index_workbook(posts_df: pd.DataFrame):
    posts_df = posts_df.copy()
    for column in INDEX_COLUMNS:
        if column not in posts_df.columns:
            posts_df[column] = ""
    posts_df = posts_df[INDEX_COLUMNS]

    original_ranks = pd.to_numeric(posts_df["original_rank"], errors="coerce")
    strong_flag_mask = posts_df["is_original_strong"].astype(str).str.lower().isin(["true", "1"])
    strong_df = posts_df[
        strong_flag_mask
        | original_ranks.between(1, STRONG_ORIGINAL_RANK_THRESHOLD, inclusive="both")
    ]

    with pd.ExcelWriter(INDEX_PATH, engine="openpyxl", mode="w") as writer:
        posts_df.to_excel(writer, sheet_name="posts", index=False)
        strong_df.to_excel(writer, sheet_name="strong_originals", index=False)


def persist_post_record(cache_info, updates: dict, write_index=None):
    metadata_path = cache_info["metadata_path"]
    existing = _load_metadata(metadata_path)

    merged = dict(existing)
    for key, value in (updates or {}).items():
        merged[key] = value

    merged["post_hash"] = cache_info["post_hash"]
    merged["threads_url"] = cache_info["threads_url"]
    merged["cache_dir"] = str(cache_info["post_dir"])
    merged["media_dir"] = str(cache_info["media_dir"])
    merged["last_processed_at"] = datetime.now().isoformat(timespec="seconds")

    try:
        write_json_file(metadata_path, merged)
    except Exception as e:
        print(f"⚠️ [PostCache] metadata 저장 실패: {e}")

    if _should_write_index(merged, force=write_index):
        try:
            posts_df = _load_posts_sheet()
            row = _build_index_row(merged)
            if "post_hash" in posts_df.columns and not posts_df.empty:
                posts_df = posts_df[posts_df["post_hash"] != cache_info["post_hash"]]
            posts_df = pd.concat([posts_df, pd.DataFrame([row])], ignore_index=True)
            _write_index_workbook(posts_df)
        except Exception as e:
            print(f"⚠️ [PostCache] 인덱스 저장 실패: {e}")

    return merged
