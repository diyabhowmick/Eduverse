"""Semantic coverage.

The goal is a book with no opaque pixels in it. That is a measurable thing, so
it gets measured: every block is either machine readable, meaning a model can
work with its content directly, or opaque, meaning the content survives only as
an image nobody can query.

This is the number to watch. Character counts and block counts tell you nothing
was lost. Coverage tells you whether what survived is usable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .schema import Block, Book

# text, headings, lists and captions are readable by construction
READABLE_TYPES = {"title", "heading", "paragraph", "list_item", "caption",
                  "box", "figure_note", "table"}


@dataclass
class Coverage:
    total: int = 0
    readable: int = 0
    opaque: int = 0
    by_type: Dict[str, Tuple[int, int]] = field(default_factory=dict)
    opaque_blocks: List[Dict] = field(default_factory=list)
    figures: int = 0
    described: int = 0
    regenerable: int = 0
    vector: int = 0
    equations: int = 0
    equations_latex: int = 0
    equations_from_vlm: int = 0
    tables: int = 0
    tables_from_image: int = 0

    @property
    def ratio(self) -> float:
        return self.readable / self.total if self.total else 1.0

    def summary(self) -> Dict:
        return {
            "blocks": self.total,
            "machine_readable": self.readable,
            "opaque": self.opaque,
            "coverage": round(self.ratio, 4),
            "figures": self.figures,
            "figures_described": self.described,
            "figures_regenerable": self.regenerable,
            "figures_with_svg": self.vector,
            "equations": self.equations,
            "equations_as_latex": self.equations_latex,
            "equations_read_by_vlm": self.equations_from_vlm,
            "tables": self.tables,
            "tables_recovered_from_image": self.tables_from_image,
        }


def is_readable(b: Block) -> Tuple[bool, str]:
    """Can a model work with this block's content, or only look at a picture?"""
    if b.type == "page_furniture":
        return True, "not content"
    if b.type == "equation":
        if b.latex and not b.math_unreadable:
            return True, "latex"
        if b.omml_xml:
            return True, "omml"
        return False, "equation survives only as an image"
    if b.type == "figure":
        m = b.figure
        if m is None:
            return False, "figure with no description"
        if m.regenerable:
            return True, "regenerable spec"
        if (m.desc or "").strip():
            return True, "described"
        return False, "figure with no description"
    if b.type == "table":
        if b.table and any(c.text.strip() for c in b.table.cells):
            return True, "cells"
        return False, "empty table"
    if b.type in READABLE_TYPES:
        return (True, "text") if (b.text or "").strip() else (False, "empty")
    return False, f"no reader for {b.type}"


def measure(book: Book) -> Coverage:
    cov = Coverage()
    for page, b in book.blocks():
        if b.type == "page_furniture":
            continue
        cov.total += 1
        ok, why = is_readable(b)
        r, o = cov.by_type.get(b.type, (0, 0))
        if ok:
            cov.readable += 1
            cov.by_type[b.type] = (r + 1, o)
        else:
            cov.opaque += 1
            cov.by_type[b.type] = (r, o + 1)
            cov.opaque_blocks.append({
                "id": b.id, "page": b.page, "type": b.type, "why": why,
                "bbox": [round(v, 1) for v in b.bbox_pt],
            })

        if b.type == "figure":
            cov.figures += 1
            m = b.figure
            if m:
                if (m.desc or "").strip():
                    cov.described += 1
                if m.regenerable:
                    cov.regenerable += 1
                if m.svg_ref:
                    cov.vector += 1
        elif b.type == "equation":
            cov.equations += 1
            if b.latex and not b.math_unreadable:
                cov.equations_latex += 1
            if b.latex_source == "vlm":
                cov.equations_from_vlm += 1
        elif b.type == "table":
            cov.tables += 1
            if b.source in ("vlm_table", "ocr_table"):
                cov.tables_from_image += 1
    return cov


def worst_pages(cov: Coverage, n: int = 8) -> List[Tuple[int, int]]:
    counts: Dict[int, int] = {}
    for ob in cov.opaque_blocks:
        counts[ob["page"]] = counts.get(ob["page"], 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])[:n]
