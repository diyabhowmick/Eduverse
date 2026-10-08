"""Core seed (always): the first Super Admin and default settings.
Demo seed (opt in): python -m app.seed --demo  fills sample schools, plans, books and activity."""
import random, sys
from pathlib import Path
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from .config import settings
from .models import User, Setting, Plan, Discount, School, Book, Job, UsageEvent, AuditLog, ClassRoom, ClassBook, StudentProgress, SchoolRequest
from .security import hash_pw
from .defaults import ALL


def ensure_core(db: Session):
    if not db.query(User).filter(User.role == "super_admin").first():
        db.add(User(email=settings.superadmin_email, name="Super Admin", role="super_admin",
                    password_hash=hash_pw(settings.superadmin_password)))
    # The factory needs an owner on day one, or the first book has to be
    # processed by the Super Admin — which is the job this role exists to take.
    if not db.query(User).filter(User.role == "platform_admin").first():
        db.add(User(email="platform@eduverse.local", name="Platform Admin",
                    role="platform_admin",
                    password_hash=hash_pw(settings.superadmin_password)))
    for k, v in ALL.items():
        if not db.get(Setting, k):
            db.add(Setting(key=k, value=v))
    db.commit()


def demo(db: Session):
    if db.query(School).count():
        print("Demo data already present"); return
    rnd = random.Random(7)
    now = datetime.utcnow()
    plans = [Plan(name="Starter", price_per_seat=499, billing_cycle="yearly", credits_per_seat=200, max_books=3,
                  features={"explain_panel": True, "notebook": False, "practice_questions": False}),
             Plan(name="Standard", price_per_seat=899, billing_cycle="yearly", credits_per_seat=600, max_books=8,
                  features={"explain_panel": True, "notebook": True, "practice_questions": False}),
             Plan(name="Premium", price_per_seat=1499, billing_cycle="yearly", credits_per_seat=2000, max_books=0,
                  features={"explain_panel": True, "notebook": True, "practice_questions": True})]
    db.add_all(plans); db.flush()
    discs = [Discount(code="LAUNCH20", percent=20, max_uses=50, used=6),
             Discount(code="GOVTSCHOOL30", percent=30, max_uses=0, used=2)]
    db.add_all(discs); db.flush()
    sch = [("Sri Vidya Mandir Matric School", "Coimbatore", 1, 320, None),
           ("Government Higher Secondary School", "Madurai", 0, 540, 1),
           ("St. Joseph's Matriculation School", "Chennai", 2, 260, 0),
           ("Kamaraj Vidyalaya", "Tiruchirappalli", 1, 180, None),
           ("Green Valley Public School", "Salem", 0, 120, None)]
    schools = []
    for name, city, pi, seats, di in sch:
        s = School(name=name, board="Tamil Nadu State Board", medium="English", city=city, academic_year="2026-27",
                   plan_id=plans[pi].id, seats=seats, discount_id=discs[di].id if di is not None else None,
                   contact_name="Principal", contact_email=name.split()[0].lower() + "@school.example",
                   created_at=now - timedelta(days=rnd.randint(20, 90)))
        db.add(s); schools.append(s)
    schools[-1].status = "suspended"
    db.flush()
    h = hash_pw("Student@123"); ha = hash_pw("Admin@123")
    first = ["Arun", "Divya", "Karthik", "Meena", "Suresh", "Priya", "Vignesh", "Anitha", "Ravi", "Lakshmi", "Kavya", "Rahul",
             "Nithya", "Sanjay", "Harini", "Gokul", "Deepa", "Pranav", "Swetha", "Ashwin"]
    last = ["S", "R", "K", "M", "P", "V", "N", "T"]
    students_by_school = {}
    for i, s in enumerate(schools):
        db.add(User(email=f"admin{i+1}@school.example", name=f"{first[i]} {last[i]}", role="admin", school_id=s.id,
                    password_hash=ha, phone="", last_login=now - timedelta(hours=rnd.randint(1, 90))))
        cls = [ClassRoom(school_id=s.id, grade=str(g), section=sec, class_teacher=f"{rnd.choice(first)} {rnd.choice(last)}")
               for g in (6, 7, 8, 9, 10) for sec in ("A", "B")]
        db.add_all(cls); db.flush()
        n = int(s.seats * rnd.uniform(0.55, 0.9))
        studs = []
        for k in range(n):
            c = cls[k % len(cls)] if k < n - 6 else None
            roll = f"{c.grade}{c.section}{k // len(cls) + 1:02d}" if c else ""
            u = User(email=f"s{s.id}_{k}@student.example", name=f"{rnd.choice(first)} {rnd.choice(last)}", role="student",
                     school_id=s.id, class_id=c.id if c else None, roll_no=roll, password_hash=h,
                     status="suspended" if k % 97 == 5 else "active")
            db.add(u); studs.append((u, c))
        students_by_school[s.id] = (cls, studs)
    db.flush()
    db.add(User(email="reviewer@eduverse.local", name="Content Reviewer", role="reviewer", password_hash=h))
    c8a = db.query(ClassRoom).filter(ClassRoom.school_id == schools[0].id, ClassRoom.grade == "8", ClassRoom.section == "A").first()
    db.add(User(email="student@eduverse.local", name="Kavya S", role="student", school_id=schools[0].id, class_id=c8a.id, roll_no="8A00", password_hash=h))
    db.add(User(email="reviewer2@eduverse.local", name="Kavitha R", role="reviewer", password_hash=h))
    bk = [("Science", "8", "live", 282, 249, "Tamil"), ("Science", "9", "rejected", 296, 249), ("Mathematics", "8", "processing", 240, 229),
          ("Science", "7", "processing", 212, 229), ("Social Science", "8", "live", 268, 229), ("Science", "10", "upcoming", 0, 279),
          ("Mathematics", "9", "upcoming", 0, 249), ("English", "8", "retired", 190, 199)]
    books = []
    for row in bk:
        subj, g, st, pages, price = row[:5]; med = row[5] if len(row) > 5 else "English"
        b = Book(title=f"{subj} Standard {g}" + (f" ({med} medium)" if med != "English" else ""), subject=subj, board="Tamil Nadu State Board", grade=g, medium=med,
                 edition="Revised 2020", pages=pages, price=price, status=st,
                 live_at=now - timedelta(days=30) if st == "live" else None)
        db.add(b); books.append(b)
    db.flush()
    books[1].review_note = "Pages 12 to 18: figures are cut in half in the scan. Rescan those pages and run M1 again."
    books[1].reviewed_by, books[1].reviewed_at = "reviewer@eduverse.local", now - timedelta(days=3)
    jobs = [(books[0], "done", 282, 282, ""), (books[1], "done", 296, 296, ""), (books[2], "done", 240, 240, ""),
            (books[3], "failed", 212, 41, "Page 42: VLM returned no JSON after one retry. Page image is 90 degrees rotated."),
            (books[4], "done", 268, 268, "")]
    for b, st, p, pd, err in jobs:
        db.add(Job(book_id=b.id, filename=f"{b.subject.lower().replace(' ', '_')}_std{b.grade}.pdf",
                   storage_key=f"originals/{b.id}/demo.pdf", status=st, pages=p, pages_done=pd, cost_credits=p,
                   error=err, triggered_by=settings.superadmin_email,
                   created_at=now - timedelta(days=rnd.randint(1, 25)),
                   finished_at=None if st == "running" else now - timedelta(days=rnd.randint(0, 5))))
    live = [b for b in books if b.status == "live"]
    # One demo teacher at the first school. They are given the classes that
    # actually have a book, so the teacher screens show real reading numbers
    # rather than a column of zeroes.
    first_sid = next(iter(students_by_school), None)
    if first_sid:
        fcls, _ = students_by_school[first_sid]
        t = User(email="teacher@eduverse.local", name="Lakshmi N", role="teacher",
                 school_id=first_sid, password_hash=h,
                 last_login=now - timedelta(hours=6))
        db.add(t); db.flush()
        with_book = [c for c in fcls if any(b.grade == c.grade for b in live)]
        for c in (with_book or fcls)[:3]:
            c.teacher_id = t.id
            c.class_teacher = t.name

    for sid, (cls, studs) in students_by_school.items():
        for c in cls:
            for b in live:
                if b.grade == c.grade:
                    db.add(ClassBook(class_id=c.id, book_id=b.id))
        for u, c in studs:
            if not c:
                continue
            for b in live:
                if b.grade == c.grade and rnd.random() > 0.08:
                    pct = max(0, min(100, rnd.gauss(46, 22)))
                    db.add(StudentProgress(user_id=u.id, book_id=b.id, percent=pct, minutes=int(pct * rnd.uniform(4, 9)),
                                           explanations=int(pct * rnd.uniform(0.5, 1.5)),
                                           last_read=now - timedelta(days=rnd.choice([0, 0, 1, 2, 3, 5, 9, 16]), hours=rnd.randint(0, 20))))
    db.add(SchoolRequest(school_id=schools[3].id, kind="seats", detail={"seats": 60}, created_by="admin4@school.example",
                         message="New Class 6 section opening in October.", created_at=now - timedelta(days=2)))
    db.add(SchoolRequest(school_id=schools[0].id, kind="book", detail={"book_title": "Mathematics Standard 7"}, created_by="admin1@school.example",
                         message="Needed for Class 7 before term 2.", created_at=now - timedelta(days=4)))
    db.add(SchoolRequest(school_id=schools[0].id, kind="plan", detail={"plan_id": plans[2].id, "plan": "Premium", "from": "Starter"},
                         created_by="admin1@school.example", status="declined", response="Please renew the Starter term first; we can move you in April.",
                         created_at=now - timedelta(days=20), resolved_at=now - timedelta(days=18)))
    for d in range(30):
        day = (now - timedelta(days=29 - d)).replace(hour=0, minute=0, second=0, microsecond=0)
        weekend = day.weekday() >= 5
        for s in schools[:-1]:
            for b in live:
                act = int(s.seats * rnd.uniform(0.18, 0.34) * (0.45 if weekend else 1) * (0.6 if b.subject != "Science" else 1) * (0.7 + d / 60))
                db.add(UsageEvent(day=day, school_id=s.id, book_id=b.id, active_students=act,
                                  reading_minutes=act * rnd.randint(18, 34), explanations=act * rnd.randint(3, 7),
                                  llm_tokens=act * rnd.randint(2500, 4200)))
    acts = [("plan.update", "plan", "2", {"name": "Standard", "price_from": 799, "price_to": 899}),
            ("school.create", "school", "4", {"name": "Kamaraj Vidyalaya"}),
            ("admin.create", "user", "4", {"email": "admin4@school.example"}),
            ("book.go_live", "book", "5", {"title": "Social Science Standard 8"}),
            ("job.create", "job", "4", {"file": "science_std7.pdf", "pages": 212}),
            ("school.update", "school", "5", {"status": "suspended"}),
            ("settings.ai", "setting", "ai", {})]
    for i, (a, t, tid, det) in enumerate(acts):
        db.add(AuditLog(at=now - timedelta(hours=6 * (len(acts) - i)), actor_email=settings.superadmin_email,
                        actor_role="super_admin", action=a, target_type=t, target_id=tid, detail=det))
    db.commit()
    sample = Path(__file__).resolve().parents[2] / "samples" / "tn_science_std8_flow.docx"
    if sample.exists():  # the real sample book goes through the converter into the review queue
        from .content import ingest_flow
        b = Book(title="", subject="", board="", grade="", medium="English", status="processing", price=249)
        db.add(b); db.flush()
        key = f"originals/{b.id}/tn_science_std8_flow.docx"
        from .storage import get_storage
        get_storage().put(key, sample.read_bytes()); b.flow_key = key
        b.assigned_reviewer_id = db.query(User).filter(User.email == "reviewer@eduverse.local").first().id
        ingest_flow(db, b, sample.read_bytes())
        db.add(Job(book_id=b.id, filename=sample.name, storage_key=key, status="done", pages=b.pages, pages_done=b.pages,
                   cost_credits=0, triggered_by=settings.superadmin_email, finished_at=datetime.utcnow()))
        db.commit()
    print("Demo data loaded")


def wait_for_db(engine, seconds: int = 60):
    """On a hosted platform the app container often starts before the database
    is accepting connections. Without this the very first deploy dies on a race
    and the log says "connection refused", which looks like a wrong password.
    """
    import time
    from sqlalchemy import text
    last = None
    for _ in range(seconds):
        try:
            with engine.connect() as con:
                con.execute(text("SELECT 1"))
            return
        except Exception as e:                      # noqa: BLE001 - any driver error
            last = e
            time.sleep(1)
    raise SystemExit(f"Database not reachable after {seconds}s: {last}")


if __name__ == "__main__":
    from .db import Base, engine, SessionLocal
    wait_for_db(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        ensure_core(db)
        if "--demo" in sys.argv:
            demo(db)
