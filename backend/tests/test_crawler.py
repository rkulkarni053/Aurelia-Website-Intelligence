"""Crawler follows sitemap URLs when the raw HTML has no anchors."""

import httpx

from backend.app.services.crawler import crawl_website


SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/</loc></url>
  <url><loc>https://example.com/about</loc></url>
  <url><loc>https://example.com/services/live</loc></url>
</urlset>
"""

PAGES = {
    "/": "<html><head><title>Home</title></head><body><div id='app'></div></body></html>",
    "/about": "<html><head><title>About</title></head><body><a href='/contact'>Contact</a></body></html>",
    "/services/live": "<html><head><title>Live</title></head><body>Live</body></html>",
    "/contact": "<html><head><title>Contact</title></head><body>Contact</body></html>",
}


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/robots.txt":
        return httpx.Response(
            200,
            text="User-agent: *\nSitemap: https://example.com/sitemap.xml\n",
            headers={"content-type": "text/plain"},
        )
    if path == "/sitemap.xml":
        return httpx.Response(
            200,
            text=SITEMAP,
            headers={"content-type": "application/xml"},
        )
    html = PAGES.get(path)
    if html is None:
        return httpx.Response(404, text="missing", headers={"content-type": "text/plain"})
    return httpx.Response(
        200,
        text=html,
        headers={"content-type": "text/html; charset=utf-8"},
    )


def test_crawl_uses_sitemap_when_homepage_has_no_links():
    result = crawl_website(
        "https://example.com/",
        transport=httpx.MockTransport(_handler),
        rendered_links=lambda url: [],
    )
    urls = [page["url"] for page in result["pages"]]
    assert urls == [
        "https://example.com/",
        "https://example.com/about",
        "https://example.com/services/live",
        "https://example.com/contact",
    ]
    assert result["pages_crawled"] == 4
    assert result["errors"] == []


def test_rendered_links_fill_in_when_sitemap_is_missing():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in ("/robots.txt", "/sitemap.xml"):
            return httpx.Response(404, text="nope", headers={"content-type": "text/plain"})
        if request.url.path == "/":
            return httpx.Response(
                200,
                text=PAGES["/"],
                headers={"content-type": "text/html"},
            )
        if request.url.path == "/portfolio":
            return httpx.Response(
                200,
                text="<html><head><title>Portfolio</title></head><body>Work</body></html>",
                headers={"content-type": "text/html"},
            )
        return httpx.Response(404, text="missing", headers={"content-type": "text/plain"})

    result = crawl_website(
        "https://example.com/",
        transport=httpx.MockTransport(handler),
        rendered_links=lambda url: ["/portfolio"],
    )
    assert [page["url"] for page in result["pages"]] == [
        "https://example.com/",
        "https://example.com/portfolio",
    ]
