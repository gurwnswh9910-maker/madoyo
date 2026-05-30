import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from seleniumbase import Driver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from scraper import dismiss_thread_popup, _extract_coupang_urls_from_current_page


TIMEOUT_SECONDS = 8
SCROLL_PAUSE_SECONDS = 1.2
MAX_IDLE_SCROLLS = 8
DEFAULT_PREOPEN_SKIP_STREAK = 5
DEFAULT_NO_COUPANG_STREAK = 3
DEFAULT_MIN_INTERACTION_TOTAL = 7
DEFAULT_LONG_COMMENT_THRESHOLD = 250
CARD_JS = r"""
return (function() {
  function cleanText(value) {
    return (value || "").replace(/\s+/g, " ").trim();
  }
  function uniq(values) {
    return Array.from(new Set((values || []).filter(Boolean)));
  }
  function parseMetricValue(root, labels) {
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
      if (!matched) {
        continue;
      }
      const spans = uniq(Array.from(button.querySelectorAll("span")).map((el) => cleanText(el.innerText)));
      const numericSpans = spans.filter((text) => /\d/.test(text));
      if (numericSpans.length) {
        return numericSpans[0];
      }
      for (const label of labels) {
        if (buttonText.startsWith(label)) {
          return cleanText(buttonText.slice(label.length));
        }
      }
      return "0";
    }
    return "0";
  }
  function isNoiseText(text) {
    if (!text) {
      return true;
    }
    const exactNoise = new Set([
      "번역하기",
      "See translation",
      "활동 보기",
      "좋아요",
      "댓글",
      "답글",
      "리포스트",
      "공유",
      "공유하기",
      "더 보기",
      "팔로우",
    ]);
    if (exactNoise.has(text)) {
      return true;
    }
    if (/^\d+([.,]\d+)?([km])?$/i.test(text)) {
      return true;
    }
    if (/^\d+([.,]\d+)?(천|만)?$/.test(text)) {
      return true;
    }
    if (/^\d+\s*(초|분|시간|일|주|개월|년)$/i.test(text)) {
      return true;
    }
    if (/^@[A-Za-z0-9._]+$/.test(text)) {
      return true;
    }
    return false;
  }
  function collectTextBlocks(root) {
    const texts = uniq(
      Array.from(root.querySelectorAll('[dir="auto"]'))
        .map((el) => cleanText(el.innerText))
        .filter(Boolean)
    );
    return texts;
  }
  function extractPreviewText(texts) {
    const filtered = texts.filter((text) => !isNoiseText(text));
    if (!filtered.length) {
      return "";
    }
    return filtered.slice().sort((a, b) => b.length - a.length)[0];
  }
  function collectNativeMedia(root) {
    const nativeImages = [];
    const externalPreviewImages = [];
    const videos = [];
    for (const img of Array.from(root.querySelectorAll("img"))) {
      const src = img.getAttribute("src") || "";
      const alt = img.getAttribute("alt") || "";
      const rect = img.getBoundingClientRect();
      const areaOk = rect.width >= 120 && rect.height >= 120;
      const isProfile = alt.toLowerCase().includes("profile picture") || alt.includes("프로필 사진");
      if (src.includes("scontent") || src.includes("cdninstagram.com")) {
        if (areaOk && !isProfile) {
          nativeImages.push({src, alt, width: rect.width, height: rect.height});
        }
      } else if (areaOk) {
        externalPreviewImages.push({src, alt, width: rect.width, height: rect.height});
      }
    }
    for (const video of Array.from(root.querySelectorAll("video"))) {
      const src = video.getAttribute("src") || "";
      const poster = video.getAttribute("poster") || "";
      videos.push({src, poster});
    }
    return {
      native_images: nativeImages,
      external_preview_images: externalPreviewImages,
      videos,
      native_media_count: nativeImages.length + videos.length,
    };
  }
  const rows = Array.from(document.querySelectorAll("div[data-virtualized]"));
  const cards = [];
  const seen = new Set();
  let feedPosition = 0;
  for (const row of rows) {
    const postAnchor = row.querySelector('a[href*="/post/"]');
    if (!postAnchor) {
      continue;
    }
    const postUrl = (postAnchor.href || "").split("?")[0];
    if (!postUrl || seen.has(postUrl)) {
      continue;
    }
    seen.add(postUrl);
    feedPosition += 1;
    const textBlocks = collectTextBlocks(row);
    const previewText = extractPreviewText(textBlocks);
    const media = collectNativeMedia(row);
    const timeEl = row.querySelector("time");
    const profileLinks = uniq(
      Array.from(row.querySelectorAll('a[href*="/@"]')).map((el) => (el.href || "").split("?")[0])
    );
    const externalLinks = uniq(
      Array.from(row.querySelectorAll("a[href]"))
        .map((el) => el.href || "")
        .filter((href) => href && !/threads\.(?:net|com)/i.test(href))
    );
    cards.push({
      post_url: postUrl,
      feed_position: feedPosition,
      profile_links: profileLinks,
      handle: profileLinks.length ? (profileLinks[0].match(/threads\.(?:net|com)\/(@[^/?#]+)/i) || ["", ""])[1] : "",
      time_text: timeEl ? cleanText(timeEl.innerText) : "",
      time_datetime: timeEl ? (timeEl.getAttribute("datetime") || "") : "",
      preview_text: previewText,
      text_blocks: textBlocks.slice(0, 12),
      likes_text: parseMetricValue(row, ["좋아요", "Like"]),
      replies_text: parseMetricValue(row, ["댓글", "답글", "Reply"]),
      reposts_text: parseMetricValue(row, ["리포스트", "Repost"]),
      shares_text: parseMetricValue(row, ["공유하기", "공유", "Share", "보내기"]),
      is_reply_context: textBlocks.some((text) => text.includes("답글")),
      has_external_link: externalLinks.length > 0,
      has_expiry_text: textBlocks.some((text) => text.includes("남음")),
      external_links: externalLinks.slice(0, 6),
      native_media_count: media.native_media_count,
      native_images: media.native_images.slice(0, 6),
      external_preview_images: media.external_preview_images.slice(0, 6),
      videos: media.videos.slice(0, 6),
    });
  }
  return cards;
})();
"""

