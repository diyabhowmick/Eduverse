# Why the reviewer saw "loading", and what changed

## What I did wrong first

I said the cause was a style name mismatch — M1 writing `EV Note` while the
converter looked for `EVNote`. **That was wrong.** The sample flow document uses
`EVNote`, M1's own output uses `EVNote`, and they match. I had read the code and
guessed instead of running it.

## What it actually is

Running both documents through the real backend function:

```
sample flow.docx  -> converter -> 46 review pages   reviewer loads
M1's flow.docx    -> converter ->  0 review pages   reviewer spins
```

Same code. The difference is what M1 hands over.

The converter found chapters only by looking for a printed section number:

```python
SEC_RE = re.compile(r"^\s*(\d{1,2})\.(\d{1,2})(?:\.(\d{1,2}))?\.?\s+(\S.*)$")
```

`1.1 Unit Systems` matches. `Chapter 1 Introduction` does not. `Introduction`
does not.

With no match, `chapter_starts` returned nothing, the converter emitted **zero
chapters**, `page_numbers()` returned an empty list, no `ReviewPage` rows were
written — and the reviewer's screen asked for `pages/undefined`.

It even said so, in a line that is easy to miss:

```
Untitled book |  | chapters [] of 0 in the index
sections 0 | figures 0 | tables 0 | equations 0
```

The styles tell the same story:

```
sample flow.docx : EVBody 901 · EVH1/H2/H3 present · EVNote 50
M1's flow.docx   : EVBody 6   · no heading styles  · EVNote 3
```

A scanned book whose headings the model could not label has no numbered
sections, so it could never be split, and therefore never reviewed.

## What changed

**A ladder of fallbacks, so every book splits somehow.**

| Tried | When it applies |
|---|---|
| **sections** | printed numbers like `1.1` — the good route, unchanged |
| **headings** | any heading style, numbered or not. Units numbered in the order they appear |
| **pages** | every page becomes a unit. Always possible, because every item knows its page |
| **whole** | nothing at all to go on — one unit holding everything |

The last two always succeed. A book split by page is not as good as one split by
chapter, but **the reviewer can work with it**, which is the point.

**And it says which route it took.** The report now carries `split_by` and a
`split_warning` in plain words:

> No section numbers and no headings were found, so every page became a unit.
> The text, figures and tables are all here, but the book has no chapter
> structure.

The warning is printed by the converter, stored on the job, and shown on the
Processing row. The job still finishes and the book still reaches the reviewer —
this is a warning, not a failure.

## Checked by running it

```
M1 output (no headings)    split_by=pages     pages=  3   OK
sample (proper headings)   split_by=sections  pages= 46   OK
```

Both reach the reviewer. Before this change the first produced nothing at all.

## Worth knowing

This makes the pipeline survive any book, but it does not make a book without
headings as good as one with them. If your books keep coming out as `split_by=
pages`, the thing to improve is **M1's heading detection on scanned pages** —
that is where the structure is being lost, and no amount of downstream fallback
recovers it.
