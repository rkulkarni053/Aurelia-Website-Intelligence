from backend.app.services.finding_clusters import dedupe_findings, cluster_summary


def test_dedupe_clusters_a11y_contrast():
    findings = [
        {
            "code": "a11y_color-contrast",
            "severity": "high",
            "category": "accessibility",
            "title": "Elements must have sufficient color contrast",
            "description": "contrast fail",
            "url": f"https://example.com/p{i}",
            "detail": {"node_count": 2},
        }
        for i in range(5)
    ]
    out = dedupe_findings(findings)
    assert len(out) == 1
    assert out[0]["detail"]["clustered"] is True
    assert out[0]["detail"]["page_count"] == 5
    assert "hard to read" in out[0]["title"].lower() or "contrast" in out[0]["title"].lower()


def test_cluster_summary_orders_by_severity():
    findings = [
        {
            "code": "thin_content",
            "severity": "medium",
            "category": "seo",
            "title": "Thin",
            "description": "thin",
            "url": "https://a.com",
        },
        {
            "code": "missing_sitemap",
            "severity": "high",
            "category": "seo",
            "title": "No sitemap",
            "description": "missing",
            "url": "https://a.com",
        },
    ]
    cards = cluster_summary(findings, max_items=2)
    assert cards[0]["severity"] == "high"
