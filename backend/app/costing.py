"""What a book cost to make, and what one would cost before you make it.

The numbers come from two real runs:

    39 pages, 37 native + 2 hybrid, 45 figures   388s
    12 pages, all scanned,          13 figures   316s

Two things are paid for. Reading a page the model has to transcribe, and
describing a figure — which happens to every figure on every book, native or
not, and takes two calls: a description, and a structured spec for the ones
that can be redrawn.

A native page costs nothing at all, because the text is copied straight out of
the file. That single fact is why a native PDF is roughly three times cheaper
than a scanned one, and why finding a text-layer version of a textbook is worth
five minutes of somebody's time.
"""
from __future__ import annotations

# per million tokens, gpt-4.1-mini
IN_RATE, OUT_RATE = 0.40, 1.60

# a page image at 150 DPI in, a page of text out
PAGE_IN, PAGE_OUT = 2700, 1200
# a cropped figure in, a short description out
FIG_IN, FIG_OUT = 900, 220
FIG_CALLS = 2          # describe, then spec

# roughly what pre-generating every explanation costs for a whole book:
# keywords x modes x depths, each a short answer
EXPL_PER_KEYWORD = 6
EXPL_IN, EXPL_OUT = 700, 180


def _usd(tok_in: int, tok_out: int) -> float:
    return tok_in / 1e6 * IN_RATE + tok_out / 1e6 * OUT_RATE


def book_cost(scanned_pages: int, figures: int, keywords: int = 0) -> dict:
    """What a book costs, broken down so somebody can see where it went."""
    pages = _usd(scanned_pages * PAGE_IN, scanned_pages * PAGE_OUT)
    figs = _usd(figures * FIG_CALLS * FIG_IN, figures * FIG_CALLS * FIG_OUT)
    expl = _usd(keywords * EXPL_PER_KEYWORD * EXPL_IN,
                keywords * EXPL_PER_KEYWORD * EXPL_OUT) if keywords else 0.0
    return {"pages": round(pages, 4), "figures": round(figs, 4),
            "explanations": round(expl, 4),
            "total": round(pages + figs + expl, 4)}


def estimate(pages: int, route: str, figures: int, keywords: int = 0) -> dict:
    """What a book WOULD cost, shown before anybody spends it.

    Seeing that a scanned book costs three times a native one changes which
    file somebody uploads, which is worth more than any backend optimisation.
    """
    scanned = pages if route == "scanned" else 0
    out = book_cost(scanned, figures, keywords)
    native = book_cost(0, figures, keywords)["total"]
    out["times_more_than_native"] = round(out["total"] / native, 2) if native else None
    # What actually differs between the two routes is the page reading. Figures
    # and explanations cost the same either way, so quoting a multiple of the
    # TOTAL understates it badly once explanations are included.
    out["extra_vs_native"] = round(out["total"] - native, 4)
    if route == "scanned":
        out["note"] = (
            f"Every page is read by a model, which adds ${out['pages']:.2f} that a "
            f"book with a text layer would not cost at all. Figures and "
            f"explanations are the same either way. Scanned books also convert "
            f"worse — fewer headings found, so the reviewer gets less structure.")
    else:
        out["note"] = ("Native, so no page reading at all. The cost is describing "
                       "the figures and pre-generating the explanations — both "
                       "paid once, then shared by every school on this syllabus.")
    return out


def per_school(cost: float, schools: int) -> float | None:
    """The number that actually matters. A book is paid for once and read by
    every school on that syllabus."""
    return round(cost / schools, 4) if schools else None
