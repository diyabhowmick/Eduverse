from datetime import datetime
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


class SealedJSON(TypeDecorator):
    """JSON whose secret fields (api_key and the like) are encrypted in the database and plain in Python."""
    impl = JSON
    cache_ok = True

    def process_bind_param(self, value, dialect):
        from .hardening import walk, seal
        return walk(value, seal) if value is not None else value

    def process_result_value(self, value, dialect):
        from .hardening import walk, unseal
        return walk(value, unseal) if value is not None else value
from .db import Base

ROLES = ("super_admin", "admin", "reviewer", "student")


def now():
    return datetime.utcnow()


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    price_per_seat: Mapped[float] = mapped_column(Float, default=0)
    billing_cycle: Mapped[str] = mapped_column(String(20), default="yearly")  # monthly | yearly
    credits_per_seat: Mapped[int] = mapped_column(Integer, default=0)
    max_books: Mapped[int] = mapped_column(Integer, default=0)  # 0 = unlimited
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Discount(Base):
    __tablename__ = "discounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    percent: Mapped[float] = mapped_column(Float)
    max_uses: Mapped[int] = mapped_column(Integer, default=0)  # 0 = unlimited
    used: Mapped[int] = mapped_column(Integer, default=0)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class School(Base):
    __tablename__ = "schools"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    board: Mapped[str] = mapped_column(String(80))
    medium: Mapped[str] = mapped_column(String(40), default="English")
    city: Mapped[str] = mapped_column(String(80), default="")
    contact_name: Mapped[str] = mapped_column(String(120), default="")
    contact_email: Mapped[str] = mapped_column(String(160), default="")
    academic_year: Mapped[str] = mapped_column(String(20), default="")
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id"), nullable=True)
    seats: Mapped[int] = mapped_column(Integer, default=0)
    discount_id: Mapped[int | None] = mapped_column(ForeignKey("discounts.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | suspended
    logo: Mapped[str] = mapped_column(Text, default="")  # data URL, set by the school admin
    rules: Mapped[dict] = mapped_column(JSON, default=dict)  # allowed depths, exam windows
    kind: Mapped[str] = mapped_column(String(20), default="school")  # school | college | coaching | other (B2B buyer type)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    plan = relationship("Plan")
    discount = relationship("Discount")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | suspended
    school_id: Mapped[int | None] = mapped_column(ForeignKey("schools.id"), nullable=True)
    phone: Mapped[str] = mapped_column(String(30), default="")
    class_id: Mapped[int | None] = mapped_column(ForeignKey("classes.id"), nullable=True)
    roll_no: Mapped[str] = mapped_column(String(40), default="")
    # Individual (B2C) learners have no organisation; they keep what they are studying here
    # so the store opens on the right shelf: {"track", "level", "board", "grade", "exam", "university", "course"}
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    signup: Mapped[str] = mapped_column(String(20), default="")  # "" = created by an organisation | self = signed up on their own
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)   # raised to sign out every session (password reset, suspension)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    school = relationship("School")
    klass = relationship("ClassRoom", foreign_keys=[class_id])


class ClassRoom(Base):
    __tablename__ = "classes"
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"), index=True)
    grade: Mapped[str] = mapped_column(String(20))
    section: Mapped[str] = mapped_column(String(20), default="")
    class_teacher: Mapped[str] = mapped_column(String(120), default="")
    # The teacher account that sees this class. The name above is left alone,
    # so a school that has not linked anyone is unaffected.
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ClassBook(Base):
    __tablename__ = "class_books"
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), primary_key=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class SchoolRequest(Base):
    __tablename__ = "school_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # seats | book | plan | other
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    message: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | approved | declined
    response: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(160), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # the book an approved book-request produced, so the school can follow it
    book_id: Mapped[int | None] = mapped_column(ForeignKey("books.id"), nullable=True)
    school = relationship("School")


