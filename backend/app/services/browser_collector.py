from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

from backend.app.services.playwright_env import ensure_playwright_browsers_path

VIEWPORTS = {
    "desktop": {"width": 1440, "height": 900},
    "mobile": {"width": 390, "height": 844},
}

PERFORMANCE_JS = """
async () => {
  const navigation = performance.getEntriesByType("navigation")[0];

  const resources = performance.getEntriesByType("resource").map((r) => ({
    name: r.name,
    initiator_type: r.initiatorType,
    duration_ms: Math.round(r.duration),
    start_time_ms: Math.round(r.startTime),
    response_start_ms: Math.round(r.responseStart),
    transfer_size: r.transferSize || 0,
    encoded_body_size: r.encodedBodySize || 0,
    decoded_body_size: r.decodedBodySize || 0,
  }));

  const by_type = {};
  let total_transfer_bytes = 0;
  let total_encoded_bytes = 0;
  let total_decoded_bytes = 0;

  for (const r of resources) {
    const type = r.initiator_type || "other";

    if (!by_type[type]) {
      by_type[type] = {
        requests: 0,
        transfer_bytes: 0,
        encoded_body_bytes: 0,
        decoded_body_bytes: 0,
      };
    }

    by_type[type].requests += 1;
    by_type[type].transfer_bytes += r.transfer_size;
    by_type[type].encoded_body_bytes += r.encoded_body_size;
    by_type[type].decoded_body_bytes += r.decoded_body_size;

    total_transfer_bytes += r.transfer_size;
    total_encoded_bytes += r.encoded_body_size;
    total_decoded_bytes += r.decoded_body_size;
  }

  const paintEntries = performance.getEntriesByType("paint");
  const fcp = paintEntries.find(
    (p) => p.name === "first-contentful-paint"
  );

  let lcp = null;

  try {
    const lcpEntries = await new Promise((resolve) => {
      let entries = [];

      const observer = new PerformanceObserver((list) => {
        entries = list.getEntries();
      });

      observer.observe({
        type: "largest-contentful-paint",
        buffered: true,
      });

      setTimeout(() => {
        observer.disconnect();
        resolve(entries);
      }, 0);
    });

    if (lcpEntries.length) {
      lcp = lcpEntries[lcpEntries.length - 1];
    }
  } catch (_) {
    // LCP unavailable in this browser/context.
  }

  const large_images = Array.from(document.images)
    .map((img) => ({
      url: img.currentSrc || img.src,
      natural_width: img.naturalWidth,
      natural_height: img.naturalHeight,
    }))
    .filter((img) => img.natural_width && img.natural_height);

  return {
    navigation: navigation
      ? {
          dns_ms: Math.max(
            0,
            Math.round(navigation.domainLookupEnd - navigation.domainLookupStart)
          ),
          connect_ms: Math.max(
            0,
            Math.round(navigation.connectEnd - navigation.connectStart)
          ),
          tls_ms: navigation.secureConnectionStart
            ? Math.max(
                0,
                Math.round(
                  navigation.connectEnd - navigation.secureConnectionStart
                )
              )
            : 0,
          request_ms: Math.max(
            0,
            Math.round(navigation.responseStart - navigation.requestStart)
          ),
          ttfb_ms: Math.max(
            0,
            Math.round(navigation.responseStart - navigation.requestStart)
          ),
          response_ms: Math.max(
            0,
            Math.round(navigation.responseEnd - navigation.responseStart)
          ),
          dom_content_loaded_ms: Math.round(
            navigation.domContentLoadedEventEnd
          ),
          load_event_ms: Math.round(navigation.loadEventEnd),
          duration_ms: Math.round(navigation.duration),
          transfer_size: navigation.transferSize || 0,
          encoded_body_size: navigation.encodedBodySize || 0,
          decoded_body_size: navigation.decodedBodySize || 0,
        }
      : null,

    fcp_ms: fcp ? Math.round(fcp.startTime) : null,
    lcp_ms: lcp ? Math.round(lcp.startTime) : null,

    total_requests: resources.length,
    total_transfer_bytes:
      (navigation ? navigation.transferSize || 0 : 0) +
      total_transfer_bytes,
    total_encoded_body_bytes:
      (navigation ? navigation.encodedBodySize || 0 : 0) +
      total_encoded_bytes,
    total_decoded_body_bytes: total_decoded_bytes,

    resource_summary: by_type,

    large_images,
  };
}
"""


