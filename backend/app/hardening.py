"""The security trunk: everything that keeps EduVerse safe in one place, so feature builds branch from it
instead of re-solving it. See SECURITY.md for the rules each piece enforces."""
import base64, hashlib, hmac, os, re, threading, time
from pathlib import Path
from fastapi import HTTPException
from .config import settings

WEAK_SECRETS = {"", "change-me-in-production", "changeme", "secret", "x"}


# ---------------- production checks ----------------
def is_prod() -> bool:
    return os.getenv("APP_ENV", "").lower() == "production" or os.getenv("RAILWAY_ENVIRONMENT_NAME", "").lower() == "production"


def check_config():
    """Refuses to start production with settings that would leave it open."""
    problems = []
    if settings.jwt_secret in WEAK_SECRETS or len(settings.jwt_secret) < 32:
        problems.append("JWT_SECRET is missing or shorter than 32 characters")
    if settings.database_url.startswith("sqlite"):
        problems.append("DATABASE_URL points at SQLite; production must use PostgreSQL")
    if settings.superadmin_password in ("ChangeMe@123", ""):
        problems.append("SUPERADMIN_PASSWORD is still the default")
    if not problems:
        return
    msg = "[EV SECURITY] " + "; ".join(problems)
    if is_prod():
        raise SystemExit(msg + ". Refusing to start in production.")
    print(msg + ". Fine for a local run, not for production.", flush=True)


# ---------------- secrets at rest (API keys inside settings) ----------------
SECRET_FIELDS = {"api_key", "secret", "secret_key", "password", "token"}
_box = None


def box():
    global _box
    if _box is None:
        from cryptography.fernet import Fernet
        raw = os.getenv("SETTINGS_KEY", "")
        if raw:
            key = base64.urlsafe_b64encode(hashlib.sha256(("ev-settings|" + raw).encode()).digest())
        else:   # derived from the sign-in secret, so an existing install keeps working; set SETTINGS_KEY to separate them
            key = base64.urlsafe_b64encode(hashlib.sha256(("ev-settings|" + settings.jwt_secret).encode()).digest())
        _box = Fernet(key)
    return _box


def seal(v: str) -> str:
    if not v or not isinstance(v, str) or v.startswith("enc:"):
        return v
    return "enc:" + box().encrypt(v.encode()).decode()


def unseal(v):
    if isinstance(v, str) and v.startswith("enc:"):
        try:
            return box().decrypt(v[4:].encode()).decode()
        except Exception:
            print("[EV SECURITY] a stored key could not be decrypted; SETTINGS_KEY or JWT_SECRET changed. Re-enter it in AI settings.", flush=True)
            return ""
    return v


def walk(v, f):
    if isinstance(v, dict):
        return {k: (f(x) if k in SECRET_FIELDS and isinstance(x, str) else walk(x, f)) for k, x in v.items()}
    if isinstance(v, list):
        return [walk(x, f) for x in v]
    return v


# ---------------- rate limits (Redis when REDIS_URL is set, memory otherwise) ----------------
class Limiter:
    def __init__(self):
        self.r = None
        url = os.getenv("REDIS_URL", "")
        if url:
            try:
                import redis
                self.r = redis.Redis.from_url(url, socket_timeout=1)
                self.r.ping()
            except Exception as e:
                print(f"[EV SECURITY] REDIS_URL set but not reachable ({e}); rate limits are per process", flush=True)
                self.r = None
        self.mem: dict[str, list[float]] = {}
        self.lock = threading.Lock()

    def hit(self, key: str, limit: int, window: int) -> bool:
        """Counts one attempt. False once the key has used its limit inside the window."""
        if self.r is not None:
            try:
                k = "ev:rl:" + key
                n = self.r.incr(k)
                if n == 1:
                    self.r.expire(k, window)
                return n <= limit
            except Exception:
                pass
        now = time.time()
        with self.lock:
            q = [t for t in self.mem.get(key, []) if now - t < window]
            q.append(now)
            self.mem[key] = q
            if len(self.mem) > 50000:
                self.mem = {k: v for k, v in self.mem.items() if v and now - v[-1] < 3600}
            return len(q) <= limit

    def clear(self, key: str):
        if self.r is not None:
            try:
                self.r.delete("ev:rl:" + key)
            except Exception:
                pass
        with self.lock:
            self.mem.pop(key, None)


