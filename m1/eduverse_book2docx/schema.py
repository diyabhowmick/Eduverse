"""book.json data model.

Rule for the whole package: the writers read ONLY this. If a thing is not
here, fix the extractor, never the writer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Tuple

SCHEMA_VERSION = "2.0"

# Block types the writer knows how to emit.
BLOCK_TYPES = (
    "title",
    "heading",
    "paragraph",
    "list_item",
    "caption",
    "figure",
    "figure_note",   # the description box printed under a figure
    "table",
    "equation",
    "box",           # activity / do-you-know / sidebar
    "page_furniture",  # never written, always logged
)

FIG_KINDS = ("photo", "diagram", "chart", "map", "text_banner", "decorative")


def _r(v: float, n: int = 2) -> float:
    return round(float(v), n)


@dataclass
class Run:
    """A formatting span inside a block's text, by character offset."""
    s: int
    e: int
    bold: bool = False
    italic: bool = False
    underline: bool = False
    superscript: bool = False
    subscript: bool = False
    color: Optional[str] = None       # "RRGGBB"
    font: Optional[str] = None

    def styled(self) -> bool:
        return any([self.bold, self.italic, self.underline,
                    self.superscript, self.subscript, self.color])


@dataclass
class TableCell:
    row: int
    col: int
    text: str = ""
    runs: List[Run] = field(default_factory=list)
    row_span: int = 1
    col_span: int = 1
    is_header: bool = False
    bbox_pt: Optional[List[float]] = None
    blocks: List["Block"] = field(default_factory=list)  # nested figure/equation


@dataclass
class TableData:
    rows: int
    cols: int
    cells: List[TableCell] = field(default_factory=list)
    col_widths_pt: List[float] = field(default_factory=list)
    has_v_rules: bool = True
    has_h_rules: bool = True
    header_rows: int = 0


@dataclass
class FigureMeta:
    fig_kind: str = "photo"
    desc: str = ""
    entities: List[str] = field(default_factory=list)
    relationships: List[str] = field(default_factory=list)
    data_points: List[str] = field(default_factory=list)
    text_in_image: List[str] = field(default_factory=list)
    label: str = ""
    spec: Dict[str, Any] = field(default_factory=dict)   # regenerable structure
    regenerable: bool = False         # the spec is complete enough to redraw
    svg_ref: Optional[str] = None     # vector redraw built from the spec
    text_only: bool = False           # the region held nothing but printed text
    error: str = ""                   # why the description is missing, if it is
    part_of: Optional[str] = None     # id of the composite this was split from


@dataclass
class Block:
    id: str
    page: int
    type: str
    bbox_pt: List[float]                  # x0, y0, x1, y1 - top-left origin
    text: str = ""
    level: Optional[int] = None           # heading level 1..4
    heading_size: Optional[float] = None  # point size that made it a heading
    runs: List[Run] = field(default_factory=list)
    align: str = "left"                   # left|center|right|justify
    indent_level: int = 0
    column: int = 0
    order: int = 0
    source: str = ""                      # native_span|ocr|docx_style|vector|vlm_crop
    confidence: float = 1.0

    # figure
    image_ref: Optional[str] = None
    redraw_ref: Optional[str] = None
    px_w: Optional[int] = None
    px_h: Optional[int] = None
    figure: Optional[FigureMeta] = None

    # table
    table: Optional[TableData] = None

    # equation
    latex: Optional[str] = None
    latex_source: Optional[str] = None    # text_layer | vlm | docx
    omml_xml: Optional[str] = None        # raw OMML from a docx input
    math_desc: str = ""                   # a plain reading of the formula
    math_unreadable: bool = False
    display_math: bool = False
    eq_number: Optional[str] = None

    # relations
    caption_of: Optional[str] = None
    block_kind: Optional[str] = None       # activity|note|example|summary ...
    flags: List[str] = field(default_factory=list)
    font_size: Optional[float] = None      # largest printed size in the block
    box: int = -1                          # index into page.boxes_pt, -1 none

    # -- geometry helpers -------------------------------------------------
    @property
    def x0(self) -> float: return self.bbox_pt[0]

    @property
    def y0(self) -> float: return self.bbox_pt[1]

    @property
    def x1(self) -> float: return self.bbox_pt[2]

    @property
    def y1(self) -> float: return self.bbox_pt[3]

    @property
    def width(self) -> float: return self.bbox_pt[2] - self.bbox_pt[0]

    @property
    def height(self) -> float: return self.bbox_pt[3] - self.bbox_pt[1]

    def char_count(self) -> int:
        if self.type == "table" and self.table:
            return sum(len(c.text) for c in self.table.cells)
        return len(self.text or "")


@dataclass
class Page:
    page: int
    width_pt: float
    height_pt: float
    route: str = "native"            # native|hybrid|scanned|docx
    rotation: int = 0
    blocks: List[Block] = field(default_factory=list)
    raster_ref: Optional[str] = None
    columns: int = 1
    margins_pt: List[float] = field(default_factory=lambda: [56.0, 56.0, 56.0, 56.0])
    layout_confidence: float = 1.0
    layout_notes: List[str] = field(default_factory=list)
    boxes_pt: List[List[float]] = field(default_factory=list)


@dataclass
class Book:
    book_id: str
    source_file: str
    schema_version: str = SCHEMA_VERSION
    detected: Dict[str, Any] = field(default_factory=dict)
    pages: List[Page] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    # -- iteration ---------------------------------------------------------
    def blocks(self):
        for p in self.pages:
            for b in p.blocks:
                yield p, b

    def block_by_id(self, bid: str) -> Optional[Block]:
        for _, b in self.blocks():
            if b.id == bid:
                return b
        return None

    def counts(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for _, b in self.blocks():
            out[b.type] = out.get(b.type, 0) + 1
        return out

    def char_total(self) -> int:
        return sum(b.char_count() for _, b in self.blocks()
                   if b.type != "page_furniture")

    # -- io ----------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        for p in d["pages"]:
            for b in p["blocks"]:
                b["bbox_pt"] = [_r(v) for v in b["bbox_pt"]]
                for k in ("figure", "table", "runs"):
                    if not b.get(k):
                        b.pop(k, None)
                for k, v in list(b.items()):
                    if v is None or v == [] or v == "" or v is False:
                        if k not in ("text", "type", "id", "page", "bbox_pt"):
                            b.pop(k, None)
        return d

    def save(self, path) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, ensure_ascii=False, indent=2)

    @staticmethod
    def load(path) -> "Book":
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        return Book.from_dict(d)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Book":
        pages = []
        for pd in d.get("pages", []):
            blocks = [_block_from_dict(bd) for bd in pd.get("blocks", [])]
            pd = dict(pd)
            pd["blocks"] = blocks
            pages.append(Page(**pd))
        d = dict(d)
        d["pages"] = pages
        return Book(**d)


def _runs_from(lst) -> List[Run]:
    return [Run(**r) for r in (lst or [])]


def _cell_from(cd) -> TableCell:
    cd = dict(cd)
    cd["runs"] = _runs_from(cd.get("runs"))
    cd["blocks"] = [_block_from_dict(b) for b in cd.get("blocks", [])]
    return TableCell(**cd)


def _block_from_dict(bd: Dict[str, Any]) -> Block:
    bd = dict(bd)
    bd["runs"] = _runs_from(bd.get("runs"))
    if bd.get("figure"):
        bd["figure"] = FigureMeta(**bd["figure"])
    if bd.get("table"):
        td = dict(bd["table"])
        td["cells"] = [_cell_from(c) for c in td.get("cells", [])]
        bd["table"] = TableData(**td)
    return Block(**bd)
