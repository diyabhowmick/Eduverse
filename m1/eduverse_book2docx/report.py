"""report.html, the per page scorecard.

This is how you know a page is good without reading it.
"""

from __future__ import annotations

import html
import os
from typing import Dict, List

from .config import Config
from .ledger import Ledger
from .schema import Book
from .verify import Result

CSS = """
:root{--red:#E0212F;--ink:#1a1a1a;--mut:#6b6b6b;--line:#e3e1da;--bg:#faf9f6}
*{box-sizing:border-box}
body{font-family:Arial,Helvetica,sans-serif;color:var(--ink);background:var(--bg);
margin:0;padding:28px;line-height:1.5}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 10px;font-weight:600}
.sub{color:var(--mut);font-size:13px;margin-bottom:20px}
.cards{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:8px}
.card{background:#fff;border:1px solid var(--line);border-radius:8px;padding:12px 16px;min-width:130px}
.card b{display:block;font-size:22px;line-height:1.2}
.card span{font-size:12px;color:var(--mut)}
table{border-collapse:collapse;width:100%;background:#fff;font-size:13px}
th,td{border:1px solid var(--line);padding:6px 9px;text-align:left;vertical-align:top}
th{background:#f1efe8;font-weight:600}
.ok{color:#1d7a4c;font-weight:600}.bad{color:var(--red);font-weight:600}
.warn{color:#a5730a;font-weight:600}
tr.fail td{background:#fdf3f3}
code{background:#f1efe8;padding:1px 4px;border-radius:3px;font-size:12px}
.small{font-size:12px;color:var(--mut)}
"""


def render(out_path: str, book: Book, ledger: Ledger, cfg: Config,
           book_check: Result, docx_check: Result, stats: Dict[str, int],
           render_check=None, elapsed: float = 0.0, cov=None) -> str:
    d = book.detected or {}
    counts = book.counts()
    n_pages = len(book.pages)
    figs = counts.get("figure", 0)
    described = sum(1 for _, b in book.blocks()
                    if b.type == "figure" and b.figure and b.figure.desc.strip())
    unread_math = sum(1 for _, b in book.blocks() if b.math_unreadable)
    bad_pages = sorted(book_check.page_issues)

    rows = []
    for page in book.pages:
        issues = book_check.page_issues.get(page.page, [])
        pc = {}
        for b in page.blocks:
            pc[b.type] = pc.get(b.type, 0) + 1
        dropped = [e for e in ledger.entries if e["page"] == page.page]
        status = "ok" if not issues else "bad"
        rows.append(f"""<tr class="{'fail' if issues else ''}">
<td>{page.page}</td><td><code>{page.route}</code></td>
<td>{int(page.width_pt)} x {int(page.height_pt)}</td>
<td class="{'bad' if page.layout_confidence < 0.9 else ''}">{page.columns}col
{f" {page.layout_confidence:.2f}" if page.layout_confidence < 1 else ""}</td>
<td>{pc.get('heading',0)}</td><td>{pc.get('paragraph',0)}</td>
<td>{pc.get('list_item',0)}</td><td>{pc.get('table',0)}</td>
<td>{pc.get('figure',0)}</td><td>{pc.get('equation',0)}</td>
<td>{len(dropped)}</td>
<td class="{status}">{'pass' if not issues else 'fail'}</td>
<td class="small">{html.escape('; '.join(issues))[:300]}</td></tr>""")

    def check_rows(res: Result) -> str:
        out = []
        for c in res.checks:
            cls = "ok" if c.ok else "bad"
            out.append(f"<tr class=\"{'' if c.ok else 'fail'}\"><td>{html.escape(c.name)}</td>"
                       f"<td class='{cls}'>{'pass' if c.ok else 'FAIL'}</td>"
                       f"<td>{html.escape(str(c.expected))}</td>"
                       f"<td>{html.escape(str(c.found))}</td>"
                       f"<td class='small'>{html.escape(c.detail)}</td></tr>")
        return "".join(out)

    reasons = ledger.by_reason()
    reason_rows = "".join(
        f"<tr><td><code>{html.escape(k)}</code></td><td>{v}</td></tr>"
        for k, v in sorted(reasons.items(), key=lambda kv: -kv[1]))

    render_row = ""
    if render_check is not None:
        cls = "ok" if render_check.ok else "bad"
        render_row = (f"<tr><td>{render_check.name}</td>"
                      f"<td class='{cls}'>{'pass' if render_check.ok else 'FAIL'}</td>"
                      f"<td>{render_check.expected}</td><td>{render_check.found}</td>"
                      f"<td class='small'>{html.escape(render_check.detail)}</td></tr>")

    errors: Dict[str, int] = {}
    for _p, b in book.blocks():
        if b.type == "figure" and b.figure and b.figure.error:
            errors[b.figure.error] = errors.get(b.figure.error, 0) + 1
    desc_warning = ""
    if figs and described < figs:
        rows_e = "".join(f"<tr><td>{v}</td><td class='small'>{html.escape(k)}</td></tr>"
                         for k, v in sorted(errors.items(), key=lambda kv: -kv[1]))
        desc_warning = f"""<h2>Figure descriptions are missing</h2>
<div class="sub">{figs - described} of {figs} figures have no description, so
their box says so instead of carrying one. The equation and table boxes are
built locally and are unaffected.</div>
<table><tr><th>figures</th><th>reason</th></tr>{rows_e or
'<tr><td>' + str(figs - described) + '</td><td class="small">no reason recorded</td></tr>'}</table>
<div class="sub">If the reason is a connection error, the model was not reached:
<code>python -m eduverse_book2docx --check</code></div>"""

    cov_cards = ""
    cov_table = ""
    if cov is not None:
        cs = cov.summary()
        pct = cs["coverage"] * 100
        cls = "ok" if pct >= 99 else ("warn" if pct >= 95 else "bad")
        cov_cards = f"""<div class="cards">
<div class="card"><b class="{cls}">{pct:.1f}%</b><span>machine readable</span></div>
<div class="card"><b>{cs['opaque']}</b><span>opaque blocks</span></div>
<div class="card"><b>{cs['figures_regenerable']}/{cs['figures']}</b>
<span>figures regenerable</span></div>
<div class="card"><b>{cs['figures_with_svg']}</b><span>redrawn as SVG</span></div>
<div class="card"><b>{cs['equations_as_latex']}/{cs['equations']}</b>
<span>equations as LaTeX</span></div>
<div class="card"><b>{cs['equations_read_by_vlm']}</b><span>read by the VLM</span></div>
<div class="card"><b>{cs['tables_recovered_from_image']}</b>
<span>tables out of images</span></div>
</div>"""
        rows_t = "".join(
            f"<tr><td><code>{html.escape(k)}</code></td><td>{r}</td>"
            f"<td class=\"{'bad' if o else ''}\">{o}</td></tr>"
            for k, (r, o) in sorted(cov.by_type.items()))
        opaque_rows = "".join(
            f"<tr class='fail'><td>{o['page']}</td><td><code>{html.escape(o['id'])}"
            f"</code></td><td>{html.escape(o['type'])}</td>"
            f"<td class='small'>{html.escape(o['why'])}</td></tr>"
            for o in cov.opaque_blocks[:60])
        cov_table = f"""<table><tr><th>block type</th><th>readable</th>
<th>opaque</th></tr>{rows_t}</table>"""
        if opaque_rows:
            cov_table += f"""<h2>Opaque blocks</h2><table><tr><th>page</th>
<th>id</th><th>type</th><th>why</th></tr>{opaque_rows}</table>"""

    html_doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EduVerse ingest report</title><style>{CSS}</style></head><body>
