"""School Admin API. Every query is scoped to the signed-in admin's own school."""
import csv, io, re, secrets
from collections import defaultdict
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import (User, School, ClassRoom, ClassBook, Book, SchoolRequest, StudentProgress, UsageEvent,
                      AuditLog, Setting)
from ..security import require, hash_pw
from ..audit import log
from ..defaults import FEATURES, AI

router = APIRouter(prefix="/api/school", tags=["school admin"])
school_admin = require("admin")
DEPTHS = ["exam", "concept_clarity", "curiosity", "research"]


def my_school(db: Session, me: User) -> School:
    s = db.get(School, me.school_id) if me.school_id else None
    if not s:
        raise HTTPException(403, "No school linked to this account")
    return s


def seats_used(db, sid):
    return db.query(User).filter(User.school_id == sid, User.role == "student").count()


def feature(db, key):
    s = db.get(Setting, "features")
    return (s.value if s else FEATURES).get(key, False)


# ---------- overview and profile ----------
@router.get("/overview")
def overview(db: Session = Depends(get_db), me=Depends(school_admin)):
    s = my_school(db, me)
    used = seats_used(db, s.id)
    active = db.query(User).filter(User.school_id == s.id, User.role == "student", User.status == "active").count()
    classes = db.query(ClassRoom).filter(ClassRoom.school_id == s.id).count()
    cids = [c.id for c in db.query(ClassRoom.id).filter(ClassRoom.school_id == s.id)]
    books = db.query(ClassBook.book_id).filter(ClassBook.class_id.in_(cids)).distinct().count() if cids else 0
    week = datetime.utcnow() - timedelta(days=7)
    ev = db.query(UsageEvent).filter(UsageEvent.school_id == s.id, UsageEvent.day >= week).all()
    unassigned = db.query(User).filter(User.school_id == s.id, User.role == "student", User.class_id.is_(None)).count()
    no_books = sum(1 for c in cids if not db.query(ClassBook).filter(ClassBook.class_id == c).count())
    ids = [u.id for u in db.query(User.id).filter(User.school_id == s.id, User.role == "student")]
    idle = 0
    if ids:
        recent = {p.user_id for p in db.query(StudentProgress).filter(StudentProgress.user_id.in_(ids),
                                                                         StudentProgress.last_read >= week)}
        idle = len(set(ids) - recent)
    return {
        "school": {"name": s.name, "board": s.board, "medium": s.medium, "city": s.city, "academic_year": s.academic_year,
                   "logo": s.logo, "plan": s.plan.name if s.plan else "", "max_books": s.plan.max_books if s.plan else 0,
                   "credits_per_seat": s.plan.credits_per_seat if s.plan else 0},
        "seats": s.seats, "seats_used": used, "active_students": active, "classes": classes, "books": books,
        "week_minutes": sum(e.reading_minutes for e in ev), "week_explanations": sum(e.explanations for e in ev),
        "week_active": max((e.active_students for e in ev), default=0),
        "attention": {"unassigned_students": unassigned, "classes_without_books": no_books, "idle_students": idle,
                      "open_requests": db.query(SchoolRequest).filter(SchoolRequest.school_id == s.id, SchoolRequest.status == "open").count()},
        "recent": [{"at": a.at, "actor": a.actor_email, "action": a.action, "detail": a.detail}
                   for a in db.query(AuditLog).filter(AuditLog.actor_email.in_(
                       [u.email for u in db.query(User.email).filter(User.school_id == s.id, User.role == "admin")]))
                   .order_by(AuditLog.at.desc()).limit(8)],
    }


class ProfileIn(BaseModel):
    name: str = Field(min_length=2)
    city: str = ""
    contact_name: str = ""
    contact_email: str = ""
    academic_year: str = ""
    logo: str = ""


@router.get("/profile")
def get_profile(db: Session = Depends(get_db), me=Depends(school_admin)):
    s = my_school(db, me)
    return {"name": s.name, "board": s.board, "medium": s.medium, "city": s.city, "contact_name": s.contact_name,
            "contact_email": s.contact_email, "academic_year": s.academic_year, "logo": s.logo,
            "plan": s.plan.name if s.plan else "", "seats": s.seats}


