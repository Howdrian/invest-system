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
.institution-hero{margin:18px 0 34px;padding:28px 0 24px;border-bottom:1px solid var(--line)}.hero-kicker{display:flex;justify-content:space-between;gap:16px;color:var(--muted);font-size:12px;letter-spacing:.12em;text-transform:uppercase}.hero-decision{display:flex;align-items:center;gap:12px;margin-top:24px}.action-chip{display:inline-flex;border-radius:999px;background:#dbeafe;color:#0b1020;padding:6px 14px;font-weight:800}.confidence-copy{color:var(--muted);font-size:13px}.institution-hero h1{font-size:clamp(30px,6vw,46px);margin:14px 0 4px;letter-spacing:-.03em}.decision-line{max-width:900px;margin:20px 0 18px;font-size:clamp(19px,3vw,27px);line-height:1.55;color:#f8fbff;font-weight:650}.research-boundary{display:flex;gap:12px;align-items:flex-start;max-width:900px;color:var(--muted);font-size:14px}.research-boundary strong{color:#cfe0ff;white-space:nowrap}.research-section{margin:0 0 34px;padding:0 0 30px;border-bottom:1px solid rgba(38,52,79,.72)}.research-section h2{margin:.2em 0 .6em}.section-heading{margin-bottom:16px}.eyebrow{margin:0;color:#7dd3fc;font-size:11px;font-weight:800;letter-spacing:.15em}.executive-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:26px}.executive-grid>div+div{border-left:1px solid var(--line);padding-left:26px}.executive-grid ul{padding-left:19px}.core-evidence-drawer{margin:-18px 0 34px;border-bottom:1px solid var(--line)}.core-evidence-drawer>summary{cursor:pointer;padding:12px 0;color:#dbeafe;font-weight:700}.core-evidence-drawer>div{padding:0 0 20px}.scenario-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.scenario-grid>div{padding:18px;border-left:3px solid #38547c;background:rgba(15,23,42,.5)}.scope-tag,.stance{display:inline-flex;border-radius:999px;background:rgba(125,211,252,.12);color:#bde9ff;padding:2px 8px;font-size:11px}.cio-verdict{margin:18px 0;padding:18px 20px;border-left:4px solid var(--accent);background:rgba(125,211,252,.08)}.cio-verdict>span{color:var(--accent);font-size:12px;font-weight:800;letter-spacing:.08em}.cio-verdict p{margin:8px 0 0;font-size:18px}.research-table{margin:0}.research-table th{letter-spacing:.05em}.research-table td{padding:13px 10px}.stock-table{min-width:980px}.methodology-drawer{margin:12px 0 28px;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}.methodology-drawer>summary{cursor:pointer;padding:14px 0;color:var(--muted);font-weight:700}.methodology-drawer>div{padding:0 0 18px}
.hero-facts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;margin:20px 0 10px;padding:18px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}.hero-fact{min-width:0}.hero-fact span{display:block;margin-bottom:5px;color:var(--muted);font-size:12px}.hero-fact strong{display:block;color:#e8f2ff;font-size:16px;line-height:1.55}.hero-meta{display:flex;flex-wrap:wrap;gap:8px 20px;margin:10px 0 20px;color:var(--muted);font-size:12px}.hero-meta b{color:#dbeafe;font-weight:650}.reader-matrix-cards{display:none}.matrix-card{border:1px solid var(--line);border-radius:14px;background:rgba(15,23,42,.58);padding:14px}.matrix-card-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}.matrix-card-heading small{display:block;margin-top:2px}.matrix-card dl{margin:12px 0 0}.matrix-card dl>div{display:grid;grid-template-columns:minmax(90px,.7fr) minmax(0,1.3fr);gap:10px;padding:9px 0;border-top:1px solid #23304a}.matrix-card dt{color:var(--muted);font-size:12px}.matrix-card dd{margin:0}.evidence-list{display:grid;gap:10px;padding-left:20px}.evidence-meta,.evidence-copy{display:block}.evidence-meta{color:var(--muted);font-size:12px}.evidence-copy{margin-top:2px}
.flow-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.flow-card{margin:0}.flow-card h3{margin-top:0}.flow-row{border-top:1px solid #22304a;padding:10px 0}.flow-row:first-of-type{border-top:0}.flow-label{display:block;color:#9db2d5;font-size:12px;letter-spacing:.08em;text-transform:uppercase;margin-bottom:4px}.raw-report{opacity:.92}.raw-report h1:first-child{font-size:24px}
.department-list{display:grid;gap:10px}.department-card{max-width:100%;border:1px solid var(--line);border-radius:14px;background:#0f172a}.department-card>summary{position:relative;min-height:44px;cursor:pointer;padding:14px 92px 14px 16px}.department-title{display:block;font-weight:700;color:#dbeafe}.department-open-label{position:absolute;top:14px;right:16px;color:var(--accent);font-size:12px;font-weight:650}.department-summary{display:block;margin-top:4px;color:var(--muted);font-size:14px;font-weight:400}.department-card:not([open]) .department-summary{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden}.department-details{padding:4px 16px 16px;border-top:1px solid var(--line)}.department-group{margin-top:2px;border:1px solid var(--line);border-radius:14px}.department-group>summary{display:flex;min-height:44px;cursor:pointer;align-items:center;justify-content:space-between;gap:12px;padding:10px 16px;color:#dbeafe;font-weight:700}.department-group>summary span:last-child{color:var(--accent);font-size:12px}.department-group-body{display:grid;gap:10px;padding:12px;border-top:1px solid var(--line)}.diagnostics-entry{text-align:right;color:var(--muted);font-size:12px}
.warn{color:var(--yellow)}.bad{color:var(--red)}.good{color:var(--green)}
.table-wrap{width:100%;max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}.table-wrap table{min-width:640px}table{width:100%;border-collapse:collapse;margin:12px 0}th,td{border-bottom:1px solid #23304a;padding:9px;text-align:left;vertical-align:top;overflow-wrap:anywhere;word-break:break-word}th{color:#9db2d5;font-size:12px;text-transform:uppercase}
blockquote{border-left:4px solid var(--accent);margin:12px 0;padding:8px 14px;background:#0f172a;color:#dbeafe}
code{background:#0f172a;border:1px solid #1f2a44;border-radius:5px;padding:1px 5px;overflow-wrap:anywhere;word-break:break-word}pre{max-width:100%;overflow:auto;background:#0f172a;border:1px solid #1f2a44;border-radius:12px;padding:14px}img,svg{max-width:100%}
ul,ol{padding-left:24px}.toc a{display:inline-block;margin:4px 8px 4px 0;padding:6px 10px;border:1px solid var(--line);border-radius:9px;background:#0f172a}
.footer{margin-top:28px;color:var(--muted);font-size:13px}
@media(max-width:900px){.hero,.grid,.grid3,.flow-grid,.executive-grid,.scenario-grid{grid-template-columns:1fr}.kpi{border-left:0;padding-left:0}.executive-grid>div+div{border-left:0;border-top:1px solid var(--line);padding:18px 0 0}.hero-kicker{flex-direction:column;gap:2px}}
@media(max-width:700px){.reader-matrix-table{display:none}.reader-matrix-cards{display:grid;gap:12px}}
@media(max-width:640px){.hero,.card,.flow-card{border-radius:16px;padding:16px}.hero-facts{grid-template-columns:1fr;gap:12px}.department-card>summary{padding:12px 78px 12px 12px}.department-open-label{top:12px;right:12px}.department-details{padding:4px 12px 12px}.matrix-card dl>div{grid-template-columns:1fr;gap:2px}}
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
