"""Serve a converted book with live explanations:
python -m eduverse_convert.serve out/ --llm ollama --model qwen3.5:4b   (or anthropic / openai with --api-key, or mock to test)"""
import argparse, json, time
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from .explain import explain


class Handler(SimpleHTTPRequestHandler):
    cfg = {}

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/explain/config":
            return self._json({"provider": self.cfg["llm"], "model": self.cfg["model"]})
        return super().do_GET()

    def do_POST(self):
        if self.path != "/explain":
            return self.send_error(404)
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            t0 = time.time()
            text = explain(self.cfg["llm"], self.cfg["model"], body.get("term", "")[:80], body.get("book", {}), body.get("chapter", ""),
                           body.get("paragraph", ""), body.get("definition", ""), body.get("figures", [])[:3], body.get("depth", "concept_clarity"),
                           base_url=self.cfg.get("base_url"), api_key=self.cfg.get("api_key"))
            self._json({"text": text, "provider": self.cfg["llm"], "model": self.cfg["model"], "seconds": round(time.time() - t0, 1)})
        except Exception as e:
            self._json({"error": f"The model did not answer: {e}"}, 502)

    def _json(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data))); self.end_headers()
        self.wfile.write(data)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="eduverse_convert.serve")
    ap.add_argument("out"); ap.add_argument("--llm", choices=["ollama", "anthropic", "openai", "mock"], default="ollama")
    ap.add_argument("--model", default="qwen3.5:4b"); ap.add_argument("--base-url"); ap.add_argument("--api-key"); ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args(argv)
    Handler.cfg = {"llm": a.llm, "model": a.model, "base_url": a.base_url, "api_key": a.api_key}
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), partial(Handler, directory=a.out))
    print(f"EduVerse reader on http://127.0.0.1:{a.port}  (explanations: {a.llm} {a.model})")
    srv.serve_forever()


if __name__ == "__main__":
    main()
