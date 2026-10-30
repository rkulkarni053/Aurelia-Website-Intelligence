import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import Icon from "./Icon";

const DialogContext = createContext(null);

export function useDialogs() {
  const ctx = useContext(DialogContext);
  if (!ctx) throw new Error("useDialogs must be used inside <DialogProvider>");
  return ctx;
}

function Dialog({ dialog, onClose }) {
  const [value, setValue] = useState(dialog.initial || "");
  const inputRef = useRef(null);
  const confirmRef = useRef(null);
  const isPrompt = dialog.type === "prompt";

  useEffect(() => {
    const el = isPrompt ? inputRef.current : confirmRef.current;
    el?.focus();
    if (isPrompt) inputRef.current?.select();
  }, [isPrompt]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onClose(isPrompt ? null : false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isPrompt, onClose]);

  const submit = (e) => {
    e.preventDefault();
    if (isPrompt) {
      const trimmed = value.trim();
      if (!trimmed) return;
      onClose(trimmed);
    } else {
      onClose(true);
    }
  };

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="dialog-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose(isPrompt ? null : false);
      }}
    >
      <form className="modal dialog" onSubmit={submit}>
        <div className={`dialog-icon${dialog.danger ? " danger" : ""}`}>
          <Icon name={dialog.icon || (dialog.danger ? "trash" : isPrompt ? "edit" : "warning")} size={20} />
        </div>
        <h3 id="dialog-title">{dialog.title}</h3>
        {dialog.message ? <p className="dialog-message">{dialog.message}</p> : null}
        {isPrompt ? (
          <label className="dialog-field">
            <span>{dialog.label || "Name"}</span>
            <input
              ref={inputRef}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={dialog.placeholder || ""}
            />
          </label>
        ) : null}
        <div className="dialog-actions">
          <button type="button" className="button" onClick={() => onClose(isPrompt ? null : false)}>
            Cancel
          </button>
          <button
            ref={confirmRef}
            type="submit"
            className={`button ${dialog.danger ? "danger" : "primary"}`}
            disabled={isPrompt && !value.trim()}
          >
            {dialog.confirmLabel || (isPrompt ? "Save" : "Confirm")}
          </button>
        </div>
      </form>
    </div>
  );
}

export function DialogProvider({ children }) {
  const [dialog, setDialog] = useState(null);
  const resolverRef = useRef(null);

  const open = useCallback(
    (type, options) =>
      new Promise((resolve) => {
        resolverRef.current = resolve;
        setDialog({ type, ...options });
      }),
    []
  );

  const close = useCallback((result) => {
    resolverRef.current?.(result);
    resolverRef.current = null;
    setDialog(null);
  }, []);

  const api = useRef({
    confirm: (options) => open("confirm", options),
    prompt: (options) => open("prompt", options),
  }).current;

  return (
    <DialogContext.Provider value={api}>
      {children}
      {dialog ? <Dialog key={dialog.title} dialog={dialog} onClose={close} /> : null}
    </DialogContext.Provider>
  );
}
