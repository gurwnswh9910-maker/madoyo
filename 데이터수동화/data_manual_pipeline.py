import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import pandas as pd
from google import genai


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(__file__).resolve().parent
AUTO_DIR = BASE_DIR / "자동화"
CODE_DIR = BASE_DIR / "작동중코드"
MANUAL_DIR = BASE_DIR / "수동화"

for path in (AUTO_DIR, CODE_DIR):
    sys.path.insert(0, str(path))

from app_config import GlobalConfig
from coupang_api import extract_and_convert_coupang_link, search_coupang_product
from marketing_focus_extractor import extract_marketing_focus
from optimize_copy_v2 import run_optimization
from scraper import (
    cache_media_locally,
    fetch_coupang_product_info,
    init_driver,
    scrape_comment_for_coupang,
    scrape_thread_content,
)


DEFAULT_INPUT_DIR = MANUAL_DIR / "수동화참조"
DEFAULT_MEDIA_DIR = DATA_DIR / "미디어"
DEFAULT_RUNS_DIR = DATA_DIR / "runs"
DEFAULT_DB_PATH = DATA_DIR / "data" / "runs.sqlite"
DEFAULT_GENERATOR_VERSION = "upgrade_v10"


class CoupangBlockedError(RuntimeError):
    pass


def safe_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def make_jsonable(value):
    if isinstance(value, dict):
        return {str(key): make_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [make_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [make_jsonable(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, Path):
        return str(value)
    return value


def json_text(payload) -> str:
    return json.dumps(make_jsonable(payload), ensure_ascii=False, sort_keys=True)


def find_link_column(df: pd.DataFrame) -> str:
    for column in df.columns:
        label = str(column)
        if "링크" in label or "url" in label.lower():
            return column
    raise SystemExit("입력 엑셀에서 링크 컬럼을 찾지 못했습니다.")


def pick_input_excel(input_excel: str | None, input_dir: Path) -> Path:
    if input_excel:
        path = Path(input_excel).expanduser().resolve()
        if not path.exists():
            raise SystemExit(f"입력 엑셀을 찾지 못했습니다: {path}")
        return path

    candidates = [
        path
        for path in sorted(input_dir.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not path.name.startswith("~$")
    ]
    if not candidates:
        raise SystemExit(f"입력 엑셀을 찾지 못했습니다: {input_dir}")
    return candidates[0]


def extract_post_id(url: str) -> str:
    match = re.search(r"/post/([^/?#]+)", safe_str(url))
    if match:
        return match.group(1)
    return hashlib.sha1(safe_str(url).encode("utf-8")).hexdigest()[:12]


def build_media_folder(media_root: Path, url: str, row_index: int) -> Path:
    post_id = extract_post_id(url)
    if post_id:
        return media_root / post_id
    digest = hashlib.sha1(safe_str(url).encode("utf-8")).hexdigest()[:10]
    return media_root / f"row_{row_index + 1:05d}_{digest}"


def init_db(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                input_excel TEXT NOT NULL,
                generator_version TEXT NOT NULL,
                notes TEXT
            );
            CREATE TABLE IF NOT EXISTS source_posts (
                run_id TEXT NOT NULL,
                row_index INTEGER NOT NULL,
                url TEXT NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT,
                original_text TEXT,
                product_name TEXT,
                product_image TEXT,
                deep_link TEXT,
                raw_coupang_url TEXT,
                media_folder TEXT,
                source_media_urls_json TEXT,
                local_media_paths_json TEXT,
                marketing_focus_json TEXT,
                optimization_meta_json TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY (run_id, row_index)
            );
            CREATE TABLE IF NOT EXISTS raw_candidates (
                run_id TEXT NOT NULL,
                row_index INTEGER NOT NULL,
                url TEXT NOT NULL,
                generator_version TEXT NOT NULL,
                candidate_id TEXT NOT NULL,
                task_cid TEXT,
                strategy TEXT,
                variant_index INTEGER,
                raw_copy TEXT,
                cleaned_copy TEXT,
                generation_time_sec REAL,
                accepted_after_filter INTEGER,
                final_rank INTEGER,
                final_total_score REAL,
                confidence_gate_json TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_raw_candidates_run_row
                ON raw_candidates(run_id, row_index);
            """
        )


def insert_run(db_path: Path, run_id: str, input_excel: Path, generator_version: str, notes: str = ""):
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO runs(run_id, created_at, input_excel, generator_version, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, datetime.now().isoformat(timespec="seconds"), str(input_excel), generator_version, notes),
        )


def save_source_post(db_path: Path, row_index: int, payload: dict):
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO source_posts(
                run_id, row_index, url, status, error_message, original_text, product_name,
                product_image, deep_link, raw_coupang_url, media_folder,
                source_media_urls_json, local_media_paths_json, marketing_focus_json,
                optimization_meta_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["run_id"],
                row_index,
                payload["url"],
                payload.get("status", ""),
                payload.get("error_message", ""),
                payload.get("original_text", ""),
                payload.get("product_name", ""),
                payload.get("product_image", ""),
                payload.get("deep_link", ""),
                payload.get("raw_coupang_url", ""),
                payload.get("media_folder", ""),
                json_text(payload.get("source_media_urls", [])),
                json_text(payload.get("local_media_paths", [])),
                json_text(payload.get("marketing_focus", {})),
                json_text(payload.get("optimization_meta", {})),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )


def save_raw_candidates(db_path: Path, run_id: str, row_index: int, url: str, raw_candidates: list[dict], final_candidates: list[dict]):
    final_by_id = {safe_str(item.get("cid")): item for item in final_candidates or []}
    now = datetime.now().isoformat(timespec="seconds")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "DELETE FROM raw_candidates WHERE run_id = ? AND row_index = ?",
            (run_id, row_index),
        )
        for item in raw_candidates:
            candidate_id = safe_str(item.get("candidate_id"))
            final_item = final_by_id.get(candidate_id, {})
            conn.execute(
                """
                INSERT INTO raw_candidates(
                    run_id, row_index, url, generator_version, candidate_id, task_cid,
                    strategy, variant_index, raw_copy, cleaned_copy, generation_time_sec,
                    accepted_after_filter, final_rank, final_total_score, confidence_gate_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    row_index,
                    url,
                    safe_str(item.get("generator_version")),
                    candidate_id,
                    safe_str(item.get("task_cid")),
                    safe_str(item.get("strategy")),
                    int(item.get("variant_index", 0)),
                    safe_str(item.get("raw_copy")),
                    safe_str(item.get("cleaned_copy")),
                    float(item.get("generation_time_sec", 0) or 0),
                    1 if final_item else 0,
                    int(final_item.get("rank", 0) or 0) if final_item else None,
                    float(final_item.get("total_score", 0) or 0) if final_item else None,
                    json_text(final_item.get("confidence_gate", {})) if final_item else "{}",
                    now,
                ),
            )


def resolve_coupang_payload(raw_coupang_url: str, driver) -> dict:
    product_info = fetch_coupang_product_info(raw_coupang_url, driver=driver)
    product_name = safe_str(product_info.get("product_name", ""))
    product_image = safe_str(product_info.get("image_url", ""))
    resolved_product_url = safe_str(product_info.get("product_url", ""))

    if product_info.get("is_blocked", False):
        raise CoupangBlockedError("쿠팡 Akamai Access Denied 감지")

    deep_link = extract_and_convert_coupang_link(raw_coupang_url, resolved_url=resolved_product_url)
    if not deep_link and product_name:
        search_res = search_coupang_product(product_name, limit=5)
        if search_res:
            deep_link = safe_str(search_res.get("product_url", ""))
            if not product_name:
                product_name = safe_str(search_res.get("product_name", ""))

    return {
        "product_name": product_name,
        "product_image": product_image,
        "deep_link": safe_str(deep_link),
    }


def process_row(
    *,
    run_id: str,
    row_index: int,
    row: pd.Series,
    link_column: str,
    media_root: Path,
    threads_driver,
    coupang_driver,
    coupang_executor: ThreadPoolExecutor,
    client,
    shared_resources: dict,
    generator_version: str,
    db_path: Path,
) -> dict:
    url = safe_str(row.get(link_column, ""))
    payload = {
        "run_id": run_id,
        "url": url,
        "status": "started",
        "error_message": "",
        "source_media_urls": [],
        "local_media_paths": [],
        "marketing_focus": {},
        "optimization_meta": {},
    }

    if not url.startswith("http"):
        payload["status"] = "invalid_url"
        payload["error_message"] = "유효한 URL이 없습니다."
        save_source_post(db_path, row_index, payload)
        return payload

    thread_info = scrape_thread_content(url, driver=threads_driver)
    original_text = safe_str(thread_info.get("text", "")) or safe_str(row.get("본문", ""))
    source_media_urls = thread_info.get("all_media", []) or thread_info.get("images", []) or []
    video_urls = thread_info.get("video_urls", []) or []
    coupang_urls = thread_info.get("coupang_urls", []) or []
    if not coupang_urls:
        comment_info = scrape_comment_for_coupang(url, driver=threads_driver)
        if comment_info:
            coupang_urls = comment_info.get("coupang_urls", []) or []
    raw_coupang_url = safe_str(coupang_urls[0]) if coupang_urls else ""

    payload["original_text"] = original_text
    payload["source_media_urls"] = source_media_urls
    payload["raw_coupang_url"] = raw_coupang_url

    coupang_future = None
    if raw_coupang_url:
        print("  [쿠팡] 상품/딥링크 처리 시작", flush=True)
        coupang_future = coupang_executor.submit(resolve_coupang_payload, raw_coupang_url, coupang_driver)

    media_folder = build_media_folder(media_root, url, row_index)
    if media_folder.exists():
        shutil.rmtree(media_folder, ignore_errors=True)
    local_media_paths = []
    if source_media_urls:
        local_media_paths = cache_media_locally(
            source_media_urls,
            media_folder,
            driver=threads_driver,
            video_urls=video_urls,
            prefix="media",
            max_items=10,
        )
    payload["media_folder"] = str(media_folder) if local_media_paths else ""
    payload["local_media_paths"] = [str(path) for path in local_media_paths]

    product_name = ""
    product_image = ""
    deep_link = ""
    if coupang_future:
        coupang_payload = coupang_future.result()
        product_name = coupang_payload["product_name"]
        product_image = coupang_payload["product_image"]
        deep_link = coupang_payload["deep_link"]
    payload["product_name"] = product_name
    payload["product_image"] = product_image
    payload["deep_link"] = deep_link

    if not original_text:
        payload["status"] = "text_missing"
        payload["error_message"] = "본문을 수집하지 못했습니다."
        save_source_post(db_path, row_index, payload)
        return payload

    candidate_images = list(local_media_paths)
    if product_image:
        candidate_images.append(product_image)

    marketing_focus = extract_marketing_focus(
        client,
        GlobalConfig.MODEL_NAME,
        product_name or "상품",
        original_text,
        [str(path) for path in local_media_paths],
        coupang_images=[product_image] if product_image else None,
    )
    payload["marketing_focus"] = marketing_focus

    raw_candidates: list[dict] = []
    optimization_payload = run_optimization(
        original_copy=original_text,
        product_focus=marketing_focus,
        input_image_urls=candidate_images or None,
        shared_resources=shared_resources,
        return_metadata=True,
        raw_candidate_collector=raw_candidates,
        generator_version=generator_version,
    )
    meta = optimization_payload.get("meta", {}) if isinstance(optimization_payload, dict) else {}
    payload["optimization_meta"] = meta
    payload["status"] = "completed"

    final_candidates = meta.get("all_candidates", []) if isinstance(meta, dict) else []
    save_source_post(db_path, row_index, payload)
    save_raw_candidates(db_path, run_id, row_index, url, raw_candidates, final_candidates)
    print(
        f"  [저장] raw={len(raw_candidates)} accepted={meta.get('accepted_generated_copy_count', 0)} "
        f"original_rank={meta.get('original_rank', '')}",
        flush=True,
    )
    return payload


def write_run_summary(db_path: Path, run_id: str, run_dir: Path):
    with sqlite3.connect(db_path) as conn:
        posts = pd.read_sql_query("SELECT * FROM source_posts WHERE run_id = ? ORDER BY row_index", conn, params=(run_id,))
        candidates = pd.read_sql_query("SELECT * FROM raw_candidates WHERE run_id = ? ORDER BY row_index, candidate_id", conn, params=(run_id,))

    status_counts = posts["status"].value_counts().to_dict() if not posts.empty else {}
    accepted_count = int(candidates["accepted_after_filter"].sum()) if not candidates.empty else 0
    summary = {
        "run_id": run_id,
        "status_counts": status_counts,
        "source_post_count": int(len(posts)),
        "raw_candidate_count": int(len(candidates)),
        "accepted_candidate_count": accepted_count,
        "db_path": str(db_path),
        "run_dir": str(run_dir),
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if not posts.empty:
        posts.to_csv(run_dir / "source_posts.csv", index=False, encoding="utf-8-sig")
    if not candidates.empty:
        candidates.to_csv(run_dir / "raw_candidates.csv", index=False, encoding="utf-8-sig")
    return summary


def main():
    parser = argparse.ArgumentParser(description="데이터수동화: URL 원천 데이터와 채점 전 raw copy 전체 저장")
    parser.add_argument("--input-excel", help="직접 지정할 입력 엑셀 경로")
    parser.add_argument("--input-dir", help="입력 엑셀 폴더. 기본값은 수동화/수동화참조")
    parser.add_argument("--db-path", help="SQLite 저장 경로")
    parser.add_argument("--media-dir", help="미디어 저장 폴더")
    parser.add_argument("--runs-dir", help="run 산출물 폴더")
    parser.add_argument("--generator-version", default=DEFAULT_GENERATOR_VERSION)
    parser.add_argument("--limit", type=int, default=0, help="앞에서 N개만 처리. 0이면 전체")
    args = parser.parse_args()

    input_dir = Path(args.input_dir).expanduser().resolve() if args.input_dir else DEFAULT_INPUT_DIR
    input_excel = pick_input_excel(args.input_excel, input_dir)
    db_path = Path(args.db_path).expanduser().resolve() if args.db_path else DEFAULT_DB_PATH
    media_dir = Path(args.media_dir).expanduser().resolve() if args.media_dir else DEFAULT_MEDIA_DIR
    runs_dir = Path(args.runs_dir).expanduser().resolve() if args.runs_dir else DEFAULT_RUNS_DIR
    run_id = f"data_manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    copied_input = run_dir / input_excel.name
    shutil.copy2(input_excel, copied_input)

    print(f"데이터수동화 run_id: {run_id}")
    print(f"입력 엑셀: {input_excel}")
    print(f"입력 사본: {copied_input}")
    print(f"SQLite DB: {db_path}")
    print(f"미디어 폴더: {media_dir}")
    print(f"생성기 버전: {args.generator_version}")

    init_db(db_path)
    insert_run(db_path, run_id, input_excel, args.generator_version)

    df = pd.read_excel(input_excel, engine="openpyxl")
    link_column = find_link_column(df)
    if args.limit and args.limit > 0:
        df = df.head(args.limit)

    client = genai.Client(api_key=GlobalConfig.GEMINI_API_KEY)
    shared_resources = {"genai_client": client}
    threads_driver = None
    coupang_driver = None
    coupang_executor = None

    try:
        print("Threads 브라우저 초기화...")
        threads_driver = init_driver()
        print("Coupang 전용 브라우저 초기화...")
        coupang_driver = init_driver()
        coupang_executor = ThreadPoolExecutor(max_workers=1)

        for row_index, row in df.iterrows():
            url = safe_str(row.get(link_column, ""))
            if not url:
                continue
            print(f"\n[{row_index + 1}/{len(df)}] {url}", flush=True)
            try:
                process_row(
                    run_id=run_id,
                    row_index=row_index,
                    row=row,
                    link_column=link_column,
                    media_root=media_dir,
                    threads_driver=threads_driver,
                    coupang_driver=coupang_driver,
                    coupang_executor=coupang_executor,
                    client=client,
                    shared_resources=shared_resources,
                    generator_version=args.generator_version,
                    db_path=db_path,
                )
            except CoupangBlockedError as exc:
                payload = {"run_id": run_id, "url": url, "status": "coupang_blocked", "error_message": str(exc)}
                save_source_post(db_path, row_index, payload)
                print(f"쿠팡 차단 감지로 중단: {exc}", flush=True)
                break
            except Exception as exc:
                payload = {"run_id": run_id, "url": url, "status": "error", "error_message": str(exc)}
                save_source_post(db_path, row_index, payload)
                print(f"  오류: {exc}", flush=True)

    finally:
        if coupang_executor:
            coupang_executor.shutdown(wait=False, cancel_futures=True)
        for driver in (threads_driver, coupang_driver):
            try:
                if driver:
                    driver.quit()
            except Exception:
                pass

    summary = write_run_summary(db_path, run_id, run_dir)
    print("\n데이터수동화 완료")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
