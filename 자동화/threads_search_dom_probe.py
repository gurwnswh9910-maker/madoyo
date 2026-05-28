import json
import sys
import time
from datetime import datetime
from pathlib import Path

from seleniumbase import Driver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException

from scraper import dismiss_thread_popup


try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

OUT_DIR = Path(__file__).resolve().parent / "keyword_research_runs" / "dom_probe_20260514"
WAIT_SECONDS = 8


def now_stamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def open_page(driver, url):
    try:
        driver.get(url)
    except TimeoutException:
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass
    time.sleep(WAIT_SECONDS)
    dismiss_thread_popup(driver)
    time.sleep(1)


def text_head(driver, limit=2000):
    try:
        text = driver.execute_script("return document.body ? document.body.innerText : ''") or ""
    except Exception:
        text = ""
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())[:limit]


def count_selector(driver, selector):
    try:
        return len(driver.find_elements(By.CSS_SELECTOR, selector))
    except Exception:
        return 0


def collect_js(driver):
    try:
        return driver.execute_script(
            """
            return (function() {
              function clean(value) {
                return (value || "").replace(/\\s+/g, " ").trim();
              }
              const links = Array.from(document.querySelectorAll("a[href]")).slice(0, 80).map((a) => ({
                href: a.href || "",
                text: clean(a.innerText || a.textContent || ""),
                aria: clean(a.getAttribute("aria-label") || "")
              }));
              const fields = Array.from(document.querySelectorAll("input, textarea, [contenteditable='true'], [role='searchbox']")).slice(0, 40).map((el) => ({
                tag: el.tagName,
                role: el.getAttribute("role") || "",
                type: el.getAttribute("type") || "",
                placeholder: el.getAttribute("placeholder") || "",
                aria: el.getAttribute("aria-label") || "",
                text: clean(el.innerText || el.value || "")
              }));
              const virtualized = Array.from(document.querySelectorAll("div[data-virtualized]")).slice(0, 12).map((el) => ({
                text: clean(el.innerText || "").slice(0, 500),
                post_links: Array.from(el.querySelectorAll('a[href*="/post/"]')).map((a) => a.href).slice(0, 4)
              }));
              return {
                links,
                fields,
                virtualized,
                post_link_count: Array.from(document.querySelectorAll('a[href*="/post/"]')).length,
                virtualized_count: document.querySelectorAll("div[data-virtualized]").length,
                scripts_with_relay: Array.from(document.scripts).filter((s) => (s.src || "").includes("relay")).slice(0, 10).map((s) => s.src)
              };
            })();
            """
        )
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def snapshot(driver, label):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    prefix = OUT_DIR / f"{now_stamp()}_{label}"
    html_path = str(prefix.with_suffix(".html"))
    png_path = str(prefix.with_suffix(".png"))
    try:
        Path(html_path).write_text(driver.page_source or "", encoding="utf-8")
    except Exception:
        html_path = ""
    try:
        driver.save_screenshot(png_path)
    except Exception:
        png_path = ""
    return {
        "label": label,
        "url": getattr(driver, "current_url", ""),
        "title": getattr(driver, "title", ""),
        "text_head": text_head(driver),
        "selector_counts": {
            "data_virtualized": count_selector(driver, "div[data-virtualized]"),
            "post_links": count_selector(driver, 'a[href*="/post/"]'),
            "search_links": count_selector(driver, 'a[href*="/search"]'),
            "inputs": count_selector(driver, "input"),
            "textareas": count_selector(driver, "textarea"),
            "searchboxes": count_selector(driver, '[role="searchbox"]'),
        },
        "dom": collect_js(driver),
        "html_path": html_path,
        "png_path": png_path,
    }


def type_search_and_snapshot(driver, keyword):
    open_page(driver, "https://www.threads.com/search")
    try:
        search_input = driver.find_element(By.CSS_SELECTOR, 'input[type="search"]')
        search_input.clear()
        search_input.send_keys(keyword)
        time.sleep(3)
        typed = snapshot(driver, "search_typed_korean")
        search_input.send_keys(Keys.ENTER)
        time.sleep(WAIT_SECONDS)
        dismiss_thread_popup(driver)
        entered = snapshot(driver, "search_enter_korean")
        return [typed, entered]
    except Exception as exc:
        result = snapshot(driver, "search_type_failed")
        result["type_error"] = f"{type(exc).__name__}: {exc}"
        return [result]


def main():
    driver = Driver(uc=True, headless=False, browser="chrome", page_load_strategy="eager")
    driver.set_page_load_timeout(35)
    results = []
    try:
        direct_url = "https://www.threads.net/search?q=%EC%99%B8%EB%A1%9C%EC%9B%80%20%EC%A3%BC%EB%A7%90"
        open_page(driver, direct_url)
        results.append(snapshot(driver, "direct_search_net"))

        search_home_url = "https://www.threads.com/search"
        open_page(driver, search_home_url)
        results.append(snapshot(driver, "search_home_com"))

        results.extend(type_search_and_snapshot(driver, "외로움"))

        tag_url = "https://www.threads.com/search?q=NFL%20Threads&serp_type=tags&tag_id=18323298895111531"
        open_page(driver, tag_url)
        results.append(snapshot(driver, "known_tag_search_com"))

        home_url = "https://www.threads.net/"
        open_page(driver, home_url)
        results.append(snapshot(driver, "home_net"))
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = OUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary_path": str(summary_path), "results": results}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
