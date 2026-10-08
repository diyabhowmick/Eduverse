from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginIn(BaseModel):
    email: str
    password: str
    portal: str = "super_admin"


class AdminIn(BaseModel):
    name: str = Field(min_length=2)
    email: str
    phone: str = ""
    # A school admin belongs to one school. A platform admin belongs to none —
    # they run the factory, which is the same for every school.
    role: str = "admin"
    school_id: int | None = None
    password: str | None = None


class AdminPatch(BaseModel):
    name: str | None = None
    phone: str | None = None
    school_id: int | None = None
    status: str | None = None


class SchoolIn(BaseModel):
    name: str = Field(min_length=2)
    board: str
    medium: str = "English"
    city: str = ""
    contact_name: str = ""
    contact_email: str = ""
    academic_year: str = ""
    plan_id: int | None = None
    seats: int = 0
    discount_id: int | None = None
    status: str = "active"


class PlanIn(BaseModel):
    name: str
    price_per_seat: float = 0
    billing_cycle: str = "yearly"
    credits_per_seat: int = 0
    max_books: int = 0
    features: dict = {}
    active: bool = True


class DiscountIn(BaseModel):
    code: str
    percent: float = Field(gt=0, le=100)
    max_uses: int = 0
    valid_until: datetime | None = None
    active: bool = True


class BookIn(BaseModel):
    title: str
    subject: str
    board: str
    grade: str
    medium: str = "English"
    edition: str = ""
    pages: int = 0
    price: float = 0
    status: str = "upcoming"


class BookPatch(BaseModel):
    title: str | None = None
    subject: str | None = None
    board: str | None = None
    grade: str | None = None
    medium: str | None = None
    edition: str | None = None
    price: float | None = None
