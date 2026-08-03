#!/usr/bin/env python3
"""Build BigFM Investor + Sales PPTX decks from captured screenshots.

Design system:
  navy    #0A0F1E
  purple  #8B5CF6
  pink    #EC4899
  cream   #F8FAFC
  Sans-serif Calibri; slide numbers bottom-right; footer BigFM · Confidential.
Border every screenshot with a 2 pt rounded rectangle.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.enum.shapes import MSO_SHAPE
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

SHOTS = Path("/app/decks/screenshots")
OUT_DIR = Path("/app/decks")

# Colors
NAVY   = RGBColor(0x0A, 0x0F, 0x1E)
NAVY2  = RGBColor(0x11, 0x18, 0x2E)
PURPLE = RGBColor(0x8B, 0x5C, 0xF6)
PINK   = RGBColor(0xEC, 0x48, 0x99)
CREAM  = RGBColor(0xF8, 0xFA, 0xFC)
SUBTLE = RGBColor(0x94, 0xA3, 0xB8)
DIM    = RGBColor(0x64, 0x74, 0x8B)
WHITE  = RGBColor(0xFF, 0xFF, 0xFF)
AMBER  = RGBColor(0xF5, 0x9E, 0x0B)
GREEN  = RGBColor(0x10, 0xB9, 0x81)

SLIDE_W = Inches(13.333)  # 16:9
SLIDE_H = Inches(7.5)


# ────── helpers ─────────────────────────────────

def new_deck() -> Presentation:
    p = Presentation()
    p.slide_width  = SLIDE_W
    p.slide_height = SLIDE_H
    return p


def add_bg(slide, color=NAVY):
    bg = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, SLIDE_H)
    bg.fill.solid(); bg.fill.fore_color.rgb = color
    bg.line.fill.background()
    bg.shadow.inherit = False
    return bg


def add_text(slide, x, y, w, h, text, *,
                        size=18, bold=False, color=WHITE, align=PP_ALIGN.LEFT,
                        font="Calibri"):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = 0
    tf.margin_top  = tf.margin_bottom = 0
    tf.text = ""
    lines = text.split("\n") if isinstance(text, str) else text
    first = True
    for ln in lines:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.alignment = align
        r = p.add_run()
        r.text = ln
        r.font.name  = font
        r.font.size  = Pt(size)
        r.font.bold  = bold
        r.font.color.rgb = color
    return tb


def add_bullet_list(slide, x, y, w, h, items, *,
                                    size=16, color=CREAM, bullet_color=PURPLE,
                                    line_spacing=1.35):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame; tf.word_wrap = True
    tf.margin_left = tf.margin_right = Emu(0)
    tf.margin_top  = tf.margin_bottom = Emu(0)
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.line_spacing = line_spacing
        r1 = p.add_run(); r1.text = "▸  "
        r1.font.color.rgb = bullet_color
        r1.font.name = "Calibri"; r1.font.size = Pt(size); r1.font.bold = True
        r2 = p.add_run(); r2.text = item
        r2.font.color.rgb = color
        r2.font.name = "Calibri"; r2.font.size = Pt(size)
    return tb


def add_footer_and_number(slide, num, total, *,
                                                    project="BigFM · Confidential"):
    add_text(slide, Inches(0.4), Inches(7.05), Inches(6),
                        Inches(0.35), project, size=9, color=DIM)
    add_text(slide, Inches(11.6), Inches(7.05), Inches(1.4),
                        Inches(0.35), f"{num} / {total}",
                        size=9, color=DIM, align=PP_ALIGN.RIGHT)


def add_image_with_border(slide, path, x, y, w, h, *,
                                                    border=PURPLE, border_pt=2.0):
    """Add a rounded-rectangle frame with a screenshot inside."""
    # Frame
    frame = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    frame.fill.solid(); frame.fill.fore_color.rgb = NAVY2
    frame.line.color.rgb = border
    frame.line.width = Pt(border_pt)
    # inset image slightly
    inset = Emu(int(0.03 * 914400))  # ~0.03"
    slide.shapes.add_picture(str(path),
                                                      x + inset, y + inset,
                                                      w - 2 * inset, h - 2 * inset)


def gradient_accent_bar(slide, x, y, w, h):
    """Purple → pink accent bar for section headings."""
    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, x, y, w, h)
    bar.fill.solid(); bar.fill.fore_color.rgb = PURPLE
    bar.line.fill.background()


def pill(slide, x, y, w, h, text, *, fill=PURPLE, text_color=WHITE, size=10):
    p = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    p.fill.solid(); p.fill.fore_color.rgb = fill
    p.line.fill.background()
    tf = p.text_frame
    tf.margin_left = tf.margin_right = Emu(0)
    tf.margin_top  = tf.margin_bottom = Emu(0)
    tf.text = ""
    para = tf.paragraphs[0]
    para.alignment = PP_ALIGN.CENTER
    r = para.add_run(); r.text = text
    r.font.name = "Calibri"; r.font.size = Pt(size); r.font.bold = True
    r.font.color.rgb = text_color


# ────── standard slide templates ─────────────────

def add_title_slide(prs, *, eyebrow, title, subtitle,
                                          images: list[Path], footer_note=None):
    """Cover slide with 3-screenshot montage."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    add_bg(slide, NAVY)

    # Diagonal accent
    accent = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,
                                                                                Inches(0), Inches(0),
                                                                                Inches(0.35), SLIDE_H)
    accent.fill.solid(); accent.fill.fore_color.rgb = PURPLE
    accent.line.fill.background()

    add_text(slide, Inches(0.9), Inches(0.9), Inches(9),
                        Inches(0.4), eyebrow.upper(),
                        size=10, color=PINK, bold=True)
    add_text(slide, Inches(0.9), Inches(1.3), Inches(11),
                        Inches(1.5), title,
                        size=54, bold=True, color=WHITE)
    add_text(slide, Inches(0.9), Inches(3.0), Inches(11),
                        Inches(1.0), subtitle,
                        size=22, color=SUBTLE)

    # 3-image montage (bottom right)
    if images:
        base_x = Inches(4.6); base_y = Inches(4.6)
        each_w = Inches(2.7); each_h = Inches(1.7)
        for i, img in enumerate(images[:3]):
            offset_x = Inches(0.6 * i)
            offset_y = Inches(0.15 * i)
            try:
                add_image_with_border(slide, img,
                                                            base_x + offset_x,
                                                            base_y - offset_y,
                                                            each_w, each_h,
                                                            border=PINK if i == 1 else PURPLE)
            except Exception:
                pass

    add_text(slide, Inches(0.9), Inches(6.7), Inches(11),
                        Inches(0.4),
                        footer_note or datetime.now().strftime("%B %Y · BigFM"),
                        size=11, color=DIM)


