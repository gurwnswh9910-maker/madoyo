import logging
import os
import re
import time
from seleniumbase import Driver
from selenium.webdriver.common.by import By
from api.logging_utils import get_logger, log_event, preview_text

logger = get_logger(__name__)


def _default_threads_data():
    return {
        "content_text": "",
        "views": 0,
        "likes": 0,
        "replies": 0,
        "reposts": 0,
        "shares": 0,
        "created_at": "",
        "image_urls": [],
        "first_reply_views": 0,
    }


def _normalize_threads_url(url: str) -> str:
    if not url:
        return url
    if "threads.com" in url:
        return url.replace("threads.com", "threads.net")
    return url


def get_views_global(driver):
    patterns = [
        "//span[contains(text(), '조회')]",
        "//span[contains(text(), 'Views')]",
        "//span[contains(text(), 'views')]",
    ]
    for pattern in patterns:
        try:
            view_el = driver.find_element(By.XPATH, pattern)
            return view_el.text.strip()
        except Exception:
            continue
    return "0"


def get_metric_inside_box(parent_el, label_names):
    if isinstance(label_names, str):
        label_names = [label_names]
    for label in label_names:
        try:
            xpath = f".//*[contains(@aria-label, '{label}')]//ancestor::div[1]//span"
            element = parent_el.find_element(By.XPATH, xpath)
            return element.text.strip()
        except Exception:
            continue
    return "0"


def check_is_profile_link(el):
    try:
        el.find_element(By.XPATH, "./ancestor::a")
        return True
    except Exception:
        return False


def parse_metric_to_int(value):
    text = str(value or "").strip()
    if not text:
        return 0

    cleaned = (
        text.replace("조회", "")
        .replace("Views", "")
        .replace("views", "")
        .replace(",", "")
        .strip()
    )

    match = re.search(r"([0-9]+(?:\.[0-9]+)?)", cleaned)
    if not match:
        return 0

    number = float(match.group(1))
    multiplier = 1

    lowered = cleaned.lower()
    if "천" in cleaned or lowered.endswith("k"):
        multiplier = 1_000
    elif "만" in cleaned:
        multiplier = 10_000
    elif lowered.endswith("m"):
        multiplier = 1_000_000

    return int(number * multiplier)


