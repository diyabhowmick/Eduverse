"""python -m eduverse_convert flow.docx -o out/ [--llm ollama|anthropic|openai --model NAME]"""
import argparse, hashlib, json, re, shutil, sys, time
from pathlib import Path
from .reader import read
from .structure import build
from .keywords import select, mark, walk, block_text
from . import render


MAX_SIDE = 1000  # stored images are capped; the reader shows them smaller still


def shrink(blob, ext):
    try:
        import io
        from PIL import Image
        im = Image.open(io.BytesIO(blob))
        if max(im.size) <= MAX_SIDE:
            return blob
        im.thumbnail((MAX_SIDE, MAX_SIDE))
        buf = io.BytesIO()
        fmt = "JPEG" if ext.lower() in ("jpg", "jpeg") else "PNG"
        im.save(buf, fmt, **({"quality": 85, "optimize": True} if fmt == "JPEG" else {"optimize": True}))
        return buf.getvalue()
    except Exception:
        return blob


def convert(src, out, llm=None, model=None, base_url=None, api_key=None, log=print):
    src, out = Path(src), Path(out)
    t0 = time.time()
    out.mkdir(parents=True, exist_ok=True)
    (out / "images").mkdir(exist_ok=True)
    raw, images = read(src)
    book, ledger = build(raw)
    data = src.read_bytes()
    text = " ".join(e.get("text", "") for e in raw if e["kind"] == "p")
    book["book"]["fingerprint"] = {"file_sha256": hashlib.sha256(data).hexdigest(),
                                   "text_sha256": hashlib.sha256(re.sub(r"\s+", " ", text.lower()).encode()).hexdigest()}
    book["book"]["source_file"] = src.name
    used = set()
    llm_notes = {}
    for ch in book["chapters"]:
        terms = select(ch)
        if llm:
            ctext = "\n".join(block_text(b) for b, box in walk(ch["blocks"]) if box not in ("exercises", "references", "internet", "glossary"))
            try:
                from .llm import refine
                terms, note = refine(ch, book["book"], terms, ctext, llm, model, base_url=base_url, api_key=api_key)
                llm_notes[ch["number"]] = note
            except Exception as e:  # the rules result stands if the model is unreachable
                llm_notes[ch["number"]] = {"error": str(e)[:200]}
                log(f"  LLM pass skipped for chapter {ch['number']}: {e}")
        mark(ch, terms, f"k{ch['number']}-")
        ch["keywords"] = terms
        for b, _ in walk(ch["blocks"]):
            if b["type"] == "figure":
                used.add(b["image"].split("/")[-1])
    for h, (blob, ext) in images.items():
        name = f"{h}.{ext}"
        if name in used:
            (out / "images" / name).write_bytes(shrink(blob, ext))
    # report
    def count(t):
        return sum(1 for ch in book["chapters"] for b, _ in walk(ch["blocks"]) if b["type"] == t)
    figs = [b for ch in book["chapters"] for b, _ in walk(ch["blocks"]) if b["type"] == "figure"]
    report = {
        "source": src.name, "seconds": round(time.time() - t0, 1),
        "book": book["book"], "identity_evidence": book["identity_evidence"],
        "index_entries": len(book["toc"]), "chapters_in_file": [c["number"] for c in book["chapters"]],
        "chapters_partial": [c["number"] for c in book["chapters"] if c.get("partial")],
        "sections": sum(len([s for s in c["sections"] if s["number"]]) for c in book["chapters"]),
        "blocks": {t: count(t) for t in ("paragraph", "list", "heading", "figure", "table", "equation", "marker")},
        "boxes": {k: sum(1 for ch in book["chapters"] for b in ch["blocks"] if b["type"] == "box" and b["kind"] == k)
                  for k in ("activity", "problem", "more_to_know", "info_bits", "points", "glossary", "exercises", "concept_map", "ict")},
        "figures": {"kept": len(figs), "with_caption": sum(1 for f in figs if f["caption"]), "with_description": sum(1 for f in figs if f.get("desc"))},
        "keywords": {c["number"]: {"count": len(c["keywords"]), "highlights": sum(len(x.get("marks", [])) for b, _ in walk(c["blocks"]) for x in ([b] + b.get("items", [])))}
                     for c in book["chapters"]},
        "llm": {"provider": llm or "none", "notes": llm_notes},
        "lines_joined": (_stats := book.pop("stats", {})).get("joined", 0),
        # How the book had to be split, and whether that is a problem worth
        # telling somebody about.
        "split_by": _stats.get("split_by", "sections"),
        "split_warning": {
            "sections": "",
            "headings": "No printed section numbers were found, so the book was "
                        "split at its headings instead. Units are numbered in the "
                        "order they appear, not as the book numbers them.",
            "pages":    "No section numbers and no headings were found, so every "
                        "page became a unit. The text, figures and tables are all "
                        "here, but the book has no chapter structure.",
            "whole":    "Nothing could be used to split this book, so it is one "
                        "unit. Check that the file is the right one.",
        }.get(_stats.get("split_by", "sections"), ""),
        "ledger": {}, "needs_review": [],
    }
    for l in ledger:
        report["ledger"][l["what"]] = report["ledger"].get(l["what"], 0) + 1
    report["needs_review"] = [l for l in ledger if any(k in l["what"] for k in ("could not be located", "without a description", "no matching", "spaces missing", "without an image"))]
    book["schema"] = "eduverse.book/1"
    (out / "book.json").write_text(json.dumps(book, ensure_ascii=False, indent=1, default=list), encoding="utf-8")
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=list), encoding="utf-8")
    with open(out / "ledger.jsonl", "w", encoding="utf-8") as f:
        for l in ledger:
            f.write(json.dumps(l, ensure_ascii=False) + "\n")
    render.write_preview(book, report, out)
    return book, report


def main(argv=None):
    ap = argparse.ArgumentParser(prog="eduverse_convert", description="M1 flow document to EduVerse digital textbook")
    ap.add_argument("flow"); ap.add_argument("-o", "--out", default="out")
    ap.add_argument("--llm", choices=["ollama", "anthropic", "openai"]); ap.add_argument("--model", default="qwen3.5:4b")
    ap.add_argument("--base-url"); ap.add_argument("--api-key")
    a = ap.parse_args(argv)
    book, rep = convert(a.flow, a.out, a.llm, a.model, a.base_url, a.api_key)
    b = rep["book"]
    if rep.get("split_warning"):
        print("! " + rep["split_warning"])
    print(f"{b['title']} | {b['board']} | chapters {rep['chapters_in_file']} of {rep['index_entries']} in the index"
          f"{' | partial: ' + str(rep['chapters_partial']) if rep['chapters_partial'] else ''}")
    print(f"sections {rep['sections']} | figures {rep['figures']['kept']} | tables {rep['blocks']['table']} | equations {rep['blocks']['equation']} | "
          f"keywords {sum(v['count'] for v in rep['keywords'].values())} | needs review {len(rep['needs_review'])} | {rep['seconds']}s")
    print(f"open {Path(a.out) / 'index.html'}")


if __name__ == "__main__":
    sys.exit(main())
