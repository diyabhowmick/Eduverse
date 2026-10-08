"""Server tests. Run with: python -m tests.test_server"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS: list = []
FAIL: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append((name, detail))


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="ev_srv_")
    os.environ["EDUVERSE_DATA"] = os.path.join(tmp, "jobs")
    os.environ["EDUVERSE_WORKERS"] = "1"

    from fastapi.testclient import TestClient
    from tests.make_sample import build as build_sample
    from eduverse_book2docx import server

    client = TestClient(server.app)

    # -- health and index ------------------------------------------------
    r = client.get("/api/health")
    check("health responds", r.status_code == 200, str(r.status_code))
    h = r.json()
    check("health names both models",
          "ocr" in h["models"] and "vlm" in h["models"])

    r = client.get("/")
    check("index served", r.status_code == 200 and "EduVerse" in r.text)

    # -- rejections ------------------------------------------------------
    r = client.post("/api/jobs",
                    files={"file": ("notes.txt", b"hello", "text/plain")})
    check("wrong extension rejected", r.status_code == 400, str(r.status_code))

    r = client.post("/api/jobs",
                    files={"file": ("empty.pdf", b"", "application/pdf")})
    check("empty file rejected", r.status_code == 400, str(r.status_code))

    r = client.get("/api/jobs/deadbeef")
    check("unknown job is 404", r.status_code == 404)

    # -- a real conversion ----------------------------------------------
    pdf = build_sample(os.path.join(tmp, "s.pdf"))
    with open(pdf, "rb") as fh:
        data = fh.read()

    r = client.post(
        "/api/jobs",
        files={"file": ("s.pdf", data, "application/pdf")},
        data={"offline": "true", "layout_docx": "true", "describe": "false"})
    check("job accepted", r.status_code == 202, r.text[:200])
    jid = r.json()["job_id"]

    deadline = time.time() + 180
    job = {}
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{jid}").json()
        if job["status"] in ("ready", "failed"):
            break
        time.sleep(0.4)

    check("job reached ready", job.get("status") == "ready",
          str(job.get("error"))[:400])
    if job.get("status") != "ready":
        return report()

    s = job["summary"]
    check("summary has pages", s["pages"] == 4, str(s.get("pages")))
    check("summary ledger balanced", s["ledger"]["balanced"])
    check("summary gate passed", s["gate_passed"], str(s.get("failures")))
    check("summary counts figures", s["counts"].get("figure", 0) >= 2)
    check("progress reached 100", job["percent"] == 100, str(job["percent"]))

    # -- downloads -------------------------------------------------------
    for name, sniff in (("flow.docx", b"PK"), ("layout.docx", b"PK"),
                        ("book.json", b"{"), ("ledger.jsonl", b"{")):
        r = client.get(f"/api/jobs/{jid}/files/{name}")
        check(f"download {name}", r.status_code == 200, str(r.status_code))
        check(f"{name} looks right", r.content.startswith(sniff))
        check(f"{name} has a filename",
              "attachment" in r.headers.get("content-disposition", ""))

    r = client.get(f"/api/jobs/{jid}/files/book.json")
    check("docx download is big enough", len(r.content) > 500)

    r = client.get(f"/api/jobs/{jid}/files/secrets.env")
    check("arbitrary file blocked", r.status_code == 400, str(r.status_code))

    r = client.get(f"/api/jobs/{jid}/report")
    check("report served", r.status_code == 200 and "ingest report" in r.text)

    r = client.get(f"/api/jobs/{jid}/book")
    check("book endpoint serves json",
          r.status_code == 200 and "pages" in r.json())

    r = client.get(f"/api/jobs/{jid}/figures")
    figs = r.json()["figures"]
    check("figures listed", r.status_code == 200 and len(figs) >= 2)
    r = client.get(figs[0]["url"])
    check("figure png served",
          r.status_code == 200 and r.content[:4] == b"\x89PNG")

    r = client.get(f"/api/jobs/{jid}/asset/pages/p001.png")
    check("page raster served", r.status_code == 200)
    r = client.get(f"/api/jobs/{jid}/asset/figures/..%2F..%2Fjob.json")
    check("path traversal blocked", r.status_code in (400, 404),
          str(r.status_code))

    # -- listing and deletion --------------------------------------------
    r = client.get("/api/jobs")
    check("job listed", any(j["id"] == jid for j in r.json()["jobs"]))

    r = client.delete(f"/api/jobs/{jid}")
    check("job deleted", r.status_code == 200)
    check("job gone from disk",
          not os.path.exists(os.path.join(os.environ["EDUVERSE_DATA"], jid)))
    check("job gone from api",
          client.get(f"/api/jobs/{jid}").status_code == 404)

    # -- docx input through the API --------------------------------------
    with open(os.path.join(tmp, "in.docx"), "wb") as fh:
        fh.write(b"")
    r = client.post("/api/jobs",
                    files={"file": ("x.docx", b"PK\x03\x04broken", "application/octet-stream")},
                    data={"offline": "true"})
    check("docx accepted for queueing", r.status_code == 202)
    jid2 = r.json()["job_id"]
    deadline = time.time() + 60
    while time.time() < deadline:
        j2 = client.get(f"/api/jobs/{jid2}").json()
        if j2["status"] in ("ready", "failed"):
            break
        time.sleep(0.3)
    check("broken docx fails cleanly", j2["status"] == "failed" and j2["error"])
    check("failure does not kill the worker",
          client.get("/api/health").status_code == 200)

    return report()


def report() -> int:
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed\n")
    for name, detail in FAIL:
        print(f"FAIL  {name}")
        if detail:
            print("      " + detail.strip().replace("\n", "\n      ")[:500])
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
