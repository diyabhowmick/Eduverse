"""Cleans what the AI paper reader returns, so a question shows on screen the way it is printed.

Every function here is pure text in, text out, so it can be tested without a database or a model.

- clean():         maths stays in $ signs, plain sentences stay plain, a table stays one block.
- drop_echoed_options(): the model sometimes copies the options into the question text as well.
- question_number(): "Q.7", "7.", "(7)" are all question 7.
"""
import re
from difflib import SequenceMatcher

# JSON reads "\f", "\b", "\t", "\r", "\n" as control characters, so a LaTeX \frac, \beta, \times, \rho or \nu whose
# backslash was not doubled arrives as a control character followed by the rest of the command.
_LOST = [("\x0c", "\\f"), ("\x08", "\\b")]
_CR_CMD = re.compile(r"\r(?=(?:ho|ight|ightarrow|angle|m|ceil|floor|Rightarrow)(?![a-z]))")
_TAB_CMD = re.compile(r"\t(?=(?:ext|extbf|extit|extrm|imes|heta|au|an|ilde|o|op|riangle|hinspace)(?![a-z]))")
# Only commands no line of ordinary text starts with. A real line break before "i) Hg2+" must stay a line break,
# never become \ni (drawn as ∋); \nu counts only when maths follows it at once (\nu_0, \nu^2, \nu}).
_NL_CMD = re.compile(r"\n(?=(?:eq|abla|leq|geq|parallel|mid|exists|subseteq|supseteq|ewarrow|earrow)(?![a-z])|u(?=[_^{}$]))")

# A whole table: \begin{array}...\end{array} and friends, possibly over several lines.
_ENV = re.compile(r"\\begin\{(array|tabular|matrix|pmatrix|bmatrix|vmatrix|cases|aligned|align\*?)\}[\s\S]*?\\end\{\1\}")
# Text already in maths: $$...$$ or $...$ (a single $ block may run over lines when it holds a table).
_MATH = re.compile(r"\$\$[\s\S]+?\$\$|\$(?:[^$\\]|\\[\s\S])+?\$")
# Formatting that only means "print this word in italics / bold" and has no place in plain text.
_FORMAT = re.compile(r"\\(?:textit|textbf|textrm|textsf|texttt|emph|text|mathrm|mathit|mathbf|underline|uline)\s*\{([^{}]*)\}")
_ESCAPED = re.compile(r"\\([%&#_$])")
_SPACING = re.compile(r"\\[,;:! ](?![A-Za-z])|~")
_MD_ROW = re.compile(r"^\s*\|.*\|\s*$")
_MD_RULE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def _restore_escapes(text: str) -> str:
    for bad, good in _LOST:
        text = text.replace(bad, good)
    text = _CR_CMD.sub(r"\\r", text).replace("\r\n", "\n").replace("\r", "\n")
    text = _TAB_CMD.sub(r"\\t", text)
    text = text.replace("\n" + "ewline", "\n")
    return _NL_CMD.sub(r"\\n", text)


def _tex_text(s: str) -> str:
    """Plain words for inside \\text{...}."""
    s = s.replace("\\", "\\textbackslash ")
    return re.sub(r"([{}&%#_$^])", r"\\\1", s).replace("\\^", "\\hat{}")


def _md_cell(c: str) -> str:
    c = c.strip()
    if not c:
        return ""
    # A cell may mix words and $maths$: words go in \text, maths stays maths.
    out = []
    for part in re.split(r"(\$[^$]+\$)", c):
        if part.startswith("$") and part.endswith("$") and len(part) > 2:
            out.append(part[1:-1])
        elif part:
            out.append("\\text{" + _tex_text(part) + "}")
    return " ".join(out)


def _markdown_tables(text: str) -> str:
    """A table written as | a | b | rows becomes a LaTeX array, the one table form the screen draws."""
    lines, out, i = text.split("\n"), [], 0
    while i < len(lines):
        j = i
        while j < len(lines) and (_MD_ROW.match(lines[j]) or (j > i and _MD_RULE.match(lines[j]))):
            j += 1
        block = [l for l in lines[i:j] if not _MD_RULE.match(l)]
        if j - i >= 2 and len(block) >= 2:
            rows = [[c for c in l.strip().strip("|").split("|")] for l in block]
            n = max(len(r) for r in rows)
            body = " \\\\ \\hline\n".join(" & ".join(_md_cell(c) for c in r + [""] * (n - len(r))) for r in rows)
            out.append("$$\\begin{array}{|" + "l|" * n + "}\n\\hline\n" + body + " \\\\ \\hline\n\\end{array}$$")
            i = j
        else:
            out.append(lines[i]); i += 1
    return "\n".join(out)