class StudentProgress(Base):
    """Written by the student app as the student reads."""
    __tablename__ = "student_progress"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), primary_key=True)
    percent: Mapped[float] = mapped_column(Float, default=0)
    minutes: Mapped[int] = mapped_column(Integer, default=0)
    explanations: Mapped[int] = mapped_column(Integer, default=0)
    last_read: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sections: Mapped[list] = mapped_column(JSON, default=list)    # section ids the student has opened
    position: Mapped[dict] = mapped_column(JSON, default=dict)    # last chapter and section, to continue reading


class Purchase(Base):
    __tablename__ = "purchases"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"))
    price: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(20), default="demo")  # demo until a payment gateway is connected | paid | refunded
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class StudentDay(Base):
    """Per student per day, for daily limits and streaks."""
    __tablename__ = "student_days"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    day: Mapped[str] = mapped_column(String(10), primary_key=True)  # YYYY-MM-DD
    seconds: Mapped[int] = mapped_column(Integer, default=0)
    explanations: Mapped[int] = mapped_column(Integer, default=0)


class Book(Base):
    __tablename__ = "books"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(80))
    board: Mapped[str] = mapped_column(String(80))
    grade: Mapped[str] = mapped_column(String(20))
    medium: Mapped[str] = mapped_column(String(40), default="English")
    edition: Mapped[str] = mapped_column(String(40), default="")
    pages: Mapped[int] = mapped_column(Integer, default=0)
    price: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(20), default="processing")  # upcoming | processing | in_review | rejected | live | retired
    fingerprint: Mapped[str] = mapped_column(String(80), default="")
    content_key: Mapped[str] = mapped_column(String(300), default="")   # storage folder of the converted book (book.json, images/)
    live_key: Mapped[str] = mapped_column(String(300), default="")      # the published version students read; kept while a new version is processed and reviewed
    original_key: Mapped[str] = mapped_column(String(400), default="")  # storage key of the uploaded original
    flow_key: Mapped[str] = mapped_column(String(400), default="")      # storage key of the M1 flow document
    review_note: Mapped[str] = mapped_column(Text, default="")
    assigned_reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[str] = mapped_column(String(160), default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    live_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Product line. textbook = a digitised book. exam = an exam pack (past papers, recap, mock tests).
    track: Mapped[str] = mapped_column(String(20), default="textbook")
    level: Mapped[str] = mapped_column(String(20), default="school")   # school | degree | competitive
    exam: Mapped[str] = mapped_column(String(80), default="")          # exam packs: "Class 10 Board", "NEET UG", "Semester exam"
    university: Mapped[str] = mapped_column(String(160), default="")   # degree level
    course: Mapped[str] = mapped_column(String(120), default="")       # degree level, e.g. B.Sc Physics
    semester: Mapped[str] = mapped_column(String(20), default="")      # degree level
    linked_book_ids: Mapped[list] = mapped_column(JSON, default=list)  # exam packs: textbooks its questions are tagged against
    content_type: Mapped[str] = mapped_column(String(20), default="book")  # book | document | exam
    cover_key: Mapped[str] = mapped_column(String(400), default="")        # uploaded cover image, if any


class QuestionPaper(Base):
    """One past paper inside an exam pack."""
    __tablename__ = "question_papers"
    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), index=True)
    year: Mapped[int] = mapped_column(Integer)
    session: Mapped[str] = mapped_column(String(60), default="")       # March, Supplementary, Shift 1
    title: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")   # draft | in_review | approved | rejected
    source_key: Mapped[str] = mapped_column(String(400), default="")
    review_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_by: Mapped[str] = mapped_column(String(160), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    # AI reading and answering, run in a separate process
    ai_status: Mapped[str] = mapped_column(String(20), default="")     # "" | queued | running | done | failed
    ai_stage: Mapped[str] = mapped_column(String(40), default="")
    ai_done: Mapped[int] = mapped_column(Integer, default=0)
    ai_total: Mapped[int] = mapped_column(Integer, default=0)
    ai_error: Mapped[str] = mapped_column(Text, default="")


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("question_papers.id"), index=True)
    number: Mapped[str] = mapped_column(String(20), default="")
    section: Mapped[str] = mapped_column(String(60), default="")
    text: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSON, default=list)          # [{"key": "a", "text": "..."}] for MCQs
    answer: Mapped[str] = mapped_column(Text, default="")              # option key for MCQs, else short answer
    solution: Mapped[str] = mapped_column(Text, default="")
    marks: Mapped[float] = mapped_column(Float, default=0)
    chapter: Mapped[str] = mapped_column(String(200), default="")      # chapter of a linked textbook
    chapter_ref: Mapped[dict] = mapped_column(JSON, default=dict)      # {"book_id", "chapter"} to jump to the reader
    position: Mapped[int] = mapped_column(Integer, default=0)
    qtype: Mapped[str] = mapped_column(String(20), default="")         # mcq | multi | numeric | written
    answer_source: Mapped[str] = mapped_column(String(20), default="") # paper | key | ai | human
    confidence: Mapped[str] = mapped_column(String(10), default="")    # high | medium | low, for AI answers
    page: Mapped[int] = mapped_column(Integer, default=0)              # page of the original paper, from 1
    figure_key: Mapped[str] = mapped_column(String(400), default="")   # picture cropped from the original page: figure 1
    figures: Mapped[list] = mapped_column(JSON, default=list)          # storage keys of figures 2, 3, ... ("" where one failed);
                                                                       # the text says where each is printed with [[fig:N]]