def get_threads_full_data(url):
    """Scrape a Threads post and return text, media, and engagement metrics."""
    normalized_url = _normalize_threads_url(url)
    chrome_bin = os.environ.get("CHROME_BIN", "/usr/bin/google-chrome")
    extra_args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--single-process",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-client-side-phishing-detection",
        "--disable-default-apps",
        "--disable-extensions",
        "--mute-audio",
    ]

    log_event(
        logger,
        logging.INFO,
        "scraper.threads.started",
        url=preview_text(normalized_url, limit=120),
        chrome_bin=chrome_bin,
    )

    driver = None
    data = _default_threads_data()
    try:
        driver = Driver(
            uc=True,
            headless=True,
            browser="chrome",
            binary_location=chrome_bin,
            extra_args=extra_args,
        )
        log_event(logger, logging.INFO, "scraper.driver.created", url=preview_text(normalized_url, limit=120))

        driver.get(normalized_url)
        log_event(logger, logging.INFO, "scraper.page.loaded", url=preview_text(normalized_url, limit=120))
        time.sleep(8)

        try:
            clicked_count = 0
            for _ in range(5):
                next_buttons = driver.find_elements(
                    By.CSS_SELECTOR,
                    "div[role='button'][aria-label='Next'], div[role='button'][aria-label='다음']",
                )
                visible_next = [button for button in next_buttons if button.is_displayed()]
                if not visible_next:
                    break
                driver.execute_script("arguments[0].click();", visible_next[0])
                clicked_count += 1
                time.sleep(1.0)
            if clicked_count:
                log_event(
                    logger,
                    logging.INFO,
                    "scraper.carousel.advanced",
                    url=preview_text(normalized_url, limit=120),
                    click_count=clicked_count,
                )
        except Exception:
            logger.exception("scraper.carousel.failed | url=%r", normalized_url)

        js_code = """
        function extractResearchData() {
            let heartButtons = Array.from(document.querySelectorAll('svg[aria-label="Like"], svg[aria-label="좋아요"]'));
            let mainHeart = heartButtons.find(btn => btn.getBoundingClientRect().y > 50);
            if (!mainHeart) return {error: "No context"};

            let container = mainHeart.closest('article') || mainHeart.closest('div[data-pressable-container="true"]');
            if (!container) {
                let current = mainHeart;
                for (let i = 0; i < 15; i++) {
                    if (!current) break;
                    let rect = current.getBoundingClientRect();
                    if (rect.height > 150 && rect.width > 200) {
                        container = current;
                        break;
                    }
                    current = current.parentElement;
                }
            }
            if (!container) return {error: "No container"};

            function getVal(labels) {
                for (const label of labels) {
                    let el = container.querySelector(`[aria-label*="${label}"]`);
                    if (el) {
                        let span = el.closest('div')?.querySelector('span');
                        if (span) return span.innerText;
                    }
                }
                return "0";
            }

            let videoEls = Array.from(container.querySelectorAll('video'));
            let posterUrls = videoEls.map(v => v.getAttribute('poster')).filter(Boolean);
            let allImgs = Array.from(container.querySelectorAll('img')).map(img => img.src).filter(Boolean);
            let validImgs = allImgs.filter(src => src.includes('scontent') && !posterUrls.includes(src));
            let validVids = videoEls
                .map(v => v.src || v.querySelector('source')?.src || '')
                .filter(Boolean);

            let textNodes = Array.from(container.querySelectorAll('[dir="auto"]'));
            let ignoredLabels = ['좋아요', '답글', '리포스트', '공유', 'Like', 'Reply', 'Repost', 'Share'];
            let validTexts = textNodes
                .map(node => node.innerText.trim())
                .filter(text => text.length > 5 && !ignoredLabels.includes(text));
            let mainText = validTexts.length > 0
                ? validTexts.reduce((a, b) => a.length >= b.length ? a : b)
                : '';

            let firstReplyUrl = (function() {
                let parent = container.parentElement;
                let next = parent ? parent.querySelector('a[href*="/post/"]') : null;
                return (next && next.href !== window.location.href) ? next.href : null;
            })();

            return {
                text: mainText,
                likes: getVal(['좋아요', 'Like']),
                replies: getVal(['답글', 'Reply']),
                reposts: getVal(['리포스트', 'Repost']),
                shares: getVal(['보내기', '공유', 'Share']),
                media: [...validVids, ...validImgs],
                createdAt: (container.querySelector('time') || {}).dateTime || '',
                firstReplyUrl: firstReplyUrl,
            };
        }
        return extractResearchData();
        """

        result = driver.execute_script(js_code)
        if not result:
            log_event(logger, logging.WARNING, "scraper.extract.empty", url=preview_text(normalized_url, limit=120))
            return data

        if result.get("error"):
            log_event(
                logger,
                logging.WARNING,
                "scraper.extract.no_context",
                url=preview_text(normalized_url, limit=120),
                error=result.get("error"),
            )
            return data

        data["content_text"] = result.get("text", "")
        data["created_at"] = result.get("createdAt", "")
        data["likes"] = parse_metric_to_int(result.get("likes"))
        data["replies"] = parse_metric_to_int(result.get("replies"))
        data["reposts"] = parse_metric_to_int(result.get("reposts"))
        data["shares"] = parse_metric_to_int(result.get("shares"))
        data["image_urls"] = result.get("media", []) or []
        data["views"] = parse_metric_to_int(get_views_global(driver))

        log_event(
            logger,
            logging.INFO,
            "scraper.extract.completed",
            url=preview_text(normalized_url, limit=120),
            has_text=bool(data["content_text"]),
            image_count=len(data["image_urls"]),
            views=data["views"],
            likes=data["likes"],
            replies=data["replies"],
            reposts=data["reposts"],
            shares=data["shares"],
        )

        first_reply_url = result.get("firstReplyUrl")
        if first_reply_url:
            log_event(
                logger,
                logging.INFO,
                "scraper.first_reply.started",
                url=preview_text(normalized_url, limit=120),
                first_reply_url=preview_text(first_reply_url, limit=120),
            )
            driver.get(first_reply_url)
            time.sleep(5)
            data["first_reply_views"] = parse_metric_to_int(get_views_global(driver))
            log_event(
                logger,
                logging.INFO,
                "scraper.first_reply.completed",
                url=preview_text(normalized_url, limit=120),
                first_reply_views=data["first_reply_views"],
            )

        return data
    except Exception:
        logger.exception("scraper.threads.failed | url=%r", normalized_url)
        return None
    finally:
        if driver is not None:
            try:
                driver.quit()
                log_event(logger, logging.INFO, "scraper.driver.closed", url=preview_text(normalized_url, limit=120))
            except Exception:
                logger.exception("scraper.driver.close_failed | url=%r", normalized_url)


def calculate_mss_from_metrics(metrics):
    """Calculate MSS from post metrics with a first-reply preference."""
    if not metrics:
        return 0.0

    views = metrics.get("views", 0) or 0
    first_reply_views = metrics.get("first_reply_views", 0) or 0

    if views > 0 and first_reply_views > 0:
        raw_mss = (first_reply_views ** 2) / views
        return round(float(min(raw_mss * 10.0, 100.0)), 2)

    likes = metrics.get("likes", 0) or 0
    replies = metrics.get("replies", 0) or 0
    reposts = metrics.get("reposts", 0) or 0
    raw_score = (likes * 1) + (replies * 5) + (reposts * 10)
    return min(raw_score / 15.0, 100.0)
