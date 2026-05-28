import argparse
import json
import sys
import time
import urllib.parse
from pathlib import Path

from seleniumbase import Driver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from scraper import dismiss_thread_popup


try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def build_search_url(keyword):
    return "https://www.threads.com/search?q=" + urllib.parse.quote(keyword) + "&serp_type=default"


def count_posts(driver):
    return driver.execute_script(
        """
        return (function() {
          const rows = Array.from(document.querySelectorAll("div[data-virtualized]"));
          const postLinks = Array.from(document.querySelectorAll('a[href*="/post/"]'))
            .map((a) => (a.href || "").split("?")[0].replace(/\\/media$/, ""));
          const uniquePosts = Array.from(new Set(postLinks));
          const visibleRows = rows.map((row) => ({
            text: (row.innerText || "").replace(/\\s+/g, " ").trim().slice(0, 180),
            links: Array.from(row.querySelectorAll('a[href*="/post/"]')).map((a) => (a.href || "").split("?")[0]).slice(0, 3)
          })).filter((row) => row.links.length);
          return {
            data_virtualized: rows.length,
            post_links: postLinks.length,
            unique_posts: uniquePosts.length,
            scroll_y: window.scrollY,
            scroll_height: document.documentElement.scrollHeight,
            inner_height: window.innerHeight,
            scrollers: Array.from(document.querySelectorAll("*")).filter((el) => {
              const style = window.getComputedStyle(el);
              return (style.overflowY === "auto" || style.overflowY === "scroll") &&
                el.scrollHeight > el.clientHeight + 100;
            }).map((el) => ({
              scrollTop: el.scrollTop,
              scrollHeight: el.scrollHeight,
              clientHeight: el.clientHeight,
              postLinks: el.querySelectorAll('a[href*="/post/"]').length
            })).sort((a, b) => (b.scrollHeight - b.clientHeight) - (a.scrollHeight - a.clientHeight)).slice(0, 4),
            visible_rows: visibleRows.slice(0, 12)
          };
        })();
        """
    )


def scroll_once(driver, mode):
    if mode == "pagedown":
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.PAGE_DOWN)
    elif mode == "end":
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.END)
    else:
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
              return {before, after: target.scrollTop || window.scrollY || 0};
            })();
            """
        )
    time.sleep(2.5)
    dismiss_thread_popup(driver)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keyword", required=True)
    parser.add_argument("--scrolls", type=int, default=20)
    parser.add_argument("--mode", choices=["js", "pagedown", "end"], default="js")
    parser.add_argument("--output-dir", default=str(Path(__file__).resolve().parent / "keyword_research_runs" / "deep_scroll_probe"))
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    driver = Driver(uc=True, headless=False, browser="chrome", page_load_strategy="eager")
    driver.set_page_load_timeout(35)
    rows = []
    try:
        driver.get(build_search_url(args.keyword))
        time.sleep(8)
        dismiss_thread_popup(driver)
        for i in range(args.scrolls + 1):
            state = count_posts(driver)
            state["step"] = i
            state["keyword"] = args.keyword
            rows.append(state)
            print(
                f"[{args.keyword}] step={i} unique={state['unique_posts']} post_links={state['post_links']} "
                f"rows={state['data_virtualized']} y={state['scroll_y']}/{state['scroll_height']}",
                flush=True,
            )
            if i < args.scrolls:
                scroll_once(driver, args.mode)
        html_path = out_dir / f"{args.keyword}_final.html"
        png_path = out_dir / f"{args.keyword}_final.png"
        html_path.write_text(driver.page_source or "", encoding="utf-8")
        driver.save_screenshot(str(png_path))
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    summary_path = out_dir / f"{args.keyword}_summary.json"
    summary_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary_path": str(summary_path), "final_unique_posts": rows[-1]["unique_posts"] if rows else 0}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
