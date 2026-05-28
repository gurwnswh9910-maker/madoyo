import argparse
import io
import json
import os
import random
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv


if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding="utf-8")
    except Exception:
        pass


SEMI_DIR = Path(__file__).resolve().parent
BASE_DIR = SEMI_DIR.parent
AUTO_DIR = BASE_DIR / "자동화"
CODE_DIR = BASE_DIR / "작동중코드"

for path in (AUTO_DIR, CODE_DIR):
    sys.path.insert(0, str(path))

load_dotenv(BASE_DIR / ".env", override=False)

from app_config import GlobalConfig
from publisher import collapse_duplicate_reply_urls, get_reply_text_rejection, upload_to_threads
from content_guard import (
    DEFAULT_MAX_BODY_LINES,
    DEFAULT_MAX_REPLY_LINES,
    get_text_rejection,
    rejection_category,
)


REF_DIR = SEMI_DIR / "반자동참조"
DONE_DIR = REF_DIR / "업로드완료"
RESULT_DIR = SEMI_DIR / "반자동결과"
ACCOUNT_PROTECTION_ERROR_CATEGORIES = {"account_restricted", "action_blocked"}
VALID_LOCAL_MEDIA_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".gif"}


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def pick_input_excel(input_excel: str | None) -> Path:
    if input_excel:
        path = Path(input_excel).expanduser().resolve()
        if not path.exists():
            raise SystemExit(f"입력 엑셀을 찾지 못했습니다: {path}")
        return path

    REF_DIR.mkdir(parents=True, exist_ok=True)
    candidates = [
        path
        for path in sorted(REF_DIR.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not path.name.startswith("~$")
    ]
    if not candidates:
        raise SystemExit(f"반자동참조 폴더에 엑셀을 넣어주세요: {REF_DIR}")
    if len(candidates) > 1:
        names = "\n".join(f"- {path.name}" for path in candidates)
        raise SystemExit(f"반자동참조에는 엑셀 1개만 두는 기준입니다.\n{names}")
    return candidates[0]


def find_column(df: pd.DataFrame, preferred: list[str], keywords: list[str] | None = None) -> str | None:
    columns = list(df.columns)
    lowered = {str(column).strip().lower(): column for column in columns}
    for name in preferred:
        match = lowered.get(name.lower())
        if match is not None:
            return match

    for column in columns:
        label = str(column).strip().lower()
        if any(keyword.lower() in label for keyword in keywords or []):
            return column
    return None


def parse_media_urls(value) -> list[str]:
    text = safe_str(value)
    if not text:
        return []

    try:
        parsed = json.loads(text)
    except Exception:
        parsed = None

    if isinstance(parsed, list):
        return [safe_str(item) for item in parsed if safe_str(item).startswith("http")]
    if isinstance(parsed, dict):
        return [safe_str(item) for item in parsed.values() if safe_str(item).startswith("http")]

    parts = re.split(r"[\n,;]+", text)
    return [part.strip() for part in parts if part.strip().startswith("http")]


def collect_copies(row: pd.Series) -> list[str]:
    copies = []
    for column in ("카피1", "카피2", "카피3"):
        value = safe_str(row.get(column, ""))
        if value:
            copies.append(value)
    return copies


def build_content_rejection_message(field_name: str, rejection: dict) -> str:
    max_length = rejection.get("max_length", 500)
    return (
        f"{field_name} 위생 컷({rejection['reason']}): "
        f"{rejection.get('text_length', 0)}자 / 최대 {max_length}자"
    )


def build_reply_text(deep_link: str) -> str:
    return GlobalConfig.REPLY_TEMPLATE.format(s_url=deep_link)


def count_local_media_files(folder_path_str: str) -> int:
    if not folder_path_str:
        return 0
    folder_path = Path(folder_path_str)
    if not folder_path.exists():
        return 0
    return sum(1 for path in folder_path.iterdir() if path.is_file() and path.suffix.lower() in VALID_LOCAL_MEDIA_EXTS)


def load_processed_links(account_name: str) -> set[str]:
    path = SEMI_DIR / f"processed_{account_name.lower()}.log"
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def log_processed_link(account_name: str, url: str):
    path = SEMI_DIR / f"processed_{account_name.lower()}.log"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(url.strip() + "\n")


def load_accounts(accounts_arg: str | None):
    raw = accounts_arg or os.getenv("THREADS_CURRENT_ACCOUNT", "1")
    account_names = [name.strip() for name in raw.split(",") if name.strip()]
    accounts = []
    for name in account_names:
        user_id, token = GlobalConfig.get_account_credentials(name)
        if user_id and token:
            accounts.append((name, user_id, token))
        else:
            print(f"⚠️ [{name}] 계정 토큰을 찾지 못해 제외합니다.", flush=True)

    if not accounts:
        raise SystemExit(
            "업로드 가능한 계정 토큰이 없습니다. THREADS_CURRENT_ACCOUNT/--accounts와 "
            "THREADS_ACCOUNT_<번호>_USER_ID/THREADS_ACCOUNT_<번호>_ACCESS_TOKEN을 확인해주세요."
        )
    return accounts


def build_publish_items(
    df: pd.DataFrame,
    min_media_count: int,
    allow_missing_deeplink: bool = False,
    drop_invalid_reply: bool = False,
):
    link_col = find_column(df, ["링크", "post_url", "url"], ["링크", "url"])
    if not link_col:
        raise SystemExit("엑셀에서 링크 컬럼을 찾지 못했습니다.")

    media_col = find_column(
        df,
        ["업로드미디어URL", "rehosted_media_urls", "rehosted_media_url"],
        ["업로드미디어", "rehosted"],
    )
    deeplink_col = find_column(df, ["내쿠팡링크", "coupang_deep_link"], ["내쿠팡", "deep_link"])
    status_col = find_column(df, ["처리상태", "status"], ["처리상태", "status"])
    local_folder_col = find_column(df, ["미디어폴더", "media_folder"], ["미디어폴더", "folder"])

    ready_items = []
    skipped_rows = []
    for row_index, row in df.iterrows():
        url = safe_str(row.get(link_col, ""))
        if not url.startswith("http"):
            continue

        status = safe_str(row.get(status_col, "")) if status_col else ""
        media_urls = parse_media_urls(row.get(media_col, "")) if media_col else []
        media_folder = safe_str(row.get(local_folder_col, "")) if local_folder_col else ""
        local_media_count = count_local_media_files(media_folder)
        deep_link = safe_str(row.get(deeplink_col, "")) if deeplink_col else ""
        raw_copies = collect_copies(row)
        copies = []
        copy_rejections = []
        for copy_index, copy_text in enumerate(raw_copies, start=1):
            rejection = get_text_rejection(
                copy_text,
                reject_repeated=True,
                reject_meta=True,
                reject_urls=True,
                reject_disclosure=True,
                max_lines=DEFAULT_MAX_BODY_LINES,
                min_hangul_chars=5,
            )
            if rejection is None:
                copies.append(copy_text)
            else:
                copy_rejections.append(
                    {
                        "copy_rank": copy_index,
                        "error_category": rejection_category(rejection["reason"]),
                        "message": build_content_rejection_message(f"카피{copy_index}", rejection),
                    }
                )
        reply_rejection = None
        upload_reply_text = None
        reply_status = "omitted"
        reply_skip_reason = ""
        if deep_link:
            reply_text = build_reply_text(deep_link)
            reply_rejection = get_reply_text_rejection(reply_text)
            if reply_rejection is None:
                upload_reply_text = reply_text
                reply_status = "ready"
            else:
                fallback_reply_text = collapse_duplicate_reply_urls(reply_text)
                fallback_rejection = (
                    get_reply_text_rejection(fallback_reply_text)
                    if fallback_reply_text != reply_text
                    else reply_rejection
                )
                if fallback_reply_text != reply_text and fallback_rejection is None:
                    upload_reply_text = fallback_reply_text
                    reply_status = "fallback_single_link"
                    reply_skip_reason = (
                        build_content_rejection_message("첫댓글", reply_rejection)
                        + " -> 링크 1회 폴백"
                    )
                    reply_rejection = None
        else:
            reply_skip_reason = (
                "내쿠팡링크 없음" if allow_missing_deeplink else ""
            )
        skip_reason = ""
        upload_deep_link = deep_link
        if reply_rejection is not None and drop_invalid_reply:
            upload_deep_link = ""
            upload_reply_text = None
            reply_status = "omitted"
            reply_skip_reason = build_content_rejection_message("첫댓글", reply_rejection)

        if status and status.lower() != "completed":
            skip_reason = f"처리상태={status}"
        elif max(len(media_urls), local_media_count) < min_media_count:
            skip_reason = f"업로드미디어URL {len(media_urls)}개 / 로컬미디어 {local_media_count}개"
        elif not deep_link and not allow_missing_deeplink:
            skip_reason = "내쿠팡링크 없음"
        elif reply_rejection is not None and not drop_invalid_reply:
            skip_reason = build_content_rejection_message("첫댓글", reply_rejection)
        elif not copies:
            if copy_rejections:
                skip_reason = "게시 가능한 카피 없음: " + "; ".join(item["message"] for item in copy_rejections)
            else:
                skip_reason = "카피 없음"

        item = {
            "excel_row": row_index + 2,
            "url": url,
            "media_urls": media_urls,
            "media_folder": media_folder,
            "local_media_count": local_media_count,
            "deep_link": upload_deep_link,
            "source_deep_link": deep_link,
            "reply_text": upload_reply_text,
            "reply_status": reply_status,
            "reply_skip_reason": reply_skip_reason,
            "copies": copies,
            "product_name": safe_str(row.get("상품명", "")),
            "skip_reason": skip_reason,
            "copy_rejections": copy_rejections,
        }
        if skip_reason:
            skipped_rows.append(item)
        else:
            ready_items.append(item)

    return ready_items, skipped_rows


def build_output_path(input_excel: Path) -> Path:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%m%d_%H%M")
    return RESULT_DIR / f"{input_excel.stem}_반자동결과_{stamp}.xlsx"


def clean_for_excel(obj):
    if isinstance(obj, str):
        # 엑셀(XML)에서 허용되지 않는 제어 문자 제거
        import re
        return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", obj)
    if isinstance(obj, list):
        return [clean_for_excel(x) for x in obj]
    if isinstance(obj, dict):
        return {k: clean_for_excel(v) for k, v in obj.items()}
    return obj

def write_results(output_path: Path, result_rows: list[dict], skipped_rows: list[dict]):
    # 데이터 클리닝
    cleaned_results = [clean_for_excel(row) for row in result_rows]
    cleaned_skipped = [clean_for_excel(row) for row in skipped_rows]
    
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        pd.DataFrame(cleaned_results).to_excel(writer, sheet_name="results", index=False)
        pd.DataFrame(cleaned_skipped).to_excel(writer, sheet_name="skipped_input", index=False)


def format_seconds(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}시간 {minutes}분 {secs}초"
    if minutes:
        return f"{minutes}분 {secs}초"
    return f"{secs}초"

def rehost_local_media(folder_path_str: str) -> list[str]:
    if not folder_path_str:
        return []
    
    folder_path = Path(folder_path_str)
    if not folder_path.exists():
        print(f"    [WARN] 로컬 미디어 폴더를 찾을 수 없습니다: {folder_path_str}")
        return []
        
    files = sorted([f for f in folder_path.iterdir() if f.suffix.lower() in VALID_LOCAL_MEDIA_EXTS])
    
    if not files:
        print(f"    [WARN] 폴더 내에 유효한 미디어 파일이 없습니다: {folder_path_str}")
        return []
        
    print(f"    [REHOST] 로컬 파일 {len(files)}개 실시간 재호스팅 시작...", flush=True)
    import requests
    new_urls = []
    for i, file_path in enumerate(files, start=1):
        try:
            with open(file_path, "rb") as f:
                resp = requests.post("https://tmpfiles.org/api/v1/upload", files={"file": f}, timeout=30)
                if resp.status_code == 200:
                    raw_url = resp.json()["data"]["url"]
                    # /dl/ 경로 보정
                    dl_url = raw_url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
                    new_urls.append(dl_url)
                    print(f"      - {i}/{len(files)} 성공: {file_path.name}")
                else:
                    print(f"      - {i}/{len(files)} 실패 (HTTP {resp.status_code})")
        except Exception as e:
            print(f"      - {i}/{len(files)} 오류: {e}")
            
    return new_urls


def wait_until_next_slot(start_time: float, completed_originals: int, slot_seconds: float, args):
    if slot_seconds <= 0:
        return

    jitter_window = min(slot_seconds * args.slot_jitter_ratio, args.slot_jitter_max_seconds)
    target_time = start_time + (slot_seconds * completed_originals) + random.uniform(-jitter_window, jitter_window)
    wait_seconds = max(0, target_time - time.time())
    if wait_seconds <= 0:
        print("[TIME] 다음 슬롯 시간이 이미 지나 바로 계속합니다.", flush=True)
        return
    if args.dry_run:
        print(f"[DRY] [dry-run] 다음 원본 슬롯까지 {format_seconds(wait_seconds)} 대기 예정입니다.", flush=True)
        return
    print(f"[WAIT] 다음 원본 슬롯까지 {format_seconds(wait_seconds)} 대기합니다.", flush=True)
    time.sleep(wait_seconds)


def move_to_done(input_excel: Path):
    DONE_DIR.mkdir(parents=True, exist_ok=True)
    target = DONE_DIR / input_excel.name
    if target.exists():
        target = DONE_DIR / f"{input_excel.stem}_{int(time.time())}{input_excel.suffix}"
    shutil.move(str(input_excel), str(target))
    print(f"[SUCCESS] 입력 엑셀 이동 완료: {target}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="수동화 엑셀 기반 Threads 업로드 전용 반자동 파이프라인")
    parser.add_argument("--input-excel", help="직접 지정할 수동화 결과 엑셀 경로")
    parser.add_argument("--accounts", help="업로드 계정 번호 목록. 예: 1,2,3")
    parser.add_argument("--hours", type=float, default=0, help="k개 원본을 분산 처리할 총 시간")
    parser.add_argument("--original-limit", type=int, default=0, help="처리할 원본 개수 k. 3계정에 각 30개여도 k=30")
    parser.add_argument("--dry-run", action="store_true", help="실제 업로드 없이 엑셀/스케줄만 검증")
    parser.add_argument("--move-done", action="store_true", help="완료 후 입력 엑셀을 반자동참조/업로드완료로 이동")
    parser.add_argument("--min-media-count", type=int, default=2, help="업로드에 필요한 최소 공개 미디어 URL 개수")
    parser.add_argument("--allow-missing-deeplink", action="store_true", help="내쿠팡링크가 없는 행도 첫댓글 없이 업로드")
    parser.add_argument("--drop-invalid-reply", action="store_true", help="첫댓글 위생 컷이 걸리면 본문만 업로드")
    parser.add_argument("--account-delay-min", type=float, default=20.0, help="같은 원본에서 계정 사이 최소 대기 초")
    parser.add_argument("--account-delay-max", type=float, default=45.0, help="같은 원본에서 계정 사이 최대 대기 초")
    parser.add_argument("--slot-jitter-ratio", type=float, default=0.15, help="원본 슬롯 대기 시간 랜덤 흔들림 비율")
    parser.add_argument("--slot-jitter-max-seconds", type=float, default=300.0, help="원본 슬롯 랜덤 흔들림 최대 초")
    args = parser.parse_args()

    input_excel = pick_input_excel(args.input_excel)
    output_path = build_output_path(input_excel)
    accounts = load_accounts(args.accounts)

    df = pd.read_excel(input_excel, engine="openpyxl")
    ready_items, skipped_rows = build_publish_items(
        df,
        args.min_media_count,
        args.allow_missing_deeplink,
        args.drop_invalid_reply,
    )
    if not ready_items:
        write_results(output_path, [], skipped_rows)
        raise SystemExit(f"업로드 가능한 행이 없습니다. 결과 확인: {output_path}")

    target_originals = args.original_limit if args.original_limit > 0 else len(ready_items)
    target_originals = min(target_originals, len(ready_items))
    ready_items = ready_items[:target_originals]
    slot_seconds = (args.hours * 3600 / target_originals) if args.hours > 0 and target_originals > 0 else 0

    print(f"입력 엑셀: {input_excel}", flush=True)
    print(f"결과 엑셀: {output_path}", flush=True)
    print(f"대상 계정: {', '.join(account[0] for account in accounts)}", flush=True)
    print(f"원본 기준 k={target_originals}, 총 업로드 시도 최대={target_originals * len(accounts)}", flush=True)
    if slot_seconds:
        print(f"원본 슬롯 간격 기준: 약 {format_seconds(slot_seconds)}", flush=True)

    processed_by_account = {account[0]: load_processed_links(account[0]) for account in accounts}
    quarantined_accounts = set()
    result_rows = []
    start_time = time.time()

    for original_index, item in enumerate(ready_items, start=1):
        print(f"\n[{original_index}/{target_originals}] {item['url']}", flush=True)
        target_accounts = []
        for account in accounts:
            account_name = account[0]
            if account_name in quarantined_accounts:
                continue
            if item["url"] in processed_by_account[account_name]:
                print(f"  - [{account_name}] 이미 처리한 원본이라 건너뜁니다.", flush=True)
                continue
            target_accounts.append(account)

        random.shuffle(target_accounts)
        if not target_accounts:
            result_rows.append(
                {
                    "time": now_iso(),
                    "original_index": original_index,
                    "excel_row": item["excel_row"],
                    "url": item["url"],
                    "account": "ALL",
                    "status": "skipped",
                    "stage": "precheck",
                    "error_category": "already_processed_or_quarantined",
                    "error_message": "",
                }
            )
            write_results(output_path, result_rows, skipped_rows)
            wait_until_next_slot(start_time, original_index, slot_seconds, args)
            continue

        for account_position, (account_name, user_id, token) in enumerate(target_accounts):
            # [LIVE REHOST] 로컬 파일이 있다면 매 계정 업로드 전에(또는 원본 단위로) URL 갱신
            # 첫 번째 계정 시도 시에만 재호스팅 수행
            if account_position == 0 and item["media_folder"]:
                fresh_urls = rehost_local_media(item["media_folder"])
                if len(fresh_urls) >= args.min_media_count:
                    item["media_urls"] = fresh_urls
                    print(f"    [INFO] 로컬 파일을 사용하여 {len(fresh_urls)}개 URL 갱신 완료")
                elif fresh_urls:
                    print(
                        f"    [WARN] 로컬 재호스팅 성공 {len(fresh_urls)}개가 최소 {args.min_media_count}개보다 적어 "
                        "기존 업로드미디어URL을 유지합니다.",
                        flush=True,
                    )

            copy_index = ((original_index - 1) + account_position) % len(item["copies"])
            post_text = item["copies"][copy_index]
            reply_text = item.get("reply_text")
            if item.get("reply_status") == "fallback_single_link":
                reply_note = " / 첫댓글 1링크 폴백"
            else:
                reply_note = " / 첫댓글 없음" if not reply_text else ""
            print(f"  [게시] {account_name} / 카피{copy_index + 1} / 미디어 {len(item['media_urls'])}개{reply_note}", flush=True)

            if args.dry_run:
                upload_result = {
                    "ok": True,
                    "stage": "dry_run",
                    "error_category": None,
                    "error_code": None,
                    "error_subcode": None,
                    "error_message": "",
                    "media_id": "",
                }
            else:
                upload_result = upload_to_threads(
                    user_id,
                    token,
                    post_text,
                    item["media_urls"],
                    reply_text,
                    None,
                )

            ok = bool(upload_result.get("ok"))
            result_rows.append(
                {
                    "time": now_iso(),
                    "original_index": original_index,
                    "original_count": target_originals,
                    "excel_row": item["excel_row"],
                    "url": item["url"],
                    "product_name": item["product_name"],
                    "account": account_name,
                    "copy_rank": copy_index + 1,
                    "media_count": len(item["media_urls"]),
                    "reply_status": item.get("reply_status", "ready" if reply_text else "omitted"),
                    "reply_skip_reason": item.get("reply_skip_reason", ""),
                    "status": "posted" if ok and not args.dry_run else "dry_run" if args.dry_run else "failed",
                    "stage": upload_result.get("stage"),
                    "error_category": upload_result.get("error_category"),
                    "error_code": upload_result.get("error_code"),
                    "error_subcode": upload_result.get("error_subcode"),
                    "error_message": upload_result.get("error_message", ""),
                    "media_id": upload_result.get("media_id", ""),
                }
            )

            if ok and not args.dry_run:
                log_processed_link(account_name, item["url"])
                processed_by_account[account_name].add(item["url"])
            elif upload_result.get("error_category") in ACCOUNT_PROTECTION_ERROR_CATEGORIES:
                quarantined_accounts.add(account_name)
                print(f"  🛡️ [{account_name}] 보호성 오류로 이번 런에서 격리합니다.", flush=True)

            write_results(output_path, result_rows, skipped_rows)

            if account_position < len(target_accounts) - 1:
                delay = random.uniform(args.account_delay_min, args.account_delay_max)
                if args.dry_run:
                    print(f"    🧪 [dry-run] 다음 계정 전 {delay:.1f}초 대기 예정", flush=True)
                else:
                    print(f"    ⏳ 다음 계정 전 {delay:.1f}초 대기", flush=True)
                    time.sleep(delay)

        if original_index < target_originals:
            wait_until_next_slot(start_time, original_index, slot_seconds, args)

    write_results(output_path, result_rows, skipped_rows)
    if args.move_done and not args.dry_run:
        move_to_done(input_excel)

    print(f"\n반자동 업로드 런 종료. 결과 엑셀: {output_path}", flush=True)


if __name__ == "__main__":
    main()
