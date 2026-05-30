import argparse
import json
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

import pandas as pd
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from scraper import dismiss_thread_popup
from threads_feed_sourcing import extract_feed_cards, init_driver, now_iso


WAIT_SECONDS = 5
SCROLL_PAUSE_SECONDS = 1.3

LABEL_COLUMNS = [
    "라벨상태",
    "전략보존",
    "적합도점수",
    "핵심문제라벨",
    "세그먼트추정",
    "마케팅각도",
    "외로움직접표현",
    "사람만나기시도",
    "모임실패경험",
    "관계지속실패",
    "스몰토크불만",
    "깊은대화욕구",
    "기존대안피로",
    "첫참석불안",
    "안전품질불안",
    "후속연락욕구",
    "행동의향",
    "경쟁서비스언급",
    "라벨근거메모",
]

LABEL_SCHEMA = [
    {"라벨": "라벨상태", "값": "blank / reviewed / exclude", "설명": "사람이 라벨링했는지 상태"},
    {"라벨": "전략보존", "값": "Y / N", "설명": "전략 추출 후보로 남길지"},
    {"라벨": "적합도점수", "값": "0-5", "설명": "사업 핵심 문제와의 정성 적합도"},
    {"라벨": "핵심문제라벨", "값": "free text", "설명": "가장 강한 문제 프레임"},
    {"라벨": "세그먼트추정", "값": "free text", "설명": "직장인, 내향인, 1인가구 등"},
    {"라벨": "마케팅각도", "값": "free text", "설명": "공감형, 불만형, 오퍼형 등"},
    {"라벨": "외로움직접표현", "값": "0/1", "설명": "외롭다/공허하다 등 직접 표현"},
    {"라벨": "사람만나기시도", "값": "0/1", "설명": "모임/소개팅/오픈채팅 등 행동 시도"},
    {"라벨": "모임실패경험", "값": "0/1", "설명": "모임 자체에 대한 실패/불만 경험"},
    {"라벨": "관계지속실패", "값": "0/1", "설명": "끝난 뒤 연락/관계로 이어지지 않음"},
    {"라벨": "스몰토크불만", "값": "0/1", "설명": "얕은 대화, 어색한 대화에 대한 불만"},
    {"라벨": "깊은대화욕구", "값": "0/1", "설명": "진짜 이야기/깊은 대화 욕구"},
    {"라벨": "기존대안피로", "값": "0/1", "설명": "소개팅앱, 오픈채팅, 소모임 등에 대한 피로"},
    {"라벨": "첫참석불안", "값": "0/1", "설명": "처음 나가는 자리의 불안/어색함"},
    {"라벨": "안전품질불안", "값": "0/1", "설명": "이상한 사람, 목적 불일치, 안전 우려"},
    {"라벨": "후속연락욕구", "값": "0/1", "설명": "다시 연락할 사람/명분에 대한 욕구"},
    {"라벨": "행동의향", "값": "0/1", "설명": "모임 참여/신청/궁금 등 행동 신호"},
    {"라벨": "경쟁서비스언급", "값": "free text", "설명": "문토, 타임레프트, 소개팅앱 등"},
    {"라벨": "라벨근거메모", "값": "free text", "설명": "라벨 판단 근거 문장"},
]

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def safe_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def parse_keywords(args):
    records = []
    if args.keywords_xlsx:
        df = pd.read_excel(args.keywords_xlsx, sheet_name="keywords")
        for _, row in df.iterrows():
            keyword = safe_text(row.get("keyword", ""))
            search_query = safe_text(row.get("search_query", keyword)) or keyword
            if not keyword:
                continue
            records.append(
                {
                    "keyword": keyword,
                    "search_query": search_query,
                    "category": safe_text(row.get("category", "")),
                    "priority": row.get("priority", ""),
                    "intent": safe_text(row.get("intent", "")),
                    "notes": safe_text(row.get("notes", "")),
                }
            )
    if args.keywords:
        for part in args.keywords.split(","):
            keyword = part.strip()
            if keyword:
                records.append({"keyword": keyword, "search_query": keyword})
    if args.keywords_file:
        path = Path(args.keywords_file)
        for line in path.read_text(encoding="utf-8").splitlines():
            keyword = line.strip()
            if keyword and not keyword.startswith("#"):
                records.append({"keyword": keyword, "search_query": keyword})

    deduped = []
    seen = set()
    for record in records:
        key = record.get("search_query") or record.get("keyword")
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def build_search_url(keyword):
    return "https://www.threads.com/search?q=" + urllib.parse.quote(keyword) + "&serp_type=default"


def open_search_page(driver, keyword):
    url = build_search_url(keyword)
    driver.get(url)
    time.sleep(WAIT_SECONDS)
    dismiss_thread_popup(driver)
    return url


