import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx

HEADERS = {"User-Agent": "WebsiteIntelligenceBot/0.1"}
MAX_BYTES = 5_000_000
MAX_CHILD_SITEMAPS = 40
SAMPLE_URLS = 10

# Common WordPress / CMS sitemap entry points.
_DEFAULT_SITEMAP_PATHS = (
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/wp-sitemap.xml",
    "/sitemap-index.xml",
)


def _fetch(client: httpx.Client, url: str) -> dict:
    result = {
        "url": url,
        "final_url": None,
        "status_code": None,
        "content_type": None,
        "looks_like_html": False,
        "text": None,
        "error": None,
    }
    try:
        response = client.get(url)
        content_type = response.headers.get("content-type", "")
        text = response.text[:MAX_BYTES]
        result.update(
            final_url=str(response.url),
            status_code=response.status_code,
            content_type=content_type or None,
            looks_like_html=(
                "html" in content_type.lower()
                or text.lstrip()[:15].lower().startswith(("<!doctype", "<html"))
            ),
            text=text,
        )
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def _parse_robots(text: str) -> dict:
    sitemaps = []
    groups = []
    current = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "sitemap" and value:
            sitemaps.append(value)
        elif key == "user-agent":
            if current is None or current["rules"]:
                current = {"user_agents": [], "rules": []}
                groups.append(current)
            current["user_agents"].append(value)
        elif key in ("allow", "disallow", "crawl-delay") and current:
            current["rules"].append({"directive": key, "value": value})

    blocks_everything = any(
        "*" in g["user_agents"]
        and any(r["directive"] == "disallow" and r["value"] == "/" for r in g["rules"])
        for g in groups
    )
    return {
        "sitemaps": sitemaps,
        "groups": groups,
        "blocks_all_crawlers": blocks_everything,
    }


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_sitemap(text: str) -> dict:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return {"valid_xml": False, "error": str(exc), "type": None,
                "url_count": 0, "sample_urls": [], "urls": [],
                "child_sitemaps": []}

    locs = [
        (el.text or "").strip()
        for el in root.iter()
        if _local(el.tag) == "loc" and (el.text or "").strip()
    ]
    kind = _local(root.tag)
    if kind == "sitemapindex":
        return {"valid_xml": True, "error": None, "type": "index",
                "url_count": 0, "sample_urls": [], "urls": [],
                "child_sitemaps": locs}
    return {"valid_xml": True, "error": None, "type": kind,
            "url_count": len(locs), "sample_urls": locs[:SAMPLE_URLS],
            "urls": locs, "child_sitemaps": []}


MAX_SITEMAP_URLS = 2000


def sitemap_page_urls(site_url: str, client: httpx.Client) -> list[str]:
    """Same-host page URLs declared in robots.txt or sitemap.xml.

    Returns every <loc> from urlsets, following a sitemap index. Never raises.
    Covers classic /sitemap.xml plus WordPress wp-sitemap.xml indexes.
    """
    parsed = urlparse(site_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    host = parsed.netloc.lower()

    try:
        robots = _fetch(client, urljoin(origin, "/robots.txt"))
        declared = []
        if (
            robots["status_code"] == 200
            and not robots["looks_like_html"]
            and robots["text"]
        ):
            declared = _parse_robots(robots["text"])["sitemaps"]

        queue = list(declared)
        for path in _DEFAULT_SITEMAP_PATHS:
            candidate = urljoin(origin, path)
            if candidate not in queue:
                queue.append(candidate)

        seen: set[str] = set()
        urls: list[str] = []
        fetched = 0
        while queue and fetched < 1 + MAX_CHILD_SITEMAPS and len(urls) < MAX_SITEMAP_URLS:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            fetched += 1

            fetch = _fetch(client, url)
            if (
                fetch["status_code"] != 200
                or not fetch["text"]
                or fetch["looks_like_html"]
            ):
                continue
            sitemap = _parse_sitemap(fetch["text"])
            if not sitemap["valid_xml"]:
                continue
            for child in sitemap["child_sitemaps"]:
                if child not in seen:
                    queue.append(child)
            for loc in sitemap["urls"]:
                if urlparse(loc).netloc.lower() != host:
                    continue
                urls.append(loc)
                if len(urls) >= MAX_SITEMAP_URLS:
                    break
        # De-dupe while preserving order
        out: list[str] = []
        seen_loc: set[str] = set()
        for loc in urls:
            if loc in seen_loc:
                continue
            seen_loc.add(loc)
            out.append(loc)
        return out
    except Exception:
        return []


def collect_seo(site_url: str) -> dict:
    """Collect robots.txt + sitemap evidence. Never raises."""
    parsed = urlparse(site_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    analysis = {
        "origin": origin,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "robots": {"found": False, "fetch": None, "parsed": None},
        "sitemaps": [],
        "sitemap_found": False,
        "total_sitemap_urls": 0,
        "raw_robots": None,
        "raw_sitemap": None,
    }

    with httpx.Client(
        timeout=10.0, follow_redirects=True, headers=HEADERS
    ) as client:
        robots = _fetch(client, urljoin(origin, "/robots.txt"))
        robots_ok = (
            robots["status_code"] == 200
            and not robots["looks_like_html"]
            and robots["text"] is not None
        )
        analysis["robots"]["found"] = robots_ok
        analysis["robots"]["fetch"] = {
            k: v for k, v in robots.items() if k != "text"
        }

        declared = []
        if robots_ok:
            analysis["raw_robots"] = robots["text"]
            parsed_robots = _parse_robots(robots["text"])
            analysis["robots"]["parsed"] = parsed_robots
            declared = parsed_robots["sitemaps"]

        candidates = declared or [urljoin(origin, "/sitemap.xml")]
        analysis["sitemap_declared_in_robots"] = bool(declared)

        queue = list(candidates)
        seen = set()
        fetched = 0
        while queue and fetched < 1 + MAX_CHILD_SITEMAPS:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            fetched += 1

            fetch = _fetch(client, url)
            entry = {
                "fetch": {k: v for k, v in fetch.items() if k != "text"},
                "found": False,
                "parsed": None,
            }
            if (
                fetch["status_code"] == 200
                and fetch["text"]
                and not fetch["looks_like_html"]
            ):
                sitemap = _parse_sitemap(fetch["text"])
                entry["found"] = sitemap["valid_xml"]
                entry["parsed"] = sitemap
                if sitemap["valid_xml"]:
                    analysis["sitemap_found"] = True
                    analysis["total_sitemap_urls"] += sitemap["url_count"]
                    if analysis["raw_sitemap"] is None:
                        analysis["raw_sitemap"] = fetch["text"]
                    queue.extend(sitemap["child_sitemaps"])
            analysis["sitemaps"].append(entry)

    return analysis
