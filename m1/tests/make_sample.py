"""Build a synthetic textbook PDF exercising every block type.

Page 1  native: title, headings, bold inline, list, vector diagram, caption
Page 2  native: two columns, a ruled table, a display formula
Page 3  native: a harder table, merged header cell, numeric columns
Page 4  scanned: page 1 re-rendered as a flat image, no text layer
"""

from __future__ import annotations

import os
import sys

import fitz


def build(path: str) -> str:
    doc = fitz.open()

    # ---- page 1 --------------------------------------------------------
    p = doc.new_page(width=595, height=842)
    p.insert_text((56, 80), "Light and Reflection", fontname="hebo", fontsize=22)
    p.insert_text((56, 120), "2.3 Reflection at a plane mirror",
                  fontname="hebo", fontsize=15)
    body = ("When a ray of light falls on a smooth polished surface it is "
            "sent back into the same medium. This is called reflection. "
            "The ray that arrives is the incident ray and the ray that "
            "leaves is the reflected ray.")
    _wrap(p, body, 56, 150, 480, 11)
    p.insert_text((56, 215), "Laws of reflection", fontname="hebo", fontsize=12.5)
    for i, item in enumerate([
        "The angle of incidence is equal to the angle of reflection.",
        "The incident ray, the normal and the reflected ray lie in one plane.",
    ]):
        p.insert_text((70, 240 + i * 18), "\u2022  " + item, fontsize=11)

    # a vector ray diagram
    p.draw_line(fitz.Point(320, 470), fitz.Point(520, 470))
    for x in range(325, 520, 12):
        p.draw_line(fitz.Point(x, 470), fitz.Point(x - 6, 478))
    p.draw_line(fitz.Point(340, 400), fitz.Point(420, 470))
    p.draw_line(fitz.Point(420, 470), fitz.Point(500, 400))
    p.draw_line(fitz.Point(420, 470), fitz.Point(420, 390), dashes="[3 3] 0")
    p.insert_text((398, 385), "N", fontsize=9)
    p.insert_text((408, 445), "i", fontsize=9)
    p.insert_text((432, 445), "r", fontsize=9)
    p.insert_text((418, 484), "O", fontsize=9)
    p.insert_text((330, 500), "Fig 2.4  Reflection at a plane mirror", fontsize=9)
    p.insert_text((56, 800), "42", fontsize=9)
    p.insert_text((240, 40), "Class 8 Science  Samacheer Kalvi", fontsize=8)

    # ---- page 2 --------------------------------------------------------
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((56, 80), "2.4 Refractive index", fontname="hebo", fontsize=15)
    left = ("Light bends when it passes from one medium into another. "
            "The amount of bending depends on the two media. The ratio of "
            "the speed of light in vacuum to the speed in the medium is "
            "called the refractive index of that medium.")
    right = ("A denser medium slows light down more, so it has a higher "
             "refractive index. Water is denser than air and glass is "
             "denser than water, which is why a straw looks broken.")
    _wrap(p2, left, 56, 110, 220, 10.5)
    _wrap(p2, right, 320, 110, 220, 10.5)

    p2.insert_text((56, 300), "$n = \\frac{c}{v}$", fontsize=12)

    # a ruled table
    x0, y0, w, h = 56, 340, 480, 96
    cols = [x0, x0 + 160, x0 + 320, x0 + w]
    rows = [y0, y0 + 24, y0 + 48, y0 + 72, y0 + 96]
    for x in cols:
        p2.draw_line(fitz.Point(x, rows[0]), fitz.Point(x, rows[-1]))
    for y in rows:
        p2.draw_line(fitz.Point(cols[0], y), fitz.Point(cols[-1], y))
    data = [["Medium", "Refractive index", "Speed km per s"],
            ["Vacuum", "1.00", "300000"],
            ["Water", "1.33", "225000"],
            ["Glass", "1.50", "200000"]]
    for ri, row in enumerate(data):
        for ci, cell in enumerate(row):
            p2.insert_text((cols[ci] + 6, rows[ri] + 16), cell,
                           fontname="hebo" if ri == 0 else "helv", fontsize=10)
    p2.insert_text((56, 460), "Table 2.1  Refractive index of some media", fontsize=9)
    p2.insert_text((56, 800), "43", fontsize=9)

    # ---- page 4, a harder table ----------------------------------------
    p4 = doc.new_page(width=595, height=842)
    p4.insert_text((56, 80), "2.5 Speed of light in media",
                   fontname="hebo", fontsize=15)
    x0, y0, w = 56, 120, 480
    cols = [x0, x0 + 150, x0 + 260, x0 + 370, x0 + w]
    rows = [y0 + 26 * i for i in range(7)]
    # outer verticals run the full height, the two inner ones stop below the
    # merged header cell, which is what makes it a merge
    for x in (cols[0], cols[1], cols[-1]):
        p4.draw_line(fitz.Point(x, rows[0]), fitz.Point(x, rows[-1]))
    for x in (cols[2], cols[3]):
        p4.draw_line(fitz.Point(x, rows[1]), fitz.Point(x, rows[-1]))
    for y in rows:
        p4.draw_line(fitz.Point(cols[0], y), fitz.Point(cols[-1], y))
    p4.insert_text((cols[0] + 6, rows[0] + 17), "Medium",
                   fontname="hebo", fontsize=10)
    p4.insert_text((cols[1] + 6, rows[0] + 17), "Measured values",
                   fontname="hebo", fontsize=10)
    for ci, head in enumerate(["Index", "Speed", "Density"]):
        p4.insert_text((cols[ci + 1] + 6, rows[1] + 17), head,
                       fontname="hebo", fontsize=10)
    body4 = [["Vacuum", "1.00", "300000", "0.0"],
             ["Air", "1.00", "299700", "1.2"],
             ["Water", "1.33", "225000", "1000"],
             ["Glass", "1.50", "200000", "2500"]]
    for ri, row in enumerate(body4):
        for ci, cell in enumerate(row):
            p4.insert_text((cols[ci] + 6, rows[ri + 2] + 17), cell, fontsize=10)
    p4.insert_text((56, 300), "Table 2.2  Speed of light in some media", fontsize=9)
    p4.insert_text((56, 800), "44", fontsize=9)

    # ---- page 3, a flat scan of page 1 ---------------------------------
    pix = doc[0].get_pixmap(dpi=200, alpha=False)
    p3 = doc.new_page(width=595, height=842)
    p3.insert_image(fitz.Rect(0, 0, 595, 842), pixmap=pix)

    doc.save(path)
    doc.close()
    return path


def _wrap(page, text: str, x: float, y: float, width: float, size: float):
    words = text.split()
    line = ""
    ly = y
    for w in words:
        trial = (line + " " + w).strip()
        if len(trial) * size * 0.5 > width:
            page.insert_text((x, ly), line, fontsize=size)
            ly += size * 1.4
            line = w
        else:
            line = trial
    if line:
        page.insert_text((x, ly), line, fontsize=size)
    return ly


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "sample_book.pdf"
    print(build(out))
