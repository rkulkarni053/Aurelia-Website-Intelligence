import { useEffect, useState } from "react";
import { STORAGE_KEYS } from "../api";

const THEMES = ["light", "dark"];

function readTheme() {
  const stored = localStorage.getItem(STORAGE_KEYS.theme);
  if (THEMES.includes(stored)) return stored;
  if (window.matchMedia?.("(prefers-color-scheme: dark)").matches) return "dark";
  return "light";
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  document.documentElement.style.colorScheme = theme;
}

export default function useTheme() {
  const [theme, setThemeState] = useState(() => {
    if (typeof document === "undefined") return "light";
    const initial = readTheme();
    applyTheme(initial);
    return initial;
  });

  useEffect(() => {
    applyTheme(theme);
    localStorage.setItem(STORAGE_KEYS.theme, theme);
  }, [theme]);

  const setTheme = (next) => {
    if (!THEMES.includes(next)) return;
    setThemeState(next);
  };

  const toggleTheme = () => setThemeState((t) => (t === "dark" ? "light" : "dark"));

  return { theme, setTheme, toggleTheme, isDark: theme === "dark" };
}
