# B14 - fixes from the Phase 1 page review (pages 1 to 15)

Every item in "Eduverse Changes - Phase 1" was traced through the B13 run
(book.json, ledger.jsonl, flow.docx) to its cause. Measured on the 50 page
Class 8 Science book, offline, B13 against B14:

| | B13 | B14 |
|---|---|---|
| Headings found | 71 | 170 |
| White text written white in flow.docx | yes | 0 runs |
| "Table of Contents" | caption | heading |
| Glossary rows with their own definition (page 13) | 2 of 8 | 8 of 8 |
| Running footer "Measurement" published | 4 pages | 0 |
| Concept maps kept whole | 0 | 3 (pages 15, 25, 38) |
| Indian Standard Meridian map (page 11) | lost, labels as text | one figure, labels inside it |
| Structural page issues at the gate | 4 | 4 (page 49 fixed, page 4 offline only, see below) |
| Tests | 450 | 475 |

## What was wrong, and what was done

**Headings that looked missing were written white.** "Learning Objectives",
"Introduction", "Unit Systems", "1.3 Clocks", "Points to Remember",
"Glossary", "Reference Book" and "Internet Resources" were all extracted. They
are printed white on a brown band, the run colour FFFFFF was kept, and on white
paper they vanished. Pages 5, 6, 9, 12, 13, 14. `readable_color` now drops any
colour too light to read on white; accent colours are kept.

**Section labels were voted down to body text.** The book sets its labels in
Verdana Bold at body size. Size gave no vote, so "Activity 1", "Problem 2",
"Solution", "1. Analog clocks" stayed paragraphs and ran on as body text. The
size profile now also records the body font family. A short bold line that is
in a different family from the body, or knocked out light on a band, is a
heading: level 2 for knockout labels, the deepest level for the rest. A
sentence never qualifies.

**Pictures were slotted in before the first later block.** One out of order
block (the words printed inside the seal on page 2) dragged every picture on
the page to the top, and a full width table (page 11, Fig 1.13) always landed
first. New module `placement.py` puts each late block AFTER the last block that
precedes it, reading bands, columns and rows. Pictures side by side across both
columns (the page 3 QR codes) read as one row, left to right.

**A word printed under a picture was left behind.** "E - book", "Assessment",
"DIGI links" are now bound to the QR code above them as captions and travel
with it (`bind_figure_labels`).

**Side headings landed at the end of the page.** "HOW TO USE THE BOOK" and the
"DO YOU KNOW?" badges are printed beside their text. `hoist_side_headings`
moves a heading ahead of the first block it sits level with. Text read out of
a one line badge now takes the badge's own position and level 3, not a sliver
of it at H1.

**Table of Contents became a caption.** `bind_captions` still matched on the
word alone. Captions now need a number after the word (`is_numbered_caption`).

**The running footer is repeated only for one unit.** "Measurement" beside the
page number repeats on odd pages of unit 1, far short of the 30% book wide
threshold. The same words at the same spot on 3 pages are now furniture
(`furniture_min_same_spot_pages`).

**The glossary merged into one paragraph.** Definitions printed one under
another joined into a single block under "Calibration", so five looked
missing. `pair_label_rows` rebuilds rows by baseline: each bold term takes the
definition lines from its own baseline to the next term's.

**The map was thrown out as prose.** Its run together labels have more than
three words, so they counted as a sentence and blocked the drawing. Type under
6.5 pt is now lettering, never prose, and is absorbed into the figure whatever
its length.

**The concept map came apart.** Each box is a ruled panel with text inside, so
every box was dropped as a panel, the arrows were left as stray paragraphs and
the rest cut into separate pictures. Three or more arrow glyphs seed a map
that grows through the drawings and short labels touching it and is emitted
once, with all its words in `text_in_image`.

**A thumb tab was published as a figure.** A thin picture wholly outside the
text frame that runs into the page edge is decoration (page 2 brown tab).

**Activity and Do you know boxes did not stand apart.** `in_panel` was set on
every block of a page with a full page tint, so it meant nothing. Blocks are
now tied to the printed box they sit in (`Block.box`, from `page.boxes_pt`),
and flow.docx shades and rules each box's paragraphs as one panel; the digital
HTML boxes them too (`box_panels_in_docx`).

## Model verdicts now have to agree with the page

These only act when the model is running, so they are covered by tests with a
fake model, not by the offline run. Check them on the next Ollama run.

- **A diagram is not a table.** Only regions the model classes as `table` are
  offered to `as_table` (`vlm_table_kinds`), and never one the book captions as
  a Figure. Targets page 7 Activity 3 circuit, page 10 Fig 1.10 digital clock,
  page 11 Fig 1.13.
- **A captioned picture or a QR code is not text.** A "text only" verdict is
  overruled when a Figure caption sits on the region (unless the model called
  it a text banner) or the crop is a machine code. Targets the page 15 QR code.
- **A banner whose words are already extracted is dropped.** The text layer
  keeps the words, the picture of them goes, and the words become a heading.
  Targets "Preface" printed twice on page 4.
- **A screenshot stays a picture.** Text read out of an embedded image whose
  median line is under 6.5 pt is a screenshot (`text_only_min_line_pt`).
  Targets the page 15 ICT corner.

## Known limits

- Offline, the PREFACE circle stays as a figure beside its heading, because
  only the model can say it is a banner. That is the page 4 gate issue.
- Page 11, 39 and 45 each keep one overlapping pair, as in B13.
- New thresholds (6.5 pt lettering, 3 page footer, 3 arrow map) are tuned on
  this one book.

## New settings (all defaulted)

`furniture_min_same_spot_pages` 3, `vlm_table_kinds` ("table",),
`text_only_min_line_pt` 6.5, `label_max_font_pt` 14, `pair_label_rows` True,
`concept_maps` True, `concept_map_min_arrows` 3, `box_panels_in_docx` True.
New Block fields: `font_size`, `box`.
