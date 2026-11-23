"""Chapter tests: questions written from a textbook's own words and figures.

Two writers:
  rules  - always available, no AI: fill-in-the-blank and meaning questions from the book's
           highlighted words, and figure questions from figure captions and descriptions.
  ai     - the configured model writes a fuller set; every question must quote a sentence that
           really is in the chapter, or it is dropped, so nothing is made up.
A reviewer approves each question before any student sees it.
"""
import json, os, random, re

LETTERS = "abcd"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", re.sub(r"\s+", " ", (s or "").lower())).strip()


def _strip(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def walk(blocks):
    for b in blocks:
        yield b
        if b.get("type") == "box":
            yield from walk(b.get("children") or [])


def section_titles(ch) -> dict:
    return {s["id"]: ((s.get("number") or "") + " " + (s.get("title") or "")).strip() for s in ch.get("sections", [])}


def sentences(ch):
    """(sentence, section id) for every sentence of running text in the chapter."""
    out = []
    for b in walk(ch.get("blocks", [])):
        texts = [b.get("text", "")] if b.get("type") == "paragraph" else [i.get("text", "") for i in b.get("items", [])] if b.get("type") == "list" else []
        for t in texts:
            for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", _strip(t)):
                if len(s.split()) >= 5:
                    out.append((s, b.get("section", "")))
    return out


def terms_pool(chapters):
    """Short headings and bold words of the book: believable wrong options for a fill-in-the-blank."""
    out = []
    for c in chapters:
        for b in walk(c.get("blocks", [])):
            if b.get("type") == "heading" and 1 <= len((b.get("text") or "").split()) <= 3:
                out.append(b["text"].strip().lower())
            out += [t.strip().lower() for t in (b.get("bold") or []) if isinstance(t, str) and 1 <= len(t.split()) <= 3]
    generic = {"introduction", "summary", "exercise", "exercises", "activity", "further reading", "glossary", "references", "evaluation",
               "points to remember", "let us learn", "do you know", "more to know", "units and symbols", "conclusion", "answers"}
    seen, uniq = set(), []
    for t in out:
        if _norm(t) not in seen and _norm(t) not in generic:
            seen.add(_norm(t)); uniq.append(t)
    return uniq


def figures(ch):
    return [b for b in walk(ch.get("blocks", [])) if b.get("type") == "figure" and (b.get("caption") or (b.get("desc") or {}).get("summary"))]


def _opts(rng, right, wrong):
    pool = [right] + wrong[:3]
    rng.shuffle(pool)
    return [{"key": LETTERS[i], "text": t} for i, t in enumerate(pool)], LETTERS[pool.index(right)]


def rules(data: dict, chapter_no: int, seed: int = 7) -> list[dict]:
    rng = random.Random(seed * 1000 + chapter_no)
    chapters = data["chapters"]
    ch = next(c for c in chapters if c["number"] == chapter_no)
    titles = section_titles(ch)
    sents = sentences(ch)
    all_kw = [k for c in chapters for k in c.get("keywords", [])]
    out = []

    for k in ch.get("keywords", []):
        term = k["term"]
        pat = re.compile(r"\b" + re.escape(term) + r"\b", re.I)
        # Prefer the sentence that defines the word, then any sentence that uses it.
        cands = [(s, sec) for s, sec in sents if pat.search(s)]
        cands.sort(key=lambda x: (_norm(k.get("definition", "")) not in _norm(x[0]) and _norm(x[0]) not in _norm(k.get("definition", "")), len(x[0])))
        if not cands:
            continue
        s, sec = cands[0]
        blank = pat.sub("______", s, count=1)
        others = [x["term"] for x in all_kw if _norm(x["term"]) != _norm(term)]
        others += [t for t in terms_pool(chapters) if _norm(t) != _norm(term) and _norm(t) not in map(_norm, others) and _norm(t) not in _norm(s)]
        rng.shuffle(others)
        q = {"section": sec, "section_title": titles.get(sec, ""), "source": s, "level": "easy",
             "explanation": k.get("definition") or s, "text": "Fill in the blank: " + blank}
        if len(others) >= 3:
            q["options"], q["answer"] = _opts(rng, term, others)
            q["qtype"] = "mcq"
        else:
            q["qtype"], q["options"], q["answer"] = "fill", [], term
        out.append(q)

        # What does the word mean? Needs three other definitions to choose from.
        defs = [x["definition"] for x in all_kw if x.get("definition") and _norm(x["term"]) != _norm(term)]
        if k.get("definition") and len(defs) >= 3:
            rng.shuffle(defs)
            o, a = _opts(rng, k["definition"], defs)
            out.append({"section": sec, "section_title": titles.get(sec, ""), "source": k["definition"], "level": "medium", "qtype": "mcq",
                        "text": f"Which of these is true about {term}?", "options": o, "answer": a, "explanation": k["definition"]})

    all_figs = [f for c in chapters for f in figures(c)]
    for f in figures(ch):
        d = f.get("desc") or {}
        name = f"Figure {f['number']}" if f.get("number") else "this figure"
        fig = {"image": f.get("image", ""), "number": f.get("number", ""), "caption": f.get("caption", "")}
        caps = [x.get("caption") for x in all_figs if x.get("caption") and x is not f and _norm(x.get("caption")) != _norm(f.get("caption"))]
        if f.get("caption") and len(caps) >= 3:
            rng.shuffle(caps)
            o, a = _opts(rng, f["caption"], caps)
            out.append({"section": f.get("section", ""), "section_title": titles.get(f.get("section", ""), ""), "qtype": "figure", "level": "easy", "figure": fig,
                        "text": f"Look at the figure. What does {name} show?", "options": o, "answer": a,
                        "source": f"{name}: {f['caption']}", "explanation": d.get("summary") or f"{name} shows {f['caption'].lower()}."})
        rel = [r for r in (d.get("relations") or []) if len(r.split()) >= 3]
        others = [r for x in all_figs if x is not f for r in ((x.get("desc") or {}).get("relations") or [])]
        if rel and len(others) >= 3:
            rng.shuffle(others)
            o, a = _opts(rng, rel[0], others)
            out.append({"section": f.get("section", ""), "section_title": titles.get(f.get("section", ""), ""), "qtype": "figure", "level": "medium", "figure": fig,
                        "text": f"Look at {name}. Which statement about it is true?", "options": o, "answer": a,
                        "source": f"{name}: " + " ".join(rel), "explanation": d.get("summary") or rel[0]})
        elif d.get("text_in_figure") and d.get("parts"):
            # A labelled diagram: ask what the parts are, answered as a fill-in.
            out.append({"section": f.get("section", ""), "section_title": titles.get(f.get("section", ""), ""), "qtype": "fill", "level": "medium", "figure": fig,
                        "text": f"Look at {name}. Name one part shown in it.", "options": [], "answer": "|".join(d["parts"]),
                        "source": f"{name}: " + "; ".join(d["parts"]), "explanation": d.get("summary") or "; ".join(d["parts"])})
    return out


def chapter_text(ch, limit=7000) -> str:
    parts, n = [], 0
    for b in walk(ch.get("blocks", [])):
        t = (b.get("text") or " ".join(i.get("text", "") for i in b.get("items", []))) if b.get("type") in ("paragraph", "list", "heading") else ""
        if b.get("type") == "heading":
            t = f"\n## {b.get('number', '')} {b.get('text', '')}"
        if t:
            parts.append(t); n += len(t)
        if n > limit:
            break
    return "\n".join(parts)


def ai_prompt(book, ch, count=12) -> str:
    figs = "\n".join(f"- Figure {f.get('number') or '?'}: {f.get('caption', '')}. {(f.get('desc') or {}).get('summary', '')}" for f in figures(ch)) or "none"
    return f"""You are writing a chapter test for a Class {book.grade} {book.subject} student ({book.board}).
Chapter: {ch['title']}

Chapter text:
\"\"\"{chapter_text(ch)}\"\"\"

Figures in this chapter:
{figs}

Write {count} multiple-choice questions that check understanding of THIS chapter only.
Mix levels: about 5 easy (recall), 5 medium (understanding), 2 hard (apply to a new situation).
If there are figures, make 1 or 2 questions about a figure and set "figure" to its number.
Each question has exactly 4 options and one correct answer. Wrong options must be believable but clearly wrong by the book.
"source" must be one sentence copied word for word from the chapter text that proves the answer.
Reply with JSON only: {{"questions": [{{"level": "easy|medium|hard", "text": "...", "options": ["...", "...", "...", "..."], "answer": 0, "explanation": "one or two simple sentences", "source": "exact sentence", "figure": ""}}]}}"""


def from_ai(raw: str, ch, seed: int = 7) -> list[dict]:
    """Keep only well-formed questions whose source sentence really is in the chapter."""
    rng = random.Random(seed)
    m = re.search(r"\{.*\}", raw or "", re.S)
    items = json.loads(m.group(0)).get("questions", []) if m else []
    text = _norm(chapter_text(ch, 100000))
    sents = sentences(ch); titles = section_titles(ch)
    figs = {str(f.get("number")): f for f in figures(ch)}
    out = []
    for it in items:
        opts = [str(o).strip() for o in it.get("options", []) if str(o).strip()]
        try:
            ans = int(it.get("answer"))
        except (TypeError, ValueError):
            continue
        src = _strip(it.get("source", ""))
        if len(opts) != 4 or not 0 <= ans < 4 or not it.get("text") or len(_norm(src)) < 15 or _norm(src) not in text:
            continue
        right = opts[ans]
        rng.shuffle(opts)
        sec = next((s for t, s in sents if _norm(src)[:40] in _norm(t)), "")
        q = {"section": sec, "section_title": titles.get(sec, ""), "qtype": "mcq", "level": it.get("level") if it.get("level") in ("easy", "medium", "hard") else "medium",
             "text": _strip(it["text"]), "options": [{"key": LETTERS[i], "text": t} for i, t in enumerate(opts)], "answer": LETTERS[opts.index(right)],
             "explanation": _strip(it.get("explanation", "")) or src, "source": src}
        f = figs.get(str(it.get("figure") or "").replace("Figure", "").strip())
        if f:
            q["qtype"], q["figure"] = "figure", {"image": f.get("image", ""), "number": f.get("number", ""), "caption": f.get("caption", "")}
        out.append(q)
    return out


def is_right(q, given: str) -> bool:
    g = (given or "").strip()
    if not g:
        return False
    if q.qtype in ("mcq", "figure"):
        return g == q.answer
    ok = set()
    for a in q.answer.split("|"):
        if a.strip():
            ok |= {_norm(a), _norm(re.sub(r"\(.*?\)", "", a))}
    return _norm(g) in ok


def option_text(q, key: str) -> str:
    if q.qtype in ("mcq", "figure"):
        return next((o["text"] for o in q.options or [] if o["key"] == key), key or "nothing")
    return key or "nothing"


def correct_text(q) -> str:
    if q.qtype in ("mcq", "figure"):
        return option_text(q, q.answer)
    parts = [a.strip() for a in q.answer.split("|") if a.strip()]
    return parts[0] if len(parts) == 1 else "any of: " + ", ".join(re.sub(r"\s*\(.*?\)", "", a) for a in parts)


def teach_rules(q, given: str, reason: str) -> str:
    """Eddie's explanation without AI: what they picked, the right answer, and the book's own words."""
    yours, right = option_text(q, given), correct_text(q)
    guess = not reason.strip() or re.search(r"\b(guess(ed)?|no idea|don'?t know|not sure|unsure|random)\b", reason, re.I)
    s = f'You picked "{yours}", but the answer is "{right}". ' if given else f'You left this one blank. The answer is "{right}". '
    s += "No problem, let's learn it properly. " if guess else "Good that you told me why, that helps. "
    if q.source:
        s += f'Your book says: "{q.source.rstrip(".")}." '
    if q.explanation and _norm(q.explanation) != _norm(q.source) and len(q.explanation.split()) >= 6:
        s += q.explanation.strip() + " "
    return s + "Want to see it in your book?"


def teach_prompt(q, given: str, reason: str, who: str) -> str:
    opts = "\n".join(f"({o['key']}) {o['text']}" for o in q.options or [])
    fig = f"\nThe question is about Figure {q.figure.get('number')}: {q.figure.get('caption')}." if q.figure else ""
    return f"""You are Eddie, a warm robot teacher, talking out loud with {who} who just got a test question wrong.
Question: {q.text}{fig}
{('Options:' + chr(10) + opts) if opts else ''}
Correct answer: {correct_text(q)}
The student answered: {option_text(q, given) if given else 'nothing'}
Their reason, in their own words: "{reason.strip()[:300] or 'they did not say'}"
What the textbook says: "{q.source}"
{('Explanation: ' + q.explanation) if q.explanation else ''}

In under 90 words: first say kindly what was right or understandable in their thinking, then show the exact mistake, then explain the correct idea using the textbook sentence and one everyday example.
Spoken style: plain sentences, no lists, no markdown, no LaTeX, maths said in words. End by asking if they want to see it in their book."""
