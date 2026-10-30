"""Ensure Playwright can find installed browsers.

Cursor (and some sandboxes) set PLAYWRIGHT_BROWSERS_PATH to a missing
/tmp cache. Prefer that path only when it actually contains Chromium;
otherwise fall back to the user cache under ~/.cache/ms-playwright.
"""

from __future__ import annotations

import os
from pathlib import Path


def ensure_playwright_browsers_path() -> Path | None:
    candidates: list[Path] = []
    current = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if current:
        candidates.append(Path(current))
    home_cache = Path.home() / ".cache" / "ms-playwright"
    candidates.append(home_cache)

    for path in candidates:
        if not path.is_dir():
            continue
        has_chrome = any(path.glob("chromium*/**/chrome-headless-shell")) or any(
            path.glob("chromium-*/chrome-linux*/chrome")
        )
        # Directory with any chromium* folder is good enough.
        if has_chrome or any(path.glob("chromium*")):
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(path)
            return path

    # Last resort: unset broken override so Playwright uses its default.
    if current and not Path(current).is_dir():
        os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)
    return None
