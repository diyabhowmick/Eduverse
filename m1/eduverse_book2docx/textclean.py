"""Text sanitising.

PDFs with broken embedded fonts and OCR output both emit control characters
that are legal in Python and illegal in XML. Word rejects the whole document
for one of them, so every string that reaches a writer passes through here.

Replacement is length preserving on purpose: run offsets in book.json are
character indexes into the block text, so deleting a character would silently
shift every run after it.
"""

from __future__ import annotations

import re
import unicodedata

# XML 1.0 allows tab, newline, carriage return, then 0x20 and up.
# Everything else in the C0 and C1 ranges is illegal, as are the surrogates
# and the two noncharacters.
ILLEGAL = re.compile(
    "["
    "\x00-\x08\x0b\x0c\x0e-\x1f"      # C0 except \t \n \r
    "\x7f-\x9f"                        # DEL and C1
    "\ud800-\udfff"                    # lone surrogates
    "\ufffe\uffff"                     # noncharacters
    "]"
)

# Private use area: what a broken CM font subset usually maps to. Legal XML,
# but it renders as a blank box, so it is worth knowing about.
PRIVATE_USE = re.compile("[\ue000-\uf8ff\U000f0000-\U000ffffd]")


def clean(text: str, keep_breaks: bool = True) -> str:
    """Make a string safe to put in a docx. Same length in, same length out."""
    if not text:
        return ""
    out = ILLEGAL.sub(" ", text)
    out = PRIVATE_USE.sub(" ", out)
    if not keep_breaks:
        out = out.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    return out


def had_illegal(text: str) -> bool:
    return bool(text) and bool(ILLEGAL.search(text) or PRIVATE_USE.search(text))


def broken_ratio(text: str) -> float:
    """Fraction of characters that are unusable. A high value means the page's
    text layer is corrupt and the page should be treated as scanned."""
    if not text:
        return 0.0
    bad = len(ILLEGAL.findall(text)) + len(PRIVATE_USE.findall(text))
    bad += sum(1 for c in text if c == "\ufffd")
    return bad / len(text)


def normalise(text: str) -> str:
    """NFC plus the sanitiser. Use where the exact offsets no longer matter."""
    if not text:
        return ""
    return clean(unicodedata.normalize("NFC", text))


def luminance(hex_color: str) -> float:
    """Relative lightness of an RRGGBB colour, 0 black to 1 white."""
    try:
        r, g, b = (int(hex_color[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except (TypeError, ValueError):
        return 0.0
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def is_light(hex_color: str, cut: float = 0.78) -> bool:
    """Text this light was printed on a coloured band. The band is not
    reproduced, so the text would vanish on white paper."""
    return bool(hex_color) and luminance(hex_color) >= cut


def readable_color(hex_color):
    """The colour to write, or None when writing it would hide the text."""
    if not hex_color or is_light(hex_color):
        return None
    return hex_color


def font_family(font: str) -> str:
    """'ABCDEF+Verdana-Bold' -> 'verdana'. Weight and style suffixes go, so
    the regular and bold cut of one face count as one family."""
    f = (font or "").split("+")[-1]
    f = re.split(r"[-,]", f)[0].replace(" ", "").lower()
    for _ in range(3):
        f = re.sub(r"(bold|italic|oblique|regular|semibold|medium|light|black|"
                   r"condensed|mt|ps|std|pro)$", "", f)
    return f