DETAIL_JS = r"""
return (function() {
  function rawText(value) {
    return (value || "").trim();
  }
  function cleanText(value) {
    return (value || "").replace(/\s+/g, " ").trim();
  }
  function uniq(values) {
    return Array.from(new Set((values || []).filter(Boolean)));
  }
  function normalizeHref(value) {
    return (value || "").split("?")[0].replace("threads.net", "threads.com");
  }
  const currentHref = normalizeHref(window.location.href || "");
  function isMetricText(text) {
    if (!text) {
      return true;
    }
    if (/^\d+([.,]\d+)?([km])?$/i.test(text)) {
      return true;
    }
    if (/^\d+\s*(views?|replies?|reply|likes?|reposts?|shares?)$/i.test(text)) {
      return true;
    }
    if (/^\d+[smhdwy]$/i.test(text)) {
      return true;
    }
    if (/^\d{4}-\d{2}-\d{2}$/.test(text)) {
      return true;
    }
    return false;
  }
  function isNoiseText(text) {
    const lowered = cleanText(text).toLowerCase();
    if (!lowered) {
      return true;
    }
    if (isMetricText(lowered)) {
      return true;
    }
    return (
      lowered === "threads" ||
      lowered === "see translation" ||
      lowered === "related threads" ||
      lowered === "author" ||
      lowered === "like" ||
      lowered === "reply" ||
      lowered === "repost" ||
      lowered === "share" ||
      lowered === "follow" ||
      lowered === "번역하기" ||
      lowered === "활동 보기" ||
      lowered === "좋아요" ||
      lowered === "답글" ||
      lowered === "리포스트" ||
      lowered === "공유" ||
      lowered === "공유하기" ||
      lowered === "팔로우" ||
      lowered === "더 보기"
    );
  }
  function normalizePostText(value) {
    const lines = rawText(value).split(/\n+/).map((line) => cleanText(line)).filter(Boolean);
    const cleaned = [];
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (isNoiseText(line)) {
        continue;
      }
      if (/^\d+\s*\/\s*\d+$/.test(line)) {
        continue;
      }
      if (/^\d+$/.test(line) && lines[i + 1] === "/" && /^\d+$/.test(lines[i + 2] || "")) {
        i += 2;
        continue;
      }
      if (line === "/" && cleaned.length && /^\d+$/.test(cleaned[cleaned.length - 1]) && /^\d+$/.test(lines[i + 1] || "")) {
        cleaned.pop();
        i += 1;
        continue;
      }
      cleaned.push(line);
    }
    return cleaned.join("\n").replace(/\n{3,}/g, "\n\n").trim();
  }
  function numericWeight(value) {
    const parsed = parseInt(value || "400", 10);
    return Number.isFinite(parsed) ? parsed : 400;
  }
  function collectCandidates(container, handleSet) {
    const likeSvgs = Array.from(container.querySelectorAll("svg")).filter((svg) => {
      const aria = (svg.getAttribute("aria-label") || "").trim();
      const title = (svg.querySelector("title")?.textContent || "").trim();
      return aria === "Like" || aria === "좋아요" || title === "Like" || title === "좋아요";
    }).filter((svg) => svg.getBoundingClientRect().y > 40);
    const maxY = likeSvgs.length ? likeSvgs[0].getBoundingClientRect().y : Number.POSITIVE_INFINITY;
    const candidates = [];
    for (const node of Array.from(container.querySelectorAll('[dir="auto"]'))) {
      const text = normalizePostText(node.innerText || node.textContent || "");
      const inline = cleanText(text);
      const rect = node.getBoundingClientRect();
      const style = window.getComputedStyle(node);
      const fontSize = parseFloat(style.fontSize || "0");
      const fontWeight = numericWeight(style.fontWeight);
      if (!inline || isNoiseText(inline)) {
        continue;
      }
      if (handleSet.has(inline)) {
        continue;
      }
      if (node.closest("time") || node.closest('a[href*="/@"]')) {
        continue;
      }
      if (fontSize < 12 || fontSize > 20 || fontWeight >= 700) {
        continue;
      }
      if (rect.y < 40 || rect.y > maxY - 8 || rect.width < 20 || rect.height < 8) {
        continue;
      }
      let score = inline.length;
      if (/[가-힣A-Za-z]{3,}/.test(inline)) {
        score += 10;
      }
      if (text.includes("\n")) {
        score += 25;
      }
      candidates.push({node, text, inline, score, y: rect.y, x: rect.x, maxY});
    }
    candidates.sort((a, b) => (b.score - a.score) || (a.y - b.y) || (a.x - b.x));
    return candidates;
  }
  function selectCluster(candidate, container) {
    let best = candidate.text;
    let bestLength = cleanText(best).length;
    let node = candidate.node;
    for (let depth = 0; node && depth < 10; depth++, node = node.parentElement) {
      const rect = node.getBoundingClientRect();
      if (rect.y < 40 || rect.y > candidate.maxY - 8) {
        continue;
      }
      if (node.querySelectorAll('[role="button"],button').length > 0) {
        continue;
      }
      const text = normalizePostText(node.innerText || node.textContent || "");
      const inline = cleanText(text);
      if (!inline || !inline.includes(candidate.inline.slice(0, Math.min(20, candidate.inline.length)))) {
        continue;
      }
      if (inline.length >= bestLength) {
        best = text;
        bestLength = inline.length;
      }
      if (node === container) {
        break;
      }
    }
    return best;
  }
  function joinCandidates(candidates) {
    const sorted = candidates.slice().sort((a, b) => (a.y - b.y) || (a.x - b.x));
    let out = [];
    for (const candidate of sorted) {
      const text = normalizePostText(candidate.text);
      const inline = cleanText(text);
      if (!inline || out.some((prev) => cleanText(prev).includes(inline))) {
        continue;
      }
      out = out.filter((prev) => !inline.includes(cleanText(prev)));
      out.push(text);
    }
    return normalizePostText(out.join("\n"));
  }
  function extractContentText(container, handleSet) {
    const candidates = collectCandidates(container, handleSet);
    if (!candidates.length) {
      return "";
    }
    const cluster = selectCluster(candidates[0], container);
    const joined = joinCandidates(candidates);
    const clusterInline = cleanText(cluster);
    const joinedInline = cleanText(joined);
    if (joinedInline.length > clusterInline.length && !joinedInline.includes(clusterInline)) {
      return joined;
    }
    return cluster || joined;
  }
  function buildCard(container) {
    const postLinks = uniq(
      Array.from(container.querySelectorAll('a[href*="/post/"]'))
        .map((node) => normalizeHref(node.href || ""))
        .filter(Boolean)
    );
    if (!postLinks.length) {
      return null;
    }
    const handleTexts = uniq(
      Array.from(container.querySelectorAll('a[href*="/@"]'))
        .map((node) => cleanText(node.innerText))
        .filter(Boolean)
    );
    const handleSet = new Set(handleTexts);
    return {
      post_links: postLinks,
      content_text: extractContentText(container, handleSet),
      created_at: (container.querySelector("time") || {}).dateTime || "",
    };
  }
  const cards = Array.from(document.querySelectorAll('article, div[data-pressable-container="true"]'))
    .map(buildCard)
    .filter(Boolean);
  const currentCard = cards.find((card) => card.post_links.includes(currentHref));
  if (!currentCard) {
    return {error: "no_current_card"};
  }
  const firstReplyUrl = (cards.find((card) => (card.post_links[0] || "") !== currentHref) || {}).post_links?.[0] || "";
  return {
    content_text: currentCard.content_text || "",
    first_reply_url: firstReplyUrl,
    created_at: currentCard.created_at || "",
  };
})();
"""


