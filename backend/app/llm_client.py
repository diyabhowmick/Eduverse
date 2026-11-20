import json, os, urllib.error, urllib.request


def _usage(usage, prompt, completion):
    """Fills the caller's dict with real token counts, when the caller wants them."""
    if usage is not None:
        usage["prompt"] = int(prompt or 0)
        usage["completion"] = int(completion or 0)


def openai_json(model, prompt, images=(), base_url=None, api_key=None, timeout=240, usage=None):
    """One OpenAI request returning a JSON object. images are PNG data URLs."""
    content = [{"type": "text", "text": prompt}] + [{"type": "image_url", "image_url": {"url": u, "detail": "high"}} for u in images]
    body = {"model": model, "response_format": {"type": "json_object"}, "messages": [{"role": "user", "content": content}]}
    req = urllib.request.Request((base_url or "https://api.openai.com/v1") + "/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json", "Authorization": "Bearer " + (api_key or os.getenv("OPENAI_API_KEY", ""))})
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read())["error"]["message"]
        except Exception:
            msg = e.reason
        raise RuntimeError(f"OpenAI answered {e.code}: {msg}") from None
    u = data.get("usage") or {}
    _usage(usage, u.get("prompt_tokens"), u.get("completion_tokens"))
    return json.loads(data["choices"][0]["message"]["content"])


def call(provider, model, prompt, base_url=None, api_key=None, timeout=120, json_mode=False, usage=None):
    if provider == "ollama":
        url = (base_url or "http://localhost:11434") + "/api/generate"
        body = {"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.3}}
        if json_mode:
            body["format"] = "json"
        req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
        d = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        _usage(usage, d.get("prompt_eval_count"), d.get("eval_count"))
        return d["response"]
    if provider == "anthropic":
        req = urllib.request.Request((base_url or "https://api.anthropic.com") + "/v1/messages",
                                     json.dumps({"model": model, "max_tokens": 1200, "messages": [{"role": "user", "content": prompt}]}).encode(),
                                     {"Content-Type": "application/json", "x-api-key": api_key or os.getenv("ANTHROPIC_API_KEY", ""), "anthropic-version": "2023-06-01"})
        d = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        _usage(usage, (d.get("usage") or {}).get("input_tokens"), (d.get("usage") or {}).get("output_tokens"))
        return d["content"][0]["text"]
    if provider == "openai":
        req = urllib.request.Request((base_url or "https://api.openai.com/v1") + "/chat/completions",
                                     json.dumps({"model": model, **({"response_format": {"type": "json_object"}} if json_mode else {}), "messages": [{"role": "user", "content": prompt}]}).encode(),
                                     {"Content-Type": "application/json", "Authorization": "Bearer " + (api_key or os.getenv("OPENAI_API_KEY", ""))})
        d = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        _usage(usage, (d.get("usage") or {}).get("prompt_tokens"), (d.get("usage") or {}).get("completion_tokens"))
        return d["choices"][0]["message"]["content"]
    raise ValueError("provider must be ollama, anthropic or openai")
