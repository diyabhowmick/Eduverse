"""Detect maths in extracted text, normalise it to LaTeX, validate it.

The rule that matters: never publish a wrong formula. If validation fails the
block is marked math_unreadable and the writer emits the cropped image instead.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from .omml import can_convert, GREEK, SYMBOLS

# $..$, $$..$$, \(..\), \[..\]
INLINE_RE = re.compile(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)", re.S)
DISPLAY_RE = re.compile(r"\$\$(.+?)\$\$", re.S)
PAREN_RE = re.compile(r"\\\((.+?)\\\)", re.S)
BRACK_RE = re.compile(r"\\\[(.+?)\\\]", re.S)

# A line of plain text that is really a formula: mostly symbols and few words.
MATHY = re.compile(r"[=+\u2212\u00d7\u00f7\u2264\u2265\u2260\u221a\u222b\u2211\u03c0]")
SUBSUP = re.compile(r"[\u2070-\u209f\u00b2\u00b3\u00b9]")

# H2SO4 style chemistry, which must NOT go through the equation path
CHEM_RE = re.compile(r"\b(?:[A-Z][a-z]?\d*){2,}\b")

SUP_MAP = {"\u2070": "0", "\u00b9": "1", "\u00b2": "2", "\u00b3": "3",
           "\u2074": "4", "\u2075": "5", "\u2076": "6", "\u2077": "7",
           "\u2078": "8", "\u2079": "9", "\u207a": "+", "\u207b": "-",
           "\u207f": "n"}
SUB_MAP = {"\u2080": "0", "\u2081": "1", "\u2082": "2", "\u2083": "3",
           "\u2084": "4", "\u2085": "5", "\u2086": "6", "\u2087": "7",
           "\u2088": "8", "\u2089": "9", "\u208a": "+", "\u208b": "-"}
UNI_TO_TEX = {v: "\\" + k for k, v in {**GREEK}.items()}
UNI_TO_TEX.update({"\u00d7": "\\times", "\u00f7": "\\div", "\u00b1": "\\pm",
                   "\u2264": "\\leq", "\u2265": "\\geq", "\u2260": "\\neq",
                   "\u2248": "\\approx", "\u221e": "\\infty",
                   "\u2192": "\\rightarrow", "\u2211": "\\sum",
                   "\u222b": "\\int", "\u221a": "\\sqrt",
                   "\u2220": "\\angle", "\u00b0": "^\\circ"})


def find_math_spans(text: str) -> List[Tuple[int, int, str, bool]]:
    """Return (start, end, latex, is_display) for every delimited formula."""
    spans: List[Tuple[int, int, str, bool]] = []
    for rx, disp in ((DISPLAY_RE, True), (BRACK_RE, True),
                     (PAREN_RE, False), (INLINE_RE, False)):
        for m in rx.finditer(text):
            if any(s <= m.start() < e for s, e, _, _ in spans):
                continue
            spans.append((m.start(), m.end(), m.group(1).strip(), disp))
    spans.sort(key=lambda s: s[0])
    return spans


def looks_like_formula(text: str) -> bool:
    """A whole undelimited line that is really a display formula."""
    t = text.strip()
    if len(t) < 2 or len(t) > 160:
        return False
    words = [w for w in re.findall(r"[A-Za-z]{4,}", t)]
    if len(words) > 3:
        return False
    if not (MATHY.search(t) or SUBSUP.search(t)):
        return False
    if CHEM_RE.search(t) and "=" not in t:
        return False
    symbols = sum(1 for c in t if not c.isalnum() and not c.isspace())
    return symbols >= 1 and (symbols / max(len(t), 1)) > 0.05


def unicode_to_latex(text: str) -> str:
    """Turn a printed formula line into LaTeX. Conservative on purpose."""
    out: List[str] = []
    i = 0
    while i < len(text):
        c = text[i]
        if c in SUP_MAP:
            run = ""
            while i < len(text) and text[i] in SUP_MAP:
                run += SUP_MAP[text[i]]
                i += 1
            out.append("^{" + run + "}")
            continue
        if c in SUB_MAP:
            run = ""
            while i < len(text) and text[i] in SUB_MAP:
                run += SUB_MAP[text[i]]
                i += 1
            out.append("_{" + run + "}")
            continue
        tex = UNI_TO_TEX.get(c)
        if tex is not None:
            out.append(tex)
            # A LaTeX command runs on into whatever follows it, so a delta
            # printed beside a T becomes \DeltaT, which is not a command at
            # all and fails validation. One space closes the name. This is
            # what sent every temperature formula in the book to the VLM.
            nxt = text[i + 1] if i + 1 < len(text) else ""
            if tex[-1:].isalpha() and (nxt.isalpha() or nxt in "\\"):
                out.append(" ")
        else:
            out.append(c)
        i += 1
    return "".join(out)


def validate(latex: str) -> Tuple[bool, str]:
    """Structural checks before we trust a formula."""
    if not latex or not latex.strip():
        return False, "empty"
    if latex.count("{") != latex.count("}"):
        return False, "brace imbalance"
    if latex.count("\\left") != latex.count("\\right"):
        return False, "left right mismatch"
    begins = re.findall(r"\\begin\{(\w+\*?)\}", latex)
    ends = re.findall(r"\\end\{(\w+\*?)\}", latex)
    if sorted(begins) != sorted(ends):
        return False, "environment not closed"
    if re.search(r"[\ufffd\u0000-\u0008]", latex):
        return False, "broken characters"
    if re.search(r"\\[A-Za-z]+\s*\{\s*\}", latex):
        return False, "empty argument"
    if not can_convert(latex):
        return False, "unsupported command"
    return True, ""


def prepare(latex: str) -> Tuple[Optional[str], str]:
    """Normalise then validate. Returns (latex or None, reason)."""
    cleaned = latex.strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if re.search(r"[\u2070-\u209f\u00b2\u00b3\u00b9]", cleaned) or \
            any(ch in UNI_TO_TEX for ch in cleaned):
        cleaned = unicode_to_latex(cleaned)
    ok, why = validate(cleaned)
    return (cleaned, "") if ok else (None, why)


def is_chemistry(text: str) -> bool:
    """Chemistry goes through sub and superscript runs, not the equation path."""
    t = text.strip()
    if "=" in t or "\\frac" in t:
        return False
    return bool(CHEM_RE.search(t)) and not MATHY.search(t)


def split_chem_runs(text: str):
    """Yield (chunk, kind) with kind in plain|sub|sup for a chemical formula."""
    out = []
    for ch in text:
        if ch in SUB_MAP:
            out.append((SUB_MAP[ch], "sub"))
        elif ch in SUP_MAP:
            out.append((SUP_MAP[ch], "sup"))
        elif ch.isdigit() and out and out[-1][1] == "plain" and \
                out[-1][0][-1:].isalpha():
            out.append((ch, "sub"))
        else:
            if out and out[-1][1] == "plain":
                out[-1] = (out[-1][0] + ch, "plain")
            else:
                out.append((ch, "plain"))
    merged = []
    for chunk, kind in out:
        if merged and merged[-1][1] == kind:
            merged[-1] = (merged[-1][0] + chunk, kind)
        else:
            merged.append((chunk, kind))
    return merged


# ---------------------------------------------------------------------------
# Reading a formula out in words
# ---------------------------------------------------------------------------

_SPOKEN = {
    "+": "plus", "-": "minus", "\u2212": "minus", "=": "equals",
    "<": "is less than", ">": "is greater than", "/": "divided by",
    "\\times": "times", "\\div": "divided by", "\\pm": "plus or minus",
    "\\cdot": "times", "\\leq": "is less than or equal to",
    "\\geq": "is greater than or equal to", "\\neq": "is not equal to",
    "\\approx": "is approximately", "\\propto": "is proportional to",
    "\\infty": "infinity", "\\rightarrow": "gives", "\\to": "gives",
    "\\partial": "partial", "\\circ": "degrees",
}

_GREEK_SPOKEN = {k: k for k in GREEK}


def speak(latex: str) -> str:
    """A plain reading of a formula, so the box says what the symbols say.

    This is deterministic and offline: the LaTeX is already the exact recipe
    for a replica, and this is the sentence a person or a model reads instead
    of parsing it.
    """
    if not latex:
        return ""
    t = latex.strip()
    t = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}",
               lambda m: f"({speak(m.group(1))}) divided by ({speak(m.group(2))})", t)
    t = re.sub(r"\\sqrt\[([^\]]*)\]\{([^{}]*)\}",
               lambda m: f"the {speak(m.group(1))} root of ({speak(m.group(2))})", t)
    t = re.sub(r"\\sqrt\{([^{}]*)\}",
               lambda m: f"the square root of ({speak(m.group(1))})", t)
    t = re.sub(r"\\sum_\{([^{}]*)\}\^\{([^{}]*)\}",
               lambda m: f"the sum from {speak(m.group(1))} to {speak(m.group(2))} of", t)
    t = re.sub(r"\\int_\{([^{}]*)\}\^\{([^{}]*)\}",
               lambda m: f"the integral from {speak(m.group(1))} to {speak(m.group(2))} of", t)
    t = re.sub(r"\^\{([^{}]*)\}", lambda m: _power(m.group(1)), t)
    t = re.sub(r"\^(\w)", lambda m: _power(m.group(1)), t)
    t = re.sub(r"_\{([^{}]*)\}", lambda m: f" sub {speak(m.group(1))}", t)
    t = re.sub(r"_(\w)", lambda m: f" sub {m.group(1)}", t)
    for cmd in sorted(_SPOKEN, key=len, reverse=True):
        t = t.replace(cmd, f" {_SPOKEN[cmd]} ")
    for name in sorted(GREEK, key=len, reverse=True):
        t = t.replace("\\" + name, f" {name} ")
    t = re.sub(r"\\text\{([^{}]*)\}", r"\1", t)
    t = t.replace("{", " ").replace("}", " ").replace("\\", " ")
    return re.sub(r"\s+", " ", t).strip()


def _power(exp: str) -> str:
    e = exp.strip()
    if e == "2":
        return " squared"
    if e == "3":
        return " cubed"
    if e in ("\\circ", "circ"):
        return " degrees"
    return f" to the power {speak(e)}"
