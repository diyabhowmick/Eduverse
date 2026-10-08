"""Important words: candidates from the book's own signals, scored, then marked at their first use in each topic."""
import re
from collections import defaultdict

W = {"glossary": 3.0, "definition": 3.0, "heading": 2.0, "unit_law": 2.0, "quoted": 1.5, "caption": 1.0, "points": 1.0, "exercises": 0.5, "frequent": 0.5}
THRESHOLD = 2.5
GENERIC = {"the above activity", "this process", "the following", "students", "student", "lesson", "figure", "table", "activity", "example",
           "problem", "solution", "introduction", "physics", "science", "daily life", "day to day life", "our daily life", "the same", "different types",
           "types", "uses", "applications", "advantages", "disadvantages", "definition", "unit", "units", "note", "answer", "question", "measure",
           "the unit", "one", "two", "three", "value", "values", "object", "objects", "body", "bodies", "things", "form", "way", "ways", "same", "other", "amount", "height", "hour", "minute", "second", "metre", "meter", "length", "mass", "time", "curved", "image", "thermo", "heat"}
LEAD = r"^(types of|applications of|uses of|advantages of|disadvantages of|factors affecting|rules for|effects of|terms related to|increasing and decreasing|images formed by|image formed by|transfer of)\s+"
DEF_AFTER = [r"\b(?:is|are|was)\s+(?:called|known as|termed|named|referred to as|defined as)\s+(?:the\s+|a\s+|an\s+)?[‘'\"“]?([A-Za-z][A-Za-z \-’']{2,40}?)[’'\"”]?(?=[.,;:)]|\s+(?:and|or|which|in|of)\b)",
             r"\b(?:known as|called)\s+[‘'\"“]([^’'\"”]{3,40})[’'\"”]"]
DEF_BEFORE = [r"(?:^|[.;]\s+)([A-Z][a-z]+(?:\s+[a-z]+){0,3})\s+(?:is|are)\s+(?:defined as|a measure of|the (?:measure|process|property|amount|ratio|angle|force|device|instrument|distance|closeness|study|flow|bending|splitting|bouncing|technique|form of heat transfer|process of)\b)"]
UNIT_LAW = [r"\bSI unit of (?:the\s+)?([a-z][a-z ]{2,30}?) is (?:the\s+)?[‘'\"]?([a-z]{3,20})",
            r"\b([A-Z][a-z]+(?:’s|'s)\s+[Ll]aws?(?:\s+of\s+[a-z]+)?)",
            r"\b([a-z]*(?:meter|metre|scope))\b",
            r"\bmeasured (?:in|by|using) (?:a |an |the )?(?:device called |unit called )?[‘'\"]?([a-z]{4,20})"]
QUOTED = r"[‘'\"“]([A-Za-z][A-Za-z \-]{2,30}?)[’'\"”]"


def norm(s):
    return re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower()).strip()