def add_content_slide(prs, num, total, *, title, subtitle=None,
                                                bullets=None, image=None,
                                                images=None, image_layout="right",
                                                caption=None):
    """Standard content slide.

    Layouts:
      • bullets + right image        (image_layout="right")
      • bullets + left image           (image_layout="left")
      • bullets full width               (no image)
      • image grid 2x2                    (images=[4 paths])
      • single big image                  (image, no bullets)
    """
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide)

    gradient_accent_bar(slide, Inches(0.4), Inches(0.6), Inches(0.6), Pt(3))
    add_text(slide, Inches(0.4), Inches(0.75), Inches(12.5),
                        Inches(0.9), title,
                        size=32, bold=True, color=WHITE)
    if subtitle:
        add_text(slide, Inches(0.4), Inches(1.5), Inches(12.5),
                            Inches(0.5), subtitle,
                            size=14, color=SUBTLE)

    top_y = Inches(2.1) if subtitle else Inches(1.7)

    if images and len(images) >= 4:  # 2x2 grid
        cell_w = Inches(5.7); cell_h = Inches(2.35)
        gap_x = Inches(0.25); gap_y = Inches(0.25)
        for i, (img, cap) in enumerate(images[:4]):
            r, c = divmod(i, 2)
            x = Inches(0.7) + c * (cell_w + gap_x)
            y = top_y + r * (cell_h + gap_y)
            add_image_with_border(slide, img, x, y, cell_w, cell_h)
            if cap:
                add_text(slide, x, y + cell_h + Emu(20000),
                                    cell_w, Inches(0.25), cap,
                                    size=10, color=SUBTLE,
                                    align=PP_ALIGN.CENTER)
    elif image is not None and bullets:
        # side-by-side: bullets + image
        if image_layout == "left":
            add_image_with_border(slide, image,
                                                        Inches(0.6), top_y,
                                                        Inches(6.0), Inches(4.5))
            add_bullet_list(slide, Inches(7.0), top_y,
                                              Inches(6.0), Inches(4.5),
                                              bullets, size=15)
        else:
            add_bullet_list(slide, Inches(0.6), top_y,
                                              Inches(6.0), Inches(4.5),
                                              bullets, size=15)
            add_image_with_border(slide, image,
                                                        Inches(7.0), top_y,
                                                        Inches(6.0), Inches(4.5))
        if caption:
            add_text(slide, Inches(7.0), top_y + Inches(4.55),
                                Inches(6), Inches(0.3), caption,
                                size=10, color=SUBTLE, align=PP_ALIGN.CENTER)
    elif image is not None:
        # single big image, centered
        add_image_with_border(slide, image,
                                                    Inches(1.7), top_y,
                                                    Inches(10.0), Inches(4.5))
        if caption:
            add_text(slide, Inches(0.4), top_y + Inches(4.6),
                                Inches(12.5), Inches(0.4), caption,
                                size=11, color=SUBTLE, align=PP_ALIGN.CENTER)
    elif bullets:
        add_bullet_list(slide, Inches(0.6), top_y,
                                          Inches(12.2), Inches(4.5),
                                          bullets, size=18, line_spacing=1.4)

    add_footer_and_number(slide, num, total)


def add_section_divider(prs, num, total, *, section, title, subtitle):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide, NAVY)
    # Full-height purple bar
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,
                                                                    Inches(0), Inches(0),
                                                                    Inches(4.5), SLIDE_H)
    bar.fill.solid(); bar.fill.fore_color.rgb = PURPLE
    bar.line.fill.background()

    add_text(slide, Inches(0.5), Inches(0.7), Inches(3.8),
                        Inches(0.5), section.upper(),
                        size=12, color=WHITE, bold=True)
    add_text(slide, Inches(5.0), Inches(2.6), Inches(8),
                        Inches(1.2), title,
                        size=44, bold=True, color=WHITE)
    add_text(slide, Inches(5.0), Inches(4.2), Inches(8),
                        Inches(1.5), subtitle,
                        size=18, color=SUBTLE)
    add_footer_and_number(slide, num, total)


def add_table_slide(prs, num, total, *, title, subtitle=None,
                                        headers, rows, col_widths=None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide)

    gradient_accent_bar(slide, Inches(0.4), Inches(0.6), Inches(0.6), Pt(3))
    add_text(slide, Inches(0.4), Inches(0.75), Inches(12.5),
                        Inches(0.9), title, size=32, bold=True, color=WHITE)
    if subtitle:
        add_text(slide, Inches(0.4), Inches(1.5), Inches(12.5),
                            Inches(0.5), subtitle, size=14, color=SUBTLE)

    n_cols = len(headers); n_rows = len(rows) + 1
    top = Inches(2.1) if subtitle else Inches(1.7)
    left = Inches(0.5); width = Inches(12.3); height = Inches(4.9)
    tbl_shape = slide.shapes.add_table(n_rows, n_cols, left, top,
                                                                                width, height)
    tbl = tbl_shape.table

    # Set column widths
    if col_widths:
        total_w = sum(col_widths)
        for j, w in enumerate(col_widths):
            tbl.columns[j].width = int(width * (w / total_w))

    # Header row
    for j, htext in enumerate(headers):
        cell = tbl.cell(0, j)
        cell.fill.solid(); cell.fill.fore_color.rgb = PURPLE
        cell.text = ""
        p = cell.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        r = p.add_run(); r.text = htext
        r.font.name = "Calibri"; r.font.size = Pt(13)
        r.font.bold = True; r.font.color.rgb = WHITE
        cell.margin_left = cell.margin_right = Emu(80000)
        cell.margin_top = cell.margin_bottom = Emu(50000)

    # Data rows
    for i, row in enumerate(rows, start=1):
        for j, val in enumerate(row):
            cell = tbl.cell(i, j)
            fill_color = NAVY2 if i % 2 == 1 else NAVY
            cell.fill.solid(); cell.fill.fore_color.rgb = fill_color
            cell.text = ""
            p = cell.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT
            r = p.add_run(); r.text = str(val)
            r.font.name = "Calibri"; r.font.size = Pt(11)
            r.font.color.rgb = CREAM
            cell.margin_left = cell.margin_right = Emu(80000)
            cell.margin_top = cell.margin_bottom = Emu(50000)

    add_footer_and_number(slide, num, total)


