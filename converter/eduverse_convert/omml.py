"""Office Math (OMML) to LaTeX. Covers the structures textbooks use: fractions, scripts, radicals, delimiters, n-ary, accents."""
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
SYM = {"π": r"\pi", "θ": r"\theta", "μ": r"\mu", "µ": r"\mu", "Δ": r"\Delta", "α": r"\alpha", "β": r"\beta", "λ": r"\lambda",
       "Ω": r"\Omega", "ω": r"\omega", "×": r"\times", "÷": r"\div", "°": r"^{\circ}", "∘": r"^{\circ}", "≈": r"\approx",
       "≤": r"\le", "≥": r"\ge", "±": r"\pm", "→": r"\rightarrow", "∞": r"\infty", "√": r"\sqrt{}", "–": "-", "−": "-"}


def _txt(s):
    out = []
    for ch in s:
        if ch in SYM:
            out.append(SYM[ch] + (" " if SYM[ch][-1].isalpha() else ""))
        elif ch in "{}_^#%&$":
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def _kids(el, name):
    c = el.find(M + name)
    return conv(c) if c is not None else ""


def conv(el):
    if el is None:
        return ""
    out = []
    for c in el:
        t = c.tag.replace(M, "")
        if t == "r":
            out.append(_txt("".join(x.text or "" for x in c.iter(M + "t"))))
        elif t == "f":
            out.append(r"\frac{%s}{%s}" % (_kids(c, "num"), _kids(c, "den")))
        elif t == "sSup":
            out.append("{%s}^{%s}" % (_kids(c, "e"), _kids(c, "sup")))
        elif t == "sSub":
            out.append("{%s}_{%s}" % (_kids(c, "e"), _kids(c, "sub")))
        elif t == "sSubSup":
            out.append("{%s}_{%s}^{%s}" % (_kids(c, "e"), _kids(c, "sub"), _kids(c, "sup")))
        elif t == "rad":
            deg = _kids(c, "deg")
            out.append((r"\sqrt[%s]{%s}" % (deg, _kids(c, "e"))) if deg else r"\sqrt{%s}" % _kids(c, "e"))
        elif t == "d":
            pr = c.find(M + "dPr")
            beg, end = "(", ")"
            if pr is not None:
                b, e = pr.find(M + "begChr"), pr.find(M + "endChr")
                beg = b.get(M + "val", "(") if b is not None else "("
                end = e.get(M + "val", ")") if e is not None else ")"
            inner = ",".join(conv(e) for e in c.findall(M + "e"))
            beg = {"{": r"\{", "|": "|", "[": "[", "": "."}.get(beg, beg); end = {"}": r"\}", "|": "|", "]": "]", "": "."}.get(end, end)
            out.append(r"\left%s %s \right%s" % (beg, inner, end))
        elif t == "nary":
            pr = c.find(M + "naryPr"); op = r"\sum"
            if pr is not None and pr.find(M + "chr") is not None:
                op = {"∫": r"\int", "∏": r"\prod", "∑": r"\sum"}.get(pr.find(M + "chr").get(M + "val"), r"\sum")
            out.append("%s_{%s}^{%s}{%s}" % (op, _kids(c, "sub"), _kids(c, "sup"), _kids(c, "e")))
        elif t == "acc":
            out.append(r"\vec{%s}" % _kids(c, "e"))
        elif t == "bar":
            out.append(r"\overline{%s}" % _kids(c, "e"))
        elif t in ("e", "num", "den", "oMath", "box", "borderBox", "func", "fName", "limLow", "limUpp", "eqArr", "m", "mr"):
            out.append(conv(c) + (r" \\ " if t == "e" and el.tag == M + "eqArr" else ""))
        elif t.endswith("Pr"):
            continue
        else:
            out.append(conv(c))
    return "".join(out)


import re as _re


def tidy(s: str) -> str:
    s = s.replace("^{^{\\circ}}", "^{\\circ}")
    for _ in range(3):  # linear fractions written as (a)/(b)
        s = _re.sub(r"\(([^()]{1,60})\)\s*/\s*\(([^()]{1,60})\)", r"\\frac{\1}{\2}", s)
    s = _re.sub(r"(?<![\\a-zA-Z{])([A-Za-z]{3,})", r"\\text{\1}", s)
    return s


def to_latex(omath_el) -> str:
    s = conv(omath_el).strip()
    return tidy(" ".join(s.split()))


def spaces_lost(omath_el) -> bool:
    """M1 sometimes writes an equation one letter per run with the spaces dropped ('Weknowthat')."""
    return bool(_re.search(r"[a-z]{9,}", plain(omath_el)))


def plain(omath_el) -> str:
    return "".join(x.text or "" for x in omath_el.iter(M + "t"))
