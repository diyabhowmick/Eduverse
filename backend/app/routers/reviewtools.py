"""Reviewer tools for what the pipeline got wrong, fixed on the original page in one step, with no re-processing.

Crop on the original page:
    replace   the picture is cut off, too tight or has the wrong part: draw the right box
    join      a figure came out in pieces: draw one box round the whole thing, the other pieces are removed
    add       a picture is missing, or one picture should be two (split): draw a box, a new figure is added after
              the block you choose
Move a block up or down: text in the wrong order (columns, side boxes) is put right.

The crop is cut from the uploaded PDF at 200 DPI, so it is sharp whatever M1 did.
"""
import hashlib
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..audit import log
from ..db import get_db
from .. import content as C
from .review import get_book, editable, reviewer

router = APIRouter(prefix="/api/review", tags=["review tools"])
CROP_DPI = 200


class CropIn(BaseModel):
    box: list[float]                 # x0, y0, x1, y1 as fractions of the page, 0 to 1
    mode: str = "replace"            # replace | add
    block_id: str | None = None      # replace: the figure; add: the block the new picture goes after (none: end of page)
    remove: list[str] = []           # replace: other figures on this page that are pieces of this one
    caption: str = ""


def _crop(b, page: int, box: list[float]) -> tuple[bytes, int, int]:
    if not (b.original_key or "").lower().endswith(".pdf"):
        raise HTTPException(409, "Cropping needs the original PDF, and this book was uploaded in another format")
    if len(box) != 4 or not all(0 <= v <= 1 for v in box) or box[2] - box[0] < 0.02 or box[3] - box[1] < 0.02:
        raise HTTPException(422, "Draw a box round the picture first")
    import pymupdf
    with pymupdf.open(stream=C._store().get(b.original_key), filetype="pdf") as doc:
        if not 1 <= page <= doc.page_count:
            raise HTTPException(404, "No such page")
        pg = doc[page - 1]
        r = pg.rect
        clip = pymupdf.Rect(r.x0 + box[0] * r.width, r.y0 + box[1] * r.height, r.x0 + box[2] * r.width, r.y0 + box[3] * r.height)
        pix = pg.get_pixmap(dpi=CROP_DPI, clip=clip)
        return pix.tobytes("png"), pix.width, pix.height


def _blocks_of_page(data, page):
    """(chapter, parent list, block) for every block on this page, in order."""
    out = []
    for ch in data["chapters"]:
        def walk(lst):
            for blk in lst:
                if blk.get("type") == "box":
                    walk(blk["children"])
                if blk.get("page") == page or blk.get("page_end") == page:
                    out.append((ch, lst, blk))
        walk(ch["blocks"])
    return out


@router.post("/books/{bid}/pages/{page}/crop")
def crop(bid: int, page: int, body: CropIn, db: Session = Depends(get_db), me=Depends(reviewer)):
    b = get_book(db, bid, me); editable(b)
    png, w, h = _crop(b, page, body.box)
    key = f"images/crop_p{page}_{hashlib.sha1(png).hexdigest()[:12]}.png"
    C._store().put(f"{b.content_key}/{key}", png)
    data = C.load(b)
    on_page = _blocks_of_page(data, page)
    if body.mode == "replace":
        hit = next(((ch, lst, blk) for ch, lst, blk in on_page if blk.get("id") == body.block_id and blk.get("type") == "figure"), None)
        if not hit:
            raise HTTPException(404, "That picture is not on this page")
        blk = hit[2]
        before = blk.get("image")
        blk["image"], blk["width"], blk["height"] = key, w, h
        blk["crop"] = {"page": page, "box": [round(v, 4) for v in body.box], "by": me.email}
        blk.pop("m2", None)          # a redrawn version of the old crop no longer matches
        if body.caption.strip():
            blk["caption"] = body.caption.strip()
        removed = []
        for ch, lst, other in on_page:
            if other.get("id") in body.remove and other is not blk and other.get("type") == "figure":
                lst.remove(other); removed.append(other["id"])
        C.save(b, data)
        log(db, me, "review.figure_recrop", "book", bid, block=blk["id"], page=page, before=before, joined=removed)
        db.commit()
        return {"id": blk["id"], "image": key, "removed": removed}
    if body.mode == "add":
        new = {"type": "figure", "image": key, "width": w, "height": h, "number": "", "caption": body.caption.strip(), "desc": None,
               "page": page, "id": "r" + uuid.uuid4().hex[:8], "crop": {"page": page, "box": [round(v, 4) for v in body.box], "by": me.email}}
        anchor = next(((ch, lst, blk) for ch, lst, blk in on_page if blk.get("id") == body.block_id), None) if body.block_id else None
        if not anchor and on_page:
            anchor = on_page[-1]
        if anchor:
            ch, lst, blk = anchor
            new["section"] = blk.get("section", "")
            lst.insert(lst.index(blk) + 1, new)
        else:
            # a page with nothing on it yet: the unit whose pages surround it
            ch = next((c for c in data["chapters"] if (c.get("page_start") or 0) <= page <= (c.get("page_end") or 0)), data["chapters"][-1])
            new["section"] = (ch.get("sections") or [{"id": ""}])[0]["id"]
            ch["blocks"].append(new)
        C.save(b, data)
        log(db, me, "review.figure_add", "book", bid, block=new["id"], page=page)
        db.commit()
        return {"id": new["id"], "image": key}
    raise HTTPException(422, "Unknown crop mode")


class MoveIn(BaseModel):
    dir: str   # up | down


@router.post("/books/{bid}/blocks/{block_id}/move")
def move(bid: int, block_id: str, body: MoveIn, db: Session = Depends(get_db), me=Depends(reviewer)):
    """Put text back in the printed order: swap a block with the one before or after it."""
    b = get_book(db, bid, me); editable(b)
    data = C.load(b)
    ch, blk, parent = C.find_block(data, block_id)
    if not blk:
        raise HTTPException(404, "Block not found")
    lst = parent["children"] if parent else ch["blocks"]
    i = lst.index(blk); j = i - 1 if body.dir == "up" else i + 1
    if body.dir not in ("up", "down"):
        raise HTTPException(422, "Move up or down")
    if not 0 <= j < len(lst):
        raise HTTPException(409, "It is already at the " + ("top" if body.dir == "up" else "bottom"))
    lst[i], lst[j] = lst[j], lst[i]
    if lst[i].get("section") != blk.get("section") and lst[i].get("type") == "heading":
        blk["section"] = lst[i]["section"] if body.dir == "up" else blk.get("section")
    C.save(b, data)
    log(db, me, "review.block_move", "book", bid, block=block_id, dir=body.dir)
    db.commit()
    return {"ok": True}
