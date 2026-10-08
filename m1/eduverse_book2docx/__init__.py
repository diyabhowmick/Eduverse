"""EduVerse book to DOCX pipeline.

Input : one PDF or DOCX book, nothing declared about it.
Output: book.json, flow.docx, figures/, report.html, ledger.jsonl,
        and optionally layout.docx.
"""

__version__ = "1.0.0"

from .schema import Block, Page, Book, Run, TableCell, TableData, FigureMeta

__all__ = [
    "Block",
    "Page",
    "Book",
    "Run",
    "TableCell",
    "TableData",
    "FigureMeta",
    "__version__",
]
