"""python -m eduverse_book2docx BOOK.pdf -o out/"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .config import Config
from .ollama_client import OllamaClient
from .pipeline import run


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="eduverse_book2docx",
        description="Turn a printed book (PDF or DOCX) into a digital book: "
                    "book.json plus an editable flow.docx.")
    p.add_argument("input", nargs="?", help="path to the .pdf or .docx")
    p.add_argument("-o", "--out", default="out", help="output folder")
    p.add_argument("--page-lock", action="store_true",
                   help="one docx page per printed page")
    p.add_argument("--layout-docx", action="store_true",
                   help="also write the positional layout.docx")
    p.add_argument("--no-page-markers", action="store_true")
    p.add_argument("--no-digital", action="store_true",
                   help="skip digital/index.html")
    p.add_argument("--no-spec", action="store_true",
                   help="skip the figure spec pass, descriptions only")
    p.add_argument("--no-describe", action="store_true",
                   help="skip the figure description pass")
    p.add_argument("--no-split", action="store_true",
                   help="skip composite figure splitting")
    p.add_argument("--offline", action="store_true",
                   help="never call Ollama, geometry only")
    p.add_argument("--dpi", type=int, default=None)
    p.add_argument("--ocr-model", default=None)
    p.add_argument("--vlm-model", default=None)
    p.add_argument("--host", default=None, help="Ollama host URL")
    p.add_argument("--fail-on-gate", action="store_true")
    p.add_argument("--check", action="store_true",
                   help="check Ollama and the models, then exit")
    p.add_argument("--describe", metavar="IMAGE",
                   help="send one image straight to the VLM and print what "
                        "comes back, then exit. Use this to prove the model "
                        "works before blaming the pipeline.")
    p.add_argument("--json", action="store_true", help="machine readable summary")
    return p


def cfg_from_args(a) -> Config:
    cfg = Config()
    if a.host:
        cfg.ollama_host = a.host
    if a.ocr_model:
        cfg.ocr_model = a.ocr_model
    if a.vlm_model:
        cfg.vlm_model = a.vlm_model
    if a.dpi:
        cfg.page_dpi = a.dpi
        cfg.figure_dpi = a.dpi
    cfg.offline = bool(a.offline)
    cfg.page_lock = bool(a.page_lock)
    cfg.write_layout_docx = bool(a.layout_docx)
    cfg.show_page_markers = not a.no_page_markers
    cfg.describe_figures = not a.no_describe
    cfg.composite_split = not a.no_split
    cfg.write_digital = not a.no_digital
    if a.no_spec:
        cfg.figure_spec = False
        cfg.emit_svg = False
    cfg.fail_on_gate = bool(a.fail_on_gate)
    return cfg


def _describe_one(path: str, cfg: Config) -> int:
    """One image, one call, printed raw. If this works the model is fine and
    any missing description is a pipeline problem. If it fails, it is not."""
    import time
    from PIL import Image
    from .figures import to_png_bytes

    if not os.path.exists(path):
        print(f"no such file: {path}", file=sys.stderr)
        return 2
    client = OllamaClient(cfg)
    health = client.health()
    print(f"host      {cfg.ollama_host}")
    print(f"model     {cfg.vlm_model}")
    if not health.get("ok"):
        print(f"ollama    NOT REACHABLE: "
              f"{health.get('error') or health.get('missing')}")
        return 1
    print("ollama    ok")

    with Image.open(path) as im:
        im.load()
        print(f"image     {im.size[0]} x {im.size[1]} {im.mode}")
        payload = to_png_bytes(im.convert("RGB"))
    print(f"sending   {len(payload) // 1024} KB\n")

    t0 = time.time()
    try:
        d = client.describe_figure(payload)
    except Exception as exc:
        print(f"FAILED after {time.time() - t0:.1f}s: "
              f"{type(exc).__name__}: {exc}")
        return 1
    call = client.calls[-1] if client.calls else {}
    print(f"answered in {time.time() - t0:.1f}s via /api/{call.get('endpoint','?')}"
          f", {call.get('chars', 0)} characters\n")
    raw = getattr(client, "last_raw", "")
    print("--- raw reply from the model ---")
    print(raw[:2000] if raw.strip() else "(nothing at all)")
    print("--- after parsing ---")
    print(json.dumps(d, indent=2, ensure_ascii=False))
    desc = str(d.get("desc") or "").strip()
    print()
    if desc:
        print(f"OK: {len(desc)} characters of description")
        return 0
    print("The model answered but produced no description. "
          "Try a larger vision model.")
    return 1


def _progress(stage: str, i: int, n: int) -> None:
    bar = int(28 * i / max(1, n))
    sys.stderr.write(f"\r{stage:<6} [{'#' * bar}{'.' * (28 - bar)}] {i}/{n}")
    sys.stderr.flush()
    if i == n:
        sys.stderr.write("\n")


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    cfg = cfg_from_args(a)

    if a.check:
        h = OllamaClient(cfg).health()
        print(json.dumps(h, indent=2))
        return 0 if h.get("ok") else 1

    if a.describe:
        return _describe_one(a.describe, cfg)

    if not a.input:
        build_parser().print_help()
        return 2
    if not os.path.exists(a.input):
        print(f"no such file: {a.input}", file=sys.stderr)
        return 2

    res = run(a.input, a.out, cfg, progress=None if a.json else _progress)
    _ = cfg

    if a.json:
        print(json.dumps({
            "out": res.out_dir, "passed": res.passed,
            "pages": len(res.book.pages),
            "detected": res.book.detected,
            "counts": res.book.counts(),
            "ledger": {"detected": res.ledger.detected,
                       "emitted": res.ledger.emitted,
                       "dropped": res.ledger.dropped,
                       "balanced": res.ledger.balanced()},
            "coverage": res.coverage.summary() if res.coverage else None,
            "stats": res.stats, "files": res.files,
            "failures": res.failures, "elapsed_s": round(res.elapsed, 1),
        }, indent=2, default=str))
        return 0 if res.passed else 1

    c = res.book.counts()
    print(f"\n{res.book.source_file}  {len(res.book.pages)} pages  "
          f"{res.elapsed:.1f}s")
    print(f"  detected   {res.book.detected}")
    print(f"  blocks     " + ", ".join(f"{k} {v}" for k, v in sorted(c.items())))
    print(f"  ledger     detected {res.ledger.detected}, "
          f"emitted {res.ledger.emitted}, dropped {res.ledger.dropped}, "
          f"{'balanced' if res.ledger.balanced() else 'OFF BY ' + str(res.ledger.imbalance())}")
    print(f"  written    " + ", ".join(f"{k} {v}" for k, v in res.stats.items()))
    if res.coverage:
        cs = res.coverage.summary()
        print(f"  readable   {cs['coverage'] * 100:.1f}% "
              f"({cs['machine_readable']}/{cs['blocks']} blocks), "
              f"{cs['opaque']} opaque")
        print(f"  figures    {cs['figures_described']}/{cs['figures']} described, "
              f"{cs['figures_regenerable']} regenerable, "
              f"{cs['figures_with_svg']} redrawn as SVG")
        if cs["figures"] and cs["figures_described"] < cs["figures"] \
                and not cfg.offline and cfg.describe_figures:
            reasons = {b.figure.error for _p, b in res.book.blocks()
                       if b.type == "figure" and b.figure and b.figure.error}
            for why in list(reasons)[:2]:
                print(f"  WARN       no figure description: {why[:100]}")
            print("  WARN       run --check to test Ollama and the models")
        print(f"  equations  {cs['equations_as_latex']}/{cs['equations']} as LaTeX"
              + (f", {cs['equations_read_by_vlm']} read by the VLM"
                 if cs['equations_read_by_vlm'] else ""))
    for f in res.failures:
        print(f"  FAIL       {f}")
    print(f"  gate       {'pass' if res.passed else 'fail'}")
    for k, v in res.files.items():
        print(f"  {k:<10} {v}")
    return 0 if res.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