@router.put("/profile")
def put_profile(body: ProfileIn, db: Session = Depends(get_db), me=Depends(school_admin)):
    s = my_school(db, me)
    if body.logo and (not body.logo.startswith("data:image/") or len(body.logo) > 400_000):
        raise HTTPException(422, "Logo must be a PNG, JPG or SVG image under 300 KB")
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    log(db, me, "school.profile", "school", s.id, name=s.name)
    db.commit()
    return get_profile(db, me)


# ---------- classes ----------
class ClassIn(BaseModel):
    grade: str = Field(min_length=1)
    section: str = ""
    class_teacher: str = ""


def class_out(db, c: ClassRoom):
    bids = [b.book_id for b in db.query(ClassBook).filter(ClassBook.class_id == c.id)]
    books = db.query(Book).filter(Book.id.in_(bids)).all() if bids else []
    return {"id": c.id, "grade": c.grade, "section": c.section, "class_teacher": c.class_teacher,
            "label": f"Class {c.grade}{(' ' + c.section) if c.section else ''}",
            "students": db.query(User).filter(User.class_id == c.id, User.role == "student").count(),
            "books": [{"id": b.id, "title": b.title, "subject": b.subject} for b in books]}


def own_class(db, me, cid) -> ClassRoom:
    c = db.get(ClassRoom, cid)
    if not c or c.school_id != me.school_id:
        raise HTTPException(404, "Class not found")
    return c


@router.get("/classes")
def classes(db: Session = Depends(get_db), me=Depends(school_admin)):
    rows = db.query(ClassRoom).filter(ClassRoom.school_id == me.school_id).all()
    rows.sort(key=lambda c: (int(c.grade) if c.grade.isdigit() else 99, c.grade, c.section))
    return [class_out(db, c) for c in rows]


@router.post("/classes")
def create_class(body: ClassIn, db: Session = Depends(get_db), me=Depends(school_admin)):
    grade, sec = body.grade.strip(), body.section.strip().upper()
    if db.query(ClassRoom).filter(ClassRoom.school_id == me.school_id, ClassRoom.grade == grade, ClassRoom.section == sec).first():
        raise HTTPException(409, "This class and section already exist")
    c = ClassRoom(school_id=me.school_id, grade=grade, section=sec, class_teacher=body.class_teacher)
    db.add(c); db.flush()
    log(db, me, "class.create", "class", c.id, grade=grade, section=sec)
    db.commit()
    return class_out(db, c)


@router.put("/classes/{cid}")
def update_class(cid: int, body: ClassIn, db: Session = Depends(get_db), me=Depends(school_admin)):
    c = own_class(db, me, cid)
    c.grade, c.section, c.class_teacher = body.grade.strip(), body.section.strip().upper(), body.class_teacher
    log(db, me, "class.update", "class", cid)
    db.commit()
    return class_out(db, c)


@router.delete("/classes/{cid}")
def delete_class(cid: int, db: Session = Depends(get_db), me=Depends(school_admin)):
    c = own_class(db, me, cid)
    n = db.query(User).filter(User.class_id == cid).count()
    if n:
        raise HTTPException(409, f"Move the {n} students in this class first")
    db.query(ClassBook).filter(ClassBook.class_id == cid).delete()
    log(db, me, "class.delete", "class", cid)
    db.delete(c); db.commit()
    return {"ok": True}


class BooksIn(BaseModel):
    book_ids: list[int]


