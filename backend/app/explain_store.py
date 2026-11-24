"""Saved explanations: ask the model once, then serve the same answer to every student who asks the same thing.

Levels. Level 1 is the word a student taps (in a textbook) or the question they open (in an exam pack).
Level 2 is a phrase inside that explanation. Both are saved and shared, so only the first asker costs a
model request. Level 3 and beyond is generated live for one student, is not saved, and always costs a credit.

Choosing. One place can hold up to three candidates. Each is shown in turn until it has been seen enough;
then the best liked is shown most, with a small share of views still trying the others. A textbook
explanation becomes final on its own once votes clearly favour it. An exam explanation becomes final only
when a reviewer pins it, because a well liked wrong solution would do real harm."""
import random, re
from datetime import datetime
from math import sqrt
from fastapi import HTTPException
from sqlalchemy import func
from .models import AiUsage, Explanation, Setting
from .defaults import AI
from .explain_prompt import build_prompt

MAX_CANDIDATES = 3
TRY_EACH = 30           # views before a candidate is judged on its votes
MIN_VOTES = 10          # votes before a textbook explanation can become final on its own
EXPLORE = 0.1           # share of views that still try the others once there is a favourite
LIVE = ("candidate", "final")


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())[:120]


def ai_conf(db) -> dict:
    s = db.get(Setting, "ai")
    return s.value if s else AI


def month_tokens(db) -> int:
    start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return int(db.query(func.coalesce(func.sum(AiUsage.prompt_tokens + AiUsage.completion_tokens), 0)).filter(AiUsage.at >= start).scalar() or 0)


def budget_left(db):
    budget = int(ai_conf(db).get("monthly_token_budget") or 0)
    return None if not budget else budget - month_tokens(db)


def record(db, kind, model="", usage=None, user_id=None, book_id=None, cached=False, term="", where=""):
    u = usage or {}
    db.add(AiUsage(kind=kind, model=model or "", prompt_tokens=u.get("prompt", 0), completion_tokens=u.get("completion", 0), cached=cached,
                   user_id=user_id, book_id=book_id, term=(term or "")[:200], where=(where or "")[:200]))


