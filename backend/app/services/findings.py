import json
from pathlib import Path

EXPIRY_WARNING_DAYS = 30


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _finding(
    code,
    severity,
    category,
    title,
    description,
    evidence_file,
    url=None,
    detail=None,
):
    return {
        "code": code,
        "severity": severity,
        "category": category,
        "title": title,
        "description": description,
        "url": url,
        "evidence_file": evidence_file,
        "detail": detail,
    }


def _is_browser_tooling_error(error: str) -> bool:
    text = (error or "").lower()
    return any(
        needle in text
        for needle in (
            "executable doesn't exist",
            "playwright install",
            "browserType.launch".lower(),
            "looks like playwright was just installed",
        )
    )


def _browser_render_failed(root: Path) -> bool:
    data = _load(root / "evidence" / "browser.json") or []
    return any(isinstance(ev, dict) and ev.get("error") for ev in data)


def _browser_findings(root: Path) -> list[dict]:
    out = []
    ef = "evidence/browser.json"
    data = _load(root / ef)
    if not data:
        return out

    for ev in data:
        url = ev.get("final_url") or ev.get("url")

        if ev.get("error"):
            err = str(ev["error"])
            if _is_browser_tooling_error(err):
                # Infra / local tooling — not a defect on the customer site.
                out.append(_finding(
                    "browser_tooling_unavailable", "info", "technical",
                    "Browser capture unavailable on this machine",
                    "Playwright could not launch locally, so screenshots and "
                    "rendered-DOM checks were skipped. Re-run the crawl after "
                    "browsers are installed.",
                    ef, url, {"error": err[:300]},
                ))
            else:
                out.append(_finding(
                    "page_render_failed", "high", "technical",
                    "Page could not be rendered in a browser",
                    "The browser failed to load this page, so no DOM or "
                    "screenshot evidence exists for it.",
                    ef, url, {"error": err[:500]},
                ))
            continue

        dom = ev.get("dom") or {}

        if not dom.get("title"):
            out.append(_finding(
                "missing_title", "high", "seo", "Page has no title",
                "The page has no <title> text.", ef, url,
            ))

        if not dom.get("meta_description"):
            out.append(_finding(
                "missing_meta_description", "medium", "seo",
                "Page has no meta description",
                "No meta description was found in the rendered page.",
                ef, url,
            ))

        # H1 presence/count is covered by axe-core's page-has-heading-one
        # rule (see _accessibility_findings); multiple H1s is still only
        # checked here since axe doesn't flag that.
        h1s = (dom.get("headings") or {}).get("h1", [])
        if len(h1s) > 1:
            out.append(_finding(
                "multiple_h1", "low", "seo", "Page has multiple H1 headings",
                f"{len(h1s)} H1 headings were found.", ef, url,
                {"h1": h1s},
            ))

        if not dom.get("canonical"):
            out.append(_finding(
                "missing_canonical", "low", "seo",
                "Page has no canonical URL",
                "No rel=canonical link was found.", ef, url,
            ))

        if not dom.get("lang"):
            out.append(_finding(
                "missing_lang", "low", "accessibility",
                "Page has no language attribute",
                "The <html> element has no lang attribute.", ef, url,
            ))

        if not dom.get("viewport_meta"):
            out.append(_finding(
                "missing_viewport_meta", "medium", "technical",
                "Page has no viewport meta tag",
                "Without a viewport meta tag, mobile rendering is "
                "usually poor.", ef, url,
            ))

        no_alt = [
            img.get("src")
            for img in dom.get("images", [])
            if img.get("alt") is None
        ]
        if no_alt:
            out.append(_finding(
                "images_missing_alt", "medium", "accessibility",
                "Images are missing alt attributes",
                f"{len(no_alt)} image(s) have no alt attribute.",
                ef, url, {"count": len(no_alt), "sample": no_alt[:5]},
            ))

        if ev.get("failed_requests"):
            out.append(_finding(
                "failed_requests", "low", "technical",
                "Some resources failed to load",
                f"{len(ev['failed_requests'])} request(s) failed "
                "while loading the page.",
                ef, url, {"sample": ev["failed_requests"][:5]},
            ))

    return out


