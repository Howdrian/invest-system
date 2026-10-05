"""Read official filing content; excerpts are source material, not AI summaries."""
from __future__ import annotations

import io
import re
from html.parser import HTMLParser
from typing import Any


class _FilingHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skipped = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in {"script", "style"}:
            self.skipped += 1
        elif tag in {"p", "tr", "div", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self.skipped:
            self.skipped -= 1

    def handle_data(self, data: str) -> None:
        if not self.skipped:
            self.parts.append(data + " ")


def extract_filing_text(content: bytes, *, max_pages: int = 40) -> str:
    if content.lstrip().startswith(b"%PDF"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(f"[Page {i + 1}]\n{page.extract_text() or ''}"
                         for i, page in enumerate(reader.pages[:max_pages]))
    parser = _FilingHTML()
    parser.feed(content.decode("utf-8", errors="replace"))
    return "".join(parser.parts)


def financial_excerpt(text: str, *, limit: int = 4000) -> str:
    """Keep explanatory passages and adjacent context, not only growth figures."""
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines() if line.strip()]
    if len("\n".join(lines)) <= limit:
        return "\n".join(lines)
    important = re.compile(
        r"现金流量.*(?:原因|说明)|(?:原因|主要是).*现金|成员单位存款|营运资[本金]|"
        r"利润.*变动原因|收入.*变动原因|主营.*(?:变化|变动)|不良贷款|净息差|"
        r"working capital|cash flow.*(?:due|reflect|change)|net cash.*(?:provided|used)|"
        r"10b5-1|transaction code|reporting person|repurchase|buyback", re.I)
    selected: set[int] = set()
    for i, line in enumerate(lines):
        if important.search(line):
            selected.update(range(max(0, i - 2), min(len(lines), i + 5)))
    # Preserve order and include the document heading; ellipses denote omitted text.
    selected.update(range(min(4, len(lines))))
    if len(selected) <= 4:
        return "\n".join(lines)[:limit]
    parts: list[str] = []
    previous = -1
    for i in sorted(selected):
        if i > previous + 1:
            parts.append("[…]")
        parts.append(lines[i])
        previous = i
    return "\n".join(parts)[:limit]
