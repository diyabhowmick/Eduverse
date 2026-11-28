"""Screenshots and measurements of the student learning map. A review tool, not part of the app.

    python docs/map_screens/shoot_map.py --base http://127.0.0.1:8000 --metrics before.json
    python docs/map_screens/shoot_map.py --base http://127.0.0.1:8000 --metrics after.json --shots

Signs in as the demo student (python -m app.seed --demo). The theme is set the way the app reads it,
localStorage.ev_theme -> <html data-theme>, not prefers-color-scheme. Needs Python Playwright and Chrome.

The long book is synthetic: 14 chapters, made up here and served to the browser by intercepting
/api/student/books/<id>/map. It lives only in this script; the app never sees it except through that one
intercepted request. Screenshots of it are named long-book-*.png; the demo book's are demo-book-*.png.
"""
import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
WIDTHS = (390, 1440, 2560)
LONG_ID = 9901          # an id the synthetic book is served under; the route is intercepted, so no such book exists

TOPICS = ["Measurement", "Forces and Pressure", "Light", "Heat", "Electricity", "Magnetism", "Sound", "Matter",
          "Atoms and Molecules", "Chemical Reactions", "Cells", "Microorganisms", "Plants", "The Universe"]
SECTIONS = ["Introduction to {}", "Units of {}", "Laws of {}", "{} in daily life", "Measuring {}", "Experiments with {}",
            "Uses of {}", "History of {}", "{} and energy"]


def long_book() -> dict:
    """14 chapters of 5 to 9 sections: the first four finished, the fifth half read, tests of every kind."""
    chapters, total, done = [], 0, 0
    for c, topic in enumerate(TOPICS, 1):
        n = 5 + (c * 7) % 5
        secs = []
        for s in range(1, n + 1):
            is_done = c < 5 or (c == 5 and s <= 2)
            secs.append({"id": f"L{c}-s{s}", "number": f"{c}.{s}", "title": SECTIONS[(s - 1) % len(SECTIONS)].format(topic), "done": is_done})
        d = sum(x["done"] for x in secs)
        total += n; done += d
        test = {"questions": 0 if c in (7, 12) else 10, "taken": c < 5, "score": [9, 6, 0, 10][c - 1] if c < 5 else 0,
                "out_of": 10, "stars": [3, 2, 0, 3][c - 1] if c < 5 else 0}
        chapters.append({"number": c, "title": topic, "done": d, "total": n, "complete": d == n, "test": test, "sections": secs})
    return {"book": {"id": LONG_ID, "title": "Science Standard 9 (synthetic long book)", "subject": "Science", "grade": "9",
                     "board": "Tamil Nadu State Board"}, "current": {"chapter": 5, "section": "L5-s3"}, "done": done,
            "total": total, "percent": round(100 * done / total), "stars": 8, "streak": 4, "chapters": chapters}


STYLE_PROBE = """() => {
  const props = ['color', 'background-color', 'border-color', 'box-shadow', 'opacity', 'font-weight'];
  const pick = sel => { const el = document.querySelector(sel); if (!el) return null; const cs = getComputedStyle(el);
    return Object.fromEntries(props.map(p => [p, cs.getPropertyValue(p)])) };
  const out = {};
  for (const sel of ['.map-label', '.map-banner .tt', '.map-banner .tt b', '.map-banner .tt span', '.map-banner .num',
                     '.map-banner.done .num', '.map-node .disc', '.map-node.done .disc', '.map-node.here .disc',
                     '.map-node.boss .disc', '.map-hero-name', '.map-chip.gold', '.map-chip.fire', '.map-stars'])
    out[sel] = pick(sel);
  return out;
}"""


def login(base):
    r = urllib.request.Request(base + "/api/auth/login", data=json.dumps(
        {"email": "student@eduverse.local", "password": "Student@123", "portal": "student"}).encode(), headers={"content-type": "application/json"})
    return json.loads(urllib.request.urlopen(r).read())