def scroll_search(driver):
    moved = False
    try:
        moved = bool(
            driver.execute_script(
                """
                return (function() {
                  const candidates = Array.from(document.querySelectorAll("*")).filter((el) => {
                    const style = window.getComputedStyle(el);
                    return (style.overflowY === "auto" || style.overflowY === "scroll") &&
                      el.scrollHeight > el.clientHeight + 100;
                  });
                  candidates.sort((a, b) =>
                    (b.scrollHeight - b.clientHeight) - (a.scrollHeight - a.clientHeight)
                  );
                  const target = candidates[0] || document.scrollingElement || document.documentElement;
                  const before = target.scrollTop || window.scrollY || 0;
                  const delta = Math.max(450, Math.floor((target.clientHeight || window.innerHeight) * 0.85));
                  if (target === document.scrollingElement || target === document.documentElement) {
                    window.scrollBy(0, delta);
                  } else {
                    target.scrollTop = before + delta;
                  }
                  const after = target.scrollTop || window.scrollY || 0;
                  return after > before;
                })();
                """
            )
        )
    except Exception:
        moved = False
    if not moved:
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.PAGE_DOWN)
    time.sleep(SCROLL_PAUSE_SECONDS)
    dismiss_thread_popup(driver)


def normalize_post_url(url):
    value = str(url or "").split("?")[0]
    if value.endswith("/media"):
        value = value[: -len("/media")]
    return value


def is_body_noise(text, handle=""):
    value = " ".join(str(text or "").split()).strip()
    if not value:
        return True
    handle_value = str(handle or "").strip().lstrip("@")
    if handle_value and value in {handle_value, "@" + handle_value}:
        return True
    if value in {"번역하기", "See translation", "좋아요", "답글", "댓글", "리포스트", "공유", "공유하기"}:
        return True
    if value.replace(".", "", 1).replace(",", "").isdigit():
        return True
    if value.endswith("천") or value.endswith("만"):
        return any(ch.isdigit() for ch in value)
    if len(value) <= 5 and any(ch.isdigit() for ch in value):
        return True
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        return True
    return False


def select_body_text(card):
    handle = card.get("handle", "")
    blocks = card.get("text_blocks", []) or []
    candidates = [str(block).strip() for block in blocks if not is_body_noise(block, handle)]
    if candidates:
        return sorted(candidates, key=len, reverse=True)[0]
    preview = str(card.get("preview_text", "")).strip()
    return "" if is_body_noise(preview, handle) else preview


def card_to_row(keyword_record, card, keyword_rank, source_url):
    keyword = keyword_record.get("keyword", "")
    search_query = keyword_record.get("search_query", keyword)
    row = {
        "수집시각": now_iso(),
        "키워드": keyword,
        "검색쿼리": search_query,
        "키워드분류": keyword_record.get("category", ""),
        "우선순위": keyword_record.get("priority", ""),
        "검색의도": keyword_record.get("intent", ""),
        "키워드내순번": keyword_rank,
        "검색URL": source_url,
        "게시글링크": normalize_post_url(card.get("post_url", "")),
        "작성자": card.get("handle", ""),
        "작성시간_표시": card.get("time_text", ""),
        "작성시간_datetime": card.get("time_datetime", ""),
        "본문_카드표시": select_body_text(card),
        "본문_후보블록": json.dumps(card.get("text_blocks", []), ensure_ascii=False),
        "외부링크있음": bool(card.get("has_external_link", False)),
        "외부링크": "\n".join(card.get("external_links", []) or []),
        "좋아요수": card.get("likes", 0),
        "댓글수": card.get("replies", 0),
        "리포스트수": card.get("reposts", 0),
        "공유수": card.get("shares", 0),
        "좋아요_원문": card.get("likes_text", ""),
        "댓글_원문": card.get("replies_text", ""),
        "리포스트_원문": card.get("reposts_text", ""),
        "공유_원문": card.get("shares_text", ""),
        "반응합계": card.get("interaction_total", 0),
        "네이티브미디어수": card.get("native_media_count", 0),
        "답글맥락여부": bool(card.get("is_reply_context", False)),
        "만료문구여부": bool(card.get("has_expiry_text", False)),
    }
    for column in LABEL_COLUMNS:
        row[column] = ""
    return row


def get_page_state(driver):
    try:
        text = driver.execute_script("return document.body ? document.body.innerText : ''") or ""
    except Exception:
        text = ""
    if "HTTP ERROR 429" in text or "Too Many Requests" in text or "페이지가 작동하지 않습니다" in text:
        return "rate_limited"
    if "검색 결과가 없습니다" in text:
        return "no_results"
    return "ok"