def _performance_findings(root: Path) -> list[dict]:
    out = []
    ef = "evidence/performance.json"
    data = _load(root / ef)

    if not data:
        return out

    for ev in data:
        if ev.get("error"):
            continue

        performance = ev.get("performance") or {}
        url = ev.get("final_url") or ev.get("url")

        navigation = performance.get("navigation") or {}

        lcp = performance.get("lcp_ms")
        if lcp is not None:
            if lcp > 4000:
                out.append(_finding(
                    "slow_lcp",
                    "high",
                    "performance",
                    "Largest Contentful Paint is very slow",
                    f"LCP was {lcp} ms, which is above 4 seconds.",
                    ef,
                    url,
                    {"lcp_ms": lcp},
                ))
            elif lcp > 2500:
                out.append(_finding(
                    "slow_lcp",
                    "medium",
                    "performance",
                    "Largest Contentful Paint needs improvement",
                    f"LCP was {lcp} ms, which is above 2.5 seconds.",
                    ef,
                    url,
                    {"lcp_ms": lcp},
                ))

        ttfb = navigation.get("ttfb_ms")
        if ttfb is not None and ttfb > 800:
            out.append(_finding(
                "slow_ttfb",
                "medium",
                "performance",
                "Time to First Byte is slow",
                f"TTFB was {ttfb} ms, which is above 800 ms.",
                ef,
                url,
                {"ttfb_ms": ttfb},
            ))

        total_bytes = performance.get("total_transfer_bytes")
        if total_bytes is not None:
            if total_bytes > 5 * 1024 * 1024:
                out.append(_finding(
                    "very_large_page_weight",
                    "high",
                    "performance",
                    "Page has very large transfer weight",
                    f"The page transferred {total_bytes / 1024 / 1024:.2f} MB.",
                    ef,
                    url,
                    {"total_transfer_bytes": total_bytes},
                ))
            elif total_bytes > 3 * 1024 * 1024:
                out.append(_finding(
                    "large_page_weight",
                    "medium",
                    "performance",
                    "Page has large transfer weight",
                    f"The page transferred {total_bytes / 1024 / 1024:.2f} MB.",
                    ef,
                    url,
                    {"total_transfer_bytes": total_bytes},
                ))

        requests = performance.get("total_requests")
        if requests is not None:
            if requests > 200:
                out.append(_finding(
                    "excessive_requests",
                    "medium",
                    "performance",
                    "Page makes excessive network requests",
                    f"The page made {requests} resource requests.",
                    ef,
                    url,
                    {"total_requests": requests},
                ))
            elif requests > 100:
                out.append(_finding(
                    "excessive_requests",
                    "low",
                    "performance",
                    "Page makes many network requests",
                    f"The page made {requests} resource requests.",
                    ef,
                    url,
                    {"total_requests": requests},
                ))

        for image in performance.get("large_images", []):
            transfer_bytes = image.get("transfer_bytes")

            if transfer_bytes is not None and transfer_bytes > 500 * 1024:
                out.append(_finding(
                    "large_image",
                    "medium",
                    "performance",
                    "Image has a large transfer size",
                    (
                        f"The image transferred "
                        f"{transfer_bytes / 1024:.0f} KB."
                    ),
                    ef,
                    url,
                    {
                        "image_url": image.get("url"),
                        "transfer_bytes": transfer_bytes,
                        "natural_width": image.get("natural_width"),
                        "natural_height": image.get("natural_height"),
                    },
                ))

    return out


def _ssl_findings(root: Path) -> list[dict]:
    out = []
    ef = "ssl/certificate.json"
    ssl = _load(root / ef)
    if not ssl:
        return out

    domain = ssl.get("domain")

    if not ssl.get("https_enabled"):
        out.append(_finding(
            "https_unavailable", "high", "security",
            "HTTPS is not available",
            "A TLS connection could not be established.",
            ef, domain, {"error": ssl.get("error")},
        ))
        return out

    days = ssl.get("days_remaining")

    if not ssl.get("certificate_valid"):
        if days is not None and days < 0:
            out.append(_finding(
                "certificate_expired", "high", "security",
                "TLS certificate has expired",
                f"The certificate expired {abs(days)} day(s) ago.",
                ef, domain,
                {"valid_until": ssl.get("valid_until"),
                 "details_source": ssl.get("details_source"),
                 "error": ssl.get("error")},
            ))
        else:
            out.append(_finding(
                "certificate_invalid", "high", "security",
                "TLS certificate failed validation",
                ssl.get("error") or "Certificate verification failed.",
                ef, domain,
                {"details_source": ssl.get("details_source"),
                 "error": ssl.get("error")},
            ))
    elif days is not None and days <= EXPIRY_WARNING_DAYS:
        out.append(_finding(
            "certificate_expiring_soon", "medium", "security",
            "TLS certificate expires soon",
            f"The certificate expires in {days} day(s).",
            ef, domain, {"valid_until": ssl.get("valid_until")},
        ))

    redirect = ssl.get("http_to_https")
    if (
        redirect
        and redirect.get("error") is None
        and not redirect.get("redirects_to_https")
    ):
        out.append(_finding(
            "http_not_redirected_to_https", "medium", "security",
            "HTTP does not redirect to HTTPS",
            "Requesting the http:// version did not redirect to https://.",
            ef, domain,
            {"status_code": redirect.get("status_code"),
             "location": redirect.get("location")},
        ))

    return out


