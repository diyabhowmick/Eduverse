"""LaTeX to OMML.

Word stores maths as OMML, not MathML. The usual route is LaTeX to MathML to
OMML through Microsoft's MML2OMML.XSL, which is not redistributable and not on
a Linux box. So this module builds OMML directly from LaTeX. Everything it
cannot parse raises Unsupported and the caller falls back to the cropped
image, per the rule that a picture of the right formula beats a typed wrong one.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple
from xml.sax.saxutils import escape

M = "http://schemas.openxmlformats.org/officeDocument/2006/math"


class Unsupported(Exception):
    pass


GREEK = {
    "alpha": "\u03b1", "beta": "\u03b2", "gamma": "\u03b3", "delta": "\u03b4",
    "epsilon": "\u03b5", "varepsilon": "\u03b5", "zeta": "\u03b6", "eta": "\u03b7",
    "theta": "\u03b8", "vartheta": "\u03d1", "iota": "\u03b9", "kappa": "\u03ba",
    "lambda": "\u03bb", "mu": "\u03bc", "nu": "\u03bd", "xi": "\u03be",
    "pi": "\u03c0", "rho": "\u03c1", "sigma": "\u03c3", "tau": "\u03c4",
    "upsilon": "\u03c5", "phi": "\u03c6", "varphi": "\u03d5", "chi": "\u03c7",
    "psi": "\u03c8", "omega": "\u03c9",
    "Gamma": "\u0393", "Delta": "\u0394", "Theta": "\u0398", "Lambda": "\u039b",
    "Xi": "\u039e", "Pi": "\u03a0", "Sigma": "\u03a3", "Upsilon": "\u03a5",
    "Phi": "\u03a6", "Psi": "\u03a8", "Omega": "\u03a9",
}

SYMBOLS = {
    "times": "\u00d7", "div": "\u00f7", "pm": "\u00b1", "mp": "\u2213",
    "cdot": "\u22c5", "ast": "\u2217", "star": "\u22c6",
    "leq": "\u2264", "le": "\u2264", "geq": "\u2265", "ge": "\u2265",
    "neq": "\u2260", "ne": "\u2260", "approx": "\u2248", "equiv": "\u2261",
    "sim": "\u223c", "propto": "\u221d", "infty": "\u221e",
    "rightarrow": "\u2192", "to": "\u2192", "leftarrow": "\u2190",
    "leftrightarrow": "\u2194", "Rightarrow": "\u21d2", "Leftarrow": "\u21d0",
    "uparrow": "\u2191", "downarrow": "\u2193",
    "partial": "\u2202", "nabla": "\u2207", "forall": "\u2200", "exists": "\u2203",
    "in": "\u2208", "notin": "\u2209", "subset": "\u2282", "supset": "\u2283",
    "cup": "\u222a", "cap": "\u2229", "emptyset": "\u2205",
    "degree": "\u00b0", "circ": "\u2218", "prime": "\u2032",
    "ldots": "\u2026", "cdots": "\u22ef", "dots": "\u2026",
    "angle": "\u2220", "triangle": "\u25b3", "perp": "\u22a5", "parallel": "\u2225",
    "therefore": "\u2234", "because": "\u2235", "sqrt": "\u221a",
    "%": "%", "&": "&", "$": "$", "#": "#", "_": "_", "{": "{", "}": "}",
    ",": "\u2009", ";": "\u2003", ":": "\u2005", " ": " ",
}

BIG_OPS = {
    "sum": "\u2211", "prod": "\u220f", "coprod": "\u2210",
    "int": "\u222b", "iint": "\u222c", "iiint": "\u222d", "oint": "\u222e",
    "bigcup": "\u22c3", "bigcap": "\u22c2", "lim": "lim",
}

FUNCS = ("sin", "cos", "tan", "cot", "sec", "csc", "log", "ln", "exp",
         "sinh", "cosh", "tanh", "arcsin", "arccos", "arctan", "max", "min",
         "det", "dim", "gcd", "deg")

ACCENTS = {"hat": "\u0302", "bar": "\u0304", "overline": "\u0304",
           "vec": "\u20d7", "tilde": "\u0303", "dot": "\u0307", "ddot": "\u0308"}

MATRIX_ENVS = {"matrix": ("", ""), "pmatrix": ("(", ")"),
               "bmatrix": ("[", "]"), "vmatrix": ("|", "|"),
               "Bmatrix": ("{", "}"), "cases": ("{", "")}

TEXT_CMDS = ("text", "textrm", "mathrm", "mbox", "operatorname", "mathbf",
             "textbf", "mathit", "textit")

_TOKEN_RE = re.compile(r"""
    (?P<cmd>\\[A-Za-z]+\*?)
  | (?P<esc>\\.)
  | (?P<open>\{)
  | (?P<close>\})
  | (?P<sup>\^)
  | (?P<sub>_)
  | (?P<amp>&)
  | (?P<nl>\\\\)
  | (?P<num>\d+(?:\.\d+)?)
  | (?P<sp>\s+)
  | (?P<ch>.)