class MockAttempt(Base):
    __tablename__ = "mock_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), index=True)
    question_ids: Mapped[list] = mapped_column(JSON, default=list)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    score: Mapped[float] = mapped_column(Float, default=0)
    total: Mapped[float] = mapped_column(Float, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    paper_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minutes: Mapped[int] = mapped_column(Integer, default=0)            # 0 = no time limit
    mark_correct: Mapped[float] = mapped_column(Float, default=0)       # 0 = each question's own marks
    mark_wrong: Mapped[float] = mapped_column(Float, default=0)         # taken off for a wrong answer
    time_taken: Mapped[int] = mapped_column(Integer, default=0)         # seconds
    times: Mapped[dict] = mapped_column(JSON, default=dict)             # seconds spent on each question


class QuestionProgress(Base):
    """What one student has done with one question: tried it, got it right or wrong, saved it for revision."""
    __tablename__ = "question_progress"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), index=True)
    status: Mapped[str] = mapped_column(String(10), default="")          # "" | correct | wrong
    bookmarked: Mapped[bool] = mapped_column(Boolean, default=False)
    tries: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[datetime] = mapped_column(DateTime, default=now)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int | None] = mapped_column(ForeignKey("books.id"), nullable=True)
    stage: Mapped[str] = mapped_column(String(20), default="M1")
    filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(400))
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued | running | done | failed | cancelled
    pages: Mapped[int] = mapped_column(Integer, default=0)
    pages_done: Mapped[int] = mapped_column(Integer, default=0)
    cost_credits: Mapped[float] = mapped_column(Float, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    triggered_by: Mapped[str] = mapped_column(String(160), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    kind: Mapped[str] = mapped_column(String(10), default="")  # book (printed book, runs M1) | flow (M1 output, convert only)
    extras_key: Mapped[str] = mapped_column(String(400), default="")  # M1 report, ledger and settings used
    note: Mapped[str] = mapped_column(Text, default="")  # warning on a job that still finished, e.g. book split by page
    # `stage` only ever holds where the job is NOW, and each stage overwrites
    # pages_done, so once a job moved on there was no way to tell whether it
    # spent forty minutes in M1 or in M2 — which is exactly what people ask
    # when a book takes too long. This keeps one entry per stage:
    #   {"M1 read": {"started": iso, "finished": iso, "pages": 212,
    #                "done": 212, "failed": 0, "error": ""}, ...}
    stages: Mapped[dict] = mapped_column(JSON, default=dict)
    book = relationship("Book")


class ReviewPage(Base):
    __tablename__ = "review_pages"
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), primary_key=True)
    page: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | approved | rejected
    comment: Mapped[str] = mapped_column(Text, default="")
    reviewer: Mapped[str] = mapped_column(String(160), default="")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # What kind of problem, and what would fix it. A free-text comment says what
    # one reviewer saw; a category can be counted, which is what tells you
    # whether the pipeline has a figure problem or a maths problem.
    # Categories and their default fix live in review.py FLAGS.
    category: Mapped[str] = mapped_column(String(20), default="", index=True)
    rerun: Mapped[str] = mapped_column(String(20), default="")   # m1 | m2 | converter | manual
    # A rejected page is an open issue. It becomes pending when somebody fixes
    # it (re-review needed), and approved when the fix is accepted — so the
    # page's own status already carries the whole issue lifecycle, and there is
    # no second table to disagree with it.
    fixed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fixed_by: Mapped[str] = mapped_column(String(160), default="")


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(SealedJSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class UsageEvent(Base):
    """Student activity rolled up per day; written by the student app, read by analytics."""
    __tablename__ = "usage_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[datetime] = mapped_column(DateTime, index=True)
    school_id: Mapped[int | None] = mapped_column(ForeignKey("schools.id"), nullable=True)
    book_id: Mapped[int | None] = mapped_column(ForeignKey("books.id"), nullable=True)
    active_students: Mapped[int] = mapped_column(Integer, default=0)
    reading_minutes: Mapped[int] = mapped_column(Integer, default=0)
    explanations: Mapped[int] = mapped_column(Integer, default=0)
    llm_tokens: Mapped[int] = mapped_column(Integer, default=0)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    actor_email: Mapped[str] = mapped_column(String(160))
    actor_role: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(60), index=True)
    target_type: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[str] = mapped_column(String(40), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64), default="")    # each entry carries the hash of the one before,
    hash: Mapped[str] = mapped_column(String(64), default="", index=True)  # so an edited or deleted entry breaks the chain


