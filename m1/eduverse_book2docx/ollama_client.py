"""Thin Ollama client for the two local models.

qwen3.5:4b reads the page and returns Markdown text.
qwen3.5:4b             describes a cropped figure and returns JSON.

Nothing else in the package talks to the network.
"""

from __future__ import annotations

import base64
import io
import json
import re
import time
from typing import Any, Dict, List, Optional

from .config import Config

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None


OCR_PROMPT = (
    "Transcribe every character on this page exactly as printed, in reading order.\n"
    "Return GitHub Markdown only.\n"
    "Use # ## ### for heading levels as they appear by size and weight.\n"
    "Use **text** for bold, *text* for italic.\n"
    "Use a Markdown table for any ruled or aligned table.\n"
    "Use $...$ for inline maths and $$...$$ for display maths.\n"
    "Write <<FIGURE>> on its own line where a picture or diagram sits.\n"
    "Do not translate. Do not summarise. Do not add anything that is not printed."
)

VLM_PROMPT = (
    "Look at this cropped figure from a school textbook.\n"
    "Reply with one JSON object and nothing else. Keys:\n"
    '  "fig_kind": one of photo, diagram, chart, map, text_banner, decorative\n'
    "     decorative means ornament with nothing to read and nothing to name: "
    "a rule, a border, a flourish, a corner swirl, a plain tint or gradient. "
    "A seal, emblem, crest, coat of arms, logo, monogram, badge, stamp, "
    "QR code or anything with printed characters in it is NOT decorative, "
    "however small. When in doubt call it photo or diagram, never "
    "decorative.\n"
    '  "label": the printed figure label if visible, else ""\n'
    '  "desc": a description detailed enough that someone who has never seen '
    "this figure could draw a faithful replica from your words alone, without "
    "the picture. Work top left to bottom right. Give the overall layout "
    "first, then every element in turn: what it is, where it sits relative to "
    "the others, its rough size and proportion, its shape, its orientation, "
    "how it connects to what is around it, and the exact text printed on or "
    "beside it. Name arrow directions and what they join. Name line styles, "
    "solid or dashed. Name any shading, hatching or fill. Give angles and "
    "counts where they are printed. Describe structure and geometry, not "
    "mood or beauty. Do not interpret, do not explain the science, do not add "
    "anything that is not drawn.\n"
    '  "entities": list of the named parts\n'
    '  "relationships": list of short statements about how the parts relate\n'
    '  "data_points": list of readable values, empty if none\n'
    '  "text_in_image": every piece of text printed inside the figure\n'
    "Return only the JSON."
)

EQ_DESC_PROMPT = (
    "This is a formula cut out of a school textbook page.\n"
    "Reply with one JSON object and nothing else. Keys:\n"
    '  "reading": the formula read aloud in words, as a teacher would say it, '
    "for example \"I equals Q over t\". Symbols become words. No LaTeX.\n"
    '  "about": at most one short sentence saying what the formula gives, '
    "only if the picture itself makes that plain. Empty string if not.\n"
    "Describe only what is printed. Never solve it, never continue it, and "
    "never add a step that is not there.\n"
)

MATH_PROMPT = (
    "This crop is a single printed mathematical expression from a school "
    "textbook.\n"
    "Reply with one JSON object and nothing else:\n"
    '  {"latex": "...", "confident": true}\n'
    "Transcribe exactly what is printed, in LaTeX. Do not simplify, do not "
    "solve, do not add anything that is not printed. If any part of it is "
    "unreadable, set confident to false and put what you can read in latex."
)

DIAGRAM_SPEC_PROMPT = (
    "This crop is a diagram from a school textbook. Describe its STRUCTURE so "
    "it can be redrawn from scratch.\n"
    "Reply with one JSON object and nothing else:\n"
    '  {"kind":"diagram",\n'
    '   "layout":"one of flow, cycle, hierarchy, parts, ray, circuit, free",\n'
    '   "nodes":[{"id":"n1","label":"...","shape":"box|circle|ellipse|label",'
    '"x":0.0,"y":0.0,"w":0.0,"h":0.0}],\n'
    '   "edges":[{"from":"n1","to":"n2","label":"","style":"solid|dashed|arrow"}],\n'
    '   "annotations":[{"text":"...","x":0.0,"y":0.0}],\n'
    '   "caption":""}\n'
    "Coordinates are fractions of the crop, origin top left. Include every "
    "labelled part and every arrow. Use the printed labels exactly."
)