def add_grid_tiles_slide(prs, num, total, *, title, subtitle, tiles,
                                                    cols=3, rows=None):
    """Grid of tiles.  Each tile: dict(name, pitch, price, best_for, tint?)."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide)

    gradient_accent_bar(slide, Inches(0.4), Inches(0.6), Inches(0.6), Pt(3))
    add_text(slide, Inches(0.4), Inches(0.75), Inches(12.5),
                        Inches(0.9), title, size=32, bold=True, color=WHITE)
    if subtitle:
        add_text(slide, Inches(0.4), Inches(1.5), Inches(12.5),
                            Inches(0.5), subtitle, size=14, color=SUBTLE)

    if rows is None:
        rows = -(-len(tiles) // cols)  # ceil div

    top = Inches(2.1) if subtitle else Inches(1.7)
    total_w = Inches(12.5)
    tile_w = int(total_w / cols) - Emu(120000)
    tile_h = Inches(1.4) if rows > 3 else Inches(1.6)
    gap_x = Emu(120000)
    gap_y = Emu(120000)

    for idx, t in enumerate(tiles):
        r, c = divmod(idx, cols)
        x = Inches(0.4) + c * (tile_w + gap_x)
        y = top + r * (tile_h + gap_y)
        # Tile background
        tile = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                                                              x, y, tile_w, tile_h)
        tile.fill.solid(); tile.fill.fore_color.rgb = NAVY2
        tint = t.get("tint", PURPLE)
        tile.line.color.rgb = tint
        tile.line.width = Pt(1.0)
        tf = tile.text_frame
        tf.margin_left = tf.margin_right = Emu(100000)
        tf.margin_top = tf.margin_bottom = Emu(70000)
        tf.text = ""
        # Name
        p1 = tf.paragraphs[0]
        r1 = p1.add_run(); r1.text = t.get("name", "")
        r1.font.name = "Calibri"; r1.font.size = Pt(13); r1.font.bold = True
        r1.font.color.rgb = WHITE
        # Pitch
        p2 = tf.add_paragraph()
        r2 = p2.add_run(); r2.text = t.get("pitch", "")
        r2.font.name = "Calibri"; r2.font.size = Pt(9)
        r2.font.color.rgb = SUBTLE
        # Price / meta
        meta = t.get("price") or t.get("meta")
        if meta:
            p3 = tf.add_paragraph()
            r3 = p3.add_run(); r3.text = meta
            r3.font.name = "Calibri"; r3.font.size = Pt(9)
            r3.font.bold = True; r3.font.color.rgb = tint
        best = t.get("best_for")
        if best:
            p4 = tf.add_paragraph()
            r4 = p4.add_run(); r4.text = f"Best for: {best}"
            r4.font.name = "Calibri"; r4.font.size = Pt(8)
            r4.font.color.rgb = DIM
            r4.font.italic = True

    add_footer_and_number(slide, num, total)


def add_diagram_solution_slide(prs, num, total, *, title, subtitle,
                                                              rings):
    """Solution diagram: concentric labeled arcs."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide)

    gradient_accent_bar(slide, Inches(0.4), Inches(0.6), Inches(0.6), Pt(3))
    add_text(slide, Inches(0.4), Inches(0.75), Inches(12.5),
                        Inches(0.9), title, size=32, bold=True, color=WHITE)
    if subtitle:
        add_text(slide, Inches(0.4), Inches(1.5), Inches(12.5),
                            Inches(0.5), subtitle, size=14, color=SUBTLE)

    # Concentric circles centered around x=6.667, y=4.6
    center_x = Inches(4.2)
    center_y = Inches(4.6)
    radii = [Inches(2.9), Inches(2.3), Inches(1.7), Inches(1.1), Inches(0.55)]
    colors = [
        RGBColor(0x1E, 0x1E, 0x3F),
        RGBColor(0x2C, 0x22, 0x59),
        RGBColor(0x45, 0x2A, 0x72),
        RGBColor(0x63, 0x3A, 0x8F),
        PURPLE,
    ]
    for i, (r, color) in enumerate(zip(radii, colors)):
        oval = slide.shapes.add_shape(MSO_SHAPE.OVAL,
                                                                                center_x - r,
                                                                                center_y - r,
                                                                                r * 2, r * 2)
        oval.fill.solid(); oval.fill.fore_color.rgb = color
        oval.line.color.rgb = PINK if i == 4 else NAVY
        oval.line.width = Pt(0.8)
    # Center label
    add_text(slide, center_x - Inches(1.5), center_y - Inches(0.2),
                        Inches(3), Inches(0.4), "Listener",
                        size=13, color=WHITE, bold=True,
                        align=PP_ALIGN.CENTER)

    # Ring labels — right side
    ring_labels = rings  # list of (label, subtitle)
    lx = Inches(7.6)
    ly = Inches(2.2)
    for i, (lbl, sub) in enumerate(ring_labels):
        # Chip
        chip = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                                                                lx, ly + Inches(i * 0.85),
                                                                                Inches(0.7), Inches(0.55))
        chip.fill.solid(); chip.fill.fore_color.rgb = PURPLE
        chip.line.fill.background()
        tf = chip.text_frame
        tf.text = ""
        p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
        r = p.add_run(); r.text = str(i + 1)
        r.font.name = "Calibri"; r.font.size = Pt(16)
        r.font.bold = True; r.font.color.rgb = WHITE

        add_text(slide, lx + Inches(0.9), ly + Inches(i * 0.85),
                            Inches(5), Inches(0.35), lbl,
                            size=15, bold=True, color=WHITE)
        add_text(slide, lx + Inches(0.9), ly + Inches(i * 0.85 + 0.32),
                            Inches(5), Inches(0.3), sub,
                            size=11, color=SUBTLE)

    add_footer_and_number(slide, num, total)


# ────── screenshot lookup ──────────────────────

def s(name: str) -> Path:
    p = SHOTS / name
    if not p.exists():
        raise FileNotFoundError(p)
    return p