def _strong(tok: str) -> bool:
    """A chunk that can only be maths: a LaTeX command, a power or a subscript (a ____ blank is not one)."""
    t = re.sub(r"_{2,}", "", tok)
    return bool(re.search(r"\\[A-Za-z]+|\^|_(?=[{A-Za-z0-9])", t))


def _joiner(tok: str) -> bool:
    """A chunk that may sit inside a formula between two maths chunks: a number, an operator, one letter, each possibly
    followed by a comma, as in (2, \\frac{7}{2}, 6)."""
    return bool(re.fullmatch(r"(?:[=+\-*/<>(),.\[\]|:]+|[(\[]?-?\d+(?:\.\d+)?|[(\[]?[A-Za-z]|\\[A-Za-z]+)[,;)\]]*", tok))


_LEAD = re.compile(r"[=+\-*/<>(\[|:]+|-?\d+(?:\.\d+)?|[A-Za-z]")
_RELATION = re.compile(r"(?:^|[^A-Za-z])(?:[=<>+\-]|\\(?:in|notin|ni|subset|subseteq|supset|supseteq|le|leq|ge|geq|ne|neq|approx|equiv|sim|simeq|"
                       r"propto|to|rightarrow|Rightarrow|leftarrow|cdot|times|div|pm|mp|cup|cap|setminus|mid|parallel|perp))$")


def _unbalanced(formula: str) -> bool:
    """\\left without its \\right, or an open brace: cutting the formula here would leave something KaTeX cannot draw."""
    return len(re.findall(r"\\left(?![a-z])", formula)) > len(re.findall(r"\\right(?![a-z])", formula)) \
        or formula.count("{") > formula.count("}")


def _chunks(line: str) -> list[str]:
    """Splits on spaces, but never inside braces, so \\frac{a + b}{c} stays one chunk."""
    out, cur, depth = [], "", 0
    for ch in line:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        if ch == " " and depth == 0:
            out.append(cur); cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def _wrap_bare_maths(line: str) -> str:
    """'then \\frac{E}{G} has the dimensions' -> 'then $\\frac{E}{G}$ has the dimensions'. Only formulas get $ signs."""
    if not re.search(r"\\[A-Za-z]|\^|_[{A-Za-z0-9]", line):
        return line
    toks = _chunks(line)
    n = len(toks)
    strong = [bool(t) and _strong(t) for t in toks]
    join = [bool(t) and _joiner(t) and t not in ("a", "I") for t in toks]
    out, i = [], 0
    while i < n:
        if not strong[i]:
            out.append(toks[i]); i += 1; continue
        a = i
        # Backwards only over plain operands and operators ("x =" before \frac), never a list mark such as "i)".
        while a > 0 and _LEAD.fullmatch(toks[a - 1] or "") and toks[a - 1] not in ("a", "I") and len(out) and out[-1] == toks[a - 1]:
            a -= 1; out.pop()
        b, j = i, i + 1
        while j < n:
            if strong[j]:
                b = j; j += 1
            elif join[j]:
                k = j
                while k < n and join[k] and not strong[k]:
                    k += 1
                if k < n and strong[k]:
                    b, j = k, k + 1
                else:
                    break
            else:
                break
        # A formula ending in a relation or operator takes its right-hand side: "\in S", "= 5", "+ c".
        while b + 1 < n and _RELATION.search(toks[b]) and toks[b + 1] and join[b + 1]:
            b += 1
        # Never stop inside \left ... \right: take words up to the matching \right.
        while _unbalanced(" ".join(toks[a:b + 1])) and b + 1 < n:
            b += 1
        formula = " ".join(toks[a:b + 1])
        tail = re.search(r"[.,;:?!]+$", formula)
        tail = tail.group() if tail else ""
        if tail:
            formula = formula[:-len(tail)]
        out.append(f"${formula}${tail}")
        i = b + 1
    return " ".join(out)


