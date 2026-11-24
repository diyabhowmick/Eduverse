"""Reads a PDF's text layer in its own process: python -m app.paperread <file> [plain]. A crash here cannot reach the website.
'plain' leaves tables as plain text, for answer keys."""
import sys
from pathlib import Path
from .papers import read_text

f = Path(sys.argv[1])
sys.stdout.buffer.write(read_text(f.name, f.read_bytes(), tables="plain" not in sys.argv[2:]).encode("utf-8"))
