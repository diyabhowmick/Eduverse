# EduVerse book to DOCX — RUNBOOK

Input a printed book as PDF or DOCX. Output a digital book: `book.json` plus an
editable `flow.docx` with headings, subheadings, bold, real tables, native Word
equations, and images at their printed size with the VLM description attached.

Everything runs locally against Ollama. Nothing leaves the machine.

---

## 1. Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

ollama pull qwen3.5:4b
export OLLAMA_KEEP_ALIVE=30m
```

Check the model is reachable before a long run:

```bash
python -m eduverse_book2docx --check
```

LibreOffice is optional. With `--page-lock` and `soffice` on PATH the pipeline
also renders the docx and compares the page count, which catches a wrong style.
In flow mode the book is reflowed on purpose, so that check does not run.

## 2. Run

```bash
python -m eduverse_book2docx book.pdf -o out/
```

Output folder:

```
out/
  book.json        the whole book, single source of truth
  flow.docx        the editable digital book
  layout.docx      optional, positional
  pages/p001.png   original page rasters for the compare view
  figures/         cropped figures plus one .json description each
  report.html      per page scorecard, pass or fail
  ledger.jsonl     every dropped block with a reason code
  eduverse_base.docx  the style sheet, edit it to change your fonts
```

Useful flags:

| flag | what it does |
|---|---|
| `--page-lock` | one docx page per printed page |
| `--layout-docx` | also write the positional `layout.docx` |
| `--no-page-markers` | drop the small "Page 12" labels |
| `--no-describe` | skip the figure description pass, much faster, no descriptions |
| `--no-split` | skip composite figure splitting |
| `--offline` | never call Ollama, geometry only, for testing |
| `--dpi 400` | raise raster and crop resolution |
| `--fail-on-gate` | exit non zero and raise if any check fails |
| `--json` | machine readable summary on stdout |
| `--check` | verify Ollama and the models, then exit |
| `--describe IMAGE` | send one image straight to the VLM and print what comes back |

Chapter by chapter is the sane unit of work. A 250 page book in one go is fine
but you will wait, because the VLM description pass dominates wall clock.

## 2b. The API

```bash
uvicorn eduverse_book2docx.server:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` for the upload page: drag a file in, tick the
options, watch the progress bar, download the results. Same options as the CLI.

| endpoint | what |
|---|---|
| `GET /` | upload page |
| `GET /api/health` | Ollama reachable, both models present, queue depth |
| `POST /api/jobs` | multipart upload, returns `job_id`, 202 |
| `GET /api/jobs` | every job, newest first |
| `GET /api/jobs/{id}` | status, stage, percent, summary, error |
| `DELETE /api/jobs/{id}` | remove the job and its folder |
| `GET /api/jobs/{id}/files/{name}` | download flow.docx, layout.docx, book.json, ledger.jsonl, report.html |
| `GET /api/jobs/{id}/digital` | the dynamic textbook, rendered |
| `GET /api/jobs/{id}/report` | the scorecard, rendered |
| `GET /api/jobs/{id}/book` | book.json as a response body |
| `GET /api/jobs/{id}/figures` | figure list with asset URLs |
| `GET /api/jobs/{id}/asset/{figures\|pages}/{name}` | one PNG |

`POST /api/jobs` form fields: `file`, `page_lock`, `layout_docx`,
`page_markers`, `describe`, `split_composites`, `offline`, `dpi`.

```bash
curl -s -F file=@book.pdf -F describe=true http://localhost:8000/api/jobs
curl -s http://localhost:8000/api/jobs/<id>
curl -sO -J http://localhost:8000/api/jobs/<id>/files/flow.docx
```

Environment:

| var | default | meaning |
|---|---|---|
| `EDUVERSE_DATA` | `./eduverse_jobs` | where jobs and outputs live |
| `EDUVERSE_WORKERS` | `1` | concurrent conversions. Keep it at 1 unless the box has spare VRAM, both models are loaded per job |
| `EDUVERSE_MAX_UPLOAD_MB` | `200` | upload ceiling |
| `EDUVERSE_HOST` / `EDUVERSE_PORT` | `0.0.0.0` / `8000` | bind address |
| `OLLAMA_HOST` | `http://localhost:11434` | if Ollama is on another box |

