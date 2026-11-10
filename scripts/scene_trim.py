"""Trim plain photo background / empty paper around photographed artwork.

Finds the border colour (median of the outer 2% frame), keeps the bounding
box of pixels that clearly differ from it (blurred, so paper grain is
ignored), then adds a safety margin. It only removes plain border area, but
faint pencil can fall under the threshold: ALWAYS look at every result and
keep a picture untrimmed when its drawing reaches the edge.

  python scene_trim.py SRC_DIR DST_DIR            # every *-000.jpg in SRC_DIR
  python scene_trim.py SRC.jpg DST.jpg --margin 0.045 --thresh 38
Defaults: --thresh 38 (0-255 difference), --margin 0.015 (share of the long side).
Raise --margin when thin strokes (whiskers) sit near the edge; use
--margin 0 --thresh 60 to cut exactly to a sheet of paper on a gray backdrop.
"""
import argparse, os
from PIL import Image, ImageChops, ImageFilter


def trim(src, dst, thresh=38, margin=0.015):
    im = Image.open(src).convert("RGB")
    w, h = im.size
    b = max(4, int(min(w, h) * 0.02))
    px = []
    for box in [(0, 0, w, b), (0, h - b, w, h), (0, 0, b, h), (w - b, 0, w, h)]:
        px += list(im.crop(box).getdata())
    med = tuple(sorted(p[c] for p in px)[len(px) // 2] for c in range(3))
    diff = ImageChops.difference(im.filter(ImageFilter.GaussianBlur(3)),
                                 Image.new("RGB", im.size, med)).convert("L")
    mask = diff.point(lambda v: 255 if v > thresh else 0).filter(ImageFilter.MedianFilter(9))
    box = mask.getbbox()
    if box:
        m = int(max(w, h) * margin)
        box = (max(0, box[0] - m), max(0, box[1] - m), min(w, box[2] + m), min(h, box[3] + m))
        im = im.crop(box)
    im.save(dst, quality=95, subsampling=0)
    return (w, h), im.size


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--thresh", type=int, default=38)
    ap.add_argument("--margin", type=float, default=0.015)
    a = ap.parse_args()
    if os.path.isdir(a.src):
        os.makedirs(a.dst, exist_ok=True)
        for f in sorted(os.listdir(a.src)):
            if f.endswith("-000.jpg"):
                print(f, *trim(os.path.join(a.src, f), os.path.join(a.dst, f), a.thresh, a.margin))
    else:
        print(*trim(a.src, a.dst, a.thresh, a.margin))
