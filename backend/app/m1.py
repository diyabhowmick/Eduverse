"""Module 1 (book extraction) inside EduVerse.

Every M1 setting comes from M1's own Config dataclass: the defaults, the types and the help text
are read from m1/eduverse_book2docx/config.py, so a new field in M1 shows up in Settings by itself.
Super Admin's changes are stored as overrides in the settings table under the key "m1".
"""
import copy, os, re, sys, threading
from pathlib import Path

M1_PATH = Path(os.getenv("M1_PATH", str(Path(__file__).resolve().parents[2] / "m1")))
if str(M1_PATH) not in sys.path:
    sys.path.insert(0, str(M1_PATH))

from eduverse_book2docx.config import Config  # noqa: E402

SECRETS = ("openai_api_key",)
LOCK = threading.Lock()  # one book through M1 at a time

GROUP_OF_SECTION = {
    "Model provider": "Model", "Ollama": "Model",
    "Rasterisation": "Page reading", "Page routing": "Page reading",
    "Structure": "Headings and layout", "layout (rules A and B)": "Headings and layout",
    "Bold detection on scans": "Text",
    "Figures": "Figures", "Tables": "Equations and tables",
    "Writer": "Output", "Verification": "Verification", "Style sheet": "Styles",
}
GROUPS = ["Model", "Page reading", "Headings and layout", "Text", "Figures", "Equations and tables", "Output", "Verification", "Styles"]
COMMON = ["provider", "ollama_host", "vlm_model", "ocr_model", "openai_api_key", "openai_model", "offline",
          "page_dpi", "describe_figures", "figure_spec", "emit_svg", "vlm_tables", "vlm_math", "describe_equations",
          "composite_split", "write_digital", "fail_on_gate"]
CHOICES = {"provider": ["ollama", "openai"], "equation_images_in_docx": ["fallback", "always", "never"]}
HIDDEN = {"redraw"}  # superseded by M2 image regeneration
LABELS = {
    "provider": "Model provider", "ollama_host": "Ollama address", "vlm_model": "Vision model (figures, tables, maths)",
    "ocr_model": "Reading model (scanned pages)", "openai_api_key": "OpenAI API key", "openai_model": "OpenAI model",
    "openai_base_url": "OpenAI address", "offline": "Offline test mode (no model calls)",
}
SHOW_WHEN = {"ollama_host": ("provider", "ollama"), "vlm_model": ("provider", "ollama"), "ocr_model": ("provider", "ollama"),
             "ollama_keep_alive": ("provider", "ollama"), "openai_api_key": ("provider", "openai"),
             "openai_model": ("provider", "openai"), "openai_base_url": ("provider", "openai"),
             "openai_max_tokens": ("provider", "openai")}


def _group(section: str, name: str) -> str:
    if any(w in name for w in ("equation", "math", "fraction")):
        return "Equations and tables"
    if name.startswith("table") or name == "vlm_tables":
        return "Equations and tables"
    if name in ("join_fragments", "merge_lone_bullets", "strip_ocr_layout_tags", "dedupe_text", "dedupe_text_min_chars",
                "dedupe_text_shift_pt", "line_join_max_gap_pt", "text_only_to_text", "text_only_min_chars"):
        return "Text"
    if name.endswith("_shading") or name == "box_panels_in_docx":
        return "Styles"
    return GROUP_OF_SECTION.get(section, "Output")


def _pretty(name: str) -> str:
    s = name.replace("_", " ")
    for a, b in ((" pt", " (pt)"), (" px", " (px)"), (" frac", " (fraction)"), (" s", " (seconds)")):
        if s.endswith(a):
            s = s[: -len(a)] + b
    s = re.sub(r"\bvlm\b", "vision model", s)
    s = re.sub(r"\bocr\b", "OCR", s)
    s = re.sub(r"\bdpi\b", "DPI", s)
    s = re.sub(r"\bsvg\b", "SVG", s)
    s = re.sub(r"\bdocx\b", "Word file", s)
    return s[:1].upper() + s[1:]


def _type(v) -> str:
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, (tuple, list)):
        return "list"
    if isinstance(v, dict):
        return "styles"
    return "str"


def _plain(v):
    if isinstance(v, tuple):
        return [_plain(x) for x in v]
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    return v


