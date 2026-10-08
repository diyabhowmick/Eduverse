"""A six page book shaped like a real state textbook.

Every page carries a running head and a page number. One page holds a boxed
activity whose lines are laid out separately, which is what produces the
"Measure / length / breadth of your / book" fragmentation. Bold run-in labels
sit alongside genuinely sized headings, so heading levels can be checked.
"""

from __future__ import annotations

import sys

import fitz

RUNNING_HEAD = "Science 8"
BODY = 10.5
H1, H2, H3 = 22.0, 15.0, 12.0


def build(path: str) -> str:
    doc = fitz.open()
    logo = _logo_bytes()
    for pno in range(1, 7):
        pg = doc.new_page(width=595, height=842)
        _furniture(pg, pno)
        # the same logo on every page: a watermark, not content
        pg.insert_image(fitz.Rect(470, 20, 560, 74), stream=logo)
        if pno == 1:
            _cover(pg)
        elif pno == 2:
            _unit_opening(pg)
        elif pno == 3:
            _activity_box(pg)
            _shattered_clock(pg)
            _shattered_raster(pg)
        elif pno == 4:
            _run_in_labels(pg)
            _si_table(pg)
            _shadow_text(pg)
        else:
            _plain(pg, pno)
    doc.save(path)
    doc.close()
    return path


def _furniture(pg, pno: int) -> None:
    # running head at the top, page number at the foot, on every page
    pg.insert_text((56, 38), RUNNING_HEAD, fontsize=8)
    pg.insert_text((520, 812), str(pno), fontsize=9)
    # a side tab, narrow, vertically in the middle of the page
    pg.insert_text((566, 420), "Unit 1", fontsize=7)


def _cover(pg) -> None:
    pg.insert_text((56, 120), "MEASUREMENT", fontname="hebo", fontsize=H1)
    pg.insert_text((56, 170), "GOVERNMENT OF TAMIL NADU",
                   fontname="hebo", fontsize=BODY)
    pg.insert_text((56, 200), "STANDARD EIGHT", fontname="hebo", fontsize=BODY)
    _wrap(pg, "A publication under the Free Textbook Programme of the "
              "Government of Tamil Nadu, prepared by the State Council of "
              "Educational Research and Training.", 56, 240, 480, BODY)


def _unit_opening(pg) -> None:
    pg.insert_text((56, 100), "1.1  Unit Systems", fontname="hebo", fontsize=H2)
    _wrap(pg, "We need three things for a perfect measurement. They are an "
              "instrument, a standard quantity to compare against, and a "
              "trained observer who records the reading carefully.",
          56, 130, 480, BODY)
    pg.insert_text((56, 210), "1.1.1  Temperature", fontname="hebo", fontsize=H3)
    _wrap(pg, "Temperature tells us how hot or cold a body is. The SI unit of "
              "temperature is the kelvin, named after Lord Kelvin.",
          56, 236, 480, BODY)


def _activity_box(pg) -> None:
    pg.insert_text((56, 100), "1.2  Measuring length",
                   fontname="hebo", fontsize=H2)
    _wrap(pg, "Measurement is the base of all scientific studies. It plays a "
              "vital role in daily life and in every branch of science.",
          56, 130, 480, BODY)

    # the activity box: each line placed on its own, as a real book does
    pg.draw_rect(fitz.Rect(56, 190, 300, 330))
    pg.insert_text((66, 210), "Activity 1", fontname="hebo", fontsize=BODY)
    for i, line in enumerate(["Measure", "the length", "and breadth of your",
                              "science book", "using a ruler", "and compare",
                              "your value with", "those of your friends."]):
        pg.insert_text((66, 232 + i * 13), line, fontsize=9.5)

    _wrap(pg, "Let us say that the length of the book is thirty centimetres. "
              "Here the length is the physical quantity and the ruler is the "
              "instrument used.", 320, 200, 220, BODY)


def _run_in_labels(pg) -> None:
    pg.insert_text((56, 100), "1.3  Units and symbols",
                   fontname="hebo", fontsize=H2)
    # bold labels at body size: run-in headings, not a new heading depth
    for i, (label, text) in enumerate([
        ("Learning Objectives", "After this lesson students will be able to "
                                "explain the system of units."),
        ("Introduction", "Physics is the study of nature and natural "
                         "phenomena around us."),
        ("Do you know?", "The metre was once defined by a bar kept in Paris."),
    ]):
        y = 140 + i * 70
        pg.insert_text((56, y), label, fontname="hebo", fontsize=BODY)
        _wrap(pg, text, 56, y + 18, 480, BODY)


def _plain(pg, pno: int) -> None:
    pg.insert_text((56, 100), f"1.{pno}  Further reading",
                   fontname="hebo", fontsize=H2)
    _wrap(pg, f"The International System of Units was agreed in nineteen sixty "
              f"at the eleventh General Conference on Weights and Measures. It "
              f"defines seven base quantities, described here on page {pno} of "
              f"this unit, from which all other units follow.",
          56, 130, 480, BODY)


