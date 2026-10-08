from datetime import datetime
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
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
    # A plan with no end date cannot be renewed, because nothing knows it is
    # ending. This was the easiest money in the product to lose.
    plan_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    plan_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    price_per_seat: Mapped[float] = mapped_column(Float, default=0)
    contact_phone: Mapped[str] = mapped_column(String(40), default="")
    is_test: Mapped[bool] = mapped_column(Boolean, default=False)   # kept out of every total
    # A school buys a pool of questions a month, but each student draws only a
    # slice of it — otherwise the keenest reader in the class finishes the
    # whole allowance by Tuesday.
    ask_pool: Mapped[int] = mapped_column(Integer, default=5000)
    ask_pool_used: Mapped[int] = mapped_column(Integer, default=0)
    ask_per_student_day: Mapped[int] = mapped_column(Integer, default=10)
    discount_id: Mapped[int | None] = mapped_column(ForeignKey("discounts.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | suspended
    logo: Mapped[str] = mapped_column(Text, default="")  # data URL, set by the school admin
    rules: Mapped[dict] = mapped_column(JSON, default=dict)  # allowed depths, exam windows
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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
    fingerprint: Mapped[str] = mapped_column(String(80), default="", index=True)
    # A hash of the uploaded FILE. Kept apart from `fingerprint`, which the
    # converter overwrites with a hash of the text — both are useful, but only
    # this one answers "have we been given this exact file before".
    file_sha: Mapped[str] = mapped_column(String(80), default="", index=True)
    # What this book cost to produce, and how. A book is paid for once and
    # read by every school on that syllabus, so cost per school is the number
    # that matters — and it needs these to be worked out.
    cost_usd: Mapped[float] = mapped_column(Float, default=0)
    route_native: Mapped[int] = mapped_column(Integer, default=0)
    route_scanned: Mapped[int] = mapped_column(Integer, default=0)
    figures_n: Mapped[int] = mapped_column(Integer, default=0)
    split_by: Mapped[str] = mapped_column(String(20), default="")   # sections | headings | pages
    headings_n: Mapped[int] = mapped_column(Integer, default=0)
    content_key: Mapped[str] = mapped_column(String(300), default="")   # storage folder of the converted book (book.json, images/)
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
    book = relationship("Book")


class ReviewPage(Base):
    __tablename__ = "review_pages"
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), primary_key=True)
    page: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | approved | rejected
    comment: Mapped[str] = mapped_column(Text, default="")
    reviewer: Mapped[str] = mapped_column(String(160), default="")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class AskLog(Base):
    """Every question a student types, and whether it cost anything.

    Tapping a word is free, because that answer was written during review. This
    is the one place a model runs while somebody waits, so it is capped per
    student per day and every refusal is recorded — a refused question must not
    count against the quota, or students spend it testing the boundary.
    """
    __tablename__ = "ask_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    school_id: Mapped[int | None] = mapped_column(ForeignKey("schools.id"), index=True)
    book_id: Mapped[int | None] = mapped_column(ForeignKey("books.id"), nullable=True)
    section: Mapped[str] = mapped_column(String(20), default="")
    question: Mapped[str] = mapped_column(Text, default="")
    answered: Mapped[bool] = mapped_column(Boolean, default=False)
    refused_why: Mapped[str] = mapped_column(String(40), default="")  # off_topic | over_cap | pool_empty
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


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