Jobs are queued to a worker thread, so the upload returns immediately and the
page polls. Outputs are written to `EDUVERSE_DATA/<job_id>/out/` and survive a
restart: a job that was mid run when the server died comes back marked failed,
a job that had finished stays downloadable.

There is no auth. Put it behind your own reverse proxy before it leaves the
laptop.

## 2c. The dynamic textbook

The docx is for a human to edit. `digital/index.html` is the other output and
the one the product is built on: one semantic file where nothing is a picture of
content.

- maths is MathML, with the LaTeX kept in `data-latex`
- tables are real `<table>` with `<th>`, `colspan` and `rowspan`
- a figure with a spec is **inline SVG**, redrawn from structure, not a photo
- every figure carries `data-spec`, `data-kind` and `data-regenerable`
- each figure's description sits visibly under it and in the DOM
- a compact machine index is embedded as
  `<script type="application/json" id="eduverse-book">`: outline, figures,
  equations, tables and the coverage numbers, so a model does not have to parse
  the prose back into structure

Three passes exist only to close the holes where content would otherwise survive
as pixels:

| pass | what it does | switch |
|---|---|---|
| figure spec | asks the VLM for nodes and edges, or axes and series, then redraws it as SVG | `figure_spec`, `emit_svg` |
| VLM maths | reads a formula the text layer mangled, validates it, and only then uses it | `vlm_math` |
| VLM tables | pulls the cells out of a picture of a table and publishes a real table | `vlm_tables` |

None of them ever invents. An unsure formula still falls back to the image, a
spec that cannot be redrawn leaves the photo in place, and a region that is not
a table stays a figure.

**Images go over `/api/chat`.** That endpoint carries images reliably on
current Ollama builds. `/api/generate` still accepts an images array but some
model templates ignore it there, and the model then answers about nothing at
all, which looks exactly like a model refusing to describe. Chat is tried
first, generate is the fallback, and a chat reply that comes back empty falls
through instead of being reported as the answer. The report and `--describe`
both say which endpoint answered.

**`--check` now proves the model can see.** It sends a tiny red circle and asks
what shape and colour it is. A model that cannot describe your figures will
fail that in a second, which saves running a whole book to find out.

**The vision model is a thinking model.** Qwen 3.5 reasons out loud before it
answers, and that reasoning is not JSON. It is stripped before parsing, closed
block or not, on both the description and the OCR path, and the request also
carries `think: false` so the model does not spend its whole budget reasoning
and run out before it answers. Older Ollama builds ignore that flag harmlessly. If you swap in a
different model, nothing needs changing for that.

**Semantic coverage** is the number that tracks this goal, and it is on the
report and in `book.json` under `stats.coverage`. A block is machine readable
when a model can work with its content: text, a table with cells, an equation
with LaTeX or OMML, a figure with a description or a spec. Everything else is
opaque and listed by id and page so you can go and look at it.

Character counts tell you nothing was lost. Coverage tells you whether what
survived is usable.

## 2d. How a page is read

Layout is worked out before any text is read. Grouping lines into paragraphs
first is what hides a column gap, which is how a two column page ends up read
straight across.

1. **Boxes first.** A bordered or tinted region holding text is a panel. It is
   read start to finish as its own little document, and nothing outside it may
   cut in. A small square shape inside a panel holding one short word is a
   title badge, so that word comes first however far down it sits. That is the
   PREFACE case: the word is printed in a circle halfway down and the paragraph
   wraps around it.
2. **Columns from lines, not blocks.** A gutter is a vertical strip that few
   lines cross, and far fewer than cross the text either side of it. It is not
   required to be empty: a banner or a full width heading crosses a real
   gutter, and demanding emptiness makes the page read as one column. Stray
   marks under 12pt are left out entirely, because a five point registration
   cross in the white space is enough to hide a gutter.
