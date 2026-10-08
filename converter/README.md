# eduverse_convert

M1 flow document (.docx) to EduVerse digital textbook.

```
pip install python-docx
python -m eduverse_convert flow.docx -o out/
python -m eduverse_convert flow.docx -o out/ --llm ollama --model qwen3.5:4b      # optional AI pass
python -m eduverse_convert flow.docx -o out/ --llm anthropic --model claude-sonnet-4-6 --api-key ...
python -m eduverse_convert flow.docx -o out/ --llm openai --model gpt-4.1-mini --api-key ...
```

Output in `out/`: `book.json` (schema `eduverse.book/1`), `images/`, `report.json`, `ledger.jsonl` (every removal or change with its
reason and page), `index.html` (offline preview reader: home, index, chapter reader, explain panel, conversion report).

## What it does, in order
1. **Read**: docx body in order, `Page N` markers, heading styles, inline images with their M1 description tables, OMML equations to LaTeX.
2. **Identity**: class, subject, board, edition, publisher from the front pages ("STANDARD EIGHT", "GOVERNMENT OF ..."), cover image text as backup.
3. **Index**: the table whose header has a title and a page column. Units not present in the file are marked "not in this file".
4. **Chapters**: first numbered section `N.1` per unit, walked back to the chapter opener (Learning objectives, unit banner, index title).
   A unit shorter than 60% of its index page span is marked partial.
5. **Clean up**: running headers and footers (unit titles, subject+class, book codes), in-figure labels that leaked into the text,
   sentences broken over lines are joined, decorative images (QR codes, logos, banners, icons) removed. All logged in the ledger.
6. **Blocks**: headings, paragraphs, lists, equations, figures (caption paired by number), tables, and boxes: activity, problem,
   more to know, info bits, points to remember, glossary, exercises, concept map, ICT corner, references.
7. **Important words**: candidates from glossary, definition sentences, topic headings, units, laws and instruments, quoted terms,
   figure titles, points to remember and exercises; scored, then highlighted at first use in each topic, about one per 40 words.
   The optional AI pass drops generic words, adds missed concepts and flags prerequisites; it can only add words the chapter contains.

Nothing in the book's text is rewritten. Figure descriptions are kept on each figure for the explain panel and the LLM.

## Live explanations
```
python -m eduverse_convert.serve out/ --llm ollama --model qwen3.5:4b      # http://127.0.0.1:8765
python -m eduverse_convert.serve out/ --llm anthropic --model claude-sonnet-4-6 --api-key ...
python -m eduverse_convert.serve out/ --llm openai --model gpt-4.1-mini --api-key ...
python -m eduverse_convert.serve out/ --llm mock      # test double, no model needed
```
Tap a highlighted word, or select any words and press Explain. The model gets the word, the paragraph being read, the book's own
definition and related figure descriptions, and answers at the chosen depth (exam, concept clarity, curiosity, research).
Every important word is clickable at least once per unit. In the platform the same call is `POST /api/explain`, which uses the
provider, model, keys and depth rules from Super Admin AI settings and the school's allowed depths for students.
