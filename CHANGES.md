# v49 (25 Nov): capacity

Load tested on PostgreSQL with 3,000 student accounts. As delivered, a 2 vCPU server took about 400 students reading at once
and froze at about 600; fixed, about 600 a process and about 1,200 with the 2 processes now set by default. Full numbers in
the capacity audit PDF.
- **Freeze under load fixed.** Requests held a database connection while waiting for a thread; a burst of about 40 used every
  connection and stopped the server for 30 seconds. API requests in progress are now capped at the number of connections, the
  rest queue, and a request that waits over 20 s gets "busy, try again". `db.py`, `main.py`.
- **2 web processes by default** (`WEB_CONCURRENCY`); only one runs background work. `Dockerfile`, `tasks.py`.
- **Books kept in memory for a minute** for progress saves, Home and opening a book. `content.load_ro`.
- **Compressed answers** over 1 KB.
- **Sign-in limit per internet address raised to 600 per 10 minutes** (a school shares one address), and it reads the address
  our own proxy adds, which a browser cannot fake. Per-account limits unchanged.
- New settings: THREADS, DB_POOL_SIZE, DB_MAX_OVERFLOW, DB_POOL_TIMEOUT, QUEUE_WAIT_SECONDS, WEB_CONCURRENCY, LOGIN_PER_IP_10MIN.
- `loadtest/`: the load test, to run against staging.

# v48 (25 Nov): the book looks like the textbook

## v51 - fixes from the review as each user

Student
- Chapter test questions without AI: never the same option twice; the meaning question asks which book sentence explains the word, and no other option mentions it, so there is one right answer.
- New hard questions: one book sentence has a word swapped, the student spots the wrong one. Questions come only from statements, not from exercises, aims or activities.
- Lists that print their own labels ("1.", "(a)") no longer get a second number; (a), (b) sit under their question.
- The book's own Keywords list counts as important words.
- Page view: running headers and footers are never marked as important words.
- Eddie sits in the right margin, his hint never covers the text or the explanation panel.
- Page view with the explanation open folds the topic list away so the page stays readable.
- Last unit says the book is finished, not "On to the next one".
- Home offers "Start reading" for a book the school gave, instead of "Find your textbooks".
- Progress shows "None practised yet" instead of 0% right.
- Social Science covers get their own art (they had the Science atom).
- No empty "Introduction" topic; a chapter title no longer repeats "Chapter 2" under "Unit 2".
- Demo data: only the book the sample fills is live, in English, with its real page count.

Teacher
- Class page shows each book: class average, who has not started, and each student's progress per book.

School admin
- Class cards list book titles, not just subjects.

Reviewer
- Tables have borders and a header row (the border colour was undefined).
- Publishing says "0 of N" with the same N the writing job shows.
- The original page is always the PDF page for a PDF upload (a failed render is retried); click it to zoom in.

Super admin
- Recent activity names the person, book or school instead of "user 1018"; unknown actions read as words.

## v50 - human review of M1 and M2

M1 (book reading) and the converter
- Chemistry and units keep their small numbers: CO(NH2)2, (NH4)2SO4 and m2 now print as subscripts and superscripts.
- (a), (b), (c) lists are read as lists, not merged into one paragraph with the text after them.
- Printed boxes are kept: the converter now reads M1's box marks, so Activity, Do you know and side panels come out as boxes instead of being missed or left as a marker.
- A shaded Keywords side panel stays text (it had become a picture) and is read after the text beside it, as a list.
- Match the columns (A / B) comes out as a two column table, not loose lines.
- Chapter titles keep the book's case ("and", not "And") and single spaces.
- Page check problems now show as reviewer flags on the page (they were only written to the ledger). No false alarm for the chapter title or for subscripts.

M2 (figures), round 2
- When a figure is not redrawn (no image model, kind switched off, no description), the reviewer is still offered the no-AI cleaned copy, unless it would look the same as the print.
- A redrawn picture keeps the printed figure's shape: it is padded, never stretched, so the page does not jump.
- After a redraw, the new picture is read back and any printed label it lost or misspelled is listed for the reviewer.
- A figure with no AI description but with a caption is described from its caption, so it is no longer flagged.
- scripts/m2_redraw_check.py tests the redraw path with the image model mocked.

