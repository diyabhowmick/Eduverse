"""Turns the raw element stream into a book: identity, index, chapters, sections and typed blocks.
Rules are about textbook conventions (numbered sections, captions, box labels), never about one particular book."""
import re
from collections import Counter, defaultdict

NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
             "eleven": 11, "twelve": 12, "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7,
             "eighth": 8, "ninth": 9, "tenth": 10, "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12}
SUBJECTS = ["social science", "computer science", "mathematics", "maths", "science", "physics", "chemistry", "biology", "english",
            "tamil", "hindi", "malayalam", "kannada", "telugu", "history", "geography", "civics", "economics", "environmental studies", "evs"]
SEC_RE = re.compile(r"^\s*(\d{1,2})\.(\d{1,2})(?:\.(\d{1,2}))?\.?\s+(\S.*)$")
BOX = [("learning_objectives", r"learning objectives"), ("activity", r"activity\s*\d+"), ("problem", r"problem\s*\d+"),
       ("do_you_know", r"do you know\s*\??"), ("more_to_know", r"more to know"), ("info_bits", r"info\s*bits"),
       ("points", r"points to remember"), ("glossary", r"glossary"), ("exercises", r"textbook exercises|exercises"),
       ("concept_map", r"concept map"), ("ict", r"ict corner"), ("references", r"reference books?"), ("internet", r"internet resources")]
BOX_TITLES = {"learning_objectives": "Learning objectives", "do_you_know": "Do you know?", "more_to_know": "More to know", "info_bits": "Info bits",
              "points": "Points to remember", "glossary": "Glossary", "exercises": "Textbook exercises", "concept_map": "Concept map",
              "ict": "ICT corner", "references": "Reference books", "internet": "Internet resources"}
TAIL_BOXES = {"points", "glossary", "exercises", "concept_map", "ict", "references", "internet"}   # run to the next big marker
SHORT_BOXES = {"activity", "problem", "more_to_know", "info_bits"}                                    # a few paragraphs
HEADING_STYLES = {"EVH1", "EVH2", "EVH3"}


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def box_kind(text):
    t = norm(text)
    for kind, pat in BOX:
        if re.fullmatch(pat, t):
            return kind
    return None


# ---------------- pairing images and tables with their descriptions ----------------
def pair_descriptions(raw, ledger):
    items = []
    for el in raw:
        if el["kind"] == "desc":
            owner = None
            for prev in reversed(items[-3:]):
                if prev["kind"] == "p" and prev.get("drawings") and "desc" not in prev:
                    owner = prev; break
                if prev["kind"] == "table" and "desc" not in prev and el["desc"]["kind"] == "table":
                    owner = prev; break
            if owner is not None:
                owner["desc"] = el["desc"]
            else:
                ledger.append({"page": el["page"], "what": "description without an image or table", "text": el["desc"]["summary"][:120]})
            continue
        items.append(el)
    return items


