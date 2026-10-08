"""Schema-correct element insertion.

OOXML sequences are order enforced. Appending a valid element in the wrong slot
produces a file Word may still open but that fails XSD validation, so every
element this package adds goes in through here.
"""

from __future__ import annotations

from typing import List

from docx.oxml.ns import qn

# CT_PPrBase / CT_PPr
PPR_ORDER: List[str] = [
    "pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr",
    "widowControl", "numPr", "suppressLineNumbers", "pBdr", "shd", "tabs",
    "suppressAutoHyphens", "kinsoku", "wordWrap", "overflowPunct",
    "topLinePunct", "autoSpaceDE", "autoSpaceDN", "bidi", "adjustRightInd",
    "snapToGrid", "spacing", "ind", "contextualSpacing", "mirrorIndents",
    "suppressOverlap", "jc", "textDirection", "textAlignment",
    "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr",
    "sectPr", "pPrChange",
]

# CT_TblPrBase / CT_TblPr
TBLPR_ORDER: List[str] = [
    "tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblStyleRowBandSize",
    "tblStyleColBandSize", "tblW", "jc", "tblCellSpacing", "tblInd",
    "tblBorders", "shd", "tblLayout", "tblCellMar", "tblLook", "tblCaption",
    "tblDescription", "tblPrChange",
]

# CT_TcPrBase / CT_TcPr
TCPR_ORDER: List[str] = [
    "cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd",
    "noWrap", "tcMar", "textDirection", "tcFitText", "vAlign", "hideMark",
    "headers", "cellIns", "cellDel", "cellMerge", "tcPrChange",
]

# CT_TrPr
TRPR_ORDER: List[str] = [
    "cnfStyle", "divId", "gridBefore", "gridAfter", "wBefore", "wAfter",
    "cantSplit", "trHeight", "tblHeader", "tblCellSpacing", "jc", "hidden",
    "ins", "del", "trPrChange",
]

# CT_P: pPr must be the first child
P_ORDER: List[str] = ["pPr"]


def insert_ordered(parent, element, order: List[str]) -> None:
    """Place element among parent's children per the given tag sequence."""
    tag = _local(element.tag)
    try:
        idx = order.index(tag)
    except ValueError:
        parent.append(element)
        return
    for child in parent:
        ctag = _local(child.tag)
        try:
            cidx = order.index(ctag)
        except ValueError:
            continue
        if cidx > idx:
            child.addprevious(element)
            return
    parent.append(element)


def replace_ordered(parent, element, order: List[str]) -> None:
    """Drop any existing element with the same tag, then insert in order."""
    tag = _local(element.tag)
    for old in parent.findall(qn(f"w:{tag}")):
        parent.remove(old)
    insert_ordered(parent, element, order)


def after_ppr(p_element, element) -> None:
    """Bookmarks and runs must come after pPr, never before it."""
    ppr = p_element.find(qn("w:pPr"))
    if ppr is not None:
        ppr.addnext(element)
    else:
        p_element.insert(0, element)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
