from collections import deque
from urllib.parse import parse_qs, urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from backend.app.services.seo_collector import sitemap_page_urls


# Defaults — overridden by Settings when called from the crawl worker.
MAX_PAGES = 500
REQUEST_TIMEOUT = 15.0

_SKIP_SUFFIXES = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
    ".pdf", ".css", ".js", ".xml", ".zip", ".mp4", ".webm",
    ".woff", ".woff2", ".ttf", ".map", ".json",
)

# Admin / cart / feed noise — not useful site content for audits.
_SKIP_PATH_MARKERS = (
    "/wp-admin",
    "/wp-login",
    "/xmlrpc.php",
    "/wp-cron.php",
    "/cdn-cgi/",
    "/cart",
    "/checkout",
    "/my-account",
    "/account/login",
    "/feed",
    "/comments/feed",
)

_SKIP_QUERY_KEYS = {
    "replytocom",
    "add-to-cart",
    "remove_item",
    "share",
    "fbclid",
    "gclid",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
}


def normalize_url(url: str) -> str:
    """Drop fragments; strip tracking query params; normalize host/path."""
    parsed = urlparse(url.split("#", 1)[0])
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return url.split("#", 1)[0]
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")

    query = parsed.query
    if query:
        qs = parse_qs(query, keep_blank_values=True)
        kept = {
            k: v
            for k, v in qs.items()
            if k.lower() not in _SKIP_QUERY_KEYS
        }
        # Rebuild stable query string
        parts = []
        for key in sorted(kept):
            for val in kept[key]:
                if val == "":
                    parts.append(key)
                else:
                    parts.append(f"{key}={val}")
        query = "&".join(parts)

    return urlunparse(
        (parsed.scheme.lower(), parsed.netloc.lower(), path, "", query, "")
    )


def _same_host(url: str, host: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and parsed.netloc.lower() == host


def _skip_asset(url: str) -> bool:
    path = urlparse(url).path.lower()
    if path.endswith(_SKIP_SUFFIXES):
        return True
    if any(marker in path for marker in _SKIP_PATH_MARKERS):
        return True
    # WordPress REST / embeds are not page content.
    if "/wp-json/" in path or path.endswith("/embed"):
        return True
    return False


def _enqueue(queue: deque, seen: set[str], url: str, host: str) -> None:
    clean = normalize_url(url)
    if not _same_host(clean, host) or _skip_asset(clean) or clean in seen:
        return
    seen.add(clean)
    queue.append(clean)


def _count_same_host_anchors(html: str, base_url: str, host: str) -> int:
    soup = BeautifulSoup(html or "", "html.parser")
    count = 0
    for link in soup.find_all("a", href=True):
        absolute = urljoin(base_url, link["href"])
        if _same_host(normalize_url(absolute), host) and not _skip_asset(absolute):
            count += 1
    return count


def _rendered_hrefs(url: str) -> list[str]:
    """Links from a JS-rendered page. Used for SPAs / Next.js / heavy JS themes."""
    try:
        from playwright.sync_api import sync_playwright

        from backend.app.services.playwright_env import (
            ensure_playwright_browsers_path,
        )

        ensure_playwright_browsers_path()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page()
                page.goto(url, wait_until="networkidle", timeout=45000)
                hrefs = page.eval_on_selector_all(
                    "a[href]",
                    "els => els.map(a => a.getAttribute('href')).filter(Boolean)",
                )
                return list(hrefs)
            finally:
                browser.close()
    except Exception:
        return []


def crawl_website(
    start_url: str,
    *,
    max_pages: int | None = None,
    transport: httpx.BaseTransport | None = None,
    rendered_links=None,
) -> dict:
    """Crawl same-host HTML pages via sitemap + link graph (+ JS harvest).

    Works for WordPress (sitemaps + classic links), static HTML, and JS SPAs
    (Playwright harvest when the raw HTML has almost no anchors).
    """
    limit = max_pages if max_pages is not None else MAX_PAGES
    parsed_start = urlparse(start_url)
    host = parsed_start.netloc.lower()

    queue: deque[str] = deque()
    queued: set[str] = set()
    visited: set[str] = set()
    pages = []
    errors = []
    rendered_seeded = False

    headers = {
        "User-Agent": "WebsiteIntelligenceBot/0.1",
    }
    harvest = rendered_links if rendered_links is not None else _rendered_hrefs

    with httpx.Client(
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
        headers=headers,
        transport=transport,
    ) as client:
        _enqueue(queue, queued, start_url, host)
        for loc in sitemap_page_urls(start_url, client):
            _enqueue(queue, queued, loc, host)

        while queue and len(pages) < limit:
            url = queue.popleft()

            if url in visited:
                continue

            visited.add(url)

            try:
                response = client.get(url)
            except httpx.HTTPError as exc:
                errors.append({"url": url, "error": str(exc)})
                continue

            content_type = response.headers.get("content-type", "")

            if "text/html" not in content_type:
                continue

            final_url = normalize_url(str(response.url))
            if not _same_host(final_url, host):
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            title = soup.title.get_text(strip=True) if soup.title else None

            pages.append(
                {
                    "url": final_url,
                    "status_code": response.status_code,
                    "title": title,
                    "html": response.text,
                    "html_source": "static",
                }
            )

            for link in soup.find_all("a", href=True):
                absolute_url = urljoin(str(response.url), link["href"])
                _enqueue(queue, queued, absolute_url, host)

            # JS-heavy sites: if this page (or the whole queue) has almost no
            # same-host anchors, harvest the rendered DOM once from the home
            # (and again from the current page if still stuck).
            static_links = _count_same_host_anchors(
                response.text, str(response.url), host
            )
            need_render = (not rendered_seeded and static_links < 3) or (
                not queue and not rendered_seeded
            )
            if need_render:
                rendered_seeded = True
                seed_url = start_url if static_links < 3 else str(response.url)
                for href in harvest(seed_url):
                    _enqueue(queue, queued, urljoin(seed_url, href), host)
                # If home harvest still left us empty, try current page too.
                if not queue and seed_url != str(response.url):
                    for href in harvest(str(response.url)):
                        _enqueue(
                            queue, queued, urljoin(str(response.url), href), host
                        )

    if not pages and errors:
        raise RuntimeError(f"Could not fetch any pages: {errors[0]['error']}")

    return {
        "pages_discovered": len(queued),
        "pages_crawled": len(pages),
        "pages": pages,
        "errors": errors,
        "max_pages": limit,
        "truncated": len(pages) >= limit and bool(queue),
    }
