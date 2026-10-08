"""Builds the explanation prompt from what the student is reading. Used by the preview server and the backend."""
DEPTHS = {
    "exam": "Short and exam focused: a clear definition, the key points a teacher expects, one example. Under 120 words.",
    "concept_clarity": "Explain in plain words for this class, use one everyday analogy and one worked example. Under 200 words.",
    "curiosity": "Explain the idea, why it matters and where it is used in real life. Under 220 words.",
    "research": "Go to first principles, mention how the idea developed and what it leads to in higher classes. Under 300 words.",
}


def build_prompt(term, book, chapter, paragraph="", definition="", figures=(), depth="concept_clarity", rules=None):
    rule = (rules or {}).get(depth) or DEPTHS.get(depth, DEPTHS["concept_clarity"])
    figs = "\n".join(f"- {f}" for f in figures if f)
    return f"""You are EduVerse, a patient tutor for a Class {book.get('class', '')} {book.get('subject', '')} student ({book.get('board', '')}).
The student is reading Unit "{chapter}" and tapped the word: "{term}".

The paragraph they are reading:
\"\"\"{paragraph[:1500]}\"\"\"

What their textbook says about it:
\"\"\"{definition[:800] or 'The textbook uses this word without defining it here.'}\"\"\"
{('Figures on this topic in the book:' + chr(10) + figs) if figs else ''}

Explain "{term}" so it makes sense in this paragraph. Stay consistent with the textbook; do not contradict it.
If the word depends on an idea from an earlier class, explain that idea first in one or two lines.
How deep to go: {rule}
Write plain text for a student, short paragraphs, no markdown headings."""


def explain(provider, model, term, book, chapter, paragraph="", definition="", figures=(), depth="concept_clarity", rules=None, **kw):
    prompt = build_prompt(term, book, chapter, paragraph, definition, figures, depth, rules)
    if provider == "mock":  # offline test double: shows the flow works, not a real answer
        return (f"[Test model, not a real answer] {term}: {definition or 'no definition in the book.'} "
                f"In the paragraph you are reading, it is used like this: {paragraph[:160]}...")
    from .llm import call
    return call(provider, model, prompt, **kw).strip()
