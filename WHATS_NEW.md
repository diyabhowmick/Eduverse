# What was added

Built on the previous build. Five backend features, each tested by running it.

## 1 · Never pay twice for the same book

A hash of the uploaded **file** is stored separately from the converter's text
hash, because the converter overwrites that one. Upload the same file again:

```
409  We already have this book: Science Standard 8. It was processed on
     22 Sep 2026 and 4 classes already read it. Assign the existing one
     instead, or tick 'process anyway'.
```

`force=true` goes ahead anyway. This is the biggest saving available — one
textbook serves every school on that syllabus, so the same file arriving twice
should cost nothing.

**Tested:** first upload 200, same file 409, forced 200.

## 2 · Money and renewals

`School` now has `plan_start`, `plan_end`, `price_per_seat`, `contact_phone`
and `is_test`. **There was no renewal date anywhere before** — a plan simply
existed, which makes a renewal something you notice after it has passed.

Three endpoints, Super Admin only:

| | |
|---|---|
| `/api/money/overview` | billed, idle, renewing in 45 days, at risk, catalogue cost |
| `/api/money/needs-attention` | the home screen: seats nearly full, renewals due, schools gone quiet, schools that never onboarded, books stuck in review, books converted badly |
| `/api/money/books` | every book with its cost and cost per class |

`is_test` keeps a demo school out of every total, so you can try things without
moving a number you make decisions from.

## 3 · What each book cost

`backend/app/costing.py`, with the rates taken from your two real runs. `Book`
now records `cost_usd`, `route_native`, `route_scanned`, `figures_n`,
`split_by` and `headings_n`, written when the job finishes.

`/api/money/estimate` answers what a book **would** cost before anybody spends
it — and says plainly that a scanned book costs about three times a native one,
because every page has to be read.

## 4 · Platform Admin

A new role that splits the factory out of Super Admin: books, jobs, reviewers,
models, cost. **It cannot see what any school pays.** Super Admin can still do
everything. Uploading a book now requires `platform_admin`, which Super Admin
satisfies.

## 5 · The student ask quota

`/api/ask` — the one place a model runs while somebody waits. Four protections,
cheapest first:

- **The page goes with the question.** The model is given the paragraph and
  told to answer from it, so an answer cannot wander into something the book
  never said.
- **A word check before spending anything.** No overlap with the page, no API
  call at all.
- **A cap per student per day**, not per school. A shared pool sounds fairer
  and is not — the best reader in the class finishes it by Tuesday.
- **A refusal costs nothing.** Otherwise students spend the quota finding out
  where the edges are.

Every question is logged in `ask_log`, answered or refused, so a teacher can
see what a class asks.

**Tested:** off-topic refused and not counted · on-topic answered and counted ·
past the cap refused with a clear message and a reminder that tapping words is
still free.

## Not done

The demo screens are not wired up. These are the endpoints and the data behind
them; the React screens for money, books-by-demand, sign-in slips, the academic
year, reviewer keyboard shortcuts and the student ask box still need building.

Also not done: pre-generating explanations during review. That needs a job that
walks every keyword after conversion, and it is the largest remaining piece.

## After updating

Replace the folder and restart. The new columns are added automatically, so
existing data is kept.