""", re.X)


def tokenize(src: str) -> List[Tuple[str, str]]:
    src = src.replace("\\\\", "\x00NL\x00")
    out: List[Tuple[str, str]] = []
    i = 0
    while i < len(src):
        if src.startswith("\x00NL\x00", i):
            out.append(("nl", "\\\\"))
            i += 5
            continue
        m = _TOKEN_RE.match(src, i)
        if not m:
            i += 1
            continue
        kind = m.lastgroup
        val = m.group()
        i = m.end()
        if kind == "sp":
            continue
        out.append((kind, val))
    return out


# --------------------------------------------------------------------------
# XML helpers. Strings, not lxml, because they get injected into a paragraph.
# --------------------------------------------------------------------------

# Word only renders maths whose runs declare Cambria Math. Without this the
# oMath is well formed but invisible in Word and LibreOffice alike.
WRPR = ('<w:rPr><w:rFonts w:ascii="Cambria Math" w:hAnsi="Cambria Math" '
        'w:cs="Cambria Math"/></w:rPr>')
CTRL = f'<m:ctrlPr>{WRPR}</m:ctrlPr>'


def _t(text: str, sty: Optional[str] = None) -> str:
    rpr = ""
    if sty == "text":
        rpr = f'<m:rPr><m:nor/></m:rPr>{WRPR}'
    elif sty == "bold":
        rpr = f'<m:rPr><m:sty m:val="b"/></m:rPr>{WRPR}'
    else:
        rpr = WRPR
    return f'<m:r>{rpr}<m:t xml:space="preserve">{escape(text)}</m:t></m:r>'


def _e(tag: str, inner: str) -> str:
    return f"<m:{tag}>{inner}</m:{tag}>"


class Parser:
    def __init__(self, tokens: List[Tuple[str, str]]):
        self.tk = tokens
        self.i = 0

    def peek(self) -> Optional[Tuple[str, str]]:
        return self.tk[self.i] if self.i < len(self.tk) else None

    def next(self) -> Optional[Tuple[str, str]]:
        t = self.peek()
        if t is not None:
            self.i += 1
        return t

    # -- groups ----------------------------------------------------------
    def group(self) -> str:
        """Parse one argument: a braced group or a single atom."""
        t = self.peek()
        if t is None:
            return _t("")
        if t[0] == "open":
            self.next()
            return self.sequence(stop_on_close=True)
        return self.atom()

    def raw_group(self) -> str:
        """Argument as literal text, for \\text{...} and \\begin{...}."""
        t = self.peek()
        if t is None:
            return ""
        if t[0] != "open":
            self.next()
            return t[1]
        self.next()
        depth = 1
        buf = []
        while self.i < len(self.tk):
            k, v = self.tk[self.i]
            self.i += 1
            if k == "open":
                depth += 1
            elif k == "close":
                depth -= 1
                if depth == 0:
                    break
            buf.append(" " if k == "sp" else v)
        return "".join(buf)

    def optional(self) -> Optional[str]:
        """Parse a [..] optional argument if present."""
        t = self.peek()
        if t and t[0] == "ch" and t[1] == "[":
            self.next()
            buf = []
            while self.i < len(self.tk):
                k, v = self.tk[self.i]
                self.i += 1
                if k == "ch" and v == "]":
                    break
                buf.append(v)
            return "".join(buf)
        return None

    # -- main loop -------------------------------------------------------
    def sequence(self, stop_on_close: bool = False,
                 stop_on: Tuple[str, ...] = ()) -> str:
        out: List[str] = []
        while True:
            t = self.peek()
            if t is None:
                break
            if t[0] == "close":
                self.next()
                if stop_on_close:
                    break
                continue
            if t[0] == "cmd" and t[1][1:] in stop_on:
                break
            if t[0] in ("amp", "nl"):
                break
            out.append(self.script_wrapped())
        return "".join(out) or _t("")

    def script_wrapped(self) -> str:
        base = self.atom()
        sup = sub = None
        while True:
            t = self.peek()
            if t and t[0] == "sub" and sub is None:
                self.next()
                sub = self.group()
            elif t and t[0] == "sup" and sup is None:
                self.next()
                sup = self.group()
            else:
                break
        if sup is not None and sub is not None:
            return _e("sSubSup",
                      f'<m:sSubSupPr>{CTRL}</m:sSubSupPr>'
                      + _e("e", base) + _e("sub", sub) + _e("sup", sup))
        if sup is not None:
            return _e("sSup", f'<m:sSupPr>{CTRL}</m:sSupPr>'
                      + _e("e", base) + _e("sup", sup))
        if sub is not None:
            return _e("sSub", f'<m:sSubPr>{CTRL}</m:sSubPr>'
                      + _e("e", base) + _e("sub", sub))
        return base

    # -- atoms -----------------------------------------------------------
    def atom(self) -> str:
        t = self.next()
        if t is None:
            return _t("")
        kind, val = t
        if kind == "open":
            return self.sequence(stop_on_close=True)
        if kind in ("num", "ch"):
            return _t(val)
        if kind == "esc":
            return _t(SYMBOLS.get(val[1], val[1]))
        if kind == "cmd":
            return self.command(val[1:].rstrip("*"))
        if kind in ("sup", "sub"):
            # stray script, treat the character literally
            return _t(val)
        return _t(val)

    def command(self, name: str) -> str:
        if name in ("frac", "dfrac", "tfrac", "cfrac"):
            num, den = self.group(), self.group()
            return _e("f", f'<m:fPr>{CTRL}</m:fPr>'
                      + _e("num", num) + _e("den", den))
        if name == "binom":
            a, b = self.group(), self.group()
            return _e("d", '<m:dPr><m:begChr m:val="("/><m:endChr m:val=")"/></m:dPr>'
                      + _e("e", _e("f",
                                   '<m:fPr><m:type m:val="noBar"/></m:fPr>'
                                   + _e("num", a) + _e("den", b))))
        if name == "sqrt":
            deg = self.optional()
            body = self.group()
            if deg:
                dx = to_omml_inner(deg)
                return _e("rad", f'<m:radPr>{CTRL}</m:radPr>'
                          + _e("deg", dx) + _e("e", body))
            return _e("rad",
                      f'<m:radPr><m:degHide m:val="1"/>{CTRL}</m:radPr>'
                      + _e("deg", "") + _e("e", body))
        if name in BIG_OPS:
            return self.big_op(name)
        if name in ACCENTS:
            body = self.group()
            return _e("acc",
                      f'<m:accPr><m:chr m:val="{ACCENTS[name]}"/>{CTRL}</m:accPr>'
                      + _e("e", body))
        if name in TEXT_CMDS:
            raw = self.raw_group()
            sty = "bold" if name in ("mathbf", "textbf") else "text"
            return _t(raw, sty)
        if name in ("left", "right"):
            return self.delims(name)
        if name == "begin":
            return self.environment()
        if name == "end":
            self.raw_group()
            return ""
        if name in FUNCS:
            return _t(name, "text")
        if name in GREEK:
            return _t(GREEK[name])
        if name in SYMBOLS:
            return _t(SYMBOLS[name])
        if name in ("quad", "qquad", "!", "displaystyle", "limits",
                    "nolimits", "textstyle", "scriptstyle"):
            return _t(" " if name.startswith("q") else "")
        raise Unsupported(f"\\{name}")

    def big_op(self, name: str) -> str:
        chr_ = BIG_OPS[name]
        sub = sup = None
        while True:
            t = self.peek()
            if t and t[0] == "sub" and sub is None:
                self.next()
                sub = self.group()
            elif t and t[0] == "sup" and sup is None:
                self.next()
                sup = self.group()
            elif t and t[0] == "cmd" and t[1] in ("\\limits", "\\nolimits"):
                self.next()
            else:
                break
        body = self.script_wrapped() if self.peek() else _t("")
        op = _t(chr_, "text" if chr_ == "lim" else None)
        if sub is not None and sup is not None:
            pr = ('<m:naryPr><m:chr m:val="%s"/><m:limLoc m:val="undOvr"/>'
                  f'{CTRL}</m:naryPr>' % chr_)
            return _e("nary", pr + _e("sub", sub) + _e("sup", sup) + _e("e", body))
        if sub is not None:
            pr = ('<m:naryPr><m:chr m:val="%s"/><m:limLoc m:val="undOvr"/>'
                  f'<m:supHide m:val="1"/>{CTRL}</m:naryPr>' % chr_)
            return _e("nary", pr + _e("sub", sub) + _e("sup", "") + _e("e", body))
        pr = ('<m:naryPr><m:chr m:val="%s"/><m:subHide m:val="1"/>'
              f'<m:supHide m:val="1"/>{CTRL}</m:naryPr>' % chr_)
        return _e("nary", pr + _e("sub", "") + _e("sup", "") + _e("e", body))

    def delims(self, which: str) -> str:
        opener = self.next()
        if opener is None:
            return _t("")
        beg = _delim_char(opener[1])
        if which == "right":
            return _t(beg)
        body = self.sequence(stop_on=("right",))
        end = ")"
        t = self.peek()
        if t and t[0] == "cmd" and t[1] == "\\right":
            self.next()
            closer = self.next()
            if closer:
                end = _delim_char(closer[1])
        pr = (f'<m:dPr><m:begChr m:val="{escape(beg)}"/>'
              f'<m:endChr m:val="{escape(end)}"/>{CTRL}</m:dPr>')
        return _e("d", pr + _e("e", body))

    def environment(self) -> str:
        env = self.raw_group()
        if env not in MATRIX_ENVS:
            raise Unsupported(f"env {env}")
        beg, end = MATRIX_ENVS[env]
        rows: List[List[str]] = [[]]
        cur: List[str] = []
        while True:
            t = self.peek()
            if t is None:
                break
            if t[0] == "cmd" and t[1] == "\\end":
                self.next()
                self.raw_group()
                break
            if t[0] == "amp":
                self.next()
                rows[-1].append("".join(cur) or _t(""))
                cur = []
                continue
            if t[0] == "nl":
                self.next()
                rows[-1].append("".join(cur) or _t(""))
                cur = []
                rows.append([])
                continue
            cur.append(self.script_wrapped())
        if cur:
            rows[-1].append("".join(cur))
        rows = [r for r in rows if r]
        ncols = max((len(r) for r in rows), default=1)
        mcpr = ('<m:mPr><m:mcs><m:mc><m:mcPr>'
                f'<m:count m:val="{ncols}"/><m:mcJc m:val="center"/>'
                f'</m:mcPr></m:mc></m:mcs>{CTRL}</m:mPr>')
        body = mcpr
        for r in rows:
            cells = "".join(_e("e", c) for c in r)
            body += _e("mr", cells)
        matrix = _e("m", body)
        if beg or end:
            pr = (f'<m:dPr><m:begChr m:val="{escape(beg)}"/>'
                  f'<m:endChr m:val="{escape(end)}"/>{CTRL}</m:dPr>')
            return _e("d", pr + _e("e", matrix))
        return matrix


def _delim_char(tok: str) -> str:
    if tok.startswith("\\"):
        name = tok[1:]
        if name == ".":
            return ""
        return SYMBOLS.get(name, {"lbrace": "{", "rbrace": "}",
                                  "langle": "\u27e8", "rangle": "\u27e9",
                                  "lvert": "|", "rvert": "|"}.get(name, name))
    return tok


def to_omml_inner(latex: str) -> str:
    p = Parser(tokenize(latex))
    return p.sequence()


def latex_to_omml(latex: str, display: bool = False) -> str:
    """Return an <m:oMath> (or <m:oMathPara>) XML string.

    Raises Unsupported for anything the parser does not know.
    """
    latex = latex.strip()
    latex = re.sub(r"^\$\$?|\$\$?$", "", latex).strip()
    latex = re.sub(r"^\\\[|\\\]$", "", latex).strip()
    latex = re.sub(r"^\\\(|\\\)$", "", latex).strip()
    if not latex:
        raise Unsupported("empty")
    inner = to_omml_inner(latex)
    om = f'<m:oMath xmlns:m="{M}">{inner}</m:oMath>'
    if display:
        return (f'<m:oMathPara xmlns:m="{M}">'
                f'<m:oMathParaPr><m:jc m:val="center"/></m:oMathParaPr>'
                f'{om}</m:oMathPara>')
    return om


def can_convert(latex: str) -> bool:
    try:
        latex_to_omml(latex)
        return True
    except (Unsupported, RecursionError, IndexError, ValueError):
        return False
