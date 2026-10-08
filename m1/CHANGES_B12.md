# B12 - what the page by page comparison against the PDF turned up

Ten pages of the Class 8 Science book, read against the source PDF page by
page. Every fault below was found by comparing the printed page with the
delivered flow.docx, then traced through book.json and the drop ledger.

| | B11 | B12 |
|---|---|---|
| Figures published (10 pages) | 16 | 32 |
| Figure and table captions published | 8 | 15 |
| QR codes published (6 printed) | 3 | 6 |
| Body words missing against the PDF text layer | 17 | 11 (page numerals only, plus one label and one equation phrase) |
| Page issues at the gate | 2 | 0 |
| Tests | 450 + 40 | 450 + 40 |

## What was wrong, and what was done

**A seal was thrown away for being decorative.** The state emblem on the cover
was classified `decorative` and dropped before it ever reached book.json. The
verdict now has to survive `decorative_stands`: a crop with printed text in it,
with named parts, or that reads as a seal, crest, logo, badge or code is not
ornament, whatever the model says. The prompt was narrowed to match, and
`post_filter` applies the same test a second time for figures that arrive by
another path.

**A logo was too small to count.** The publisher's logo on the imprint page is
3,577 pt2 against a floor of 4,611. One floor was being applied to everything.
An embedded image is placed on purpose, so `figure_min_area_frac_native` gives
it its own much lower bar; loose vector fragments keep the old one.

**Artwork printed inside a panel was discarded with the panel.** Drawings are
merged by proximity, so a ruled border joins everything it encloses into one
rectangle, and that rectangle is correctly rejected as a border. The council's
seal and the whole Activity 3 circuit went with it. `_regions_inside_panel` now
searches a panel, a claimed grid and a full page tint after the border itself
is set aside, keeping only clusters that carry no sentence, are not hairlines
or bars, and cover less than 70% of what encloses them. A recovered cluster
grows to take in the one and two word labels printed on it.

**Four different QR codes were read as one picture printed four times.** An 8x8
average hash cannot separate machine codes: measured distance between the four
codes on the contents page was 1 to 5, against a threshold of 4. Two of them
were dropped as duplicates, and one as a watermark repeated across pages. The
hash went to 16x16 and `is_code_like` keeps dense square codes out of the
comparison altogether. Distinct codes now sit 29 to 63 apart; the same picture
rescaled still sits at 3.

**Two photographs were republished as tables.** `as_table` was being asked
about every photo, and it answered yes for the four picture hot and cold
composite and for the digital clock. Photos are no longer offered to it.

**Captions were swallowed by the figures they name.** A caption that overlaps
its own picture was absorbed as a label and never printed again: seven of the
twelve figure captions in unit 1 were missing from the document. A caption now
keeps its place in the flow, where a caption is a caption word followed by a
number, so `Table of Contents` stays a heading. Labels that really are absorbed
are appended to the figure's `text_in_image`, so the words survive even when no
description was made.

**A right column figure was spliced into the left column.** Figures and tables
are found after the columns are known but carry no column of their own, so they
defaulted to column 0 and were placed by y alone. `_place_late_blocks` now
reads the column off the geometry first. Figure 1.1 and its caption, and Table
1.2 with its caption, land in the right column where they are printed.

**A publisher's web address was read as a print mark.** `PRINTMARK_RE` matched
any line starting `www.`, wherever it sat. A web address is furniture in a
margin band and content on an imprint page, so position decides. An imprint row
`First Edition - 2019` is also no longer read as a bulleted list.

**One expression arriving as three blocks.** A rebuilt stacked fraction leaves
the rest of its line as separate blocks on the same baseline: `60 deg = pi/180`,
`x 60 = pi`, `3 radian`. Written out one under the other they overlapped each
other on the page, which is what the gate was failing on. `join_split_math`
puts blocks that share a baseline and touch back together.

**Seven learning objectives were published as three paragraphs.** The bullets
are Wingdings bytes outside the dingbat map, so `clean()` turned them into
spaces and the lines merged. Any byte in a symbol font that is not a letter or
digit is now taken as the bullet it prints, read before cleaning. The bullets
are also printed lower than the text they mark, so the extractor files them on
their own line; `_reseat_bullets` gives each one back to the line it belongs to.

**A drop reason was recorded wrong.** A furniture block inside a panel was
logged under `in_panel`, the first flag on the block, rather than the furniture
flag that caused the drop.

## Equations are also kept as pictures of themselves

A formula is rebuilt from the page's own spans where the geometry allows it
(`fractions.py`), and read by the model where it does not. Both can be wrong,
and a wrong formula in a textbook is worse than a missing one, because nothing
about it looks wrong. So `equations.py` now cuts every equation out of the page
and keeps the crop beside the reconstruction, in `figures/pXXX_eqNN.png` with
the path in `book.json`. The crop is a pixmap of a region already known, so it
costs no model call and cannot fail.

Where a model is available, each crop is also read aloud: `describe_equation`
returns the formula in words ("I equals Q over t") and, only when the picture
makes it plain, one sentence on what it gives. The prompt forbids solving it,
continuing it, or adding a step that is not printed. The reading is stored as
`math_desc`, and rides in the picture's alt text along with the LaTeX.

Snipping runs after the joining pass, so a formula printed in pieces is cut out
as the one formula it is.

| setting | default | what it does |
|---|---|---|
| `equation_snippets` | `True` | cut every equation out of the page |
| `equation_snippet_dpi` | `220` | how finely |
| `describe_equations` | `True` | ask the model to read it in words |
| `equation_images_in_docx` | `"fallback"` | `fallback` writes the picture only when OMML fails, as before. `always` writes it under every formula. `never` keeps it on disk and out of the document |
| `equation_description_box` | `False` | print the reading under the formula, visible |

`latex_source` already records where a formula came from: `text_layer` for a
geometry rebuild, `vlm` for a model read. Reviewing the `vlm` ones first is the
cheapest way to spend a reviewer's time.
