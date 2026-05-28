from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parent.parent
MEDIA_MANUAL_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = MEDIA_MANUAL_DIR / "미디어수동참조"
DEFAULT_RESULT_DIR = MEDIA_MANUAL_DIR / "미디어수동결과"
SEMI_AUTO_REF_DIR = ROOT_DIR / "반자동" / "반자동참조"
WORKING_CODE_DIR = ROOT_DIR / "작동중코드"

VALID_MEDIA_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov"}
MANIFEST_NAMES = ("manifest.xlsx", "manifest.csv", "미디어수동_manifest.xlsx", "미디어수동_manifest.csv")

BASE_RESULT_COLUMNS = [
    "링크",
    "본문",
    "상품명",
    "본문조회수",
    "작성시간",
    "좋아요",
    "답글수",
    "리포스트",
    "공유수",
    "첫댓글URL",
    "첫댓글조회수",
    "크롤링시간",
    "미디어_해시값",
    "미디어폴더",
    "미디어파일수",
    "원본미디어URL",
    "업로드미디어URL",
    "업로드미디어수",
    "카피1",
    "카피2",
    "카피3",
    "내쿠팡링크",
    "쿠팡원본링크",
    "처리상태",
    "오류메시지",
]

EXTRA_RESULT_COLUMNS = [
    "미디어수동폴더",
    "미디어파일목록",
    "검색방식",
    "유사본문1",
    "유사본문1_MSS",
    "유사본문1_Alpha",
    "유사본문2",
    "유사본문2_MSS",
    "유사본문2_Alpha",
    "유사본문3",
    "유사본문3_MSS",
    "유사본문3_Alpha",
    "생성후보수",
    "카피채점모드",
]

OUTPUT_COLUMNS = BASE_RESULT_COLUMNS + EXTRA_RESULT_COLUMNS
SEMI_AUTO_REQUIRED_COLUMNS = ["링크", "처리상태", "미디어폴더", "업로드미디어URL", "카피1", "카피2", "카피3", "내쿠팡링크"]


def natural_key(value: Any) -> list[Any]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", str(value))]


def safe_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    return str(value).strip()


def json_list(values: list[Any]) -> str:
    return json.dumps([str(value) for value in values if str(value)], ensure_ascii=False)


def find_column(df: pd.DataFrame, exact_names: list[str], contains: list[str] | None = None) -> str | None:
    columns = [str(col).strip() for col in df.columns]
    for name in exact_names:
        for col in columns:
            if col == name:
                return col
    for needle in contains or []:
        for col in columns:
            if needle.lower() in col.lower():
                return col
    return None


def load_manifest(input_dir: Path) -> tuple[dict[str, dict[str, Any]], str]:
    manifest_path = None
    for name in MANIFEST_NAMES:
        candidate = input_dir / name
        if candidate.exists():
            manifest_path = candidate
            break
    if manifest_path is None:
        return {}, ""

    if manifest_path.suffix.lower() == ".csv":
        df = pd.read_csv(manifest_path)
    else:
        df = pd.read_excel(manifest_path, engine="openpyxl")

    folder_col = find_column(df, ["폴더", "folder", "미디어폴더", "post_folder"], ["폴더", "folder"])
    if not folder_col:
        return {}, str(manifest_path)

    manifest: dict[str, dict[str, Any]] = {}
    for _, row in df.iterrows():
        folder_name = safe_str(row.get(folder_col, ""))
        if not folder_name:
            continue
        manifest[folder_name] = {str(col).strip(): row.get(col, "") for col in df.columns}
    return manifest, str(manifest_path)


def get_meta_value(meta: dict[str, Any], exact_names: list[str], contains: list[str] | None = None) -> str:
    if not meta:
        return ""
    for name in exact_names:
        if name in meta:
            return safe_str(meta.get(name))
    for needle in contains or []:
        for key, value in meta.items():
            if needle.lower() in str(key).lower():
                return safe_str(value)
    return ""