# ---------------- identity ----------------
def identity(items, first_chapter_page):
    front = [e for e in items if e["page"] and e["page"] < max(2, first_chapter_page)]
    texts = [e.get("text", "") for e in front if e["kind"] == "p"]
    joined = "\n".join(texts)
    out, conf = {"title": "", "subject": "", "class": "", "board": "", "publisher": "", "edition": ""}, {}
    m = re.search(r"\b(standard|class|grade|std\.?)\s+([a-z]+|\d{1,2}|[ivx]+)\b", joined, re.I)
    if m:
        v = m.group(2).lower(); out["class"] = str(NUM_WORDS.get(v, v)); conf["class"] = "front page text"
    for t in texts:
        if norm(t) in SUBJECTS:
            out["subject"] = t.strip().title(); conf["subject"] = "front page heading"; break
    if not out["subject"]:
        for s in SUBJECTS:
            if re.search(r"\b" + s + r"\b", joined, re.I):
                out["subject"] = s.title(); conf["subject"] = "front page text"; break
    m = re.search(r"government of ([a-z ]+?)\s*$", joined, re.I | re.M)
    if m:
        out["board"] = m.group(1).strip().title() + " State Board"; conf["board"] = "'Government of' line"
    elif re.search(r"\bNCERT\b|\bCBSE\b", joined):
        out["board"] = "CBSE"; conf["board"] = "NCERT/CBSE mention"
    m = re.search(r"revised edition\s*[-:]?\s*\n?\s*[-:]?\s*(\d{4})", joined, re.I) or re.search(r"(first|second|third) edition\s*[-:]?\s*\n?\s*[-:]?\s*(\d{4})", joined, re.I)
    if m:
        out["edition"] = ("Revised " + m.group(1)) if "revised" in m.group(0).lower() else m.group(0).split()[0].title() + " " + m.group(2)
    for pat in (r"corporation", r"\bscert\b|\bncert\b|council", r"publisher|publishing"):
        hit = next((t for t in texts if re.search(pat, t, re.I) and len(t) < 90 and not t.strip().startswith("(")), None)
        if hit:
            out["publisher"] = hit.strip(); break
    for e in front:  # cover image text confirms class and subject
        tif = " ".join((e.get("desc") or {}).get("text_in_figure", []))
        if not out["class"]:
            m = re.search(r"\b(\d{1,2})\b", tif)
            if m: out["class"] = m.group(1); conf["class"] = "cover image"
    out["title"] = " ".join(x for x in [out["subject"], ("Standard " + out["class"]) if out["class"] else ""] if x) or "Untitled book"
    return out, conf


# ---------------- table of contents ----------------
def find_toc(items):
    for i, e in enumerate(items):
        if e["kind"] != "table" or len(e["rows"]) < 3:
            continue
        head = [norm(c) for c in e["rows"][0]]
        ti = next((k for k, h in enumerate(head) if h in ("title", "chapter title", "lesson", "chapter", "topic", "name")), None)
        ui = next((k for k, h in enumerate(head) if h in ("unit", "chapter", "lesson", "s no", "no", "unit no", "chapter no")), None)
        pi = next((k for k, h in enumerate(head) if "page" in h), None)
        if ti is None or pi is None:
            continue
        mi = next((k for k, h in enumerate(head) if h == "month"), None)
        toc = []
        for r in e["rows"][1:]:
            if ti >= len(r) or not r[ti].strip():
                continue
            unit = r[ui].strip() if ui is not None and ui != ti and ui < len(r) else ""
            page = re.sub(r"\D", "", r[pi]) if pi < len(r) else ""
            entry = {"unit": int(unit) if unit.isdigit() else None, "title": r[ti].strip(), "page": int(page) if page else None,
                     "month": r[mi].strip() if mi is not None and mi < len(r) else ""}
            toc.append(entry)
        return i, toc
    return None, []


# ---------------- chapters ----------------
def chapter_starts(items, toc):
    first_sec = {}
    for i, e in enumerate(items):
        if e["kind"] == "p":
            m = SEC_RE.match(e["text"])
            if m and (e["style"] in HEADING_STYLES or len(e["text"]) < 80):
                n = int(m.group(1))
                first_sec.setdefault(n, i)
    starts = {}
    titles = {t["unit"]: norm(t["title"]) for t in toc if t["unit"]}
    for n, idx in sorted(first_sec.items()):
        page = items[idx]["page"]
        start = None
        for j in range(idx - 1, -1, -1):  # walk back over the chapter opener on this page or the one before
            e = items[j]
            if e["page"] < page - 1:
                break
            t = norm(e.get("text", ""))
            banner = norm(" ".join((e.get("desc") or {}).get("text_in_figure", [])))
            if (t in ("learning objectives", "u n i t", f"unit {n}") or (titles.get(n) and t == titles[n])
                    or (banner and re.search(rf"\bunit {n}\b", banner))):
                start = j
        if start is None:
            start = idx
        pg = items[start]["page"]
        while start > 0 and items[start - 1]["page"] == pg:  # chapter opens at the top of its page
            start -= 1
        starts[n] = start
    ordered = sorted(starts.items())
    clean, last = [], -1
    for n, s in ordered:
        if s > last:
            clean.append((n, s)); last = s
    return clean


