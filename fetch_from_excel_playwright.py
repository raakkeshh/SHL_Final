# fetch_from_excel_playwright.py
"""
Robust Playwright scraper for SHL assessment pages.
Reads URLs from 'Gen_AI Dataset.xlsx' (column containing 'http' or 'Assessment_url'),
visits each page headlessly, waits for networkidle, scrolls, extracts:
  - page title
  - meta description
  - main article text (paragraphs, headings, lists)
  - visible button/label text
  - any structured product description blocks
Saves results to data/catalog_from_excel_full.csv
"""

import pandas as pd
import os, time, re, json
from playwright.sync_api import sync_playwright
from urllib.parse import urlparse

DF_PATH = "Gen_AI Dataset.xlsx"
OUT_CSV = "data/catalog_from_excel_full.csv"
os.makedirs("data", exist_ok=True)

def find_url_column(df):
    # heuristic: find a column that contains 'http' or 'www' in most rows
    for col in df.columns:
        sample = df[col].astype(str).head(50).str.lower()
        hits = sample.str.contains("http").sum() + sample.str.contains("www").sum()
        if hits >= 1:
            return col
    # fallback common column name
    for name in ["Assessment_url", "URL", "url", "link"]:
        if name in df.columns:
            return name
    raise RuntimeError("No URL-like column found in Excel. Please ensure a column with page URLs exists.")

def extract_main_text(page):
    """Try multiple approaches to extract visible textual content."""
    parts = []

    # Title tag
    try:
        t = page.title().strip()
        if t:
            parts.append(t)
    except Exception:
        pass

    # meta description
    try:
        desc = page.locator('meta[name="description"]').get_attribute('content')
        if desc:
            parts.append(desc.strip())
    except Exception:
        pass

    # main element(s)
    try:
        # attempt to capture main/article sections
        main_selectors = [
            "main",
            "article",
            "div[class*='content']",
            "div[class*='product']",
            "section[class*='content']",
            "div[class*='description']",
            "div[class*='product-description']",
            "div[class*='page']",
        ]
        seen = set()
        for sel in main_selectors:
            nodes = page.locator(sel)
            if nodes.count() == 0:
                continue
            for i in range(nodes.count()):
                txt = nodes.nth(i).inner_text(timeout=2000).strip()
                if txt:
                    # sanitize whitespace and de-duplicate
                    txt = re.sub(r"\s+", " ", txt)
                    if txt not in seen:
                        parts.append(txt)
                        seen.add(txt)
    except Exception:
        pass

    # specific blocks: headings + paragraphs + list items
    try:
        elems = page.locator("h1, h2, h3, h4, p, li, span")
        # limit to first ~1000 elements
        max_elems = min(200, elems.count() if elems.count() is not None else 0)
        seen_s = set()
        for i in range(max_elems):
            try:
                txt = elems.nth(i).inner_text(timeout=500).strip()
            except Exception:
                continue
            if not txt:
                continue
            txt = re.sub(r"\s+", " ", txt)
            if len(txt) < 10:
                # very short; include if contains colon or keyword
                if ":" not in txt:
                    continue
            if txt not in seen_s:
                parts.append(txt)
                seen_s.add(txt)
    except Exception:
        pass

    # aria/alt attributes (images with alt text)
    try:
        imgs = page.locator("img[alt]")
        for i in range(min(50, imgs.count() if imgs.count() is not None else 0)):
            alt = imgs.nth(i).get_attribute("alt")
            if alt:
                alt = alt.strip()
                if alt not in seen:
                    parts.append(alt)
                    seen.add(alt)
    except Exception:
        pass

    # fallback: full body text
    if not parts:
        try:
            body = page.locator("body").inner_text()
            if body:
                body = re.sub(r"\s+", " ", body).strip()
                parts.append(body)
        except Exception:
            pass

    # join with separators
    joined = "\n\n".join(parts)
    # remove repeated boilerplate lines (e.g., "We recommend upgrading...")
    joined = re.sub(r"We recommend upgrading to a modern browser.*", "", joined, flags=re.I)
    return joined.strip()

def fetch_urls(urls, headless=True, limit=None, pause_between=0.6):
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        for idx, u in enumerate(urls):
            if limit and idx >= limit:
                break
            print(f"[{idx+1}/{len(urls)}] Fetching: {u}")
            try:
                page.goto(u, timeout=60000)
                page.wait_for_load_state("networkidle", timeout=30000)
            except Exception as e:
                print("Initial goto failed:", e)
                try:
                    page.goto(u, timeout=120000)
                    page.wait_for_load_state("networkidle", timeout=60000)
                except Exception as e2:
                    print("Double-goto failed, skipping:", u, e2)
                    results.append({"source_url": u, "canonical_url": u, "title": "", "meta_description": "", "extracted_text": ""})
                    continue

            # scroll slowly to bottom to trigger lazy-loaded content
            try:
                page.evaluate("""() => {
                    return new Promise(resolve => {
                        let total = 0;
                        const step = 300;
                        const timer = setInterval(() => {
                            window.scrollBy(0, step);
                            total += step;
                            if (total > document.body.scrollHeight) {
                                clearInterval(timer);
                                resolve(true);
                            }
                        }, 120);
                        setTimeout(() => { clearInterval(timer); resolve(true); }, 3000);
                    });
                }""")
                page.wait_for_timeout(700)
            except Exception:
                pass

            # extract
            try:
                title = page.title().strip()
            except Exception:
                title = ""

            meta_desc = ""
            try:
                md = page.locator('meta[name="description"]').get_attribute('content')
                if md:
                    meta_desc = md.strip()
            except Exception:
                pass

            text = extract_main_text(page)
            snippet = (text[:1200] if text else "")  # short snippet for CSV preview

            results.append({
                "source_url": u,
                "canonical_url": u,
                "title": title,
                "meta_description": meta_desc,
                "extracted_text": text,
                "text_snippet": snippet
            })

            time.sleep(pause_between)
        browser.close()
    return results

def main():
    # read excel
    df = pd.read_excel(DF_PATH)
    url_col = find_url_column(df)
    print("Using URL column:", url_col)
    urls = df[url_col].dropna().astype(str).drop_duplicates().tolist()
    print("Found urls:", len(urls))

    # fetch
    data = fetch_urls(urls, headless=True, pause_between=0.5)

    # save
    outdf = pd.DataFrame(data)
    outdf.to_csv(OUT_CSV, index=False)
    print("Saved:", OUT_CSV)

if __name__ == "__main__":
    main()