# =============== INVESTOR DECK =================================
def build_investor_deck():
    prs = new_deck()
    N = 18

    # 1 · Cover
    add_title_slide(prs,
        eyebrow="Series-A · Pitch",
        title="BigFM",
        subtitle="AI-powered radio + rewards + local commerce",
        images=[
            s("21_mobile_home.png"),
            s("03_marketplace_radiolife.png"),
            s("16_admin_home.png"),
        ],
        footer_note=f"{datetime.now().strftime('%B %Y')}  ·  BigFM · Confidential")

    # 2 · The Vision
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide, NAVY)
    gradient_accent_bar(slide, Inches(0.4), Inches(0.6), Inches(0.6), Pt(3))
    add_text(slide, Inches(0.4), Inches(0.75), Inches(12), Inches(0.9),
                        "The Vision", size=32, bold=True, color=WHITE)
    add_text(slide, Inches(1.2), Inches(2.9), Inches(11), Inches(2),
                        "Personalized live radio that turns listening\ninto real-world rewards.",
                        size=38, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    add_text(slide, Inches(1.2), Inches(5.3), Inches(11), Inches(0.6),
                        "Web, mobile — one player, one wallet, one AI RJ.",
                        size=16, color=SUBTLE, align=PP_ALIGN.CENTER)
    add_footer_and_number(slide, 2, N)

    # 3 · The Problem
    add_content_slide(prs, 3, N,
        title="The Problem",
        subtitle="Audio is broken along three axes.",
        bullets=[
            "Legacy radio is one-way and un-personalized — every listener hears the same content at the same time.",
            "Spotify solved on-demand but killed the shared radio moment — no live curation, no serendipity, no AI host.",
            "Local businesses can't buy hyperlocal audio ads programmatically — radio's ad stack still runs on faxed spot orders.",
        ],
        image=s("02_radio_browse_legacy.png"),
        image_layout="right",
        caption="Today's audio: fragmented, un-monetized locally, one-way.")

    # 4 · The Solution (diagram)
    add_diagram_solution_slide(prs, 4, N,
        title="The Solution",
        subtitle="One AI-curated radio stack — engagement layer + ad platform + local commerce.",
        rings=[
            ("Live radio · podcasts · news · trivia",
              "Non-interactive queue, AI RJ personas, breaking news ribbon"),
            ("Marketplace · wallet · rewards",
              "Save → visit → redeem → earn points loop"),
            ("11 ad products",
              "Boosts, sponsored reads, retargeting, coupon CPA, takeover…"),
            ("Admin console · analytics · ops",
              "QA dashboard, location intel, revenue live, notifications"),
        ])

    # 5 · Listener Experience  (2×2 grid)
    add_content_slide(prs, 5, N,
        title="Listener Experience",
        subtitle="One player. Every discovery / save / learn / redeem in one flow.",
        images=[
            (s("01_home_radiolife.png"),   "Home · Discover"),
            (s("03_marketplace_radiolife.png"), "Marketplace · Save"),
            (s("04_news_live_radiolife.png"),  "News · Learn"),
            (s("06_wallet_radiolife.png"),      "Wallet · Redeem"),
        ])

    # 6 · The Radio Engine
    add_content_slide(prs, 6, N,
        title="The Radio Engine",
        subtitle="Server-side personalized queue + AI RJ voiceovers + geo-flagship routing.",
        bullets=[
            "Non-interactive queue: no on-demand search, no per-song skip abuse — protects rights + creates a moment.",
            "AI RJ personas (ElevenLabs) bridge songs with real-time weather / commute / mood context.",
            "Flagship routing gives 15 stations first-shelf placement per region, with pre-roll parity across community stations.",
            "Compliance rules baked in: hourly skip cap, cross-station artist cooldown, sponsor read frequency guard.",
        ],
        image=s("08_station_detail.png"),
        image_layout="right",
        caption="Big FM 106.2 station page · flagship + AI RJ chips.")

    # 7 · Podcasts / News / Trivia (grid)
    add_content_slide(prs, 7, N,
        title="The Engagement Flywheel",
        subtitle="Complementary formats, one login, one wallet — every action feeds points.",
        images=[
            (s("05_podcasts_radiolife.png"),   "Podcasts"),
            (s("04_news_live_radiolife.png"),  "News · Live"),
            (s("07_trivia_radiolife.png"),      "Trivia lobby"),
            (s("06_wallet_radiolife.png"),      "Rewards wallet"),
        ])

    # 8 · Commerce Loop
    add_content_slide(prs, 8, N,
        title="Commerce Loop: Marketplace + Wallet + Rewards",
        subtitle="Save → visit → redeem → earn — three monetization tiers baked in.",
        bullets=[
            "Save a coupon in-app → adds to Wallet, redeemable at merchant.",
            "Visit merchant → geofence detects proximity → passive reward accrual.",
            "Scan-to-pay flow: Stripe Connect app fee split, real-time reconciliation.",
            "Points ledger: earn from listening, saving, redeeming — spend on premium unlocks.",
            "Every merchant txn: platform fee, coupon CPA charge, referral bonus — three layers.",
        ],
        image=s("03_marketplace_radiolife.png"),
        image_layout="right")

    # 9 · AI RJ Personas
    add_content_slide(prs, 9, N,
        title="AI RJ Personas",
        subtitle="Voice-branded AI hosts (ElevenLabs) — advertisers can sponsor their reads.",
        bullets=[
            "10 curated personas across dayparts (morning, drive, lunch, night, Friday, devotional).",
            "Each persona has voice + tagline + LLM-driven script conditioned on song, weather, hour, city.",
            "Sponsored RJ reads are a first-class ad product — pay-per-play or takeover-hour bundles.",
            "Admins govern persona safety + brand consistency from the console.",
        ],
        image=s("19_admin_rj_personas.png"),
        image_layout="right",
        caption="Admin RJ personas management console.")

    # 10 · Location-Aware
    add_content_slide(prs, 10, N,
        title="Location-Aware Everything",
        subtitle="Commute mode + geofenced ads + hyperlocal analytics all share one geo pipeline.",
        bullets=[
            "Commute mode auto-detects morning / evening drive windows and swaps into a shorter-song queue.",
            "Geofences drive location-boost ads — advertisers reach listeners within 500 m of their storefront.",
            "Foot-traffic linkage attributes scan-to-pay conversions to the ad impression within a 60-min window.",
            "Admin location-intel dashboard exposes it all: heatmaps, regions rank, geofence effectiveness.",
        ],
        image=s("18_admin_location_intel.png"),
        image_layout="right",
        caption="Admin location intelligence dashboard.")

    # 11 · Monetization Stack — table
    add_table_slide(prs, 11, N,
        title="The Monetization Stack",
        subtitle="11 ad products in one platform · one payment rail · one analytics view.",
        headers=["Product",                             "One-line pitch",                                                                            "Pricing model"],
        col_widths=[3, 6, 2.2],
        rows=[
            ("Flagship Boosts",                    "Direct-bid auction for time-boxed slots on flagship stations.",         "CPA (bid) + Stripe"),
            ("Sponsored AI RJ Reads",       "Advertisers sponsor the AI host's bridge between songs.",                    "CPM · pack"),
            ("Location-Boost Ads",              "Geofenced audio + banner ads reaching listeners within 500 m.",     "CPM · geofence"),
            ("Marketplace Featured Slots", "Boosted deal placement above the marketplace grid.",                            "Flat · slot"),
            ("Radio Takeover Hour",            "Own an entire hour: branded overlay + 4 sponsor reads + bonus.",   "$100 – $1000 / hr"),
            ("Retargeting Audiences",       "Re-engage listeners who saved but didn't redeem.  11 signals.",           "CPM · audience"),
            ("Coupon Campaigns (CPA/CPS/Hybrid)", "Pay only when a real customer redeems your coupon.",                "$2 / redemption avg"),
            ("Podcast Completion Rewards", "Sponsor a podcast episode + bonus points to finishers.",                        "CPM + reward"),
            ("Trivia Sponsorships",              "Sponsor a trivia round with branded prize + logo.",                                    "Flat · round"),
            ("Banner Ads",                              "Persistent skyscraper + billboard slots across web.",                              "CPM · placement"),
            ("Notification Campaigns",       "Push a targeted deal / promo to segmented users.",                                    "CPA · send"),
        ])

    # 12 · Advertiser Self-Serve
    add_content_slide(prs, 12, N,
        title="Advertiser Self-Serve",
        subtitle="From signup → live campaign in under 10 minutes.  Stripe Connect + prepaid budgets.",
        bullets=[
            "Register, verify, top up — same flow as Uber advertising or Meta Ads Manager.",
            "Wizard-driven creation for every ad product (no sales rep required for < $500).",
            "Real-time budget burn indicator + impression cap enforcement.",
            "Admin gate kicks in at $500+ for compliance + brand-safety review.",
            "Every campaign wires into the same conversion attribution pipeline (scan-to-pay, coupon redeem, wallet save).",
        ],
        image=s("09_adver_dashboard.png"),
        image_layout="right",
        caption="Advertiser dashboard overview.")

    # 13 · Admin Ops
    add_content_slide(prs, 13, N,
        title="Admin Ops & Analytics",
        subtitle="Full operational cockpit — every phase from R (news) to T (admin home) unified.",
        images=[
            (s("16_admin_home.png"),           "Admin Home"),
            (s("17_admin_qa.png"),                "QA Dashboard"),
            (s("18_admin_location_intel.png"),  "Location Intel"),
            (s("20_admin_news.png"),            "News moderation"),
        ])

    # 14 · Dual Platform
    add_content_slide(prs, 14, N,
        title="Dual Platform — Web + Mobile",
        subtitle="Same backend.  Native Expo mobile app mirrors every web surface.",
        images=[
            (s("01_home_radiolife.png"),      "Web · Home"),
            (s("21_mobile_home.png"),          "Mobile · Home"),
            (s("04_news_live_radiolife.png"), "Web · News"),
            (s("22_mobile_news.png"),          "Mobile · News"),
        ])

    # 15 · Traction Highlights
    add_content_slide(prs, 15, N,
        title="Traction Highlights",
        subtitle="Engineering velocity translates directly to product surface.",
        bullets=[
            "58,557 imported radio stations · fully searchable · dual-scheme (HTTP-proxy + HTTPS).",
            "818 podcast channels · 3,935 episodes · progressive completion rewards.",
            "23 notification recipes wired · segmented by geo + role + behavior.",
            "21 shipped phases · dual-design system (Legacy dark + RadioLife light).",
            "Complete admin ops surface: QA dashboard, location intel, revenue-live, ad-review queue.",
            "Web + Expo mobile mirror sharing 100% of the same backend + ad pipeline.",
        ])

    # 16 · Business Model
    add_content_slide(prs, 16, N,
        title="Business Model",
        subtitle="Diversified revenue.  Marginal cost per additional listener is near zero.",
        bullets=[
            "Platform take: 20–40% of ad prepayments across 11 products (highest on takeover + coupon CPA).",
            "Stripe app-fee on every scan-to-pay txn: 2.5–5% depending on merchant tier.",
            "Premium listener tier (Q1 roadmap): $2.99 / mo — skip-limit removal, ad-free, HD stream.",
            "Unit economics: no COGS per listener beyond streaming bandwidth + LLM/TTS variable cost.",
            "Revenue-share with claimed stations: 70/30 direct-sold, 50/50 programmatic backfill.",
        ])

    # 17 · Roadmap
    add_table_slide(prs, 17, N,
        title="Roadmap · Next 4 Quarters",
        subtitle="Growth + platform depth + partner integrations.",
        headers=["Quarter", "Focus",                                                                                                      "Outcome"],
        col_widths=[1.2, 4.5, 4],
        rows=[
            ("Q1", "Mobile Tier 2 · user_location_pings real persistence · premium subs",  "Push adoption + new revenue tier"),
            ("Q2", "Retargeting hooks across remaining 6 ad types · ML slot recommendation",  "+25% campaign ROI"),
            ("Q3", "OpenRTB adapter · partner POS APIs · station claim wizard v2",         "Programmatic backfill · POS attribution"),
            ("Q4", "Expansion markets (SG, IN) · creator marketplace · social passport",  "Multi-market SaaS + creator economy"),
        ])

    # 18 · The Ask
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide, NAVY)
    gradient_accent_bar(slide, Inches(0.4), Inches(0.6), Inches(0.6), Pt(3))
    add_text(slide, Inches(0.4), Inches(0.75), Inches(12.5), Inches(0.9),
                        "The Ask", size=32, bold=True, color=WHITE)
    add_text(slide, Inches(1.0), Inches(2.4), Inches(11), Inches(1.2),
                        "[ Placeholder ]", size=36, bold=True, color=AMBER,
                        align=PP_ALIGN.CENTER)
    add_text(slide, Inches(1.0), Inches(3.6), Inches(11), Inches(0.7),
                        "$X to accelerate to Y outcome.", size=22, color=WHITE,
                        align=PP_ALIGN.CENTER)
    add_bullet_list(slide, Inches(2.5), Inches(4.6), Inches(9), Inches(2),
                                      ["Use of funds: engineering (mobile Tier 2 + OpenRTB), sales team ramp, expansion markets, creator marketplace pilot.",
                                        "Milestones: 3 expansion markets live, 100+ paying advertisers, $X ARR, premium subs revenue mix.",
                                        "Contact: [ your contact block here — email, phone, calendar link ]."],
                                      size=13, line_spacing=1.35)
    add_footer_and_number(slide, 18, N)

    out = OUT_DIR / "BigFM_Investor_Deck.pptx"
    prs.save(str(out))
    return out, len(prs.slides.__iter__.__self__._sldIdLst)


