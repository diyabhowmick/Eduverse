"""Question papers: read a file into text, split the text into questions, tag each question to a textbook chapter.

The splitter is rule based on purpose. A past paper is printed in a small number of layouts
("1." / "Q1." / "1)" numbering, "(a)" / "A." options, "Answer:" and "Solution:" lines, "Section A" headings),
and every question it produces goes to a reviewer before a student sees it."""
import io, os, re, subprocess, sys, tempfile
from collections import Counter
from pathlib import Path

Q_RE = re.compile(r"^\s*(?:Q(?:uestion)?\s*\.?\s*(\d{1,3})\s*[\.\):\-]?|(\d{1,3})\s*[\.\)])\s*(\S.*)?$", re.I)
OPT_RE = re.compile(r"^\s*(?:\(([a-dA-D1-4])\)|([a-dA-D])[\)\.])(?:\s+(\S.*))?$")
INLINE_OPT_RE = re.compile(r"\(([a-dA-D1-4])\)\s*")
KEY_HEAD_RE = re.compile(r"^\s*(?:answer\s*keys?|answers?|key)\s*:?\s*$", re.I)
KEY_RE = re.compile(r"(?<![\d.])(?:Q\s*)?(\d{1,3})\s*(?:[\.\):\-]\s*\(?(-?\d+(?:\.\d+)?|[a-dA-D])\)?|\s+\(?([a-dA-D])\)?)(?![A-Za-z0-9])")
ANS_RE = re.compile(r"^\s*(?:ans(?:wer)?|correct answer|key)\s*[:.\-]\s*(.*)$", re.I)
SOL_RE = re.compile(r"^\s*(?:sol(?:ution)?|explanation|hint)\s*[:.\-]\s*(.*)$", re.I)
SEC_RE = re.compile(r"^\s*(?:[A-Za-z&]+\s+){0,2}?(section|part)\s+([A-Z]|[IVX]+|\d+)\b.*$", re.I)
MARKS_RE = re.compile(r"[\[\(]\s*(\d+(?:\.\d+)?)\s*marks?\s*[\]\)]\s*$", re.I)


def read_text(name: str, data: bytes) -> str:
    n = name.lower()
    if n.endswith(".docx"):
        import docx
        d = docx.Document(io.BytesIO(data))
        lines = []
        for p in d.paragraphs:
            if (p.style.name or "").replace(" ", "") == "EVNote" and re.fullmatch(r"\s*Page\s+\d+\s*", p.text or ""):
                continue  # M1 page marker
            lines.append(p.text)
        for t in d.tables:
            for r in t.rows:
                lines.append("  ".join(c.text for c in r.cells))
        return "\n".join(lines)
    if n.endswith(".pdf"):
        import pymupdf
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            return "\n".join(pg.get_text() for pg in doc)
    return data.decode("utf-8", errors="replace")


def read_text_safe(name: str, data: bytes) -> str:
    """PDFs are read in a separate process, so a crash in the PDF library fails this upload and not the website."""
    if not name.lower().endswith(".pdf"):
        return read_text(name, data)
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "paper.pdf"
        f.write_bytes(data)
        r = subprocess.run([sys.executable, "-m", "app.paperread", str(f)], capture_output=True, timeout=180,
                           env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent.parent)})
    if r.returncode:
        raise ValueError("The PDF could not be opened. Check that it is a normal, unlocked PDF.")
    return r.stdout.decode("utf-8", errors="replace")


def parse_key(text: str) -> dict[str, str]:
    """'1. (a)  2-C  3 d  21. 35' -> {number: answer}."""
    return {m.group(1): (m.group(2) or m.group(3)).lower() for m in KEY_RE.finditer(text or "")}


def apply_key(rows: list[dict], key: dict[str, str]) -> int:
    """Fills answers from a key, by question number. Printed (1)-(4) keys are mapped onto the options' own keys."""
    n = 0
    for q in rows:
        a = key.get(str(q.get("number")))
        if not a:
            continue
        keys = [o["key"] for o in q.get("options") or []]
        if keys and a not in keys and a.isdigit() and 1 <= int(a) <= len(keys):
            a = keys[int(a) - 1]
        if keys and a not in keys:
            continue
        q["answer"], q["answer_source"] = a, "key"; n += 1
    return n


def _split_inline_options(text):
    """'Which is a metal? (a) Iron (b) Wood (c) Glass (d) Paper' -> stem plus four options."""
    parts = INLINE_OPT_RE.split(text)
    if len(parts) >= 5 and [p.lower() for p in parts[1::2][:2]] in (["a", "b"], ["1", "2"]):
        stem = parts[0].strip()
        opts = [{"key": parts[i].lower(), "text": parts[i + 1].strip()} for i in range(1, len(parts) - 1, 2)]
        return stem, opts
    return text, []


