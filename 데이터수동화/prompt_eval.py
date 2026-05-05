import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from google import genai


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(__file__).resolve().parent
CODE_DIR = BASE_DIR / "작동중코드"
AUTO_DIR = BASE_DIR / "자동화"

for path in (AUTO_DIR, CODE_DIR, DATA_DIR):
    sys.path.insert(0, str(path))

from app_config import GlobalConfig
from data_manual_pipeline import (
    DEFAULT_DB_PATH,
    DEFAULT_RUNS_DIR,
    init_db,
    insert_run,
    json_text,
    save_raw_candidates,
    save_source_post,
    write_run_summary,
)
from optimize_copy_v2 import run_optimization


def load_source_posts(db_path: Path, source_run_id: str) -> pd.DataFrame:
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(
            """
            SELECT *
            FROM source_posts
            WHERE run_id = ? AND status = 'completed'
            ORDER BY row_index
            """,
            conn,
            params=(source_run_id,),
        )


def decode_json(value, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def main():
    parser = argparse.ArgumentParser(description="저장된 데이터수동화 원천 데이터로 새 프롬프트 버전 평가")
    parser.add_argument("--source-run-id", required=True, help="스크래핑/원천 데이터가 있는 baseline run_id")
    parser.add_argument("--generator-version", required=True, help="평가할 프롬프트/생성기 버전")
    parser.add_argument("--db-path", help="SQLite DB 경로")
    parser.add_argument("--runs-dir", help="run 산출물 폴더")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    db_path = Path(args.db_path).expanduser().resolve() if args.db_path else DEFAULT_DB_PATH
    runs_dir = Path(args.runs_dir).expanduser().resolve() if args.runs_dir else DEFAULT_RUNS_DIR
    run_id = f"prompt_eval_{args.generator_version}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    init_db(db_path)
    insert_run(
        db_path,
        run_id,
        Path(f"db://source_run/{args.source_run_id}"),
        args.generator_version,
        notes=f"prompt eval from {args.source_run_id}",
    )

    posts = load_source_posts(db_path, args.source_run_id)
    if args.limit and args.limit > 0:
        posts = posts.head(args.limit)
    if posts.empty:
        raise SystemExit(f"완료된 source_posts가 없습니다: {args.source_run_id}")

    print(f"prompt_eval run_id: {run_id}")
    print(f"source_run_id: {args.source_run_id}")
    print(f"generator_version: {args.generator_version}")
    print(f"SQLite DB: {db_path}")
    print(f"rows: {len(posts)}")
    print("스크래핑 없이 저장된 원본/미디어/상품/marketing_focus를 재사용합니다.")

    client = genai.Client(api_key=GlobalConfig.GEMINI_API_KEY)
    shared_resources = {"genai_client": client}

    for _, post in posts.iterrows():
        row_index = int(post["row_index"])
        url = str(post["url"])
        print(f"\n[{row_index + 1}] {url}", flush=True)

        payload = post.to_dict()
        payload["run_id"] = run_id
        payload["status"] = "started"
        payload["error_message"] = ""

        try:
            original_text = str(post["original_text"] or "")
            product_image = str(post["product_image"] or "")
            local_media_paths = decode_json(post["local_media_paths_json"], [])
            marketing_focus = decode_json(post["marketing_focus_json"], {})
            candidate_images = list(local_media_paths)
            if product_image:
                candidate_images.append(product_image)

            raw_candidates = []
            optimization_payload = run_optimization(
                original_copy=original_text,
                product_focus=marketing_focus,
                input_image_urls=candidate_images or None,
                shared_resources=shared_resources,
                return_metadata=True,
                raw_candidate_collector=raw_candidates,
                generator_version=args.generator_version,
            )
            meta = optimization_payload.get("meta", {}) if isinstance(optimization_payload, dict) else {}
            final_candidates = meta.get("all_candidates", []) if isinstance(meta, dict) else []

            payload["status"] = "completed"
            payload["optimization_meta_json"] = json_text(meta)
            save_source_post(db_path, row_index, {
                "run_id": run_id,
                "url": url,
                "status": "completed",
                "error_message": "",
                "original_text": original_text,
                "product_name": str(post["product_name"] or ""),
                "product_image": product_image,
                "deep_link": str(post["deep_link"] or ""),
                "raw_coupang_url": str(post["raw_coupang_url"] or ""),
                "media_folder": str(post["media_folder"] or ""),
                "source_media_urls": decode_json(post["source_media_urls_json"], []),
                "local_media_paths": local_media_paths,
                "marketing_focus": marketing_focus,
                "optimization_meta": meta,
            })
            save_raw_candidates(db_path, run_id, row_index, url, raw_candidates, final_candidates)
            print(
                f"  [저장] raw={len(raw_candidates)} accepted={meta.get('accepted_generated_copy_count', 0)} "
                f"original_rank={meta.get('original_rank', '')}",
                flush=True,
            )
        except Exception as exc:
            save_source_post(db_path, row_index, {
                "run_id": run_id,
                "url": url,
                "status": "error",
                "error_message": str(exc),
            })
            print(f"  오류: {exc}", flush=True)

    summary = write_run_summary(db_path, run_id, run_dir)
    print("\nprompt_eval 완료")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