CHART_SPEC_PROMPT = (
    "This crop is a chart from a school textbook. Describe its DATA so it can "
    "be redrawn from scratch.\n"
    "Reply with one JSON object and nothing else:\n"
    '  {"kind":"chart",\n'
    '   "chart_type":"bar|line|pie|scatter|area",\n'
    '   "title":"", "x_label":"", "y_label":"", "x_unit":"", "y_unit":"",\n'
    '   "categories":["..."],\n'
    '   "series":[{"name":"","values":[0]}],\n'
    '   "notes":""}\n'
    "Read every value you can from the axes and the plotted marks. If a value "
    "is not readable, use null rather than guessing."
)

TABLE_SPEC_PROMPT = (
    "This crop is a table from a school textbook.\n"
    "Reply with one JSON object and nothing else:\n"
    '  {"is_table": true, "header": ["..."], "rows": [["..."]], "caption": ""}\n'
    "One entry per column, one list per row, in printed order. Keep every cell "
    "exactly as printed, empty string for a blank cell. If this is not a "
    "table, return is_table false and nothing else."
)

SPLIT_PROMPT = (
    "This crop may contain several separate figures printed side by side or "
    "stacked. Reply with one JSON object and nothing else:\n"
    '  {"count": N, "parts": [{"x0":0.0,"y0":0.0,"x1":1.0,"y1":1.0}]}\n'
    "Coordinates are fractions of this crop, origin top left. "
    "If it is a single figure return count 1 and one part covering 0,0,1,1."
)


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.calls: List[Dict[str, Any]] = []
        self.last_raw: str = ""     # the untouched reply, for --describe

    # -- plumbing ---------------------------------------------------------
    def _post(self, model: str, prompt: str, images: Optional[List[bytes]],
              num_ctx: int, want_json: bool) -> str:
        """Send a prompt, and an image when there is one.

        /api/chat is the endpoint that carries images reliably on current
        Ollama builds. /api/generate still accepts them but some model
        templates ignore the images array there, and the model then answers
        about nothing at all, which looks exactly like a model that refuses to
        describe. So chat is tried first and generate is the fallback.
        """
        if self.cfg.offline:
            return self._mock(model, want_json)
        if requests is None:
            raise OllamaError("requests is not installed")

        if (self.cfg.provider or "ollama").lower() == "openai":
            return self._post_openai(prompt, images, want_json)

        b64 = [base64.b64encode(i).decode() for i in (images or [])]
        options = {"temperature": self.cfg.temperature, "num_ctx": num_ctx}

        t0 = time.time()
        last: Optional[Exception] = None
        for endpoint in ("chat", "generate"):
            if endpoint == "chat":
                msg: Dict[str, Any] = {"role": "user", "content": prompt}
                if b64:
                    msg["images"] = b64
                payload: Dict[str, Any] = {
                    "model": model, "messages": [msg], "stream": False,
                    "keep_alive": self.cfg.ollama_keep_alive,
                    "options": options,
                }
            else:
                payload = {
                    "model": model, "prompt": prompt, "stream": False,
                    "keep_alive": self.cfg.ollama_keep_alive,
                    "options": options,
                }
                if b64:
                    payload["images"] = b64
            if want_json:
                payload["format"] = "json"
            # A thinking model spends its budget reasoning and can run out
            # before it answers. Ask it not to think; older builds ignore this.
            if self.cfg.disable_thinking:
                payload["think"] = False

            try:
                r = requests.post(f"{self.cfg.ollama_host}/api/{endpoint}",
                                  json=payload,
                                  timeout=self.cfg.ollama_timeout_s)
                r.raise_for_status()
                body = r.json()
                out = (body.get("message", {}) or {}).get("content", "") \
                    if endpoint == "chat" else body.get("response", "")
                out = out or ""
                if not out.strip() and endpoint == "chat":
                    last = OllamaError("empty answer from /api/chat")
                    continue                 # try the other endpoint
                self.calls.append({"model": model, "ok": True,
                                   "endpoint": endpoint,
                                   "s": round(time.time() - t0, 2),
                                   "chars": len(out)})
                self.last_raw = out
                return out
            except Exception as exc:
                last = exc
                continue

        self.calls.append({"model": model, "ok": False, "error": str(last),
                           "s": round(time.time() - t0, 2)})
        raise OllamaError(f"{model}: {last}") from last

    def _post_openai(self, prompt: str, images: Optional[List[bytes]],
                     want_json: bool) -> str:
        """Same prompt and images, sent to the OpenAI chat completions API."""
        if not self.cfg.openai_api_key:
            raise OllamaError("OpenAI is selected but no API key is set")
        model = self.cfg.openai_model
        content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
        for i in images or []:
            content.append({"type": "image_url", "image_url": {
                "url": "data:image/png;base64," + base64.b64encode(i).decode(),
                "detail": "high"}})
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": self.cfg.openai_max_tokens,
        }
        if self.cfg.temperature is not None and not model.startswith(("o1", "o3", "o4", "gpt-5")):
            payload["temperature"] = self.cfg.temperature
        if want_json:
            payload["response_format"] = {"type": "json_object"}
        t0 = time.time()
        last: Optional[Exception] = None
        for attempt in range(3):
            try:
                r = requests.post(
                    self.cfg.openai_base_url.rstrip("/") + "/chat/completions",
                    json=payload, timeout=self.cfg.ollama_timeout_s,
                    headers={"Authorization": f"Bearer {self.cfg.openai_api_key}"})
                if r.status_code in (429, 500, 502, 503) and attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                if r.status_code >= 400:
                    raise OllamaError(f"OpenAI {r.status_code}: {r.text[:200]}")
                out = r.json()["choices"][0]["message"].get("content") or ""
                self.calls.append({"model": model, "ok": True, "endpoint": "openai",
                                   "s": round(time.time() - t0, 2), "chars": len(out)})
                self.last_raw = out
                return out
            except Exception as exc:
                last = exc
                if isinstance(exc, OllamaError):
                    break
        self.calls.append({"model": model, "ok": False, "error": str(last),
                           "s": round(time.time() - t0, 2)})
        raise OllamaError(f"{model}: {last}") from last

    def _mock(self, model: str, want_json: bool) -> str:
        self.calls.append({"model": model, "ok": True, "s": 0.0, "mock": True})
        if want_json:
            return json.dumps({
                "fig_kind": "diagram", "text_only": False, "label": "", "desc": "",
                "entities": [], "relationships": [], "data_points": [],
                "text_in_image": [], "count": 1,
                "parts": [{"x0": 0.0, "y0": 0.0, "x1": 1.0, "y1": 1.0}],
                "latex": "", "confident": False,
                "is_table": False, "header": [], "rows": [],
            })
        return ""

    # -- public -----------------------------------------------------------
    def ocr_page(self, png_bytes: bytes) -> str:
        """Markdown transcription of a full page image."""
        raw = self._post(self.cfg.ocr_model, OCR_PROMPT, [png_bytes],
                         self.cfg.ocr_num_ctx, want_json=False)
        raw = THINK_RE.sub("", raw or "")
        return OPEN_THINK_RE.sub("", raw).strip()

    def describe_figure(self, png_bytes: bytes) -> Dict[str, Any]:
        raw = self._post(self.cfg.vlm_model, VLM_PROMPT, [png_bytes],
                         self.cfg.vlm_num_ctx, want_json=True)
        return _safe_json(raw, {
            "fig_kind": "photo", "text_only": False, "label": "", "desc": "",
            "entities": [], "relationships": [], "data_points": [],
            "text_in_image": [],
        })

    def split_composite(self, png_bytes: bytes) -> List[Dict[str, float]]:
        raw = self._post(self.cfg.vlm_model, SPLIT_PROMPT, [png_bytes],
                         self.cfg.vlm_num_ctx, want_json=True)
        d = _safe_json(raw, {"count": 1, "parts": []})
        parts = d.get("parts") or []
        clean = []
        for p in parts:
            try:
                box = [float(p["x0"]), float(p["y0"]), float(p["x1"]), float(p["y1"])]
            except (KeyError, TypeError, ValueError):
                continue
            box = [min(max(v, 0.0), 1.0) for v in box]
            if box[2] - box[0] > 0.08 and box[3] - box[1] > 0.08:
                clean.append({"x0": box[0], "y0": box[1], "x1": box[2], "y1": box[3]})
        return clean or [{"x0": 0.0, "y0": 0.0, "x1": 1.0, "y1": 1.0}]

    def read_math(self, png_bytes: bytes) -> Dict[str, Any]:
        """Read a printed formula the text layer could not give us."""
        raw = self._post(self.cfg.vlm_model, MATH_PROMPT, [png_bytes],
                         self.cfg.vlm_num_ctx, want_json=True)
        return _safe_json(raw, {"latex": "", "confident": False})

    def describe_equation(self, png_bytes: bytes) -> Dict[str, Any]:
        """Read a printed formula aloud, for someone who cannot see it."""
        raw = self._post(self.cfg.vlm_model, EQ_DESC_PROMPT, [png_bytes],
                         self.cfg.vlm_num_ctx, want_json=True)
        return _safe_json(raw, {"reading": "", "about": ""})

    def figure_spec(self, png_bytes: bytes, kind: str) -> Dict[str, Any]:
        """A structure complete enough to redraw the figure without the image."""
        prompt = CHART_SPEC_PROMPT if kind == "chart" else DIAGRAM_SPEC_PROMPT
        raw = self._post(self.cfg.vlm_model, prompt, [png_bytes],
                         self.cfg.vlm_num_ctx, want_json=True)
        return _safe_json(raw, {})

    def read_table(self, png_bytes: bytes) -> Dict[str, Any]:
        """Pull a real table out of a picture of a table."""
        raw = self._post(self.cfg.vlm_model, TABLE_SPEC_PROMPT, [png_bytes],
                         self.cfg.vlm_num_ctx, want_json=True)
        return _safe_json(raw, {"is_table": False, "header": [], "rows": []})

    def _vision_probe(self) -> Dict[str, Any]:
        """Send a tiny image and ask what colour it is.

        A model that answers about nothing is the failure that looks like a
        model that will not describe, so it is worth one second to rule out.
        """
        import io
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            return {"sees_image": True, "note": "Pillow missing, probe skipped"}
        im = Image.new("RGB", (96, 96), "white")
        ImageDraw.Draw(im).ellipse([16, 16, 80, 80], fill=(220, 20, 40))
        buf = io.BytesIO()
        im.save(buf, "PNG")
        try:
            raw = self._post(
                self.cfg.vlm_model,
                "What single shape is in this image and what colour is it? "
                'Reply with JSON only: {"shape":"...","colour":"..."}',
                [buf.getvalue()], 2048, want_json=True)
        except Exception as exc:
            return {"sees_image": False, "error": str(exc)[:160]}
        d = _safe_json(raw, {})
        blob = json.dumps(d).lower()
        seen = ("circle" in blob or "round" in blob or "ellipse" in blob
                or "red" in blob)
        return {"sees_image": bool(seen), "answer": d,
                "note": "" if seen else
                        "the model replied but did not see the image"}

    def health(self) -> Dict[str, Any]:
        if self.cfg.offline:
            return {"ok": True, "offline": True, "models": []}
        if requests is None:
            return {"ok": False, "error": "requests missing"}
        if (self.cfg.provider or "ollama").lower() == "openai":
            if not self.cfg.openai_api_key:
                return {"ok": False, "provider": "openai", "error": "No OpenAI API key set"}
            out = {"provider": "openai", "models": [self.cfg.openai_model], "missing": []}
            out["vision"] = self._vision_probe()
            out["ok"] = bool(out["vision"].get("sees_image"))
            if not out["ok"] and out["vision"].get("error"):
                out["error"] = out["vision"]["error"]
            return out
        try:
            r = requests.get(f"{self.cfg.ollama_host}/api/tags", timeout=10)
            r.raise_for_status()
            names = [m["name"] for m in r.json().get("models", [])]
            missing = [m for m in (self.cfg.ocr_model, self.cfg.vlm_model)
                       if not any(n.startswith(m.split(":")[0]) for n in names)]
            out = {"ok": not missing, "models": names, "missing": missing}
            if not missing:
                out["vision"] = self._vision_probe()
                out["ok"] = bool(out["vision"].get("sees_image"))
            return out
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)
OPEN_THINK_RE = re.compile(r"<think>.*$", re.S | re.I)


def _safe_json(raw: str, default: Dict[str, Any]) -> Dict[str, Any]:
    if not raw:
        return dict(default)
    txt = raw.strip()
    # A thinking model reasons out loud before it answers, and that reasoning
    # is not JSON. Strip it, including a block left unclosed by a cut off reply.
    txt = THINK_RE.sub("", txt)
    txt = OPEN_THINK_RE.sub("", txt).strip()
    txt = re.sub(r"^```(?:json)?|```$", "", txt, flags=re.M).strip()
    try:
        d = json.loads(txt)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", txt, re.S)
        if not m:
            return dict(default)
        try:
            d = json.loads(m.group(0))
        except json.JSONDecodeError:
            return dict(default)
    if not isinstance(d, dict):
        return dict(default)
    out = dict(default)
    out.update(d)
    return out