def defaults() -> dict:
    return {k: _plain(v) for k, v in Config().to_dict().items()}


def fields() -> list:
    """Every Config field with its group, type, default and the help text written above it in config.py."""
    src = Path(sys.modules[Config.__module__].__file__).read_text(encoding="utf-8").splitlines()
    dflt = defaults()
    section, notes, out, seen = "", [], [], set()
    for line in src:
        s = line.strip()
        m = re.match(r"#\s*-{3,}\s*(.+?)\s*-{3,}", s)
        if m:
            section, notes = m.group(1), []
            continue
        if s.startswith("#"):
            notes.append(s.lstrip("# ").strip())
            continue
        m = re.match(r"^    (\w+)\s*:\s*[\w\[\], ]+\s*=\s*(.*)$", line)
        if m and m.group(1) in dflt and m.group(1) not in seen:
            name = m.group(1); seen.add(name)
            inline = m.group(2).split("#", 1)[1].strip() if "#" in m.group(2) and not m.group(2).lstrip().startswith(('"#', "'#")) else ""
            help_ = " ".join(notes + ([inline] if inline else [])).strip()
            notes = []
            if name in HIDDEN:
                continue
            f = {"name": name, "label": LABELS.get(name, _pretty(name)), "group": _group(section, name),
                 "type": _type(dflt[name]), "default": dflt[name], "help": help_[:400],
                 "common": name in COMMON, "secret": name in SECRETS}
            if name in CHOICES:
                f["type"], f["choices"] = "choice", CHOICES[name]
            if name in SHOW_WHEN:
                f["show_when"] = SHOW_WHEN[name]
            out.append(f)
            continue
        if not s:
            notes = []
    order = {n: i for i, n in enumerate(COMMON)}
    out.sort(key=lambda f: (GROUPS.index(f["group"]), order.get(f["name"], 999)))
    return out


def _coerce(name, value, default):
    t = _type(default)
    if t == "bool":
        return bool(value) if not isinstance(value, str) else value.lower() in ("1", "true", "yes", "on")
    if t == "int":
        return int(float(value))
    if t == "float":
        return float(value)
    if t == "list":
        if isinstance(value, str):
            value = [x.strip() for x in value.split(",") if x.strip()]
        return list(value)
    if t == "styles":
        if not isinstance(value, dict):
            raise ValueError("styles must be an object")
        return {k: list(v) for k, v in value.items()}
    return str(value)


def clean_overrides(values: dict) -> dict:
    """Keep only real fields that differ from M1's default, each coerced to the default's type."""
    dflt, out = defaults(), {}
    for k, v in (values or {}).items():
        if k not in dflt or k in HIDDEN:
            continue
        try:
            v = _coerce(k, v, dflt[k])
        except (TypeError, ValueError):
            raise ValueError(f"{_pretty(k)}: not a valid {_type(dflt[k])}")
        if v != dflt[k]:
            out[k] = v
    if out.get("provider", "ollama") not in CHOICES["provider"]:
        raise ValueError("Model provider must be ollama or openai")
    return out


def stored(db) -> dict:
    from .models import Setting
    s = db.get(Setting, "m1")
    return dict((s.value or {}).get("overrides", {})) if s else {}


def effective(db) -> dict:
    return {**defaults(), **stored(db)}


def masked(values: dict) -> dict:
    v = copy.deepcopy(values)
    for k in SECRETS:
        if v.get(k):
            v[k] = "saved"
    return v


def to_config(values: dict) -> Config:
    cfg = Config()
    dflt = cfg.to_dict()
    for k, v in values.items():
        if k not in dflt:
            continue
        d = dflt[k]
        if isinstance(d, tuple):
            v = tuple(v)
        elif isinstance(d, dict):
            v = {n: tuple(x) if isinstance(x, list) else x for n, x in v.items()}
        setattr(cfg, k, v)
    return cfg


def check_models(values: dict) -> dict:
    from eduverse_book2docx.ollama_client import OllamaClient
    return OllamaClient(to_config(values)).health()


def run(src: str, out_dir: str, values: dict, progress=None):
    from eduverse_book2docx import pipeline
    return pipeline.run(src, out_dir, to_config(values), progress=progress)
