"""Load test for EduVerse.

Mode "max": N students hammer the server with no pauses, in the real mix of requests, to find the most
requests per second it can serve and how fast.
Mode "real": N students with real pauses (progress save every 30 s, a page every ~30 s, a tap every ~90 s),
to check what students actually feel at that number.

One request mix, per reading student per minute (from the reader code):
  progress save       2      POST /api/student/books/{id}/progress      (every 30 s, Reader.jsx)
  page view page      2      GET  layout/pNNNN.json + .webp             (a page every ~30 s)
  tap a saved word    0.7    POST /api/learn/explain                    (served from storage)
  picture             0.3    GET  /api/content/.../images/...
  home                0.2    GET  /api/student/home
  open the book       0.1    GET  /api/student/books/{id}               (the whole book, once a session)
  notes for the unit  0.1    GET  /api/student/study/chapter
  = about 7.4 requests a minute for each student who is reading.
"""
import asyncio, json, random, sys, time, os
import httpx

B = os.getenv("EV_URL", "http://127.0.0.1:8000")
TOK = json.load(open('loadtest/tokens.json'))
D = json.load(open('loadtest/load_data.json'))
BID = D['bid']
MIX = [("progress", 2.0), ("page_json", 1.0), ("page_img", 1.0), ("explain", 0.7), ("image", 0.3), ("home", 0.2), ("book", 0.1), ("notes", 0.1)]
PER_MIN = sum(w for _, w in MIX)


def pick():
    r = random.random() * PER_MIN
    for k, w in MIX:
        r -= w
        if r <= 0:
            return k
    return MIX[0][0]


async def do(c, kind, tok):
    h = {"Authorization": "Bearer " + tok}
    if kind == "progress":
        s = random.choice(D['secs'])
        return await c.post(f"/api/student/books/{BID}/progress", json={"chapter": s['chapter'], "section": s['section'], "seconds": 30}, headers=h)
    if kind == "page_json":
        return await c.get(f"/api/content/{BID}/layout/p{random.randint(1, D['pages']):04d}.json", headers=h)
    if kind == "page_img":
        return await c.get(f"/api/content/{BID}/layout/p{random.randint(1, D['pages']):04d}.webp", headers=h)
    if kind == "explain":
        k = random.choice(D['kws'])
        return await c.post("/api/learn/explain", json={"book_id": BID, "chapter": k['chapter'], "keyword_id": k['keyword_id'], "term": k['term']}, headers=h)
    if kind == "image":
        return await c.get(f"/api/content/{BID}/{random.choice(D['imgs'])}", headers=h)
    if kind == "home":
        return await c.get("/api/student/home", headers=h)
    if kind == "book":
        return await c.get(f"/api/student/books/{BID}", headers=h)
    if kind == "notes":
        return await c.get(f"/api/student/study/chapter?book_id={BID}&chapter=1", headers=h)


class Stats:
    def __init__(self):
        self.lat = {}; self.err = {}; self.codes = {}; self.n = 0

    def add(self, kind, ms, code):
        self.lat.setdefault(kind, []).append(ms); self.n += 1
        if code >= 400 or code == 0:
            self.err[kind] = self.err.get(kind, 0) + 1
            self.codes[code] = self.codes.get(code, 0) + 1


def pct(a, p):
    a = sorted(a)
    return a[min(len(a) - 1, int(len(a) * p))] if a else 0


async def user(i, c, st, stop, real):
    tok = TOK[i % len(TOK)]
    if real:
        await asyncio.sleep(random.random() * 8)   # students do not all start in the same second
    while time.time() < stop:
        kind = pick()
        t = time.perf_counter(); code = 0
        try:
            r = await do(c, kind, tok); code = r.status_code
            await r.aread()
        except Exception:
            code = 0
        st.add(kind, (time.perf_counter() - t) * 1000, code)
        if real:
            await asyncio.sleep(max(0, min(random.expovariate(PER_MIN / 60), stop - time.time())))   # on average PER_MIN requests a minute


def server_pids():
    out = []
    for p in os.listdir('/proc'):
        if p.isdigit():
            try:
                if b'uvicorn' in open(f'/proc/{p}/cmdline', 'rb').read() or b'multiprocessing' in open(f'/proc/{p}/cmdline', 'rb').read() and b'app.main' in open(f'/proc/{p}/cmdline', 'rb').read():
                    out.append(p)
            except Exception:
                pass
    return out


def cpu_ticks(pids):
    t = 0
    for p in pids:
        try:
            f = open(f'/proc/{p}/stat').read().split(')')[1].split()
            t += int(f[11]) + int(f[12])
        except Exception:
            pass
    return t


def rss_mb(pids):
    m = 0
    for p in pids:
        try:
            for l in open(f'/proc/{p}/status'):
                if l.startswith('VmRSS'):
                    m += int(l.split()[1]) / 1024
        except Exception:
            pass
    return round(m)


async def run(n, secs, real):
    st = Stats()
    limits = httpx.Limits(max_connections=n + 10, max_keepalive_connections=n + 10)
    async with httpx.AsyncClient(base_url=B, timeout=60, limits=limits) as c:
        pids = server_pids(); c0 = cpu_ticks(pids); t0 = time.time()
        stop = time.time() + secs
        await asyncio.gather(*(user(i, c, st, stop, real) for i in range(n)))
        el = time.time() - t0; cpu = (cpu_ticks(pids) - c0) / os.sysconf('SC_CLK_TCK') / el * 100
    allms = [x for v in st.lat.values() for x in v]
    res = {"mode": "real" if real else "max", "users": n, "seconds": round(el), "requests": st.n, "rps": round(st.n / el, 1),
           "p50": round(pct(allms, .5)), "p95": round(pct(allms, .95)), "p99": round(pct(allms, .99)),
           "errors": sum(st.err.values()), "error_codes": st.codes, "server_cpu_pct": round(cpu), "server_mb": rss_mb(pids),
           "by_kind": {k: {"n": len(v), "p50": round(pct(v, .5)), "p95": round(pct(v, .95)), "err": st.err.get(k, 0)} for k, v in st.lat.items()}}
    print(json.dumps(res), flush=True)
    return res


if __name__ == "__main__":
    mode, n, secs = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    asyncio.run(run(n, secs, mode == "real"))