def fallback_starts(items):
    """Where to split a book that has no printed section numbers.

    The main route above needs headings like "1.1 Unit Systems". Plenty of
    books do not have them — a scanned book whose headings the model could not
    label, a workbook, a reader. Without a fallback the converter emitted no
    chapters at all, wrote no review pages, and the reviewer was left with a
    screen that spun forever.

    So it tries, in order, until something works:

      headings   any heading style, numbered or not
      pages      every page becomes a unit

    The last one always succeeds, because every item knows its page. A book
    split by page is not as good as one split by chapter, but the reviewer can
    work with it, which is the whole point.
    """
    # 1 · any heading, even without a number in front of it
    heads = [i for i, e in enumerate(items)
             if e["kind"] == "p" and e.get("style") in HEADING_STYLES
             and len((e.get("text") or "").strip()) > 2]
    if len(heads) >= 2:
        return [(n + 1, i) for n, i in enumerate(heads)], "headings"

    # 2 · one unit per page. Always possible.
    seen, out = set(), []
    for i, e in enumerate(items):
        pg = e.get("page")
        if pg is not None and pg not in seen:
            seen.add(pg)
            out.append((len(out) + 1, i))
    if out:
        return out, "pages"

    # 3 · nothing at all to go on — one unit holding everything
    return ([(1, 0)] if items else []), "whole"


# ---------------- noise ----------------
def running_lines(items, chapter_titles, ident):
    """Running headers and footers: chapter titles repeated away from the chapter opener, 'Unit N' lines, subject+class tokens."""
    rep = set()
    for n, title in chapter_titles.items():
        rep |= {norm(title), f"unit {n} {norm(title)}", f"unit {n}"}
    s, c = norm(ident.get("subject")), ident.get("class", "")
    if s:
        rep |= {f"{s}{c}", f"{s} {c}"}
    return rep


def is_code(text):
    t = text.strip()
    return bool(re.fullmatch(r"[A-Z]\d{2,4}_\d+_[A-Z_]+", t)) or t in ("http://", "https://") or bool(re.fullmatch(r"[\W_]+", t))