class Task(Base):
    """Durable background work. Survives restarts; any worker can pick it up; a dead worker's task is retried."""
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)           # m1 | prep | paper_ai
    args: Mapped[list] = mapped_column(JSON, default=list)
    key: Mapped[str] = mapped_column(String(120), index=True)           # kind and args, so the same work is never queued twice
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)   # queued | running | done | failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_by: Mapped[str] = mapped_column(String(80), default="")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Explanation(Base):
    """A saved explanation, shared by every student who asks the same thing in the same place.
    anchor names the place: a keyword in a chapter of one version of a book, a passage, an exam question,
    or a phrase inside another explanation (level 2). Several candidates can share an anchor and style;
    votes decide which one becomes final."""
    __tablename__ = "explanations"
    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(20))                       # book | question
    anchor: Mapped[str] = mapped_column(String(400), index=True)
    level: Mapped[int] = mapped_column(Integer, default=1)               # 1 = the word tapped, 2 = a phrase inside that answer
    style: Mapped[str] = mapped_column(String(30), default="concept_clarity")
    lang: Mapped[str] = mapped_column(String(20), default="English")
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("explanations.id"), nullable=True, index=True)
    book_id: Mapped[int | None] = mapped_column(ForeignKey("books.id"), nullable=True, index=True)
    question_id: Mapped[int | None] = mapped_column(ForeignKey("questions.id"), nullable=True, index=True)
    term: Mapped[str] = mapped_column(String(200), default="")
    text: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(80), default="")
    source: Mapped[str] = mapped_column(String(20), default="live")      # live | prepared | edited
    status: Mapped[str] = mapped_column(String(20), default="candidate") # candidate | final | retired | flagged
    shown: Mapped[int] = mapped_column(Integer, default=0)
    helpful: Mapped[int] = mapped_column(Integer, default=0)
    unhelpful: Mapped[int] = mapped_column(Integer, default=0)
    retries: Mapped[int] = mapped_column(Integer, default=0)            # "Explain differently" pressed on it
    reports: Mapped[int] = mapped_column(Integer, default=0)
    decided_by: Mapped[str] = mapped_column(String(160), default="")    # "votes" or the reviewer who chose it
    marked: Mapped[bool] = mapped_column(Boolean, default=False)         # its level 2 words have been picked out ahead of students
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Drawing(Base):
    """A drawing that goes with an explanation: a script (see draw_spec.py) compiled to SVG and checked by draw_check.py.
    Reviewed before a student sees it; only a final drawing is shown. explanation_id is empty while a drawing is
    compiled and checked before it is attached to anything."""
    __tablename__ = "drawings"
    id: Mapped[int] = mapped_column(primary_key=True)
    explanation_id: Mapped[int | None] = mapped_column(ForeignKey("explanations.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(20), default="geometry")     # geometry
    script: Mapped[str] = mapped_column(Text)                             # the JSON source
    svg: Mapped[str] = mapped_column(Text, default="")                    # the compiled output
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="candidate")  # candidate | final | rejected
    checks: Mapped[list] = mapped_column(JSON, default=list)              # what the gate found: [{severity, code, message}]
    model: Mapped[str] = mapped_column(String(80), default="")           # the model that wrote the script; empty when written by hand
    source: Mapped[str] = mapped_column(String(20), default="authored")   # authored | generated
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ExplainLink(Base):
    """A word inside a level 1 explanation that leads to a shared level 2 explanation.
    The level 2 text is written once per book; bridge is the one line that ties it back to this explanation."""
    __tablename__ = "explain_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int] = mapped_column(ForeignKey("explanations.id"), index=True)
    book_id: Mapped[int | None] = mapped_column(ForeignKey("books.id"), nullable=True, index=True)
    term: Mapped[str] = mapped_column(String(200))
    key: Mapped[str] = mapped_column(String(120), index=True)
    bridge: Mapped[str] = mapped_column(Text, default="")


class Misconception(Base):
    """A student's own words and the reply they got, kept so the next student who says the same thing is answered from here.
    explanation_id is the saved explanation the reply points into; empty when the reply was written in full."""
    __tablename__ = "misconceptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int | None] = mapped_column(ForeignKey("books.id"), nullable=True, index=True)
    root_id: Mapped[int | None] = mapped_column(ForeignKey("explanations.id"), nullable=True, index=True)
    explanation_id: Mapped[int | None] = mapped_column(ForeignKey("explanations.id"), nullable=True)
    sample: Mapped[str] = mapped_column(Text)
    reply: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20), default="bridge")     # bridge | full
    vec: Mapped[dict] = mapped_column(JSON, default=dict)
    vec_model: Mapped[str] = mapped_column(String(60), default="")
    hits: Mapped[int] = mapped_column(Integer, default=0)
    askers: Mapped[list] = mapped_column(JSON, default=list)            # distinct students who asked this; shared with others only after 3, or once approved
    status: Mapped[str] = mapped_column(String(20), default="candidate") # candidate | final | retired | held
    model: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ExplainVec(Base):
    """The matching vector of a saved explanation, worked out once."""
    __tablename__ = "explain_vecs"
    id: Mapped[int] = mapped_column(primary_key=True)
    explanation_id: Mapped[int] = mapped_column(ForeignKey("explanations.id"), index=True)
    book_id: Mapped[int | None] = mapped_column(ForeignKey("books.id"), nullable=True, index=True)
    model: Mapped[str] = mapped_column(String(60), default="local")
    vec: Mapped[dict] = mapped_column(JSON, default=dict)


