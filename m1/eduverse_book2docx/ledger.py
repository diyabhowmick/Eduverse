"""Drop ledger. The invariant detected == emitted + dropped is the only thing
that catches silent loss, so every discard goes through here with a reason."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

REASONS = {
    "furniture_header": "running header or footer",
    "furniture_pageno": "page number",
    "furniture_printmark": "printing or InDesign production mark",
    "decorative": "decorative image with no content",
    "empty": "no text and no pixels",
    "duplicate": "same content already emitted",
    "below_min_area": "image region under the minimum area",
    "unsupported": "no writer for this block type",
    "ocr_empty": "OCR returned nothing for this region",
    "watermark": "logo or watermark repeated across pages",
    "outside_page": "bbox falls outside the page box",
}


@dataclass
class Ledger:
    detected: int = 0
    emitted: int = 0
    entries: List[Dict[str, Any]] = field(default_factory=list)
    _started: float = field(default_factory=time.time)

    def detect(self, n: int = 1) -> None:
        self.detected += n

    def emit(self, n: int = 1) -> None:
        self.emitted += n

    def drop(self, block_id: str, page: int, reason: str,
             detail: str = "", bbox: Optional[list] = None) -> None:
        self.entries.append({
            "id": block_id,
            "page": page,
            "reason": reason,
            "reason_text": REASONS.get(reason, reason),
            "detail": detail,
            "bbox": bbox,
        })

    @property
    def dropped(self) -> int:
        return len(self.entries)

    def balanced(self) -> bool:
        return self.detected == self.emitted + self.dropped

    def imbalance(self) -> int:
        return self.detected - (self.emitted + self.dropped)

    def by_reason(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for e in self.entries:
            out[e["reason"]] = out.get(e["reason"], 0) + 1
        return out

    def save(self, path) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "_summary": {
                    "detected": self.detected,
                    "emitted": self.emitted,
                    "dropped": self.dropped,
                    "balanced": self.balanced(),
                    "imbalance": self.imbalance(),
                    "by_reason": self.by_reason(),
                    "elapsed_s": round(time.time() - self._started, 1),
                }
            }, ensure_ascii=False) + "\n")
            for e in self.entries:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")