def _seo_findings(root: Path) -> list[dict]:
    out = []
    ef = "seo/analysis.json"
    seo = _load(root / ef)
    if not seo:
        return out

    origin = seo.get("origin")
    robots = seo.get("robots") or {}
    robots_fetch = robots.get("fetch") or {}

    if not robots.get("found") and robots_fetch.get("error") is None:
        out.append(_finding(
            "robots_txt_missing", "low", "seo", "No robots.txt found",
            "robots.txt did not return a valid text file.",
            ef, origin, {"status_code": robots_fetch.get("status_code")},
        ))

    if (robots.get("parsed") or {}).get("blocks_all_crawlers"):
        out.append(_finding(
            "robots_blocks_all_crawlers", "high", "seo",
            "robots.txt blocks all crawlers",
            "A 'User-agent: *' group disallows the whole site.",
            ef, origin,
        ))

    sitemap_fetch_ok = any(
        (s.get("fetch") or {}).get("error") is None
        for s in seo.get("sitemaps", [])
    )
    if not seo.get("sitemap_found") and sitemap_fetch_ok:
        out.append(_finding(
            "sitemap_missing", "medium", "seo", "No XML sitemap found",
            "No valid sitemap was found at the declared or default location.",
            ef, origin,
        ))

    if robots.get("found") and not seo.get("sitemap_declared_in_robots"):
        out.append(_finding(
            "sitemap_not_in_robots", "low", "seo",
            "robots.txt does not declare a sitemap",
            "robots.txt has no Sitemap: line.", ef, origin,
        ))

    return out


def _page_findings(root: Path) -> list[dict]:
    out = []
    ef = "evidence/pages.json"
    data = _load(root / ef)
    if not data:
        return out

    for page in data.get("pages", []):
        status = page.get("status_code")
        if status is not None and status >= 400:
            out.append(_finding(
                "page_http_error",
                "high" if status >= 500 else "medium",
                "technical",
                f"Page returned HTTP {status}",
                "The crawler received an error status for this page.",
                ef, page.get("url"), {"status_code": status},
            ))

    for err in data.get("errors", []):
        out.append(_finding(
            "page_fetch_failed", "medium", "technical",
            "Page could not be fetched",
            "The crawler could not retrieve this URL.",
            ef, err.get("url"), {"error": err.get("error")},
        ))

    return out


def _accessibility_findings(root: Path) -> list[dict]:
    out = []
    ef = "evidence/accessibility.json"
    data = _load(root / ef)
    if not data:
        return out

    for a11y in data:
        url = a11y.get("url")

        if a11y.get("error"):
            out.append(_finding(
                "accessibility_scan_failed", "low", "accessibility",
                "Accessibility scan could not run",
                "axe-core could not be run against this page.",
                ef, url, {"error": a11y["error"]},
            ))
            continue

        impact_to_severity = {
            "critical": "high", "serious": "high",
            "moderate": "medium", "minor": "low",
        }

        for v in a11y.get("violations", []):
            out.append(_finding(
                f"a11y_{v['id']}",
                impact_to_severity.get(v.get("impact"), "medium"),
                "accessibility",
                v["help"],
                v["description"],
                ef, url,
                {"impact": v.get("impact"),
                 "help_url": v.get("help_url"),
                 "node_count": v.get("node_count"),
                 "sample_targets": v.get("sample_targets")},
            ))

    return out