def parse_metric_to_int(value):
    text = str(value or "").strip()
    if not text:
        return 0
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)", text.replace(",", ""))
    if not match:
        return 0
    number = float(match.group(1))
    multiplier = 1
    lowered = text.lower()
    if "천" in text or lowered.endswith("k"):
        multiplier = 1000
    elif "만" in text:
        multiplier = 10000
    elif lowered.endswith("m"):
        multiplier = 1000000
    return int(number * multiplier)


def now_iso():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_driver(headless=False):
    driver = Driver(uc=True, headless=headless, browser="chrome")
    driver.set_page_load_timeout(40)
    return driver


def open_threads_home(driver):
    driver.get("https://www.threads.net/")
    time.sleep(TIMEOUT_SECONDS)
    dismiss_thread_popup(driver)
    time.sleep(1)


def extract_feed_cards(driver):
    try:
        cards = driver.execute_script(CARD_JS) or []
    except Exception:
        return []
    normalized = []
    for card in cards:
        likes = parse_metric_to_int(card.get("likes_text"))
        replies = parse_metric_to_int(card.get("replies_text"))
        reposts = parse_metric_to_int(card.get("reposts_text"))
        shares = parse_metric_to_int(card.get("shares_text"))
        normalized.append(
            {
                **card,
                "likes": likes,
                "replies": replies,
                "reposts": reposts,
                "shares": shares,
                "interaction_total": likes + replies + reposts + shares,
                "has_native_media": (card.get("native_media_count") or 0) > 0,
            }
        )
    return normalized


