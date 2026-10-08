# Splitting Super Admin into two roles

Built on **EduVerse_Code_4168**. Nothing outside this list is touched.

Before this change there were six roles on paper and five that could sign in.
`platform_admin` existed as one line in `security.py`, guarded one endpoint, had
no login page, no screens, and no way to create such an account. It is now a
real login.

## The idea

| | Super Admin | Platform Admin |
|---|---|---|
| owns | the money | the factory |
| sees | schools, seats, prices, renewals | books, jobs, reviewers, keys, token spend |
| never sees | — | **what any school pays** |

The last row is the whole point, and it is enforced in the backend, not by
hiding menu items.

## Where the line is drawn

Cost and revenue are different numbers and they are guarded differently. The
factory has to see what processing costs or it cannot be asked to spend less;
it must never see what a school was charged.

```
revenue   /api/money/overview, /needs-attention     super_admin
          /api/pricing/*, /api/schools, /api/admins
          /api/analytics, /api/dashboard, /api/audit

cost      /api/money/books, /api/money/estimate     platform_admin
          /api/factory/*

factory   /api/books, /api/jobs, /api/pipeline/*    platform_admin
          /api/reviewers
```

`platform_admin = require("super_admin", "platform_admin")`, so **Super Admin can
still do everything Platform Admin can**. That is deliberate: being locked out of
your own pipeline on a Sunday is worse than a longer menu. Super Admin's nav
therefore keeps the factory screens below its own.

Verified by test, not by reading: a Platform Admin token gets **403** on
`/api/money/overview`, `/needs-attention`, `/api/pricing/plans`, `/api/schools`,
`/api/admins`, `/api/analytics`, `/api/dashboard`, `/api/audit` and `/api/settings/ai`,
and **200** on all ten factory endpoints. Admin, reviewer, teacher and student
tokens all get 403 on `/api/factory/*`.

## Making the account

The **Admins** screen now has a Role dropdown and lists both kinds. A platform
admin belongs to no school, so the School field disappears when that role is
chosen, and `PATCH` refuses to put a school on one afterwards — a school would
hand them that school's money screens.

Seeded on first run so the factory has an owner on day one:

```
platform@eduverse.local   /   same password as the Super Admin seed
```

Sign-in page: **`/login/platform`**.

## New screens

**Platform Admin** (`/pa`) — What needs doing, Catalogue and cost, Book
catalogue, Processing, Reviewers, Pipeline health, Keys and spending, Cost
settings, M1, M2, AI settings.

Three of those are new:

- **Pipeline health** — `GET /api/factory/health`. Success rate, minutes a page,
  failures *grouped by reason* so the same problem twenty times reads as one
  problem, how books came out (sections / headings / page-by-page), books stuck
  in review, and long books with no figures at all.
- **Keys and spending** — `GET /api/factory/keys`. All three API keys in one
  place with what each one does, because a key typed into one screen does
  nothing for the other two and that has caught people out. Plus catalogue
  spend, all time and this month.
- **Cost settings** — `GET`/`PUT /api/factory/cost-settings`. The six settings
  that actually move the bill. **It has no store of its own**: each value is read
  from and written back to where it already lives (M1 overrides, M2 settings, the
  AI setting), so this screen and the M1/M2/AI screens can never disagree. A
  second copy of "page quality" is exactly the mistake the three separate key
  screens already made.

**Super Admin** (`/sa`) — the index is now **What needs you today**
(`/api/money/needs-attention`): renewals inside 45 days, schools nearly out of
seats, schools gone quiet, schools that paid and never set up, books stuck in
review. Every row is a decision with money attached. The old statistics
dashboard is still there, moved to `/sa/numbers` and linked from the top of the
new screen.

## One shared bug fixed on the way

`.switch` in `styles.css` had `width`/`height` on a `<label>`, which is an inline
box — those are ignored. It only ever looked right because every existing use
sits inside a flex container, which blockifies it. In a table cell it collapsed
to a sliver. Adding `display:inline-block` fixes it everywhere; flex items ignore
the declaration, so no existing screen changes.

## Still to do

From the demo HTMLs, not started: pre-generating explanations during review (the
largest remaining backend piece), the reviewer's Explanations screen, School
Admin's Progress / Sign-in slips / Parent reports / Teachers / Academic year,
and Student's Practice / How I am doing / Saved for offline.
