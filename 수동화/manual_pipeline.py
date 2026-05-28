import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import pandas as pd
from selenium.webdriver.common.by import By

BASE_DIR = Path(__file__).resolve().parent.parent
AUTO_DIR = BASE_DIR / "자동화"
CODE_DIR = BASE_DIR / "작동중코드"

for path in (AUTO_DIR, CODE_DIR):
    sys.path.insert(0, str(path))

from google import genai

from app_config import GlobalConfig
from coupang_api import extract_and_convert_coupang_link, search_coupang_product
from marketing_focus_extractor import extract_marketing_focus
from optimize_copy_v2 import run_optimization
from scraper import (
    cache_media_locally,
    fetch_and_rehost,
    fetch_coupang_product_info,
    init_driver,
    scrape_comment_for_coupang,
    scrape_thread_content,
)


class CoupangBlockedError(RuntimeError):
    pass


MANUAL_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = MANUAL_DIR / "수동화참조"
DEFAULT_MEDIA_DIR = MANUAL_DIR / "수동화 미디어"
TEMP_CACHE_ROOTNAME = ".수동화_cache"
RESULT_COLUMNS = [
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

METADATA_JS = r"""
const expectedUrl = (arguments[0] || "").split("?")[0].replace("threads.net", "threads.com");
function cleanText(value) {
  return (value || "").replace(/\s+/g, " ").trim();
}
function uniq(values) {
  return Array.from(new Set((values || []).filter(Boolean)));
}
function normalizeUrl(value) {
  return (value || "").split("?")[0].replace("threads.net", "threads.com");
}
function parseMetric(root, labels) {
  const buttons = Array.from(root.querySelectorAll('[role="button"]'));
  for (const button of buttons) {
    const titles = uniq(Array.from(button.querySelectorAll("title")).map((el) => cleanText(el.textContent)));
    const aria = uniq(Array.from(button.querySelectorAll("[aria-label]")).map((el) => cleanText(el.getAttribute("aria-label"))));
    const buttonText = cleanText(button.innerText);
    const matched = labels.some((label) =>
      titles.includes(label) ||
      aria.some((text) => text === label || text.startsWith(label + " ")) ||
      buttonText.startsWith(label)
    );
    if (!matched) continue;

    const spans = uniq(Array.from(button.querySelectorAll("span")).map((el) => cleanText(el.innerText)));
    const numericSpans = spans.filter((text) => /\d/.test(text));
    if (numericSpans.length) return numericSpans[0];

    for (const label of labels) {
      if (buttonText.startsWith(label)) return cleanText(buttonText.slice(label.length));
    }
    return "0";
  }
  return "0";
}

const candidates = Array.from(document.querySelectorAll('article, div[data-pressable-container="true"], div[data-virtualized]'));
let root = null;
for (const candidate of candidates) {
  const postUrls = uniq(Array.from(candidate.querySelectorAll('a[href*="/post/"]')).map((el) => normalizeUrl(el.href)));
  if (postUrls.includes(expectedUrl)) {
    root = candidate;
    break;
  }
}
if (!root) root = document.body;

const postUrls = uniq(Array.from(root.querySelectorAll('a[href*="/post/"]')).map((el) => el.href || ""));
let firstReplyUrl = "";
for (const postUrl of postUrls) {
  if (normalizeUrl(postUrl) && normalizeUrl(postUrl) !== expectedUrl) {
    firstReplyUrl = postUrl;
    break;
  }
}

const timeEl = root.querySelector("time");
return {
  created_at: timeEl ? (timeEl.getAttribute("datetime") || cleanText(timeEl.innerText)) : "",
  likes: parseMetric(root, ["좋아요", "Like"]),
  replies: parseMetric(root, ["답글", "댓글", "Reply"]),
  reposts: parseMetric(root, ["리포스트", "Repost"]),
  shares: parseMetric(root, ["보내기", "공유하기", "공유", "Share"]),
  first_reply_url: firstReplyUrl,
};
"""


def safe_str(value):
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def json_list(values) -> str:
    return json.dumps([safe_str(value) for value in values or [] if safe_str(value)], ensure_ascii=False)


def build_empty_result(status: str = "started", error_message: str = "") -> dict:
    result = {column: "" for column in RESULT_COLUMNS}
    result["미디어파일수"] = 0
    result["업로드미디어수"] = 0
    result["처리상태"] = status
    result["오류메시지"] = error_message
    return result


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


def build_cache_dir(excel_dir: Path, stem: str) -> Path:
    cache_dir = excel_dir / TEMP_CACHE_ROOTNAME / stem
    (cache_dir / "rows").mkdir(parents=True, exist_ok=True)
    return cache_dir


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def row_cache_path(cache_dir: Path, row_index: int, url: str) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", safe_str(url))[:80] or f"row_{row_index + 1:05d}"
    return cache_dir / "rows" / f"{row_index:05d}_{safe_name}.json"


def load_cached_rows(cache_dir: Path) -> dict[int, dict]:
    rows_dir = cache_dir / "rows"
    items: dict[int, dict] = {}
    if not rows_dir.exists():
        return items
    for path in sorted(rows_dir.glob("*.json")):
        payload = read_json(path, {})
        if not payload:
            continue
        row_index = int(payload.get("row_index", -1))
        if row_index >= 0:
            items[row_index] = dict(payload.get("result") or {})
    return items


def finalize_excel(input_df: pd.DataFrame, cache_dir: Path, output_excel: Path) -> int:
    result_df = input_df.copy()
    for column in RESULT_COLUMNS:
        if column not in result_df.columns:
            result_df[column] = ""
        else:
            result_df[column] = result_df[column].astype("object")

    cached_rows = load_cached_rows(cache_dir)
    for row_index, result in cached_rows.items():
        if row_index >= len(result_df):
            continue
        for column in RESULT_COLUMNS:
            if column in result:
                result_df.at[row_index, column] = result.get(column, "")

    output_excel.parent.mkdir(parents=True, exist_ok=True)
    result_df.to_excel(output_excel, index=False)
    return len(cached_rows)


def cleanup_cache(cache_dir: Path):
    if cache_dir.exists():
        shutil.rmtree(cache_dir, ignore_errors=True)
    parent_dir = cache_dir.parent
    try:
        if parent_dir.exists() and not any(parent_dir.iterdir()):
            parent_dir.rmdir()
    except Exception:
        pass


def build_media_folder(media_root: Path, url: str, row_index: int) -> Path:
    match = re.search(r"/post/([^/?#]+)", safe_str(url))
    if match:
        folder_name = match.group(1)
    else:
        digest = hashlib.sha1(safe_str(url).encode("utf-8")).hexdigest()[:10]
        folder_name = f"row_{row_index + 1:05d}_{digest}"
    return media_root / folder_name


def extract_post_id(url: str) -> str:
    match = re.search(r"/post/([^/?#]+)", safe_str(url))
    if match:
        return match.group(1)
    return ""


def prepare_output_excel_path(excel_dir: Path, input_excel: Path, output_excel: str | None) -> Path:
    if output_excel:
        return Path(output_excel).expanduser().resolve()
    timestamp = datetime.now().strftime("%m%d_%H%M")
    return excel_dir / f"{input_excel.stem}_수동화결과_{timestamp}.xlsx"


def get_views_global(driver) -> str:
    xpaths = [
        "//*[contains(text(), '조회') or contains(text(), 'view') or contains(text(), 'View')]",
        "//*[contains(@aria-label, '조회') or contains(@aria-label, 'view') or contains(@aria-label, 'View')]",
    ]
    patterns = [
        r"([\d,.]+\s*[만천]?\s*회)",
        r"([\d,.]+\s*(?:views?|Views?))",
    ]

    for xpath in xpaths:
        try:
            elements = driver.find_elements(By.XPATH, xpath)
        except Exception:
            continue
        for element in elements:
            text = safe_str(element.text) or safe_str(element.get_attribute("aria-label"))
            if not text:
                continue
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    return " ".join(match.group(1).split())
    return ""


def collect_crawl_metadata(driver, url: str) -> dict:
    metadata = {
        "본문조회수": "",
        "작성시간": "",
        "좋아요": "0",
        "답글수": "0",
        "리포스트": "0",
        "공유수": "0",
        "첫댓글URL": "",
        "첫댓글조회수": "",
        "크롤링시간": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "미디어_해시값": extract_post_id(url),
    }

    metadata["본문조회수"] = get_views_global(driver)
    try:
        payload = driver.execute_script(METADATA_JS, url) or {}
        metadata["작성시간"] = safe_str(payload.get("created_at", ""))
        metadata["좋아요"] = safe_str(payload.get("likes", "0")) or "0"
        metadata["답글수"] = safe_str(payload.get("replies", "0")) or "0"
        metadata["리포스트"] = safe_str(payload.get("reposts", "0")) or "0"
        metadata["공유수"] = safe_str(payload.get("shares", "0")) or "0"
        metadata["첫댓글URL"] = safe_str(payload.get("first_reply_url", ""))
    except Exception:
        pass

    # [C] 첫 번째 댓글 영역 탐색 (makingprogram.py 방식 우회 전략 도입)
    try:
        all_post_links = driver.find_elements(By.XPATH, "//a[contains(@href, '/post/')]")
        main_url_base = url.split('?')[0].replace("threads.net", "threads.com")
        first_comment_url = None
        
        for link_el in all_post_links:
            try:
                href = link_el.get_attribute("href")
                if not href:
                    continue
                href_base = href.split('?')[0].replace("threads.net", "threads.com")
                if href_base != main_url_base:
                    first_comment_url = href
                    break
            except:
                continue

        if first_comment_url:
            metadata["첫댓글URL"] = first_comment_url
            driver.get(first_comment_url)
            time.sleep(5)
            metadata["첫댓글조회수"] = get_views_global(driver)
        else:
            if metadata.get("첫댓글조회수") == "":
                metadata["첫댓글조회수"] = "없음"
    except Exception as e:
        print(f"   ⚠️ 첫댓글 조회 실패: {e}")
        metadata["첫댓글조회수"] = "없음"

    return metadata


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
    row_index: int,
    source_row: pd.Series,
    link_column: str,
    media_root: Path,
    threads_driver,
    coupang_driver,
    coupang_executor: ThreadPoolExecutor,
    client,
    shared_resources: dict,
) -> dict:
    url = safe_str(source_row.get(link_column, ""))
    result = build_empty_result()

    if not url.startswith("http"):
        result["처리상태"] = "invalid_url"
        result["오류메시지"] = "유효한 URL이 없습니다."
        return result

    thread_info = scrape_thread_content(url, driver=threads_driver)
    original_text = safe_str(thread_info.get("text", ""))
    source_media_urls = thread_info.get("all_media", []) or thread_info.get("images", []) or []
    video_urls = thread_info.get("video_urls", []) or []
    result["본문"] = original_text
    result["원본미디어URL"] = json_list(source_media_urls)

    coupang_urls = thread_info.get("coupang_urls", []) or []
    if not coupang_urls:
        comment_info = scrape_comment_for_coupang(url, driver=threads_driver)
        if comment_info:
            coupang_urls = comment_info.get("coupang_urls", []) or []
    raw_coupang_url = safe_str(coupang_urls[0]) if coupang_urls else ""
    result["쿠팡원본링크"] = raw_coupang_url

    coupang_future = None
    if raw_coupang_url:
        print("  [쿠팡] 별도 브라우저에서 상품/딥링크 처리 시작", flush=True)
        coupang_future = coupang_executor.submit(resolve_coupang_payload, raw_coupang_url, coupang_driver)

    media_folder = build_media_folder(media_root, url, row_index)
    local_media_paths = []

    if media_folder.exists():
        shutil.rmtree(media_folder, ignore_errors=True)

    if source_media_urls:
        local_media_paths = cache_media_locally(
            source_media_urls,
            media_folder,
            driver=threads_driver,
            video_urls=video_urls,
            prefix="media",
            max_items=10,
        )
    result["미디어폴더"] = str(media_folder) if local_media_paths else ""
    result["미디어파일수"] = len(local_media_paths)
    result["미디어_해시값"] = media_folder.name

    public_media_urls = []
    if source_media_urls:
        public_media_urls = fetch_and_rehost(source_media_urls, driver=threads_driver, video_urls=video_urls)
    result["업로드미디어URL"] = json_list(public_media_urls)
    result["업로드미디어수"] = len(public_media_urls)
    result.update({key: value for key, value in collect_crawl_metadata(threads_driver, url).items() if value != ""})

    product_name = ""
    product_image = ""
    if coupang_future:
        try:
            coupang_payload = coupang_future.result()
        except CoupangBlockedError:
            result["처리상태"] = "coupang_blocked"
            result["오류메시지"] = "쿠팡 Akamai Access Denied 감지로 run 중단"
            raise
        product_name = coupang_payload["product_name"]
        product_image = coupang_payload["product_image"]
        result["상품명"] = product_name
        result["내쿠팡링크"] = coupang_payload["deep_link"]

    candidate_images = list(local_media_paths)
    if product_image:
        candidate_images.append(product_image)

    if not original_text:
        result["처리상태"] = "text_missing"
        result["오류메시지"] = "본문을 수집하지 못했습니다."
        return result

    marketing_focus = extract_marketing_focus(
        client,
        GlobalConfig.MODEL_NAME,
        result["상품명"] or "상품",
        original_text,
        local_media_paths,
        coupang_images=[product_image] if product_image else None,
    )

    optimization_payload = run_optimization(
        original_copy=original_text,
        product_focus=marketing_focus,
        input_image_urls=candidate_images or None,
        shared_resources=shared_resources,
        return_metadata=True,
    )

    top_results = optimization_payload.get("top_results", []) if isinstance(optimization_payload, dict) else []
    copies = [safe_str(item.get("copy", "")) for item in top_results[:3]]
    while len(copies) < 3:
        copies.append("")

    result["카피1"], result["카피2"], result["카피3"] = copies
    result["처리상태"] = "completed"
    return result