EXTRACT_JS = """
() => {
  const meta = (sel, attr = "content") => {
    const el = document.querySelector(sel);
    return el ? el.getAttribute(attr) : null;
  };

  const headings = {};
  for (let i = 1; i <= 6; i++) {
    headings["h" + i] = Array.from(document.querySelectorAll("h" + i))
      .map((h) => h.textContent.trim())
      .filter(Boolean);
  }

  const images = Array.from(document.images).map((img) => ({
    src: img.currentSrc || img.src,
    alt: img.getAttribute("alt"),
    width: img.naturalWidth,
    height: img.naturalHeight,
  }));

  const links = Array.from(document.querySelectorAll("a[href]")).map((a) => ({
    href: a.href,
    text: a.textContent.trim().slice(0, 200),
    rel: a.getAttribute("rel"),
  }));

  const og = {};
  document.querySelectorAll('meta[property^="og:"]').forEach((m) => {
    og[m.getAttribute("property")] = m.getAttribute("content");
  });

  return {
    title: document.title || null,
    meta_description: meta('meta[name="description"]'),
    canonical: meta('link[rel="canonical"]', "href"),
    robots_meta: meta('meta[name="robots"]'),
    lang: document.documentElement.getAttribute("lang"),
    viewport_meta: meta('meta[name="viewport"]'),
    open_graph: og,
    headings: headings,
    images: images,
    links: links,
    forms: document.forms.length,
    buttons: document.querySelectorAll("button, [role=button]").length,
    json_ld_blocks: document.querySelectorAll(
      'script[type="application/ld+json"]'
    ).length,
  };
}
"""


def collect_browser_evidence(url: str, out_dir: Path, name: str) -> dict:
    """Render a page, save screenshots + DOM, return structured evidence.

    Never raises; errors are recorded in the result.
    out_dir is the crawl root; files go under screenshots/ and html/.
    """
    evidence = {
        "url": url,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "final_url": None,
        "status_code": None,
        "load_time_ms": None,
        "performance": None,
        "screenshots": {},
        "rendered_html_file": None,
        "dom": None,
        "console_errors": [],
        "failed_requests": [],
        "error": None,
    }

    try:
        ensure_playwright_browsers_path()
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                for label, viewport in VIEWPORTS.items():
                    context = browser.new_context(
                        viewport=viewport,
                        is_mobile=(label == "mobile"),
                        user_agent="WebsiteIntelligenceBot/0.1 (Playwright)",
                    )
                    page = context.new_page()

                    if label == "desktop":
                        page.on(
                            "console",
                            lambda m: evidence["console_errors"].append(m.text)
                            if m.type == "error"
                            else None,
                        )
                        page.on(
                            "requestfailed",
                            lambda r: evidence["failed_requests"].append(
                                {"url": r.url, "failure": r.failure}
                            ),
                        )

                    started = datetime.now(timezone.utc)
                    response = page.goto(
                        url, wait_until="networkidle", timeout=30000
                    )
                    elapsed = datetime.now(timezone.utc) - started

                    shot = f"screenshots/{name}-{label}.png"
                    page.screenshot(path=str(out_dir / shot), full_page=True)
                    evidence["screenshots"][label] = shot

                    if label == "desktop":
                        evidence["final_url"] = page.url
                        evidence["status_code"] = (
                            response.status if response else None
                        )
                        evidence["load_time_ms"] = int(
                            elapsed.total_seconds() * 1000
                        )

                        try:
                            evidence["performance"] = page.evaluate(
                                PERFORMANCE_JS
                            )
                        except Exception as perf_exc:
                            evidence["performance"] = {
                                "error": (
                                    f"{type(perf_exc).__name__}: "
                                    f"{perf_exc}"
                                )
                            }

                        rendered = f"html/{name}-rendered.html"
                        (out_dir / rendered).write_text(
                            page.content(), encoding="utf-8"
                        )
                        evidence["rendered_html_file"] = rendered
                        evidence["dom"] = page.evaluate(EXTRACT_JS)

                    context.close()
            finally:
                browser.close()

    except Exception as exc:
        evidence["error"] = f"{type(exc).__name__}: {exc}"

    return evidence
