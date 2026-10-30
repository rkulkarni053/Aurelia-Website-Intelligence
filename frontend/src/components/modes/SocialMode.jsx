import { useEffect, useRef, useState } from "react";
import { formatDate } from "../../api";
import Icon from "../Icon";

const SUGGESTIONS = [
  "Add reel: The moment everything goes quiet",
  "CTA: Enquire about your date",
  "softer music",
  "more upbeat soundtrack",
  "focus on LinkedIn",
  "add hashtag #YourBrand",
];

export default function SocialMode({
  socialChat,
  busy,
  disabled,
  onSend,
}) {
  const [message, setMessage] = useState("");
  const logRef = useRef(null);
  const messages = socialChat?.messages || [];
  const social = socialChat?.social_content || {};
  const chatDisabled = disabled || busy.socialChat;
  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
  const chips = lastAssistant?.suggestions?.length
    ? lastAssistant.suggestions
    : SUGGESTIONS;

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [messages]);

  const send = (value) => {
    const text = (value || "").trim();
    if (chatDisabled || !text) return;
    setMessage("");
    onSend(text);
  };

  const ideas = social.post_ideas || [];
  const tracks = social.soundtracks || [];
  const hashtags = social.hashtags || [];
  const pillars = social.content_pillars || [];
  const weekPlan = social.week_plan || [];
  const platforms = social.platforms || [];

  return (
    <div className="mode-body">
      <div className="design-layout social-layout">
        <div className="stack base44-chat-col">
          <section className="panel chat-surface base44-chat">
            <div className="panel-head">
              <h3>
                <Icon name="share" size={18} className="panel-icon blue" />
                Social with Brain
              </h3>
              <span className="panel-meta">
                {messages.length
                  ? `${messages.length} turns · pack updates live`
                  : "Refine posts, hashtags, and soundtrack ideas"}
              </span>
            </div>

            <div className="design-chat-log" ref={logRef}>
              {!messages.length ? (
                <div className="chat-empty">
                  Ask Brain to improve the social plan — new Reels, CTAs, softer music,
                  LinkedIn angles, or hashtags. The pack on the right updates as you chat.
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
              {chips.slice(0, 6).map((s) => (
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
                placeholder='e.g. "Add reel: First look at golden hour"'
                disabled={chatDisabled}
                autoComplete="off"
              />
              <button
                type="submit"
                className="button primary"
                disabled={chatDisabled || !message.trim()}
              >
                <Icon name="send" size={14} />
                <span>{busy.socialChat ? "Updating…" : "Send"}</span>
              </button>
            </form>
          </section>
        </div>

        <div className="stack social-pack-col">
          <section className="panel">
            <div className="panel-head">
              <h3>
                <Icon name="trend" size={18} className="panel-icon blue" />
                {social.brand || "Social pack"}
              </h3>
              <span className="panel-meta">
                {social.updated_at || social.generated_at
                  ? formatDate(social.updated_at || social.generated_at)
                  : social.source || "Draft"}
              </span>
            </div>

            {platforms.length ? (
              <div className="social-chip-row">
                {platforms.map((p) => (
                  <span key={p} className="social-chip">
                    {p}
                  </span>
                ))}
              </div>
            ) : null}

            {social.posting_cadence ? (
              <p className="brief-notes">{social.posting_cadence}</p>
            ) : null}

            {!ideas.length && !tracks.length ? (
              <div className="empty-inline">
                <Icon name="share" size={28} />
                <p>
                  Run Ask Brain or send a chat message to generate post ideas, hashtags,
                  and soundtrack references for this brand.
                </p>
              </div>
            ) : null}
          </section>

          {pillars.length ? (
            <section className="panel">
              <div className="panel-head">
                <h3>Content pillars</h3>
              </div>
              <ul className="social-list">
                {pillars.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            </section>
          ) : null}

          {ideas.length ? (
            <section className="panel">
              <div className="panel-head">
                <h3>Post ideas</h3>
                <span className="panel-meta">{ideas.length}</span>
              </div>
              <div className="social-idea-grid">
                {ideas.map((idea, i) => (
                  <article className="social-idea" key={`${idea.format}-${i}`}>
                    <span className="social-format">{idea.format || "Post"}</span>
                    <strong>{idea.hook}</strong>
                    {idea.body ? <p>{idea.body}</p> : null}
                    {idea.cta ? <span className="social-cta">{idea.cta}</span> : null}
                  </article>
                ))}
              </div>
            </section>
          ) : null}

          {hashtags.length ? (
            <section className="panel">
              <div className="panel-head">
                <h3>Hashtags</h3>
              </div>
              <div className="social-chip-row">
                {hashtags.map((t) => (
                  <span key={t} className="social-chip tag">
                    {t}
                  </span>
                ))}
              </div>
            </section>
          ) : null}

          {tracks.length ? (
            <section className="panel">
              <div className="panel-head">
                <h3>Soundtrack refs</h3>
                <span className="panel-meta">Mood-fit · verify before post</span>
              </div>
              <div className="social-track-list">
                {tracks.map((t, i) => (
                  <article className="social-track" key={`${t.title}-${i}`}>
                    <strong>
                      {t.title}
                      {t.artist ? <span> — {t.artist}</span> : null}
                    </strong>
                    {t.mood ? <p className="social-mood">{t.mood}</p> : null}
                    {t.why ? <p>{t.why}</p> : null}
                    {t.trend_note ? (
                      <p className="social-trend">{t.trend_note}</p>
                    ) : null}
                  </article>
                ))}
              </div>
              {social.music_disclaimer ? (
                <p className="brief-notes social-disclaimer">{social.music_disclaimer}</p>
              ) : null}
            </section>
          ) : null}

          {weekPlan.length ? (
            <section className="panel">
              <div className="panel-head">
                <h3>Week plan</h3>
              </div>
              <ul className="social-list">
                {weekPlan.map((row) => (
                  <li key={row}>{row}</li>
                ))}
              </ul>
            </section>
          ) : null}
        </div>
      </div>
    </div>
  );
}