def discover_posts(input_dir: Path, min_media_count: int) -> tuple[list[dict[str, Any]], list[dict[str, str]], str]:
    issues: list[dict[str, str]] = []
    posts: list[dict[str, Any]] = []

    if not input_dir.exists():
        issues.append({"level": "error", "target": str(input_dir), "message": "입력 폴더가 없습니다."})
        return posts, issues, ""

    manifest, manifest_path = load_manifest(input_dir)
    post_dirs = [path for path in input_dir.iterdir() if path.is_dir() and not path.name.startswith(".")]
    post_dirs = sorted(post_dirs, key=lambda path: natural_key(path.name))

    if not post_dirs:
        issues.append({"level": "error", "target": str(input_dir), "message": "게시물 폴더가 없습니다. 폴더 1개가 게시물 1개입니다."})
        return posts, issues, manifest_path

    for post_dir in post_dirs:
        media_files = [
            path
            for path in post_dir.iterdir()
            if path.is_file() and path.suffix.lower() in VALID_MEDIA_EXTS
        ]
        media_files = sorted(media_files, key=lambda path: natural_key(path.name))
        if not media_files:
            issues.append({"level": "error", "target": str(post_dir), "message": "유효한 미디어 파일이 없습니다."})
            continue
        if len(media_files) < min_media_count:
            issues.append({
                "level": "error",
                "target": str(post_dir),
                "message": f"미디어 {len(media_files)}개입니다. 반자동 기본 기준은 최소 {min_media_count}개입니다.",
            })
        posts.append({"folder": post_dir, "media_files": media_files, "meta": manifest.get(post_dir.name, {})})

    return posts, issues, manifest_path


def format_check(input_dir: Path, min_media_count: int) -> int:
    posts, issues, manifest_path = discover_posts(input_dir, min_media_count)
    print(f"입력 폴더: {input_dir}")
    print(f"manifest: {manifest_path or '없음'}")
    print(f"게시물 폴더 수: {len(posts)}")
    for post in posts:
        folder = post["folder"]
        files = post["media_files"]
        print(f"  - {folder.name}: {len(files)}개 / 순서: {', '.join(path.name for path in files)}")
    for issue in issues:
        print(f"[{issue['level'].upper()}] {issue['target']} - {issue['message']}")
    return 1 if any(issue["level"] == "error" for issue in issues) else 0


def parse_media_urls(value: Any) -> list[str]:
    if isinstance(value, list):
        return [safe_str(item) for item in value if safe_str(item)]
    text = safe_str(value)
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [safe_str(item) for item in parsed if safe_str(item)]
    except json.JSONDecodeError:
        pass
    parts = re.split(r"[\n,]+", text)
    return [part.strip() for part in parts if part.strip()]


def count_local_media_files(folder_path_str: str) -> int:
    if not folder_path_str:
        return 0
    folder = Path(folder_path_str)
    if not folder.exists():
        return 0
    return sum(1 for path in folder.iterdir() if path.is_file() and path.suffix.lower() in VALID_MEDIA_EXTS)


def validate_output_excel(excel_path: Path, min_media_count: int) -> int:
    if not excel_path.exists():
        print(f"[ERROR] 결과 엑셀이 없습니다: {excel_path}")
        return 1

    df = pd.read_excel(excel_path, engine="openpyxl")
    issues: list[str] = []
    for col in SEMI_AUTO_REQUIRED_COLUMNS:
        if col not in df.columns:
            issues.append(f"필수 컬럼 누락: {col}")

    if issues:
        for issue in issues:
            print(f"[ERROR] {issue}")
        return 1

    completed_count = 0
    for idx, row in df.iterrows():
        status = safe_str(row.get("처리상태", ""))
        if status != "completed":
            continue
        completed_count += 1
        excel_row = idx + 2
        link = safe_str(row.get("링크", ""))
        if not link.startswith("http"):
            issues.append(f"{excel_row}행 링크가 http로 시작하지 않습니다.")

        media_urls = parse_media_urls(row.get("업로드미디어URL", ""))
        local_count = count_local_media_files(safe_str(row.get("미디어폴더", "")))
        if max(len(media_urls), local_count) < min_media_count:
            issues.append(f"{excel_row}행 미디어가 부족합니다. 업로드URL {len(media_urls)}개 / 로컬 {local_count}개")

        copies = [safe_str(row.get(col, "")) for col in ["카피1", "카피2", "카피3"]]
        if not any(copies):
            issues.append(f"{excel_row}행 카피가 없습니다.")

    if completed_count == 0:
        issues.append("처리상태=completed 행이 없습니다.")

    if issues:
        for issue in issues:
            print(f"[ERROR] {issue}")
        return 1

    print(f"[OK] 반자동 입력 형식 검사 통과: {excel_path}")
    print("     내쿠팡링크는 v1에서 비워둘 수 있습니다. 업로드 시 --allow-missing-deeplink를 사용하세요.")
    return 0


def pseudo_link_for_folder(folder_name: str) -> str:
    return f"https://local.madoyo/media-manual/{quote(folder_name)}"


def clean_for_excel(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value)
    if isinstance(value, list):
        return [clean_for_excel(item) for item in value]
    if isinstance(value, dict):
        return {key: clean_for_excel(item) for key, item in value.items()}
    return value


