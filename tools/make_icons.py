"""Draws the add-on's menu icons (resources/media/icon-*.png) from Font Awesome Free glyphs.

The icons are white glyphs on a transparent 320 x 320 square, the glyph about 135 px across, like the default icons
of Arctic Fuse (which are Font Awesome too), so they sit well next to the skin's own.

    python tools/make_icons.py <path to fa-solid-900.ttf> [icon-name ...]

Font Awesome Free 6 (for example the copy in skin.arctic.fuse.3.cine/fonts). Icons: CC BY 4.0, see
resources/media/LICENSE.txt.
"""

import os
import sys

from PIL import Image, ImageDraw, ImageFont

SIZE = 320
GLYPH = 135  # the larger side of the glyph, in pixels
WHITE = (255, 255, 255)
PLAYING_RED = (229, 57, 53)  # the first screen's entry for what plays
ICONS = {  # file name -> Font Awesome glyph, or (glyph, colour); white unless given
    "icon-generate": 0xE2CA,   # wand-magic-sparkles: a mix made from what plays
    "icon-discovery": 0xF14E,  # compass: Discovery mode, off
    "icon-searching": 0xF002,  # magnifying-glass: Discovery mode on, or the radio scanning
    "icon-radio": 0xF8D7,      # radio: Radio mode, off
    "icon-playing": 0xF144,    # circle-play: a radio station playing
    "icon-skip": 0xF051,       # forward-step: on to the next snippet
    "icon-stop": 0xF28D,       # circle-stop: the partner of circle-play
    "icon-settings": 0xF013,   # gear
    "icon-info": 0xF05A,       # circle-info: Station information
    "icon-favourite": 0xF005,  # star (Kodi's favourites are stars): save a station as a favourite
    "icon-playing-red": (0xF144, PLAYING_RED),  # circle-play: the first screen's Current mix / Current station
}


def draw(font_path: str, codepoint: int, path: str, colour: tuple = WHITE) -> None:
    probe = ImageFont.truetype(font_path, 400)
    left, top, right, bottom = probe.getbbox(chr(codepoint))
    font = ImageFont.truetype(font_path, int(400 * GLYPH / max(right - left, bottom - top)))
    left, top, right, bottom = font.getbbox(chr(codepoint))
    image = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 0))
    ImageDraw.Draw(image).text(((SIZE - (right - left)) / 2 - left, (SIZE - (bottom - top)) / 2 - top), chr(codepoint),
                               font=font, fill=(*colour, 255))
    image.save(path, "PNG", optimize=True)


def main() -> None:
    folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources", "media")
    os.makedirs(folder, exist_ok=True)
    only = sys.argv[2:]  # names to draw (all without)
    for name, glyph in ICONS.items():
        if only and name not in only:
            continue
        codepoint, colour = glyph if isinstance(glyph, tuple) else (glyph, WHITE)
        draw(sys.argv[1], codepoint, os.path.join(folder, f"{name}.png"), colour)
        print(f"{name}.png")


if __name__ == "__main__":
    main()
