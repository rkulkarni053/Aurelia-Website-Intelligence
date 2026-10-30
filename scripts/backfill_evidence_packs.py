"""Backfill evidence packs for crawls that already have findings on disk.

Usage (from repo root):
  .venv/bin/python -m scripts.backfill_evidence_packs
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.evidence_pack import (  # noqa: E402
    PACK_FILENAME,
    build_and_write_evidence_pack,
)


def main() -> int:
    data = ROOT / "data" / "websites"
    if not data.exists():
        print(f"No data directory at {data}")
        return 1

    written = 0

    for findings_path in sorted(data.glob("*/crawls/*/evidence/findings.json")):
        crawl_root = findings_path.parents[1]
        domain = crawl_root.parents[1].name
        crawl_id = crawl_root.name

        pack = build_and_write_evidence_pack(
            crawl_root,
            website={"domain": domain},
            crawl={"id": crawl_id},
        )
        written += 1
        pack_path = crawl_root / PACK_FILENAME
        print(
            f"wrote {pack_path.relative_to(ROOT)} "
            f"(overall={pack['scores']['overall']}/10, "
            f"findings={pack['findings']['total']})"
        )

    print(f"done: {written} pack(s) written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
