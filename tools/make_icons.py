"""Draws the add-on's menu icons (resources/media/icon-*.png) from Font Awesome Free glyphs.

The icons are white glyphs on a transparent 320 x 320 square, the glyph about 135 px across, like the default icons
of Arctic Fuse (which are Font Awesome too), so they sit well next to the skin's own.

    python tools/make_icons.py <path to fa-solid-900.ttf>

Font Awesome Free 6 (for example the copy in skin.arctic.fuse.3.cine/fonts). Icons: CC BY 4.0, see
resources/media/LICENSE.txt.
"""

import os
import sys

from PIL import Image, ImageDraw, ImageFont

SIZE = 320
GLYPH = 135  # the larger side of the glyph, in pixels
ICONS = {  # file name -> Font Awesome glyph
    "icon-generate": 0xE2CA,   # wand-magic-sparkles: a mix made from what plays
    "icon-discovery": 0xF14E,  # compass: Discovery mode, off
    "icon-searching": 0xF002,  # magnifying-glass: Discovery mode on, or the radio scanning
    "icon-radio": 0xF8D7,      # radio: Radio mode, off
    "icon-playing": 0xF144,    # circle-play: a radio station playing
    "icon-settings": 0xF013,   # gear
}


def draw(font_path: str, codepoint: int, path: str) -> None:
    probe = ImageFont.truetype(font_path, 400)
    left, top, right, bottom = probe.getbbox(chr(codepoint))
    font = ImageFont.truetype(font_path, int(400 * GLYPH / max(right - left, bottom - top)))
    left, top, right, bottom = font.getbbox(chr(codepoint))
    image = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 0))
    ImageDraw.Draw(image).text(((SIZE - (right - left)) / 2 - left, (SIZE - (bottom - top)) / 2 - top), chr(codepoint),
                               font=font, fill=(255, 255, 255, 255))
    image.save(path, "PNG", optimize=True)


def main() -> None:
    folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources", "media")
    os.makedirs(folder, exist_ok=True)
    for name, codepoint in ICONS.items():
        draw(sys.argv[1], codepoint, os.path.join(folder, f"{name}.png"))
        print(f"{name}.png")


if __name__ == "__main__":
    main()
