
# SPDX-License-Identifier: AGPL-3.0-only
# TG Deleter - Desktop utility for managing Telegram messages
# Copyright (C) 2024-2026 TG Deleter Contributors

"""
Generate the TG Deleter app icon (assets/icon.png + assets/icon.ico).

Run: python assets/make_icon.py

A geometric wolf head (brand mark) in white on a Telegram-blue rounded tile.
Rendered at 4x supersampling and downscaled for smooth edges.
"""
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
SIZE = 256
SS = 4  # supersample factor
S = SIZE * SS

BLUE_TOP = (42, 171, 238)    # #2AABEE
BLUE_BOTTOM = (28, 130, 190)  # darker telegram blue
WHITE = (255, 255, 255)


def _gradient_tile() -> Image.Image:
    """Rounded square with a vertical blue gradient."""
    grad = Image.new("RGB", (S, S))
    px = grad.load()
    for y in range(S):
        t = y / (S - 1)
        r = round(BLUE_TOP[0] + (BLUE_BOTTOM[0] - BLUE_TOP[0]) * t)
        g = round(BLUE_TOP[1] + (BLUE_BOTTOM[1] - BLUE_TOP[1]) * t)
        b = round(BLUE_TOP[2] + (BLUE_BOTTOM[2] - BLUE_TOP[2]) * t)
        for x in range(S):
            px[x, y] = (r, g, b)

    mask = Image.new("L", (S, S), 0)
    md = ImageDraw.Draw(mask)
    radius = int(S * 0.235)
    md.rounded_rectangle([0, 0, S - 1, S - 1], radius=radius, fill=255)

    tile = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    tile.paste(grad, (0, 0), mask)
    return tile


def _wolf(draw: ImageDraw.ImageDraw):
    """White geometric wolf head, centered on the tile."""
    def p(x, y):
        return (int(x * S), int(y * S))

    # Ears (two sharp triangles)
    draw.polygon([p(0.27, 0.40), p(0.34, 0.14), p(0.50, 0.34)], fill=WHITE)
    draw.polygon([p(0.73, 0.40), p(0.66, 0.14), p(0.50, 0.34)], fill=WHITE)

    # Head / muzzle (shield pointing down to the chin)
    draw.polygon(
        [
            p(0.28, 0.37),
            p(0.72, 0.37),
            p(0.66, 0.62),
            p(0.50, 0.84),
            p(0.34, 0.62),
        ],
        fill=WHITE,
    )

    # Eyes (cut back to blue for contrast)
    draw.polygon([p(0.40, 0.50), p(0.47, 0.50), p(0.435, 0.585)], fill=BLUE_TOP)
    draw.polygon([p(0.60, 0.50), p(0.53, 0.50), p(0.565, 0.585)], fill=BLUE_TOP)

    # Snout notch
    draw.polygon([p(0.47, 0.70), p(0.53, 0.70), p(0.50, 0.80)], fill=BLUE_BOTTOM)


def build():
    tile = _gradient_tile()
    draw = ImageDraw.Draw(tile)
    _wolf(draw)
    icon = tile.resize((SIZE, SIZE), Image.LANCZOS)

    png_path = os.path.join(HERE, "icon.png")
    ico_path = os.path.join(HERE, "icon.ico")
    icon.save(png_path)
    icon.save(
        ico_path,
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print("wrote", png_path)
    print("wrote", ico_path)


if __name__ == "__main__":
    build()
