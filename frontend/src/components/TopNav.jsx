import { useEffect, useMemo, useRef, useState } from "react";
import { BRAND } from "../lib/brand";
import { shortDate } from "../lib/crawl";
import Icon from "./Icon";

function flatten(portfolio) {
  const out = [];
  const groups = [
    ...(portfolio?.companies || []),
    { id: "", name: "Unassigned", projects: portfolio?.unassigned_projects || [], virtual: true },
  ];
  for (const company of groups) {
    if (!company.virtual) {
      out.push({ kind: "company", label: company.name, sub: `${company.project_count || 0} projects`, target: { companyId: company.id } });
    }
    for (const project of company.projects || []) {
      out.push({
        kind: "project",
        label: project.name,
        sub: company.name,
        target: { companyId: company.id, projectId: project.id },
      });
      for (const site of project.websites || []) {
        out.push({
          kind: "site",
          label: site.domain || site.url,
          sub: `${project.name} · ${site.crawl_count || 0} crawls`,
          target: {
            companyId: company.id,
            projectId: project.id,
            websiteId: site.id,
            crawlId: site.crawls?.[0]?.id || "",
          },
        });
        for (const crawl of site.crawls || []) {
          const when = crawl.completed_at || crawl.created_at;
          out.push({
            kind: "crawl",
            label: `${site.domain || site.url} · ${shortDate(when, { withTime: true })}`,
            sub: `${crawl.status} · ${crawl.pages_crawled || 0}/${crawl.pages_discovered || 0} pages`,
            haystack: `${site.domain} ${crawl.status} ${new Date(when).toLocaleString()} ${shortDate(when)}`,
            searchOnly: true,
            target: {
              companyId: company.id,
              projectId: project.id,
              websiteId: site.id,
              crawlId: crawl.id,
            },
          });
        }
      }
    }
  }
  return out;
}

const KIND_ICON = { company: "building", project: "folder", site: "globe", crawl: "pulse" };

export default function TopNav({ portfolio, alerts, theme = "light", onToggleTheme, onSelect, onMenu }) {
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);
  const [active, setActive] = useState(0);
  const [bellOpen, setBellOpen] = useState(false);
  const inputRef = useRef(null);
  const entries = useMemo(() => flatten(portfolio), [portfolio]);

  const results = useMemo(() => {
    const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length) return entries.filter((e) => e.kind === "site").slice(0, 6);
    return entries
      .filter((e) => {
        const text = `${e.label} ${e.sub} ${e.haystack || ""}`.toLowerCase();
        return terms.every((t) => text.includes(t));
      })
      .slice(0, 10);
  }, [entries, query]);

  useEffect(() => setActive(0), [query]);

  const choose = (r) => {
    setQuery("");
    inputRef.current?.blur();
    onSelect(r.target);
  };

  const onInputKey = (e) => {
    if (!results.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => (i + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => (i - 1 + results.length) % results.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(results[Math.min(active, results.length - 1)]);
    }
  };

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      }
      if (e.key === "Escape") {
        inputRef.current?.blur();
        setBellOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const isMac = typeof navigator !== "undefined" && /Mac/i.test(navigator.platform);

  return (
    <div className="topnav">
      <button type="button" className="icon-circle menu-btn" onClick={onMenu} aria-label="Open menu">
        <Icon name="menu" size={18} />
      </button>

      <div className={`search${focused ? " focused" : ""}`}>
        <Icon name="search" size={16} />
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setTimeout(() => setFocused(false), 150)}
          onKeyDown={onInputKey}
          placeholder="Search website, projects, or crawls..."
          aria-label="Search"
        />
        <kbd>{isMac ? "⌘" : "Ctrl"} K</kbd>
        {focused ? (
          <div className="search-results" role="listbox">
            {!results.length ? (
              <div className="search-empty">No matches for “{query}”</div>
            ) : (
              results.map((r, idx) => (
                <button
                  key={`${r.kind}-${r.label}-${idx}`}
                  type="button"
                  role="option"
                  aria-selected={idx === active}
                  className={`search-item${idx === active ? " active" : ""}`}
                  onMouseDown={(e) => e.preventDefault()}
                  onMouseEnter={() => setActive(idx)}
                  onClick={() => choose(r)}
                >
                  <span className={`search-kind ${r.kind}`}>
                    <Icon name={KIND_ICON[r.kind]} size={14} />
                  </span>
                  <span className="search-text">
                    <strong>{r.label}</strong>
                    <span>{r.sub}</span>
                  </span>
                  <span className="search-tag">{r.kind}</span>
                </button>
              ))
            )}
          </div>
        ) : null}
      </div>

      <div className="topnav-right">
        <button
          type="button"
          className="icon-circle"
          aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          title={theme === "dark" ? "Light mode" : "Dark mode"}
          onClick={onToggleTheme}
        >
          <Icon name={theme === "dark" ? "sun" : "moon"} size={18} />
        </button>
        <div className="bell-wrap">
          <button
            type="button"
            className="icon-circle"
            aria-label="Notifications"
            onClick={() => setBellOpen((v) => !v)}
          >
            <Icon name="bell" size={18} />
            {alerts.length ? <span className="bell-dot" /> : null}
          </button>
          {bellOpen ? (
            <div className="bell-panel">
              <div className="bell-head">Notifications</div>
              {!alerts.length ? (
                <div className="search-empty">You're all caught up.</div>
              ) : (
                alerts.map((a, i) => (
                  <div className={`bell-item ${a.tone}`} key={i}>
                    <span className="bell-item-dot" />
                    <span>{a.text}</span>
                  </div>
                ))
              )}
            </div>
          ) : null}
        </div>
        <div className="avatar" title={BRAND.full}>
          {BRAND.short}
        </div>
      </div>
    </div>
  );
}