def _plain(seg: str) -> str:
    """Text outside $ signs: tables become display blocks, word formatting goes, real formulas get $ signs."""
    parts, last = [], 0
    for m in _ENV.finditer(seg):
        parts.append(("t", seg[last:m.start()])); parts.append(("m", "$$" + m.group().strip() + "$$")); last = m.end()
    parts.append(("t", seg[last:]))
    out = []
    for kind, s in parts:
        if kind == "m" or s.startswith("$$"):
            out.append(s); continue
        # Pieces already turned into $$tables$$ by _markdown_tables must not be touched again.
        sub = []
        for piece in re.split(r"(\$\$[\s\S]+?\$\$)", s):
            if piece.startswith("$$"):
                sub.append(piece); continue
            for _ in range(3):  # nested \textbf{\textit{word}}
                piece = _FORMAT.sub(r"\1", piece)
            piece = _ESCAPED.sub(r"\1", piece)
            piece = _SPACING.sub(" ", piece)
            piece = "\n".join(_wrap_bare_maths(l) for l in piece.split("\n"))
            sub.append(piece)
        out.append("".join(sub))
    return "".join(out)


def is_prose(inner: str) -> bool:
    """Maths that is really a sentence: italic formatting, or several ordinary words in a row.
    KaTeX would draw it with no spaces, as in 'GeneralikeSelaginella...'."""
    if "\\begin{" in inner:
        return False
    if re.search(r"\\(?:textit|emph|textbf)\{", inner):
        return True
    bare = re.sub(r"\\[A-Za-z]+\s*(\{[^{}]*\})?", " ", inner)
    return len(re.findall(r"(?<![\\A-Za-z])[A-Za-z]{4,}(?![A-Za-z])", bare)) >= 4


# Text saved before this module existed cut a table into one $...$ per line: $\begin{array}{|c|c|}$ / $row \\$ / $\end{array}$
_LEGACY_TABLE = re.compile(r"(^|[^$])\$\\begin\{(array|tabular)\}([\s\S]*?)\\end\{\2\}\$(?!\$)")


def _join_legacy_table(m):
    pre, env, inner = m.group(1), m.group(2), m.group(3)
    if "$" not in inner:
        return m.group()
    return f"{pre}$$\\begin{{{env}}}{inner.replace('$', '')}\\end{{{env}}}$$"


# LaTeX's own display and inline markers, \[ ... \] and \( ... \). The screen only knows $$ and $. A row break with
# spacing, \\[4pt], is not a marker: the [ follows two backslashes.
_LONE_MARK = re.compile(r"\$[ \t]*\\[\[\]()][ \t]*\$[ \t]*\n?")                # $\[$ left by the old per-line code
_DISPLAY_MARK = re.compile(r"(?<!\\)\\\[([\s\S]*?)(?:(?<!\\)|(?<=\\\\))\\\]")
_INLINE_MARK = re.compile(r"(?<!\\)\\\(([\s\S]*?)(?:(?<!\\)|(?<=\\\\))\\\)")
_STRAY_MARK = re.compile(r"(?m)^[ \t]*\\[\[\]][ \t]*\n?")                    # a marker whose partner was lost


def _markers(text: str) -> str:
    text = _LONE_MARK.sub("", text)
    # Already inside $ signs (a table the code wrapped earlier): only the markers go.
    text = _DISPLAY_MARK.sub(lambda m: m.group(1).strip() if "$" in m.group(1) else "$$" + m.group(1).strip() + "$$", text)
    text = _INLINE_MARK.sub(lambda m: m.group(1) if "$" in m.group(1) else "$" + m.group(1).strip() + "$", text)
    return _STRAY_MARK.sub("", text)


def clean(text) -> str:
    """Model output -> text the screen can draw. Idempotent: cleaning clean text changes nothing."""
    text = str(text or "")
    text = _LEGACY_TABLE.sub(_join_legacy_table, text)
    text = _markers(text)
    text = re.sub(r"<br\s*/?>|</br>", "\n", text, flags=re.I)
    text = _restore_escapes(text).replace("\\newline", "\n")
    text = _markdown_tables(text)  # before the $ split, so a cell holding $maths$ does not break the table apart
    out, last = [], 0
    for m in _MATH.finditer(text):
        out.append(_plain(text[last:m.start()]))
        block = m.group()
        if not block.startswith("$$") and is_prose(block[1:-1]):
            out.append(_plain(block[1:-1])); last = m.end(); continue  # a sentence wrongly put in maths
        if not block.startswith("$$") and "\\begin{" in block:
            block = "$" + block + "$"  # a table is its own block, not a word in the sentence
        out.append(block); last = m.end()
    out.append(_plain(text[last:]))
    text = "".join(out)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ---------------- options copied into the question ----------------
