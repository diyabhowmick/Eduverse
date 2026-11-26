"""Make test students and the data loadgen.py needs. Run from backend/ with the same environment as the server:
    python ../loadtest/prepare.py <book_id> [students]
The book must be live and assigned to the demo class (Class 8 A of the first demo school). Only use on staging."""
import json, sys
sys.path.insert(0, ".")
from app.db import SessionLocal
from app.models import User, ClassRoom, ClassBook, School, Book
from app.security import make_token
from app import content as C
bid, n = int(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 1000
db = SessionLocal()
tmpl = db.query(User).filter(User.email == "student@eduverse.local").first()
sch = db.get(School, tmpl.school_id); sch.seats = max(sch.seats or 0, n + 100)
if not db.query(ClassBook).filter(ClassBook.class_id == tmpl.class_id, ClassBook.book_id == bid).first():
    db.add(ClassBook(class_id=tmpl.class_id, book_id=bid))
users = []
for i in range(n):
    e = f"load{i}@school.example"
    u = db.query(User).filter(User.email == e).first() or User(email=e, name=f"Load Student {i}", role="student", password_hash=tmpl.password_hash,
                                                              school_id=tmpl.school_id, class_id=tmpl.class_id, status="active")
    db.add(u); users.append(u)
db.commit()
json.dump([make_token(u) for u in users], open("../loadtest/tokens.json", "w"))
b = db.get(Book, bid); data = C.load(b, C.reader_key(b))
json.dump({"bid": bid, "pages": b.pages,
           "kws": [{"chapter": ch["number"], "keyword_id": k["id"], "term": k["term"]} for ch in data["chapters"] for k in ch.get("keywords", [])],
           "secs": [{"chapter": ch["number"], "section": s["id"]} for ch in data["chapters"] for s in ch["sections"] if s["number"]],
           "imgs": sorted({x["image"] for ch in data["chapters"] for x in ch["blocks"] if x["type"] == "figure"})},
          open("../loadtest/load_data.json", "w"))
print(n, "students ready")
