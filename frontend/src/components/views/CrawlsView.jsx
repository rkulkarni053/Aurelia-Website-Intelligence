import { formatDate } from "../../api";
import { crawlBadgeClass, crawlDuration } from "../../lib/crawl";
import Icon from "../Icon";

export default function CrawlsView({
  website,
  crawls,
  crawlId,
  history,
  busy,
  onSelect,
  onCrawl,
}) {
  const totals = Object.fromEntries(history.map((h) => [h.id, h]));

  return (
    <div className="mode-body">
      <div className="view-head">
        <div>
          <h2>Crawl history</h2>
          <p>{website ? `${crawls.length} crawl(s) for ${website.domain}` : "Select a website to see its crawls."}</p>
        </div>
        <button
          type="button"
          className="action-btn primary solo"
          disabled={!website || busy.crawl}
          onClick={onCrawl}
        >
          <Icon name="play" size={14} />
          <span>{busy.crawl ? "Crawling…" : "Run New Crawl"}</span>
        </button>
      </div>

      <section className="panel">
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Started</th>
                <th>Status</th>
                <th>Pages</th>
                <th>Duration</th>
                <th>Findings</th>
                <th>High</th>
                <th aria-label="Open" />
              </tr>
            </thead>
            <tbody>
              {!crawls.length ? (
                <tr>
                  <td colSpan={7} className="table-empty">
                    No crawls yet.
                  </td>
                </tr>
              ) : (
                crawls.map((c) => (
                  <tr
                    key={c.id}
                    className={String(c.id) === String(crawlId) ? "current" : ""}
                    onClick={() => onSelect(c.id)}
                  >
                    <td>{formatDate(c.started_at || c.created_at)}</td>
                    <td>
                      <span className={`badge ${crawlBadgeClass(c.status)}`}>{c.status}</span>
                    </td>
                    <td>
                      {c.pages_crawled || 0} / {c.pages_discovered || 0}
                    </td>
                    <td>{crawlDuration(c)}</td>
                    <td>{totals[c.id]?.total ?? "—"}</td>
                    <td className={totals[c.id]?.high ? "text-high" : ""}>{totals[c.id]?.high ?? "—"}</td>
                    <td className="row-more">
                      <Icon name="chevron" size={15} />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
