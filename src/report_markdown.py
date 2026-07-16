# -*- coding: utf-8 -*-
"""Small deterministic Markdown-to-HTML helpers for static reports."""

from __future__ import annotations

import html
import re
from typing import Any, List

CSS = """<style>
:root{--bg:#0b1020;--card:#121a2b;--line:#26344f;--text:#edf2ff;--muted:#9aa8c7;--accent:#7dd3fc;--red:#fb7185;--yellow:#facc15;--green:#86efac}
*{box-sizing:border-box}html,body{max-width:100%;min-width:0}body{margin:0;background:linear-gradient(135deg,#08101f,#111827);color:var(--text);font-family:"Noto Sans SC","PingFang SC","Microsoft YaHei",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.65}
main{width:100%;max-width:1120px;min-width:0;margin:0 auto;padding:clamp(14px,4vw,28px);overflow-wrap:anywhere}a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
h1{font-size:clamp(26px,7vw,32px);margin:.2em 0 .4em}h2{font-size:23px;margin:1.1em 0 .5em;color:#cfe0ff}h3{font-size:18px;margin:1em 0 .35em;color:#dbeafe}h1,h2,h3,h4,p,li,a,summary,span{overflow-wrap:anywhere;word-break:break-word}
.hero,.card,.flow-card{max-width:100%;min-width:0;border:1px solid var(--line);background:rgba(18,26,43,.94);border-radius:22px;padding:20px;margin:16px 0}.hero{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(220px,.8fr);gap:20px}.hero>*{min-width:0}
.muted,small{color:var(--muted)}.kpi{border-left:1px solid var(--line);padding-left:16px}.kpi b{display:block;font-size:24px;color:var(--accent)}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.grid3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.pill{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:3px 10px;margin:2px 4px 2px 0;font-size:12px;color:#dbeafe;background:#0f172a}
.flow-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.flow-card{margin:0}.flow-card h3{margin-top:0}.flow-row{border-top:1px solid #22304a;padding:10px 0}.flow-row:first-of-type{border-top:0}.flow-label{display:block;color:#9db2d5;font-size:12px;letter-spacing:.08em;text-transform:uppercase;margin-bottom:4px}.raw-report{opacity:.92}.raw-report h1:first-child{font-size:24px}
.department-list{display:grid;gap:10px}.department-card{max-width:100%;border:1px solid var(--line);border-radius:14px;background:#0f172a}.department-card>summary{cursor:pointer;padding:14px 16px}.department-title{display:block;font-weight:700;color:#dbeafe}.department-summary{display:block;margin-top:4px;color:var(--muted);font-size:14px;font-weight:400}.department-card:not([open]) .department-summary{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden}.department-details{padding:4px 16px 16px;border-top:1px solid var(--line)}.diagnostics-entry{text-align:right;color:var(--muted);font-size:12px}
.warn{color:var(--yellow)}.bad{color:var(--red)}.good{color:var(--green)}
.table-wrap{width:100%;max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}.table-wrap table{min-width:640px}table{width:100%;border-collapse:collapse;margin:12px 0}th,td{border-bottom:1px solid #23304a;padding:9px;text-align:left;vertical-align:top;overflow-wrap:anywhere;word-break:break-word}th{color:#9db2d5;font-size:12px;text-transform:uppercase}
blockquote{border-left:4px solid var(--accent);margin:12px 0;padding:8px 14px;background:#0f172a;color:#dbeafe}
code{background:#0f172a;border:1px solid #1f2a44;border-radius:5px;padding:1px 5px;overflow-wrap:anywhere;word-break:break-word}pre{max-width:100%;overflow:auto;background:#0f172a;border:1px solid #1f2a44;border-radius:12px;padding:14px}img,svg{max-width:100%}
ul,ol{padding-left:24px}.toc a{display:inline-block;margin:4px 8px 4px 0;padding:6px 10px;border:1px solid var(--line);border-radius:9px;background:#0f172a}
.footer{margin-top:28px;color:var(--muted);font-size:13px}
@media(max-width:900px){.hero,.grid,.grid3,.flow-grid{grid-template-columns:1fr}.kpi{border-left:0;padding-left:0}}
@media(max-width:640px){.hero,.card,.flow-card{border-radius:16px;padding:16px}.department-card>summary{padding:12px}.department-details{padding:4px 12px 12px}}
</style>"""


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def inline_md(text: str) -> str:
    escaped = esc(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', escaped)
    return escaped


def markdown_to_html(markdown: str) -> str:
    """Render the report Markdown subset as deterministic HTML."""

    lines = markdown.splitlines()
    parts: List[str] = []
    in_list = False
    in_code = False
    code_lines: List[str] = []
    i = 0

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            parts.append("</ul>")
            in_list = False

    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
                parts.append(f"<pre><code>{esc(chr(10).join(code_lines))}</code></pre>")
                code_lines = []
                in_code = False
            else:
                close_list()
                in_code = True
            i += 1
            continue
        if in_code:
            code_lines.append(raw)
            i += 1
            continue

        if not stripped:
            close_list()
            i += 1
            continue

        if stripped.startswith("|") and i + 1 < len(lines) and _is_table_separator(lines[i + 1]):
            close_list()
            header = _split_table_row(stripped)
            i += 2
            rows: List[List[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(_split_table_row(lines[i].strip()))
                i += 1
            head = "".join(f"<th>{inline_md(cell)}</th>" for cell in header)
            body = "".join(
                "<tr>" + "".join(f"<td>{inline_md(cell)}</td>" for cell in row) + "</tr>"
                for row in rows
            )
            parts.append(
                '<div class="table-wrap" role="region" tabindex="0">'
                f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
                "</div>"
            )
            continue

        if stripped.startswith("#"):
            close_list()
            level = min(len(stripped) - len(stripped.lstrip("#")), 4)
            text = stripped[level:].strip()
            parts.append(f"<h{level}>{inline_md(text)}</h{level}>")
        elif stripped.startswith(">"):
            close_list()
            parts.append(f"<blockquote>{inline_md(stripped.lstrip('>').strip())}</blockquote>")
        elif stripped.startswith(("- ", "* ")):
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{inline_md(stripped[2:].strip())}</li>")
        elif re.match(r"^\d+\.\s+", stripped):
            if not in_list:
                parts.append("<ul>")
                in_list = True
            list_item = re.sub(r"^\d+\.\s+", "", stripped)
            parts.append(f"<li>{inline_md(list_item)}</li>")
        else:
            close_list()
            parts.append(f"<p>{inline_md(stripped)}</p>")
        i += 1

    close_list()
    if in_code:
        parts.append(f"<pre><code>{esc(chr(10).join(code_lines))}</code></pre>")
    return "\n".join(parts)


def _is_table_separator(line: str) -> bool:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells)


def _split_table_row(line: str) -> List[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]
