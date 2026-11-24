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

## Explanations written once, served from storage (v40, 23 Nov)

Students get the same explanations, but the model is asked once per book instead of once per student.

**Writing ahead** (AI usage, Write ahead, or automatically when a textbook goes live):
1. Level 1 for every highlighted word, as before.
2. One request per level 1 answer picks up to 4 hard words inside it, each with one line tying it back.
3. Each of those words is explained once for the whole book (`l2:` anchor), shared by every level 1 answer that uses it.

**Serving a tap:** a database read. The reader streams the saved text in a few words at a time so it feels live.
Level 2 words are underlined in the explanation. A word nobody prepared, and anything at level 3, is written
once and saved, so the next student gets it free. A reviewer sees these under Explanations, Written live.

**A typed question** is matched to what is saved before any model call:

| Match | What happens | Model |
|---|---|---|
| Same as an earlier student's question | that reply again | none |
| Close to another saved explanation | that explanation | none |
| Partly close | two or three lines on what is off, leading into the saved explanation | ~100 tokens |
| Nothing close | a full answer | as before |

Every reply the model writes is kept with the student's words. Matching is local and free by default (hashed
words, no model); OpenAI embeddings can be switched on in AI settings to also catch the same question in other words.

**New:** tables `explain_links`, `misconceptions`, `explain_vecs`; column `explanations.marked` (all added on start).
`explain_match.py`. AI settings, Saved explanations card. Explanations page for reviewers and Super Admin
(levels, written live, reported, student questions; edit, approve, retire, underline or remove a word).

**Approval before publishing (v41):** a textbook cannot go live, from the reviewer's Publish or Super Admin's Go live,
until every level 1 and level 2 explanation is approved and nothing reported is open. If nothing has been written
yet, publishing starts writing them and says so. Explanations page shows "To approve" per book and has
**Approve all** per tab. Both switches (write ahead on publish, approve before publishing) are in AI settings.

## Interface pass (v42, 23 Nov)

- **Reader:** the explanation opens as a drawer that slides in from the right (desktop) and closes with X; a bottom sheet on phones. The first highlighted word pulses until a student taps one.
- **One word style:** red dotted underline with a soft marker, the same in the book and inside explanations, light, dark and night.
- **Path chips:** density › particles as numbered chips; tap one to go back.
- **Ask Eddie:** typed questions are a chat under each explanation (bubbles, typing dots, saved answers stream in).
- **Student home:** "Continue reading" row, bigger book cards with a progress ring.
- **Reviewer Explanations:** list on the left; the book's own paragraph (or the sentence that leads to a level 2 word) beside the explanation, word highlighted. Keys: J K move, A approve and next, E edit, R retire.
- **Motion:** page fade and rise, staggered cards, press feedback, hover lift. All off under reduced motion. New file `motion.css`.

## 3D store and books (v43, 23 Nov)

- **Store, step 1, Choose your universe:** a card per school board (yours first), exam and university, with counts, class range and subjects. Cards lift and fan their books on hover; the card grows into its page (View Transitions, plain fade where not supported).
- **Step 2, the shelf:** class picker with a sliding red pill; books stand on a ledge and slide in from the side you moved towards. Exams switch with chips.
- **Step 3, the book up close:** large 3D book that turns slowly; "Turn it over" shows the chapter list on the back (years of papers for exam packs); "Open the book" swings the cover open, fans three pages and goes into the reader.
- **Book3D** (`Book3D.jsx`, `books3d.css`): real cover, spine, page edges and back in CSS 3D, leans towards the pointer with a moving sheen, red bookmark showing progress. Covers are drawn per subject (atoms, grid, map, letters, hexagons, waves, cell, code) when no cover image is uploaded. Board names only, no board logos.
- **Exam packs** are paper stacks with year tabs that fan out on hover.
- **Home and My books** use the same 3D books. Phones with little memory and reduced motion get flat covers.
- **New API:** `GET /api/student/store/segments`, `GET /api/student/store/books/{id}`.

## Security trunk (v44, 24 Nov)

See **SECURITY.md**. Book images now need a signed-in owner; shared replies need approval or three askers; login limits and lockout;
sessions end on password reset; API keys encrypted at rest; upload checks; security headers; hash-chained audit log; consent for
under 18s with data download and deletion request; durable task queue with a worker role; S3 signed image links; Docker Compose
for one box; non-root container. 27 security checks pass, plus the explanation and approval checks from v40 and v41.

## Study space: Notebook, Revise, Mistake book (v45, 24 Nov)

Built on the v44 security trunk. Everything is private to the learner and included in "Download my data".

- **Notebook** (new tab): notes, four-colour highlights, voice notes (up to 3 minutes, with a transcript when an OpenAI key is saved; never uses the learner's credits) and saved explanations. Search across all of it, filter by book or #tag, "Go to page", "Make a card".
- **Reader:** selecting words gives Explain, Note, Highlight and Voice. Highlights are painted into the book and notes get a margin marker. The side panel has four tabs: Explain, Notes, Saved, Mistakes. Every explanation has a Save star.
- **Not sure** on chapter tests, quick checks, Daily 5, mock tests and practice.
- **Mistake book:** every wrong or "not sure" answer from any test, practice or past paper, with your answer, the right one and the solution. Try again in place; it clears itself after two right answers on different days.
- **Revise** (new tab): today's cards (mistakes, not sure, saved explanations, words you opened three times or marked not helpful, notes you turned into cards), a 3D flip card rated Again, Hard, Good, Easy (keys 1 to 4), spaced 1, 3, 7, 14, 30, 60 days; revision streak; weak topics with a five-question Quick fix.
- **Home and menu:** "N cards to revise today" card and a count on the Revise tab.
- **New API** under `/api/student/study`; new tables `notes`, `saved_explanations`, `mistakes`, `topic_stats`, `review_cards`, `review_days` (created on start). Voice transcription runs on the task queue.

## AWS ready (v46, 24 Nov)

`deploy/aws/`: Terraform (VPC, EC2 with Docker Compose, RDS PostgreSQL 16 single-AZ with 7-day backups and point-in-time restore, private versioned S3, ECR, Secrets Manager, CloudWatch logs and alarms, Route 53, SSM instead of SSH), Caddy for HTTPS, and Windows scripts: `bootstrap.ps1`, `apply.ps1`, `deploy.ps1` (build, push, start, roll back if not ready), `backup-now.ps1`. The app reads its secrets from Secrets Manager (`AWS_SECRET_ID`), builds the RDS address from `DB_HOST`, and has `/api/ready`. See DEPLOY_AWS.md.
