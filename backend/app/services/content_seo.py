"""Content / word SEO analysis from crawled HTML pages."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlparse

from bs4 import BeautifulSoup

STOPWORDS = {
    "the", "and", "for", "that", "with", "this", "from", "your", "have",
    "are", "was", "were", "will", "can", "our", "you", "not", "but",
    "all", "any", "about", "into", "more", "when", "what", "which",
    "their", "there", "been", "than", "then", "them", "they", "also",
}


def _visible_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(text: str) -> list[str]:
    return [
        t for t in re.findall(r"[a-zA-Z][a-zA-Z0-9'-]{2,}", text.lower())
        if t not in STOPWORDS
    ]


def analyze_page_content(
    url: str,
    html: str,
    *,
    html_source: str = "static",
) -> dict:
    soup = BeautifulSoup(html or "", "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    meta = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    meta_description = (meta.get("content") or "").strip() if meta else ""

    h1s = [h.get_text(" ", strip=True) for h in soup.find_all("h1")]
    h2s = [h.get_text(" ", strip=True) for h in soup.find_all("h2")]
    text = _visible_text(soup)
    words = _tokens(text)
    word_count = len(words)
    counts = Counter(words)
    top_keywords = [
        {"term": term, "count": count}
        for term, count in counts.most_common(8)
    ]
    top_freq = (top_keywords[0]["count"] / word_count) if word_count else 0

    return {
        "url": url,
        "html_source": html_source,
        "title": title,
        "title_length": len(title),
        "meta_description": meta_description,
        "meta_description_length": len(meta_description),
        "h1_count": len(h1s),
        "h1": h1s[:5],
        "h2_count": len(h2s),
        "word_count": word_count,
        "top_keywords": top_keywords,
        "top_keyword_density": round(top_freq, 4),
        "thin_content": word_count < 150,
        "title_too_short": 0 < len(title) < 30,
        "title_too_long": len(title) > 65,
        "meta_too_short": 0 < len(meta_description) < 70,
        "meta_too_long": len(meta_description) > 160,
        "missing_h1": len(h1s) == 0,
        "keyword_stuffing_risk": top_freq >= 0.08 and word_count >= 80,
    }


def collect_content_seo(pages: list[dict], sample: int = 15) -> dict:
    analyzed = []
    # Prefer pages that already have rendered HTML when mixed.
    ordered = sorted(
        pages,
        key=lambda p: 0 if p.get("html_source") == "rendered" else 1,
    )
    for page in ordered[:sample]:
        analyzed.append(
            analyze_page_content(
                page.get("url") or "",
                page.get("html") or "",
                html_source=str(page.get("html_source") or "static"),
            )
        )

    thin = sum(1 for p in analyzed if p.get("thin_content"))
    missing_h1 = sum(1 for p in analyzed if p.get("missing_h1"))
    stuffing = sum(1 for p in analyzed if p.get("keyword_stuffing_risk"))
    rendered = sum(1 for p in analyzed if p.get("html_source") == "rendered")

    return {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "pages_analyzed": len(analyzed),
        "pages_from_rendered_html": rendered,
        "thin_content_pages": thin,
        "missing_h1_pages": missing_h1,
        "keyword_stuffing_pages": stuffing,
        "pages": analyzed,
    }