def build_base_row(post: dict[str, Any], use_manifest_deeplink: bool) -> dict[str, Any]:
    folder: Path = post["folder"]
    media_files: list[Path] = post["media_files"]
    meta = post.get("meta", {})
    link = get_meta_value(meta, ["링크", "url", "URL", "source_url"], ["링크", "url"])
    if not link.startswith("http"):
        link = pseudo_link_for_folder(folder.name)
    description = get_meta_value(meta, ["본문", "설명", "메모", "description"], ["설명", "메모", "description"])
    product_name = get_meta_value(meta, ["상품명", "product_name"], ["상품"])
    deeplink = get_meta_value(meta, ["내쿠팡링크", "coupang_deep_link"], ["내쿠팡", "deep_link"]) if use_manifest_deeplink else ""
    raw_coupang = get_meta_value(meta, ["쿠팡원본링크", "coupang_raw_url"], ["쿠팡원본", "coupang_raw"]) if use_manifest_deeplink else ""
    return {
        "링크": link,
        "본문": description or f"미디어수동 입력: {folder.name}",
        "상품명": product_name or folder.name,
        "본문조회수": "",
        "작성시간": "",
        "좋아요": "",
        "답글수": "",
        "리포스트": "",
        "공유수": "",
        "첫댓글URL": "",
        "첫댓글조회수": "",
        "크롤링시간": datetime.now().isoformat(timespec="seconds"),
        "미디어_해시값": folder.name,
        "미디어폴더": str(folder.resolve()),
        "미디어파일수": len(media_files),
        "원본미디어URL": json_list([path.resolve() for path in media_files]),
        "업로드미디어URL": "",
        "업로드미디어수": 0,
        "카피1": "",
        "카피2": "",
        "카피3": "",
        "내쿠팡링크": deeplink,
        "쿠팡원본링크": raw_coupang,
        "처리상태": "pending",
        "오류메시지": "",
        "미디어수동폴더": folder.name,
        "미디어파일목록": json_list([path.name for path in media_files]),
        "검색방식": "visual_only_alpha_70_mss_30_similarity",
    }


def fill_retrieved_examples(row: dict[str, Any], examples: list[dict[str, Any]]) -> None:
    for i in range(1, 4):
        row[f"유사본문{i}"] = ""
        row[f"유사본문{i}_MSS"] = ""
        row[f"유사본문{i}_Alpha"] = ""
    for i, example in enumerate(examples[:3], start=1):
        row[f"유사본문{i}"] = safe_str(example.get("본문", ""))
        row[f"유사본문{i}_MSS"] = example.get("MSS", "")
        row[f"유사본문{i}_Alpha"] = example.get("alpha_score", "")


