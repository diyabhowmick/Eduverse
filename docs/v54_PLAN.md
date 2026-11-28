# v54 — the large view for explanations, merged onto the reader divider

Feature **A** of the 14-feature brief, rebased onto the uncommitted work that was already in
the tree (big-screen layout, reader divider, logo, login animation).

## Why this is a rebase and not a copy

v53 was built on commit `c572423`, which has no divider. Between then and now the working tree
gained a draggable divider, `wide.css`, `homeChunks.js` and the brand mark. Copying the v53
files over that tree would have deleted all of it: `Reader.jsx` and `main.jsx` are edited by
both pieces of work, in the same places.

So feature A was extracted as a patch against `c572423` and applied on top of the current
`Reader.jsx` instead. Three collisions had to be settled by hand.

### 1. `main.jsx` — two imports, not one

`import './wide.css'` and `import './focus.css'`, in that order. `focus.css` must load last
so it can override `motion.css`.

### 2. `motion.css` sizes the panel from `--sw`

The divider sets `--sw` and `motion.css` applies it:

```css
.sside-in { width: var(--sw, 400px); padding: 0 max(18px, calc((var(--sw,400px) - 760px)/2)) 24px }
```

In the large view that would have pinned the content to a 400-ish column in the middle of a
1500px window. Every rule in `focus.css` is therefore written as `.sside.focus …` — two
classes, so it outranks `motion.css`'s single-class rules whatever the load order.

**`--sw` itself is never touched.** The split the student dragged is still there when the
window closes. Verified: drag to 862px → open large → Esc → still 862px.

### 3. The divider has nothing to resize while the window is open

It is not rendered then (`panel && !narrow && !focus`), rather than hidden in CSS, so it also
leaves the window's tab order.

## The bug this merge caught in v53

`focus.css` positions the window with `position: fixed; left: 50%; transform: translate(-50%,-50%)`.
That silently did not centre.

`Layout.jsx` wraps every page in `.route-fx`, which carries `animation: mv-rise .34s … both`.
The animation's last keyframe is `transform: none`, but `animation-fill-mode: both` keeps that
keyframe applied forever, and `transform: none` **computes to `matrix(1,0,0,1,0,0)`** — an
identity transform, not `none`. Any transform makes an element the containing block for
`position: fixed` descendants. So the window centred on the content area rather than the
screen: measured 114px of gap on the left against 46px on the right.

It shipped in v53 because the v53 test only asserted that the panel grew and that Esc shrank
it; it never measured where the window actually was.

Fix: `Reader.jsx` puts `ev-focus` on `<body>` while the window is open, and `focus.css` has
`body.ev-focus .route-fx { animation: none; transform: none }`. Now 80px / 80px. It also means
the veil covers the topbar and the nav rail, which it previously could not — `.route-fx`'s
transform had been trapping it in a stacking context.

## The decision that shapes the whole feature

The panel is **not** moved into a dialog and **not** portalled. React reconciles by position:
moving `<aside class="sside">` anywhere else in the tree unmounts `ExplainPanel` and destroys
the trail, the Eddie conversation, the votes and the saved state — the one thing the large view
must not do. The `<aside>` keeps its exact place and a class turns it into a centred window.
The grid keeps its `--sw` column while the panel is out of flow, so the book never reflows.

## What the student sees

- **Expand** in the panel header, **F**, or **Esc** to come back; clicking the dimmed book also closes it.
- Window is 90vw (max 1500px), height fits the explanation between `min(440px, 60vh)` and 88vh,
  so a two-line definition does not sit in a mostly empty full-height window.
- **Reading comfort → "Explanations open"** → *Beside the book* / *Large*, stored in `ev_reader`.
- Phones are unchanged: the full-screen sheet already is the large view, and neither the divider
  nor the window appears below 1001px.

## Verification

50/50 automated checks, light and dark, plus a phone pass — no page errors.

Covering: divider renders and drags; the drag is saved to `ev_reader_split`; the window is 90vw
and viewport-centred; the inner content actually widens past the `--sw` column; `--sw` survives
the round trip; the divider disappears and returns; the veil covers the full screen including the
nav rail; body scroll locks and unlocks; `route-fx`'s transform is cleared; `ExplainPanel` receives
`layout="wide"`; F and Esc both work; phones never enter it.

Separate sweep at 2560 / 1440 / 390 across six student pages: no horizontal overflow, no failed
requests, logo loads everywhere. (`/api/voice/say` returns 503 in the test environment because no
voice provider is configured there — unrelated to this change.)

## Files

| File | |
|---|---|
| `frontend/src/focus.css` | new |
| `frontend/src/main.jsx` | one import |
| `frontend/src/ExplainPanel.jsx` | accepts `layout` |
| `frontend/src/pages/student/Reader.jsx` | focus state, keys, veil, Expand, body class, preference |

No backend file is touched. `Reader.jsx` keeps its CRLF line endings so the diff stays readable.

## Known, not fixed

On a phone the word title appears twice — once in the sheet header, once in the panel header.
It predates this work and was left alone to keep the diff honest.

## CHANGES.md entry

```
## v54 - explanations can open large

- **Expand an explanation to a centred window** (Expand, or F; Esc or the dimmed book closes it).
  The panel is not moved in the page, so the trail, the chat with Eddie, the votes and anything
  saved all survive the switch. The window fits the explanation rather than always filling the
  screen. `focus.css`, `Reader.jsx`, `ExplainPanel.jsx`, `main.jsx`.
- **Reading comfort** gained "Explanations open: Beside the book / Large".
- The divider's split is untouched by it and is still set the way you left it on the way back.
- Fixed: the window did not actually centre. `.route-fx` keeps an identity transform from its
  entrance animation's fill mode, which made it the containing block for the fixed window. It is
  cleared while the window is open, which also lets the dimming cover the topbar and nav rail.
```
