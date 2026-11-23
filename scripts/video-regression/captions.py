"""Compare glyphs from decoded video frames with independently typeset caption text."""

from pathlib import Path

from PIL import Image, ImageChops


def glyphs(image):
    mask = image.convert("L").point(lambda pixel: 255 if pixel > 145 else 0)
    bounds = mask.getbbox()
    if bounds is None:
        raise AssertionError("Caption contains no visible glyphs")
    return mask.crop(bounds)


def similarity(actual, expected):
    # Cropping to the ink removes baseline differences. Permit a pixel of rasterization drift.
    if abs(actual.width - expected.width) > 2 or abs(actual.height - expected.height) > 2:
        return 0.0
    size = (max(actual.width, expected.width) + 4, max(actual.height, expected.height) + 4)
    reference = Image.new("L", size)
    reference.paste(expected, (2, 2))
    best = 0.0
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            shifted = Image.new("L", size)
            shifted.paste(actual, (2 + dx, 2 + dy))
            overlap = ImageChops.darker(shifted, reference).histogram()[255]
            union = ImageChops.lighter(shifted, reference).histogram()[255]
            best = max(best, overlap / union)
    return best


def verify(output: Path):
    for name in ("original", "edited"):
        with Image.open(output / f"{name}.png") as frame:
            # At 1280x720 the dark caption box starts at x=56. Read its top padding
            # to locate the right edge independently of the expected caption length.
            gray = frame.convert("L")
            edge = next((x for x in range(80, 950) if gray.getpixel((x, 627)) > 110), None)
            if edge is None or edge <= 80:
                raise AssertionError(f"{name}: caption box missing")
            crop = frame.crop((72, 630, edge - 8, 675))
            crop.save(output / f"{name}-caption.png")
            actual = glyphs(crop)
        with Image.open(output / f"{name}-expected.png") as reference:
            score = similarity(actual, glyphs(reference))
        print(f"{name} caption glyph similarity: {score:.3f}", flush=True)
        if score < 0.75:
            raise AssertionError(f"{name}: downloaded MP4 does not show the expected caption")
