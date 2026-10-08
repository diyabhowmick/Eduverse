# Teacher login

Built on the **EduVerse_Code_4168** base. Nothing else is changed.

## Signing in

```
http://localhost:8000/login/teacher
teacher@eduverse.local  /  Student@123
```

The account exists only after `python -m app.seed --demo` on a fresh database.
Lakshmi N is given the classes that actually have a book, so the screens show
real reading numbers rather than a column of zeroes.

## Four screens

| Screen | What it shows |
|---|---|
| **Home** | A sentence first — *"36 students across 2 classes. 4 have not read this week."* Then each class with its average, how many read this week, and a tag if anyone is behind |
| **My classes** | Every class they hold: students, books, average progress, read this week, hours read |
| **A class** | Every student with their progress and when they last read. Anyone who has not read in seven days is tagged **Behind**, with a **Nudge** button |
| **Analytics** | The same charts the school admin has, over 7, 30 or 90 days, but only this teacher's classes |

## What a teacher cannot do

No adding, removing or suspending students. That is the school admin's job, and
it is the whole reason a teacher could not simply be given an admin account. The
class screen says so plainly at the foot.

**The one action they have is Nudge**, which records that a student was nudged
and changes nothing else. A teacher's job here is to notice, not to administer.

Checked by calling the endpoints as a signed-in teacher:

```
/api/school/students          403   an admin endpoint, correctly refused
another teacher's class       404   not yours
nudge a student in your class 200
```

## How it is built

Five endpoints under `/api/teacher`, guarded by `require("teacher")` — the same
helper every other role uses.

The numbers come from `progress_map` and `student_out` in `school.py`, the same
functions the admin screens use, so a class reads identically on both sides.

A class carries a new `teacher_id`. The old `class_teacher` name is left alone,
so a school that has not linked anyone is unaffected. The column is added
automatically on start.

One thing this made necessary: `users` now points at `classes` twice — a
student's `class_id` and a teacher's `teacher_id` — so `User.klass` had to say
which link it follows, or SQLAlchemy refuses to start.

## Tested, not assumed

Logged in as the teacher and called every endpoint:

```
LOGIN                     200  role: teacher
/api/teacher/overview     200  36 students · 2 classes · 41% average · 271h
/api/teacher/classes      200  Class 8 A · 19 students · 43% · 2 books
/api/teacher/analytics    200  30 days · top 8 · needs help 8
/api/teacher/classes/{id} 200  19 students, Behind flags set
```

Also checked that every icon the menu uses exists in `ui.jsx`, and that every
import resolves to a real file — the two things that broke the previous attempt.