3. **Confirmed by pairing.** Text must sit on both sides of the gap and
   actually overlap vertically. A ragged right margin is not a column.
4. **Bands.** Only a page that has columns can have bands. A line that crosses
   the gutter splits the page, and the columns are worked out again for each
   band. A long line in a wide single column is not a band break, or every
   wrapped paragraph becomes its own band.
5. **Order.** Band, then column, then top to bottom, with each box kept whole.
6. **Joining.** Two lines join when the first does not finish a sentence and
   the second continues one, or the first ends in a hyphen. Never across a
   column, a box edge, a band or a size change. A bold line followed by an
   unbold one is a run-in label, not the start of that paragraph. Several short
   capitalised lines in a row are a list, not a broken sentence. Inside a narrow
   box every line joins, because the column is too thin to judge by punctuation.
7. **Confidence.** Every page carries a layout confidence and the report shows
   it, so you can go to the doubtful pages instead of reading them all.

Nothing here is guessed for a page with fewer than six lines. It is read as one
column.

## 3. What decides what

**Routing.** Each PDF page is classified as native (real text layer), hybrid
(some text, some image regions) or scanned (no text layer). Native pages never
touch the OCR model. A DOCX never touches it at all.

**The rule that matters.** Text comes from the OCR model. Position and size
never do. Geometry always comes from PyMuPDF or from computer vision. Mixing
that up is what breaks image placement.

**Heading levels** come from a font size histogram built across the whole book,
weighted by characters, never per page. Size alone never decides: weight,
colour, section numbering, line length and position all vote, and a block needs
three votes to become a heading. Change `heading_min_size_ratio` and
`max_heading_levels` in `config.py` if a book uses an unusual scale.

**Running heads, page numbers and side tabs** are found book wide, not page by
page. A short line that appears in the same band on 30% or more of the pages is
furniture whatever it looks like on any single page, so a side tab reading
"Unit 1" printed down the outer margin goes the same way a page number does. A
book under four pages is too short to judge and nothing is dropped.

**A bold label at body size is not a new heading level.** A run-in label like
"Activity 1" or "Do you know?" stays a paragraph with its bold intact. Making it
a heading is what turns every bold word in a state textbook into an H4 and
flattens the real hierarchy. Only a size the book actually uses becomes a
heading level, and no depth beyond those sizes is ever invented.

**A sentence split across blocks is stitched back together.** A boxed activity
or a narrow column arrives as one PyMuPDF block per line, which is what produces
"Measure / the length / and breadth of your / science book". Two blocks join
only when the first does not end a sentence and the second continues one, so a
genuine list of short terms is left alone. Switch it off with
`join_fragments = False`.

**A ruled panel around text is a border, not a figure.** If the inside of a
vector rectangle is mostly text, the rectangle is dropped and the blocks inside
it are flagged `in_panel` with `block_kind: panel`, so the activity keeps its
heading and its text instead of becoming a picture.

**Bold** on a native page is the PyMuPDF span flag or a Bold in the font name.
On a scan it is stroke thickness: ink density per word against the page median,
threshold `bold_ink_ratio`.

**Equations** go LaTeX to OMML directly, no Microsoft XSL needed. Every formula
is validated first (brace balance, environment closure, left/right match,
supported commands). A formula that fails validation is never typed out. The
block is marked `math_unreadable` and the writer emits the cropped image
instead, because a picture of the right formula beats a typed wrong one. A DOCX
input that already contains Word equations has its OMML carried through
verbatim.

**Chemistry** (H2SO4) goes through subscript and superscript runs, not the
equation path.

**Figures.** Embedded rasters use the real placement rect. Vector drawings are
merged first then filtered by area, so hatching joins its diagram instead of
being discarded. Scanned pages find figures by removing text boxes and grouping
what ink is left. Composite regions are split by asking the VLM for fractional
part boxes, then cropped from the geometry.

**Figure candidates are gathered before anything is emitted.** Embedded images,
vector regions and scanned ink regions all go into one list, and only then is it
decided what a figure is. Emitting on discovery is what produced the two figure
faults: one clock arriving as six pictures, and the same picture arriving twice
because two detectors both found it.