def collect_keyword(driver, keyword_record, max_cards, max_scrolls, idle_limit):
    search_query = keyword_record.get("search_query", keyword_record.get("keyword", ""))
    source_url = open_search_page(driver, search_query)
    seen = set()
    rows = []
    idle_scrolls = 0
    scroll_count = 0

    while True:
        cards = extract_feed_cards(driver)
        new_cards = []
        for card in cards:
            post_url = normalize_post_url(card.get("post_url", ""))
            if not post_url or post_url in seen:
                continue
            seen.add(post_url)
            new_cards.append(card)

        if new_cards:
            idle_scrolls = 0
            for card in new_cards:
                rows.append(card_to_row(keyword_record, card, len(rows) + 1, source_url))
                if max_cards and len(rows) >= max_cards:
                    return rows, "max_cards_reached"
        else:
            page_state = get_page_state(driver)
            if page_state != "ok":
                return rows, page_state
            idle_scrolls += 1
            if idle_scrolls >= idle_limit:
                return rows, "idle_limit_reached"

        if max_scrolls and scroll_count >= max_scrolls:
            return rows, "max_scrolls_reached"

        scroll_search(driver)
        scroll_count += 1


def build_output_path(output_dir):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(output_dir) / f"threads_keyword_research_{stamp}.xlsx"


def write_outputs(output_path, rows, summary_rows, run_config):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_path.with_suffix(".jsonl")
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name="raw_posts", index=False)
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="keyword_summary", index=False)
        pd.DataFrame(LABEL_SCHEMA).to_excel(writer, sheet_name="label_schema", index=False)
        pd.DataFrame([run_config]).to_excel(writer, sheet_name="run_config", index=False)
    return jsonl_path


def main():
    parser = argparse.ArgumentParser(description="Threads logged-out keyword card research collector.")
    parser.add_argument("--keywords", default="", help="Comma-separated keywords.")
    parser.add_argument("--keywords-file", default="", help="UTF-8 text file, one keyword per line.")
    parser.add_argument("--keywords-xlsx", default="", help="Excel file with a 'keywords' sheet.")
    parser.add_argument("--output-dir", default=str(Path(__file__).resolve().parent / "keyword_research_runs"))
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--max-cards-per-keyword", type=int, default=40)
    parser.add_argument("--max-scrolls-per-keyword", type=int, default=12)
    parser.add_argument("--idle-limit", type=int, default=4)
    args = parser.parse_args()

    keywords = parse_keywords(args)
    if not keywords:
        raise SystemExit("키워드가 없습니다. --keywords, --keywords-file, --keywords-xlsx 중 하나를 지정하세요.")

    output_path = build_output_path(args.output_dir)
    rows = []
    summary_rows = []
    driver = None

    try:
        driver = init_driver(headless=args.headless)
        for index, keyword_record in enumerate(keywords, start=1):
            keyword = keyword_record.get("keyword", "")
            search_query = keyword_record.get("search_query", keyword)
            print(f"[{index}/{len(keywords)}] 검색 시작: {keyword} / query={search_query}", flush=True)
            started_at = now_iso()
            try:
                keyword_rows, stop_reason = collect_keyword(
                    driver=driver,
                    keyword_record=keyword_record,
                    max_cards=args.max_cards_per_keyword,
                    max_scrolls=args.max_scrolls_per_keyword,
                    idle_limit=args.idle_limit,
                )
                rows.extend(keyword_rows)
                summary_rows.append(
                    {
                        "키워드": keyword,
                        "검색쿼리": search_query,
                        "키워드분류": keyword_record.get("category", ""),
                        "우선순위": keyword_record.get("priority", ""),
                        "검색의도": keyword_record.get("intent", ""),
                        "시작시각": started_at,
                        "종료시각": now_iso(),
                        "수집게시글수": len(keyword_rows),
                        "중단이유": stop_reason,
                    }
                )
                print(f"    수집 {len(keyword_rows)}건, 중단이유={stop_reason}", flush=True)
            except Exception as exc:
                summary_rows.append(
                    {
                        "키워드": keyword,
                        "검색쿼리": search_query,
                        "키워드분류": keyword_record.get("category", ""),
                        "우선순위": keyword_record.get("priority", ""),
                        "검색의도": keyword_record.get("intent", ""),
                        "시작시각": started_at,
                        "종료시각": now_iso(),
                        "수집게시글수": 0,
                        "중단이유": f"error:{type(exc).__name__}:{exc}",
                    }
                )
                print(f"    오류: {type(exc).__name__}: {exc}", flush=True)
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

    run_config = {
        "실행시각": now_iso(),
        "키워드수": len(keywords),
        "최대카드_키워드당": args.max_cards_per_keyword,
        "최대스크롤_키워드당": args.max_scrolls_per_keyword,
        "idle_limit": args.idle_limit,
        "검색방식": "https://www.threads.com/search?q=<query>&serp_type=default",
        "산출구조": "Excel raw_posts for labeling + JSONL raw sidecar",
        "상세글진입": "No",
    }
    jsonl_path = write_outputs(output_path, rows, summary_rows, run_config)
    result = {
        "output_path": str(output_path),
        "jsonl_path": str(jsonl_path),
        "keyword_count": len(keywords),
        "row_count": len(rows),
        "finished_at": now_iso(),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
