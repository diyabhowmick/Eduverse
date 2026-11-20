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