**Fragments of one illustration are clustered.** A PDF is free to store a clock
face as one image object and its hands, numerals and tick marks as five more.
Each is a real object, none is a figure on its own. Candidates join when they
touch, nearly touch, or one sits inside the other, and only when no line of text
runs between them and the merge does not balloon a small piece into a much
bigger box. The merged figure is flagged `merged_from_N_fragments` and every
fragment is logged, so the ledger still balances.

**A picture the size of the page is a background**, a border, or the scan of the
page itself. It is dropped unless the page yielded nothing else, so a page that
genuinely is one image is never lost.

**A string printed twice is read once.** Coloured headings are often drawn
twice, a grey copy under the real one to fake a shadow. Both are real text to
the extractor, and joined into one block they read as a stutter: "Analog clocks
Analog clocks". A line repeating the one before it at the same spot is dropped
at extraction, a block whose text is one string doubled is collapsed, and a
block repeating another at the same position is dropped. The same words
genuinely repeated elsewhere on the page are kept.

**Duplicates are caught three ways.** The same image placed twice at the same
spot is dropped at source. Two crops that hash the same on one page are dropped
after the first, using an average hash so a rescaled or requantised copy still
matches. And a picture that appears on 30% or more of the pages is a logo, a
watermark or a border, dropped as `watermark` exactly the way a running head is.
A flat crop with almost no variation is never a figure at all.

**Tables** are claimed before figures, because a ruled grid is a table and not
a drawing. Three routes into `tables.py`:

- *native*, where PyMuPDF finds the grid. The cell text is rebuilt from the
  spans inside each cell rather than from `tb.extract()`, which hands back plain
  strings and throws the weight away, so bold and italic survive into the cell.
  Three strategies are tried in turn, so an unruled table aligned only by
  whitespace is still found.
- *scanned*, where long horizontal and vertical runs of ink are intersected to
  find the grid, then the OCR model reads that region and its markdown table is
  mapped onto it.
- *markdown*, where the OCR model returned a pipe table with no rules to confirm.

**Cell values are assigned by where the text sits, not by strict containment.**
A label printed a hair wider than its ruled box is normal. Requiring containment
empties the whole column silently: the table then reads "metre" as the unit of
nothing while the labels leak into the surrounding prose. Each span goes to the
cell its centre falls in.

**A single column is never a table.** The shape is re-checked after empty rows
and columns are pruned, because pruning can collapse a grid down to one column,
and one column is a sidebar or a list.

**Merged cells** are read off the ruling lines, not guessed. If the vertical
rule that should separate two cells was never drawn and the right hand cell is
empty, the pair is one cell. Same logic vertically for row spans.

**Column widths** come from the real grid boundaries, scaled to the text width,
and are set on every cell, because Word ignores a width set only on the column.
Header rows are detected from bold, not from position, since plenty of tables
start with data. A detected header row repeats across page breaks. Borders drawn
are the borders the printed table drew: no vertical rules in the book means none
in the docx. Numeric cells are right aligned. Wrapped cell text is joined back
into one value. Entirely empty rows and columns are pruned. Text blocks that
fall inside a table are absorbed into it and logged, so nothing appears twice.

**Descriptions** ride in the picture alt text: invisible to the reader, readable
by any tool, and they survive a round trip through Word. That is the field that
carries the description into the digital book later.

**A region that is only text is not a figure.** The VLM is asked, for every
crop, whether it holds nothing but printed text. If it does, the OCR model
reads the crop out and the result is published as real blocks in place of the
picture: headings keep their level, bullets become list items, bold survives,
tables stay tables. The image file is not kept and the drop is logged as
`published as text`. Switch it off with `text_only_to_text = False` in
`config.py` if you would rather keep the picture.

**Every figure, every equation and every table gets a description box printed
directly beneath it** in `flow.docx` and in the digital book. A shaded panel,
headed by what it describes.

