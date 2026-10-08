"""Every tunable in one place. Nothing else in the package hardcodes a number."""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any


@dataclass
class Config:
    # ---- Model provider --------------------------------------------------
    # "ollama" runs the local model below. "openai" sends the same prompts
    # and page images to the OpenAI chat API instead.
    provider: str = "ollama"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_max_tokens: int = 4096

    # ---- Ollama ----------------------------------------------------------
    ollama_host: str = "http://localhost:11434"
    # ONE model does everything: OCR, figure description, tables, maths.
    ocr_model: str = "qwen3.5:4b"
    vlm_model: str = "qwen3.5:4b"
    ollama_timeout_s: int = 300
    ollama_keep_alive: str = "30m"
    ocr_num_ctx: int = 8192
    vlm_num_ctx: int = 8192
    temperature: float = 0.0
    # qwen3.5 reasons before answering and can spend its whole budget doing it
    disable_thinking: bool = True
    # offline = never touch the network; OCR returns empty, VLM returns a stub.
    # Use it for tests and for scoring the geometry half of the pipeline.
    offline: bool = False

    # ---- Rasterisation ---------------------------------------------------
    # What the MODEL is sent. Vision models bill by pixel count and are
    # trained around 150 DPI, so 300 costs four times as much for no gain.
    ocr_dpi: int = 150
    page_dpi: int = 300           # page raster kept for the reviewer compare view
    figure_dpi: int = 300         # vector figure rasterisation
    ocr_max_edge_px: int = 2200   # downscale before sending to the OCR model

    # ---- Page routing ----------------------------------------------------
    native_min_chars: int = 200   # >= this much real text on the page -> native
    hybrid_min_chars: int = 20    # between the two -> hybrid
    native_min_text_area: float = 0.02   # fraction of page area covered by text
    corrupt_text_ratio: float = 0.15     # above this the text layer is unusable

    # ---- Structure -------------------------------------------------------
    body_size_tolerance: float = 0.30   # pt band that counts as "the same size"
    heading_max_chars: int = 90
    heading_min_size_ratio: float = 1.06
    max_heading_levels: int = 4
    heading_min_pages: int = 3        # a size on fewer pages is a one-off
    heading_from_numbering: bool = True   # 1.2.6 decides the level, not the size
    heading_block_in_figure: bool = True  # text inside a figure is never a heading
    front_matter_max_pages: int = 8   # cover, copyright and contents
    caption_max_gap_pt: float = 40.0
    furniture_min_same_spot_pages: int = 3
    vlm_table_kinds: tuple = ("table",)   # model kinds offered to as_table
    text_only_min_line_pt: float = 6.5
    label_max_font_pt: float = 14.0
    pair_label_rows: bool = True
    concept_maps: bool = True            # boxes + arrows kept as one diagram
    concept_map_min_arrows: int = 3         # glossary: term + its own definition      # bigger type is a title, not a label   # smaller text is a screenshot   # same words, same spot = furniture
    caption_keep_printed_side: bool = True  # above the table, below the figure
    caption_prefixes: tuple = (
        "fig", "figure", "table", "diagram", "plate", "chart", "graph",
        "பட", "படம்",
    )
    # ---- layout (rules A and B) -----------------------------------------
    column_gutter_min_pt: float = 14.0
    column_min_lines: int = 6         # fewer lines than this: do not guess
    column_min_side_lines: int = 3    # text needed on each side of a gutter
    column_min_pairs: int = 3         # lines that actually sit side by side
    max_columns: int = 3
    full_width_frac: float = 0.70     # wider than this and it is a band break
    max_bands: int = 6                # more than this and the split is noise
    min_line_width_pt: float = 12.0   # shorter fragments never define a gutter
    gutter_noise_frac: float = 0.06   # coverage below this still counts as empty
    gutter_max_cross_frac: float = 0.22  # banners may cross a real gutter
    gutter_max_width_frac: float = 0.22  # wider than this is not a gutter
    gutter_valley_ratio: float = 2.5     # the sides must be this much busier
    # last rung of the gutter search: count rows crossing a narrow centre strip
    centre_corridor_lo_frac: float = 0.40
    centre_corridor_hi_frac: float = 0.60
    centre_corridor_min_rows: int = 10
    centre_corridor_max_cross_frac: float = 0.32
    # a gap that only reads across for part of the page is a table's column
    # gap, not the page gutter
    gutter_min_support_frac: float = 0.45
    gutter_contested_lines: int = 3   # below this, a gap needs no further proof
    # stacked fractions are rebuilt from the spans on the rule, not whole lines
    fold_fractions_at_span_level: bool = True
    fraction_rule_max_width_pt: float = 170.0
    fraction_leg_max_rise_pt: float = 13.0
    fraction_leg_max_drop_pt: float = 17.0
    fraction_leg_max_chars: int = 40
    detect_boxes: bool = True
    box_min_area_frac: float = 0.004
    box_max_area_frac: float = 0.75
    badge_max_lines: int = 2          # a title badge holds one short line
    narrow_box_frac: float = 0.30     # narrower than this and lines always join
    # a short line repeated in the same band on many pages is a running head
    drop_repeating_furniture: bool = True
    # stitch a sentence back together when the layout split it across blocks
    join_fragments: bool = True
    merge_lone_bullets: bool = True   # a bullet mark joins the text beside it
    strip_ocr_layout_tags: bool = True  # OCR models that answer in layout markup
    # the same string emitted twice at nearly the same spot: a shadow layer, a
    # transparency fallback, or two extraction paths returning one block
    dedupe_text: bool = True
    dedupe_text_min_chars: int = 4
    dedupe_text_shift_pt: float = 3.0
    line_join_max_gap_pt: float = 2.2   # multiplier of line height

    # ---- Bold detection on scans ----------------------------------------
    bold_ink_ratio: float = 1.28   # word ink density vs page median
    bold_min_word_px: int = 60

    # ---- Figures ---------------------------------------------------------
    figure_min_area_frac: float = 0.008   # of page area
    # An embedded image is something the publisher placed on purpose, so a
    # small one is a logo or a seal, not noise. Vector fragments need the
    # bigger floor; a native image gets this one.
    figure_min_area_frac_native: float = 0.0015
    figure_max_area_frac: float = 0.90    # above this it is a page background
    # a panel is a border around text, but artwork is often printed inside one.
    # after the panel itself is set aside its inside is searched again.
    panel_inner_figures: bool = True
    panel_inner_min_area_frac: float = 0.002
    # A PDF often stores one illustration as many image XObjects: 80% of the
    # clock in one, the hands and numerals in five more. Candidates are gathered
    # and clustered before anything is emitted, so the clock comes out once.
    fragment_merge: bool = True
    fragment_gap_pt: float = 7.0      # closer than this and they are one figure
    fragment_max_growth: float = 3.2  # a merge may not balloon a small piece
    # the same picture emitted twice, or a logo repeated on every page
    grid_min_parts: int = 3           # a tidy grid under one caption
    grid_size_tolerance: float = 1.6  # how alike the tiles must be
    prune_unused_figures: bool = True  # a crop whose block was dropped
    dedupe_images: bool = True
    dup_hash_bits: int = 16           # perceptual hash grid, 16 means 256 bits
    dup_max_distance: int = 10        # hamming distance that still counts as same
    # QR codes, barcodes and other machine codes are all dense noise, so any
    # hash puts them on top of each other. They are content and are never
    # deduplicated or called a watermark.
    skip_code_like_dedupe: bool = True
    repeat_image_page_frac: float = 0.30
    figure_merge_gap_px: int = 10
    figure_bleed_px: int = 4
    # a region that turns out to hold nothing but printed text is read out as
    # text and the picture is dropped, since a picture of a paragraph is not a
    # figure
    # two blocks on one baseline, one of them an equation, are one
    # expression printed in pieces
    join_split_math: bool = True
    text_only_to_text: bool = True
    text_only_min_chars: int = 12
    # a real figure keeps its picture and gets a visible description box under
    # it, so the description is readable in the document and not only in the
    # alt text
    figure_description_box: bool = True
    equation_description_box: bool = False
    # Every formula is also cut out of the page and kept as a picture, so the
    # printed truth survives whatever the reconstruction made of it.
    equation_snippets: bool = True
    equation_snippet_dpi: int = 220
    equation_snippet_pad_pt: float = 3.0
    describe_equations: bool = True
    # fallback: the picture is written only when OMML fails, which is the old
    # behaviour. always: the picture is written under every formula. never:
    # the picture is kept on disk and in book.json but not put in the docx.
    equation_images_in_docx: str = "fallback"
    table_description_box: bool = True
    table_note_max_rows: int = 12   # longer tables are summarised, not retyped
    # OFF by default: on a real book the splitter reads the white space
    # between two people in one photograph as a gap between two pictures.
    composite_split: bool = False
    composite_min_parts: int = 2
    composite_min_gap_pt: float = 10.0   # parts must be this far apart
    composite_require_caption: bool = True  # each part needs its own caption
    composite_all_or_nothing: bool = True   # lose one part, keep the original
    describe_figures: bool = True
    # A dynamic textbook has no opaque pixels in it. These three passes close
    # the last holes where content would otherwise survive only as an image.
    figure_spec: bool = True       # ask for a structure that can be redrawn
    vlm_math: bool = True          # read a formula the text layer could not
    rejoin_stacked_fractions: bool = True  # numerator over rule over denominator
    vlm_tables: bool = True        # pull a table out of a picture of a table
    emit_svg: bool = True          # redraw the spec as vector art
    spec_kinds: tuple = ("diagram", "chart", "map")

    # ---- Tables ----------------------------------------------------------
    table_min_cells: int = 4
    table_rule_min_len_frac: float = 0.25
    cell_recover_pad_frac: float = 0.35   # how far outside its box a value may sit

    # ---- Writer ----------------------------------------------------------
    template_name: str = "eduverse_base.docx"
    page_lock: bool = False        # one docx page per printed page
    show_page_markers: bool = True
    write_layout_docx: bool = False
    write_digital: bool = True     # digital/index.html, the dynamic textbook
    redraw: bool = False           # Gemini figure redraw, deferred
    embed_alt_text: bool = True
    # binding tokens live in a bookmark, not in the visible text
    inline_bind_tokens: bool = False

    # ---- Verification ----------------------------------------------------
    char_tolerance: float = 0.005  # 0.5 %
    fail_on_gate: bool = False     # report and continue by default

    # ---- Style sheet -----------------------------------------------------
    # name -> (font, size_pt, bold, space_before_pt, space_after_pt)
    styles: Dict[str, Any] = field(default_factory=lambda: {
        "EV Title":        ("Georgia", 26, True, 0, 18),
        "EV H1":           ("Georgia", 20, True, 18, 8),
        "EV H2":           ("Georgia", 16, True, 14, 6),
        "EV H3":           ("Georgia", 13, True, 10, 4),
        "EV H4":           ("Georgia", 11.5, True, 8, 4),
        "EV Body":         ("Georgia", 11, False, 0, 6),
        "EV Caption":      ("Arial", 9.5, False, 2, 10),
        "EV Table Header": ("Arial", 10, True, 2, 2),
        "EV Table Cell":   ("Arial", 10, False, 2, 2),
        "EV List Bullet":  ("Georgia", 11, False, 0, 3),
        "EV List Number":  ("Georgia", 11, False, 0, 3),
        "EV Equation":     ("Cambria Math", 11, False, 6, 6),
        "EV Note":         ("Arial", 8.5, False, 0, 2),
        "EV Box":          ("Georgia", 10.5, False, 0, 4),
        "EV Figure Note":  ("Arial", 9, False, 0, 2),
        "EV Figure Note Head": ("Arial", 8.5, True, 0, 2),
    })
    box_shading: str = "F2F1EC"
    box_panels_in_docx: bool = True   # Activity / Do you know panels boxed
    figure_note_shading: str = "F4F6F8"
    table_header_shading: str = "EFEDE6"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


DEFAULT = Config()
