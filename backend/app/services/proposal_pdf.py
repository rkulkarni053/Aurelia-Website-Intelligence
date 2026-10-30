"""Export proposal markdown to a simple PDF (free, local)."""

from __future__ import annotations

import re
from pathlib import Path

from fpdf import FPDF


class ProposalPDF(FPDF):
    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", size=8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")


def _safe(text: str) -> str:
    # Helvetica core fonts are Latin-1; strip unsupported glyphs.
    return (
        (text or "")
        .replace("—", "-")
        .replace("–", "-")
        .replace("★", "*")
        .replace("•", "-")
        .replace("“", '"')
        .replace("”", '"')
        .replace("’", "'")
        .encode("latin-1", "replace")
        .decode("latin-1")
    )


def markdown_to_pdf(markdown: str, out_path: Path) -> Path:
    pdf = ProposalPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_margins(16, 16, 16)
    usable = pdf.epw

    def write(text: str, size: int = 10, style: str = "", h: float = 5):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", style, size)
        pdf.multi_cell(usable, h, _safe(text))

    for raw_line in (markdown or "").splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            pdf.ln(4)
            continue

        if line.startswith("# "):
            write(line[2:].strip(), size=18, style="B", h=9)
            pdf.ln(2)
        elif line.startswith("## "):
            pdf.ln(2)
            write(line[3:].strip(), size=13, style="B", h=7)
            pdf.ln(1)
        elif line.startswith("### "):
            write(line[4:].strip(), size=11, style="B", h=6)
        elif line.startswith("---"):
            pdf.ln(1)
            y = pdf.get_y()
            pdf.set_draw_color(180, 180, 180)
            pdf.line(pdf.l_margin, y, pdf.l_margin + usable, y)
            pdf.ln(3)
        elif line.startswith("|"):
            cleaned = re.sub(r"\|", " ", line).strip()
            if set(cleaned) <= set("-: "):
                continue
            write(cleaned, size=9, h=5)
        elif line.lstrip().startswith("- "):
            write("- " + line.lstrip()[2:], size=10, h=5)
        else:
            text = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
            text = re.sub(r"`(.+?)`", r"\1", text)
            write(text, size=10, h=5)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_path))
    return out_path


def export_proposal_pdf(root: Path) -> Path:
    md_path = root / "proposal" / "proposal.md"
    if not md_path.exists():
        raise FileNotFoundError("proposal.md not found; generate the proposal first")
    out = root / "proposal" / "proposal.pdf"
    markdown_to_pdf(md_path.read_text(encoding="utf-8"), out)
    return out