def extract_detail_context(driver):
    try:
        result = driver.execute_script(DETAIL_JS) or {}
    except Exception as exc:
        return {"error": f"detail_js_failed:{exc}"}
    if result.get("error"):
        return result
    return {
        "content_text": str(result.get("content_text") or "").strip(),
        "first_reply_url": str(result.get("first_reply_url") or "").strip(),
        "created_at": str(result.get("created_at") or "").strip(),
    }


def normalize_count_text(text):
    cleaned = " ".join(str(text or "").split())
    cleaned = cleaned.replace("번역하기", "").replace("See translation", "").strip()
    return cleaned


def inspect_candidate(driver, post_url):
    driver.get(post_url)
    time.sleep(TIMEOUT_SECONDS)
    dismiss_thread_popup(driver)
    detail = extract_detail_context(driver)
    if detail.get("error"):
        return {"status": "open_failed", "error": detail["error"], "post_url": post_url}

    post_page_coupang = _extract_coupang_urls_from_current_page(driver)
    first_reply_url = detail.get("first_reply_url", "")
    first_reply_text = ""
    first_reply_text_raw = ""
    first_reply_length = 0
    first_reply_coupang = []

    if first_reply_url:
        driver.get(first_reply_url)
        time.sleep(TIMEOUT_SECONDS)
        dismiss_thread_popup(driver)
        reply_detail = extract_detail_context(driver)
        first_reply_text_raw = str(reply_detail.get("content_text", "") or "").strip()
        first_reply_text = normalize_count_text(first_reply_text_raw)
        first_reply_length = len(first_reply_text)
        first_reply_coupang = _extract_coupang_urls_from_current_page(driver)

    comment_coupang_urls = list(dict.fromkeys(first_reply_coupang))
    all_coupang_urls = list(dict.fromkeys(post_page_coupang + first_reply_coupang))

    return {
        "status": "ok",
        "post_url": post_url,
        "content_text": normalize_count_text(detail.get("content_text", "")),
        "content_text_raw": str(detail.get("content_text", "") or "").strip(),
        "post_created_at": detail.get("created_at", ""),
        "first_reply_url": first_reply_url,
        "first_reply_text": first_reply_text,
        "first_reply_text_raw": first_reply_text_raw,
        "first_reply_length": first_reply_length,
        "post_page_coupang_urls": post_page_coupang,
        "comment_coupang_urls": comment_coupang_urls,
        "all_coupang_urls": all_coupang_urls,
    }


