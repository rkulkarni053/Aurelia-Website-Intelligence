import re
from datetime import datetime, timezone

import httpx

REQ_HEADERS = {"User-Agent": "WebsiteIntelligenceBot/0.1"}
SAMPLE_PAGES = 5

# Each signature can match on HTML (regex, case-insensitive) and/or
# response headers (header name -> regex matched against its value).
SIGNATURES = [
    {"name": "WordPress", "category": "cms", "html": [
        r"wp-content/", r"wp-includes/", r'generator["\']\s*content=["\']WordPress']},
    {"name": "WooCommerce", "category": "ecommerce", "html": [r"woocommerce"]},
    {"name": "Shopify", "category": "ecommerce",
     "html": [r"cdn\.shopify\.com", r"Shopify\.theme"],
     "headers": {"x-shopid": r".*", "x-shardid": r".*"}},
    {"name": "Wix", "category": "cms", "html": [r"static\.wixstatic\.com", r"\bwix\.com\b"]},
    {"name": "Squarespace", "category": "cms",
     "html": [r"squarespace\.com", r"static1\.squarespace\.com"]},
    {"name": "Webflow", "category": "cms", "html": [r"webflow\.com", r"data-wf-site"]},
    {"name": "Drupal", "category": "cms", "html": [
        r"Drupal\.settings", r"/sites/default/files", r'generator["\']\s*content=["\']Drupal']},
    {"name": "Joomla", "category": "cms", "html": [
        r"/media/jui/", r'generator["\']\s*content=["\']Joomla']},
    {"name": "Ghost", "category": "cms", "html": [
        r'generator["\']\s*content=["\']Ghost']},
    {"name": "Next.js", "category": "js_framework", "html": [r"__NEXT_DATA__", r"_next/static"]},
    {"name": "Nuxt.js", "category": "js_framework", "html": [r"__NUXT__", r"_nuxt/"]},
    {"name": "React", "category": "js_framework", "html": [
        r"react-dom", r"data-reactroot", r"data-reactid"]},
    {"name": "Vue.js", "category": "js_framework", "html": [r"v-cloak", r"__vue__"]},
    {"name": "Angular", "category": "js_framework", "html": [r"ng-version"]},
    {"name": "jQuery", "category": "js_library", "html": [
        r"jquery(?:-\d[\w.]*)?(?:\.min)?\.js"]},
    {"name": "Bootstrap", "category": "css_framework", "html": [
        r"bootstrap(?:\.min)?\.(?:css|js)"]},
    {"name": "Tailwind CSS", "category": "css_framework", "html": [
        r"tailwindcss", r"tailwind(?:\.min)?\.css"]},
    {"name": "Google Analytics", "category": "analytics", "html": [
        r"google-analytics\.com/analytics\.js",
        r"googletagmanager\.com/gtag/js"]},
    {"name": "Google Tag Manager", "category": "analytics", "html": [
        r"googletagmanager\.com/gtm\.js"]},
    {"name": "Meta Pixel", "category": "analytics", "html": [
        r"connect\.facebook\.net/[^\"']*fbevents\.js"]},
    {"name": "Hotjar", "category": "analytics", "html": [r"static\.hotjar\.com"]},
    {"name": "Segment", "category": "analytics", "html": [r"cdn\.segment\.com"]},
    {"name": "Cloudflare", "category": "cdn",
     "headers": {"server": r"cloudflare", "cf-ray": r".*"}},
    {"name": "Nginx", "category": "server", "headers": {"server": r"nginx"}},
    {"name": "Apache", "category": "server", "headers": {"server": r"apache"}},
    {"name": "Varnish", "category": "cdn", "headers": {"x-varnish": r".*"}},
    {"name": "Amazon CloudFront", "category": "cdn",
     "headers": {"x-amz-cf-id": r".*", "via": r"cloudfront"}},
    {"name": "Fastly", "category": "cdn", "headers": {"x-fastly-request-id": r".*"}},
    {"name": "PHP", "category": "language", "headers": {"x-powered-by": r"php"}},
    {"name": "ASP.NET", "category": "language",
     "headers": {"x-powered-by": r"asp\.net", "x-aspnet-version": r".*"}},
]


def _fetch_headers(site_url: str) -> dict:
    try:
        with httpx.Client(
            timeout=10.0, follow_redirects=True, headers=REQ_HEADERS
        ) as client:
            response = client.get(site_url)
            return {
                "status_code": response.status_code,
                "headers": {k.lower(): v for k, v in response.headers.items()},
                "error": None,
            }
    except Exception as exc:
        return {
            "status_code": None,
            "headers": {},
            "error": f"{type(exc).__name__}: {exc}",
        }


def detect_technologies(headers: dict, pages: list[dict]) -> list[dict]:
    """Match signatures against response headers and page HTML.

    pages: list of {"url": str, "html": str}, as produced by the crawler.
    """
    results = []

    for sig in SIGNATURES:
        evidence = []
        matched_pages = []

        for header_name, pattern in sig.get("headers", {}).items():
            value = headers.get(header_name)
            if value and re.search(pattern, value, re.I):
                evidence.append(
                    {"type": "header", "name": header_name, "value": value}
                )

        for page in pages:
            html = page.get("html") or ""
            for pattern in sig.get("html", []):
                match = re.search(pattern, html, re.I)
                if match:
                    matched_pages.append(page["url"])
                    if len(evidence) < 10:
                        evidence.append(
                            {"type": "html", "pattern": pattern,
                             "page": page["url"],
                             "snippet": match.group(0)[:120]}
                        )
                    break

        if evidence:
            results.append({
                "name": sig["name"],
                "category": sig["category"],
                "pages_matched": len(set(matched_pages)),
                "sample_pages": sorted(set(matched_pages))[:SAMPLE_PAGES],
                "evidence": evidence[:10],
            })

    results.sort(key=lambda r: (r["category"], r["name"]))
    return results


def collect_technologies(site_url: str, pages: list[dict]) -> dict:
    """Fetch homepage headers, then match signatures across the crawled pages.

    Never raises; a header-fetch failure just means header-based
    signatures are skipped, html-based ones still run.
    """
    header_result = _fetch_headers(site_url)

    detections = detect_technologies(header_result["headers"], pages)

    return {
        "site_url": site_url,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "header_fetch_error": header_result["error"],
        "response_headers": header_result["headers"],
        "pages_analyzed": len(pages),
        "detections": detections,
    }