# =============== SALES DECK =================================
def build_sales_deck():
    prs = new_deck()
    N = 20  # 18 previous + 1 reliability slide = 19; +Close = 20

    # 1 · Cover
    add_title_slide(prs,
        eyebrow="Sales Playbook · v1",
        title="BigFM Sales Playbook",
        subtitle="How to sell BigFM — to advertisers AND radio stations.",
        images=[
            s("09_adver_dashboard.png"),
            s("14_adver_coupons.png"),
            s("16_admin_home.png"),
        ],
        footer_note=f"{datetime.now().strftime('%B %Y')}  ·  BigFM · Confidential  ·  Internal")

    # 2 · What Is BigFM (60-sec pitch)
    add_content_slide(prs, 2, N,
        title="What Is BigFM  ·  60-second Pitch",
        subtitle=None,
        bullets=[
            "BigFM is a personalized live radio + local commerce + rewards platform.",
            "Listeners get an AI-curated stream with real AI radio hosts (ElevenLabs voices).",
            "Every action — listen, save a coupon, visit a merchant — earns points redeemable in-app.",
            "Advertisers self-serve 11 ad products via one dashboard (Stripe Connect, prepaid).",
            "Radio station owners monetize their digital stream through BigFM's ad demand + 70/30 rev share.",
        ],
        image=s("21_mobile_home.png"),
        image_layout="right",
        caption="Mobile home · listener view (Expo app).")

    # 3 · Who We Sell To
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide)
    gradient_accent_bar(slide, Inches(0.4), Inches(0.6), Inches(0.6), Pt(3))
    add_text(slide, Inches(0.4), Inches(0.75), Inches(12.5), Inches(0.9),
                        "Who We Sell To", size=32, bold=True, color=WHITE)
    add_text(slide, Inches(0.4), Inches(1.5), Inches(12.5), Inches(0.5),
                        "Two very distinct personas — pitch each with the same product but different lenses.",
                        size=14, color=SUBTLE)
    # Left card
    left = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                                                                  Inches(0.5), Inches(2.2),
                                                                                  Inches(6.1), Inches(4.6))
    left.fill.solid(); left.fill.fore_color.rgb = NAVY2
    left.line.color.rgb = PURPLE; left.line.width = Pt(1.2)
    tf = left.text_frame; tf.margin_left = tf.margin_right = Emu(200000)
    tf.margin_top = tf.margin_bottom = Emu(200000); tf.text = ""
    p = tf.paragraphs[0]; r = p.add_run(); r.text = "LOCAL BUSINESSES"
    r.font.name = "Calibri"; r.font.size = Pt(14); r.font.bold = True
    r.font.color.rgb = PURPLE
    p = tf.add_paragraph(); r = p.add_run(); r.text = "Restaurants · retail · events · clinics"
    r.font.name = "Calibri"; r.font.size = Pt(11); r.font.color.rgb = SUBTLE
    p = tf.add_paragraph(); p.line_spacing = 1.6; r = p.add_run()
    r.text = "\nPain:\n\"I can't reach commuters at lunchtime. Facebook ads no longer convert. Radio ads are too expensive for a 3-store chain.\""
    r.font.name = "Calibri"; r.font.size = Pt(13); r.font.color.rgb = WHITE
    p = tf.add_paragraph(); r = p.add_run(); r.text = "\nSell: coupons (CPA), location-boost, sponsored RJ reads.\nEntry point: $50 first campaign, pay-per-redemption."
    r.font.name = "Calibri"; r.font.size = Pt(11); r.font.color.rgb = AMBER

    # Right card
    right = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                                                                    Inches(6.8), Inches(2.2),
                                                                                    Inches(6.1), Inches(4.6))
    right.fill.solid(); right.fill.fore_color.rgb = NAVY2
    right.line.color.rgb = PINK; right.line.width = Pt(1.2)
    tf = right.text_frame; tf.margin_left = tf.margin_right = Emu(200000)
    tf.margin_top = tf.margin_bottom = Emu(200000); tf.text = ""
    p = tf.paragraphs[0]; r = p.add_run(); r.text = "RADIO STATION OWNERS"
    r.font.name = "Calibri"; r.font.size = Pt(14); r.font.bold = True
    r.font.color.rgb = PINK
    p = tf.add_paragraph(); r = p.add_run(); r.text = "Community · flagship · religious · niche"
    r.font.name = "Calibri"; r.font.size = Pt(11); r.font.color.rgb = SUBTLE
    p = tf.add_paragraph(); p.line_spacing = 1.6; r = p.add_run()
    r.text = "\nPain:\n\"Traditional ad-slot revenue is capped. My digital stream serves listeners but nobody pays for it. Salespeople for programmatic ads never call back.\""
    r.font.name = "Calibri"; r.font.size = Pt(13); r.font.color.rgb = WHITE
    p = tf.add_paragraph(); r = p.add_run(); r.text = "\nSell: partnership · 70/30 rev share · zero-cost onboarding.\nEntry point: free claim + owner dashboard."
    r.font.name = "Calibri"; r.font.size = Pt(11); r.font.color.rgb = AMBER
    add_footer_and_number(slide, 3, N)

    # 4 · Why Now / Why BigFM
    add_content_slide(prs, 4, N,
        title="Why Now  ·  Why BigFM",
        subtitle="Three category shifts converging in 2026.",
        bullets=[
            "Personalized audio adoption: 70%+ of drive-time listeners now stream (not FM antenna).",
            "Hyperlocal ad spend shifting from Facebook / Meta back to native audio + geo — attribution finally works.",
            "AI voice branding: ElevenLabs-grade voices at $0.05/min make sponsored RJ reads cost-competitive with pre-recorded spots.",
            "Radio station owners have LOTS of digital reach but zero programmatic revenue — a supply-side gap begging for demand.",
        ])

    # 5 · Section A · Product diagram (reuse investor diagram)
    add_diagram_solution_slide(prs, 5, N,
        title="The BigFM Product",
        subtitle="One player · four value layers · one wallet across all of them.",
        rings=[
            ("Live radio · podcasts · news · trivia",  "Engagement surface"),
            ("Marketplace · wallet · rewards",              "Commerce loop"),
            ("11 ad products",                                          "Monetization engine"),
            ("Admin console · analytics · ops",              "Governance + insights"),
        ])

    # 6 · Section B · 11 Ad Products at a Glance
    add_grid_tiles_slide(prs, 6, N,
        title="11 Ad Products At A Glance",
        subtitle="Every product ships with real-time analytics + a Stripe test-mode entry.",
        tiles=[
            {"name":"Flagship Boost",          "pitch":"Direct-bid auction, hour-length flagship slot.",
              "price":"Bid $50+",                        "best_for":"Big brands, launches"},
            {"name":"Sponsored RJ Read",  "pitch":"AI host bridges songs with your brand.",
              "price":"CPM $8-15",                      "best_for":"Personal-voice brands"},
            {"name":"Location Boost",          "pitch":"Geofence within 500 m of your storefront.",
              "price":"$0.10-0.50 / imp",          "best_for":"QSR, dine-in"},
            {"name":"Marketplace Featured","pitch":"Above-the-fold placement in the deals grid.",
              "price":"$5-25 / day",                    "best_for":"Any merchant"},
            {"name":"Takeover Hour",            "pitch":"Own the entire hour: overlay + 4 reads.",
              "price":"$100-$1000 / hr",          "best_for":"Movies, festivals"},
            {"name":"Retargeting",                "pitch":"Re-engage listeners who saved but never redeemed.",
              "price":"CPM $12",                          "best_for":"Chains, services"},
            {"name":"Coupon (CPA / CPS)",  "pitch":"Pay only per redemption or per sale.",
              "price":"$2 / redemption",           "best_for":"Restaurants, retail"},
            {"name":"Podcast Reward",          "pitch":"Bonus points to listeners who finish your episode.",
              "price":"CPM + bonus",                    "best_for":"Media, brand storytelling"},
            {"name":"Trivia Sponsor",            "pitch":"Sponsor a trivia round with logo + prize.",
              "price":"$25-$150 / round",         "best_for":"Toys, snacks, brands"},
            {"name":"Banner Ads",                  "pitch":"Persistent skyscraper + billboard slots.",
              "price":"CPM $5-10",                        "best_for":"Awareness campaigns"},
            {"name":"Notification Campaign","pitch":"Push a segmented offer to your ideal user.",
              "price":"CPA $0.20-1.50",              "best_for":"Retention, promos"},
        ], cols=3, rows=4)

    # 7 · Deep-dive · Coupon Campaigns
    add_content_slide(prs, 7, N,
        title="Deep-dive · Coupon Campaigns (CPS / CPA / Hybrid)",
        subtitle="Only pay when a real customer redeems.  Fraud-refund built in.",
        bullets=[
            "Advertiser sets: $ per redemption, cap per day, geo, category.",
            "Every redemption is verified merchant-side (scan-to-pay or manual code).",
            "Fraud detection: velocity + IP + device fingerprint → auto-refund suspicious rows.",
            "Real-time dashboard: impressions → saves → redemptions.",
            "Price: $2 / redemption typical.  Ideal for: restaurants, retail.",
        ],
        image=s("14_adver_coupons.png"),
        image_layout="right")

    # 8 · Deep-dive · Location-Boost Ads
    add_content_slide(prs, 8, N,
        title="Deep-dive · Location-Boost Ads",
        subtitle="Geofence your storefront.  Reach listeners within 500 m at lunch / dinner.",
        bullets=[
            "Draw a fence on the map — up to 5 zones per campaign.",
            "Density preview shows estimated reach + competing campaigns before you launch.",
            "Ad plays as a mid-stream audio spot + companion banner on mobile.",
            "Scan-to-pay conversions within 60 min → automatically attributed to the impression.",
            "Price: $0.10-$0.50 / impression.  Ideal for: QSR, dine-in.",
        ],
        image=s("13_adver_location_boosts.png"),
        image_layout="right")

    # 9 · Deep-dive · Radio Takeover Hour
    add_content_slide(prs, 9, N,
        title="Deep-dive · Radio Takeover Hour",
        subtitle="Own an entire hour on a flagship station.  Branded overlay + 4 sponsor reads + featured deals + 20-min-listen bonus.",
        bullets=[
            "One brand · one flagship station · one hour · saturated presence.",
            "Includes: 4 AI-RJ sponsor reads, banner takeover, hero deal on marketplace, bonus points to listeners who tune in ≥ 20 min.",
            "Live analytics: unique reach, avg time-on-station, deal saves.",
            "Price: $100 – $1,000 / hour depending on station tier and daypart.",
            "Ideal for: movie launches, festivals, product releases, election campaigns.",
        ],
        image=s("12_adver_takeover_hours.png"),
        image_layout="right")

    # 10 · Deep-dive · Retargeting Audiences
    add_content_slide(prs, 10, N,
        title="Deep-dive · Retargeting Audiences",
        subtitle="Re-engage people who saved your coupon but haven't redeemed.  11 behavioral signals to slice.",
        bullets=[
            "Signal library: saved-not-redeemed, viewed-but-not-saved, scanned-once-not-repeat, geo-frequent, hour-consistent, and 6 more.",
            "Build an audience via drag + drop signals → run any ad product against it.",
            "Attribution: each redemption/scan is tagged with the audience it fired from.",
            "Ideal for: mid-size chains + service businesses with a nurture cycle.",
        ],
        image=s("11_adver_retargeting.png"),
        image_layout="right")

    # 11 · Advertiser Onboarding Flow (comic strip)
    add_content_slide(prs, 11, N,
        title="Advertiser Onboarding · Comic Strip",
        subtitle="From signup to live campaign in under 10 minutes.",
        images=[
            (s("09_adver_dashboard.png"),    "1 · Sign up + top up (Stripe test-mode)"),
            (s("10_adver_flagship_boosts.png"),  "2 · Pick a product (Flagship Boost shown)"),
            (s("14_adver_coupons.png"),          "3 · Configure creative + budget"),
            (s("15_adver_marketplace_slots.png"), "4 · Ship it — analytics live in 60 s"),
        ])

    # 12 · Objection Handling
    add_table_slide(prs, 12, N,
        title="Objection Handling · Rehearsed Responses",
        subtitle="Six common objections + tight rebuttals.  Practice these.",
        headers=["Objection",                                                                       "Response"],
        col_widths=[3.5, 6.5],
        rows=[
            ("\"Too small for radio.\"",                                                       "Start with $50 CPA coupon — pay only per redemption.  No minimum spend."),
            ("\"How do I know it works?\"",                                       "Every campaign shows real-time impressions + saves + redemptions in the advertiser dashboard.  Numbers refresh every 30 s."),
            ("\"I already use Facebook.\"",                                       "Great — retargeting hooks let you upload your Facebook Custom Audience and re-engage on audio.  Complementary, not substitute."),
            ("\"Radio is dead.\"",                                                             "58,557 stations streaming, 70%+ commute audio via streaming.  We serve HTTPS-safe streams to any browser.  Radio moved online — you missed it."),
            ("\"How is this different from Spotify Ads?\"",         "Spotify sells CPM against a global impression pool.  We sell CPA against locally-attributed conversions.  You pay only when someone shows up."),
            ("\"What if you go down / bug in your platform?\"", "Same-day fixes.  Ad Ops rigor: broken creatives auto-skip in 2 s.  See next slide."),
        ])

    # 13 · Case Study Fixture
    add_content_slide(prs, 13, N,
        title="Case Study · Karak Cafe",
        subtitle="End-to-end flow demonstrated in test mode — real DB rows, real conversions.",
        bullets=[
            "Karak Cafe · Karama location · lat/lng geofenced 500 m.",
            "Ran a $2/redemption coupon + a location-boost during lunch (11:30 – 14:00).",
            "3 nearby-user pings within the geofence · 2 unique users · 1 scan-to-pay conversion tied to the impression.",
            "QA dashboard shows the flow live under Location Intel + Recent Activity.",
            "Real Stripe test-mode charge captured on the merchant side.",
        ],
        image=s("18_admin_location_intel.png"),
        image_layout="right",
        caption="Admin location intel · Karak proximity view.")

    # 14 · Section C · Station Partnership Value Prop
    add_content_slide(prs, 14, N,
        title="Station Partnership · Value Prop",
        subtitle="Three reasons every station owner should claim their listing today.",
        bullets=[
            "Add BigFM's stream proxy to your player — instantly monetize your digital audience with zero infra work.",
            "Access BigFM's advertiser network — we bring you demand, you keep 70% (direct-sold) or 50% (programmatic backfill).",
            "Owner dashboard shows real listener count, geographic distribution, revenue by product, pre-roll fill rate.",
            "Free HTTPS stream proxy fixes mixed-content bugs that kill your browser audience today.",
        ],
        image=s("02_radio_browse_legacy.png"),
        image_layout="right")

    # 15 · How Station Onboarding Works
    add_content_slide(prs, 15, N,
        title="Station Onboarding · 4 Steps",
        subtitle="Free.  Under 15 minutes.  Revenue starts flowing on the next month's cycle.",
        bullets=[
            "1 · Claim your station in the BigFM catalog (search + click).",
            "2 · Verify ownership (broadcast email match OR admin manual review).",
            "3 · Enable pre-roll + AI RJ personas (per-station toggles).",
            "4 · Revenue starts on next month's payout cycle (Stripe Connect).",
            "Bonus: your station gets flagship consideration if you serve a language / region under-represented in the current catalog.",
        ],
        image=s("08_station_detail.png"),
        image_layout="right",
        caption="Big FM 106.2 · station detail page with claim CTA.")

    # 16 · Revenue Share Model
    add_table_slide(prs, 16, N,
        title="Revenue Share Model",
        subtitle="Configurable per station in admin panel · numbers below are our default proposal.",
        headers=["Revenue source",                                          "Station",  "BigFM",    "Notes"],
        col_widths=[4.5, 1.5, 1.5, 3.0],
        rows=[
            ("Direct-sold ad plays on your station",                  "70%",         "30%",         "Advertiser-picked stations only"),
            ("Sponsored AI RJ reads on your station",              "60%",         "40%",         "BigFM handles voice + LLM cost"),
            ("Programmatic backfill (network-wide auction)",  "50%",         "50%",         "OpenRTB adapter (Q3 roadmap)"),
            ("Takeover Hour hosted on your station",              "80%",         "20%",         "Station carries the whole hour"),
            ("Marketplace featured slot conversions",              "0%",          "100%",     "Merchant-side ad, not station-attributed"),
            ("Coupon redemptions (CPA)",                                          "0%",          "100%",     "Merchant-side conversion"),
        ])

    # 17 · Station Owner Dashboard
    add_content_slide(prs, 17, N,
        title="Station Owner Dashboard",
        subtitle="Every claimed station gets its own analytics + revenue view.",
        bullets=[
            "Listener count: 24h · 7d · 30d rolling windows.",
            "Top listener geos: country + city rank.",
            "Revenue by product: direct-sold, RJ reads, takeover, programmatic.",
            "Pre-roll fill rate: % of playbacks served with an ad + revenue per playback.",
            "Payouts: Stripe Connect statement + downloadable CSV.",
        ],
        image=s("16_admin_home.png"),
        image_layout="right",
        caption="Admin home dashboard reference (station owner view is a subset scoped to the claimed station).")

    # 18 · What Stations Get For Free
    add_content_slide(prs, 18, N,
        title="What Stations Get For Free",
        subtitle="Five tools included on Day 1, no strings, no upfront cost.",
        bullets=[
            "Auto-import of RSS news feeds — instant news bulletins on your station without editorial staff.",
            "AI RJ persona voice branding — 10 personas, or bring your own voice via ElevenLabs sample.",
            "HTTPS stream proxy — fixes the mixed-content block that silently kills your browser audience.",
            "Pre-roll ad marketplace — you keep 70% direct-sold, 50% programmatic (Q3+).",
            "Geo-flagship routing — first-shelf placement to boost discoverability in your region.",
        ])

    # 19 · Reliability & Ad Ops Rigor (NEW)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide)
    gradient_accent_bar(slide, Inches(0.4), Inches(0.6), Inches(0.6), Pt(3))
    add_text(slide, Inches(0.4), Inches(0.75), Inches(12.5), Inches(0.9),
                        "Reliability & Ad Ops Rigor", size=32, bold=True, color=WHITE)
    add_text(slide, Inches(0.4), Inches(1.5), Inches(12.5), Inches(0.5),
                        "Ad creative rot is auto-remediated — broken creative URLs auto-skip in 2 s + fire analytics events so ops can rotate them.  Your campaign never gets stranded.",
                        size=14, color=SUBTLE)

    # Left — key promise
    left_card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                                                                            Inches(0.5), Inches(2.4),
                                                                                            Inches(6.0), Inches(4.5))
    left_card.fill.solid(); left_card.fill.fore_color.rgb = NAVY2
    left_card.line.color.rgb = GREEN; left_card.line.width = Pt(1.2)
    tf = left_card.text_frame
    tf.margin_left = tf.margin_right = Emu(200000)
    tf.margin_top = tf.margin_bottom = Emu(200000); tf.text = ""
    p = tf.paragraphs[0]
    r = p.add_run(); r.text = "The Advertiser Promise"
    r.font.name = "Calibri"; r.font.size = Pt(14); r.font.bold = True
    r.font.color.rgb = GREEN
    for line in [
        "",
        "▸ Your campaign will never sit stuck on a broken creative.",
        "▸ If our ad-serving layer can't decode the audio, the player auto-skips in 2 seconds — the listener never gets stranded.",
        "▸ Every auto-skip fires a `skip` impression with reason=audio_load_error → ops sees it, rotates the creative, and refunds the wasted impression.",
        "▸ You are not billed for auto-skipped impressions.",
    ]:
        p = tf.add_paragraph(); p.line_spacing = 1.4
        r = p.add_run(); r.text = line
        r.font.name = "Calibri"; r.font.size = Pt(12)
        r.font.color.rgb = WHITE

    # Right — engineering evidence
    right_card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                                                                              Inches(6.8), Inches(2.4),
                                                                                              Inches(6.1), Inches(4.5))
    right_card.fill.solid(); right_card.fill.fore_color.rgb = NAVY2
    right_card.line.color.rgb = PURPLE; right_card.line.width = Pt(1.2)
    tf = right_card.text_frame
    tf.margin_left = tf.margin_right = Emu(200000)
    tf.margin_top = tf.margin_bottom = Emu(200000); tf.text = ""
    p = tf.paragraphs[0]
    r = p.add_run(); r.text = "Case in point · Jul 31 2026"
    r.font.name = "Calibri"; r.font.size = Pt(14); r.font.bold = True
    r.font.color.rgb = PURPLE
    p = tf.add_paragraph(); r = p.add_run()
    r.text = "\nAn upstream demo ad's audio URL rotted (returned HTML instead of MP3).  Detected + fixed in one dev cycle:"
    r.font.name = "Calibri"; r.font.size = Pt(12); r.font.color.rgb = WHITE
    for line in [
        "",
        "• Root cause: 3 seed preroll ads' external audio URLs (kozco.com / pixabay) started returning text/html + 403.",
        "• Fix — code: 1-file, 6-line change to PrerollOverlay.onError → auto-skip after 2 s + fire `skip` impression event with reason=audio_load_error.",
        "• Fix — data: repointed the 3 rows to a backend-hosted asset (`persona_samples/p39_dawn_caller.mp3`).",
        "• Non-regression: AI radio stations kept playing throughout.",
        "• Advertiser billing impact: zero — auto-skips are free.",
    ]:
        p = tf.add_paragraph(); p.line_spacing = 1.3
        r = p.add_run(); r.text = line
        r.font.name = "Calibri"; r.font.size = Pt(10)
        r.font.color.rgb = CREAM

    add_footer_and_number(slide, 19, N)

    # 20 · Next Steps + FAQ
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide)
    gradient_accent_bar(slide, Inches(0.4), Inches(0.6), Inches(0.6), Pt(3))
    add_text(slide, Inches(0.4), Inches(0.75), Inches(12.5), Inches(0.9),
                        "Next Steps + FAQ", size=32, bold=True, color=WHITE)
    add_text(slide, Inches(0.4), Inches(1.5), Inches(12.5), Inches(0.5),
                        "How to close · what a first-month customer actually gets.",
                        size=14, color=SUBTLE)
    # Left — How to close
    add_text(slide, Inches(0.5), Inches(2.3), Inches(6), Inches(0.4),
                        "How to Close", size=16, bold=True, color=PURPLE)
    add_bullet_list(slide, Inches(0.5), Inches(2.85), Inches(6), Inches(4.5),
                                      ["Schedule a 30-min demo · in-person if possible.",
                                        "Offer $100 credit for the first-month campaigns (any product).",
                                        "Set up a joint QBR calendar (monthly for the first quarter).",
                                        "Send a follow-up email with the advertiser onboarding link + Stripe test-mode key note.",
                                        "Track them in Salesforce under the 'BigFM · first campaign' pipeline stage."],
                                      size=13, line_spacing=1.4)

    # Right — Mini-FAQ
    add_text(slide, Inches(7.0), Inches(2.3), Inches(6), Inches(0.4),
                        "Mini-FAQ", size=16, bold=True, color=PINK)
    add_bullet_list(slide, Inches(7.0), Inches(2.85), Inches(6), Inches(4.5),
                                      ["Payment terms: prepaid budget (Stripe Connect wallet).  Net-15 for approved chains > $2 k / mo.",
                                        "Minimum spend: none for coupon CPA.  $50 minimum wallet top-up.",
                                        "Cancellation: pause anytime; unused budget refundable within 30 days.",
                                        "Refunds: full refund on fraud-flagged redemptions + auto-skipped impressions (Reliability slide).",
                                        "Support: dedicated Slack channel for spend > $500/mo, email support otherwise (< 24 h SLA)."],
                                      size=12, line_spacing=1.35)
    add_footer_and_number(slide, 20, N)

    out = OUT_DIR / "BigFM_Sales_Deck.pptx"
    prs.save(str(out))
    return out, N


def main():
    inv_path, inv_n = build_investor_deck()
    print(f"Investor deck: {inv_path}  slides=18  {inv_path.stat().st_size // 1024} kB")
    sales_path, sales_n = build_sales_deck()
    print(f"Sales    deck: {sales_path}  slides={sales_n}  {sales_path.stat().st_size // 1024} kB")


if __name__ == "__main__":
    main()