- **Image description** carries the VLM's account of the picture plus its parts,
  relations, data points and any text printed inside it. The prompt asks for
  enough detail that someone who has never seen the figure could draw a faithful
  replica from the words alone: layout first, then each element in turn with its
  position, proportion, shape, orientation, connections and printed text, arrow
  directions, line styles, shading. No interpretation, no explanation of the
  science, nothing that is not drawn.
- **Equation description** reads the formula out in plain words, then gives the
  LaTeX verbatim, then says where the LaTeX came from: the page text layer, the
  vision model, or a Word equation. The LaTeX is the exact recipe for a replica;
  the reading is what a person or a model uses without parsing it.
- **Table description** gives the shape, whether it was ruled, the column names,
  any merged cells and what they span, then writes the rows out. A long table is
  summarised rather than retyped, since the table itself sits directly above.

The figure text also stays in the picture alt text, so a tool can read it
without parsing the box. Boxes survive a round trip back through the DOCX reader
as boxes, not as one cell tables. Switch them off with
`figure_description_box`, `equation_description_box`, `table_description_box`.

Block order around a figure is always: the figure, then its description box,
then the printed caption.

**decorative** figures are dropped with a reason and are never kept as a
picture.

## 4. Reading the report

Open `report.html`. The cards at the top are the whole story:

- **ledger** must say balanced. `detected == emitted + dropped` is the only
  thing that catches silent loss. If it says OFF BY n, something was emitted or
  dropped without being counted, and that is a bug worth chasing.
- **figures described** should equal the figure count. A gap means the VLM call
  failed, usually a timeout.
- **machine readable** is the headline. Below 100% the opaque blocks are listed
  by id and page, with the reason each one is opaque.
- **figures regenerable** is how many came back as structure rather than as a
  photo. A photograph is never regenerable and that is fine; a diagram or chart
  that is not regenerable is worth looking at.
- **description boxes** must equal the figure, equation and table count when
  the boxes are on. A figure box that is empty means the VLM was not reached:
  check **figures described** rather than assuming the pass is missing.
- **equations not verified** is the count that fell back to an image. A few is
  normal. A lot means the OCR model is mangling the maths on those pages.
- **pages with issues** lists exactly which pages failed which check.

The page table shows the route taken per page and the block counts. A page that
should be dense but shows two blocks was misrouted.

`ledger.jsonl` line one is the summary, every line after it is one dropped block
with its reason code.

## 5. Tuning

Every number lives in `config.py`. The ones you will actually touch:

| setting | when |
|---|---|
| `native_min_chars` | pages with sparse real text land as scanned |
| `figure_min_area_frac` | small diagrams are missed, or noise is picked up |
| `figure_merge_gap_px` | one diagram arrives as several pieces on a scan |
| `fragment_gap_pt` | a native figure arrives as several pieces, or two figures glue together |
| `fragment_max_growth` | a small piece is dragging a big figure into a huge box |
| `dup_max_distance` | near identical pictures are or are not seen as the same |
| `figure_max_area_frac` | a large legitimate figure is being dropped as background |
| `dedupe_text` / `dedupe_text_shift_pt` | repeated text is or is not collapsed |
| `repeat_image_page_frac` | a real recurring figure is being dropped as a logo |
| `fragment_merge` / `dedupe_images` | switch either behaviour off |
| `bold_ink_ratio` | scanned bold is over or under detected |
| `caption_max_gap_pt` | captions are not binding to their figures |
| `text_only_to_text` | a text-only region should stay a picture instead |
| `text_only_min_chars` | tiny text regions are being converted noisily |
| `figure_description_box` | you want the figure description in alt text only |
| `equation_description_box` / `table_description_box` | those boxes |
| `table_note_max_rows` | how many rows a table box writes out before summarising |
| `figure_spec` / `emit_svg` | figure specs and the SVG redraw |
| `vlm_math` | reading formulas off the page |
| `vlm_tables` | pulling tables out of pictures |
| `spec_kinds` | which figure kinds get asked for a spec |
| `write_digital` | the dynamic textbook output |
| `figure_note_shading` | the box tint |
| `column_gutter_min_pt` | a two column page reads as one |
| `gutter_max_cross_frac` | a banner crossing the gutter hides it, or a false gutter appears |
| `gutter_valley_ratio` | how much busier the sides must be than the gap |
| `min_line_width_pt` | stray marks are or are not ignored |
| `max_bands` | a page is being cut into too many strips |
| `heading_min_pages` | a real heading size is being ignored as a one-off |
| `front_matter_max_pages` | the cover is or is not skipped when learning sizes |
| `cell_recover_pad_frac` | table cells stay empty, or grab the wrong value |
| `grid_min_parts` / `grid_size_tolerance` | a photo grid is or is not one figure |
| `drop_repeating_furniture` | a real repeated line is being dropped as a head |
| `join_fragments` | fragments should stay separate blocks |
| `heading_max_chars` | long headings are read as paragraphs |
| `corrupt_text_ratio` | a page with a broken font is or is not sent to OCR |
| `table_min_cells` | small tables are missed, or noise becomes a table |
| `table_rule_min_len_frac` | rules are or are not recognised in a region |
| `table_header_shading` | the header row tint |
| `styles` | your fonts and sizes, the EduVerse look |