limiter = Limiter()


def guard(key: str, limit: int, window: int, msg="Too many attempts. Wait a few minutes and try again."):
    if not limiter.hit(key, limit, window):
        raise HTTPException(429, msg)


# ---------------- signed links for book images ----------------
def sign_content(bid: int, hours: int = 6) -> str:
    exp = int(time.time()) + hours * 3600
    mac = hmac.new(("ev-content|" + settings.jwt_secret).encode(), f"{bid}.{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"{exp}.{mac}"


def content_ok(bid: int, t: str) -> bool:
    try:
        exp, mac = t.split(".", 1)
        if int(exp) < time.time():
            return False
        good = hmac.new(("ev-content|" + settings.jwt_secret).encode(), f"{bid}.{exp}".encode(), hashlib.sha256).hexdigest()[:32]
        return hmac.compare_digest(good, mac)
    except Exception:
        return False


# ---------------- what may be shared with other students ----------------
_INJECT = re.compile(r"ignore (all |the )?(previous|above|prior)|system prompt|you are now|pretend to be|jailbreak|developer mode|disregard (the|all)", re.I)
_CONTACT = re.compile(r"https?://|\bwww\.|\b[\w.+-]+@[\w-]+\.[a-z]{2,}\b|(?<![\d.])(\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?![\d.])|\bt\.me/|\bwa\.me/|\b(telegram|whatsapp) (group|channel|number)", re.I)
_ABUSE = re.compile(r"\b(fuck|shit|bitch|bastard|idiot|stupid|chutiya|madarchod|bhenchod|gandu|harami|kill yourself|kys)\b", re.I)


def unsafe(text: str) -> str:
    """Why a piece of text must not be saved for other students, or "" when it is fine."""
    t = text or ""
    if _INJECT.search(t):
        return "instructions aimed at the AI"
    if _CONTACT.search(t):
        return "a link or contact detail"
    if _ABUSE.search(t):
        return "abusive words"
    return ""


# ---------------- uploads ----------------
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "400"))
MAGIC = {
    ".pdf": [b"%PDF-"], ".docx": [b"PK\x03\x04"], ".xlsx": [b"PK\x03\x04"], ".xlsm": [b"PK\x03\x04"], ".doc": [b"\xd0\xcf\x11\xe0"],
    ".png": [b"\x89PNG"], ".jpg": [b"\xff\xd8\xff"], ".jpeg": [b"\xff\xd8\xff"], ".webp": [b"RIFF"], ".gif": [b"GIF8"],
}
# What actually makes a PDF dangerous is an *action*: a dictionary that says
# /S /JavaScript or /S /Launch. The previous pattern also matched the bare
# tokens /JS, /Launch, /EmbeddedFile and /JavaScript anywhere in the file, and
# those turn up in ordinary publisher PDFs — /JS appears nine times in the Tamil
# Nadu Class 8 Science book as a plain name in the catalogue, six times in the
# English one. Both real textbooks were refused and neither contained a script.
_PDF_ACTIVE = re.compile(rb"/S\s*/(JavaScript|Launch)\b")


def check_upload(name: str, head: bytes, size: int, allowed: tuple[str, ...], whole: Path | None = None):
    """The file is what its name says (checked by its first bytes), within the size limit, and a PDF carries no scripts."""
    ext = Path(name or "").suffix.lower()
    if ext not in allowed:
        raise HTTPException(422, "This kind of file is not accepted here: " + ", ".join(allowed))
    if size > MAX_UPLOAD_MB * 1048576:
        raise HTTPException(413, f"The file is larger than {MAX_UPLOAD_MB} MB")
    if ext in MAGIC and not any(head.startswith(m) for m in MAGIC[ext]) and ext != ".csv":
        raise HTTPException(422, f"The file is named {ext} but is not really a {ext[1:].upper()} file")
    if ext == ".pdf":
        scan = head if whole is None else _pdf_scan(whole)
        if _PDF_ACTIVE.search(scan):
            # A book is worth more than the script in it. Take the script out
            # and carry on; only refuse if it cannot be taken out.
            if whole is None:
                raise HTTPException(422, "This PDF contains a script or a launch action, so it was refused. "
                                         "Print it to a new PDF and upload that.")
            gone = strip_pdf_actions(whole)
            if gone is None:
                raise HTTPException(422, "This PDF contains a script or a launch action and it could not be removed, "
                                         "so the file was refused. Print it to a new PDF and upload that.")
            print(f"[EV UPLOAD] {name}: removed active content before processing ({', '.join(gone) or 'none left'})", flush=True)


