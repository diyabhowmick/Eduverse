# EduVerse — all agreed changes

Built on **EduVerse_Code_4168**. Nothing outside this list is touched.

## The bug — a reviewer could not open a book

A book with no printed section numbers (`1.1`, `2.3` ...) produced **zero
chapters**, so no review pages were written and the reviewer's screen asked
for `pages/undefined`. Typical case: a scanned book whose headings M1 could not
label. Full diagnosis and fix in **PIPELINE_FIX.md**.

(An earlier note here blamed a style name mismatch, `EV Note` vs `EVNote`.
That was wrong: both documents use the same style. The space-insensitive match
in `reader.py` and the `page is not None` check in `content.py` stay as
harmless guards.)

## 1 · Remove a reviewer, hand over their books

`POST /api/reviewers/{id}/handover` moves every book they hold to another
reviewer. **Approved pages are kept** — approve 8 of 20 and the next reviewer
starts at page 9. Both names go to the audit log.

`DELETE /api/reviewers/{id}` refuses while they still hold books:

> Diya still has 3 books to review. Hand them to another reviewer first.

**On screen:** Reviewers now has **Hand over** and **Remove**.

## 2 · How long a reviewer is taking

Two new columns: **`assigned_at`** and **`last_opened_at`**. The list reports
`oldest_days`, `never_opened` and a tag.

| Tag | Means |
|---|---|
| Newly sent | assigned in the last two days |
| Never opened | a week old and never once opened |
| Oldest waiting | two weeks or more |

"Never opened" and "opened but stuck" are different problems and now read
differently.

**On screen:** a **Waiting** column, with the oldest book named.

## 3 · Teacher login

`/login/teacher` — **teacher@eduverse.local / Student@123**.

Four screens: **Home**, **My classes**, **a class**, **Analytics**. The teacher
is given the classes that actually have a book, so the demo shows real numbers.

A teacher cannot add, remove or suspend a student. That is the admin's job, and
it is the whole reason a teacher could not simply be given an admin account.
The one action they have is **Nudge**, which records the nudge and nothing else.

## 4 · Pull a published book back

`POST /api/books/{id}/pull_back` moves a book from **live** to **in_review**
with every approved page intact, so only what changed is checked and nothing is
reprocessed.

**On screen:** **Pull back**, beside Retire, on a live book.

## 5 · A school sees what happened to their request

A request links to the book it produced and reports its stage in plain words:

```
Planned · Being converted · Being checked · Checked, going live · Ready to assign
```

**On screen:** the school admin's Requests screen shows the stage instead of a
blank.

## 6 · Sending the model a smaller page

`ocr_dpi: int = 150` is new. The model gets a 150 DPI page; the reviewer's
compare view stays at 300, because it is drawn on a screen and costs nothing.

```
300 DPI → 8.4M pixels → about 10,700 image tokens per page
150 DPI → 2.1M pixels → about  2,700 image tokens per page
```

About **75% off** book processing, for no loss of accuracy — these models are
trained around 150 DPI.

## 7 · Stopping a job that has already started

Cancel existed, but only before a job began — so once M1 started reading you
were committed to the whole book, which is exactly when it costs money.

M1 is now checked for cancellation **once per page**, the only safe place to put
a half-read book down. Stopping is recorded as **cancelled**, not failed, and
the half-made book goes back to **upcoming**.

**On screen:** the button says **Stop** and shows while a job is running.

## Not done

**Batch processing.** No code for it, and it only saves money on a paid API.
Worth doing once enough books go through a paid provider.

## Tested, not assumed

Seeded a demo database and called the endpoints as each role:

```
super admin login  200
teacher login      200
reviewer login     200

REVIEWERS   Content Reviewer · 1 held · tag=Newly sent
PULL BACK   Science Standard 8 → 200 → status now: in_review
TEACHER     36 students · 2 classes · 41% average · 4 behind
            admin endpoint blocked: 403
```