Changing `styles` alone does not change an existing run. Delete
`out/eduverse_base.docx` so the template is rebuilt.

## 6. Troubleshooting

**Equations look blank in LibreOffice.** LibreOffice does not render imported
OMML in all builds. The XML is correct: check with
`pandoc -f docx -t markdown flow.docx`, and the formula appears as LaTeX. Word
renders it properly and it is editable in the equation editor.

**ValueError: All strings must be XML compatible.** A control character from a
broken embedded font or from OCR reached the writer. This should no longer
happen: `textclean.py` scrubs every string at extraction and again at write
time, and the replacement is length preserving so run offsets stay correct. If
you still hit it, the character came from somewhere new, so send the page number
and check `book.json` for that block.

**A page's text comes out as boxes or gibberish.** Its text layer is corrupt,
usually a subset font with no usable encoding. Pages whose text is more than
15% unusable are routed to the OCR model instead of being published as garbage.
Tune `corrupt_text_ratio` if a page is being sent to OCR unnecessarily, or is
publishing junk that should have gone to OCR.

**Ledger off by a number.** A block was emitted or dropped without a matching
`detect()`. Grep the extractor for the block id prefix in `ledger.jsonl`.

**The same figure appears several times.** Check the ledger for `duplicate` and
`watermark` entries: each names what it matched. If a genuine figure was dropped
as a watermark, it recurs on too many pages for the threshold, so raise
`repeat_image_page_frac`. If two different pictures were treated as one, lower
`dup_max_distance`.

**One picture arrives as several figures.** The pieces sit further apart than
`fragment_gap_pt`, or a line of text runs between them, or merging them would
have grown the box past `fragment_max_growth`. Raise the gap first, it is the
usual cause. Check the report: a merged figure is flagged with how many
fragments went into it.

**Two separate figures were glued into one.** Lower `fragment_gap_pt` and
`fragment_max_growth`. A caption between the two would have kept them apart, so
check the caption was detected as text and not swallowed as part of a figure.

**A diagram became a table.** The pipeline rejects a grid whose cells are less
than 45% filled, and figures never claim a region a table already owns. If one
still slips through, raise `table_min_cells`.

**A table came out as a picture.** It had no ruling lines and no whitespace
alignment PyMuPDF could see. Check the page route in the report: on a scanned
page the grid detector needs visible rules. An unruled scanned table is the one
case that still lands as a figure, and it keeps its description box.

**A table column is empty and its values are in the prose.** Fixed: cells are
assigned by span centre. If it recurs, the column's text sits outside the
detected grid entirely, so check the table bbox in `book.json` against the
printed table.

**The same sentence appears twice in a row.** A shadow layer. Check the ledger
for `duplicate` with "same text as", and for the `doubled_text_collapsed` flag
on the block. If a genuine repetition was collapsed, lower
`dedupe_text_shift_pt`.