def strip_pdf_actions(p: Path):
    """Take the scripts and launch actions out of a PDF, in place.

    Returns a list of what was removed, or None if the file could not be
    rewritten — only then is the upload refused. This runs on the rare book
    that really does carry an action, not on every upload, so the cost of
    rewriting a large file is only paid when there is something to remove.
    """
    try:
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import NameObject, ArrayObject
    except Exception:
        return None
    removed = []
    try:
        writer = PdfWriter(clone_from=str(p))
        root = writer._root_object
        for key in ("/OpenAction", "/AA"):
            if key in root:
                del root[NameObject(key)]
                removed.append("document " + key)
        names = root.get("/Names")
        names = names.get_object() if names is not None else None
        if names is not None:
            for key in ("/JavaScript", "/EmbeddedFiles"):
                if key in names:
                    del names[NameObject(key)]
                    removed.append("/Names" + key)
        for i, page in enumerate(writer.pages):
            if "/AA" in page:
                del page[NameObject("/AA")]
                removed.append(f"page {i + 1} /AA")
            annots = page.get("/Annots")
            if not annots:
                continue
            keep = []
            for a in annots:
                try:
                    act = a.get_object().get("/A")
                    kind = str(act.get_object().get("/S")) if act is not None else ""
                except Exception:
                    keep.append(a)
                    continue
                if kind in ("/JavaScript", "/Launch"):
                    removed.append(f"page {i + 1} annotation {kind}")
                    continue
                keep.append(a)
            if len(keep) != len(annots):
                page[NameObject("/Annots")] = ArrayObject(keep)
        tmp = p.with_name(p.name + ".clean")
        with open(tmp, "wb") as f:
            writer.write(f)
        os.replace(tmp, p)
    except Exception as e:
        print(f"[EV UPLOAD] could not strip active content from {p.name}: {type(e).__name__}: {e}", flush=True)
        return None
    # Whatever the structure said, make sure nothing is left that still reads as an action.
    return removed if not _PDF_ACTIVE.search(_pdf_scan(p)) else None


def _pdf_scan(p: Path) -> bytes:
    """Reads the PDF in pieces looking for active content, without holding a large book in memory."""
    found = b""
    with open(p, "rb") as f:
        tail = b""
        while True:
            chunk = f.read(4 * 1048576)
            if not chunk:
                break
            buf = tail + chunk
            m = _PDF_ACTIVE.search(buf)
            if m:
                return m.group(0)
            tail = buf[-64:]
    return found


# ---------------- response headers ----------------
CSP = ("default-src 'self'; img-src 'self' data: blob: https:; media-src 'self' blob: data:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src 'self' data: https://fonts.gstatic.com; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'")


def add_headers(request, response):
    h = response.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    h.setdefault("Permissions-Policy", "camera=(), geolocation=(), microphone=(self)")
    h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    if not request.url.path.startswith("/api/docs"):
        h.setdefault("Content-Security-Policy", CSP)
    if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.url.path.startswith("/api/") and "Cache-Control" not in h:
        h["Cache-Control"] = "no-store"
    return response


def client_ip(request) -> str:
    # The last address is the one our own proxy (Railway's edge, or Caddy) added. The first can be anything the
    # client typed, which let anyone dodge the sign-in limit by sending a made-up X-Forwarded-For.
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[-1].strip() if fwd else (request.client.host if request.client else "")) or "unknown"