class ExplanationVote(Base):
    __tablename__ = "explanation_votes"
    id: Mapped[int] = mapped_column(primary_key=True)
    explanation_id: Mapped[int] = mapped_column(ForeignKey("explanations.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    value: Mapped[str] = mapped_column(String(10))                       # up | down | report
    note: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime, default=now)


class AiUsage(Base):
    """Every model request and every saved explanation served, for the cost dashboard and the confusion map."""
    __tablename__ = "ai_usage"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)            # explain | explain_deep | prepare | paper_read | paper_answers | recap
    model: Mapped[str] = mapped_column(String(80), default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached: Mapped[bool] = mapped_column(Boolean, default=False)         # served from a saved explanation, no model call
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    book_id: Mapped[int | None] = mapped_column(ForeignKey("books.id"), nullable=True, index=True)
    term: Mapped[str] = mapped_column(String(200), default="")
    where: Mapped[str] = mapped_column(String(200), default="")          # chapter or question, in words


class PrepJob(Base):
    """Writing explanations ahead of students, for one book or exam pack."""
    __tablename__ = "prep_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), index=True)
    styles: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="queued")    # queued | running | done | failed
    total: Mapped[int] = mapped_column(Integer, default=0)
    done: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    started_by: Mapped[str] = mapped_column(String(160), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ChapterQuestion(Base):
    """A question on one chapter of a textbook, written from the book's own text and figures.
    Students only ever see approved ones; a reviewer checks every question first."""
    __tablename__ = "chapter_questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), index=True)
    chapter: Mapped[int] = mapped_column(Integer, index=True)
    section: Mapped[str] = mapped_column(String(80), default="")        # section id, to jump back into the reader
    section_title: Mapped[str] = mapped_column(String(200), default="")
    qtype: Mapped[str] = mapped_column(String(20), default="mcq")        # mcq | fill | figure
    level: Mapped[str] = mapped_column(String(10), default="easy")       # easy | medium | hard
    text: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSON, default=list)            # [{"key": "a", "text": ...}]
    answer: Mapped[str] = mapped_column(Text, default="")                # option key, or the word for fill-ins
    explanation: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(Text, default="")                # the sentence in the book it comes from
    figure: Mapped[dict] = mapped_column(JSON, default=dict)             # {"image", "number", "caption"} for figure questions
    status: Mapped[str] = mapped_column(String(12), default="draft", index=True)   # draft | approved | rejected
    origin: Mapped[str] = mapped_column(String(10), default="rules")     # rules | ai | human
    reviewed_by: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ChapterAttempt(Base):
    __tablename__ = "chapter_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), index=True)
    chapter: Mapped[int] = mapped_column(Integer)
    level: Mapped[str] = mapped_column(String(12), default="quick")      # quick | chapter | retry
    question_ids: Mapped[list] = mapped_column(JSON, default=list)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)            # {question_id: answer}
    wrong: Mapped[list] = mapped_column(JSON, default=list)
    taught: Mapped[list] = mapped_column(JSON, default=list)             # questions Eddie went through with the student
    fixed: Mapped[list] = mapped_column(JSON, default=list)              # mistakes the student then proved they had learned
    reasons: Mapped[dict] = mapped_column(JSON, default=dict)            # Daily 5: why each question was picked
    score: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    seconds: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class QuestionMemory(Base):
    """What Eddie remembers about one student and one chapter question: how often right or wrong,
    whether a mistake is still open, and when to bring it back (spaced repetition)."""
    __tablename__ = "question_memory"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("chapter_questions.id"), primary_key=True)
    book_id: Mapped[int] = mapped_column(Integer, index=True)
    right: Mapped[int] = mapped_column(Integer, default=0)
    wrong: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(10), default="")       # "" never missed | open | fixed
    box: Mapped[int] = mapped_column(Integer, default=0)              # 0..4, how well it has stuck
    due: Mapped[str] = mapped_column(String(10), default="")          # ISO date to bring it back
    last_answer: Mapped[str] = mapped_column(String(200), default="")
    last_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    fixed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ---------------- v45: the learner's own study space ----------------
