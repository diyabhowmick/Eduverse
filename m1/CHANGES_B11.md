# B11 — the column splice, the bullets and the fractions

Same 50 pages of the Class 8 Science book, both runs offline so the geometry is
compared with no model in the way.

| | B10 | B11 |
|---|---|---|
| Pages read as one column | 10 (8 of them wrongly) | 3 (1, 2, 4 — genuinely single column) |
| Blocks carrying a raw Wingdings glyph | 49 | 0 |
| Stacked fractions rebuilt | 5 | 24 |
| Pages failing the gate | 15 | 8 |
| Figure labels left in the text flow | 8 | 7 |
| Word coverage against the PDF text layer | 98.79% | 98.78% |
| Paragraphs duplicating a table cell | 0 | 0 |

Tests: 450 pipeline checks and 40 server checks, all passing.

## What was wrong, and what was done

**A two column row arrived spliced, and no column assignment could undo it.**
PyMuPDF groups by baseline, so one printed row of a two column page comes back
as a single line holding the left column and the right column joined together:
`a large wavelength, is deviated less while spherical, cylindrical, parabolic
and ellipsoid.` Placing that line in a column cannot separate it. `Line` now
carries its spans, and `lines.split_at_gutters` cuts a line at the gutter, but
only where no glyph sits inside the gutter, so a genuinely full width line is
never cut. `pdf_source` analyses the layout, cuts, then analyses again from the
cut lines.

**The gutter ladder could not survive a page that mixed layouts.** Page 36 is a
two column body over a full width glossary. The glossary rows put ink straight
through the gutter, so every coverage threshold either missed the gutter or
swallowed the ragged right edge of the left column. A last rung was added,
`_centre_corridor`: the narrow strip near the middle of the page crossed by the
fewest ROWS. Counting rows instead of ink lets eight full width rows be
outvoted by the forty that respect the columns. Pages 13, 15, 25, 36, 37, 38
and 46 now read their left column, then their right.

**A table's own column gap was being read as the page gutter.** With the
glossary now visible to the search, the gap between its label column and its
definitions came back as a second gutter and page 46 was called three columns.
A gutter that is CONTESTED, one that text crosses, now has to earn it: the rows
that read across it must cover a fair share of the text height, or it is a
table's internal gap. A gap nothing crosses is a plain column break and needs
no further proof, which is what keeps the synthetic sample passing.

**A banner across both columns was read as a left column line.** The GLOSSARY
heading is short, so it never crossed the gutter and never broke the band, and
the right column was published after it. `find_bands` now treats a panel drawn
across the gutter as a full width region, whatever the width of the text in it.

**Wingdings bullets were published as the vulgar fraction three quarters.** The
glyph byte was being taken as the character. Dingbat fonts are now mapped to
real bullet marks at read time, and the zero width copy of the same glyph that
the layout prints underneath is dropped. As a side effect the bullets now match
`BULLET_RE` in `structure.py`, so the lists are lists.

**Stacked fractions could not be rebuilt from blocks.** `fractions.rejoin` is
sound but could never fire on this book: the legs are not whole blocks and not
even whole spans, because the extractor puts the denominator of one fraction in
the same span as the words beside it (`4 radian = 180`). Characters carry their
own baseline origin, so `lines.fold_fraction_lines` takes only the glyphs
sitting on the rule, checks they form one unbroken run over it, rejects a leg
that opens with an operator, and folds the result back into the line it was
printed in. `I = (Q) / (t)`, `1 radian = (180°) / (π)` and `1° = (π) / (180)`
now come out whole. `fractions.rejoin` still runs afterwards for the cases the
span pass leaves alone.

**An equation printed on a diagram stayed in the flow.** `_absorb_labels_for`
only ever absorbed paragraphs and list items, so `r = s` printed on the arc of
a figure was published twice. Equations are absorbed too now, but only when
they sit squarely inside the figure, so a display equation directly beneath one
still belongs to the text.

## New settings, all defaulted

    centre_corridor_lo_frac        0.40
    centre_corridor_hi_frac        0.60
    centre_corridor_min_rows       10
    centre_corridor_max_cross_frac 0.32
    gutter_min_support_frac        0.45
    gutter_contested_lines         3
    fold_fractions_at_span_level   True
    fraction_rule_max_width_pt     170.0
    fraction_leg_max_rise_pt       13.0
    fraction_leg_max_drop_pt       17.0
    fraction_leg_max_chars         40

## Still open

Eight pages still raise an issue. They are two kinds, both narrower than what
they replaced:

- an equation whose legs the span pass declined, leaving two blocks that
  overlap (pages 32, 34, 44)
- two pieces of label text printed on top of each other inside a diagram
  (pages 11, 39, 45)

Composite figures are still captured whole rather than split into parts, and
the thresholds above were tuned on one book. Run the report on a second book
before trusting them.
