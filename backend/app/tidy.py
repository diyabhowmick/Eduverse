"""Repairs questions saved before the text clean-up existed, without asking the model again.

    python -m app.tidy                 show what would change, every paper
    python -m app.tidy --paper 18      one paper
    python -m app.tidy --apply         make the changes

What it does, question by question:
- tables cut into one $...$ per line are joined back into one table; sentences put in maths become words again
- options copied into the question text are removed from the text; an option's own "a." mark is removed
- numbers printed as "Q.7" or "7." become 7
For a paper read with AI, it also restores the printed order: the old reader sorted every question by number, which mixed
up papers whose sections each start again at 1 (Physics Q4 next to Chemistry Q4).

It never deletes a question, because answers, mistakes and test attempts point at questions. A question printed twice
is reported for a person to look at. Nothing is changed without --apply.
"""
import argparse, sys
from .qtext import clean, drop_echoed_options, question_number, strip_option_mark


def _num(n):
    import re
    m = re.search(r"\d+", str(n or ""))
    return int(m.group()) if m else 0


def tidy_question(q) -> dict:
    """The fields of one question that would change, as {field: new value}. Pure: q is only read."""
    opts = []
    for o in q.options or []:
        o2 = dict(o)
        o2["text"] = clean(strip_option_mark(str(o.get("key", "")), str(o.get("text", ""))))
        opts.append(o2)
    text = drop_echoed_options(clean(q.text or ""), opts)
    new = {"text": text, "options": opts, "solution": clean(q.solution or "") if q.solution else q.solution,
           "number": question_number(q.number)}
    return {k: v for k, v in new.items() if v != getattr(q, k)}


def printed_order(qs) -> list:
    """Questions of an AI-read paper in printed order. Pages go in order. On each page, questions that carry on the
    count from earlier pages come first, then any that start it again (a new subject beginning at 1) by section."""
    last, out = 0, []
    for page in sorted({q.page for q in qs}):
        here = sorted((q for q in qs if q.page == page), key=lambda q: (_num(q.number), q.position))
        carry = [q for q in here if _num(q.number) > last]
        again = sorted((q for q in here if _num(q.number) <= last), key=lambda q: (q.section or "", _num(q.number), q.position))
        out += carry + again
        if again:
            last = _num(again[-1].number)
        elif carry:
            last = _num(carry[-1].number)
    return out


def duplicates(qs) -> list[str]:
    """The same number twice in a row in one section, which a person should check."""
    return [f"Q{b.number}{' (' + b.section + ')' if b.section else ''} appears twice in a row"
            for a, b in zip(qs, qs[1:]) if b.number and a.number == b.number and (a.section or "") == (b.section or "")]


def tidy_paper(db, paper_id: int, apply: bool = False) -> dict:
    from .models import Question
    qs = db.query(Question).filter(Question.paper_id == paper_id).order_by(Question.position, Question.id).all()
    report = {"paper": paper_id, "questions": len(qs), "changed": [], "reordered": False, "duplicates": []}
    for q in qs:
        ch = tidy_question(q)
        if ch:
            report["changed"].append({"id": q.id, "number": q.number, "fields": sorted(ch)})
            if apply:
                for k, v in ch.items():
                    setattr(q, k, v)
    if qs and all(q.page for q in qs):  # read with AI: every question knows its page
        order = printed_order(qs)
        if [q.id for q in order] != [q.id for q in qs]:
            report["reordered"] = True
            if apply:
                for pos, q in enumerate(order):
                    q.position = pos
            qs = order
    report["duplicates"] = duplicates(qs)
    return report


def main():
    ap = argparse.ArgumentParser(description="Repair saved question papers without asking the model again.")
    ap.add_argument("--paper", type=int, help="only this paper id")
    ap.add_argument("--apply", action="store_true", help="make the changes (otherwise only report them)")
    a = ap.parse_args()
    from .db import SessionLocal
    from .models import QuestionPaper
    with SessionLocal() as db:
        ids = [a.paper] if a.paper else [p.id for p in db.query(QuestionPaper).order_by(QuestionPaper.id)]
        total = 0
        for pid in ids:
            r = tidy_paper(db, pid, a.apply)
            if r["changed"] or r["reordered"] or r["duplicates"]:
                total += len(r["changed"])
                print(f"paper {pid}: {len(r['changed'])} of {r['questions']} questions tidied"
                      + (", order restored" if r["reordered"] else "")
                      + "".join(f"\n  check: {d}" for d in r["duplicates"]))
        if a.apply:
            db.commit()
        print(("Applied. " if a.apply else "Nothing changed yet; run again with --apply. ") + f"{total} questions in {len(ids)} papers.")


if __name__ == "__main__":
    sys.exit(main())