def clean_term(t):
    t = (t or "").replace("\xad", "")
    t = re.sub(r"\s*\([^)]*\)", "", t).strip(" .,:;’'\"‘“”-")
    t = re.sub(r"^(as|a|an|the|one|two|this|that|its|their)\s+", "", t, flags=re.I)
    t = re.sub(LEAD, "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t)
    return t


def walk(blocks, box=None):
    for b in blocks:
        if b["type"] == "box":
            yield from walk(b["children"], b["kind"])
        else:
            yield b, box


def block_text(b):
    if b["type"] in ("paragraph", "subheading", "heading"):
        return b["text"]
    if b["type"] == "list":
        return "\n".join(i["text"] for i in b["items"])
    if b["type"] == "table":
        return "\n".join(" | ".join(r) for r in b["rows"])
    if b["type"] == "figure":
        return b.get("caption", "")
    return ""


def candidates(ch):
    cand = defaultdict(lambda: {"signals": set(), "forms": set(), "definition": ""})
    def add(term, sig, sentence=""):
        t = clean_term(term)
        k = norm(t)
        if not k or k in GENERIC or len(k) < 3 or k.isdigit() or len(k.split()) > 4 or re.search(r"\b(to|by|of|for|and|in|the|with)$", k):
            return
        c = cand[k]; c["signals"].add(sig); c["forms"].add(t)
        if sentence and sig in ("definition", "unit_law") and not c["definition"]:
            c["definition"] = sentence.strip()
    body = []
    for b, box in walk(ch["blocks"]):
        text = block_text(b)
        if not text:
            continue
        if box == "glossary":
            for line in text.split("\n"):
                if 2 < len(line) <= 40 and len(line.split()) <= 5 and line[:1].isupper() and not line.rstrip().endswith("."):
                    add(line, "glossary")
            continue
        if box in ("references", "internet", "ict", "concept_map", "learning_objectives"):
            continue
        if b["type"] == "heading" and b.get("number"):
            add(b["text"], "heading")
        if b["type"] == "figure" and b.get("caption") and len(b["caption"].split()) <= 3:
            add(b["caption"], "caption")
        if box in ("exercises", "points"):
            continue
        body.append(text)
        for sent in re.split(r"(?<=[.?!])\s+", text.replace("\n", " ")):
            for p in DEF_AFTER:
                for m in re.finditer(p, sent):
                    add(m.group(1), "definition", sent)
            for p in DEF_BEFORE:
                for m in re.finditer(p, sent):
                    add(m.group(1), "definition", sent)
            for p in UNIT_LAW:
                for m in re.finditer(p, sent):
                    for g in m.groups():
                        add(g, "unit_law", sent)
            for m in re.finditer(QUOTED, sent):
                add(m.group(1), "quoted", sent)
    joined = "\n".join(body).lower()
    extra = {"points": "", "exercises": ""}
    for b, box in walk(ch["blocks"]):
        if box in extra:
            extra[box] += "\n" + block_text(b).lower()
    for k, c in cand.items():
        pat = r"\b" + re.escape(k) + r"s?\b"
        n = len(re.findall(pat, joined))
        c["count"] = n
        if n >= 3: c["signals"].add("frequent")
        for box, txt in extra.items():
            if re.search(pat, txt): c["signals"].add(box)
        if not c["definition"]:
            m = re.search(r"[^.?!\n]*\b" + re.escape(k) + r"s?\b[^.?!\n]*[.?!]", joined)
            if m:
                # recover the original casing from the body text
                start = m.start()
                src = "\n".join(body)
                c["definition"] = src[start:m.end()].strip()
    return cand


def select(ch):
    cand = candidates(ch)
    # merge plural forms into the singular
    for k in list(cand):
        if k.endswith("s") and k[:-1] in cand:
            cand[k[:-1]]["signals"] |= cand[k]["signals"]; cand[k[:-1]]["count"] += cand[k]["count"]; del cand[k]
    out = []
    for k, c in cand.items():
        score = sum(W[s] for s in c["signals"])
        strong = c["signals"] & {"glossary", "definition"}
        if c["count"] == 0 or (score < THRESHOLD and not strong):
            continue
        form = sorted(c["forms"], key=lambda f: (f != f.lower(), len(f)))[0]
        out.append({"term": form if (not form.isupper() or len(form) <= 5) else form.title(), "key": k, "score": round(score, 1), "signals": sorted(c["signals"]),
                    "count": c["count"], "definition": c["definition"][:400], "prerequisite": False, "source": "rules"})
    out.sort(key=lambda x: (-x["score"], x["key"]))
    return out


def mark(ch, terms, id_prefix):
    """Highlight each term at its first use in every topic; about one highlight per 40 words."""
    by_len = sorted(terms, key=lambda t: -len(t["key"]))
    for t in terms:
        t["id"] = f"{id_prefix}{t['key'].replace(' ', '-')}"
        t["first_block"] = None
    seen_in_section = defaultdict(set)
    total = 0
    for b, box in walk(ch["blocks"]):
        if box in ("glossary", "references", "internet", "ict", "concept_map", "exercises", "learning_objectives"):
            continue
        targets = []
        if b["type"] == "paragraph":
            targets = [(b, "text")]
        elif b["type"] == "list":
            targets = [(it, "text") for it in b["items"]]
        for obj, field in targets:
            text = obj[field]
            words = max(1, len(text.split()))
            budget = max(1, words // 40 + 1)
            marks, taken = [], []
            for t in by_len:
                if budget <= 0: break
                if t["key"] in seen_in_section[b["section"]]:
                    continue
                m = re.search(r"(?<![A-Za-z])" + re.escape(t["key"]) + r"(?:s|es)?(?![A-Za-z])", text, re.I)
                if not m or any(not (m.end() <= a or m.start() >= z) for a, z in taken):
                    continue
                marks.append([m.start(), m.end(), t["id"]]); taken.append((m.start(), m.end()))
                seen_in_section[b["section"]].add(t["key"]); budget -= 1; total += 1
                if t["first_block"] is None: t["first_block"] = b["id"]
            if marks:
                obj["marks"] = sorted(marks)
    # second pass: every important word must be clickable at least once in the unit
    for t in by_len:
        if t["first_block"]:
            continue
        for b, box in walk(ch["blocks"]):
            if box in ("glossary", "references", "internet", "ict", "concept_map", "exercises", "learning_objectives"):
                continue
            objs = [b] if b["type"] == "paragraph" else (b["items"] if b["type"] == "list" else [])
            hit = False
            for obj in objs:
                m = re.search(r"(?<![A-Za-z])" + re.escape(t["key"]) + r"(?:s|es)?(?![A-Za-z])", obj["text"], re.I)
                if m and not any(not (m.end() <= a or m.start() >= z) for a, z, _ in obj.get("marks", [])):
                    obj.setdefault("marks", []).append([m.start(), m.end(), t["id"]]); obj["marks"].sort()
                    t["first_block"] = b["id"]; total += 1; hit = True; break
            if hit:
                break
    return total