class Note(Base):
    """A learner's note, highlight or voice note, tied to a spot in a book. Private to its owner."""
    __tablename__ = "notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    book_id: Mapped[int | None] = mapped_column(ForeignKey("books.id"), nullable=True, index=True)
    chapter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str] = mapped_column(String(80), default="")
    block_id: Mapped[str] = mapped_column(String(80), default="")      # the paragraph or figure it belongs to
    kind: Mapped[str] = mapped_column(String(12), default="note")      # note | highlight | voice
    quote: Mapped[str] = mapped_column(Text, default="")               # the words selected in the book
    body: Mapped[str] = mapped_column(Text, default="")
    color: Mapped[str] = mapped_column(String(10), default="yellow")   # yellow | red | green | blue
    tags: Mapped[list] = mapped_column(JSON, default=list)
    audio_key: Mapped[str] = mapped_column(String(300), default="")
    audio_type: Mapped[str] = mapped_column(String(40), default="")
    audio_secs: Mapped[int] = mapped_column(Integer, default=0)
    transcript: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class SavedExplanation(Base):
    """An explanation the learner kept. Points to the stored explanation, so saving costs nothing."""
    __tablename__ = "saved_explanations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    explanation_id: Mapped[int] = mapped_column(ForeignKey("explanations.id"), index=True)
    book_id: Mapped[int | None] = mapped_column(ForeignKey("books.id"), nullable=True, index=True)
    chapter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    path: Mapped[list] = mapped_column(JSON, default=list)              # the words tapped to get here: ["density", "particles"]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Mistake(Base):
    """One question the learner got wrong or was not sure about, from any test, practice or past paper.
    It clears itself after two right answers on different days."""
    __tablename__ = "mistakes"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    qsource: Mapped[str] = mapped_column(String(10))                   # chapter (ChapterQuestion) | exam (Question)
    question_id: Mapped[int] = mapped_column(Integer, index=True)
    origin: Mapped[str] = mapped_column(String(20), default="")        # Chapter test | Quick check | Daily 5 | Practice | Mock test | Quick fix
    book_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    chapter: Mapped[str] = mapped_column(String(200), default="")
    topic: Mapped[str] = mapped_column(String(200), default="")
    my_answer: Mapped[str] = mapped_column(String(300), default="")
    wrong_count: Mapped[int] = mapped_column(Integer, default=0)
    not_sure: Mapped[bool] = mapped_column(Boolean, default=False)
    right_days: Mapped[list] = mapped_column(JSON, default=list)        # days answered right since it opened
    status: Mapped[str] = mapped_column(String(10), default="open")    # open | cleared | dismissed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class TopicStat(Base):
    """Right and wrong answers per topic, for the weak topics list."""
    __tablename__ = "topic_stats"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    book_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic: Mapped[str] = mapped_column(String(200), primary_key=True)
    chapter: Mapped[str] = mapped_column(String(200), default="")
    qsource: Mapped[str] = mapped_column(String(10), default="chapter")
    right: Mapped[int] = mapped_column(Integer, default=0)
    tries: Mapped[int] = mapped_column(Integer, default=0)