def page_for(browser, base, who, width, theme, reduced=True):
    ctx = browser.new_context(viewport={"width": width, "height": 900 if width > 500 else 844}, device_scale_factor=1,
                              reduced_motion="reduce" if reduced else "no-preference")
    ctx.add_init_script(f"""localStorage.setItem('ev_token',{json.dumps(who['token'])});
      localStorage.setItem('ev_user',{json.dumps(json.dumps(who['user']))});sessionStorage.setItem('ev_ck','1');
      localStorage.setItem('ev_theme','{theme}');localStorage.setItem('ev_rail','0')""")
    book = json.dumps(long_book())
    ctx.route(f"**/api/student/books/{LONG_ID}/map", lambda route: route.fulfill(status=200, content_type="application/json", body=book))
    return ctx, ctx.new_page()


def open_map(pg, base, book_id):
    pg.goto(f"{base}/student/map/{book_id}", wait_until="networkidle")
    pg.wait_for_selector(".map-road .map-node")
    pg.wait_for_timeout(400)


def scenery_fingerprint(pg) -> str:
    html = pg.evaluate("() => (document.querySelector('.map-scene') || {}).outerHTML || ''")
    return hashlib.sha256(html.encode()).hexdigest()[:16] + f" ({len(html)} chars)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--metrics", type=Path, required=True, help="where to write the measurements (JSON)")
    ap.add_argument("--shots", action="store_true", help="also save screenshots to docs/map_screens/")
    ap.add_argument("--headed", action="store_true", help="a real window, for the scroll timing")
    args = ap.parse_args()
    who = login(args.base)
    m = {"elements": {}, "light_styles": None, "dark_styles": None, "fingerprint": {}, "scroll": {}}
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=not args.headed)
        for theme in ("light", "dark"):
            for width in WIDTHS:
                for name, bid in (("demo-book", 1), ("long-book", LONG_ID)):
                    ctx, pg = page_for(b, args.base, who, width, theme)
                    open_map(pg, args.base, bid)
                    if theme == "light":
                        m["elements"][f"{name}@{width}"] = pg.evaluate("document.querySelectorAll('.map-scroll *').length")
                    if width == 1440 and name == "demo-book":
                        m[f"{theme}_styles"] = pg.evaluate(STYLE_PROBE)
                    if args.shots:
                        pg.screenshot(path=str(HERE / f"{name}-{width}-{theme}.png"))
                    ctx.close()
        # the same book, two separate loads, same width: the scenery must be identical
        for name, bid in (("demo-book", 1), ("long-book", LONG_ID)):
            prints = []
            for _ in range(2):
                ctx, pg = page_for(b, args.base, who, 1440, "light")
                open_map(pg, args.base, bid)
                prints.append(scenery_fingerprint(pg))
                ctx.close()
            m["fingerprint"][name] = prints
        # scroll the long book top to bottom, a frame at a time, and time the frames (motion on, as a student sees it)
        ctx, pg = page_for(b, args.base, who, 1440, "light", reduced=False)
        open_map(pg, args.base, LONG_ID)
        m["scroll"] = pg.evaluate("""() => new Promise(done => {
          const el = document.querySelector('.map-scroll'); el.scrollTop = 0;
          const gaps = []; let last = performance.now();
          const step = () => { const now = performance.now(); gaps.push(now - last); last = now;
            if (el.scrollTop + el.clientHeight >= el.scrollHeight - 1) {
              gaps.sort((a, b) => a - b); const q = f => +gaps[Math.floor(f * (gaps.length - 1))].toFixed(1);
              return done({frames: gaps.length, height: el.scrollHeight, median_ms: q(.5), p95_ms: q(.95), max_ms: q(1),
                           over_50ms: gaps.filter(g => g > 50).length}) }
            el.scrollTop += 24; requestAnimationFrame(step) };
          requestAnimationFrame(step) })""")
        ctx.close()
        b.close()
    args.metrics.write_text(json.dumps(m, indent=2), encoding="utf-8")
    print(json.dumps({k: m[k] for k in ("elements", "fingerprint", "scroll")}, indent=2))


if __name__ == "__main__":
    main()
