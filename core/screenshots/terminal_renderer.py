"""Render captured console output as a terminal-style PNG for the report."""
from __future__ import annotations

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BG = (24, 26, 30)
FG = (222, 225, 230)
DIM = (128, 134, 145)
BAR = (44, 47, 54)
FONT_PT = 14
LINE = 21
PAD = 18
BAR_H = 30
WRAP = 104
MAX_LINES = 140

_FONTS = ("consola.ttf", "CascadiaMono.ttf", "cour.ttf", "DejaVuSansMono.ttf",
          "LiberationMono-Regular.ttf", "Menlo.ttc")


def _font(size: int):
    for name in _FONTS:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_console(text: str, path: str | Path, command: str = "", scale: int = 2) -> tuple[int, int]:
    """Draw `text` in a terminal window and save it to `path`. Returns pixel size."""
    lines: list[str] = []
    for raw in (text or "").expandtabs(4).split("\n"):
        lines.extend(textwrap.wrap(raw, WRAP, replace_whitespace=False, drop_whitespace=False) or [""])
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        lines = ["(the program printed nothing)"]
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES] + ["… output continues"]

    font = _font(FONT_PT * scale)
    rows = ([f"> {command}"] if command else []) + lines
    width_px = max(int(font.getlength(r)) for r in rows) + 2 * PAD * scale
    width = max(width_px, 520 * scale)
    height = (BAR_H + PAD * 2 + LINE * len(rows)) * scale

    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (width, BAR_H * scale)], fill=BAR)
    for i, colour in enumerate(((237, 106, 94), (245, 191, 79), (98, 197, 84))):
        x = (14 + i * 20) * scale
        draw.ellipse([(x, 10 * scale), (x + 11 * scale, 21 * scale)], fill=colour)
    title_font = _font(12 * scale)
    draw.text((width // 2, 15 * scale), "Output", fill=DIM, font=title_font, anchor="mm")

    y = (BAR_H + PAD) * scale
    for i, row in enumerate(rows):
        draw.text((PAD * scale, y), row, fill=DIM if (command and i == 0) else FG, font=font)
        y += LINE * scale

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, optimize=True)
    return img.size