M2 (figures)
- No-AI clean up no longer changes colours: flat artwork is left exactly as printed (brown soil had turned red, green seeds black). Photos get brightness contrast and a yellowed-paper fix that keeps hues.

## Page view
The reader can now show the printed page exactly as the textbook prints it: two columns, side boxes, text wrapped round
pictures and labels on diagrams all look like the book, because they are the book. The book's real text lies over the
page, invisible but selectable, so tapping highlighted words, selecting words to explain, highlighting and notes all work
as before. Laptops and tablets open in Page view, phones in Reading view (the flowing text), with a switch between them.

- Made while the book is processed: a WebP image of every page (about 50 KB a page, roughly 15 MB for a 300-page book)
  and the position of every printed line, in `<content_key>/layout/`. `backend/app/pagelayer.py`.
- Text positions come from the PDF. A scanned page has none, so its lines are laid out from M1's reading of the page;
  close, not exact, and marked "selection is approximate" on the page.
- Word books get Page view too when LibreOffice is in the image (it lays the book out as printed).
- Served through the paid-content route: a student who has not got the book cannot load its pages.
- `frontend/src/pages/student/PageView.jsx`, `pageview.css`; the reader picks the view and remembers it.

## The page check
Every converted page is compared with the printed page, and problems are flagged on that page for the reviewer:
words printed on the page that are missing from the digital page, text in a different order (columns, side boxes),
a picture missing, a picture cut off (ink on the printed page just outside its crop). Headers, page numbers and labels
inside pictures are left out of the comparison. A clean conversion gives no flags. The job shows "Page check: N
problem(s) flagged" when there are any.

## One printed figure is one picture
New M1 pass, `m1/eduverse_book2docx/figjoin.py`, after captions are bound:
- Sub-figures (a), (b) under one caption become one picture, labels included.
- Pieces of one picture that touch, with nothing between them, become one picture.
- Labels beside a diagram ("Petal", "Sepal", at the end of leader lines) stay in the picture instead of turning into
  body text.
- Joined figures are cut again from the page image as one rectangle.
- Two figures that each have their own caption are never joined.
- Settings: `join_figures`, `figure_join_gap_pt`, `figure_touch_gap_pt` (Super Admin, Book reading).
Also fixed: a caption is only paired with a figure on its own page (Figure 1.4 went to a picture on page 3); a word
broken by a hyphen at the end of a line is joined ("photo- synthesis"); a page whose text all ran on from the page
before now gets its review page (it blocked Publish); a table split across pages takes the caption printed under its
second half.

## Reviewer tools
- **Crop again on the original page** on every picture: drag a box on the printed page. Fixes a picture that is cut off,
  too tight or the wrong part. Tick other pieces on the page to join them into it.
- **Add a picture from this page**: a missing picture, or the second half of one that should be two (split).
- **Move up / move down** on every block: puts text back in the printed order.
- Crops are cut from the uploaded PDF at 200 DPI. `backend/app/routers/reviewtools.py`, `frontend/src/pages/reviewer/CropTool.jsx`.

## Security
- The original page images (`/api/review/books/{id}/pages/{n}/original.png`) answered anyone, signed in or not.
  Reviewers and Super Admin only now. The image cookie now covers `/api`, so plain images on the review screen carry it;
  every other endpoint still needs the Authorization header.

## Tested
A layout test book with two columns, a side box, a picture printed in two halves, sub-figures (a)/(b), a labelled
diagram with leader lines, a hyphenated line break, a footnote and a paragraph running onto the next page: 13 layout
checks pass, plus the 35 v47 checks, every API route as all five roles (0 server errors), every screen in Chrome, Page
view (tap, select and explain, highlight, switch views, phone width) and the crop tool by dragging a box.
Not tested here: scanned books read by a real model, Tamil-medium books. Send one of each to tune those.

# v47 (25 Nov): fixes from the full test audit

Every item below was reproduced first, then fixed and checked again by running it (35 automated checks, every API
route as all five roles, every screen in Chrome).

