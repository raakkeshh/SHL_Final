# crawler.py
"""
Improved SHL crawler:
- Uses requests first, falls back to Playwright for JS-rendered pages
- Expanded product URL patterns to capture /view/ assessment pages
- Polite delay, deduplication, and CSV output
- Run: python crawler.py --seeds <urls> --domain shl.com --max 600 --out data/catalog_raw.csv
"""
import os
import time
import re
import csv
import argparse
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
import pandas as pd
from tqdm import tqdm

# Try to import Playwright
PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except Exception:
    PLAYWRIGHT_AVAILABLE = False

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36 (SHL-Catalog-Crawler/1.0)"
}

# Polite delay (seconds) and a longer delay for Playwright pages
DELAY = 1.0
PLAYWRIGHT_DELAY = 1.5

# Improved patterns to catch assessment-level pages and category pages
PRODUCT_PATH_PATTERNS = [
    r"/products/product-catalog/view/",
    r"/products/product-catalog/",
    r"/products/assessments/",
    r"/products/assessments/",
    r"/products/assessments/.*",
    r"/products/assessments",  # category landing pages
    r"/products/video-interviews/",
    r"/products/assessments/skills-and-simulations/",
    r"/products/assessments/skills-and-simulations/.*",
    r"/products/assessments/behavioral-assessments/.*",
    r"/products/assessments/personality-assessment/.*",
    r"/products/assessments/.*",
    r"/product-catalog/view/",
    r"/view/",
    r"/products/"
]

# minimum length of HTML to decide whether fallback to Playwright is necessary
MIN_HTML_LENGTH_FOR_REQUESTS = 3000

def looks_like_product_url(url):
    for p in PRODUCT_PATH_PATTERNS:
        if re.search(p, url):
            return True
    return False

def fetch_with_requests(url, timeout=20):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r.text
    except Exception as e:
        # print(f"requests fetch failed for {url}: {e}")
        return None

def fetch_with_playwright(url, timeout=60):
    if not PLAYWRIGHT_AVAILABLE:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto(url, timeout=timeout*1000)
            # wait for network to be mostly idle (best-effort)
            page.wait_for_load_state("networkidle", timeout=timeout*1000/2)
            content = page.content()
            browser.close()
            time.sleep(PLAYWRIGHT_DELAY)
            return content
    except Exception:
        return None

def fetch_page(url, force_playwright=False):
    # try requests first unless forced
    if not force_playwright:
        html = fetch_with_requests(url)
        if html and len(html) >= MIN_HTML_LENGTH_FOR_REQUESTS:
            return html, "requests"
        # if small/empty html, try playwright
    html2 = fetch_with_playwright(url)
    if html2:
        return html2, "playwright"
    # fallback to whatever requests returned (could be None)
    return fetch_with_requests(url), "requests-fallback"

def extract_metadata(html, base_url):
    soup = BeautifulSoup(html, "lxml")
    title = ""
    desc = ""
    canonical = base_url

    # title
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    # meta description
    m = soup.find("meta", attrs={"name":"description"})
    if m and m.get("content"):
        desc = m["content"].strip()
    else:
        m2 = soup.find("meta", attrs={"property":"og:description"}) or \
             soup.find("meta", attrs={"name":"twitter:description"})
        if m2 and m2.get("content"):
            desc = m2["content"].strip()

    # fallback: first 2 meaningful paragraphs
    paras = [p.get_text(" ", strip=True) for p in soup.find_all("p") if p.get_text(strip=True)]
    if not desc and paras:
        desc = " ".join(paras[:2])[:1000]

    # large text snippet: join first ~12 paragraphs
    bigtext = " ".join(paras[:12])
    bigtext = re.sub(r"\s+", " ", bigtext).strip()

    linktag = soup.find("link", rel="canonical")
    if linktag and linktag.get("href"):
        canonical = urljoin(base_url, linktag["href"])

    return {
        "title": title or "",
        "description": desc or "",
        "canonical": canonical or base_url,
        "text_snippet": bigtext or ""
    }

def extract_links(html, base_url):
    soup = BeautifulSoup(html, "lxml")
    anchors = soup.find_all("a", href=True)
    urls = set()
    for a in anchors:
        href = a["href"].strip()
        if href.startswith("mailto:") or href.startswith("javascript:") or href.startswith("#"):
            continue
        full = urljoin(base_url, href)
        if not full.startswith("http"):
            continue
        parsed = urlparse(full)
        # normalize remove fragments and query for dedup purposes
        normalized = parsed._replace(fragment="").geturl()
        urls.add(normalized)
    return urls

def should_visit(url, visited, domain_allow=None):
    if url in visited:
        return False
    # restrict to same domain(s) if domain_allow provided
    if domain_allow:
        parsed = urlparse(url)
        if not any(parsed.netloc.endswith(d) for d in domain_allow):
            return False
    # only look at product-looking URLs to limit crawl
    if not looks_like_product_url(url):
        return False
    return True

def crawl(seeds, max_pages=600, domain_allow=None, output_csv="data/catalog_raw.csv", force_playwright=False):
    os.makedirs(os.path.dirname(output_csv) or ".", exist_ok=True)
    visited = set()
    to_visit = list(seeds)
    results = []

    pbar = tqdm(total=min(max_pages, 10000), desc="Pages processed")
    while to_visit and len(visited) < max_pages:
        url = to_visit.pop(0)
        if not should_visit(url, visited, domain_allow):
            continue
        try:
            fetch_mode = "requests"
            html, fetch_mode = fetch_page(url, force_playwright=force_playwright)
        except Exception:
            html = None
            fetch_mode = "error"
        print(f"Fetching ({fetch_mode}): {url}")
        time.sleep(DELAY)
        visited.add(url)
        pbar.update(1)
        if not html:
            continue
        meta = extract_metadata(html, url)
        results.append({
            "source_url": url,
            "canonical_url": meta["canonical"],
            "title": meta["title"],
            "description": meta["description"],
            "text_snippet": meta["text_snippet"],
            "fetched_with": fetch_mode
        })

        # find more links to product pages and add to queue
        links = extract_links(html, url)
        for l in links:
            if should_visit(l, visited, domain_allow) and l not in to_visit:
                to_visit.append(l)

    pbar.close()

    # deduplicate by canonical_url
    df = pd.DataFrame(results)
    if df.empty:
        print("No pages crawled. Check your seeds and network.")
        return
    df = df.drop_duplicates(subset=["canonical_url"])
    df.to_csv(output_csv, index=False, quoting=csv.QUOTE_MINIMAL)
    print(f"Saved {len(df)} unique pages to {output_csv}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Improved SHL product catalog crawler")
    parser.add_argument("--seeds", nargs="+", help="Seed URLs to start crawling from", required=True)
    parser.add_argument("--max", type=int, default=600, help="Max pages to crawl")
    parser.add_argument("--domain", nargs="+", help="Allowed domain(s) (e.g., shl.com)", default=None)
    parser.add_argument("--out", type=str, default="data/catalog_raw.csv", help="Output CSV file")
    parser.add_argument("--force-playwright", action="store_true", help="Force using Playwright for all pages")
    args = parser.parse_args()

    crawl(
        args.seeds,
        max_pages=args.max,
        domain_allow=args.domain,
        output_csv=args.out,
        force_playwright=args.force_playwright
    )
