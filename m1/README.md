# eduverse_book2docx

Printed book in, digital book out. PDF or DOCX to `book.json` plus an editable
`flow.docx` that keeps headings, subheadings, bold, tables, formulas and images
at their printed size and position.

An image that holds only text is read out and published as text. Every figure,
equation and table keeps what it is and gets a description box printed directly
beneath it, detailed enough to rebuild it from the words alone.

The other output is `digital/index.html`, the dynamic textbook: MathML for
maths, real tables, figures redrawn as inline SVG from their spec, and a machine
index embedded in the page. Semantic coverage says what fraction of the book a
model can actually work with.

Local only. ONE model does everything: `qwen3.5:4b` through Ollama reads the
scanned text and describes the figures.

```bash
pip install -r requirements.txt
ollama pull qwen3.5:4b
python -m eduverse_book2docx book.pdf -o out/
```

Or run the API and use the upload page:

```bash
uvicorn eduverse_book2docx.server:app --port 8000   # then open localhost:8000
```

Read RUNBOOK.md before the first real book.

Layout:

```
eduverse_book2docx/
  config.py        every tunable
  schema.py        book.json model, the single source of truth
  ledger.py        detected == emitted + dropped
  ollama_client.py the two models, plus an offline mock
  omml.py          LaTeX to OMML, no Microsoft XSL needed
  mathtools.py     detect, normalise, validate, fail closed
  textclean.py     strip XML-illegal characters, length preserving
  layout.py        boxes, bands, line level columns, reading order
  lines.py         line reading and layout aware paragraph grouping
  structure.py     heading levels, reading order, captions, furniture
  coverage.py      how much of the book is machine readable
  svgdraw.py       redraw a figure spec as vector art
  digital.py       the dynamic textbook: semantic HTML
  tables.py        native grids with runs and spans, CV grids on scans
  ocr.py           markdown from the model, boxes from CV, ink bold
  figures.py       region detection, cropping, composite split, description
  sources/         docx_source.py, pdf_source.py
  writer/          template.py, flow_docx.py, layout_docx.py, ooxml.py
  verify.py        reopen the docx and compare against book.json
  report.py        report.html scorecard
  pipeline.py      orchestration
  cli.py           python -m eduverse_book2docx
  server.py        FastAPI: upload, job queue, status, downloads
  ui.py            the upload page served at /
tests/
  run_tests.py     475 pipeline checks, offline
  test_server.py   40 API checks, offline
  make_sample.py   synthetic four page textbook
  make_hard_sample.py  six page book shaped like a real state textbook
```