def _content_seo_findings(root: Path) -> list[dict]:
    out = []
    ef = "seo/content.json"
    data = _load(root / ef)
    if not data:
        return out

    # Static HTML for JS/SPA shells looks "empty" when Playwright failed.
    # Downgrade those signals so chat/brain don't treat them as top priorities.
    shell_only = _browser_render_failed(root)

    for page in data.get("pages") or []:
        url = page.get("url")
        if page.get("thin_content"):
            if shell_only:
                out.append(_finding(
                    "thin_content_unverified", "info", "seo",
                    "On-page copy looks thin in static HTML",
                    f"Only {page.get('word_count', 0)} words in the raw HTML. "
                    "Browser render failed, so client-rendered content was not checked.",
                    ef, url, {"word_count": page.get("word_count"), "shell_only": True},
                ))
            else:
                out.append(_finding(
                    "thin_content", "medium", "seo",
                    "Page has thin content",
                    f"Only {page.get('word_count', 0)} meaningful words were found.",
                    ef, url, {"word_count": page.get("word_count")},
                ))
        if page.get("missing_h1"):
            if shell_only:
                out.append(_finding(
                    "missing_h1_unverified", "info", "seo",
                    "H1 not visible in static HTML",
                    "No H1 in the raw HTML. Browser render failed, so a "
                    "client-rendered H1 may still exist.",
                    ef, url, {"shell_only": True},
                ))
            else:
                out.append(_finding(
                    "missing_h1", "medium", "seo",
                    "Page is missing an H1",
                    "No H1 heading was found; search engines use H1 as a primary topic signal.",
                    ef, url,
                ))
        if page.get("title_too_short"):
            out.append(_finding(
                "title_too_short", "low", "seo",
                "Title tag is too short",
                f"Title is {page.get('title_length')} characters (aim for ~50–60).",
                ef, url, {"title": page.get("title")},
            ))
        if page.get("title_too_long"):
            out.append(_finding(
                "title_too_long", "low", "seo",
                "Title tag is too long",
                f"Title is {page.get('title_length')} characters and may be truncated.",
                ef, url, {"title": page.get("title")},
            ))
        if page.get("meta_too_short") and page.get("meta_description"):
            out.append(_finding(
                "meta_description_too_short", "low", "seo",
                "Meta description is too short",
                f"Meta description is {page.get('meta_description_length')} characters.",
                ef, url,
            ))
        if page.get("meta_too_long"):
            out.append(_finding(
                "meta_description_too_long", "low", "seo",
                "Meta description is too long",
                f"Meta description is {page.get('meta_description_length')} characters.",
                ef, url,
            ))
        if page.get("keyword_stuffing_risk"):
            top = (page.get("top_keywords") or [{}])[0]
            out.append(_finding(
                "keyword_stuffing_risk", "medium", "seo",
                "Possible keyword stuffing",
                "One term dominates page copy at an unusually high density.",
                ef, url, {"top_keyword": top},
            ))

    return out


def _siteone_category(code: str | None, text: str | None) -> str:
    blob = f"{code or ''} {text or ''}".lower()
    if any(
        key in blob
        for key in (
            "seo",
            "title",
            "meta",
            "h1",
            "heading",
            "open-graph",
            "opengraph",
            "sitemap",
            "robots",
            "canonical",
            "description",
        )
    ):
        return "seo"
    if any(
        key in blob
        for key in ("ssl", "tls", "security", "cookie", "hsts", "csp", "x-frame")
    ):
        return "security"
    if any(
        key in blob
        for key in (
            "accessib",
            "a11y",
            "lang",
            "landmark",
            "alt ",
            "aria",
            "contrast",
        )
    ):
        return "accessibility"
    if any(
        key in blob
        for key in (
            "slow",
            "performance",
            "cache",
            "brotli",
            "webp",
            "avif",
            "compress",
            "response time",
        )
    ):
        return "performance"
    return "technical"


def _siteone_findings(root: Path) -> list[dict]:
    """Map SiteOne summary CRITICAL/WARNING items into findings."""
    out = []
    ef = "seo/siteone_summary.json"
    data = _load(root / ef)
    if not data or not data.get("ok"):
        return out

    severity_map = {
        "CRITICAL": "high",
        "WARNING": "medium",
        "NOTICE": "low",
        "INFO": "info",
    }
    origin = data.get("url")
    seen = set()
    for item in data.get("summary_items") or []:
        status = (item.get("status") or "").upper()
        if status not in severity_map:
            continue
        code = item.get("code") or "siteone_issue"
        text = item.get("text") or "SiteOne reported an issue"
        key = (code, text)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            _finding(
                f"siteone_{code}",
                severity_map[status],
                _siteone_category(code, text),
                text[:120],
                f"SiteOne Crawler: {text}",
                ef,
                origin,
                {"siteone_status": status, "siteone_code": code},
            )
        )

    scores = data.get("scores") or {}
    overall = scores.get("overall")
    if overall is not None and overall < 5:
        out.append(
            _finding(
                "siteone_low_overall_score",
                "high",
                "technical",
                f"SiteOne overall quality score is low ({overall}/10)",
                "The SiteOne audit overall score is below 5/10.",
                ef,
                origin,
                {"overall": overall, "by_category": scores.get("by_category")},
            )
        )
    return out


def analyze_crawl(root: Path) -> list[dict]:
    """Apply deterministic rules to a crawl's saved evidence."""
    from backend.app.services.conversion_path import conversion_findings
    from backend.app.services.finding_clusters import dedupe_findings
    from backend.app.services.upgrade_advisor import upgrade_findings

    raw = (
        _browser_findings(root)
        + _performance_findings(root)
        + _ssl_findings(root)
        + _seo_findings(root)
        + _content_seo_findings(root)
        + _siteone_findings(root)
        + _page_findings(root)
        + _accessibility_findings(root)
        + conversion_findings(root)
        + upgrade_findings(root)
    )
    return dedupe_findings(raw)
