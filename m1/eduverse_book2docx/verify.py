"""Verification. Reopen what we wrote and compare it against book.json.

Failure is visible, not silent. Every check names what it expected and what it
found so the report can point at the page.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from docx import Document
from docx.oxml.ns import qn

from .config import Config
from .ledger import Ledger
from .schema import Block, Book


@dataclass
class Check:
    name: str
    ok: bool
    expected: object = ""
    found: object = ""
    detail: str = ""


@dataclass
class Result:
    checks: List[Check] = field(default_factory=list)
    page_issues: Dict[int, List[str]] = field(default_factory=dict)

    def add(self, name, ok, expected="", found="", detail="") -> None:
        self.checks.append(Check(name, ok, expected, found, detail))

    def page_issue(self, page: int, msg: str) -> None:
        self.page_issues.setdefault(page, []).append(msg)

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checks)

    def failures(self) -> List[Check]:
        return [c for c in self.checks if not c.ok]


# ---------------------------------------------------------------------------
# book.json level checks
# ---------------------------------------------------------------------------

def check_book(book: Book, ledger: Ledger, cfg: Config) -> Result:
    r = Result()
    r.add("ledger balanced", ledger.balanced(),
          ledger.detected, ledger.emitted + ledger.dropped,
          f"imbalance {ledger.imbalance()}")

    for page in book.pages:
        # every figure has a description
        for b in page.blocks:
            if b.type == "figure":
                if not b.image_ref:
                    r.page_issue(page.page, f"{b.id} figure with no image file")
                elif (cfg.describe_figures and not cfg.offline
                      and (b.figure is None or not (b.figure.desc or "").strip())):
                    r.page_issue(page.page, f"{b.id} figure with no description")
            if b.type == "heading" and not b.level:
                r.page_issue(page.page, f"{b.id} heading with no level")
            if b.math_unreadable:
                r.page_issue(page.page, f"{b.id} equation not verified")
            if b.type != "figure_note" and not _within(b, page):
                r.page_issue(page.page, f"{b.id} bbox outside the page")
        if page.layout_confidence < 0.75:
            r.page_issue(page.page,
                         f"layout uncertain ({page.layout_confidence:.2f})"
                         + (": " + "; ".join(page.layout_notes)
                            if page.layout_notes else ""))
        # reading order monotonic within a column
        order_ok = _order_monotonic(page.blocks)
        if not order_ok:
            r.page_issue(page.page, "reading order not monotonic")
        # text coverage: how much of the page area carries a block
        cov = _coverage(page)
        if page.route != "scanned" and cov < 0.02 and page.blocks:
            r.page_issue(page.page, f"low block coverage {cov:.1%}")
        ov = _overlaps(page)
        if ov:
            r.page_issue(page.page, f"{ov} overlapping block pairs")

    r.add("no page issues", not r.page_issues,
          0, sum(len(v) for v in r.page_issues.values()))
    return r


def _within(b: Block, page) -> bool:
    tol = 6.0
    return (b.x0 >= -tol and b.y0 >= -tol
            and b.x1 <= page.width_pt + tol and b.y1 <= page.height_pt + tol)


def _order_monotonic(blocks) -> bool:
    """Judged inside a column: crossing to the next column resets the y."""
    # A caption travels with its picture, a description box has no printed
    # place, and a side heading is moved ahead of its text on purpose: none of
    # them is an ordering fault.
    ys = [b.y0 for b in blocks if b.column in (0, -1)
          and b.type not in ("caption", "figure_note")
          and "side_heading" not in b.flags]
    if len(ys) < 3:
        return True
    inversions = sum(1 for a, b in zip(ys, ys[1:]) if b < a - 4)
    return inversions <= max(1, len(ys) // 8)


def _coverage(page) -> float:
    area = page.width_pt * page.height_pt
    if area <= 0:
        return 0.0
    return sum(max(0.0, b.width) * max(0.0, b.height)
               for b in page.blocks if b.type != "page_furniture") / area


def _overlaps(page) -> int:
    """Blocks that sit on top of each other where the page does not.

    A description box is a flow construct with no printed position of its own,
    so it can never be an overlap. Neither can a caption or a title PRINTED
    OVER a picture: a unit opener prints MEASUREMENT across the artwork, and
    reporting that as a fault buries the overlaps that are real, which are two
    pieces of TEXT landing on the same spot.
    """
    blocks = [b for b in page.blocks
              if b.type not in ("page_furniture", "figure_note")
              and b.width > 2]
    n = 0
    for i, a in enumerate(blocks):
        for b in blocks[i + 1:]:
            ix = min(a.x1, b.x1) - max(a.x0, b.x0)
            iy = min(a.y1, b.y1) - max(a.y0, b.y0)
            if ix <= 4 or iy <= 4:
                continue
            small = min(a.width * a.height, b.width * b.height)
            if small <= 0 or (ix * iy) / small <= 0.55:
                continue
            if _text_on_picture(a, b):
                continue
            n += 1
    return n


def _text_on_picture(a: Block, b: Block) -> bool:
    kinds = {a.type, b.type}
    if "figure" not in kinds:
        return False
    return bool(kinds & {"paragraph", "heading", "caption", "list_item",
                         "equation"})


# ---------------------------------------------------------------------------
# docx level checks
# ---------------------------------------------------------------------------

def check_docx(path: str, book: Book, cfg: Config, stats: Dict[str, int]) -> Result:
    r = Result()
    doc = Document(path)

    want = book.counts()
    want_tables = (want.get("table", 0) + want.get("box", 0)
                   + want.get("figure_note", 0))
    got_tables = len(doc.tables)
    r.add("table count", got_tables >= want_tables, want_tables, got_tables)

    got_pics = len(doc.inline_shapes)
    want_pics = want.get("figure", 0)
    r.add("picture count", got_pics >= want_pics * 0.98, want_pics, got_pics)

    got_eq = len(doc.element.body.findall(
        ".//{http://schemas.openxmlformats.org/officeDocument/2006/math}oMath"))
    want_eq = stats.get("equations", 0)
    r.add("equation count", got_eq >= want_eq, want_eq, got_eq)

    # every figure that carries a description must have its box in the document
    want_notes = sum(1 for _, b in book.blocks() if b.type == "figure_note")
    r.add("description boxes", stats.get("figure_notes", 0) >= want_notes,
          want_notes, stats.get("figure_notes", 0))

    want_chars = _expected_chars(book)
    got_chars = _docx_chars(doc)
    if want_chars:
        delta = abs(got_chars - want_chars) / want_chars
        r.add("character total", delta <= max(cfg.char_tolerance, 0.02),
              want_chars, got_chars, f"delta {delta:.2%}")
    else:
        r.add("character total", True, 0, got_chars)

    # bold survived
    want_bold = sum(1 for _, b in book.blocks()
                    for rn in b.runs if rn.bold)
    got_bold = sum(1 for p in doc.paragraphs for rn in p.runs if rn.bold)
    r.add("bold runs", got_bold >= want_bold * 0.9 or want_bold == 0,
          want_bold, got_bold)

    # alt text carried the descriptions
    want_desc = sum(1 for _, b in book.blocks()
                    if b.type == "figure" and b.figure
                    and (b.figure.desc or "").strip())
    got_desc = _alt_text_count(doc)
    r.add("alt text", got_desc >= want_desc, want_desc, got_desc)

    # headings landed on the right styles
    want_h = sum(1 for _, b in book.blocks() if b.type == "heading")
    got_h = sum(1 for p in doc.paragraphs
                if (p.style.name or "").startswith("EV H"))
    r.add("heading count", got_h >= want_h * 0.95 or want_h == 0, want_h, got_h)
    return r


def _expected_chars(book: Book) -> int:
    total = 0
    for _, b in book.blocks():
        if b.type == "page_furniture":
            continue
        if b.type == "figure_note":
            total += len(re.sub(r"\s+", " ", b.text or "").strip())
            total += len("Image description  ()") + len(b.block_kind or "figure")
            continue
        if b.type == "equation" and b.latex and not b.math_unreadable:
            continue                       # becomes OMML, not plain characters
        total += len(re.sub(r"\s+", " ", b.text or "").strip())
        if b.type == "table" and b.table:
            total += sum(len(re.sub(r"\s+", " ", c.text or "").strip())
                         for c in b.table.cells)
    return total


def _docx_chars(doc) -> int:
    total = 0
    for p in doc.paragraphs:
        if (p.style.name or "") == "EV Note":
            continue
        for rn in p.runs:
            if rn.font.hidden:
                continue
            total += len(re.sub(r"\s+", " ", rn.text or "").strip())
    # Walk the table XML rather than row.cells: a merged cell is returned once
    # per grid position it covers, and lxml hands back a fresh proxy object each
    # time, so neither identity nor position can dedupe it from the outside.
    for t in doc.tables:
        for tc in t._tbl.iter(qn("w:tc")):
            for rn in tc.iter(qn("w:r")):
                if rn.find(qn("w:rPr") + "/" + qn("w:vanish")) is not None:
                    continue
                txt = "".join(n.text or "" for n in rn.iter(qn("w:t")))
                total += len(re.sub(r"\s+", " ", txt).strip())
    return total


def _alt_text_count(doc) -> int:
    n = 0
    for el in doc.element.body.iter():
        if el.tag.endswith("}docPr") and (el.get("descr") or "").strip():
            n += 1
    return n


# ---------------------------------------------------------------------------
# Render check
# ---------------------------------------------------------------------------

def check_render(docx_path: str, expected_pages: int,
                 timeout: int = 240) -> Optional[Check]:
    """Render with LibreOffice and compare the page count. Page drift means a
    style is wrong. Skipped silently when soffice is not installed."""
    soffice = _which_soffice()
    if not soffice:
        return None
    out_dir = os.path.dirname(os.path.abspath(docx_path))
    try:
        subprocess.run([soffice, "--headless", "--convert-to", "pdf",
                        "--outdir", out_dir, docx_path],
                       check=True, timeout=timeout,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        return Check("render", False, expected_pages, "-", str(exc)[:120])
    pdf = os.path.splitext(docx_path)[0] + ".pdf"
    if not os.path.exists(pdf):
        return Check("render", False, expected_pages, "-", "no pdf produced")
    try:
        import fitz
        with fitz.open(pdf) as d:
            got = d.page_count
    except Exception as exc:
        return Check("render", False, expected_pages, "-", str(exc)[:120])
    drift = abs(got - expected_pages) / max(1, expected_pages)
    return Check("render page count", drift <= 0.35, expected_pages, got,
                 f"drift {drift:.0%}")


def _which_soffice() -> Optional[str]:
    from shutil import which
    for name in ("soffice", "libreoffice"):
        p = which(name)
        if p:
            return p
    return None
