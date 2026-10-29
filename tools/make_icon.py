"""The add-on's icon: "incipIt" over an 8x8 grid of tiles made from album covers in Kodi's library. Of each cover
only its coarse light and shade is kept (ABSTRACT), so no artwork is copied. Writes icon_<size>.png next to this
script. Usage: python make_icon.py [seed] [--size 1024]
The add-on's icon.png (2026-10-29) is seed 7, drawn at 1024 and reduced to 512."""
import glob
import os
import random
import sqlite3
import sys

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
DATABASE = sorted(glob.glob(os.path.join(os.environ["APPDATA"], "Kodi", "userdata", "Database", "MyMusic*.db")))[-1]
SIZE = int(sys.argv[sys.argv.index("--size") + 1]) if "--size" in sys.argv else 512
GRID = 8
SCALE = SIZE / 512
CELL = SIZE // GRID
FONT = r"C:\Windows\Fonts\bahnschrift.ttf"
SEED = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 7


def covers(count):
    """count album covers that exist on disk, from different genre folders as far as possible."""
    db = sqlite3.connect(f"file:{DATABASE}?mode=ro", uri=True)
    urls = sorted({url for (url,) in db.execute("SELECT url FROM art WHERE media_type = 'album' AND type = 'thumb'")
                   if url and not url.startswith("image://") and url.lower().endswith((".jpg", ".jpeg", ".png"))})
    by_folder = {}
    for url in urls:
        parts = url.replace("\\", "/").split("/")
        by_folder.setdefault(parts[2] if len(parts) > 3 else "?", []).append(url)
    rng = random.Random(SEED)
    for group in by_folder.values():
        rng.shuffle(group)
    chosen, folders = [], list(by_folder)
    rng.shuffle(folders)
    while len(chosen) < count and any(by_folder.values()):
        for folder in folders:
            if by_folder[folder] and len(chosen) < count:
                url = by_folder[folder].pop()
                if os.path.isfile(url):
                    chosen.append(url)
    return chosen


def square(path):
    image = Image.open(path).convert("RGB")
    return ImageOps.fit(image, (CELL, CELL), Image.LANCZOS)


def grid(images, treat):
    canvas = Image.new("RGB", (SIZE, SIZE))
    for index, image in enumerate(images):
        canvas.paste(treat(image), ((index % GRID) * CELL, (index // GRID) * CELL))
    return canvas


def font(size, weight):
    face = ImageFont.truetype(FONT, size)
    try:
        face.set_variation_by_name(weight)
    except Exception:
        pass
    return face


def name(canvas, light, accent, size=128, shadow=True, weight_rest="Light", weight_i="Bold", y=None):
    """ "incip" + "I" + "t", the capital I in its own weight and colour, centred."""
    size = round(size * SCALE)
    draw = ImageDraw.Draw(canvas)
    parts = [("incip", font(size, weight_rest), light), ("I", font(size, weight_i), accent),
             ("t", font(size, weight_rest), light)]
    widths = [draw.textlength(text, font=face) for text, face, _ in parts]
    x = (SIZE - sum(widths)) / 2
    y = (SIZE - size) / 2 - size * 0.12 if y is None else y
    if shadow:
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        shade = ImageDraw.Draw(layer)
        sx = x
        for (text, face, _), width in zip(parts, widths):
            shade.text((sx + 3 * SCALE, y + 4 * SCALE), text, font=face, fill=(0, 0, 0, 200))
            sx += width
        canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), layer.filter(ImageFilter.GaussianBlur(6 * SCALE))))
        draw = ImageDraw.Draw(canvas)
    for (text, face, colour), width in zip(parts, widths):
        draw.text((x, y), text, font=face, fill=colour)
        x += width
    return canvas


def duotone(image, dark, bright):
    grey = ImageOps.autocontrast(ImageOps.grayscale(image), cutoff=2)
    return ImageOps.colorize(grey, dark, bright)


# No artwork is copied (copyright): a cover is reduced to the brightness of ABSTRACT x ABSTRACT patches, nothing of
# its picture, lettering or design is left, and that coarse light-and-shade becomes a soft gradient tile.
ABSTRACT = 3


def abstract(image):
    patches = ImageOps.grayscale(image).resize((ABSTRACT, ABSTRACT), Image.BOX)
    return patches.resize(image.size, Image.BICUBIC).convert("RGB")


def bevel(image):
    """A thin dark edge, so the tiles still read as a wall of record sleeves."""
    image = image.copy()
    ImageDraw.Draw(image).rectangle((0, 0, image.width - 1, image.height - 1), outline=(8, 10, 18),
                                    width=max(1, round(2 * SCALE)))
    return image


def vignette(canvas, strength=170):
    mask = Image.radial_gradient("L").resize(canvas.size)
    dark = Image.new("RGB", canvas.size, (8, 9, 14))
    return Image.composite(dark, canvas, ImageEnhance.Brightness(mask).enhance(strength / 255))


def distinct(paths, count):
    """The first count covers that don't look alike (the same artwork on two albums)."""
    kept, prints = [], []
    for path in paths:
        try:
            image = square(path)
        except Exception:
            continue
        small = list(ImageOps.grayscale(image).resize((8, 8)).getdata())
        if any(sum(abs(a - b) for a, b in zip(small, other)) < 300 for other in prints):
            continue
        prints.append(small)
        kept.append((path, image))
        if len(kept) >= count:
            break
    return kept


def main():
    candidates = distinct(covers(GRID * GRID * 2), GRID * GRID * 2)
    chosen, spare = candidates[:GRID * GRID], candidates[GRID * GRID:]

    def artist(path):  # D:/music/#genre/Artist/...: an artist's own picture is often its album's cover too
        parts = path.replace("\\", "/").split("/")
        name = parts[3].lower() if len(parts) > 4 else path.lower()
        return "".join(ch for ch in name.removeprefix("the ") if ch.isalnum())

    seen = set()
    for index, (path, image) in enumerate(chosen):
        while artist(path) in seen and spare:
            print(f"cover {index} ({path}): the artist is in the grid already; replaced")
            path, image = spare.pop(0)
            chosen[index] = (path, image)
        seen.add(artist(path))
    images = [image for _path, image in chosen]
    print(f"{len(images)} covers")
    # the covers only as abstract light and shade (see ABSTRACT), in an ink-to-teal duotone, the capital I in orange
    tiles = grid(images, lambda image: bevel(duotone(abstract(image), (12, 16, 30), (70, 170, 180))))
    icon = name(vignette(tiles, 190), (245, 245, 240), (255, 138, 61), size=132, weight_rest="SemiLight")
    icon.save(os.path.join(HERE, f"icon_{SIZE}.png"))

main()
