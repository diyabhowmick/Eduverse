"""Orchestration. One call takes a file and produces the whole output folder."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from . import coverage as coverage_mod
from . import digital as digital_mod
from . import report as report_mod
from . import verify
from .config import Config
from .ledger import Ledger
from . import equations as eqmod
from . import figures as figmod
from .ollama_client import OllamaClient
from .schema import Book
from .sources import docx_source, pdf_source
from . import placement
from .structure import (assign_columns, bind_captions, bind_figure_labels,
                        dedupe_text,
                        join_split_math,
                        detect_columns, drop_furniture, join_fragments,
                        merge_lone_bullets, normalise_headings,
                        order_with_captions, reading_order,
                        recompute_alignment, renumber)
from .writer import flow_docx, layout_docx


def _place_late_blocks(page) -> None:
    """Kept for callers of the old name; see placement.place_late_blocks."""
    placement.place_late_blocks(page)


@dataclass
class RunResult:
    out_dir: str
    book: Book
    ledger: Ledger
    stats: Dict[str, int] = field(default_factory=dict)
    files: Dict[str, str] = field(default_factory=dict)
    passed: bool = True
    failures: List[str] = field(default_factory=list)
    elapsed: float = 0.0
    coverage: Optional["coverage_mod.Coverage"] = None


def _prune_figures(book, out_dir: str, cfg: Config) -> int:
    """Delete crops whose block never made it into the book.

    A picture dropped as a repeat or a duplicate still left its PNG and its
    JSON on disk, so the folder claimed content the book does not contain.
    """
    fig_dir = os.path.join(out_dir, "figures")
    if not cfg.prune_unused_figures or not os.path.isdir(fig_dir):
        return 0
    used = set()
    for page in book.pages:
        for b in page.blocks:
            for ref in (b.image_ref, b.redraw_ref):
                if ref:
                    used.add(os.path.splitext(os.path.basename(ref))[0])
    removed = 0
    for name in os.listdir(fig_dir):
        stem, ext = os.path.splitext(name)
        if ext.lower() not in (".png", ".json", ".svg"):
            continue
        if stem in used or stem.rsplit("_", 1)[0] in used:
            continue
        try:
            os.remove(os.path.join(fig_dir, name))
            removed += 1
        except OSError:
            pass
    return removed


def run(input_path: str, out_dir: str, cfg: Optional[Config] = None,
        progress: Optional[Callable] = None) -> RunResult:
    cfg = cfg or Config()
    t0 = time.time()
    os.makedirs(out_dir, exist_ok=True)
    ledger = Ledger()
    client = OllamaClient(cfg)

    ext = os.path.splitext(input_path)[1].lower()
    if ext in (".docx", ".dotx"):
        book = docx_source.extract(input_path, out_dir, cfg, ledger)
    elif ext == ".pdf":
        book = pdf_source.extract(input_path, out_dir, cfg, ledger, client,
                                  progress=progress)
    else:
        raise ValueError(f"unsupported input {ext}, expected .pdf or .docx")

    # a picture repeated on most pages is a logo or a watermark, not content
    book.stats["repeating_images_dropped"] = figmod.drop_repeating(
        book, ledger, cfg, out_dir)

    # structure pass, same for every source
    for page in book.pages:
        book.stats["text_duplicates_dropped"] = (
            book.stats.get("text_duplicates_dropped", 0)
            + dedupe_text(page, ledger, cfg))
        ncols = detect_columns(page.blocks, page, cfg)
        page.columns = ncols
        if page.route == "native" and ncols >= 1:
            # the layout engine already ordered these, so only figures and
            # tables added afterwards need placing
            _place_late_blocks(page)
        else:
            assign_columns(page.blocks, page, ncols)
            page.blocks = reading_order(page.blocks, page, ncols)
        book.stats["split_math_joined"] = (
            book.stats.get("split_math_joined", 0) + join_split_math(page, cfg))
        recompute_alignment(page)

    # book wide: a short line repeated in the same band on many pages is a
    # running head or a page number, whatever it looks like on one page
    if cfg.drop_repeating_furniture:
        book.stats["furniture_dropped"] = drop_furniture(book, ledger, cfg)

    for page in book.pages:
        if cfg.join_fragments:
            book.stats["fragments_joined"] = (
                book.stats.get("fragments_joined", 0)
                + join_fragments(page, cfg))
        book.stats["bullets_merged"] = (
            book.stats.get("bullets_merged", 0) + merge_lone_bullets(page, cfg))
        book.stats["bleed_decorations_dropped"] = (
            book.stats.get("bleed_decorations_dropped", 0)
            + placement.drop_bleed_decorations(page, ledger))
        bind_captions(page, cfg)
        book.stats["figure_labels_bound"] = (
            book.stats.get("figure_labels_bound", 0)
            + bind_figure_labels(page, cfg))
        page.blocks = order_with_captions(page.blocks, cfg)
        book.stats["side_headings_hoisted"] = (
            book.stats.get("side_headings_hoisted", 0)
            + placement.hoist_side_headings(page))
        placement.assign_boxes(page)
        renumber(page)

    book.stats["headings_normalised"] = normalise_headings(book, cfg)

    # after the joining is done, so a formula printed in pieces is cut out as
    # the one formula it is
    if ext == ".pdf":
        book.stats["equation_snippets"] = eqmod.snip_equations(
            book, input_path, out_dir, cfg, client, ledger)

    book.stats["ollama_calls"] = len(client.calls)
    book.stats["ollama_seconds"] = round(
        sum(c.get("s", 0) for c in client.calls), 1)

    cov = coverage_mod.measure(book)
    book.stats["coverage"] = cov.summary()

    book.stats["figure_files_pruned"] = _prune_figures(book, out_dir, cfg)

    json_path = os.path.join(out_dir, "book.json")
    book.save(json_path)

    flow_path, stats = flow_docx.write(book, out_dir, cfg, ledger)
    files = {"book_json": json_path, "flow_docx": flow_path}

    if cfg.write_layout_docx:
        lay_path, lstats = layout_docx.write(book, out_dir, cfg, ledger)
        files["layout_docx"] = lay_path
        for k, v in lstats.items():
            stats.setdefault(f"layout_{k}", v)

    if cfg.write_digital:
        files["digital"] = digital_mod.render(book, out_dir, cfg)

    book_check = verify.check_book(book, ledger, cfg)
    docx_check = verify.check_docx(flow_path, book, cfg, stats)
    # Only meaningful with page_lock on. Flow mode reflows the book on purpose,
    # so a page count difference there is the feature working, not a fault.
    render_check = (verify.check_render(flow_path, len(book.pages))
                    if cfg.page_lock and book.detected.get("format") != "docx"
                    else None)

    ledger_path = os.path.join(out_dir, "ledger.jsonl")
    ledger.save(ledger_path)
    files["ledger"] = ledger_path

    elapsed = time.time() - t0
    report_path = report_mod.render(
        os.path.join(out_dir, "report.html"), book, ledger, cfg,
        book_check, docx_check, stats, render_check, elapsed, cov)
    files["report"] = report_path

    failures = [f"{c.name}: expected {c.expected}, found {c.found}"
                for c in book_check.failures() + docx_check.failures()]
    if render_check is not None and not render_check.ok:
        failures.append(f"{render_check.name}: {render_check.detail}")

    res = RunResult(out_dir=out_dir, book=book, ledger=ledger, stats=stats,
                    files=files, passed=not failures, failures=failures,
                    elapsed=elapsed, coverage=cov)
    if cfg.fail_on_gate and failures:
        raise RuntimeError("gate failed: " + "; ".join(failures))
    return res
