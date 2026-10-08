"""Optional LLM pass over the rule candidates: drop generic words, add missed concepts, flag prerequisites.
Providers: ollama | anthropic | openai. Nothing runs unless a provider is given."""
import json, os, re, urllib.request

PROMPT = """You are preparing a school textbook chapter for students.
Chapter: {title} (Class {klass}, {subject}).
Candidate important words found in the chapter: {cands}

Chapter text (shortened):
{text}

Return JSON only: {{"drop": [words from the candidates that are too generic to explain],
"add": [concept words used in this text that a student would want explained, not in the candidates],
"prerequisites": [concept words this text uses but does not explain, which the student should know from lower classes]}}
Use words exactly as they appear in the text. At most 15 in each list."""


def call(provider, model, prompt, base_url=None, api_key=None, timeout=120, json_mode=False):
    if provider == "ollama":
        url = (base_url or "http://localhost:11434") + "/api/generate"
        body = {"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.3}}
        if json_mode:
            body["format"] = "json"
        req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())["response"]
    if provider == "anthropic":
        req = urllib.request.Request((base_url or "https://api.anthropic.com") + "/v1/messages",
                                     json.dumps({"model": model, "max_tokens": 1200, "messages": [{"role": "user", "content": prompt}]}).encode(),
                                     {"Content-Type": "application/json", "x-api-key": api_key or os.getenv("ANTHROPIC_API_KEY", ""), "anthropic-version": "2023-06-01"})
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())["content"][0]["text"]
    if provider == "openai":
        req = urllib.request.Request((base_url or "https://api.openai.com/v1") + "/chat/completions",
                                     json.dumps({"model": model, **({"response_format": {"type": "json_object"}} if json_mode else {}), "messages": [{"role": "user", "content": prompt}]}).encode(),
                                     {"Content-Type": "application/json", "Authorization": "Bearer " + (api_key or os.getenv("OPENAI_API_KEY", ""))})
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())["choices"][0]["message"]["content"]
    raise ValueError("provider must be ollama, anthropic or openai")


def refine(ch, book, terms, text, provider, model, **kw):
    prompt = PROMPT.format(title=ch["title"], klass=book.get("class", ""), subject=book.get("subject", ""),
                           cands=", ".join(t["term"] for t in terms), text=text[:9000])
    raw = call(provider, model, prompt, json_mode=True, **kw)
    m = re.search(r"\{.*\}", raw, re.S)
    data = json.loads(m.group(0)) if m else {}
    low = text.lower()
    drop = {w.lower() for w in data.get("drop", [])}
    kept = [t for t in terms if t["term"].lower() not in drop or t["signals"].__contains__("glossary")]
    have = {t["key"] for t in kept}
    for word, prereq in [(w, False) for w in data.get("add", [])] + [(w, True) for w in data.get("prerequisites", [])]:
        k = re.sub(r"[^a-z0-9 ]+", " ", word.lower()).strip()
        if not k or k not in low:   # never add a word the chapter does not contain
            continue
        if k in have:
            if prereq:
                next(t for t in kept if t["key"] == k)["prerequisite"] = True
            continue
        kept.append({"term": word, "key": k, "score": 0, "signals": ["llm"], "count": low.count(k), "definition": "",
                     "prerequisite": prereq, "source": provider})
        have.add(k)
    return kept, {"dropped": sorted(drop), "added": [t["term"] for t in kept if t["source"] == provider]}