## It kept crashing
- **Error boundary.** One failing screen no longer blanks the whole app. The sidebar stays; the screen shows Reload and
  Go back; the error goes to the server log as `[EV CLIENT]` (`POST /api/client-error`). `frontend/src/ErrorBoundary.jsx`.
- **After a deploy.** A tab opened before a deploy used to go blank on its next click (the screen files are renamed on
  every build). It now reloads itself once and carries on. `main.jsx` (`vite:preloadError`).
- **Missing API routes.** `/api/...` paths nobody answers now get a JSON 404. Before, they got the web page with status 200,
  so screens received empty data and broke quietly. `main.py` `spa()`.
- **Flags and issues.** Its five endpoints were lost in an earlier build; the screen crashed. Restored in
  `routers/issues.py`: issues list, summary, mark fixed, books whose content file is missing, and the storage check.
  The server also prints `[EV STORAGE]` on start when files are on a disk that a deploy wipes.

## Your three bugs
- **Exam papers not visible to students.** A reviewer approving a paper now sets the pack live (it only happened on the
  Super Admin's Publish before). Blank questions block approval. `routers/exams.py` `_pack_live`.
- **No explanations after approval.** Publishing no longer starts a job it knows will fail. If the model cannot answer
  (for example Ollama on a cloud server) or the last attempt failed in the last 10 minutes, the reviewer is told the real
  reason instead of "being written", and no job is started. Writing ahead on publish now also runs when "approve before
  publishing" is off. A new install with `OPENAI_API_KEY` set starts on OpenAI, not Ollama. Write-ahead now also picks up
  bold terms and "X is the ... pigment/process/..." sentences, so far more words have saved explanations.
  `routers/learn.py` `explain_gate`, `explain_store.py` `provider_problem`, `seed.py`, `converter/keywords.py`.
- **Broken images.** TIFF, BMP, EMF and WMF pictures from Word books are converted to PNG when read
  (`webimage.py` in both `m1/` and `converter/`). Pictures in books converted before v47 are converted the first time they
  are opened and saved back. Any picture that still cannot load shows "Picture not available" instead of a broken icon
  (`BookImg` in `ui.jsx`). EMF and WMF need LibreOffice, now in the Docker image (`--build-arg OFFICE=0` leaves it out).

## Conversion
- Captions no longer swallow the sentence printed under them (`m1/lines.py`).
- A sentence with a formula inside it stays a sentence instead of becoming an equation with its spaces lost (`m1/mathtools.py`).
- A drawn diagram joined by lines stays one picture with its lines (`m1/sources/pdf_source.py` `_vector_regions`).
- A table that runs onto the next page is joined back into one table with the right header (`converter/__main__.py`).
- The reader opens on Unit 1, not on the title page.

## Smaller fixes
- Chapter test drafts are written when a textbook goes live, ready for the reviewer to approve.
- Exam questions are tagged using the chapter text, the options and the answer, not only titles.
- Mock tests use each exam's own marking (NEET UG and JEE Main +4/-1, CUET UG +5/-1, BITSAT +3/-1, KCET and state CETs +1/0).
  Check these each year in `taxonomy.py` `MARKING`.
- Edits to a paper students can already see cannot leave a question blank.
- Sign in gives the same answer for a wrong password and the wrong sign-in page, so it no longer confirms a password.
- A teacher's Nudge now appears on the student's Home.
- Notes can be edited in the Notebook. Audit log has "Check the log has not been changed".
- An individual learner's store opens on the exam or board they chose at sign up.
- The "Not sure" button is styled on exam pages.
- Demo: live demo books have content (a sample flow document is in `samples/`), so the demo student can read them.

## Still to check on your server
- Storage: open Flags and issues. If it says "Not safe", attach a Railway volume at `/data/storage` or use S3.
- AI settings: choose OpenAI (or Claude) and save the key, unless an Ollama server is really reachable.
- Memory: watch the memory graph while a large book is processed. If it nears the limit, run the worker as its own
  service (`ROLE=worker`, and `EMBEDDED_WORKER=0` on the API) so reading a book can never restart the website.
- Scanned books with a real model were not tested here (no model key in the test setup).

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
