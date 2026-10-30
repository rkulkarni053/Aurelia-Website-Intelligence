import Icon from "./Icon";

/**
 * Guided handoff CTA between funnel modes.
 * Compact toolbar form — sits on the right of mode tabs.
 */
export default function NextStepBar({ label, hint, onClick, disabled }) {
  if (!label) return null;
  return (
    <div className="next-step toolbar">
      {hint ? <p className="next-step-hint" title={hint}>{hint}</p> : null}
      <button type="button" className="action-btn primary" onClick={onClick} disabled={disabled} title={hint || label}>
        <span>{label}</span>
        <Icon name="arrow" size={14} />
      </button>
    </div>
  );
}
