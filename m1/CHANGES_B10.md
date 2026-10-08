# B10 — the flow.docx clean-up

One model, and a docx that reads like the book.

Measured on the same 50 pages of the Class 8 Science book, both runs offline
so the geometry is compared on its own with no model in the way.

| | B9 | B10 |
|---|---|---|
| Two column pages found | 33 | 40 |
| Pages failing the gate | 42 | 14 |
| Overlapping block pairs | 75 | 24 |
| Pages with a broken reading order | 4 | 1 |
| Junk headings | 7 | 0 |
| Level 1 headings | 28 (26 of them junk) | 8 |
| Stray bullet marks | 54 | 0 |
| Binding tokens in the docx text | 22 | 0 |
| Description boxes in the docx | 69 | 22 |
| Figure files on disk with no block | 15 | 0 |
| Ledger | balanced | balanced |
| MathML elements in the digital book | 0 | 63 |

Tests: 450 pipeline checks and 40 server checks, all passing.

## One model

`ocr_model` and `vlm_model` are both `qwen3.5:4b`. The second model is gone
from the config, the client, the README and the comments. Nothing else in the
pipeline changed shape because of it.

## What was wrong, and what was done

**Two column pages read straight across.** The gutter search used one loose
threshold. A threshold high enough to forgive a banner crossing the gutter
also swallowed the ragged right edge of the left column, so the gutter came
back 120pt wide in the middle of the text and the page was called one column.
It is now a ladder, strictest first, stopping at the first rung that confirms
a gutter, plus a width test: wider than a fifth of the page is not a gutter.
Page 34 and eleven others now read their left column, then their right.

**Headings printed under their own text.** The badge promotion rule only fired
when the badge sat inside a panel with other content in it. PREFACE sits in
its own circle with nothing else inside, so it fell through and landed in the
middle of the paragraph that wraps around it. A badge with no panel now takes
the first block its own height overlaps.

**H1 was full of rubbish.** Level came from font size, so any short line in
large type became a heading, and 26 of 28 level 1 headings were map labels and
fraction legs. Three gates now: a heading has to read as words, it can never
be smaller than the body text, and a line starting with a digit is only a
numbered heading if what follows it looks like a title rather than arithmetic.
Level then comes from the book's own numbering, with unnumbered headings
printed larger than every numbered one placed at level 1.

**Text inside a picture became a heading.** A post pass over the finished book
demotes any heading whose box sits inside a figure.

**Table captions moved below their tables.** Captions were always emitted
after their target. A caption now remembers the side it was printed on, and
stays there.

**One photograph came out as five pictures.** Composite splitting is off by
default. When it is on, a split has to show a real gap measured on the page
and a caption for each part, or the region stays one figure.

**Binding tokens were visible in the document.** `[caption_of:...]` and
`[describes:...]` were hidden runs, which still sit in the text stream and
turn up in every copy and export. They travel as bookmarks now. The docx round
trip reads them back from the bookmark.

**Description boxes under every formula.** Switched off. `Equation
description (equation) equals 1000, LaTeX: = 1000` under a fragment is noise.
The flag brings them back for anyone who wants them, and the test suite covers
both states.

**Stray bullet marks.** A bullet and its sentence arrive as two blocks, so the
document held 54 paragraphs that were just a dot. The dot now joins the text
beside it and the pair becomes a list item.

**Half sentences wearing the same bullet.** This book prints its Wingdings
bullet once per LINE, so one sentence arrived as two overlapping blocks each
starting with the same mark. They are joined and the second mark is dropped.
The mark is the vulgar fraction three quarters, which `isalnum` calls a
number, which is why the first version of this fix silently did nothing.

**Stacked fractions split in two.** New `fractions.py` puts a numerator, its
rule and its denominator back together, keeping any prefix and suffix around
the fraction. The rule line is the evidence: nothing merges without one,
neither leg may be a sentence, no block is used twice, and the result is
dropped unless it validates as LaTeX.

**Greek letters glued to the next letter.** `unicode_to_latex` emitted
`\Delta` with nothing after it, so a delta printed beside a T became
`\DeltaT`, which is not a command. Every temperature formula in unit 4 failed
validation and cost a VLM call to re-read. One space closes the name.

**A recovered formula still reported as unreadable.** The VLM recovery path
cleared `math_unreadable` but left the `math:unsupported command` flag behind.
It is removed with the failure it describes.

**MathML was never produced.** `latex2mathml` was missing from requirements
and a bare `except` swallowed the ImportError, so every equation quietly
degraded to plain text while the scorecard still reported full coverage. It is
declared now, and its absence is reported once instead of hidden.

**OCR layout markup published as text.** A model that answers in its own
layout format (`title [24, 432, 132, 521]UNIT`) is detected and the tags are
stripped, keeping the words.

**Figure files with no block.** A crop dropped as a repeat still left its PNG
and JSON on disk, so the folder claimed content the book did not contain. They
are pruned after the book is written.

**The ledger was 14 short.** Extra parts of a split figure were counted at the
bottom of the loop, so a part dropped on the way down was never counted at
all. Counted at the top now. The fraction merge moves its block from emitted
to dropped rather than making one disappear.

**A failed gate still said ready.** The job status is `issues` when the gate
fails. `gate_passed` used to sit quietly inside the summary while the job
reported ready.

**The overlap gate cried wolf.** A unit opener prints MEASUREMENT across the
artwork, and reporting that as an overlap buried the ones that matter. Text
printed over a picture no longer counts; text landing on text still does.

## Still open

- 24 overlapping pairs remain, all text on text: two column question lists on
  a few pages, and fraction legs beside their own labels.
- One page still reports a non monotonic reading order.
- The 40 order inversions counted inside columns are mostly figures placed
  after the text that surrounds them, which is correct for a flow document.
- None of this has been run against a live model since the changes. The
  numbers above are the geometry half, measured offline.
