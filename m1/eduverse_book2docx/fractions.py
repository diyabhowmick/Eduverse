"""Put a stacked fraction back together.

A display fraction is printed as three things: the numerator, a rule, and the
denominator. Every text extractor returns them as separate lines, so the book
came out holding `mu =  3 x 10^8` and `2 x 10^8  = 1.5` as two unrelated
blocks, one of which was then large enough to be called a heading.

The rule line is the evidence. Nothing is merged without one, nothing is
merged unless both halves sit squarely on it, and the result is only kept if
it validates as LaTeX. A fraction that cannot be rebuilt is left exactly as it
was: two blocks are wrong, an invented formula is worse.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from .config import Config
from .mathtools import prepare
from .schema import Block, Page

Rule = Tuple[float, float, float]          # y, x0, x1

MAX_RULE_WIDTH_PT = 260.0                  # wider is a table border or a divider
MAX_GAP_PT = 18.0                          # leg to rule
MIN_COVER = 0.55                           # how much of the rule the leg spans
MAX_LEG_CHARS = 70                         # a leg is a term, not a sentence
MAX_LEG_WORDS = 9
MAX_LEG_WIDTH_RATIO = 1.5                  # of the rule it sits on


def rejoin(page: Page, h_rules: Sequence[Rule], cfg: Config) -> int:
    """Merge numerator, rule and denominator into one equation block."""
    if not cfg.rejoin_stacked_fractions or not h_rules:
        return 0

    merged = 0
    used: set = set()
    for rule in sorted(h_rules, key=lambda r: r[0]):
        y, rx0, rx1 = rule
        if (rx1 - rx0) <= 0 or (rx1 - rx0) > MAX_RULE_WIDTH_PT:
            continue
        top = _leg(page, rule, above=True, used=used)
        bot = _leg(page, rule, above=False, used=used)
        if top is None or bot is None or top is bot:
            continue
        built = _build(top.text, bot.text)
        if built is None:
            continue
        text, latex = built
        top.type = "equation"
        top.text = text
        top.latex = latex
        top.latex_source = "text_layer"
        top.math_unreadable = False
        top.display_math = True
        top.level = None
        top.runs = []
        top.bbox_pt = [min(top.x0, bot.x0), min(top.y0, bot.y0),
                       max(top.x1, bot.x1), max(top.y1, bot.y1)]
        top.flags.append("fraction_rejoined")
        page.blocks = [b for b in page.blocks if b is not bot]
        used.add(id(top))
        used.add(id(bot))
        merged += 1
    return merged


def _leg_shaped(text: str) -> bool:
    """A fraction leg is a term or a short phrase, never a sentence.

    Without this the rule under a section banner pairs the paragraph above it
    with the paragraph below and publishes the two as one fraction.
    """
    t = (text or "").strip()
    if not t or len(t) > MAX_LEG_CHARS:
        return False
    if len(t.split()) > MAX_LEG_WORDS:
        return False
    if t.endswith((".", "!", "?", ":", ";")) and len(t.split()) > 3:
        return False
    return True


def _leg(page: Page, rule: Rule, above: bool,
         used: Optional[set] = None) -> Optional[Block]:
    """The block sitting directly on one side of the rule, if there is one."""
    y, rx0, rx1 = rule
    width = rx1 - rx0
    best, best_gap = None, 1e9
    for b in page.blocks:
        if b.type not in ("paragraph", "equation", "heading", "list_item"):
            continue
        if not b.bbox_pt or not (b.text or "").strip():
            continue
        if used is not None and id(b) in used:
            continue
        if not _leg_shaped(b.text):
            continue
        gap = (y - b.y1) if above else (b.y0 - y)
        if gap < -1.0 or gap > MAX_GAP_PT:
            continue
        cover = min(b.x1, rx1) - max(b.x0, rx0)
        if width <= 0 or cover / width < MIN_COVER:
            continue
        if b.width > width * MAX_LEG_WIDTH_RATIO:   # a paragraph, not a leg
            continue
        if gap < best_gap:
            best, best_gap = b, gap
    return best


def _split_on_equals(text: str, keep: str) -> Tuple[str, str]:
    """A leg often carries part of the surrounding equation.

    `mu = 3 x 10^8` is a prefix and a numerator; `2 x 10^8 = 1.5` is a
    denominator and a suffix. Splitting on the outermost equals keeps both.
    """
    t = (text or "").strip()
    if "=" not in t:
        return ("", t) if keep == "tail" else (t, "")
    if keep == "tail":
        head, tail = t.rsplit("=", 1)
        return head.strip() + " = ", tail.strip()
    head, tail = t.split("=", 1)
    return head.strip(), " = " + tail.strip()


def _build(top_text: str, bot_text: str) -> Optional[Tuple[str, str]]:
    prefix, num = _split_on_equals(top_text, "tail")
    den, suffix = _split_on_equals(bot_text, "head")
    if not num.strip() or not den.strip():
        return None

    parts: List[str] = []
    for piece in (prefix, num, den, suffix):
        latex, _ = prepare(piece) if piece.strip() else ("", "")
        if piece.strip() and latex is None:
            return None
        parts.append(latex or "")
    p_latex, n_latex, d_latex, s_latex = parts

    latex = f"{p_latex}\\frac{{{n_latex}}}{{{d_latex}}}{s_latex}".strip()
    checked, why = prepare(latex)
    if checked is None:
        return None
    text = f"{prefix}({num}) / ({den}){suffix}".strip()
    return text, checked
