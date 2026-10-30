import { useEffect, useRef, useState } from "react";
import { formatDate } from "../../api";
import Icon from "../Icon";

const SWATCHES = [
  ["bg", "Background"],
  ["accent", "Accent"],
  ["accent_2", "Accent 2"],
  ["text", "Text"],
  ["muted", "Muted"],
];

const SUGGESTIONS = [
  "Build me a modern restaurant website",
  "Build me a cinematic agency homepage",
  "Make accent navy and gold",
  "What should we improve first?",
];

export default function DesignMode({
  designChat,
  mockups,
  demo,
  crawlId,
  busy,
  disabled,
  screenshots = [],
  onSend,
  onGenerate,
  onGenerateDemo,
}) {
  const [message, setMessage] = useState("");
  const [selectedShot, setSelectedShot] = useState("");
  const [cacheBust, setCacheBust] = useState(() => Date.now());
  const [showMockups, setShowMockups] = useState(false);
  const logRef = useRef(null);
  const messages = designChat?.messages || [];
  const brief = designChat?.design_brief;
  const palette = brief?.palette || {};
  const images = mockups?.images || [];
  const chatDisabled = disabled || busy.chat;
  const demoUrl = demo?.url_path
    ? `${demo.url_path}?t=${cacheBust}`
    : null;
  const previewBusy = busy.chat || busy.demo;

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [messages]);

  useEffect(() => setCacheBust(Date.now()), [demo?.generated_at, demo?.headline, demo?.url_path]);

  useEffect(() => {
    if (!selectedShot && screenshots[0]?.path) setSelectedShot(screenshots[0].path);
  }, [screenshots, selectedShot]);

  const send = (value, withVision = false) => {
    const text = (value || "").trim();
    if (chatDisabled) return;
    if (!text && !(withVision && selectedShot)) return;
    setMessage("");
    onSend(text, withVision ? selectedShot : null);
  };

  return (
    <div className="mode-body">
      <div className="design-layout base44-layout">
        <div className="stack base44-chat-col">
          <section className="panel chat-surface base44-chat">
            <div className="panel-head">
              <h3>
                <Icon name="send" size={18} className="panel-icon blue" />
                Build with chat
              </h3>
              <span className="panel-meta">
                {messages.length
                  ? `${messages.length} turns · edits update the live demo`
                  : "Describe changes — the preview updates"}
              </span>
            </div>

            <div className="design-chat-log" ref={logRef}>
              {!messages.length ? (
                <div className="chat-empty">
                  Tell the agent what to change on the live site — colors, headline, CTA,
                  services — or ask what to improve first.
                </div>
              ) : (
                messages.map((m, idx) => (
                  <div
                    key={`${m.role}-${idx}`}
                    className={`chat-bubble ${m.role}${m.pending ? " pending" : ""}`}
                  >
                    {m.content}
                  </div>
                ))
              )}
            </div>

            <div className="suggestion-row">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  className="suggestion"
                  disabled={chatDisabled}
                  onClick={() => send(s)}
                >
                  {s}
                </button>
              ))}
            </div>

            {screenshots.length ? (
              <div className="vision-picker">
                <label className="field-label">
                  Screenshot for vision review
                  <select
                    value={selectedShot}
                    onChange={(e) => setSelectedShot(e.target.value)}
                    disabled={chatDisabled}
                  >
                    {screenshots.map((s) => (
                      <option key={s.path} value={s.path}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                </label>
                {selectedShot ? (
                  <button
                    type="button"
                    className="button small"
                    disabled={chatDisabled}
                    onClick={() =>
                      send(message || "Review this screenshot and suggest improvements", true)
                    }
                  >
                    <Icon name="eye" size={13} />
                    Review with vision
                  </button>
                ) : null}
              </div>
            ) : null}

            <form
              className="design-chat-form"
              onSubmit={(e) => {
                e.preventDefault();
                send(message);
              }}
            >
              <input
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder='e.g. "Build me a modern restaurant website"'
                disabled={chatDisabled}
                autoComplete="off"
              />
              <button
                type="submit"
                className="button primary"
                disabled={chatDisabled || !message.trim()}
              >
                <Icon name="send" size={14} />
                <span>{busy.chat ? "Updating…" : "Send"}</span>
              </button>
            </form>
          </section>

          <section className="panel brief-card base44-brief">
            <div className="panel-head">
              <h3>
                <Icon name="brush" size={18} className="panel-icon blue" />
                Brief
              </h3>
              <span className="panel-meta">
                {brief?.updated_at ? formatDate(brief.updated_at) : "Draft"}
              </span>
            </div>
            <div className="swatch-row compact">
              {SWATCHES.filter(([key]) => palette[key]).map(([key, label]) => (
                <div className="swatch" key={key} title={`${label} ${palette[key]}`}>
                  <span className="swatch-chip" style={{ background: palette[key] }} />
                  <code>{palette[key]}</code>
                </div>
              ))}
              {!Object.keys(palette).length ? (
                <span className="card-subtitle">Palette appears after the first design edit.</span>
              ) : null}
            </div>
            {(brief?.headline || brief?.cta) && (
              <p className="brief-notes">
                {[brief?.headline, brief?.cta].filter(Boolean).join(" · ")}
              </p>
            )}
          </section>
        </div>

        <div className="stack base44-preview-col">
          <section className="panel base44-preview">
            <div className="panel-head">
              <h3>
                <Icon name="external" size={20} className="panel-icon blue" />
                Live demo
              </h3>
              <div className="panel-actions">
                <span className="panel-meta">
                  {previewBusy
                    ? "Updating preview…"
                    : demo
                      ? "Chat edits refresh this site"
                      : "Build once, then iterate in chat"}
                </span>
                <button
                  type="button"
                  className="button small"
                  onClick={onGenerateDemo}
                  disabled={disabled || busy.demo}
                >
                  <Icon name={demo ? "refresh" : "brush"} size={13} />
                  {busy.demo ? "Building…" : demo ? "Rebuild" : "Build demo"}
                </button>
                {demoUrl ? (
                  <a
                    className="button small"
                    href={demoUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <Icon name="external" size={13} />
                    Open
                  </a>
                ) : null}
              </div>
            </div>

            {busy.demo && !demoUrl ? (
              <div className="empty-inline">
                <div className="skeleton block tall" />
                <p>Building clickable demo…</p>
              </div>
            ) : !demoUrl ? (
              <div className="empty-inline">
                <Icon name="brush" size={28} />
                <p>
                  Build the demo once, then chat to iterate — colors, headline, CTA, and
                  copy update the live preview instantly.
                </p>
                <button
                  type="button"
                  className="button primary"
                  onClick={onGenerateDemo}
                  disabled={disabled || busy.demo}
                >
                  Build live demo
                </button>
              </div>
            ) : (
              <div className={`demo-frame-wrap${previewBusy ? " updating" : ""}`}>
                {previewBusy ? (
                  <div className="demo-updating-badge">Updating preview…</div>
                ) : null}
                <iframe title="Website demo preview" className="demo-frame tall" src={demoUrl} />
              </div>
            )}
          </section>

          <section className="panel base44-mockups">
            <div className="panel-head">
              <h3>
                <Icon name="image" size={18} className="panel-icon blue" />
                Concept boards
              </h3>
              <div className="panel-actions">
                <span className="panel-meta">Instant layout comps · not AI photos</span>
                <button
                  type="button"
                  className="button small"
                  onClick={() => setShowMockups((v) => !v)}
                >
                  {showMockups ? "Hide" : "Show"}
                </button>
                <button
                  type="button"
                  className="button small"
                  onClick={onGenerate}
                  disabled={disabled || busy.mockups}
                >
                  <Icon name={images.length ? "refresh" : "image"} size={13} />
                  {busy.mockups ? "Building…" : images.length ? "Refresh boards" : "Build boards"}
                </button>
              </div>
            </div>
            {showMockups ? (
              busy.mockups ? (
                <div className="mockup-grid">
                  {[0, 1].map((i) => (
                    <div key={i} className="mockup-card">
                      <div className="skeleton block tall" />
                    </div>
                  ))}
                </div>
              ) : !images.length ? (
                <div className="empty-inline">
                  <p>
                    Fast layout comps from the brief (desktop / mobile / board). For a real
                    looking site, use the live demo above.
                  </p>
                </div>
              ) : (
                <div className="mockup-grid">
                  {images.map((img) => (
                    <figure className="mockup-card" key={img.path}>
                      <a
                        href={`/data/websites/${mockups.domain}/crawls/${crawlId}/${img.path}`}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        <img
                          src={`/data/websites/${mockups.domain}/crawls/${crawlId}/${img.path}?t=${cacheBust}`}
                          alt={img.label || img.kind}
                          loading="lazy"
                        />
                      </a>
                      <figcaption className="caption">
                        <span>{img.label || img.kind}</span>
                      </figcaption>
                    </figure>
                  ))}
                </div>
              )
            ) : (
              <p className="brief-notes">
                Optional layout comps. Prefer the live HTML demo — clients click real pages.
              </p>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