def split_questions(text: str) -> list[dict]:
    out, cur, section, mode, last_no, fresh = [], None, "", "q", 0, False
    lines = text.splitlines()
    key = {}

    def close():
        if cur and (cur["text"].strip() or cur["options"]):
            cur["text"] = re.sub(r"[ \t]+", " ", cur["text"]).strip()
            m = MARKS_RE.search(cur["text"])
            if m:
                cur["marks"] = float(m.group(1)); cur["text"] = cur["text"][:m.start()].strip()
            if not cur["options"]:
                cur["text"], cur["options"] = _split_inline_options(cur["text"])
            a = cur["answer"].strip()
            ma = re.match(r"^\(?([a-dA-D1-4])\)?(?:[\s.)]|$)", a)
            if cur["options"] and ma:
                cur["answer"] = ma.group(1).lower()
            cur["solution"] = cur["solution"].strip()
            cur["answer_source"] = "paper" if cur["answer"] else ""
            cur["qtype"] = "mcq" if cur["options"] else ""
            out.append(cur)

    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        if KEY_HEAD_RE.match(line):  # answer key printed after the questions
            key = parse_key("\n".join(lines[i + 1:]))
            break
        s = SEC_RE.match(line)
        if s and len(line) < 60:
            close(); cur = None; section = line; fresh = True; mode = "q"; continue
        q = Q_RE.match(line)
        # A number starts a new question only when it continues the count, allowing for a question or two the
        # text layer dropped, or restarts it after a section heading. A numbered step inside a solution is not
        # mistaken for the next question.
        no = int(q.group(1) or q.group(2)) if q else 0
        if q and (no == last_no + 1 or (fresh and no == 1) or (mode == "q" and last_no < no <= last_no + 3)):
            close()
            last_no, fresh = no, False
            cur = {"number": str(no), "section": section, "text": q.group(3) or "", "options": [], "answer": "", "solution": "", "marks": 0}
            mode = "q"; continue
        if cur is None:
            continue  # paper header: instructions, time, max marks
        a = ANS_RE.match(line)
        if a:
            cur["answer"] = a.group(1); mode = "a"; continue
        so = SOL_RE.match(line)
        if so:
            cur["solution"] = so.group(1); mode = "s"; continue
        o = OPT_RE.match(line) if mode == "q" else None
        if o:
            k = (o.group(1) or o.group(2)).lower()
            if k.isalpha() and cur["options"] and cur["options"][0]["key"].isdigit():
                # (1) (2) were numbered statements in the question, and these letters are the real options
                cur["text"] += " " + " ".join(f"({x['key']}) {x['text']}" for x in cur["options"]); cur["options"] = []
            cur["options"].append({"key": k, "text": (o.group(3) or "").strip()}); continue
        if mode == "s":
            cur["solution"] += "\n" + line
        elif mode == "a":
            cur["answer"] += " " + line
        elif cur["options"]:
            cur["options"][-1]["text"] += " " + line
        else:
            cur["text"] += " " + line
    close()
    apply_key(out, key)
    return out


# ---------------- chapter tagging ----------------
STOP = set("""a an the of to in on for and or is are was were be by with as at from that this which what why how when where
who whom whose it its into than then there their these those can could will would shall should may might do does did done
not no yes if any all each some more most less least very also only one two three four five find give state explain write
define describe show prove calculate following given value answer question marks figure diagram""".split())


def tokens(s):
    return [w for w in re.findall(r"[a-z][a-z\-]{2,}", (s or "").lower()) if w not in STOP]


def chapter_index(books_data: list[tuple[int, dict]]):
    """[(book_id, book.json)] -> [(book_id, chapter number, chapter title, Counter of weighted terms)]"""
    idx = []
    for bid, data in books_data:
        for ch in data.get("chapters", []):
            c = Counter()
            for w in tokens(ch.get("title", "")):
                c[w] += 4
            for s in ch.get("sections", []):
                for w in tokens(s.get("title", "")):
                    c[w] += 3
            for k in ch.get("keywords", []):
                for w in tokens(k.get("term", "")):
                    c[w] += 2
            idx.append((bid, ch.get("number"), ch.get("title", ""), c))
    return idx


def tag(question_text: str, idx) -> dict | None:
    words = Counter(tokens(question_text))
    best, score = None, 0
    for bid, num, title, c in idx:
        s = sum(c[w] * min(n, 2) for w, n in words.items() if w in c)
        if s > score:
            best, score = (bid, num, title), s
    if not best or score < 3:
        return None
    return {"book_id": best[0], "chapter": best[1], "title": best[2], "score": score}
