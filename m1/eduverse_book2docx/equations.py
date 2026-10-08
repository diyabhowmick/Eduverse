"""Every formula is also kept as a picture of itself.

A formula is rebuilt from the page's own spans where the geometry allows it,
and read by the model where it does not. Both can be wrong, and a wrong formula
in a textbook is worse than a missing one because nothing about it looks wrong.
So the printed formula is cut out of the page and kept beside the
reconstruction: whatever happens to the LaTeX afterwards, the truth is still on
disk, and a reader or a reviewer can always go back to it.

The crop is taken from the PDF, so it costs nothing but a pixmap. The reading
is a model call, and is skipped offline.
"""

from __future__ import annotations

import io
import os
from typing import Optional

import fitz
from PIL import Image

from .config import Config
from .ledger import Ledger
from .schema import Book


def snip_equations(book: Book, pdf_path: str, out_dir: str, cfg: Config,
                   client, ledger: Optional[Ledger] = None) -> int:
    """Cut out every equation block and, when a model is available, read it."""
    if not cfg.equation_snippets:
        return 0
    eqs = [(p, b) for p in book.pages for b in p.blocks if b.type == "equation"]
    if not eqs:
        return 0
    fig_dir = os.path.join(out_dir, "figures")
    os.makedirs(fig_dir, exist_ok=True)
    made = 0
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return 0
    try:
        for page, blk in eqs:
            if blk.image_ref:                 # already carries its own picture
                continue
            try:
                pg = doc[page.page - 1]
            except Exception:
                continue
            png, w, h = _crop(pg, blk.bbox_pt, cfg)
            if png is None:
                continue
            n = sum(1 for b in page.blocks
                    if b.type == "equation" and b.image_ref) + 1
            name = f"p{page.page:03d}_eq{n:02d}.png"
            with open(os.path.join(fig_dir, name), "wb") as fh:
                fh.write(png)
            blk.image_ref = os.path.join("figures", name)
            blk.px_w, blk.px_h = w, h
            made += 1
            _read_aloud(blk, png, cfg, client)
    finally:
        doc.close()
    return made


def _crop(pg, bbox, cfg: Config):
    """The formula as it was printed, with a little air around it."""
    pad = cfg.equation_snippet_pad_pt
    rect = fitz.Rect(bbox[0] - pad, bbox[1] - pad,
                     bbox[2] + pad, bbox[3] + pad) & pg.rect
    if rect.is_empty or rect.width < 2 or rect.height < 2:
        return None, None, None
    try:
        pix = pg.get_pixmap(clip=rect, dpi=cfg.equation_snippet_dpi)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    except Exception:
        return None, None, None
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue(), img.width, img.height


def _read_aloud(blk, png: bytes, cfg: Config, client) -> None:
    """Ask for the formula in words. Never for its answer."""
    if cfg.offline or not cfg.describe_equations or client is None:
        return
    try:
        d = client.describe_equation(png)
    except Exception:
        return
    reading = str(d.get("reading") or "").strip()
    about = str(d.get("about") or "").strip()
    if not reading:
        return
    blk.math_desc = f"{reading} {about}".strip() if about else reading