@router.put("/classes/{cid}/books")
def set_class_books(cid: int, body: BooksIn, db: Session = Depends(get_db), me=Depends(school_admin)):
    c = own_class(db, me, cid)
    s = my_school(db, me)
    ids = list(dict.fromkeys(body.book_ids))
    limit = s.plan.max_books if s.plan else 0
    if limit and len(ids) > limit:
        raise HTTPException(422, f"Your {s.plan.name} plan allows {limit} books per class. Ask for a plan upgrade to add more.")
    books = db.query(Book).filter(Book.id.in_(ids)).all() if ids else []
    if any(b.status != "live" for b in books) or len(books) != len(ids):
        raise HTTPException(422, "Only live books can be assigned")
    db.query(ClassBook).filter(ClassBook.class_id == cid).delete()
    for b in ids:
        db.add(ClassBook(class_id=cid, book_id=b))
    log(db, me, "class.books", "class", cid, books=len(ids))
    db.commit()
    return class_out(db, c)


@router.get("/catalogue")
def catalogue(db: Session = Depends(get_db), me=Depends(school_admin)):
    s = my_school(db, me)
    books = db.query(Book).filter(Book.status.in_(("live", "upcoming"))).order_by(Book.grade, Book.subject).all()
    cls = {c.id: f"{c.grade}{c.section}" for c in db.query(ClassRoom).filter(ClassRoom.school_id == s.id)}
    assigned = defaultdict(list)
    for cb in db.query(ClassBook).filter(ClassBook.class_id.in_(list(cls))).all() if cls else []:
        assigned[cb.book_id].append(cls[cb.class_id])
    return [{"id": b.id, "title": b.title, "subject": b.subject, "board": b.board, "grade": b.grade, "medium": b.medium,
             "pages": b.pages, "status": b.status, "your_board": b.board == s.board, "classes": sorted(assigned[b.id])} for b in books]


# ---------- students ----------
class StudentIn(BaseModel):
    name: str = Field(min_length=2)
    email: str = ""
    roll_no: str = ""
    phone: str = ""
    class_id: int | None = None


class StudentPatch(BaseModel):
    name: str | None = None
    roll_no: str | None = None
    phone: str | None = None
    class_id: int | None = None
    status: str | None = None


def login_id(school_id: int, name: str, roll: str, db) -> str:
    base = re.sub(r"[^a-z0-9]+", ".", (roll or name).lower()).strip(".") or "student"
    cand, n = f"{base}.s{school_id}@eduverse.school", 1
    while db.query(User).filter(User.email == cand).first():
        n += 1; cand = f"{base}{n}.s{school_id}@eduverse.school"
    return cand


def student_out(u: User, prog=None):
    return {"id": u.id, "name": u.name, "email": u.email, "roll_no": u.roll_no, "phone": u.phone, "status": u.status,
            "class_id": u.class_id, "class": (f"{u.klass.grade}{(' ' + u.klass.section) if u.klass.section else ''}" if u.klass else ""),
            "last_login": u.last_login, "created_at": u.created_at,
            "progress": round(prog["percent"]) if prog else 0, "minutes": prog["minutes"] if prog else 0,
            "last_read": prog["last_read"] if prog else None}


def progress_map(db, ids):
    out = {}
    if not ids:
        return out
    for p in db.query(StudentProgress).filter(StudentProgress.user_id.in_(ids)):
        o = out.setdefault(p.user_id, {"percent": 0, "minutes": 0, "last_read": None, "n": 0})
        o["percent"] += p.percent; o["n"] += 1; o["minutes"] += p.minutes
        if p.last_read and (not o["last_read"] or p.last_read > o["last_read"]):
            o["last_read"] = p.last_read
    for o in out.values():
        o["percent"] /= max(1, o["n"])
    return out


@router.get("/students")
def students(class_id: int | None = None, q: str = "", status: str = "", db: Session = Depends(get_db), me=Depends(school_admin)):
    qy = db.query(User).filter(User.school_id == me.school_id, User.role == "student")
    if class_id == 0:
        qy = qy.filter(User.class_id.is_(None))
    elif class_id:
        qy = qy.filter(User.class_id == class_id)
    if status:
        qy = qy.filter(User.status == status)
    if q:
        like = f"%{q}%"
        qy = qy.filter(User.name.ilike(like) | User.email.ilike(like) | User.roll_no.ilike(like))
    rows = qy.order_by(User.class_id, User.roll_no, User.name).limit(2000).all()
    pm = progress_map(db, [u.id for u in rows])
    return [student_out(u, pm.get(u.id)) for u in rows]


