# EduVerse v6: textbooks, exams, B2C and B2B

## What changed

**Two tracks in one catalogue.** Every catalogue entry is now a *textbook* or an *exam pack*.

| | Textbooks | Exam packs |
|---|---|---|
| School | Board (CBSE, ICSE, ISC, NIOS, every state board) then class | Class 10 / Class 12 board exams |
| Degree | University, course, semester | Semester and final exams |
| Competitive | n/a | JEE Main, JEE Advanced, NEET UG, CUET UG, BITSAT, KCET, TNEA, MHT CET, AP EAPCET, TS EAMCET |

Lists live in `backend/app/taxonomy.py`; any other value typed in the catalogue form is accepted.

**Exam packs.** Super Admin adds past papers per year (Word, PDF with a text layer, plain text, or pasted).
The paper is split into questions automatically (numbering, (a)-(d) options, `Answer:` and `Solution:` lines,
`Section A` headings, `[2 marks]`) and each question is tagged to a chapter of the textbooks linked to the pack.
Draft, then **Send for review**, then a reviewer **approves** it under *Question papers*. Students see approved papers only.
A pack goes live once one paper is approved.

**Student side of an exam pack.** Past papers (last 10 years, last 20 years, every year), questions by chapter,
chapter weightage, quick recap per chapter (written live by the configured model from the chapter's terms and the
questions the exam keeps asking; counts against the daily AI limit), and mock tests (pick count, years, chapter;
MCQs marked automatically, written answers shown for self check). Each question links to its textbook chapter.

**B2C.** `/signup`: anyone creates a student account, picks what they study (textbook or exam, level, board and
class or university and course, exam). The store opens on that shelf. Buying is a per-item demo purchase until
a payment gateway is connected. Switch off with the `public_signup` feature.

**B2B.** Schools are now *Organisations* with a type: school, degree college, coaching centre, other. Seats,
plans, classes and book assignment work as before. It is optional: individuals need no organisation.

## Pricing model used
Individuals: one price per book or exam pack (the catalogue's *Individual price*). Organisations: per seat on
their plan, unchanged. Subscriptions for individuals are not built yet.

## Database
New columns are added in place on startup (`books.track/level/exam/university/course/semester/linked_book_ids`,
`schools.kind`, `users.profile/signup`). New tables `question_papers`, `questions`, `mock_attempts` are created.
Existing books stay textbooks at school level.

## Not done
- Payment gateway (purchases are still demo).
- Subscriptions for individuals.
- Splitting scanned papers: a PDF with no text layer gives no questions. Run it through M1 first and upload the flow document.
- Diagrams inside questions: the question text is kept, the figure is not.