**The figure boxes are empty but the equation and table boxes are fine.**
First prove the model works on its own:

```bash
python -m eduverse_book2docx --describe out/figures/p001_fig01.png
```

That sends one crop straight to `qwen3.5:4b` and prints the raw JSON it
returns. If a description comes back, the model is fine and the problem is in
the pipeline. If it does not, it is the model, and nothing the pipeline does
will fill that box.
 The
equation and table boxes are built locally from what was already extracted, so
they always appear. The figure box is the only one that needs the model, so an
empty figure box means `qwen3.5:4b` was not reached or returned nothing. The
box now says which, and names the error. Confirm with
`python -m eduverse_book2docx --check`, and look at the **figures described**
card on the report: `0/40` means the model was never reached, not that the pass
is missing.

**A merged cell was not detected.** Merges are read from missing ruling lines,
so a table that draws every rule and fakes the merge with white fill will not be
detected as merged. The cell text is still correct, it just sits in one column.

**Labels from inside a diagram appear in the text flow.** Short blocks sitting
within 26pt of a figure are absorbed into it. Widen `tol` in `_absorb_labels`
for diagrams with far flung labels.

**Everything on a scanned page became one figure.** The OCR model returned
nothing, so all ink looked like a picture. Check `--check`, then check the page
raster is legible at the current `page_dpi`.

**Running heads are being kept as content.** Two passes catch them. The per
page band is 6.5% of page height top and bottom, in `structure.is_furniture`.
The book wide pass needs the line to repeat on 30% of pages, in
`structure.find_repeating_furniture`. A head that changes every page, a chapter
title for instance, escapes both, and that is deliberate.

**A real repeated line was dropped.** Something legitimate appears near the page
edge on most pages. Set `drop_repeating_furniture = False` and check the ledger
for `furniture_header` entries: each names how many pages the line appeared on.

**Detection found no board or grade.** These usually live in the running head,
which is dropped as furniture but still fed to detection. If the book has no
running head, the fields stay null. Nothing is declared to the system by design.

**Word says the file needs repair.** Run
`python /path/to/validate.py flow.docx`. Every element this package writes goes
through `writer/ooxml.py` so it lands in the schema correct slot, so a failure
there is a real bug.

## 7. Tests

```bash
python -m tests.run_tests
```

```bash
python -m tests.test_server
```

448 pipeline checks plus 40 API checks, no pytest needed, all offline. They cover the OMML converter, maths
validation, the size histogram, column detection, caption binding, the drop
ledger, markdown parsing, the schema round trip, the template, the full PDF
pipeline, the DOCX round trip, the layout writer, the description boxes for figures, equations and
tables, reading a formula out in words, the text-only conversion, table extraction including merges and header detection, the SVG redraw, semantic coverage,
the digital book, VLM maths recovery, fragment clustering, image hashing, text dedupe, table cell assignment, and a six page book
shaped like a real state textbook that reproduces the running head, heading
level, fragmentation, duplicate image and shattered figure faults, and a check that nothing is generated that was not on the
page.

The API tests cover health, the upload page, rejected extensions and empty
files, a full conversion through the queue, every download, path traversal
attempts, job listing and deletion, and that a broken input fails the job
without killing the worker.

`tests/make_sample.py` builds the synthetic four page textbook used by the
pipeline tests: a native page with a vector diagram, a two column page with a
ruled table and a display formula, a page with a harder table that has a merged
header cell and numeric columns, and a flat scan of page one.

## 8. What is deliberately not here

- **Gemini figure redraw.** Deferred, and partly overtaken: a chart or a node
  and edge diagram is already redrawn as SVG from its spec. What is left for
  Gemini is the illustrative figure that no structure captures, a photograph or
  a scene. When it is picked up, the writer swaps `image_ref` for `redraw_ref`
  and nothing else changes.
- **Book upload, fingerprinting, credits.** Out of scope for this stage.
- **Generated explanations.** The book stays a plain textbook. Explanations are
  generated live when the student clicks, not at build time.
