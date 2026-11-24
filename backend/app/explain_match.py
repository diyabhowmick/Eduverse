"""Matching a student's own words to what is already saved, so most typed questions cost no model call.

Vectors are sparse dicts {slot: weight}, unit length, so a match score is a plain dot product between 0 and 1.
"local" needs no model: words, word pairs and word pieces hashed into slots. It catches the same question asked
in slightly different words. "openai" uses text-embedding-3-small and also catches paraphrases; it costs a
fraction of a paisa per question and needs the OpenAI key. Vectors from different models are never compared."""
import json, math, os, re, time, urllib.request, zlib
from .models import Explanation, ExplainVec, Misconception

SLOTS = 1 << 18
STOP = set("""a an the is are was were be been being am do does did of to in on at for by with from and or but if then so as it its this that these
those there here what which who whom whose why how when where i me my we our you your he she they them their can could would should will shall may
might must not no yes than too very just also about into over under up down out off again more most some any each other such only own same
both all few please tell explain mean means meaning understand know dont doesnt didnt isnt arent wasnt get got give like""".split())


def _stem(w: str) -> str:
    for suf in ("ations", "ation", "ings", "ing", "ies", "ied", "es", "ed", "ly", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)] + ("y" if suf in ("ies", "ied") else "")
    return w


def words(text: str) -> list[str]:
    text = re.sub(r"\$[^$]*\$", " ", (text or "").lower())
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", text) if w not in STOP and len(w) > 1]


def _slot(feature: str) -> int:
    return zlib.crc32(feature.encode()) % SLOTS


def local_vec(text: str, boost: str = "") -> dict:
    v: dict[int, float] = {}

    def add(f, w):
        k = _slot(f); v[k] = v.get(k, 0.0) + w
    for src, weight in ((text, 1.0), (boost, 2.5)):
        ws = words(src)
        for w in ws:
            add("w:" + w, weight)
            if len(w) >= 6:
                for i in range(len(w) - 3):
                    add("g:" + w[i:i + 4], 0.15 * weight)
        for a, b in zip(ws, ws[1:]):
            add("b:" + a + " " + b, 0.6 * weight)
    for k in v:   # damp words repeated many times in a long explanation
        v[k] = math.sqrt(v[k])
    n = math.sqrt(sum(x * x for x in v.values())) or 1.0
    return {str(k): round(x / n, 5) for k, x in v.items()}


def openai_vec(text: str, api_key: str = "", base_url: str = "") -> dict:
    body = json.dumps({"model": "text-embedding-3-small", "input": text[:6000]}).encode()
    req = urllib.request.Request((base_url or "https://api.openai.com/v1") + "/embeddings", body,
                                 {"Content-Type": "application/json", "Authorization": "Bearer " + (api_key or os.getenv("OPENAI_API_KEY", ""))})
    e = json.loads(urllib.request.urlopen(req, timeout=30).read())["data"][0]["embedding"]
    return {str(i): round(x, 5) for i, x in enumerate(e)}


def dot(a: dict, b: dict) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(k, 0.0) for k, x in a.items())


class Matcher:
    def __init__(self, ai: dict):
        self.conf = {**{"match_high": 0.6, "match_low": 0.28, "embeddings": "local"}, **(ai.get("prestore") or {})}
        self.model = self.conf["embeddings"] if self.conf["embeddings"] in ("local", "openai") else "local"
        self.ai = ai

    def vec(self, text: str, boost: str = "") -> dict:
        if self.model == "openai":
            pv = (self.ai.get("providers") or {}).get("openai") or {}
            try:
                return openai_vec((boost + ". " + text) if boost else text, pv.get("api_key") or "", pv.get("base_url") or "")
            except Exception:
                self.model = "local"   # the key is missing or the call failed: fall back for this request
        return local_vec(text, boost)


_cache: dict = {}   # (book_id, model) -> (time, count, [(explanation_id, vec)])


def explanation_vecs(db, m: Matcher, book_id: int) -> list[tuple[int, dict]]:
    """Vectors of every saved explanation in one book, worked out once and kept in memory for hot books."""
    from . import explain_store as X
    ids = [i for (i,) in db.query(Explanation.id).filter(Explanation.book_id == book_id, Explanation.status.in_(X.LIVE))]
    hit = _cache.get((book_id, m.model))
    if hit and hit[1] == len(ids) and time.time() - hit[0] < 600:
        return hit[2]
    have = {v.explanation_id: v.vec for v in db.query(ExplainVec).filter(ExplainVec.book_id == book_id, ExplainVec.model == m.model)}
    missing = [i for i in ids if i not in have]
    if missing:
        for e in db.query(Explanation).filter(Explanation.id.in_(missing)):
            vec = m.vec(e.text, e.term)
            if m.model != "local" and len(vec) < 50:
                continue
            have[e.id] = vec
            db.add(ExplainVec(explanation_id=e.id, book_id=book_id, model=m.model, vec=vec))
        db.flush()
    out = [(i, have[i]) for i in ids if i in have]
    _cache[(book_id, m.model)] = (time.time(), len(ids), out)
    return out


def best_misconception(db, m: Matcher, book_id: int, root_id: int | None, q: dict):
    best, score = None, 0.0
    for mc in db.query(Misconception).filter(Misconception.book_id == book_id, Misconception.status != "retired", Misconception.vec_model == m.model):
        s = dot(q, mc.vec or {}) + (0.04 if root_id and mc.root_id == root_id else 0.0)
        if s > score:
            best, score = mc, s
    return best, min(score, 1.0)


def best_explanation(db, m: Matcher, book_id: int, q: dict):
    best, score = None, 0.0
    for eid, v in explanation_vecs(db, m, book_id):
        s = dot(q, v)
        if s > score:
            best, score = eid, s
    return (db.get(Explanation, best) if best else None), score
