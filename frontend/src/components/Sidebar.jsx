import Icon from "./Icon";
import { BRAND } from "../lib/brand";

function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 40 40" aria-hidden="true">
      <rect width="40" height="40" rx="10" fill="currentColor" className="brand-mark-bg" />
      <path
        d="M12 28 L20 10 L28 28 M15.2 22.5 H24.8"
        fill="none"
        stroke="var(--brand-on-mark)"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="29.5" cy="11.5" r="2.2" fill="var(--accent)" />
    </svg>
  );
}

export default function Sidebar({ open, view, mode, counts, onNavigate, onClose, onOpenAdd }) {
  const items = [
    { id: "dashboard", label: "Workspace", icon: "home" },
    { id: "projects", label: "Projects", icon: "folder", count: counts.projects },
    { id: "sites", label: "Sites", icon: "globe", count: counts.websites },
    { id: "crawls", label: "Crawls", icon: "command" },
    { id: "reports", label: "Proposals", icon: "chart" },
    { id: "settings", label: "Settings", icon: "settings" },
  ];

  const isActive = (id) => {
    if (id === "reports") return view === "dashboard" && mode === "proposal";
    if (id === "dashboard") return view === "dashboard" && mode !== "proposal";
    return view === id;
  };

  return (
    <>
      <div className={`sidebar-scrim${open ? " open" : ""}`} onClick={onClose} aria-hidden="true" />
      <aside className={`sidebar${open ? " open" : ""}`}>
        <div className="brand">
          <div className="brand-icon" aria-hidden="true">
            <BrandMark />
          </div>
          <div>
            <h1>{BRAND.name}</h1>
            <p>{BRAND.tagline}</p>
          </div>
        </div>

        <nav className="side-nav" aria-label="Main">
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`side-link${isActive(item.id) ? " active" : ""}`}
              onClick={() => onNavigate(item.id)}
            >
              <Icon name={item.icon} size={18} />
              <span>{item.label}</span>
              {item.count ? <span className="side-count">{item.count}</span> : null}
            </button>
          ))}
        </nav>

        <div className="side-cta">
          <h4>New engagement</h4>
          <p>{BRAND.promise}</p>
          <button type="button" className="side-cta-btn" onClick={onOpenAdd}>
            <Icon name="plus" size={15} />
            <span>Add site</span>
          </button>
        </div>
      </aside>
    </>
  );
}