_MARK = r"(?:\(\s*[a-dA-D1-4]\s*\)|(?<![A-Za-z0-9])[a-dA-D1-4]\s*[.)])"
_MARK_RE = re.compile(_MARK)


def _norm(s: str) -> str:
    s = re.sub(r"\\(?:text|mathrm|textit|textbf)\s*", "", s)
    s = _MARK_RE.sub(" ", s)
    return re.sub(r"[^a-z0-9]", "", s.lower())


def strip_option_mark(key: str, text: str) -> str:
    """'a. Heterosorus' as option a's text -> 'Heterosorus'."""
    m = re.match(r"^\s*\(?\s*([a-dA-D1-4])\s*[.)]\s*", text)
    if m and m.group(1).lower() in (key.lower(), str("abcd".find(key.lower()) + 1)):
        return text[m.end():]
    return text


def drop_echoed_options(text: str, options: list[dict]) -> str:
    """When the question text ends with the same options the list already holds, the copy in the text goes.
    Statements A. B. C. D. inside the question stay, because they do not match the options' wording."""
    if len(options) < 2 or not text:
        return text
    want = _norm(" ".join(o.get("text", "") for o in options))
    if len(want) < 2:
        return text
    first = options[0].get("key", "a").lower()
    starts = [m.start() for m in re.finditer(r"(?:^|(?<=[\s:?.$]))(?:\(\s*[" + first + first.upper() + r"1]\s*\)|[" + first + first.upper() + r"1]\s*[.)])", text)]
    for p in reversed(starts):
        tail = text[p:]
        got = _norm(tail)
        if got == want or (len(want) >= 8 and SequenceMatcher(None, got, want).ratio() >= .85):
            # Also drop a "$$ ... $$" table holding only the options, whose $$ opener sits just before the mark.
            head = re.sub(r"\$\$\s*\\begin\{[^}]*\}(?:\{[^}]*\})?[\s\\hline]*$", "", text[:p]).rstrip()
            return head
    return text


def similar(a: str, b: str) -> bool:
    """The same question read twice (once at the foot of a page, once at the top of the next)."""
    a, b = _norm(a)[:300], _norm(b)[:300]
    if not a or not b:
        return True  # an empty half is a fragment of the other
    short, long_ = sorted((a, b), key=len)
    return short in long_ or SequenceMatcher(None, a, b).ratio() >= .6


# ---------------- figure markers ----------------
_FIG_ANY = re.compile(r"\[\[\s*fig(?:ure)?\s*[:#]?\s*(\d+)\s*\]\]|\[\s*fig(?:ure)?\s*[:#]?\s*(\d+)\s*\]", re.I)


def fig_markers(text: str, count: int | None = None, offset: int = 0) -> str:
    """[[figure 1]], [fig:1] -> [[fig:1]], each on its own line. offset renumbers (a question carried over a page break
    numbers its figures on from the first page's); a marker for a figure that does not exist (beyond count) goes."""
    def one(m):
        n = int(m.group(1) or m.group(2)) + offset
        return f"\n[[fig:{n}]]\n" if count is None or 1 <= n <= count + offset else "\n"
    text = _FIG_ANY.sub(one, text)
    text = re.sub(r"\s*\n\s*(\[\[fig:\d+\]\])\s*\n\s*", r"\n\1\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# Code a screen cannot draw: a structure or picture written as LaTeX packages KaTeX does not have.
UNDRAWABLE = re.compile(r"\\(?:chemfig|schemestart|setatomsep|includegraphics|tikz|begin\{tikzpicture\}|ch\{|lewis)")


# ---------------- question numbers ----------------
def question_number(raw) -> str:
    """'Q.7', 'Q 7', '7.', '(7)', 'Question 7' -> '7'. '12A' keeps its letter. Anything else is kept as printed."""
    s = str(raw or "").strip()
    m = re.match(r"^\(?\s*(?:Q(?:uestion|ues|n)?|No)?\s*\.?\s*(\d{1,4})\s*([A-Za-z]?)\s*[.):\-]?\s*$", s, re.I)
    if m:
        return m.group(1) + m.group(2)
    return s.strip(" .):")[:20]
