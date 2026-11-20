"""Reads a PDF's text layer in its own process: python -m app.paperread <file>. A crash here cannot reach the website."""
import sys
from pathlib import Path
from .papers import read_text

sys.stdout.buffer.write(read_text(Path(sys.argv[1]).name, Path(sys.argv[1]).read_bytes()).encode("utf-8"))