def check_seats(db, s: School, adding: int):
    used = seats_used(db, s.id)
    if used + adding > s.seats:
        raise HTTPException(422, f"Not enough seats: {used} of {s.seats} used, {adding} to add. Request more seats first.")


@router.post("/students")
def add_student(body: StudentIn, db: Session = Depends(get_db), me=Depends(school_admin)):
    s = my_school(db, me)
    check_seats(db, s, 1)
    if body.class_id:
        own_class(db, me, body.class_id)
    email = body.email.lower().strip() or login_id(s.id, body.name, body.roll_no, db)
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "An account with this email already exists")
    pw = secrets.token_urlsafe(6)
    u = User(name=body.name.strip(), email=email, roll_no=body.roll_no.strip(), phone=body.phone, class_id=body.class_id,
             role="student", school_id=s.id, password_hash=hash_pw(pw))
    db.add(u); db.flush()
    log(db, me, "student.create", "user", u.id, name=u.name)
    db.commit(); db.refresh(u)
    return {**student_out(u), "temp_password": pw}


def own_student(db, me, uid) -> User:
    u = db.get(User, uid)
    if not u or u.role != "student" or u.school_id != me.school_id:
        raise HTTPException(404, "Student not found")
    return u


@router.patch("/students/{uid}")
def patch_student(uid: int, body: StudentPatch, db: Session = Depends(get_db), me=Depends(school_admin)):
    u = own_student(db, me, uid)
    ch = body.model_dump(exclude_unset=True)
    if ch.get("class_id"):
        own_class(db, me, ch["class_id"])
    if "status" in ch and ch["status"] not in ("active", "suspended"):
        raise HTTPException(422, "Status must be active or suspended")
    for k, v in ch.items():
        setattr(u, k, v)
    log(db, me, "student.update", "user", uid, **{k: v for k, v in ch.items() if k in ("status", "class_id")})
    db.commit(); db.refresh(u)
    return student_out(u)


class BulkIds(BaseModel):
    ids: list[int]
    action: str  # activate | suspend | move
    class_id: int | None = None


@router.post("/students/bulk-action")
def bulk_action(body: BulkIds, db: Session = Depends(get_db), me=Depends(school_admin)):
    if body.action == "move" and body.class_id:
        own_class(db, me, body.class_id)
    n = 0
    for uid in body.ids:
        u = own_student(db, me, uid)
        if body.action == "activate": u.status = "active"
        elif body.action == "suspend": u.status = "suspended"
        elif body.action == "move": u.class_id = body.class_id
        else: raise HTTPException(422, "Unknown action")
        n += 1
    log(db, me, f"student.bulk_{body.action}", "user", "", count=n)
    db.commit()
    return {"updated": n}


@router.post("/students/{uid}/reset-password")
def reset_student(uid: int, db: Session = Depends(get_db), me=Depends(school_admin)):
    u = own_student(db, me, uid)
    pw = secrets.token_urlsafe(6)
    u.password_hash = hash_pw(pw)
    log(db, me, "student.reset_password", "user", uid)
    db.commit()
    return {"email": u.email, "temp_password": pw}


@router.delete("/students/{uid}")
def delete_student(uid: int, db: Session = Depends(get_db), me=Depends(school_admin)):
    u = own_student(db, me, uid)
    db.query(StudentProgress).filter(StudentProgress.user_id == uid).delete()
    log(db, me, "student.delete", "user", uid, name=u.name)
    db.delete(u); db.commit()
    return {"ok": True}


# ---------- bulk upload ----------
ALIASES = {"name": ("name", "student name", "full name", "student"), "roll_no": ("roll_no", "roll no", "roll", "roll number", "admission no", "admission number"),
           "grade": ("grade", "class", "standard", "std"), "section": ("section", "sec", "division"),
           "email": ("email", "email id", "mail"), "phone": ("phone", "mobile", "parent phone", "contact")}
