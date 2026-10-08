import json, os, urllib.request

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