class ReviewCard(Base):
    """A revision card. Comes back on a spaced schedule (1, 3, 7, 14, 30 days) until it is well known."""
    __tablename__ = "review_cards"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(12))                      # mistake | saved | note | word
    ref_id: Mapped[int] = mapped_column(Integer)
    book_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    front: Mapped[str] = mapped_column(Text, default="")
    back: Mapped[str] = mapped_column(Text, default="")
    where: Mapped[str] = mapped_column(String(200), default="")
    due: Mapped[str] = mapped_column(String(10), index=True)           # YYYY-MM-DD
    step: Mapped[int] = mapped_column(Integer, default=0)
    reps: Mapped[int] = mapped_column(Integer, default=0)
    lapses: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(10), default="active")  # active | done
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ReviewDay(Base):
    """Cards reviewed per day, for the revision streak."""
    __tablename__ = "review_days"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    cards: Mapped[int] = mapped_column(Integer, default=0)


# PostgreSQL refuses a NUL character anywhere in text or JSON, and one stray NUL from a PDF or a model
# reply failed a whole paper's save. Every question is scrubbed on its way in, however it was made.
from sqlalchemy import event


def _no_nul(v):
    if isinstance(v, str):
        return v.replace("\x00", "")
    if isinstance(v, list):
        return [_no_nul(x) for x in v]
    if isinstance(v, dict):
        return {_no_nul(k): _no_nul(x) for k, x in v.items()}
    return v


@event.listens_for(Question, "before_insert")
@event.listens_for(Question, "before_update")
def _scrub_question(mapper, connection, q):
    for f in ("number", "section", "text", "options", "answer", "solution", "chapter", "figure_key", "figures"):
        v = getattr(q, f, None)
        clean_v = _no_nul(v)
        if clean_v != v:
            setattr(q, f, clean_v)