TEMPLATE = "name,roll_no,grade,section,email,phone\nKavya S,8A01,8,A,,9876500001\nRahul M,8A02,8,A,,\n"


def parse_rows(filename: str, data: bytes) -> list[dict]:
    if filename.lower().endswith((".xlsx", ".xlsm")):
        import openpyxl
        ws = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
        rows = [[("" if v is None else str(v).strip()) for v in r] for r in ws.iter_rows(values_only=True)]
    else:
        rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig", errors="replace"))))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return []
    head = [h.strip().lower() for h in rows[0]]
    col = {}
    for key, names in ALIASES.items():
        for i, h in enumerate(head):
            if h in names:
                col[key] = i; break
    if "name" not in col:
        raise HTTPException(422, "The first row must have column names, with at least a name column. Download the template.")
    out = []
    for r in rows[1:]:
        get = lambda k: (r[col[k]].strip() if k in col and col[k] < len(r) else "")
        g = get("grade")
        if g.endswith(".0"): g = g[:-2]
        out.append({"name": get("name"), "roll_no": get("roll_no").removesuffix(".0"), "grade": g,
                    "section": get("section").upper(), "email": get("email").lower(), "phone": get("phone").removesuffix(".0")})
    return out


@router.get("/students/template")
def template(_=Depends(school_admin)):
    return Response(TEMPLATE, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=students_template.csv"})


@router.post("/students/upload")
async def upload_students(file: UploadFile = File(...), commit: bool = Form(False), create_classes: bool = Form(True),
                          db: Session = Depends(get_db), me=Depends(school_admin)):
    if not feature(db, "school_bulk_upload"):
        raise HTTPException(403, "Bulk upload is turned off for this platform")
    if not file.filename.lower().endswith((".csv", ".xlsx", ".xlsm")):
        raise HTTPException(422, "Upload a CSV or Excel (.xlsx) file")
    s = my_school(db, me)
    rows = parse_rows(file.filename, await file.read())
    classes = {(c.grade, c.section): c for c in db.query(ClassRoom).filter(ClassRoom.school_id == s.id)}
    existing = {e for (e,) in db.query(User.email)}
    seen, report = set(), []
    for i, r in enumerate(rows, start=2):
        problems = []
        if len(r["name"]) < 2: problems.append("name missing")
        if r["email"] and ("@" not in r["email"]): problems.append("email looks wrong")
        if r["email"] and (r["email"] in existing or r["email"] in seen): problems.append("email already used")
        key = (r["grade"], r["section"])
        cls = "none"
        if r["grade"]:
            cls = "existing" if key in classes else ("new" if create_classes else "missing")
            if cls == "missing": problems.append(f"class {r['grade']}{r['section']} does not exist")
        if r["roll_no"] and (r["roll_no"], r["grade"]) in seen: problems.append("duplicate roll number")
        seen.add(r["email"]); seen.add((r["roll_no"], r["grade"]))
        report.append({"row": i, **r, "class_status": cls, "problems": problems})
    ok = [r for r in report if not r["problems"]]
    used = seats_used(db, s.id)
    summary = {"rows": len(report), "ready": len(ok), "with_problems": len(report) - len(ok),
               "seats_free": s.seats - used, "new_classes": sorted({f"{r['grade']}{r['section']}" for r in ok if r["class_status"] == "new"})}
    if not commit:
        return {"summary": summary, "rows": report}
    if len(ok) > s.seats - used:
        raise HTTPException(422, f"Only {s.seats - used} seats free for {len(ok)} students. Request more seats first.")
    creds = io.StringIO(); w = csv.writer(creds); w.writerow(["name", "roll_no", "class", "login_email", "password"])
    for r in ok:
        c = None
        if r["grade"]:
            key = (r["grade"], r["section"])
            c = classes.get(key)
            if not c:
                c = ClassRoom(school_id=s.id, grade=r["grade"], section=r["section"]); db.add(c); db.flush(); classes[key] = c
        pw = secrets.token_urlsafe(6)
        email = r["email"] or login_id(s.id, r["name"], r["roll_no"], db)
        db.add(User(name=r["name"], email=email, roll_no=r["roll_no"], phone=r["phone"], class_id=c.id if c else None,
                    role="student", school_id=s.id, password_hash=hash_pw(pw)))
        db.flush()
        w.writerow([r["name"], r["roll_no"], f"{r['grade']}{r['section']}", email, pw])
    log(db, me, "student.bulk_upload", "school", s.id, added=len(ok), file=file.filename)
    db.commit()
    return {"summary": {**summary, "added": len(ok)}, "credentials_csv": creds.getvalue()}


# ---------- analytics ----------
@router.get("/analytics")
def analytics(days: int = 30, db: Session = Depends(get_db), me=Depends(school_admin)):
    s = my_school(db, me)
    since = datetime.utcnow() - timedelta(days=days)
    daily = defaultdict(lambda: {"active": 0, "minutes": 0, "explanations": 0})
    books = defaultdict(lambda: {"minutes": 0, "explanations": 0})
    for e in db.query(UsageEvent).filter(UsageEvent.school_id == s.id, UsageEvent.day >= since):
        d = daily[e.day.date().isoformat()]
        d["active"] += e.active_students; d["minutes"] += e.reading_minutes; d["explanations"] += e.explanations
        books[e.book_id]["minutes"] += e.reading_minutes; books[e.book_id]["explanations"] += e.explanations
    titles = {b.id: b.title for b in db.query(Book)}
    studs = db.query(User).filter(User.school_id == s.id, User.role == "student").all()
    pm = progress_map(db, [u.id for u in studs])
    per_class = defaultdict(lambda: {"students": 0, "progress": 0.0, "minutes": 0, "active_week": 0})
    week = datetime.utcnow() - timedelta(days=7)
    for u in studs:
        k = f"{u.klass.grade}{(' ' + u.klass.section) if u.klass.section else ''}" if u.klass else "No class"
        c = per_class[k]; p = pm.get(u.id)
        c["students"] += 1
        if p:
            c["progress"] += p["percent"]; c["minutes"] += p["minutes"]
            if p["last_read"] and p["last_read"] >= week: c["active_week"] += 1
    classes = [{"class": k, "students": v["students"], "avg_progress": round(v["progress"] / max(1, v["students"])),
                "hours": round(v["minutes"] / 60), "active_week": v["active_week"]} for k, v in per_class.items()]
    classes.sort(key=lambda c: (c["class"] == "No class", [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", c["class"])]))
    ranked = sorted([student_out(u, pm.get(u.id)) for u in studs], key=lambda x: -x["progress"])
    return {"daily": [{"day": k, **v} for k, v in sorted(daily.items())],
            "books": sorted([{"book": titles.get(k, ""), **v} for k, v in books.items()], key=lambda x: -x["minutes"]),
            "classes": classes, "top": ranked[:8], "needs_help": [r for r in ranked if r["status"] == "active"][-8:][::-1]}


# ---------- rules ----------
class Window(BaseModel):
    name: str
    start: str
    end: str
    class_ids: list[int] = []


class RulesIn(BaseModel):
    allowed_depths: list[str]
    daily_explanations: int = Field(ge=0)
    exam_windows: list[Window] = []


def platform_cap(db):
    s = db.get(Setting, "ai")
    return (s.value if s else AI).get("daily_explanations_per_student", 100)


@router.get("/rules")
def get_rules(db: Session = Depends(get_db), me=Depends(school_admin)):
    s = my_school(db, me)
    cap = platform_cap(db)
    r = {"allowed_depths": DEPTHS, "daily_explanations": cap, "exam_windows": [], **(s.rules or {})}
    return {**r, "platform_cap": cap}


@router.put("/rules")
def put_rules(body: RulesIn, db: Session = Depends(get_db), me=Depends(school_admin)):
    s = my_school(db, me)
    if not body.allowed_depths or any(d not in DEPTHS for d in body.allowed_depths):
        raise HTTPException(422, "Keep at least one explanation depth on")
    cap = platform_cap(db)
    if body.daily_explanations > cap:
        raise HTTPException(422, f"The platform limit is {cap} explanations per student per day")
    for w in body.exam_windows:
        if not w.start or not w.end or w.end < w.start:
            raise HTTPException(422, f"Exam window '{w.name}' needs a start date before its end date")
        for cid in w.class_ids:
            own_class(db, me, cid)
    s.rules = body.model_dump()
    log(db, me, "school.rules", "school", s.id, windows=len(body.exam_windows))
    db.commit()
    return {**s.rules, "platform_cap": cap}


# ---------- requests to Super Admin ----------
class RequestIn(BaseModel):
    kind: str
    message: str = ""
    seats: int | None = None
    plan_id: int | None = None
    book_title: str = ""


# Words a school admin understands, instead of the internal status name.
BOOK_STAGE = {"upcoming": "Planned", "processing": "Being converted",
              "in_review": "Being checked", "approved": "Checked, going live",
              "live": "Ready to assign", "rejected": "Sent back for another look",
              "retired": "Withdrawn"}


def req_out(r: SchoolRequest, db=None):
    d = {"id": r.id, "kind": r.kind, "detail": r.detail, "message": r.message, "status": r.status, "response": r.response,
            "created_by": r.created_by, "created_at": r.created_at, "resolved_at": r.resolved_at, "school": r.school.name if r.school else ""}
    bid = getattr(r, "book_id", None)
    if bid and db is not None:
        b = db.get(Book, bid)
        if b:
            d["book"] = {"id": b.id, "title": b.title,
                         "stage": BOOK_STAGE.get(b.status, b.status),
                         "ready": b.status == "live"}
    return d



@router.get("/requests")
def my_requests(db: Session = Depends(get_db), me=Depends(school_admin)):
    return [req_out(r, db) for r in db.query(SchoolRequest).filter(SchoolRequest.school_id == me.school_id).order_by(SchoolRequest.created_at.desc())]


@router.get("/plans")
def plans_for_upgrade(db: Session = Depends(get_db), me=Depends(school_admin)):
    from ..models import Plan
    return [{"id": p.id, "name": p.name, "price_per_seat": p.price_per_seat, "billing_cycle": p.billing_cycle, "max_books": p.max_books,
             "credits_per_seat": p.credits_per_seat, "features": p.features} for p in db.query(Plan).filter(Plan.active.is_(True)).order_by(Plan.price_per_seat)]


@router.post("/requests")
def create_request(body: RequestIn, db: Session = Depends(get_db), me=Depends(school_admin)):
    s = my_school(db, me)
    detail = {}
    if body.kind == "seats":
        if not body.seats or body.seats < 1: raise HTTPException(422, "Enter how many more seats you need")
        detail = {"seats": body.seats}
    elif body.kind == "plan":
        from ..models import Plan
        p = db.get(Plan, body.plan_id or 0)
        if not p: raise HTTPException(422, "Choose a plan")
        if p.id == s.plan_id: raise HTTPException(422, "You are already on this plan")
        detail = {"plan_id": p.id, "plan": p.name, "from": s.plan.name if s.plan else ""}
    elif body.kind == "book":
        if not body.book_title.strip(): raise HTTPException(422, "Name the book you need")
        detail = {"book_title": body.book_title.strip()}
    elif body.kind != "other":
        raise HTTPException(422, "Unknown request type")
    if body.kind == "other" and not body.message.strip():
        raise HTTPException(422, "Describe what you need")
    r = SchoolRequest(school_id=s.id, kind=body.kind, detail=detail, message=body.message.strip(), created_by=me.email)
    db.add(r); db.flush()
    log(db, me, "request.create", "request", r.id, kind=body.kind, **detail)
    db.commit(); db.refresh(r)
    return req_out(r)