def load_existing_links(excel_path):
    if not excel_path:
        return set()
    path = Path(excel_path)
    if not path.exists():
        return set()
    existing = set()
    try:
        sheets = pd.read_excel(path, sheet_name=None)
    except Exception:
        return set()
    for df in sheets.values():
        for column in df.columns:
            if str(column).strip().lower() in {"post_url", "link", "url", "링크"}:
                existing.update(str(value).strip() for value in df[column].dropna() if str(value).strip())
    return existing


def write_outputs(excel_path, accepted_rows, review_rows, event_rows, summary_row):
    excel_path.parent.mkdir(parents=True, exist_ok=True)
    accepted_df = pd.DataFrame(accepted_rows)
    review_df = pd.DataFrame(review_rows)
    events_df = pd.DataFrame(event_rows)
    summary_df = pd.DataFrame([summary_row])
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        accepted_df.to_excel(writer, sheet_name="accepted", index=False)
        review_df.to_excel(writer, sheet_name="review_long_comment", index=False)
        events_df.to_excel(writer, sheet_name="events", index=False)
        summary_df.to_excel(writer, sheet_name="summary", index=False)


def build_output_path(output_dir):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(output_dir) / f"threads_feed_sourcing_{stamp}.xlsx"


def scroll_feed(driver):
    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.PAGE_DOWN)
    time.sleep(SCROLL_PAUSE_SECONDS)
    dismiss_thread_popup(driver)