def _si_table(pg) -> None:
    """A table whose first column is printed a shade wider than its ruled box,
    which is how a whole column went missing from a real book."""
    x0, y0 = 56.0, 420.0
    cols = [x0, x0 + 150, x0 + 260, x0 + 360]
    rows = [y0 + 22 * i for i in range(5)]
    for x in cols:
        pg.draw_line(fitz.Point(x, rows[0]), fitz.Point(x, rows[-1]))
    for y in rows:
        pg.draw_line(fitz.Point(cols[0], y), fitz.Point(cols[-1], y))
    pg.insert_text((cols[0] + 5, rows[0] + 15), "Quantity",
                   fontname="hebo", fontsize=9)
    pg.insert_text((cols[1] + 5, rows[0] + 15), "Unit",
                   fontname="hebo", fontsize=9)
    pg.insert_text((cols[2] + 5, rows[0] + 15), "Symbol",
                   fontname="hebo", fontsize=9)
    data = [("Amount of Substance", "mole", "mol"),
            ("Electric Current", "ampere", "A"),
            ("Luminous Intensity", "candela", "cd")]
    for ri, (a, b, c) in enumerate(data):
        # the label starts before the rule and runs past it, on purpose
        pg.insert_text((cols[0] + 2, rows[ri + 1] + 15), a, fontsize=9)
        pg.insert_text((cols[1] + 5, rows[ri + 1] + 15), b, fontsize=9)
        pg.insert_text((cols[2] + 5, rows[ri + 1] + 15), c, fontsize=9)


def _shadow_text(pg) -> None:
    """The same string drawn twice a hair apart, a shadow layer under coloured
    text. It reads as a stutter in the output."""
    pg.insert_text((56, 560), "Analog and digital clocks",
                   fontname="hebo", fontsize=BODY, color=(0.7, 0.7, 0.7))
    pg.insert_text((56.6, 560.4), "Analog and digital clocks",
                   fontname="hebo", fontsize=BODY)


def _logo_bytes() -> bytes:
    """A distinctive PNG, reused on every page."""
    import zlib
    import struct
    w = h = 40
    rows = b""
    for y in range(h):
        rows += b"\x00" + bytes(
            v for x in range(w)
            for v in ((220, 33, 47) if (x + y) % 6 < 3 else (250, 249, 246)))

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows))
            + chunk(b"IEND", b""))


def _shattered_clock(pg) -> None:
    """One illustration stored as many pieces, which is how a real PDF holds a
    clock: the face as one object, the hands and numerals as several more."""
    cx, cy, r = 430.0, 560.0, 62.0
    pg.draw_circle(fitz.Point(cx, cy), r, width=1.6)          # the face, 80%
    pg.draw_line(fitz.Point(cx, cy), fitz.Point(cx + 34, cy - 18))   # hour hand
    pg.draw_line(fitz.Point(cx, cy), fitz.Point(cx - 8, cy - 48))    # minute hand
    for i, lab in enumerate(("12", "3", "6", "9")):
        ang = [(-1, 0), (0, 1), (1, 0), (0, -1)][i]
        pg.insert_text((cx + ang[1] * (r - 14) - 5, cy + ang[0] * (r - 14) + 4),
                       lab, fontsize=8)
    pg.insert_text((372, 646), "Fig 1.2  A clock face", fontsize=9)


def _shattered_raster(pg) -> None:
    """One picture stored as six separate image objects sitting side by side,
    which is exactly how the clock arrived as six figures."""
    tiles = _tile_bytes()
    x0, y0 = 90.0, 500.0
    for i in range(3):
        for j in range(2):
            pg.insert_image(
                fitz.Rect(x0 + i * 46, y0 + j * 46,
                          x0 + i * 46 + 44, y0 + j * 46 + 44),
                stream=tiles[(i + j) % len(tiles)])
    pg.insert_text((90, 606), "Fig 1.3  A six part illustration", fontsize=9)


def _tile_bytes():
    return [_png(28, 28, shade) for shade in (40, 110, 190)]


def _png(w: int, h: int, shade: int) -> bytes:
    import struct
    import zlib
    rows = b""
    for y in range(h):
        rows += b"\x00" + bytes(
            v for x in range(w)
            for v in ((shade, shade, shade) if (x * y) % 7 else (250, 250, 250)))

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows))
            + chunk(b"IEND", b""))


def _wrap(page, text: str, x: float, y: float, width: float, size: float):
    words = text.split()
    line = ""
    ly = y
    for w in words:
        trial = (line + " " + w).strip()
        if len(trial) * size * 0.5 > width:
            page.insert_text((x, ly), line, fontsize=size)
            ly += size * 1.35
            line = w
        else:
            line = trial
    if line:
        page.insert_text((x, ly), line, fontsize=size)
    return ly


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else "hard_sample.pdf"))