def generate_post_row(post: dict[str, Any], shared_resources: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    row = build_base_row(post, args.use_manifest_deeplink)
    media_files = [str(path.resolve()) for path in post["media_files"]]
    if len(media_files) < args.min_media_count:
        row["처리상태"] = "media_count_lt_min"
        row["오류메시지"] = f"미디어 {len(media_files)}개 / 최소 {args.min_media_count}개"
        return row

    if str(WORKING_CODE_DIR) not in sys.path:
        sys.path.insert(0, str(WORKING_CODE_DIR))

    from google import genai
    from app_config import GlobalConfig
    from marketing_focus_extractor import extract_marketing_focus
    from optimize_copy_v2 import run_optimization

    client = shared_resources.get("genai_client")
    if client is None:
        if not GlobalConfig.GEMINI_API_KEY:
            raise SystemExit("GEMINI_API_KEY가 없어 카피를 생성할 수 없습니다. .env를 확인해주세요.")
        client = genai.Client(api_key=GlobalConfig.GEMINI_API_KEY)
        shared_resources["genai_client"] = client

    try:
        marketing_focus = extract_marketing_focus(
            client,
            GlobalConfig.MODEL_NAME,
            row["상품명"] or "상품",
            row["본문"],
            media_files,
            coupang_images=None,
        )
        payload = run_optimization(
            original_copy="",
            product_focus=marketing_focus,
            input_image_urls=media_files,
            shared_resources=shared_resources,
            return_metadata=True,
            retrieval_bucket="visual",
        )
        top_results = payload.get("top_results", []) if isinstance(payload, dict) else []
        copies: list[str] = []
        seen: set[str] = set()
        for item in top_results:
            copy = safe_str(item.get("copy", ""))
            if not copy or copy in seen:
                continue
            seen.add(copy)
            copies.append(copy)
            if len(copies) >= 3:
                break
        while len(copies) < 3:
            copies.append("")

        row["카피1"], row["카피2"], row["카피3"] = copies[:3]
        meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
        fill_retrieved_examples(row, meta.get("retrieved_examples", []))
        row["생성후보수"] = meta.get("candidate_count", "")
        row["카피채점모드"] = meta.get("copy_scorer_mode", "")
        row["처리상태"] = "completed" if any(copies) else "copy_failed"
        if row["처리상태"] != "completed":
            row["오류메시지"] = "생성된 카피가 없습니다."
        return row
    except Exception as exc:
        row["처리상태"] = "generation_failed"
        row["오류메시지"] = str(exc)
        return row


def build_output_path(result_dir: Path) -> Path:
    result_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%m%d_%H%M")
    return result_dir / f"media_manual_ready_{stamp}.xlsx"


def write_result_excel(output_path: Path, rows: list[dict[str, Any]], issues: list[dict[str, str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned_rows = [{key: clean_for_excel(row.get(key, "")) for key in OUTPUT_COLUMNS} for row in rows]
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        pd.DataFrame(cleaned_rows, columns=OUTPUT_COLUMNS).to_excel(writer, sheet_name="results", index=False)
        pd.DataFrame(issues).to_excel(writer, sheet_name="format_check", index=False)


def copy_to_semi_auto(output_path: Path) -> Path:
    SEMI_AUTO_REF_DIR.mkdir(parents=True, exist_ok=True)
    target = SEMI_AUTO_REF_DIR / output_path.name
    if target.exists():
        target = SEMI_AUTO_REF_DIR / f"{output_path.stem}_{int(datetime.now().timestamp())}{output_path.suffix}"
    shutil.copy2(output_path, target)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="미디어 폴더 기반 수동 카피 생성 파이프라인")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR), help="폴더 1개가 게시물 1개인 입력 폴더")
    parser.add_argument("--result-dir", default=str(DEFAULT_RESULT_DIR), help="결과 엑셀 저장 폴더")
    parser.add_argument("--output-excel", help="결과 엑셀 직접 지정")
    parser.add_argument("--limit", type=int, default=0, help="처리할 게시물 폴더 수 제한")
    parser.add_argument("--min-media-count", type=int, default=2, help="반자동 업로드 기준 최소 미디어 수")
    parser.add_argument("--check-only", action="store_true", help="입력 폴더 형식만 검사하고 종료")
    parser.add_argument("--validate-output-excel", help="생성된 엑셀이 반자동 입력 형식인지 검사")
    parser.add_argument("--copy-to-semi-auto", action="store_true", help="성공한 결과 엑셀을 반자동/반자동참조로 복사")
    parser.add_argument("--use-manifest-deeplink", action="store_true", help="manifest의 내쿠팡링크를 사용. 기본은 임시 비활성")
    args = parser.parse_args()

    input_dir = Path(args.input_dir).expanduser().resolve()
    result_dir = Path(args.result_dir).expanduser().resolve()

    if args.validate_output_excel:
        return validate_output_excel(Path(args.validate_output_excel).expanduser().resolve(), args.min_media_count)

    if args.check_only:
        return format_check(input_dir, args.min_media_count)

    posts, issues, manifest_path = discover_posts(input_dir, args.min_media_count)
    print(f"입력 폴더: {input_dir}")
    print(f"manifest: {manifest_path or '없음'}")
    print(f"발견한 게시물 폴더: {len(posts)}개")
    if not posts:
        for issue in issues:
            print(f"[{issue['level'].upper()}] {issue['target']} - {issue['message']}")
        return 1

    selected_posts = posts[: args.limit] if args.limit and args.limit > 0 else posts
    output_path = Path(args.output_excel).expanduser().resolve() if args.output_excel else build_output_path(result_dir)
    shared_resources: dict[str, Any] = {}
    rows = []
    for index, post in enumerate(selected_posts, start=1):
        print(f"\n[{index}/{len(selected_posts)}] {post['folder'].name} 처리 중...", flush=True)
        row = generate_post_row(post, shared_resources, args)
        rows.append(row)
        print(f"  -> {row['처리상태']}: 카피 {sum(1 for col in ['카피1', '카피2', '카피3'] if safe_str(row.get(col)))}개")

    write_result_excel(output_path, rows, issues)
    print(f"\n결과 엑셀: {output_path}")
    validation_code = validate_output_excel(output_path, args.min_media_count)
    if args.copy_to_semi_auto and validation_code == 0:
        semi_path = copy_to_semi_auto(output_path)
        print(f"반자동 참조로 복사 완료: {semi_path}")
    print("반자동 업로드 시 v1은 내쿠팡링크가 비어 있을 수 있으므로 --allow-missing-deeplink를 사용하세요.")
    return validation_code


if __name__ == "__main__":
    raise SystemExit(main())
