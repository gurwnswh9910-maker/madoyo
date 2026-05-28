from __future__ import annotations

import argparse
import json
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pandas as pd
from google import genai


ROOT_DIR = Path(__file__).resolve().parents[1]
AUTO_DIR = ROOT_DIR / "자동화"
CODE_DIR = ROOT_DIR / "작동중코드"

sys.path.insert(0, str(AUTO_DIR))
sys.path.insert(0, str(CODE_DIR))

from app_config import GlobalConfig  # noqa: E402
from marketing_focus_extractor import extract_marketing_focus  # noqa: E402
import optimize_copy_v2  # noqa: E402
from optimize_copy_v2 import run_optimization  # noqa: E402


MEDIA_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".m4v"}


def find_excel(dataset_dir: Path, explicit_excel: str | None) -> Path:
    if explicit_excel:
        excel = Path(explicit_excel)
        if not excel.exists():
            raise FileNotFoundError(f"Excel file not found: {excel}")
        return excel

    files = sorted(dataset_dir.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"No .xlsx file found in {dataset_dir}")
    return files[0]


def read_target_rows(excel_path: Path, target_hash: str | None, limit: int) -> list[dict[str, Any]]:
    df = pd.read_excel(excel_path, engine="openpyxl")
    required = {"본문", "미디어_해시값"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns in {excel_path}: {sorted(missing)}")

    if target_hash:
        df = df[df["미디어_해시값"].astype(str).str.strip() == target_hash]
        if df.empty:
            raise ValueError(f"Hash {target_hash!r} not found in {excel_path}")

    rows = []
    for _, row in df.head(limit).iterrows():
        body = str(row.get("본문", "") or "").strip()
        media_hash = str(row.get("미디어_해시값", "") or "").strip()
        if not body or not media_hash:
            continue
        rows.append(
            {
                "body": body,
                "media_hash": media_hash,
                "link": str(row.get("링크", "") or "").strip(),
            }
        )
    return rows


def collect_media_files(dataset_dir: Path, media_hash: str, media_limit: int | None) -> list[str]:
    folder = dataset_dir / media_hash
    if not folder.exists():
        raise FileNotFoundError(f"Media folder not found: {folder}")

    files = [
        p
        for p in sorted(folder.iterdir(), key=lambda path: path.name)
        if p.is_file() and p.suffix.lower() in MEDIA_EXTENSIONS
    ]
    if media_limit is not None:
        files = files[:media_limit]
    if not files:
        raise FileNotFoundError(f"No media files found in {folder}")
    return [str(p) for p in files]


@contextmanager
def candidate_sleep_patch(disable_candidate_sleep: bool):
    real_sleep = time.sleep
    stats = {"skipped_sleep_count": 0, "skipped_sleep_seconds": 0.0}

    def wrapped_sleep(seconds):
        try:
            value = float(seconds)
        except Exception:
            return real_sleep(seconds)

        if disable_candidate_sleep and abs(value - 1.5) < 1e-9:
            stats["skipped_sleep_count"] += 1
            stats["skipped_sleep_seconds"] += value
            return None
        return real_sleep(seconds)

    optimize_copy_v2.time.sleep = wrapped_sleep
    try:
        yield stats
    finally:
        optimize_copy_v2.time.sleep = real_sleep


def preview(text: str, limit: int = 120) -> str:
    text = " ".join((text or "").split())
    return text[:limit] + ("..." if len(text) > limit else "")


def run_one(
    row: dict[str, Any],
    dataset_dir: Path,
    client: genai.Client,
    shared_resources: dict[str, Any],
    embedding_mode: str,
    media_limit: int | None,
    disable_candidate_sleep: bool,
) -> dict[str, Any]:
    media_files = collect_media_files(dataset_dir, row["media_hash"], media_limit)
    started = time.perf_counter()

    print(f"[sample] hash={row['media_hash']} media={len(media_files)} mode={embedding_mode}", flush=True)
    print(f"[sample] body={preview(row['body'])}", flush=True)

    focus_started = time.perf_counter()
    product_focus = extract_marketing_focus(
        client,
        GlobalConfig.MODEL_NAME,
        "",
        row["body"],
        media_files,
        coupang_images=None,
    )
    focus_seconds = time.perf_counter() - focus_started

    optimization_media = media_files if embedding_mode == "media" else None
    optimize_started = time.perf_counter()
    with candidate_sleep_patch(disable_candidate_sleep) as sleep_stats:
        payload = run_optimization(
            original_copy=row["body"],
            product_focus=product_focus,
            input_image_urls=optimization_media,
            shared_resources=shared_resources,
            return_metadata=True,
        )
    optimize_seconds = time.perf_counter() - optimize_started

    meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
    top_results = payload.get("top_results", []) if isinstance(payload, dict) else []
    return {
        "media_hash": row["media_hash"],
        "link": row.get("link", ""),
        "media_files": media_files,
        "embedding_mode": embedding_mode,
        "model": GlobalConfig.MODEL_NAME,
        "embedding_model": GlobalConfig.EMBEDDING_MODEL,
        "body_preview": preview(row["body"]),
        "focus_seconds": round(focus_seconds, 3),
        "optimize_seconds": round(optimize_seconds, 3),
        "total_seconds": round(time.perf_counter() - started, 3),
        "candidate_sleep_disabled": disable_candidate_sleep,
        "skipped_sleep_count": sleep_stats["skipped_sleep_count"],
        "skipped_sleep_seconds": round(sleep_stats["skipped_sleep_seconds"], 3),
        "candidate_count": meta.get("candidate_count"),
        "candidate_count_before_filter": meta.get("candidate_count_before_filter"),
        "candidate_count_after_filter": meta.get("candidate_count_after_filter"),
        "accepted_generated_copy_count": meta.get("accepted_generated_copy_count"),
        "returned_generated_copy_count": meta.get("returned_generated_copy_count"),
        "scheduled_generation_tasks": meta.get("scheduled_generation_tasks"),
        "successful_generation_tasks": meta.get("successful_generation_tasks"),
        "failed_generation_tasks": meta.get("failed_generation_tasks"),
        "embedding_cache_hits": meta.get("embedding_cache_hits"),
        "embedding_cache_misses": meta.get("embedding_cache_misses"),
        "original_rank": meta.get("original_rank"),
        "top_copy_preview": preview(top_results[0].get("copy", "")) if top_results else "",
        "generation_failures": meta.get("generation_failures", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run copy generation from a local Excel/media folder with candidate sleep removed."
    )
    parser.add_argument(
        "--dataset-dir",
        default=os.getenv("MADOYO_VERIFY_DATASET_DIR", str(ROOT_DIR / "tmp" / "verify_no_sleep_dataset")),
    )
    parser.add_argument("--excel")
    parser.add_argument("--hash")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--media-limit", type=int, default=None)
    parser.add_argument(
        "--embedding-mode",
        choices=["text-only", "media"],
        default="text-only",
        help="text-only uses uploaded media only for marketing focus, then optimizes from returned text.",
    )
    parser.add_argument("--keep-candidate-sleep", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()

    dataset_dir = Path(args.dataset_dir)
    if not dataset_dir.exists():
        raise FileNotFoundError(f"Dataset directory not found: {dataset_dir}")

    excel_path = find_excel(dataset_dir, args.excel)
    rows = read_target_rows(excel_path, args.hash, args.limit)
    if not rows:
        raise ValueError("No usable rows found.")

    print(f"[input] dataset={dataset_dir}", flush=True)
    print(f"[input] excel={excel_path}", flush=True)
    print(f"[input] rows={len(rows)}", flush=True)
    print(
        "[rate-note] One row can schedule up to 18 generation calls and one embedding call per accepted candidate.",
        flush=True,
    )

    client = genai.Client(api_key=GlobalConfig.GEMINI_API_KEY)
    shared_resources: dict[str, Any] = {}
    results = [
        run_one(
            row=row,
            dataset_dir=dataset_dir,
            client=client,
            shared_resources=shared_resources,
            embedding_mode=args.embedding_mode,
            media_limit=args.media_limit,
            disable_candidate_sleep=not args.keep_candidate_sleep,
        )
        for row in rows
    ]

    summary = {
        "dataset_dir": str(dataset_dir),
        "excel": str(excel_path),
        "row_count": len(results),
        "results": results,
    }
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(text)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
        print(f"[output] wrote {output_path}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
