# EduVerse: Super Admin, School Admin, Reviewer and Student

FastAPI + PostgreSQL backend, React (Vite) frontend, zPROx theme.

## Run
```
# backend
cd backend
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg://eduverse:eduverse@localhost:5432/eduverse   # or sqlite:///./eduverse.db for a quick try
export JWT_SECRET=<long random string>
export SUPERADMIN_EMAIL=you@company.com SUPERADMIN_PASSWORD=<strong password>
python -m app.seed            # creates the first Super Admin and default settings
python -m app.seed --demo     # optional: sample schools, plans, books and 30 days of activity
uvicorn app.main:app --port 8000

# frontend
cd frontend && npm install && npm run build   # backend serves frontend/dist at http://localhost:8000
# or: npm run dev   (http://localhost:5173, proxies /api to :8000)
```
Login pages: `/login/superadmin`, `/login/admin`, `/login/reviewer`, `/login/student`

Demo accounts (after `--demo`): school admins `admin1@school.example` to `admin5@school.example`, password `Admin@123` (admin5 belongs to a suspended school and is blocked).

## Config
| Variable | Default | Notes |
| --- | --- | --- |
| DATABASE_URL | local PostgreSQL | SQLite works for dev |
| STORAGE_BACKEND | local | `local` folder or `s3` |
| STORAGE_DIR | backend/data/storage | local only |
| S3_BUCKET, S3_REGION | | when STORAGE_BACKEND=s3 |
| M1_PATH | `../m1` | Where Module 1 (eduverse_book2docx) lives. M1 runs inside the backend; its settings are in Super Admin, Book extraction (M1) |
| JWT_SECRET, JWT_HOURS | | change in production |

## Super Admin features
Overview, Admins (create, edit, suspend, reset password, remove), Schools (plan, seats, discount, contract value),
Pricing (plans and discount codes), Book catalogue (go live only after reviewer approval, retire, restore, upcoming books),
Processing (upload to storage, M1 job queue, progress, cost, retry, cancel), AI settings (Ollama, Claude, OpenAI, limits,
M1 model, depth rules), Analytics, Platform settings (branding, feature toggles, role permissions), Audit log.

Super Admin also has School requests: approve or decline; approved seat and plan requests apply to the school at once.

## School Admin features
Every API call is scoped to the admin's own school (`/api/school/*`).
Overview (seats, weekly reading, attention items), Students (add, edit, suspend, reset password, remove, select many to
activate, suspend or move), bulk upload from CSV or Excel with a row by row check before saving and a logins file after,
Classes (sections, class teacher, assign live books within the plan's per class limit), Books (available and coming soon),
Analytics (class by class progress, students ahead and needing help), Learning rules (explanation depths, daily limit up to
the platform cap, exam mode windows per class), Requests to EduVerse (seats, plan, book, other), School profile and logo.
Seat limits are enforced on every add. A suspended school's admins and students cannot sign in.

## Reviewer
Processing takes a printed book (PDF or Word) or an M1 flow document (.docx).

Pipeline: printed book -> M1 (`m1/`, in-process, one book at a time, live page progress) -> flow.docx -> converter (`converter/`) -> M2 (figure redraw) -> reviewer -> published.

- **M1 settings** (Super Admin, Book extraction (M1)): every field of M1's `Config`, grouped, with defaults and help read from `m1/eduverse_book2docx/config.py`. Model provider Ollama (default qwen3.5:4b) or OpenAI. Check model button. Each job keeps a copy of the settings it ran with, plus M1's report.html and ledger.
- **M2 settings** (Super Admin, Figure redraw (M2)): diagrams, charts and maps M1 read as a structure are redrawn as SVG (free); other figures are generated from the description by OpenAI (gpt-image-1, dall-e-3), Google Gemini (Imagen 4, Gemini image models) or a local Stable Diffusion WebUI/Forge. Style prompt, size, kinds, images-per-book spend limit.
- **Reviewer**: sees Original vs New for each figure; Use new picture / Keep original / Edit description and redraw. A page cannot be approved while a new picture is waiting for a choice. Students see the chosen picture.
Either way the converted book is stored (`books/<id>/v<time>/` in local storage or S3) and lands in the review queue as In review.
It is never published by processing. The reviewer works page by page: original (rendered PDF page, or the M1 extraction for flow
uploads) next to the digital book; edit text, captions, equations and table cells; remove junk blocks; add or remove important
words; approve or reject each page with a comment. Publish is only possible when every page is approved; it sets the book live
for schools and students. Send back takes it out of the queue with a note for Super Admin. Every action is in the audit log.
Demo reviewer: `reviewer@eduverse.local` / `Student@123`. `--demo` loads `samples/tn_science_std8_flow.docx` into the queue.

## Student
Home (continue reading, streak, minutes, words explained, my books, coming soon), Store (syllabus and class picker; purchases are
recorded as demo purchases until a payment gateway is connected), and the Reader for published books: unit picker, topic rail,
bold clickable important words, select any words to explain, live explanations through `/api/explain` with the school's allowed
depths, exam windows and daily limit. Reading progress feeds School Admin and Super Admin analytics.
Demo student: `student@eduverse.local` / `Student@123` (Class 8 A). Publish the sample book as the reviewer first.
`AI_PROVIDER_OVERRIDE=mock` forces the offline test model for demos without an LLM.

Every change writes an audit entry.