def figure_label_runs(seq, protected, skip=frozenset()):
    """Runs of tiny fragments. Near a figure they are in-figure labels (dropped from the reading flow);
    elsewhere they are one sentence broken over several lines (merged into the next paragraph)."""
    drop, merge = set(), {}
    idx = [i for i, _ in seq]
    pos = {i: k for k, i in enumerate(idx)}
    fig_words = {}
    for k, (i, e) in enumerate(seq):
        d = e.get("desc")
        words = set()
        if e.get("drawings") and d:
            words = {norm(x) for x in d.get("text_in_figure", []) + d.get("parts", [])}
            words |= {norm(w) for x in d.get("text_in_figure", []) for w in re.split(r"\s{2,}|\|", x)}
        if e["kind"] == "table":
            words = {norm(c) for r in e["rows"] for c in r}
        if words:
            for j in range(max(0, k - 8), min(len(seq), k + 9)):
                fig_words.setdefault(idx[j], set()).update(words)
    near_fig = set()
    for k, (i, e) in enumerate(seq):
        if e.get("drawings") or e["kind"] == "table":
            for j in range(max(0, k - 3), min(len(seq), k + 4)):
                near_fig.add(idx[j])
    run = []
    def flush(next_i):
        if len(run) >= 2:
            texts = [seq[pos[r]][1]["text"].strip() for r in run]
            hits = sum(1 for r, t in zip(run, texts) if norm(t) and (norm(t) in fig_words.get(r, set()) or any(norm(t) in w for w in fig_words.get(r, set()) if len(norm(t)) > 3)))
            labelish = hits >= max(1, len(texts) // 3) or sum(1 for t in texts if not re.search(r"[a-z]{3}", t)) >= len(texts) / 2
            if labelish:
                drop.update(run)
            elif next_i is not None:
                merge[next_i] = " ".join(texts)
                drop.update(run)
        run.clear()
    for i, e in seq:
        t = e.get("text", "").strip() if e["kind"] == "p" else None
        if t is not None and (norm(t) in skip or is_code(t)):
            continue  # running headers are removed separately and do not break a run
        tiny = (t is not None and i not in protected and not e.get("drawings") and not e.get("math")
                and e["style"] not in HEADING_STYLES | {"EVCaption", "EVListNumber", "EVListBullet"}
                and 0 < len(t) <= 22 and len(t.split()) <= 3 and not re.search(r"[.?!:]$", t) and not box_kind(t) and not SEC_RE.match(t)
                and norm(t) not in ("solution", "introduction"))
        if tiny:
            run.append(i)
        else:
            nxt = i if (e["kind"] == "p" and t and e["style"] == "EVBody" and not box_kind(t)) else None
            flush(nxt)
    flush(None)
    return drop, merge


# ---------------- figures ----------------
def is_decorative(desc, caption, size):
    if caption:
        return False, ""
    if not desc:
        if size and size[0] >= 120 and size[1] >= 80:
            return False, ""
        return True, "small image without description"
    s = (desc.get("summary", "") + " " + desc.get("type", "")).lower()
    if "qr code" in s: return True, "QR code"
    if desc.get("type") == "text banner": return True, "text banner"
    if re.search(r"\b(seal|emblem|logo)\b", s): return True, "logo or seal"
    if re.search(r"\bicon\b", s) and len(s) < 900: return True, "icon"
    if size and size[0] and size[0] < 40 and size[1] < 40: return True, "tiny image"
    return False, ""


CAP_FIG = re.compile(r"^\s*(fig(?:ure)?\.?)\s*(\d+\.\d+)\s*[:.\-]?\s*(.*)$", re.I)
CAP_TAB = re.compile(r"^\s*table\s*[:.]?\s*(\d+\.\d+)\s*[:.\-]?\s*(.*)$", re.I)


def build(raw):
    ledger = []
    items = pair_descriptions(raw, ledger)
    toc_idx, toc = find_toc(items)
    starts = chapter_starts(items, toc)
    split = "sections"
    if not starts:
        # No printed section numbers anywhere. Rather than produce an empty
        # book, split it some other way and say so in the report.
        starts, split = fallback_starts(items)
    first_page = items[starts[0][1]]["page"] if starts else 99
    ident, conf = identity(items, first_page)
    toc_titles = {t["unit"]: t["title"] for t in toc if t["unit"]}
    rep = running_lines(items, toc_titles, ident)

    chapters = []
    stats = {"joined": 0, "split_by": split}
    bounds = [(n, s, (starts[k + 1][1] if k + 1 < len(starts) else len(items))) for k, (n, s) in enumerate(starts)]
    bid = 0
    for n, s, e in bounds:
        seq = list(enumerate(items))[s:e]
        protected, inside = set(), None
        for i, el in seq:
            k = box_kind(el.get("text", "")) if el["kind"] == "p" else None
            if k: inside = k
            elif el["kind"] == "p" and SEC_RE.match(el.get("text", "")): inside = None
            if inside in ("glossary", "references", "internet", "exercises", "problem"):
                protected.add(i)
        labels, merges = figure_label_runs(seq, protected, frozenset(rep))
        title = toc_titles.get(n) or ""
        if not title:  # no index: take the heading before the first section
            for i, el in seq:
                if el["kind"] == "p" and el["style"] == "EVH1" and not box_kind(el["text"]):
                    title = el["text"].strip().title(); break
        ch = {"number": n, "title": title or f"Unit {n}", "page_start": items[s]["page"], "page_end": items[e - 1]["page"],
              "sections": [], "blocks": []}
        # captions available in this chapter
        caps = [(i, el) for i, el in seq if el["kind"] == "p" and (el["style"] == "EVCaption" or CAP_FIG.match(el["text"]) or CAP_TAB.match(el["text"]))
                and (CAP_FIG.match(el["text"]) or CAP_TAB.match(el["text"]))]
        used_caps = set()

        def take_caption(i, pat):
            best = None
            for ci, cel in caps:
                if ci in used_caps or not pat.match(cel["text"]):
                    continue
                d = ci - i
                if -4 <= d <= 5 and (best is None or abs(d) < abs(best[0] - i)):
                    best = (ci, cel)
            if best:
                used_caps.add(best[0]); return best[1]["text"].strip()
            return ""

        section = {"id": f"c{n}-intro", "number": "", "title": "Introduction", "level": 2, "kind": "section"}
        ch["sections"].append(section)
        box = None; box_left = 0; box_seen_end = False
        list_block = None
        opened = False

        def emit(block):
            nonlocal bid
            bid += 1
            block["id"] = f"b{bid}"
            block["section"] = section["id"]
            (box["children"] if box is not None else ch["blocks"]).append(block)
            return block

        for i, el in seq:
            if i == toc_idx:
                continue
            page = el["page"]
            if el["kind"] == "p":
                t = el["text"].strip()
                if i in merges:
                    ledger.append({"page": page, "what": "broken lines joined into the next paragraph", "text": merges[i]})
                    t = merges[i] + " " + t
                nt = norm(t)
                if not el.get("drawings") and not el.get("math"):
                    if i in labels:
                        if i not in merges.values() and not any(t in v for v in merges.values()):
                            ledger.append({"page": page, "what": "figure label text removed from reading flow", "text": t})
                        continue
                    if nt in rep or is_code(t) or nt == "u n i t":
                        ledger.append({"page": page, "what": "running header or footer", "text": t}); continue
                    if not opened and (nt == norm(title) or re.fullmatch(rf"unit {n}", nt)):
                        opened = True; continue
                    if el["style"] == "EVCaption" and i in used_caps:
                        continue
                    if (CAP_FIG.match(t) or CAP_TAB.match(t)) and el["style"] == "EVCaption":
                        # caption whose figure comes later: keep for pairing
                        pass
                m = SEC_RE.match(t) if not el.get("drawings") else None
                if m and (el["style"] in HEADING_STYLES or len(t) < 80) and int(m.group(1)) == n:
                    box = None; list_block = None
                    num = ".".join(g for g in m.groups()[:3] if g)
                    lvl = 3 if m.group(3) else 2
                    section = {"id": f"c{n}-s{num}", "number": num, "title": re.sub(r"\s+", " ", m.group(4)).strip(), "level": lvl, "kind": "section"}
                    ch["sections"].append(section)
                    emit({"type": "heading", "level": lvl, "number": num, "text": section["title"], "page": page})
                    continue
                kind = box_kind(t) if not el.get("drawings") else None
                if kind == "do_you_know":
                    ledger.append({"page": page, "what": "Do you know label: box text could not be located, kept as a marker", "text": t})
                    list_block = None
                    emit({"type": "marker", "kind": kind, "text": BOX_TITLES[kind], "page": page})
                    continue
                if kind:
                    list_block = None
                    if kind in TAIL_BOXES:
                        box = None
                        section = {"id": f"c{n}-{kind}", "number": "", "title": BOX_TITLES[kind], "level": 2, "kind": kind}
                        if not any(sx["id"] == section["id"] for sx in ch["sections"]):
                            ch["sections"].append(section)
                    else:
                        box = None
                    b = emit({"type": "box", "kind": kind, "title": BOX_TITLES.get(kind, t), "page": page, "children": []})
                    box = b; box_left = 6 if kind in SHORT_BOXES else 10 ** 6; box_seen_end = False
                    continue
                if t.lower() == "introduction" and el["style"] in HEADING_STYLES | {"EVBody"}:
                    box = None
                    emit({"type": "heading", "level": 2, "number": "", "text": "Introduction", "page": page}); continue
                # close short boxes
                if box is not None and box["kind"] in SHORT_BOXES:
                    starts_new = bool(re.match(r"^[A-Z(“\"]", t)) and not t.lower().startswith("solution")
                    if box_left <= 0 or (box_seen_end and starts_new and box["kind"] != "problem") or (box["kind"] == "problem" and box_seen_end and starts_new and len(t) > 140):
                        box = None
                if el.get("drawings"):
                    list_block = None
                    for d in el["drawings"]:
                        cap = take_caption(i, CAP_FIG)
                        deco, why = is_decorative(el.get("desc"), cap, d["size"])
                        if deco:
                            ledger.append({"page": page, "what": f"decorative image removed ({why})", "text": (el.get("desc") or {}).get("summary", "")[:100]}); continue
                        mm = CAP_FIG.match(cap) if cap else None
                        if not el.get("desc"):
                            ledger.append({"page": page, "what": "figure kept without a description (reviewer should describe it)", "text": f"images/{d['hash']}.{d['ext']}"})
                        emit({"type": "figure", "image": f"images/{d['hash']}.{d['ext']}", "width": d["size"][0], "height": d["size"][1],
                              "number": mm.group(2) if mm else "", "caption": (mm.group(3).strip() if mm else ""), "desc": el.get("desc"), "page": page})
                    continue
                if el.get("math") and (el["style"] == "EVEquation" or not t):
                    list_block = None
                    emit({"type": "equation", "latex": [x["latex"] for x in el["math"]], "plain": [x["plain"] for x in el["math"]], "page": page})
                    for x in el["math"]:
                        if x.get("spaces_lost"):
                            ledger.append({"page": page, "what": "equation text has its spaces missing in the M1 output", "text": x["plain"]})
                    continue
                if not t:
                    continue
                if el["style"] in ("EVListNumber", "EVListBullet"):
                    if list_block is None or list_block.get("ordered") != (el["style"] == "EVListNumber") or (list_block not in (box["children"] if box else ch["blocks"])):
                        list_block = emit({"type": "list", "ordered": el["style"] == "EVListNumber", "items": [], "page": page})
                    list_block["items"].append({"text": t, "bold": el.get("bold", [])})
                    if box is not None: box_left -= 1
                    continue
                list_block = None
                if el["style"] in HEADING_STYLES and len(t) < 70:
                    emit({"type": "subheading", "text": t, "page": page})
                    continue
                if (CAP_FIG.match(t) or CAP_TAB.match(t)) and el["style"] == "EVCaption":
                    continue  # paired later with its figure or table
                container = box["children"] if box is not None else ch["blocks"]
                prev = container[-1] if container else None
                if (prev and prev["type"] == "paragraph" and not re.search(r"[.?!:;]\s*$", prev["text"]) and re.match(r"^[a-z0-9(]", t)
                        and not prev.get("math") and not el.get("math")):
                    prev["text"] = prev["text"].rstrip() + " " + t  # one sentence split over two lines
                    if prev["page"] != page: prev["page_end"] = page
                    stats["joined"] += 1
                    continue
                blk = emit({"type": "paragraph", "text": t, "bold": el.get("bold", []), "page": page})
                if el.get("math"):
                    blk["math"] = [x["latex"] for x in el["math"]]
                if box is not None:
                    box_left -= 1
                    if re.search(r"[.?!]\s*$", t): box_seen_end = True
            elif el["kind"] == "table":
                list_block = None
                cap = take_caption(i, CAP_TAB)
                mm = CAP_TAB.match(cap) if cap else None
                num, ctext = (mm.group(1), mm.group(2).strip()) if mm else ("", "")
                if not cap:
                    cap = take_caption(i, CAP_FIG); mf = CAP_FIG.match(cap) if cap else None
                    if mf: num, ctext = mf.group(2), mf.group(3).strip()
                emit({"type": "table", "rows": el["rows"], "header": True, "number": num, "label": "Figure" if cap and CAP_FIG.match(cap) else "Table",
                      "caption": ctext, "desc": el.get("desc"), "page": page})
        # captions never matched to a figure
        for ci, cel in caps:
            if ci not in used_caps:
                ledger.append({"page": cel["page"], "what": "caption with no matching figure or table", "text": cel["text"].strip()})
        chapters.append(ch)

    # TOC availability and partial chapters
    have = {c["number"]: c for c in chapters}
    for k, t in enumerate(toc):
        c = have.get(t["unit"])
        t["available"] = bool(c)
        if c:
            nxt = toc[k + 1]["page"] if k + 1 < len(toc) and toc[k + 1]["page"] else None
            if nxt and t["page"]:
                expected = nxt - t["page"]
                got = c["page_end"] - c["page_start"] + 1
                c["partial"] = got < expected * 0.6
                c["expected_pages"] = expected
    return {"book": ident, "identity_evidence": conf, "toc": toc, "chapters": chapters, "stats": stats}, ledger
