# The screens for the v5 backend

v5 added endpoints with nothing to open them, which is why the app looked
unchanged. These are the screens.

## Money and renewals — new, Super Admin

`/sa/money`. Billed this year, seats actually used, money paid for and sitting
idle, and what is at risk. Then every renewal soonest first, with the contact
name and phone beside it, and a second table of schools whose seats are going
unused.

A school with 320 seats and 12 students shows as **never onboarded**. That is
the clearest early warning of churn there is, and nothing surfaced it before.

If no school has a plan end date, the table says so plainly rather than sitting
empty — without one, a plan can lapse with nobody noticing.

## Books by demand — new, Super Admin

`/sa/demand`. The business model on one screen:

```
Science Standard 8   $0.47   10 classes   $0.047 each
```

A book is paid for once and read by every class on that syllabus, so the number
that matters is cost **per class**, and it falls every time another class picks
the book up.

It also flags live books nobody reads — money already spent on the wrong grade —
and books that converted badly, where almost no headings were found and the
thing was split page by page.

**The estimator** at the top answers what a book would cost before anybody
spends it. Switch "has a text layer" to no and watch the page cost appear.

## The duplicate check — Processing

Upload a file the catalogue already has and the modal now explains rather than
erroring: which book it is, when it was processed, how many classes read it, and
two buttons — assign the existing one, or process it anyway.

## The ask box — the student reader

At the foot of the explanation panel, always visible, with **"4 left today"**
beside the heading and ten dots showing the quota.

Tapping a highlighted word stays free, because that answer was written while the
book was with a reviewer. A question the page cannot answer is refused **and
says it did not use one of your questions** — otherwise students spend the
allowance finding where the edges are.

## One correction made while testing

The cost note claimed a scanned book costs about three times a native one. That
is true of the **processing**, but not of the total once pre-generated
explanations are included — those cost the same either way. Both the API note
and the screen now say what actually differs:

```
native   $7.29
scanned  $8.15   — the page reading adds $0.86
```

## Checked

The frontend builds, every Python file parses, all four roles sign in, and every
endpoint the new screens call returns 200 against a seeded database.

One small repair along the way: `<Tag s="bad">` appears in several existing
screens but `bad` was not in the tone map, so those tags rendered with no colour.
The tone names now pass through.