<h1>EduVerse ingest report</h1>
<div class="sub">{html.escape(book.source_file)} &nbsp; <code>{html.escape(book.book_id)}</code>
&nbsp; {elapsed:.1f}s</div>

<div class="cards">
<div class="card"><b>{n_pages}</b><span>pages</span></div>
<div class="card"><b>{ledger.detected}</b><span>blocks detected</span></div>
<div class="card"><b>{ledger.emitted}</b><span>emitted</span></div>
<div class="card"><b>{ledger.dropped}</b><span>dropped</span></div>
<div class="card"><b class="{'ok' if ledger.balanced() else 'bad'}">
{'balanced' if ledger.balanced() else 'OFF BY ' + str(ledger.imbalance())}</b>
<span>ledger</span></div>
<div class="card"><b class="{'ok' if described == figs else 'bad'}">{described}/{figs}</b>
<span>figures described</span></div>
<div class="card"><b class="{'ok' if not unread_math else 'warn'}">{unread_math}</b>
<span>equations not verified</span></div>
<div class="card"><b class="{'ok' if not bad_pages else 'bad'}">{len(bad_pages)}</b>
<span>pages with issues</span></div>
</div>

{desc_warning}

<h2>Semantic coverage</h2>
<div class="sub">How much of the book a model can actually work with. An opaque
block is content that survived only as pixels.</div>
{cov_cards}
{cov_table}

<h2>Detected, nothing declared</h2>
<table><tr><th>board</th><th>grade</th><th>subject</th><th>language</th>
<th>format</th><th>routes</th></tr>
<tr><td>{html.escape(str(d.get('board')))}</td><td>{html.escape(str(d.get('grade')))}</td>
<td>{html.escape(str(d.get('subject')))}</td><td>{html.escape(str(d.get('language')))}</td>
<td>{html.escape(str(d.get('format')))}</td>
<td class="small">{html.escape(str(d.get('routes')))}</td></tr></table>

<h2>Gate</h2>
<table><tr><th>check</th><th>result</th><th>expected</th><th>found</th><th>detail</th></tr>
{check_rows(book_check)}{check_rows(docx_check)}{render_row}</table>

<h2>Written</h2>
<table><tr><th>paragraphs</th><th>tables</th><th>pictures</th>
<th>equations</th><th>equation images</th><th>bookmarks</th></tr>
<tr><td>{stats.get('paragraphs',0)}</td><td>{stats.get('tables',0)}</td>
<td>{stats.get('pictures',0)}</td><td>{stats.get('equations',0)}</td>
<td>{stats.get('equation_images',0)}</td><td>{stats.get('bookmarks',0)}</td></tr></table>

<h2>Dropped, by reason</h2>
<table><tr><th>reason</th><th>count</th></tr>{reason_rows or
'<tr><td colspan=2 class="small">nothing dropped</td></tr>'}</table>

<h2>Pages</h2>
<table><tr><th>#</th><th>route</th><th>size pt</th><th>layout</th><th>head</th><th>para</th>
<th>list</th><th>table</th><th>fig</th><th>eq</th><th>drop</th>
<th>gate</th><th>issues</th></tr>{''.join(rows)}</table>
</body></html>"""

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html_doc)
    return out_path