def append_event(event_rows, stage, status, reason, payload):
    row = {
        "time": now_iso(),
        "stage": stage,
        "status": status,
        "reason": reason,
        **payload,
    }
    event_rows.append(row)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(Path(__file__).resolve().parent / "feed_sourcing_runs"))
    parser.add_argument("--existing-excel", default="")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--max-idle-scrolls", type=int, default=MAX_IDLE_SCROLLS)
    parser.add_argument("--max-preopen-skip-streak", type=int, default=DEFAULT_PREOPEN_SKIP_STREAK)
    parser.add_argument("--max-no-coupang-streak", type=int, default=DEFAULT_NO_COUPANG_STREAK)
    parser.add_argument("--min-interaction-total", type=int, default=DEFAULT_MIN_INTERACTION_TOTAL)
    parser.add_argument("--long-comment-threshold", type=int, default=DEFAULT_LONG_COMMENT_THRESHOLD)
    parser.add_argument("--max-seen-cards", type=int, default=0, help="0 means unlimited")
    parser.add_argument("--max-open-candidates", type=int, default=0, help="0 means unlimited")
    args = parser.parse_args()

    existing_links = load_existing_links(args.existing_excel)
    output_path = build_output_path(args.output_dir)

    accepted_rows = []
    review_rows = []
    event_rows = []
    driver = None
    visited = set()
    preopen_skip_streak = 0
    no_coupang_streak = 0
    idle_scrolls = 0
    opened_candidates = 0
    stop_reason = "completed"
    stop_status = "ok"

    try:
        driver = init_driver(headless=args.headless)
        open_threads_home(driver)
        print(f"[Start] Threads home opened: {driver.current_url}", flush=True)

        while True:
            cards = extract_feed_cards(driver)
            new_cards = [card for card in cards if card.get("post_url") and card["post_url"] not in visited]

            if not new_cards:
                idle_scrolls += 1
                if idle_scrolls >= args.max_idle_scrolls:
                    stop_reason = "feed_exhausted"
                    break
                scroll_feed(driver)
                continue

            idle_scrolls = 0
            for card in new_cards:
                post_url = card["post_url"]
                visited.add(post_url)

                if args.max_seen_cards and len(visited) > args.max_seen_cards:
                    stop_reason = "max_seen_cards_reached"
                    break

                base_payload = {
                    "post_url": post_url,
                    "handle": card.get("handle", ""),
                    "interaction_total": card.get("interaction_total", 0),
                    "likes": card.get("likes", 0),
                    "replies": card.get("replies", 0),
                    "reposts": card.get("reposts", 0),
                    "shares": card.get("shares", 0),
                    "native_media_count": card.get("native_media_count", 0),
                    "preview_text": card.get("preview_text", ""),
                }

                if post_url in existing_links:
                    preopen_skip_streak += 1
                    append_event(event_rows, "pre_open", "skip", "already_recorded", base_payload)
                elif card.get("interaction_total", 0) < args.min_interaction_total:
                    preopen_skip_streak += 1
                    append_event(event_rows, "pre_open", "skip", "low_interaction", base_payload)
                elif not card.get("has_native_media", False):
                    preopen_skip_streak += 1
                    append_event(event_rows, "pre_open", "skip", "no_native_media", base_payload)
                else:
                    if args.max_open_candidates and opened_candidates >= args.max_open_candidates:
                        stop_reason = "max_open_candidates_reached"
                        break

                    preopen_skip_streak = 0
                    append_event(event_rows, "pre_open", "open", "candidate", base_payload)
                    opened_candidates += 1
                    detail = inspect_candidate(driver, post_url)
                    if detail.get("status") != "ok":
                        append_event(event_rows, "detail", "skip", detail.get("error", "open_failed"), base_payload)
                        continue

                    row = {
                        **base_payload,
                        "time": now_iso(),
                        "time_text": card.get("time_text", ""),
                        "time_datetime": card.get("time_datetime", ""),
                        "is_reply_context": card.get("is_reply_context", False),
                        "has_external_link": card.get("has_external_link", False),
                        "has_expiry_text": card.get("has_expiry_text", False),
                        "detail_text": detail.get("content_text", ""),
                        "detail_text_raw": detail.get("content_text_raw", ""),
                        "first_reply_url": detail.get("first_reply_url", ""),
                        "first_reply_text": detail.get("first_reply_text", ""),
                        "first_reply_text_raw": detail.get("first_reply_text_raw", ""),
                        "first_reply_length": detail.get("first_reply_length", 0),
                        "comment_coupang_count": len(detail.get("comment_coupang_urls", [])),
                        "comment_coupang_url": (detail.get("comment_coupang_urls") or [""])[0],
                        "post_created_at": detail.get("post_created_at", ""),
                    }

                    if not detail.get("comment_coupang_urls"):
                        no_coupang_streak += 1
                        append_event(event_rows, "detail", "skip", "no_coupang_comment", row)
                    else:
                        no_coupang_streak = 0
                        if row["first_reply_length"] >= args.long_comment_threshold:
                            row["tag"] = "review_long_first_comment"
                            review_rows.append(row)
                            append_event(event_rows, "detail", "review", "long_first_comment", row)
                            existing_links.add(post_url)
                        else:
                            row["tag"] = "accepted_coupang_comment"
                            accepted_rows.append(row)
                            append_event(event_rows, "detail", "accept", "accepted_coupang_comment", row)
                            existing_links.add(post_url)

                    if no_coupang_streak >= args.max_no_coupang_streak:
                        stop_reason = "no_coupang_streak_reached"
                        stop_status = "failed"
                        break

                if preopen_skip_streak > args.max_preopen_skip_streak:
                    stop_reason = "preopen_skip_streak_reached"
                    stop_status = "failed"
                    break

            if stop_reason != "completed":
                break

            scroll_feed(driver)

    finally:
        summary_row = {
            "time": now_iso(),
            "stop_status": stop_status,
            "stop_reason": stop_reason,
            "visited_count": len(visited),
            "opened_candidates": opened_candidates,
            "accepted_count": len(accepted_rows),
            "review_count": len(review_rows),
            "event_count": len(event_rows),
            "preopen_skip_streak_final": preopen_skip_streak,
            "no_coupang_streak_final": no_coupang_streak,
            "output_path": str(output_path),
        }
        write_outputs(output_path, accepted_rows, review_rows, event_rows, summary_row)
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

    print(json.dumps(summary_row, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