def main():
    parser = argparse.ArgumentParser(description="수동화 링크 기반 크롤링+카피 생성 파이프라인")
    parser.add_argument("--input-excel", help="직접 지정할 입력 엑셀 경로")
    parser.add_argument("--input-dir", help="입력 엑셀 폴더. 기본값은 수동화참조")
    parser.add_argument("--excel-dir", help="결과 엑셀 저장 폴더. 기본값은 수동화 폴더")
    parser.add_argument("--output-excel", help="직접 지정할 결과 엑셀 경로")
    parser.add_argument("--media-dir", help="미디어 저장 폴더. 기본값은 수동화 미디어")
    args = parser.parse_args()

    input_dir = Path(args.input_dir).expanduser().resolve() if args.input_dir else DEFAULT_INPUT_DIR
    excel_dir = Path(args.excel_dir).expanduser().resolve() if args.excel_dir else MANUAL_DIR
    media_dir = Path(args.media_dir).expanduser().resolve() if args.media_dir else DEFAULT_MEDIA_DIR

    input_excel = pick_input_excel(args.input_excel, input_dir)
    output_excel = prepare_output_excel_path(excel_dir, input_excel, args.output_excel)
    cache_dir = build_cache_dir(excel_dir, output_excel.stem)

    print(f"입력 엑셀: {input_excel}")
    print(f"결과 엑셀: {output_excel}")
    print(f"미디어 폴더: {media_dir}")

    df = pd.read_excel(input_excel, engine="openpyxl")
    link_column = find_link_column(df)

    client = genai.Client(api_key=GlobalConfig.GEMINI_API_KEY)
    shared_resources: dict = {}
    threads_driver = None
    coupang_driver = None
    coupang_executor = None
    print("Threads 브라우저 초기화...")
    threads_driver = init_driver()
    print("Coupang 전용 브라우저 초기화...")
    coupang_driver = init_driver()
    coupang_executor = ThreadPoolExecutor(max_workers=1)
    interrupted = False

    try:
        for row_index, row in df.iterrows():
            url = safe_str(row.get(link_column, ""))
            if not url:
                continue

            print(f"\n[{row_index + 1}/{len(df)}] {url}")
            try:
                result = process_row(
                    row_index=row_index,
                    source_row=row,
                    link_column=link_column,
                    media_root=media_dir,
                    threads_driver=threads_driver,
                    coupang_driver=coupang_driver,
                    coupang_executor=coupang_executor,
                    client=client,
                    shared_resources=shared_resources,
                )
            except KeyboardInterrupt:
                interrupted = True
                print("\n중단 요청을 받아 현재까지 결과를 엑셀로 정리합니다.")
                break
            except CoupangBlockedError as exc:
                interrupted = True
                result = build_empty_result(status="coupang_blocked", error_message=str(exc))
                print(f"\n쿠팡 차단 감지로 수동화를 중단합니다: {exc}")
                write_json(
                    row_cache_path(cache_dir, row_index, url),
                    {
                        "row_index": row_index,
                        "url": url,
                        "result": result,
                    },
                )
                break
            except Exception as exc:
                result = build_empty_result(status="error", error_message=str(exc))
                print(f"  오류: {exc}")

            write_json(
                row_cache_path(cache_dir, row_index, url),
                {
                    "row_index": row_index,
                    "url": url,
                    "result": result,
                },
            )

    except KeyboardInterrupt:
        interrupted = True
        print("\n중단 요청을 받아 현재까지 결과를 엑셀로 정리합니다.")
    finally:
        written_count = finalize_excel(df, cache_dir, output_excel)
        cleanup_cache(cache_dir)
        if coupang_executor:
            coupang_executor.shutdown(wait=False, cancel_futures=True)
        try:
            if threads_driver:
                threads_driver.quit()
        except Exception:
            pass
        try:
            if coupang_driver:
                coupang_driver.quit()
        except Exception:
            pass

    if interrupted:
        print(f"\n부분 결과 엑셀 저장 완료: {output_excel} ({written_count}건)")
    else:
        print(f"\n수동화 엑셀 저장 완료: {output_excel} ({written_count}건)")


if __name__ == "__main__":
    main()