---

## Upload failed, and books went missing — 20 Nov

Two separate faults, found by reading the platform's own limits rather than
guessing again.

### 1 · "Upload failed" on a textbook

Railway closes any request whose **body has not finished uploading within five
minutes** (Railway docs, Public Networking → Specs and limits). A Tamil Nadu
textbook PDF is 75–85 MB, which needs a steady 2.4 Mbps held for the whole five
minutes to arrive in one request. On an ordinary broadband line it does not get
there: the edge cuts the request off, **the backend never receives the file**,
and the browser is left with a failure that never reached the application —
which is why nothing appeared in the server log.

The browser now sends the file in **4 MB pieces**. Each piece is its own short
request, far inside every limit; a piece that fails is retried three times on
its own instead of restarting the book. A progress percentage shows while it
goes. The pieces are joined on the server by streaming, so an 85 MB book is
never held in memory, and the joined file is checked against the size the
browser declared before a job is created.

- `POST /api/jobs/upload/start` → `{upload_id, part_size}`
- `POST /api/jobs/upload/part` → one piece; sending the same piece again is safe
- `POST /api/jobs` now takes `upload_id` **or** a whole `file` as before

Verified end to end: their 85 MB 8th Science PDF through the real form, 21
pieces, byte-identical in storage (md5 match), 288 pages detected, job created
— including on a connection throttled to 400 KB/s.

### 2 · Books that open with "needs to be processed again"

Nothing in the application ever said **where** it was writing. A container's
own disk is thrown away on every deploy; only a mounted volume survives.

**Flags and issues** now opens with a *Where files are stored* card: the folder
in use, the mount it belongs to (read from `/proc/self/mounts`), whether a
write-read-delete probe succeeds, free space, and how much is actually held.
If the folder is not on a volume it says so in red, because that is the whole
explanation for a converted book disappearing.

`GET /api/books/storage-check`.

### 3 · Failures that said nothing

An unforeseen crash used to reach the browser as Starlette's plain-text
"Internal Server Error", which the frontend could not read, so everything
looked identical: *"Request failed"*.

- Any unhandled error now returns the real reason to a super admin or platform
  admin, and a neutral message to everybody else. The traceback always goes to
  the server log marked `[EV ERROR]`, which is searchable in Railway's log view.
- A 502 or 504 is named as the platform's proxy, not the application.
- A dropped connection says so instead of "Failed to fetch".
- A file that uploads but cannot be saved names the storage folder and the
  operating-system error.

### 4 · Flag counts were grey

`Tag` looked a status up in a tone table, so a tone passed in directly
(`bad`, `warn`) fell through to no colour — which silently greyed out every
flag count and status on the issues screen. Fixed in the shared component.

### 5 · `null value in column "file_sha"` — adding any book failed

A database carried forward from an **older build of EduVerse** still has that
build's columns: `books.file_sha`, `books.split_by`, `books.cost_usd`.
`create_all` adds tables and `add_missing_columns` adds columns, but neither
ever removes one. Those three are `NOT NULL` with no default, and nothing in
the current code knows to fill them — so **every insert into `books` failed**,
and it failed a long way from its cause: adding a book died on
`null value in column "file_sha"`.

`relax_legacy_columns()` runs at startup, after the other two. For each table
the models define, it finds columns the live database has that the models do
*not*, and which are `NOT NULL` with no default, and lifts only that
constraint. Columns the models own are never touched, primary keys are
skipped, no column is dropped and no data is changed. Each one is named in the
log as `[EV SCHEMA]`. PostgreSQL only — SQLite cannot alter a constraint and a
fresh file never has the problem.

Verified against a real PostgreSQL 16 carrying exactly those three legacy
columns: the insert failed with their error, and after the fix the same upload
succeeded. `id`, `title`, `status` and `pages` stayed `NOT NULL`; a second
start printed nothing further.