def wilson(up: int, down: int) -> float:
    """Lower bound of the liked share, so three likes out of three does not beat ninety out of a hundred."""
    n = up + down
    if not n:
        return 0.0
    p, z = up / n, 1.96
    return (p + z * z / (2 * n) - z * sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / (1 + z * z / n)


def merit(e: Explanation) -> float:
    return (e.helpful + 1) / (e.helpful + e.unhelpful + 2) - 0.15 * e.retries / (e.shown + 1)


def choose(pool: list[Explanation]) -> Explanation:
    final = next((e for e in pool if e.status == "final"), None)
    if final and (len(pool) == 1 or random.random() > EXPLORE):
        return final
    fresh = [e for e in pool if e.shown < TRY_EACH]
    if fresh:
        return min(fresh, key=lambda e: e.shown)
    if random.random() < EXPLORE:
        return random.choice(pool)
    return max(pool, key=merit)


def maybe_finalise(db, anchor_pool: list[Explanation]):
    """Textbook explanations only. Exam explanations wait for a reviewer."""
    if not anchor_pool or anchor_pool[0].scope != "book" or any(e.status == "final" for e in anchor_pool):
        return
    ready = [e for e in anchor_pool if e.helpful + e.unhelpful >= MIN_VOTES]
    if not ready:
        return
    best = max(ready, key=lambda e: wilson(e.helpful, e.unhelpful))
    rivals = [merit(e) for e in anchor_pool if e is not best]
    if wilson(best.helpful, best.unhelpful) >= 0.6 and (not rivals or wilson(best.helpful, best.unhelpful) > max(rivals) - 0.05):
        best.status, best.decided_by = "final", "votes"


def check(text: str) -> str:
    """Refuses replies a student should not see: empty, cut off, or with maths that will not display."""
    t = (text or "").strip()
    if len(t) < 30:
        raise HTTPException(502, "The model returned too little. Try again.")
    if t.count("$") % 2:
        t = t.replace("$", "")  # unbalanced maths markers would garble the whole answer; plain text is safer
    return t[:6000]


import os as _os, threading as _th
# At most this many model requests at once from one API copy. The rest wait briefly, then get a clear "busy"
# instead of piling up and holding every server thread while a slow model answers.
_SLOTS = _th.BoundedSemaphore(int(_os.getenv("AI_CONCURRENCY", "8")))


def generate(db, prompt: str, *, kind: str, user_id=None, book_id=None, term="", where="") -> tuple[str, str]:
    if not _SLOTS.acquire(timeout=float(_os.getenv("AI_WAIT_SECONDS", "20"))):
        raise HTTPException(503, "Lots of students are asking right now. Try again in a few seconds.")
    try:
        return _generate(db, prompt, kind=kind, user_id=user_id, book_id=book_id, term=term, where=where)
    finally:
        _SLOTS.release()


def _generate(db, prompt: str, *, kind: str, user_id=None, book_id=None, term="", where="") -> tuple[str, str]:
    left = budget_left(db)
    if left is not None and left <= 0:
        raise HTTPException(503, "This month's AI budget is used up. Saved explanations still work; new ones return next month.")
    ai = ai_conf(db)
    import os
    provider = os.getenv("AI_PROVIDER_OVERRIDE") or ai["provider"]
    pv = ai["providers"].get(provider, {"model": "test"})
    usage = {}
    if provider == "mock":
        text = (f"Test mode: great question! Once the real AI is switched on, I will answer \"{term}\" right here, in simple words with an example."
                if kind == "buddy" else f"[Test model, not a real answer] {term}: an explanation would appear here.")
    else:
        from .llm_client import call
        try:
            text = call(provider, pv["model"], prompt, base_url=pv.get("base_url"), api_key=pv.get("api_key") or None, timeout=int(_os.getenv("AI_TIMEOUT", "90")), usage=usage)
        except Exception as e:
            import logging
            logging.getLogger("eduverse.ai").warning("AI %s did not answer for %s: %s", provider, term, str(e)[:300])
            raise HTTPException(502, "Explanations are taking a break right now. Please try again in a few minutes.")
    text = check(text)
    usage.setdefault("prompt", len(prompt) // 4); usage.setdefault("completion", len(text) // 4)
    record(db, kind, pv["model"], usage, user_id, book_id, False, term, where)
    return text, pv["model"]


# ---------------- prompts ----------------
def book_prompt(book, chapter_title, term, paragraph, definition, figures, style, ai) -> str:
    return build_prompt(term, {"class": book.grade, "subject": book.subject, "board": book.board}, chapter_title, paragraph, definition,
                        figures, style, ai.get("depth_rules")) + "\nWrite any maths as LaTeX between $ signs, like $x^2+1$."


def question_prompt(pack, q, style, ai) -> str:
    rule = (ai.get("depth_rules") or AI["depth_rules"]).get(style, "")
    options = "\n".join(f"({o['key']}) {o['text']}" for o in q.options or [])
    return f"""You are EduVerse, a patient tutor helping a student preparing for {pack.exam or 'an exam'}.
Question{f' ({q.section})' if q.section else ''}: {q.text}
{'Options:' + chr(10) + options if options else ''}
{'This question has a diagram the student can see.' if q.figure_key else ''}
Correct answer: {q.answer or 'not recorded'}
Worked solution: {q.solution or 'not recorded'}

Help the student understand why this answer is correct.
Style: {rule}
Treat the correct answer above as right and teach it. Explain the idea behind it, go through the steps, and say why any common wrong choice is tempting.
Write short plain paragraphs with no markdown headings. Write all maths as LaTeX between $ signs, like $x^2+1$."""


def deeper_prompt(root: Explanation, parent: Explanation, phrase: str, who: str) -> str:
    return f"""You are EduVerse, a patient tutor for {who}.
The student asked about "{root.term}" and was given this explanation:
\"\"\"{parent.text[:2500]}\"\"\"
In it, they did not understand: "{phrase}".
Explain just "{phrase}", simply and in this context, in under 120 words. Do not repeat the whole explanation.
Write short plain paragraphs with no markdown headings. Write any maths as LaTeX between $ signs."""


def doubt_prompt(root: Explanation, parent: Explanation, doubt: str, who: str) -> str:
    return f"""You are EduVerse, a patient tutor for {who}.
The student is studying "{root.term}" and has read this explanation:
\"\"\"{parent.text[:2500]}\"\"\"
Their question: "{doubt[:400]}"
Answer it clearly in under 150 words, consistent with the explanation above.
Write short plain paragraphs with no markdown headings. Write any maths as LaTeX between $ signs."""


# ---------------- written once, served from storage ----------------
def pconf(db_or_ai) -> dict:
    ai = db_or_ai if isinstance(db_or_ai, dict) else ai_conf(db_or_ai)
    return {**AI["prestore"], **(ai.get("prestore") or {})}


def l2_anchor(book, term: str) -> str:
    """One level 2 explanation per word per book version, shared by every level 1 answer that uses the word."""
    from . import content as C
    return f"l2:{book.id}:{C.reader_key(book)}:{norm(term)}"


def ask(ai: dict, prompt: str, *, json_mode=False, timeout=240, max_tokens=1200, usage=None) -> str:
    """One model request with the configured provider. "mock" answers without a model, for tests."""
    import os, json as _json
    provider = os.getenv("AI_PROVIDER_OVERRIDE") or ai["provider"]
    pv = ai["providers"].get(provider, {"model": "test"})
    if provider == "mock":
        if usage is not None:
            usage.update(prompt=len(prompt) // 4, completion=60)
        if json_mode:
            words = re.findall(r"[A-Za-z]{7,}", prompt.split('"""')[1] if '"""' in prompt else prompt)
            seen = []
            for w in words:
                if w.lower() not in [s.lower() for s in seen]:
                    seen.append(w)
            return _json.dumps({"terms": [{"term": w, "bridge": f"Here {w} is what the explanation leans on."} for w in seen[:3]]})
        return "[Test model, not a real answer] A short saved explanation would appear here, written once and shared."
    from .llm_client import call
    return call(provider, pv["model"], prompt, base_url=pv.get("base_url"), api_key=pv.get("api_key") or None, timeout=timeout,
                json_mode=json_mode, usage=usage, max_tokens=max_tokens)


def parse_json(text: str) -> dict:
    import json as _json
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    try:
        return _json.loads(t)
    except Exception:
        m = re.search(r"\{.*\}", t, re.S)
        return _json.loads(m.group(0)) if m else {}


def mark_prompt(e: Explanation, who: str, n: int) -> str:
    return f"""You are helping {who}. They tapped "{e.term}" and were given this explanation:
\"\"\"{e.text[:3000]}\"\"\"
Pick at most {n} words or short phrases INSIDE this explanation that such a student may not know and would want explained.
Copy each exactly as it appears in the text. Skip "{e.term}" itself, everyday words and anything the explanation already explains.
For each, write one short sentence (under 25 words) that links that word back to "{e.term}" in this explanation.
Answer only with JSON: {{"terms": [{{"term": "...", "bridge": "..."}}]}}"""


def core_prompt(book, term: str, uses: list[str], who: str, style: str, ai: dict) -> str:
    rule = (ai.get("depth_rules") or AI["depth_rules"]).get(style, "")
    seen = "\n".join(f"- {u[:300]}" for u in uses[:3])
    return f"""You are EduVerse, a patient tutor for {who} reading {book.title or 'their textbook'}.
Explain "{term}" simply, in under 120 words, so it makes sense wherever it appears in this book.
It came up while explaining:
{seen}
Style: {rule}
Do not repeat those explanations. Write short plain paragraphs with no markdown headings. Write any maths as LaTeX between $ signs."""


def bridge_prompt(target: Explanation, doubt: str, who: str) -> str:
    return f"""You are EduVerse, a patient tutor for {who}.
A saved explanation of "{target.term}" will be shown to the student right after your reply:
\"\"\"{target.text[:2500]}\"\"\"
The student wrote: "{doubt[:400]}"
Reply in two or three short sentences only. If they have something wrong, say kindly what is off. Then lead them into the explanation
below, for example "Here is how it works:". Do not re-explain the topic yourself. No markdown. Write any maths as LaTeX between $ signs."""
