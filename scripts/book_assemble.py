#!/usr/bin/env python3
"""Assemble a KindleWood story-collection book (interior + cover spread)
from a book folder of KindleWood story PDF exports and teacher assets.

Subcommands:
  init      BOOK_DIR             -- scaffold folders + book.yaml template
  scan      BOOK_DIR             -- classify every story PDF's pages (dry run)
  extract   BOOK_DIR             -- pull characters / kids' drawings / scenes
                                    into candidates/ (+ contact sheets)
  assemble  BOOK_DIR [--size letter|digest ...] [--spine IN]
                                 -- write out/<slug>-<size>-interior.pdf and
                                    out/<slug>-<size>-cover.pdf (Mixam-ready:
                                    0.125in bleed + TrimBox on every page)

Layout is HTML/CSS printed to PDF by headless Chrome (proper EN + 中文
typesetting), then TrimBox/BleedBox are stamped with pypdf.
Requires poppler (pdfimages/pdftotext/pdftoppm), Google Chrome, and the
skill venv (pypdf, pillow, pyyaml).
"""
import argparse
import base64
import glob
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BLEED = 0.125

# Trim sizes verified on mixam.com/paperbackbooks (2026-11).
# Margins in inches inside trim; gutter = binding side (perfect-bound glue
# eats ~0.25-0.375in, Mixam asks 0.5in quiet area at the spine).
SIZES = {
    "letter": dict(w=8.5, h=11.0, top=0.35, bottom=0.45, outer=0.3,
                   gutter=0.55, per_page=4, base_pt=15, opener_art=5.5,
                   solo_art=5.5, authors_cols=2, photo=1.15, note_em=0.92),
    "a5": dict(w=5.827, h=8.268, top=0.3, bottom=0.42, outer=0.28,
               gutter=0.5, per_page=1, base_pt=14, opener_art=4.5,
               solo_art=5.0, authors_cols=2, photo=0.7, note_em=0.74),
    "digest": dict(w=5.5, h=8.5, top=0.3, bottom=0.42, outer=0.28,
                   gutter=0.5, per_page=1, base_pt=14, opener_art=4.5,
                   solo_art=4.72, authors_cols=2, photo=0.68, note_em=0.72),
}
AUTHORS_PER_PAGE = 10
DESIGNER_MIN_SCALE = 0.62   # combine designer pages only if text stays legible
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fonts")
DEFAULT_FONTS = dict(en="Chalkboard SE", zh_heading="ZCOOL KuaiLe",
                     zh_body="ZCOOL KuaiLe")
SPARK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets",
                     "spark-writing.png")
SPARK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "spark")
# The standard KindleWood Families back cover (user rule: always use this one).
# Letter back panel incl. outer bleed, spine-side bleed trimmed off.
BACK_COVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets",
                          "back-cover", "kindlewood-families-back.png")
# (pose, message) for empty grid cells -- rotated so they don't repeat
FILLERS = [("reading", "Keep reading — more adventures ahead!"),
           ("cheering", "You are a storyteller! Keep imagining!"),
           ("waving", "What would YOU draw next?"),
           ("thinking", "What do you think happens next?"),
           ("laughing", "Every big story starts with a little idea!")]
IMAGINE_MSG = ("Congratulations on your writing journey \u2014 we are so proud of you! "
               "Keep imagining, keep drawing, keep writing \u2014 your stories and "
               "your voice matter.")
IMAGINE_ASK = "What are you going to draw and write next?"
# Used to fill the last page when the count is odd (instead of a blank page).
EXTRA_PROMPTS = [
    "If you could have any magical pet, what would it be? What adventures would you go on together?",
    "Imagine you woke up as a superhero. What is your superpower, and who will you help?",
    "What would happen if your toys came to life at night?",
    "Draw your dream adventure. Where would you go, and who would come with you?",
]
# Fonts shipped in fonts/ (OFL). Embedded as data URIs with a format hint --
# file:// @font-face loads proved unreliable in headless Chrome.
BUNDLED_FONTS = {"ZCOOL KuaiLe": "ZCOOLKuaiLe-Regular.ttf"}

CJK = re.compile(r"[　-〿㐀-鿿＀-￯]")


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def esc(s):
    return html.escape(str(s or ""))


def url(path):
    return "file://" + os.path.abspath(path).replace(" ", "%20")


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "book"


# ---------------------------------------------------------------- stories

def _page_images(src):
    """{page: [(w, h), ...]} of real images (smasks excluded)."""
    out = {}
    for line in sh(["pdfimages", "-list", src]).stdout.splitlines()[2:]:
        p = line.split()
        if len(p) > 4 and p[2] == "image":
            out.setdefault(int(p[0]), []).append((int(p[3]), int(p[4])))
    return out


def _image_boxes(src, n):
    """[(w, h, top, bottom)] for each image drawn on page n; w/h are pixel
    sizes, top/bottom are fractions of page height measured from the top."""
    return [(b["w"], b["h"], b["top"], b["bottom"]) for b in _draw_boxes(src, n)]


def _draw_boxes(src, n):
    """Every image drawn on page n (also inside form XObjects), as dicts
    with pixel w/h and left/right/top/bottom as fractions of the page."""
    from pypdf import PdfReader
    from pypdf.generic import ContentStream
    reader = PdfReader(src)
    page = reader.pages[n - 1]
    W, H = float(page.mediabox.width), float(page.mediabox.height)
    out = []

    def mul(m, c):
        a, b, cc, d, e, f = m
        A, B, C, D, E, F = c
        return [a*A + b*C, a*B + b*D, cc*A + d*C, cc*B + d*D,
                e*A + f*C + E, e*B + f*D + F]

    def walk(ops, res, ctm, depth=0):
        xobj = (res or {}).get("/XObject") or {}
        stack = []
        for args, op in ops:
            if op == b"q":
                stack.append(ctm)
            elif op == b"Q" and stack:
                ctm = stack.pop()
            elif op == b"cm":
                ctm = mul([float(v) for v in args], ctm)
            elif op == b"Do" and args[0] in xobj:
                x = xobj[args[0]].get_object()
                if x.get("/Subtype") == "/Image":
                    pts = [(e * ctm[0] + f * ctm[2] + ctm[4], e * ctm[1] + f * ctm[3] + ctm[5])
                           for e in (0, 1) for f in (0, 1)]
                    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
                    out.append(dict(w=int(x["/Width"]), h=int(x["/Height"]),
                                    left=min(xs) / W, right=max(xs) / W,
                                    top=1 - max(ys) / H, bottom=1 - min(ys) / H))
                elif x.get("/Subtype") == "/Form" and depth < 4:
                    m = [float(v) for v in x.get("/Matrix", [1, 0, 0, 1, 0, 0])]
                    walk(ContentStream(x, reader).operations, x.get("/Resources"),
                         mul(m, ctm), depth + 1)
    walk(page.get_contents().operations, page.get("/Resources"), [1, 0, 0, 1, 0, 0])
    return out


def _text_blocks(src, n):
    """pdftotext blocks on page n: dicts with left/right/top/bottom
    fractions and the block's lines."""
    import html as _h
    x = sh(["pdftotext", "-bbox-layout", "-f", str(n), "-l", str(n), src, "-"]).stdout
    m = re.search(r'<page width="([\d.]+)" height="([\d.]+)"', x)
    if not m:
        return []
    W, H = float(m[1]), float(m[2])
    out = []
    for b in re.finditer(r'<block xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" '
                         r'yMax="([\d.]+)">(.*?)</block>', x, re.S):
        lines = [" ".join(_h.unescape(w) for w in re.findall(r"<word[^>]*>(.*?)</word>", l))
                 for l in re.findall(r"<line.*?</line>", b[5], re.S)]
        lines = [l.strip() for l in lines if l.strip()]
        if lines:
            out.append(dict(left=float(b[1]) / W, right=float(b[3]) / W,
                            top=float(b[2]) / H, bottom=float(b[4]) / H, lines=lines))
    return sorted(out, key=lambda d: (round(d["top"], 2), d["left"]))


SKIP_TEXT = re.compile(r"^(Meet the Character|Original Creation|In the Story|Scan |"
                       r"Download Mobile App|listen and read|iOS$|Android$|\d+$)", re.I)
WORDS_TITLE = re.compile(r"^In (.+?)[\'’]s\s*Own Words", re.I)


def designer_units(src, pages, render):
    """Re-structure a story's "Meet the Character Designers" pages into
    units {name, caption, imgs, words} so they can be re-typeset in the
    book fonts instead of printed as flat page images."""
    units = []
    for p in pages:
        qr = _qr_top(src, p) or 2
        full = render(p, f"p{p:03d}")
        from PIL import Image
        page_im = Image.open(full).convert("RGB")
        PW, PH = page_im.size
        from PIL import ImageDraw
        dr = ImageDraw.Draw(page_im)  # stray words overlapping a picture's box
        for t in _text_blocks(src, p):
            dr.rectangle((int(t["left"] * PW) - 4, int(t["top"] * PH) - 4,
                          int(t["right"] * PW) + 4, int(t["bottom"] * PH) + 4), fill="white")
        boxes = [b for b in _draw_boxes(src, p)
                 if b["top"] < qr - 0.01 and (b["right"] - b["left"]) < 0.95
                 and (b["bottom"] - b["top"]) > 0.08]
        # drop boxes fully inside another (stacked layers of one picture)
        boxes = [b for b in boxes if not any(
            o is not b and o["left"] <= b["left"] + .005 and o["right"] >= b["right"] - .005
            and o["top"] <= b["top"] + .005 and o["bottom"] >= b["bottom"] - .005
            and (o["right"] - o["left"]) * (o["bottom"] - o["top"]) >
                (b["right"] - b["left"]) * (b["bottom"] - b["top"]) for o in boxes)]
        blocks = [t for t in _text_blocks(src, p)
                  if t["top"] < qr and not SKIP_TEXT.match(t["lines"][0])]
        # image rows
        rows = []
        for b in sorted(boxes, key=lambda b: b["top"]):
            for r in rows:
                ov = min(r["bottom"], b["bottom"]) - max(r["top"], b["top"])
                if ov > 0.4 * min(r["bottom"] - r["top"], b["bottom"] - b["top"]):
                    r["boxes"].append(b)
                    r["top"], r["bottom"] = min(r["top"], b["top"]), max(r["bottom"], b["bottom"])
                    r["left"], r["right"] = min(r["left"], b["left"]), max(r["right"], b["right"])
                    break
            else:
                rows.append(dict(boxes=[b], **{k: b[k] for k in ("top", "bottom", "left", "right")}))
        used = set()
        page_units = []
        for ri, r in enumerate(rows):
            imgs = []
            for bi_, b in enumerate(sorted(r["boxes"], key=lambda b: b["left"])):
                out = os.path.join(os.path.dirname(full), f"d{p:03d}-{ri}-{bi_}.jpg")
                if not os.path.exists(out):
                    crop = page_im.crop((max(0, int(b["left"] * PW)), max(0, int(b["top"] * PH)),
                                         min(PW, int(b["right"] * PW)), min(PH, int(b["bottom"] * PH))))
                    crop.convert("RGB").save(out, quality=92)
                imgs.append(out)
            cap = None
            for i, t in enumerate(blocks):
                if i in used or WORDS_TITLE.match(t["lines"][0]) or len(t["lines"]) > 2:
                    continue
                low = min(b["bottom"] for b in r["boxes"]) - 0.03
                if (low <= t["top"] <= r["bottom"] + 0.07 and
                        t["right"] > r["left"] and t["left"] < r["right"]):
                    cap = t
                    used.add(i)
                    break
            text = " ".join(cap["lines"]) if cap else ""
            q = re.search(r"[“\"]([^”\"]+)[”\"]", text)
            name = (q[1] if q else text.split("—")[0]).strip()
            page_units.append(dict(name=name, caption=text, imgs=imgs, words=[], title=""))
        # own words: a title block, then the body blocks right under it
        for i, t in enumerate(blocks):
            m = WORDS_TITLE.match(t["lines"][0])
            if not m or i in used:
                continue
            used.add(i)
            body, last = list(t["lines"][1:]), t["bottom"]
            for j, u in enumerate(blocks):
                if (j not in used and not WORDS_TITLE.match(u["lines"][0]) and
                        -0.02 <= u["top"] - last < 0.05 and
                        u["right"] > t["left"] - 0.1 and u["left"] < t["right"] + 0.1):
                    body += u["lines"]
                    used.add(j)
                    last = u["bottom"]
            who = m[1].strip()
            unit = next((x for x in page_units + units if x["name"] and
                         x["name"].lower().startswith(who.lower()[:4]) and not x["words"]), None)
            nameless = [x for x in page_units if not x["name"] and x["imgs"]]
            if unit is None and nameless:  # no caption found: the page's pictures are theirs
                unit = nameless[0]
                unit["name"] = who
                for x in nameless[1:]:
                    unit["imgs"] += x["imgs"]
                    page_units.remove(x)
            if unit is None:
                unit = dict(name=who, caption="", imgs=[], words=[], title="")
                page_units.append(unit)
            unit["title"], unit["words"] = f"In {who}'s Own Words", body
        units += page_units
    return units



QR_TEXT = re.compile(r"Scan |Scan the QR|Download Mobile App|listen and read|"
                     r"read along|^(iOS|Android)$", re.I)


def _qr_top(src, n):
    """Top (fraction from page top) of the QR block some exports put at the
    bottom of a designer page, else None. It is anchored on what only a QR
    block has -- a wide "Scan the QR code" banner image or "Scan..." /
    "Download Mobile App" text -- and then widened to the square QR / dragon
    images next to it (kids' art can be any size, so size alone is no proof)."""
    boxes = _draw_boxes(src, n)
    anchors = [b["top"] for b in boxes if b["top"] > 0.4 and b["w"] >= 2.5 * b["h"]]
    anchors += [t["top"] for t in _text_blocks(src, n)
                if t["top"] > 0.4 and QR_TEXT.search(" ".join(t["lines"]))]
    if not anchors:
        return None
    a = min(anchors)
    near = [b["top"] for b in boxes if b["w"] == b["h"] and b["w"] != 1024
            and b["top"] > 0.4 and b["top"] >= a - 0.2]
    return min([a] + near)


def _page_text(src, n):
    return sh(["pdftotext", "-f", str(n), "-l", str(n), src, "-"]).stdout


def _split_caption(text):
    en, zh = [], []
    for line in (l.strip() for l in text.splitlines()):
        if not line or line.isdigit():
            continue
        (zh if CJK.search(line) else en).append(line)
    return " ".join(en), "".join(zh)


def _is_scene(imgs, text):
    # Story pages = one square illustration + a caption.
    return (len(imgs) == 1 and imgs[0][0] == imgs[0][1] >= 512
            and text.strip() != "")


DESIGNER_TEXT = re.compile(r"Meet the Character|Own Words", re.I)


def classify(src, overrides=None):
    """Return a list of (page_no, kind) with kind in cover / designer /
    scene / drop:<reason> / ad."""
    overrides = overrides or {}
    n = int(re.search(r"Pages:\s+(\d+)", sh(["pdfinfo", src]).stdout)[1])
    imgs = _page_images(src)
    texts = {p: _page_text(src, p) for p in range(1, n + 1)}
    # Designer pages can also hold one square character image; their headings
    # ("Meet the Character...", "In Sam's Own Words") keep them out of scenes.
    scenes = [p for p in range(2, n + 1) if _is_scene(imgs.get(p, []), texts[p])
              and not DESIGNER_TEXT.search(texts[p])]
    first, last = (scenes[0], scenes[-1]) if scenes else (n + 1, n)
    kinds = []
    for p in range(1, n + 1):
        has_text, has_img = texts[p].strip() != "", bool(imgs.get(p))
        if p == 1:
            k = "cover"
        elif first <= p <= last:
            k = "scene" if p in scenes else ("designer" if has_text else "drop:blank")
        elif p < first:
            promo = has_text and all(QR_TEXT.search(l) or not l.strip() or
                                     re.match(r"^(together|\d+)$", l.strip(), re.I)
                                     for l in texts[p].splitlines())
            k = ("drop:qr" if promo else "designer" if has_text else
                 "drop:qr" if has_img else "drop:blank")
        else:
            k = "ad" if has_img and not has_text else "drop:blank"
        kinds.append((p, overrides.get(p, k)))
    return kinds, texts


def load_story(src, cache, overrides=None):
    os.makedirs(cache, exist_ok=True)
    kinds, texts = classify(src, overrides)
    story = dict(src=src, kinds=kinds, cover=None, byline="",
                 designers=[], scenes=[], ad=None)

    def render(p, name):
        out = os.path.join(cache, name)
        if not os.path.exists(out + ".jpg"):
            sh(["pdftoppm", "-jpeg", "-jpegopt", "quality=92", "-r", "300",
                "-singlefile", "-f", str(p), "-l", str(p), src, out])
        return out + ".jpg"

    def extract(p, name):
        hits = glob.glob(os.path.join(cache, name + "-*"))
        if not hits:
            sh(["pdfimages", "-all", "-f", str(p), "-l", str(p), src,
                os.path.join(cache, name)])
            hits = glob.glob(os.path.join(cache, name + "-*"))
        if not hits:
            return render(p, name)
        img = sorted(hits)[0]
        if not img.lower().endswith((".jpg", ".jpeg")):  # print-quality JPEG keeps PDFs small
            from PIL import Image
            jpg = os.path.join(cache, name + ".q95.jpg")
            if not os.path.exists(jpg):
                with Image.open(img) as im:
                    im.convert("RGB").save(jpg, quality=95, subsampling=0)
            img = jpg
        return img

    for p, k in kinds:
        if k == "cover":
            story["cover"] = extract(p, f"p{p:03d}")
            by = [l for l in texts[p].splitlines() if l.strip().startswith("By")]
            story["byline"] = by[0].strip() if by else ""
        elif k == "designer":
            story.setdefault("designer_pages", []).append(p)
            img, qr = render(p, f"p{p:03d}"), _qr_top(src, p)
            if qr is not None:  # white out the embedded QR block
                from PIL import Image, ImageDraw
                clean = img[:-4] + "-noqr.jpg"
                if not os.path.exists(clean):
                    im = Image.open(img).convert("RGB")
                    ImageDraw.Draw(im).rectangle(
                        (0, int(qr * im.height) - 8, im.width, im.height), fill="white")
                    im.save(clean, quality=92)
                img = clean
            story["designers"].append(img)
        elif k == "scene":
            en, zh = _split_caption(texts[p])
            story["scenes"].append(dict(img=extract(p, f"p{p:03d}"), en=en, zh=zh,
                                        no=len(story["scenes"]) + 1))
        elif k == "ad":
            px = max((w for w, h in _page_images(src).get(p, [])), default=0)
            if px >= story.get("ad_px", 0):
                story["ad"], story["ad_px"] = render(p, f"p{p:03d}"), px
    story["units"] = designer_units(src, story.get("designer_pages", []), render)
    return story


# ---------------------------------------------------------------- config

def load_book(book_dir):
    with open(os.path.join(book_dir, "book.yaml")) as f:
        cfg = yaml.safe_load(f) or {}
    cfg["_dir"] = book_dir

    def rel(p):
        return os.path.join(book_dir, p) if p else None
    cfg["_rel"] = rel
    chapters = cfg.get("chapters")
    if not chapters:  # auto-discover chapters/NN-name/
        chapters = [dict(dir=os.path.relpath(d, book_dir),
                         title=dict(en=os.path.basename(d).split("-", 1)[-1]
                                    .replace("-", " ").title()))
                    for d in sorted(glob.glob(os.path.join(book_dir, "chapters", "*")))
                    if os.path.isdir(d)]
    for ch in chapters:
        if not ch.get("stories"):
            ch["stories"] = [dict(file=os.path.relpath(f, book_dir))
                             for f in sorted(glob.glob(os.path.join(
                                 rel(ch["dir"]), "*.pdf")))]
        # overrides: {"<pdf file name>": {title:, pages:, designer_words:}}
        for st in ch["stories"]:
            st.update((ch.get("overrides") or {}).get(os.path.basename(st["file"]), {}))
    cfg["chapters"] = chapters
    return cfg


def bi(v):
    """Normalise a bilingual field: str or {en, zh} -> (en, zh)."""
    if isinstance(v, dict):
        return v.get("en", ""), v.get("zh", "")
    return v or "", ""


def paras(s):
    return "".join(f"<p>{esc(p.strip())}</p>"
                   for p in re.split(r"\n\s*\n", s or "") if p.strip())


# ---------------------------------------------------------------- layout

def font_css(cfg):
    """@font-face rules for bundled fonts + the family stacks to use."""
    f = dict(DEFAULT_FONTS, **(cfg.get("fonts") or {}))
    faces = ""
    for fam in {f["en"], f["zh_heading"], f["zh_body"]}:
        if fam in BUNDLED_FONTS:
            with open(os.path.join(FONT_DIR, BUNDLED_FONTS[fam]), "rb") as fh:
                b64 = base64.b64encode(fh.read()).decode()
            faces += (f'@font-face {{ font-family: "{fam}"; font-weight: 100 900; '
                      f'src: url(data:font/ttf;base64,{b64}) format("truetype") }}\n')
    return faces, f


BG_PALETTES = {  # top colour, bottom colour, soft blobs
    "cover": ((255, 236, 205), (255, 210, 175),
              [(255, 214, 120), (190, 225, 255), (255, 190, 200), (200, 240, 200)]),
    "about": ((230, 244, 255), (255, 240, 220),
              [(255, 226, 160), (200, 230, 255), (255, 205, 215), (215, 240, 210)]),
    "imagine": ((255, 244, 214), (225, 240, 255),
                [(255, 220, 140), (190, 220, 255), (255, 200, 210), (205, 240, 205)]),
}


def auto_bg(cfg, name):
    """Soft pastel watercolour-style background, generated once per book
    when the teacher does not supply one."""
    from PIL import Image, ImageDraw, ImageFilter
    out = os.path.join(cfg["_dir"], ".build", f"bg-{name}.jpg")
    if os.path.exists(out):
        return out
    os.makedirs(os.path.dirname(out), exist_ok=True)
    top, bottom, blobs = BG_PALETTES[name]
    w, h = 2700, 3400
    im = Image.new("RGB", (w, h))
    dr = ImageDraw.Draw(im)
    for y in range(h):
        t = y / h
        dr.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    for (x, y, r), c in zip([(400, 500, 260), (2300, 900, 340), (600, 2900, 300),
                             (2200, 2700, 280)], blobs):
        dr.ellipse([x - r, y - r, x + r, y + r], fill=c)
    im.filter(ImageFilter.GaussianBlur(60)).save(out, quality=92)
    return out


def bg_path(cfg, value, name):
    """Configured background path; 'auto' or missing -> generated."""
    if value and value != "auto":
        return cfg["_rel"](value)
    return auto_bg(cfg, name) if name else None


def trim_white(path):
    """Crop near-white page margins off a rendered page. Returns
    (path, width_in, height_in) at the 300ppi render scale."""
    from PIL import Image, ImageChops
    out = path[:-4] + "-trim.jpg"
    with Image.open(path) as src:
        im = src.convert("RGB")
    if not os.path.exists(out):
        mask = ImageChops.difference(im, Image.new("RGB", im.size, "white")) \
            .convert("L").point(lambda v: 255 if v > 18 else 0)
        box = mask.getbbox() or (0, 0, im.width, im.height)
        pad = 24
        box = (max(0, box[0] - pad), max(0, box[1] - pad),
               min(im.width, box[2] + pad), min(im.height, box[3] + pad))
        im.crop(box).save(out, quality=92)
        w, h = box[2] - box[0], box[3] - box[1]
    else:
        with Image.open(out) as t:
            w, h = t.size
    return out, w / 300, h / 300


def pack_designers(pieces, W, H, gap=0.2):
    """Group trimmed designer pages onto as few book pages as possible while
    keeping them >= DESIGNER_MIN_SCALE of original size."""
    def best(pcs):
        top = (0, 1)
        for c in range(1, len(pcs) + 1):
            r = -(-len(pcs) // c)
            cw, chh = (W - (c - 1) * gap) / c, (H - (r - 1) * gap) / r
            sc = min(min(cw / w, chh / h) for _, w, h in pcs)
            top = max(top, (sc, c))
        return top

    def split(pcs):
        sc, c = best(pcs)
        if sc >= DESIGNER_MIN_SCALE or len(pcs) == 1:
            return [(pcs, min(sc, 1.25), c)]
        k = (len(pcs) + 1) // 2
        return split(pcs[:k]) + split(pcs[k:])
    return split(pieces) if pieces else []


CSS = """
{faces}
@page {{ size: {PW}in {PH}in; margin: 0 }}
* {{ box-sizing: border-box; margin: 0; padding: 0 }}
html, body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact }}
body {{ font-family: "{en}", "{zhb}", sans-serif; color: #3b2f2a;
       font-size: {base}pt; line-height: 1.3 }}
.page {{ width: {PW}in; height: {PH}in; position: relative; overflow: hidden;
        break-after: page; background: #fff }}
.page:last-child {{ break-after: auto }}
.bg {{ position: absolute; inset: 0; background-size: cover;
      background-position: center }}
.safe {{ position: absolute; top: {st}in; bottom: {sb}in }}
.recto .safe {{ left: {sg}in; right: {so}in }}
.verso .safe {{ left: {so}in; right: {sg}in }}
.folio {{ position: absolute; bottom: {fb}in; font-size: 9pt; color: #9a8c84 }}
.recto .folio {{ right: {so}in }}  .verso .folio {{ left: {so}in }}
.en {{ font-weight: 700 }}
.zh {{ font-family: "{zhb}", sans-serif; color: #6e625b; font-size: .85em;
      margin-top: .35em; font-weight: 400 }}
.zhh {{ font-family: "{zhh}", "{zhb}", sans-serif; font-weight: 400 }}
.art {{ display: block; object-fit: cover; border-radius: .08in }}
.fit {{ overflow: hidden; min-height: 0 }}
.center {{ display: flex; flex-direction: column; align-items: center;
          justify-content: center; text-align: center }}
/* scenes */
.s1 {{ display: flex; flex-direction: column; align-items: center }}
.s1 .art {{ width: 100%; aspect-ratio: 1 }}
.s1 .cap {{ flex: 1; padding: .18in .1in .1in }}
.zz {{ display: flex; flex-direction: column; gap: {gap}in }}
.zz .row {{ height: {rowh}in; display: flex; gap: {gap}in }}
.zz .row.rev {{ flex-direction: row-reverse }}
.zz .art {{ width: {rowh}in; height: {rowh}in }}
.zz .cap {{ flex: 1; padding: 0 .05in }}
.zz .artw {{ position: relative; display: flex; align-items: center; justify-content: center }}
.zz .cap.zcard {{ align-self: center; height: auto; max-height: 100%; border-radius: .18in;
                 padding: .22in .24in; line-height: 1.3 }}
.solo .art {{ width: {solo}in; height: {solo}in }}
.flow {{ display: grid; grid-template-rows: 1fr 1fr; gap: {g4g}in }}
.flow .row {{ min-height: 0; min-width: 0 }}
.row.sc {{ display: grid; grid-template-columns: 1fr 1fr; gap: {g4g}in }}
.cell {{ display: flex; flex-direction: column; align-items: center; gap: .1in;
        min-height: 0 }}
.cell.flip {{ flex-direction: column-reverse }}
.cell .art {{ width: {g4a}in; height: {g4a}in; border: .05in solid #fff }}
.artw {{ position: relative }}
.sno {{ position: absolute; top: -.1in; left: -.1in; width: .42in; height: .42in;
       border-radius: 50%; background: #ffd23f; border: .035in solid #3b2f2a;
       color: #3b2f2a; font-weight: 700; font-size: .95em; display: flex;
       align-items: center; justify-content: center; line-height: 1 }}
.cell .cap {{ width: {g4a}in; height: {g4c}in; font-size: .78em; line-height: 1.25;
             border-radius: .14in; padding: .08in .12in; display: flex;
             flex-direction: column; justify-content: center; text-align: center }}
.c0 {{ background: #fff1dc }} .c1 {{ background: #e6f2ff }}
.c2 {{ background: #eaf6e4 }} .c3 {{ background: #f6e8fb }}
.spk {{ justify-content: center; background: #fffaf0; border: .03in dashed #f0c89a;
       border-radius: .22in; padding: .3in }}
.spk img {{ width: 58%; display: block }}
.spk .msg, .fill .msg {{ font-weight: 700; color: #c27a3a; font-size: 1.05em;
                        text-align: center; line-height: 1.3 }}
.row.fill {{ display: flex; align-items: center; justify-content: center; gap: .5in;
            background: #fffaf0; border: .03in dashed #f0c89a; border-radius: .22in }}
.row.fill img {{ height: 62%; display: block }}
.row.fill .msg {{ font-size: 1.4em; max-width: 3.4in }}
.row.op {{ display: flex; align-items: center; gap: .35in }}
.row.op.rev {{ flex-direction: row-reverse }}
.row.op .art {{ height: 94%; aspect-ratio: 1; width: auto; border: .06in solid #fff; transform: rotate(-1.2deg) }}
.row.op.rev .art {{ transform: rotate(1.2deg) }}
.optext {{ flex: 1; text-align: center }}
.optext .story-no {{ display: inline-block; margin: .14in 0 .1in; padding: .04in .18in;
                    border-radius: .2in; background: #fde7c8; color: #b0642a;
                    font-weight: 700; font-size: .8em }}
.optext .title {{ font-size: 1.9em; line-height: 1.15; color: #4a3328 }}
.row.des {{ display: flex; flex-direction: column; gap: .08in }}
.row.des h3 {{ font-size: .95em; color: #7b5bd0; text-align: center }}
.dcards {{ flex: 1; min-height: 0; display: grid; gap: .16in }}
.dcard {{ background: #f6f1ff; border-radius: .16in; padding: .12in .12in .1in;
         display: flex; flex-direction: column; gap: .07in; min-height: 0; min-width: 0 }}
.dcard.solo {{ flex-direction: row; align-items: stretch; gap: .2in }}
.dimgs {{ flex: 1 1 0; min-height: 1.3in; display: flex; flex-wrap: wrap; gap: .06in;
         justify-content: center; align-content: stretch }}
.dcard.solo .dimgs {{ flex: 0 0 55% }}
.dimgs figure {{ display: flex; flex-direction: column; align-items: center;
                justify-content: flex-end; min-width: 0; min-height: 0;
                flex: 1 1 0; height: 100% }}
.dimgs.n4 figure {{ flex: 0 0 47%; height: 48% }}
.dimgs figure {{ justify-content: center }}
.dimgs img {{ flex: 0 1 auto; min-height: 0; max-height: calc(100% - .16in);
             max-width: 100%; object-fit: contain; border-radius: .06in }}
.dimgs figcaption {{ font-size: .5em; color: #8a7d76; margin-top: .02in; flex: none }}
.dimgs figcaption:empty {{ display: none }}
.dtext {{ flex: 0 1 auto; max-height: 60%; min-height: 0; text-align: center;
         font-size: .78em; line-height: 1.3 }}
.dcard.solo .dtext {{ max-height: 100%; align-self: center; flex: 1 }}
.dname {{ font-weight: 700; color: #4a3328 }}
.dwt {{ color: #7b5bd0; font-weight: 700; margin: .05in 0 .03in }}
.row.desimg {{ display: flex; gap: .2in; justify-content: center; align-items: center }}
.row.desimg img {{ max-height: 100%; max-width: 48%; object-fit: contain }}
/* portrait grid (authors without notes) */
.portraits {{ display: flex; flex-wrap: wrap; justify-content: center; gap: .2in .14in;
             width: 100%; margin-top: .1in }}
.pt {{ display: flex; flex-direction: column; align-items: center; width: {pcell}in }}
.pimg {{ width: {pimg}in; height: {pimg}in; border-radius: 50%; overflow: hidden;
        background: #fff8e6; border: .045in solid #fff;}}
.pimg img {{ width: 100%; height: 100%; object-fit: cover; object-position: 50% 0;
            transform: scale(1.3); transform-origin: 50% 12% }}
.pname {{ font-weight: 700; margin-top: .06in; font-size: .9em; color: #4a3328 }}
.framed .safe {{ top: calc({st}in + {fr}in); bottom: calc({sb}in + {fr}in) }}
.framed.recto .safe {{ left: calc({sg}in + {fr}in); right: calc({so}in + {fr}in) }}
.framed.verso .safe {{ left: calc({so}in + {fr}in); right: calc({sg}in + {fr}in) }}
.framed .card {{ background: none; padding: .1in .15in }}
.solo .cap {{ width: {solo}in; padding-top: .2in }}
/* openers, headings, contents */
.kicker {{ font-size: .75em; letter-spacing: .06em; color: #c27a3a; font-weight: 700 }}
.opener .art {{ width: {oart}in; height: {oart}in; margin: .2in 0 }}
.title {{ font-size: 1.3em; font-weight: 700 }}
.byline {{ color: #8a7d76; font-size: .85em; margin-top: .06in }}
h1 {{ font-size: 2.1em; line-height: 1.1; color: #4a3328 }}
h2 {{ font-size: 1.6em; margin-bottom: .2in; color: #4a3328 }}
h2 .zhh {{ display: block; font-size: .6em; color: #6e625b; margin-top: .05in }}
.toc {{ list-style: none; width: 100%; text-align: left; flex: 1; min-height: 0 }}
.toc li {{ display: flex; align-items: baseline; gap: .5em; margin: .4em 0;
          font-size: .92em }}
.toc li.ch {{ font-weight: 700; font-size: 1.05em; margin-top: 1em; color: #c27a3a }}
.toc li.st {{ padding-left: .25in }}
.toc .dots {{ flex: 1; border-bottom: 1.5px dotted #c9b8ab;
             transform: translateY(-.25em) }}
.toc small {{ color: #8a7d76; font-weight: 400; font-size: .85em }}
.card {{ background: rgba(255,255,255,.9); border-radius: .16in;
        padding: .3in .32in;}}
.about .card {{ position: absolute; inset: 0; display: flex;
               flex-direction: column }}
.about .body {{ flex: 1; font-size: 1.08em; line-height: 1.55 }}
.about .body p {{ margin-bottom: .55em }}
.about .body .zhp {{ font-family: "{zhb}", sans-serif; color: #5f544e; margin-top: .9em }}
.sign {{ text-align: right; font-size: .85em; margin-top: .1in }}
.about .sign {{ font-family: "{sig}", "Bradley Hand", cursive; font-size: 1.75em;
               color: #4a3328; margin-top: .05in; line-height: 1.2 }}
/* authors */
.authors {{ display: grid; grid-template-columns: repeat({acols}, 1fr);
           grid-template-rows: repeat({arows}, {arowh}in); gap: .12in .3in;
           width: 100%; align-content: start; text-align: left }}
.author {{ min-height: 0; overflow: hidden; display: flow-root }}
.author .who {{ float: left; width: {photo}in; margin: 0 .14in .03in 0;
               text-align: center }}
.author .who img {{ width: {photo}in; height: {photo}in; border-radius: 50%;
                   object-fit: cover; border: .035in solid #f6dcc0; display: block }}
.author .name {{ font-weight: 700; font-size: .78em; margin-top: .03in; line-height: 1.1 }}
.author .note {{ font-size: {note}em; line-height: 1.35 }}
.solo-author {{ display: flex; gap: .35in; align-items: flex-start; margin-top: .25in }}
.solo-author .who {{ flex: 0 0 2.4in; text-align: center }}
.solo-author .who img {{ width: 2.4in; height: 2.4in; border-radius: 50%; object-fit: cover;
                        border: .06in solid #fff; display: block }}
.solo-author .name {{ font-weight: 700; font-size: 1.15em; margin-top: .1in }}
.solo-author .bio {{ flex: 1; font-size: 1em; line-height: 1.45; padding-top: .2in }}
/* designers */
.designers {{ display: grid; gap: .2in; justify-content: center;
             align-content: center; justify-items: center; align-items: center }}
.designers img {{ display: block }}
/* imagine */
.imagine .card {{ position: absolute; inset: 0; display: flex;
                 flex-direction: column; align-items: center; text-align: center }}
.imagine .msg {{ font-size: .88em; line-height: 1.45; margin-top: .05in }}
.imagine .ask {{ font-size: 1.1em; font-weight: 700; color: #c27a3a; margin-top: .18in }}
.drawbox {{ flex: 1; width: 100%; margin-top: .15in; border: .03in dashed #d3a77f;
           border-radius: .14in }}
.lines {{ width: calc(100% - {spark}in); align-self: flex-start; margin-top: .1in }}
.spark {{ position: absolute; right: .12in; bottom: .1in; width: {spark}in }}
.lines div {{ border-bottom: 1px solid #d8c9bd; height: .38in }}
"""

FIT_JS = """
<script>
function fit(){document.querySelectorAll('.fit').forEach(function(el){
  var s=parseFloat(getComputedStyle(el).fontSize);
  while((el.scrollHeight>el.clientHeight+1||el.scrollWidth>el.clientWidth+1)&&s>6){
    s-=0.5; el.style.fontSize=s+'px';}});}
var fams=%s, loads=[];
fams.forEach(function(f){loads.push(document.fonts.load('400 16px "'+f+'"'),
                                      document.fonts.load('700 16px "'+f+'"'));});
Promise.all(loads).then(function(){return document.fonts.ready}).then(fit);
</script>"""


def pack_units(units):
    """Designer cards per half-page row: 3 when every text is short,
    else 2; never leave one card alone when it can join the row before."""
    rows, i = [], 0
    while i < len(units):
        rest = units[i:]
        cap = 3 if all(len(u["words"]) <= 6 for u in rest[:3]) and len(rest) >= 3 else 2
        if len(rest) == 3 and cap == 2 and all(len(u["words"]) <= 9 for u in rest):
            cap = 3
        rows.append(rest[:cap])
        i += cap
    return rows


class Book:
    def __init__(self, cfg, size):
        self.cfg, self.size, self.S = cfg, size, SIZES[size]
        self.pages = []  # (kind, payload)
        S = self.S
        self.safe_w = S["w"] - S["outer"] - S["gutter"]
        self.safe_h = S["h"] - S["top"] - S["bottom"]
        # book.yaml `scenes_per_page: 4` packs a 2x2 grid (letter only)
        self.per_page = int(cfg.get("scenes_per_page") or S["per_page"])
        # 4 per page = flowing half-page rows: stories in a chapter run on
        self.flow = self.per_page == 4
        self.cur, self.n_fill = [], 0

    # -- page list ------------------------------------------------------
    def plan(self, stories):
        c, S = self.cfg, self.S
        if c.get("about_book"):
            self.pages.append(("about", None))
        authors = (c.get("authors") or {}).get("list") or []
        self.portraits = not any(bi(a.get("note"))[0] for a in authors)
        per = 20 if self.portraits else AUTHORS_PER_PAGE  # no notes: portrait grid
        for i in range(0, len(authors), per):
            self.pages.append(("authors", authors[i:i + per]))
        n_entries = sum(1 + len(ch["stories"]) for ch in c["chapters"]) + 1
        self.toc_cap = 999  # always one page; the list shrinks to fit (.fit)
        for i in range(max(1, -(-n_entries // self.toc_cap))):
            self.pages.append(("toc", i))
        self.index = []  # (level, item, extra, page_no)
        for ci, ch in enumerate(c["chapters"], 1):
            self.flush()  # every chapter starts on a new page
            self.index.append(("ch", ch, ci, len(self.pages) + 1))
            for si, st in enumerate(ch["stories"], 1):
                story = stories[st["file"]]
                self.index.append(("st", st, story, len(self.pages) + 1))
                if self.flow:
                    self.row(("op", (ci, ch, si, st, story)))
                    for i, grp in enumerate(pack_units(story.get("units") or [])):
                        self.row(("des", (grp, i == 0)))
                    if not story.get("units") and story["designers"]:
                        self.row(("desimg", story["designers"]))
                    sc = story["scenes"]
                    # scene_numbers: true | first-story (preview) | false
                    sn = c.get("scene_numbers", True)
                    num = sn is True or (sn == "first-story" and ci == 1 and si == 1)
                    for i in range(0, len(sc), 2):
                        self.row(("sc", (sc[i:i + 2], num)))
                    continue
                self.pages.append(("opener", (ci, ch, si, st, story)))
                pieces = [trim_white(d) for d in story["designers"]]
                for grp in pack_designers(pieces, self.safe_w, self.safe_h):
                    self.pages.append(("designers", grp))
                sc = story["scenes"]
                sn = c.get("scene_numbers", True)
                self.num = sn is True or (sn == "first-story" and ci == 1 and si == 1)
                for i in range(0, len(sc), self.per_page):
                    self.pages.append(("scenes", (sc[i:i + self.per_page], self.num)))
        self.flush()
        if c.get("imagine", True) is not False:
            self.imagine_page = len(self.pages) + 1
            self.pages.append(("imagine", None))
        if c.get("kindlewood_page", False):
            ad = best_ad(stories)
            if ad:
                self.pages.append(("designers", ([trim_white(ad)], 1.0, 1)))
        if len(self.pages) % 2:  # Mixam needs an even count: no blank pages
            prompts = (c.get("imagine") or {}).get("extra_prompts") or EXTRA_PROMPTS
            self.pages.append(("prompt", prompts[0]))

    def row(self, r):
        self.cur.append(r)
        if len(self.cur) == 2:
            self.pages.append(("flow", self.cur))
            self.cur = []

    def flush(self):
        """Close a half-filled flow page with a wide Spark row."""
        if self.cur:
            self.cur.append(("fill", None))
            self.pages.append(("flow", self.cur))
            self.cur = []

    def filler(self, wide=False):
        pose, msg = FILLERS[self.n_fill % len(FILLERS)]
        self.n_fill += 1
        img = os.path.join(SPARK_DIR, f"spark-{pose}.png")
        return (f'<div class="{"row fill" if wide else "cell spk"}">'
                f'<img src="{url(img)}"><div class="msg">{esc(msg)}</div></div>')

    def row_html(self, r):
        kind, d = r
        if kind == "op":
            ci, ch, si, st, story = d
            return (f'<div class="row op{" rev" if si % 2 == 0 else ""}">'
                    f'<img class="art" src="{url(story["cover"])}"><div class="optext">'
                    f'<div class="kicker">Chapter {ci}: {esc(bi(ch.get("title"))[0])}</div>'
                    f'<div class="story-no">Story {si}</div>'
                    f'<div class="title">{esc(st.get("title") or story["title"])}</div>'
                    f'<div class="byline">{esc(story["byline"])}</div></div></div>')
        if kind == "des":
            units, first = d
            cards = ""
            for u in units:
                labels = (["Original Creation", "In the Story"] if len(u["imgs"]) == 2
                          else [""] * len(u["imgs"]))
                figs = "".join(f'<figure><img src="{url(p)}"><figcaption>{l}</figcaption></figure>'
                               for p, l in zip(u["imgs"], labels))
                words = "<br>".join(esc(l) for l in u["words"])
                solo = " solo" if len(units) == 1 and u["words"] else ""
                cards += (f'<div class="dcard{solo}">'
                          + (f'<div class="dimgs n{len(u["imgs"])}">{figs}</div>' if figs else "")
                          + f'<div class="dtext fit"><div class="dname">{esc(u["caption"] or u["name"])}</div>'
                          + (f'<div class="dwt">{esc(u["title"])}</div><div class="dw">{words}</div>'
                             if u["words"] else "") + '</div></div>')
            head = '<h3>Meet the Character Designers</h3>' if first else ""
            return (f'<div class="row des">{head}<div class="dcards" style="grid-template-columns:'
                    f'repeat({len(units)}, 1fr)">{cards}</div></div>')
        if kind == "desimg":
            imgs = "".join(f'<img src="{url(p)}">' for p in d)
            return f'<div class="row desimg">{imgs}</div>'
        if kind == "sc":
            d, num = d
            cells = "".join(
                f'<div class="cell{" flip" if i % 2 else ""}">'
                f'<div class="artw" style="transform:rotate({[-1.2, 1][i]}deg)">'
                f'<img class="art" src="{url(s["img"])}">'
                + (f'<div class="sno">{s["no"]}</div>' if num else "") + '</div>'
                f'<div class="cap fit c{(i + self.n_sc) % 4}"><div class="en">{esc(s["en"])}</div>'
                f'<div class="zh">{esc(s["zh"])}</div></div></div>'
                for i, s in enumerate(d))
            self.n_sc += 1
            if len(d) == 1:
                cells += self.filler()
            return f'<div class="row sc">{cells}</div>'
        return self.filler(wide=True)

    # -- html -----------------------------------------------------------
    def css(self):
        css = self._css()
        # book.yaml `scene_fit: contain` keeps each scene picture whole at its own
        # aspect (photo pages of real artwork); default `cover` crops to a square.
        if (self.cfg.get("scene_fit") or "cover") == "contain":
            rowh = round((self.safe_h - 0.2) / 2, 3)
            css += (
                ".zz .row {{ align-items: center }}\n"
                ".zz .art {{ width: auto; height: auto; max-height: {h}in; "
                "max-width: {w}in; object-fit: contain; border: .05in solid #fff }}\n"
                ".solo .art, .s1 .art {{ width: auto; height: auto; aspect-ratio: auto; "
                "max-width: 100%; max-height: {h2}in; object-fit: contain }}\n"
                ".cell .art {{ object-fit: contain; background: #fff }}\n"
            ).format(h=rowh, w=round(self.safe_w * 0.64, 3), h2=round(self.safe_h * 0.7, 3))
        return css

    def _css(self):
        S, B = self.S, BLEED
        gap = 0.2
        faces, f = font_css(self.cfg)
        head_h = 0.85 if self.size == "letter" else 0.7
        g4g = 0.22  # grid gap
        g4w = (self.safe_w - g4g) / 2
        g4h = (self.safe_h - g4g) / 2
        g4a = round(min(g4w, g4h - 1.25), 3)  # art side; rest is caption
        arows = -(-AUTHORS_PER_PAGE // S["authors_cols"])
        return CSS.format(
            faces=faces, en=f["en"], zhb=f["zh_body"], zhh=f["zh_heading"],
            sig=(self.cfg.get("fonts") or {}).get("signature", "Snell Roundhand"),
            PW=S["w"] + 2 * B, PH=S["h"] + 2 * B, base=S["base_pt"],
            st=B + S["top"], sb=B + S["bottom"], sg=B + S["gutter"],
            so=B + S["outer"], fb=B + 0.22, gap=gap,
            rowh=round((self.safe_h - gap) / 2, 3), oart=S["opener_art"],
            solo=S["solo_art"], photo=S["photo"], acols=S["authors_cols"],
            spark=1.7 if self.size == "letter" else 1.15,
            note=S["note_em"], g4g=g4g, g4a=g4a, g4c=round(g4h - g4a - 0.1, 3),
            fr=0.45 if self.size == "letter" else 0.3,
            pimg=1.12 if self.size == "letter" else 0.78,
            pcell=1.22 if self.size == "letter" else 0.86,
            arows=arows,
            arowh=round((self.safe_h - head_h - (arows - 1) * 0.12) / arows, 3))

    def art_size(self, path):
        """contain mode: give every zigzag picture about the same area (portrait,
        landscape and square alike), capped by the row box."""
        if (self.cfg.get("scene_fit") or "cover") != "contain":
            return ""
        from PIL import Image
        with Image.open(path) as im:
            r = im.width / im.height
        H = round((self.safe_h - 0.2) / 2, 3)
        W = round(self.safe_w * 0.64, 3)
        area = 0.75 * W * H                   # fits r = 0.75 .. 1.33 untouched
        w, h = (area * r) ** 0.5, (area / r) ** 0.5
        k = min(1, W / w, H / h)
        return f' style="width:{w * k:.3f}in;height:{h * k:.3f}in;max-width:none;max-height:none"'

    def caption(self, s):
        return (f'<div class="cap center fit"><div class="en">{esc(s["en"])}</div>'
                f'<div class="zh">{esc(s["zh"])}</div></div>')

    def page_html(self, n, kind, data):
        side = "recto" if n % 2 else "verso"
        body, bg, folio = "", "", True
        rel = self.cfg["_rel"]

        framed = []

        def bg_of(value, auto=None):
            if value and value != "auto":
                framed.append(1)  # a real artwork frame: keep text off it
            p = bg_path(self.cfg, value, auto)
            return (f'<div class="bg" style="background-image:url({url(p)})"></div>'
                    if p else "")
        if kind == "about":
            a = self.cfg["about_book"]
            bg = bg_of(a.get("background"), "about")
            body = (f'<div class="safe about"><div class="card">'
                    f'<h2>About This Book'
                    + ('<span class="zhh">关于这本书</span>' if a.get("text_zh", "").strip() else "")
                    + '</h2>'
                    f'<div class="body fit">{paras(a.get("text_en", ""))}'
                    f'<div class="zhp">{paras(a.get("text_zh", ""))}</div>'
                    f'<div class="sign">{esc(a.get("signed", ""))}</div></div></div></div>')
            folio = False
        elif kind == "authors":
            bg = bg_of((self.cfg.get("authors") or {}).get("background"))
            cards = ""
            au = self.cfg.get("authors") or {}
            if len(au.get("list") or []) == 1:
                p = au["list"][0]
                img = f'<img src="{url(rel(p["photo"]))}">' if p.get("photo") else ""
                note = bi(p.get("note"))[0]
                body = (f'<div class="safe" style="display:flex;flex-direction:column">'
                        f'<h2 style="text-align:center">{esc(au.get("heading") or "Meet the Author")}</h2>'
                        f'<div class="solo-author"><div class="who">{img}'
                        f'<div class="name">{esc(p["name"])}</div></div>'
                        f'<div class="bio">{paras(note) if note else ""}</div></div></div>')
                data = []
            elif self.portraits:
                cells = "".join(
                    f'<div class="pt"><div class="pimg">'
                    + (f'<img src="{url(rel(p["photo"]))}">' if p.get("photo") else "")
                    + f'</div><div class="pname">{esc(p["name"])}</div></div>' for p in data)
                data = []
                body = (f'<div class="safe center" style="justify-content:flex-start">'
                        f'<h2>Meet Our Young Authors</h2><div class="portraits">{cells}</div></div>')
            for p in data:
                note = bi(p.get("note"))[0]
                img = f'<img src="{url(rel(p["photo"]))}">' if p.get("photo") else ""
                cards += (f'<div class="author fit"><div class="who">{img}'
                          f'<div class="name">{esc(p["name"])}</div></div>'
                          f'<div class="note">{esc(note)}</div></div>')
            if cards:
                body = (f'<div class="safe center" style="justify-content:flex-start">'
                        f'<h2>Meet Our Young Authors</h2>'
                        f'<div class="authors">{cards}</div></div>')
        elif kind == "toc":
            rows = []
            one = bool(self.cfg.get("single_chapter"))
            for lvl, item, extra, pg in self.index:
                if lvl == "ch" and one:
                    continue
                if lvl == "st" and one:
                    n = sum(1 for l, *_ in self.index[:self.index.index((lvl, item, extra, pg)) + 1] if l == "st")
                    rows.append(f'<li class="ch"><span>Story {n}: {esc(item.get("title") or extra["title"])} '
                                f'<small>{esc(extra["byline"])}</small></span>'
                                f'<span class="dots"></span><span>{pg}</span></li>')
                    continue
                if lvl == "ch":
                    rows.append(f'<li class="ch"><span>Chapter {extra}: '
                                f'{esc(bi(item.get("title"))[0])}</span>'
                                f'<span class="dots"></span><span>{pg}</span></li>')
                else:
                    rows.append(f'<li class="st"><span>{esc(item.get("title") or extra["title"])} '
                                f'<small>{esc(extra["byline"])}</small></span>'
                                f'<span class="dots"></span><span>{pg}</span></li>')
            if hasattr(self, "imagine_page"):
                rows.append(f'<li class="ch"><span>Keep Imagining!</span>'
                            f'<span class="dots"></span><span>{self.imagine_page}</span></li>')
            bg = bg_of((self.cfg.get("contents") or {}).get("background"))
            chunk = rows[data * self.toc_cap:(data + 1) * self.toc_cap]
            head = '<h2>Contents</h2>' if data == 0 else ""
            body = (f'<div class="safe center" style="justify-content:flex-start">{head}'
                    f'<ul class="toc fit">{"".join(chunk)}</ul></div>')
        elif kind == "opener":
            ci, ch, si, st, story = data
            kick = ("" if self.cfg.get("single_chapter") else
                    f'<div class="kicker">Chapter {ci}: {esc(bi(ch.get("title"))[0])}'
                    f' &nbsp;·&nbsp; Story {si}</div>')
            oart = self.cfg.get("opener_art")  # book.yaml: opener picture size (in)
            ost = f' style="width:{oart}in;height:{oart}in"' if oart else ""
            body = (f'<div class="safe center opener">{kick}'
                    f'<img class="art" src="{url(story["cover"])}"{ost}>'
                    f'<div class="title">{esc(st.get("title") or story["title"])}</div>'
                    f'<div class="byline">{esc(story["byline"])}</div></div>')
        elif kind == "designers":
            pcs, sc, cols = data
            imgs = "".join(f'<img src="{url(p)}" style="width:{w * sc:.3f}in;'
                           f'height:{h * sc:.3f}in">' for p, w, h in pcs)
            body = (f'<div class="safe designers" style="grid-template-columns:'
                    f'repeat({cols}, auto)">{imgs}</div>')
        elif kind == "scenes":
            data, num = data
            if self.S["per_page"] == 1:
                s = data[0]
                body = (f'<div class="safe s1"><img class="art" src="{url(s["img"])}">'
                        f'{self.caption(s)}</div>')
            elif len(data) == 1:  # odd scene out: centre it, caption below
                s = data[0]
                body = (f'<div class="safe center solo"><img class="art" src="{url(s["img"])}">'
                        f'{self.caption(s)}</div>')
            else:
                # zigzag rows: picture + caption alternate sides; numbered badge
                # and pastel caption card match the 4-per-page rules (22-23)
                rows = "".join(
                    f'<div class="row{" rev" if i % 2 else ""}">'
                    f'<div class="artw"><img class="art" src="{url(s["img"])}"{self.art_size(s["img"])}>'
                    + (f'<div class="sno">{s["no"]}</div>' if num and s.get("no") else "")
                    + f'</div><div class="cap center fit zcard c{(i + n) % 4}">'
                    f'<div class="en">{esc(s["en"])}</div><div class="zh">{esc(s["zh"])}</div></div></div>'
                    for i, s in enumerate(data))
                body = f'<div class="safe zz">{rows}</div>'
        elif kind == "flow":
            body = f'<div class="safe flow">{"".join(self.row_html(r) for r in data)}</div>'
        elif kind in ("imagine", "prompt"):
            im = self.cfg.get("imagine") or {}
            bg = bg_of(im.get("background"), "imagine")
            if kind == "imagine":
                head = (f'<h2 style="margin-bottom:.05in">'
                        f'{esc(bi(im.get("title"))[0] or "Keep Imagining!")}</h2>'
                        f'<div class="msg">{esc(bi(im.get("message"))[0] or IMAGINE_MSG)}</div>'
                        f'<div class="ask">{esc(bi(im.get("question"))[0] or IMAGINE_ASK)}</div>')
            else:
                head = (f'<div class="kicker">Story Idea</div>'
                        f'<div class="ask" style="margin-top:.08in">{esc(data)}</div>'
                        f'<div class="msg">Draw it in the box, then write your story on the lines.</div>')
            body = (f'<div class="safe imagine"><div class="card">{head}'
                    f'<div class="drawbox"></div>'
                    f'<div class="lines"><div></div><div></div><div></div></div>'
                    f'<img class="spark" src="{url(SPARK)}"></div></div>')
            folio = False
        elif kind == "blank":
            folio = False
        f = f'<div class="folio">{n}</div>' if folio else ""
        cls = " framed" if framed else ""
        return f'<section class="page {side}{cls}">{bg}{body}{f}</section>'

    def html(self, start=1, end=None):
        """HTML for pages start..end (1-based, inclusive). Page content is
        rendered in order from page 1 so rotating counters stay stable."""
        self.n_sc, self.n_fill = 0, 0
        end = end or len(self.pages)
        pages = [self.page_html(i, k, d) for i, (k, d) in enumerate(self.pages, 1)]
        pages = "".join(pages[start - 1:end])
        _, f = font_css(self.cfg)
        fams = json.dumps(sorted({f["en"], f["zh_heading"], f["zh_body"]}))
        return (f'<!doctype html><html><head><meta charset="utf-8">'
                f'<style>{self.css()}</style></head><body>{pages}'
                f'{FIT_JS % fams}</body></html>')


def best_ad(stories):
    """The KindleWood Families page rendered from the highest-res export."""
    best = max(stories.values(), key=lambda s: s.get("ad_px", 0) if s["ad"] else -1,
               default=None)
    return best["ad"] if best and best["ad"] else None


COVER_CSS = """
@page {{ size: {PW}in {PH}in; margin: 0 }}
* {{ box-sizing: border-box; margin: 0; padding: 0 }}
html, body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact }}
{faces}
body {{ font-family: "{en}", "{zhb}", sans-serif; color: #3b2f2a }}
.sheet {{ width: {PW}in; height: {PH}in; position: relative; overflow: hidden }}
.panel {{ position: absolute; top: 0; bottom: 0; overflow: hidden }}
.bg {{ position: absolute; inset: 0; background-size: cover; background-position: center }}
.back {{ left: 0; width: {BW}in }}
.spine {{ left: {BW}in; width: {SP}in; background: {spc}; display: flex;
         align-items: center; justify-content: center }}
.spine div {{ writing-mode: vertical-rl; font-weight: 700; color: #fff;
             font-size: {spf}pt; white-space: nowrap }}
.spine .spcredit {{ font-weight: 400; font-size: .72em; margin-top: .45in }}
.front {{ left: {FL}in; width: {BW}in }}
.fsafe {{ position: absolute; top: {m}in; bottom: {m}in; left: {fl}in; right: {fr}in }}
.title {{ position: absolute; top: 0; left: 0; right: 0; text-align: center;
         background: rgba(255,255,255,.85); border-radius: .18in; padding: .16in .2in }}
.title h1 {{ font-size: {tf}pt; line-height: 1.05; color: #4a3328 }}
.title .zh {{ font-family: "{zhh}", "{zhb}", sans-serif; font-size: {tz}pt; color: #6e625b;
             margin-top: .05in }}
.kwback {{ position: absolute; inset: {bm}in {bm}in {bm}in {B}in; display: flex;
          align-items: center; justify-content: center }}
.kwback img {{ max-width: 100%; max-height: 100%; display: block }}
.kwback.framedback {{ inset: 1.1in 1.0in 1.1in {fbl}in }}
.kwback.framedback img {{ border-radius: .15in;}}
.title .sub {{ font-size: {ts}pt; color: #c27a3a; font-weight: 700; margin-top: .06in;
              letter-spacing: .08em; text-transform: uppercase }}
.scenes {{ position: absolute; top: 25%; height: 41%; left: 0; right: 0;
          display: flex; flex-wrap: wrap; gap: {sg}in; align-content: center;
          justify-content: center }}
.scenes img {{ width: {tile}in; height: {tile}in; object-fit: cover; background: #fff;
              padding: {tp}in;}}
.chars {{ position: absolute; bottom: {fb}in; height: 27%; left: 0; right: 0;
         display: flex; align-items: flex-end; justify-content: center }}
.chars img {{ width: {cw}in; height: 100%; object-fit: contain; object-position: bottom }}
.chars img.sticker {{ height: {chs}in; width: {cs}in; margin: 0 {cm}in; object-fit: cover;
                     background: #fff; padding: {tp}in; border-radius: .1in;}}
.blurb {{ position: absolute; top: {m}in; left: {m2}in; right: {m}in;
         background: rgba(255,255,255,.88); border-radius: .16in; padding: .2in;
         font-size: {bf}pt; line-height: 1.4 }}
.collage {{ position: absolute; top: {ct}%; bottom: {fb}in; left: 0; right: 0;
           display: grid; grid-template-columns: repeat({cc}, 1fr);
           grid-auto-rows: 1fr; gap: {cg}in; align-items: center; justify-items: center }}
.collage img {{ width: 100%; height: 100%; object-fit: contain; min-height: 0;}}
.collage img.sticker {{ object-fit: cover; background: #fff; padding: .05in;
                       border-radius: .1in; aspect-ratio: 1; height: auto }}
.collage img.ch.sticker {{ aspect-ratio: auto; height: 100%; object-fit: contain }}
.foot {{ position: absolute; bottom: 0; left: 0; right: 0; text-align: center;
         line-height: 1.2 }}
.foot span {{ display: inline-block; background: rgba(255,255,255,.82);
             border-radius: .12in; padding: .03in .16in }}
.foot .school {{ font-size: {fs}pt; font-weight: 700; color: #4a3328 }}
.foot .credit {{ font-size: {fc}pt; font-weight: 700; color: #4a3328; margin-top: .04in }}
"""


COVER_CREDIT = "© Powered by KindleWood Studio"


def has_alpha(path):
    from PIL import Image
    with Image.open(path) as im:
        return im.mode in ("RGBA", "LA") or "transparency" in im.info


def cover_html(cfg, size, spine, n_pages, ad=None):
    S, B, rel = SIZES[size], BLEED, cfg["_rel"]
    cv = cfg.get("cover") or {}
    W, H = S["w"], S["h"]
    PW, PH = 2 * W + spine + 2 * B, H + 2 * B
    k = W / 8.5
    fw, fh = W - 0.8, H - 0.8 - 2 * B  # front safe area

    def folder(key):
        d = rel(cv.get(key) or f"cover/{key}")  # default: the init folders
        if not os.path.isdir(d):
            return []
        return sorted(f for f in glob.glob(os.path.join(d, "*"))
                      if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")))
    baked = bool(cv.get("title_baked"))  # background art already has the title
    sc_files = folder("scenes")[:6]
    ch_files = folder("characters")[:24 if baked else 8]
    ns, nc, g = max(1, len(sc_files)), max(1, len(ch_files)), 0.18
    cols = 3 if ns >= 5 else min(ns, 2)
    rows = -(-ns // cols)
    tile = min((fw - (cols - 1) * g) / cols, (0.41 * fh - (rows - 1) * g) / rows) - 0.05
    slot = fw / nc
    faces, f = font_css(cfg)
    school = (cfg.get("school") or "").strip()
    css = COVER_CSS.format(
        faces=faces, en=f["en"], zhb=f["zh_body"], zhh=f["zh_heading"],
        B=B, bm=B + 0.3, fbl=B + 1.0, sg=g, tile=round(tile, 3), tp=round(0.05 * k, 3),
        cw=round(slot, 3), cs=round(slot * 0.88, 3), cm=round(slot * 0.06, 3),
        chs=round(min(0.3 * fh, slot * 0.88 * 1.25), 3),
        PW=PW, PH=PH, BW=W + B, SP=spine, FL=W + B + spine,
        spc=cv.get("spine_color", "#d9824b"), spf=max(6, min(14, spine * 72 * .5)),
        m=B + 0.4, fl=0.4, fr=B + 0.4, m2=B + 0.4,
        tf=round(44 * k), tz=round(24 * k), ts=round(12 * k), bf=round(12 * k),
        ct=31, cc=5 if len(sc_files) + len(ch_files) > 16 else 4, cg=round(.1 * k, 3),
        fs=round(15 * k), fc=round(10 * k), fb=round((0.75 if school else 0.4) * k, 3))
    en, zh = bi(cfg.get("title"))
    bgf = (f'<div class="bg" style="background-image:'
           f'url({url(bg_path(cfg, cv.get("background"), "cover"))})"></div>')
    scenes = "".join(
        f'<img src="{url(p)}" style="transform:rotate({[-4, 3, -2, 4, -3, 2][i % 6]}deg)">'
        for i, p in enumerate(sc_files))
    chars = "".join(
        f'<img class="{"" if has_alpha(p) else "sticker"}" src="{url(p)}">'
        for p in ch_files)
    if baked:
        # one collage like the approved example: kids with scenes mixed in
        items = [("ch", p) for p in ch_files]
        step = max(1, len(items) // max(1, len(sc_files)))
        for i, p in enumerate(sc_files):
            items.insert(min(len(items), i * (step + 1) + step // 2 + 1), ("sc", p))
        tilt = [-3, 2, -1, 3, -2, 1]
        art = "".join(
            f'<img class="{kd}{"" if has_alpha(p) else " sticker"}" src="{url(p)}" '
            f'style="transform:rotate({tilt[i % 6]}deg)">' for i, (kd, p) in enumerate(items))
        main = f'<div class="collage">{art}</div>'
    else:
        main = (f'<div class="title"><h1>{esc(en)}</h1><div class="zh">{esc(zh)}</div>'
                f'<div class="sub">{esc(cfg.get("subtitle", ""))}</div></div>'
                f'<div class="scenes">{scenes}</div><div class="chars">{chars}</div>')
    if cv.get("front_image"):  # a finished front cover: use it as is
        fimg = rel(cv["front_image"])
        front_html = (f'<div class="panel front"><div class="bg" style="background-image:'
                      f'url({url(fimg)})"></div></div>')
    front = (f'<div class="panel front">{bgf}<div class="fsafe">{main}'
             f'<div class="foot">'
             + (f'<span class="school">{esc(school)}</span><br>' if school else "")
             + f'<span class="credit">{esc(COVER_CREDIT)}</span></div>'
             f'</div></div>')
    if cv.get("front_image"):
        front = front_html
    bk = cfg.get("back_cover") or {}
    if not bk and os.path.exists(BACK_COVER):  # default: the standard back cover
        back = (f'<div class="panel back"><div class="bg" style="background-image:'
                f'url({url(BACK_COVER)})"></div></div>')
    elif bk.get("background") and ad:  # KindleWood page on its own background art
        back = (f'<div class="panel back"><div class="bg" style="background-image:'
                f'url({url(rel(bk["background"]))})"></div><div class="kwback framedback">'
                f'<img src="{url(trim_white(ad)[0])}"></div></div>')
    elif bk.get("image"):
        b_en, b_zh = bi(bk.get("text"))
        blurb = (f'<div class="blurb">{esc(b_en)}<div style="color:#6e625b;margin-top:.4em">'
                 f'{esc(b_zh)}</div></div>' if b_en or b_zh else "")
        back = (f'<div class="panel back"><div class="bg" style="background-image:'
                f'url({url(rel(bk["image"]))})"></div>{blurb}</div>')
    elif ad:  # default: the KindleWood Families page from the story exports
        back = (f'<div class="panel back" style="background:#fff"><div class="kwback">'
                f'<img src="{url(trim_white(ad)[0])}"></div></div>')
    else:
        back = '<div class="panel back" style="background:#fbe3c8"></div>'

    # spine: book title + the KindleWood credit (book-rules 13)
    sp_text = (f'<b>{esc(en)}</b><span class="spcredit">{esc(COVER_CREDIT)}</span>'
               if spine >= 0.2 else "")
    spbg = ""
    if cv.get("front_image"):  # continue the front art's left edge round the spine
        from PIL import Image
        with Image.open(rel(cv["front_image"])) as im:
            im = im.convert("RGB")
            strip = im.crop((0, 0, max(1, im.width // 60), im.height)).resize((1, 12))
            stops = ", ".join("rgb(%d,%d,%d)" % strip.getpixel((0, i)) for i in range(12))
        spbg = f' style="background: linear-gradient({stops})"'
    sp = f'<div class="panel spine"{spbg}><div>{sp_text}</div></div>'
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style>'
            f'</head><body><div class="sheet">{back}{sp}{front}</div></body></html>'), PW, PH


# ---------------------------------------------------------------- output

def print_pdf(html_text, out_pdf, work):
    hp = os.path.join(work, os.path.basename(out_pdf) + ".html")
    with open(hp, "w") as f:
        f.write(html_text)
    prof = tempfile.mkdtemp(prefix="kwchrome")
    try:
        r = sh([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                f"--user-data-dir={prof}", "--virtual-time-budget=20000",
                "--run-all-compositor-stages-before-draw",
                f"--print-to-pdf={out_pdf}", url(hp)])
    finally:
        shutil.rmtree(prof, ignore_errors=True)
    if not os.path.exists(out_pdf):
        sys.exit(f"Chrome failed to print {hp}:\n{r.stderr[-2000:]}")


def stamp_boxes(pdf, trim_w, trim_h):
    """Force exact page size and set TrimBox/BleedBox (Mixam reads these)."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import RectangleObject
    reader, writer = PdfReader(pdf), PdfWriter()
    b = BLEED * 72
    PW, PH = trim_w * 72 + 2 * b, trim_h * 72 + 2 * b
    for page in reader.pages:
        page.mediabox = RectangleObject([0, 0, PW, PH])
        page.cropbox = RectangleObject([0, 0, PW, PH])
        page.bleedbox = RectangleObject([0, 0, PW, PH])
        page.trimbox = RectangleObject([b, b, PW - b, PH - b])
        writer.add_page(page)
    writer.compress_identical_objects()
    with open(pdf, "wb") as f:
        writer.write(f)
    return len(reader.pages)


def cmd_init(a):
    d = a.book_dir
    for sub in ["cover/characters", "cover/scenes", "about-book/emails", "authors",
                "chapters/01-first-theme", "imagine", "back-cover", "out"]:
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    yp = os.path.join(d, "book.yaml")
    if os.path.exists(yp):
        sys.exit(f"{yp} exists; not overwriting")
    with open(os.path.join(os.path.dirname(__file__), "..", "book.template.yaml")) as f:
        tmpl = f.read()
    with open(yp, "w") as f:
        f.write(tmpl)
    print(f"scaffolded {d} -- fill book.yaml, drop story PDFs in chapters/NN-theme/")


def _cutout(src, dst, tol=28):
    """Knock out a plain light background by flood-filling from the
    corners, so a character can stand on the cover without a box."""
    from PIL import Image, ImageDraw
    im = Image.open(src).convert("RGBA")
    w, h = im.size
    for xy in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        r, g, b, a = im.getpixel(xy)
        if a and min(r, g, b) > 200:
            ImageDraw.floodfill(im, xy, (255, 255, 255, 0), thresh=tol)
    im.save(dst)


def contact_sheet(files, out, cols=6, cell=260):
    from PIL import Image, ImageDraw
    if not files:
        return
    rows = -(-len(files) // cols)
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 34)), "white")
    dr = ImageDraw.Draw(sheet)
    for i, f in enumerate(files):
        with Image.open(f) as im:
            size = f"{im.width}x{im.height}" + ("  LOW-RES" if max(im.size) < 700 else "")
            im = im.convert("RGBA")
            im.thumbnail((cell - 12, cell - 12))
            x, y = (i % cols) * cell, (i // cols) * (cell + 34)
            tile = Image.new("RGBA", (cell - 12, cell - 12), (235, 235, 235, 255))
            tile.alpha_composite(im, ((tile.width - im.width) // 2, (tile.height - im.height) // 2))
            sheet.paste(tile.convert("RGB"), (x + 6, y + 6))
        dr.text((x + 6, y + cell - 4), os.path.basename(f)[:34], fill="black")
        dr.text((x + 6, y + cell + 8), size, fill="red" if "LOW" in size else "#666")
    sheet.save(out, quality=88)


def cmd_extract(a):
    """Pull candidate cover/author images out of every story into
    BOOK_DIR/candidates/ with contact sheets for picking."""
    cfg = load_book(a.book_dir)
    out = os.path.join(a.book_dir, "candidates")
    dirs = {k: os.path.join(out, k) for k in
            ("characters", "drawings", "scenes", "story-covers")}
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)
    for ch in cfg["chapters"]:
        for st in ch["stories"]:
            src = cfg["_rel"](st["file"])
            tag = slugify(st.get("title") or os.path.splitext(os.path.basename(src))[0])[:30]
            kinds, texts = classify(src)
            with tempfile.TemporaryDirectory() as td:
                for p, k in kinds:
                    if k not in ("cover", "designer", "scene"):
                        continue
                    rows = [l.split() for l in sh(["pdfimages", "-list", "-f", str(p),
                                                   "-l", str(p), src]).stdout.splitlines()[2:]]
                    rows = [r for r in rows if len(r) > 4 and r[2] == "image"]
                    if not rows:
                        continue
                    pre = os.path.join(td, f"p{p}")
                    sh(["pdfimages", "-all", "-f", str(p), "-l", str(p), src, pre])
                    files = {int(r[1]): (glob.glob(f"{pre}-{int(r[1]):03d}.*") or [None])[0]
                             for r in rows}
                    if k == "cover":
                        f = files[int(rows[0][1])]
                        shutil.copy(f, os.path.join(dirs["story-covers"], f"{tag}{os.path.splitext(f)[1]}"))
                    elif k == "scene":
                        f = files[int(rows[0][1])]
                        shutil.copy(f, os.path.join(dirs["scenes"], f"{tag}-p{p:02d}{os.path.splitext(f)[1]}"))
                    else:
                        # Designer page: big photos = original drawings,
                        # smaller art = the character as drawn in the story.
                        area = {int(r[1]): int(r[3]) * int(r[4]) for r in rows}
                        big = max(area.values())
                        names = re.findall(r"[\u201c\"]\s*([^\u201d\"]+?)\s*[\u201d\"]", texts[p])
                        chars = [n for n in sorted(area) if area[n] < big * 0.5]
                        for j, n in enumerate(sorted(area)):
                            f = files[n]
                            if not f:
                                continue
                            if n in chars:
                                i = chars.index(n)
                                who = slugify(names[i]) if len(names) == len(chars) else f"{i + 1}"
                                base = os.path.join(dirs["characters"], f"{tag}-{who}")
                                shutil.copy(f, base + os.path.splitext(f)[1])
                                _cutout(f, base + "-cutout.png")
                            else:
                                shutil.copy(f, os.path.join(dirs["drawings"],
                                                            f"{tag}-p{p:02d}-{j}{os.path.splitext(f)[1]}"))
    for k, d in dirs.items():
        files = sorted(f for f in glob.glob(os.path.join(d, "*")) if not f.endswith("_sheet.jpg"))
        contact_sheet(files, os.path.join(out, f"{k}_sheet.jpg"))
        print(f"{k}: {len(files)} files -> {os.path.join(out, k + '_sheet.jpg')}")


def gather(cfg):
    stories = {}
    cache = os.path.join(cfg["_dir"], ".build")
    for ch in cfg["chapters"]:
        for st in ch["stories"]:
            src = cfg["_rel"](st["file"])
            ov = {int(k): v for k, v in (st.get("pages") or {}).items()}
            s = load_story(src, os.path.join(cache, slugify(st["file"])), ov)
            s["title"] = os.path.splitext(os.path.basename(src))[0]
            # scene_images: {<scene no>: path} swaps in an edited picture (e.g. a copy
            # with plain photo edges trimmed); captions and numbering are unchanged
            for no, path in (st.get("scene_images") or {}).items():
                hit = next((x for x in s["scenes"] if x["no"] == int(no)), None)
                if hit is None:
                    sys.exit(f"scene_images: no scene {no} in {st['file']}")
                hit["img"] = cfg["_rel"](path)
            # designer_words: {Sam: [lines...]} fills text missing from an export
            for name, lines in (st.get("designer_words") or {}).items():
                u = next((u for u in s["units"] if u["name"].lower() == name.lower()), None)
                if u is None:
                    u = dict(name=name, caption=f"\u201c{name}\u201d", imgs=[], words=[], title="")
                    s["units"].append(u)
                u["words"] = list(lines) if isinstance(lines, list) else str(lines).splitlines()
                u["title"] = f"In {name}'s Own Words"
            # scene_edits: {7: {en:, zh:}} rewrites a caption (numbers as exported);
            # insert_scenes: [{after: 7, img:, en:, zh:}] adds a picture of the teacher's
            for no, ed in (st.get("scene_edits") or {}).items():
                sc = s["scenes"][int(no) - 1]
                sc.update({k: v for k, v in ed.items() if k in ("en", "zh")})
                if ed.get("img"):
                    sc["img"] = cfg["_rel"](ed["img"])
            for ins in sorted(st.get("insert_scenes") or [], key=lambda x: -int(x["after"])):
                s["scenes"].insert(int(ins["after"]), dict(
                    img=cfg["_rel"](ins["img"]), en=ins.get("en", ""), zh=ins.get("zh", "")))
            for i, sc in enumerate(s["scenes"], 1):
                sc["no"] = i
            stories[st["file"]] = s
    return stories


def cmd_scan(a):
    cfg = load_book(a.book_dir)
    for ch in cfg["chapters"]:
        print(f"[chapter] {bi(ch.get('title'))[0]}")
        for st in ch["stories"]:
            ov = {int(k): v for k, v in (st.get("pages") or {}).items()}
            kinds, _ = classify(cfg["_rel"](st["file"]), ov)  # shows book.yaml overrides
            summary = " ".join(f"{p}:{k}" for p, k in kinds)
            print(f"  {st['file']}\n    {summary}")


def cmd_assemble(a):
    cfg = load_book(a.book_dir)
    out_dir = os.path.join(a.book_dir, "out")
    work = os.path.join(a.book_dir, ".build")
    os.makedirs(out_dir, exist_ok=True)
    stories = gather(cfg)
    for st in stories.values():
        dropped = [f"{p}({k[5:]})" for p, k in st["kinds"] if k.startswith("drop")]
        print(f"story {st['title']!r}: {len(st['scenes'])} scenes, "
              f"{len(st['designers'])} designer pages"
              + (f", dropped {', '.join(dropped)}" if dropped else ""))
    slug = slugify(bi(cfg.get("title"))[0] or os.path.basename(a.book_dir))
    for size in a.size or cfg.get("sizes") or ["letter", "digest"]:
        S = SIZES[size]
        book = Book(cfg, size)
        book.plan(stories)
        interior = os.path.join(out_dir, f"{slug}-{size}-interior.pdf")
        # Chrome runs out of memory on a ~130-page picture book in one go:
        # print in batches and join them
        from pypdf import PdfWriter as _PW
        parts, step = [], 30
        for st_ in range(1, len(book.pages) + 1, step):
            part = os.path.join(work, f"{slug}-{size}-part{st_:04d}.pdf")
            print_pdf(book.html(st_, st_ + step - 1), part, work)
            parts.append(part)
        merged = _PW()
        for part in parts:
            merged.append(part)
        with open(interior, "wb") as f:
            merged.write(f)
        for part in parts:
            os.remove(part)
        n = stamp_boxes(interior, S["w"], S["h"])
        art = {1: book.safe_w, 2: (book.safe_h - 0.2) / 2,
               4: min((book.safe_w - 0.22) / 2, (book.safe_h - 0.22) / 2 - 1.25)
               }[book.per_page]
        print(f"[{size}] {interior}: {n} pages (even: {n % 2 == 0}), "
              f"scene art {art:.2f}in -> {1024 / art:.0f}ppi for 1024px images")
        spine = a.spine if a.spine is not None else round(n * a.page_thickness, 3)
        html_text, PW, PH = cover_html(cfg, size, spine, n, best_ad(stories))
        cover = os.path.join(out_dir, f"{slug}-{size}-cover.pdf")
        print_pdf(html_text, cover, work)
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import RectangleObject
        r, w = PdfReader(cover), PdfWriter()
        b = BLEED * 72
        pg = r.pages[0]
        pg.mediabox = pg.cropbox = pg.bleedbox = RectangleObject([0, 0, PW * 72, PH * 72])
        pg.trimbox = RectangleObject([b, b, PW * 72 - b, PH * 72 - b])
        w.add_page(pg)
        with open(cover, "wb") as f:
            w.write(f)
        # the same cover as separate front / back / spine files (PDF + PNG)
        W = SIZES[size]["w"]
        parts = {"front": (W + spine, PW, True), "back": (0, W + 2 * BLEED, True),
                 "spine": (W + BLEED, W + BLEED + spine, False)}
        for part, (x0, x1, bleed_x) in parts.items():
            pg = PdfReader(cover).pages[0]
            X0, X1 = x0 * 72, x1 * 72
            pg.mediabox = pg.cropbox = pg.bleedbox = RectangleObject([X0, 0, X1, PH * 72])
            bx = b if bleed_x else 0
            pg.trimbox = RectangleObject([X0 + bx, b, X1 - bx, PH * 72 - b])
            pw = PdfWriter()
            pw.add_page(pg)
            stem = os.path.join(out_dir, f"{slug}-{size}-cover-{part}")
            with open(stem + ".pdf", "wb") as f:
                pw.write(f)
            sh(["pdftoppm", "-png", "-r", "300", "-singlefile", stem + ".pdf", stem])
        note = "" if a.spine is not None else \
            " (ESTIMATE -- rerun with --spine <Mixam cart value>)"
        print(f"[{size}] {cover}: spread {PW:.3f}x{PH:.3f}in, spine {spine}in{note}")


def cmd_portraits(a):
    """candidates/portraits/<Name>--ch<N>-<story>.jpg: each child's in-story
    character (the "In the Story" picture) from every designer page, plus a
    contact sheet, to choose author photos from."""
    from PIL import Image
    cfg = load_book(a.book_dir)
    stories = gather(cfg)
    out = os.path.join(a.book_dir, "candidates", "portraits")
    os.makedirs(out, exist_ok=True)
    made = []
    for ci, ch in enumerate(cfg["chapters"], 1):
        for st in ch["stories"]:
            for u in stories[st["file"]].get("units") or []:
                if not u["imgs"] or not u["words"] and len(u["imgs"]) != 1:
                    continue  # group drawings ("Farm") are not portraits
                pic = u["imgs"][1] if len(u["imgs"]) >= 2 else u["imgs"][0]
                name = re.sub(r"[^A-Za-z]", "", u["name"]).capitalize()
                dst = os.path.join(out, f"{name}--ch{ci}-{slugify(st['file'])[:30]}.jpg")
                Image.open(pic).convert("RGB").save(dst, quality=92)
                made.append(dst)
    contact_sheet(made, os.path.join(a.book_dir, "candidates", "portraits_sheet.jpg"))
    print(f"{len(made)} portraits -> {out}")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("init", "scan", "extract", "portraits", "assemble"):
        sp = sub.add_parser(name)
        sp.add_argument("book_dir")
        if name == "assemble":
            sp.add_argument("--size", action="append", choices=list(SIZES))
            sp.add_argument("--spine", type=float,
                            help="spine width in inches from Mixam's cart")
            sp.add_argument("--page-thickness", type=float, default=0.0035,
                            help="inches per interior page for the spine estimate")
    a = p.parse_args()
    if a.cmd != "init" and not os.path.isfile(os.path.join(a.book_dir, "book.yaml")):
        sys.exit(f"error: {a.book_dir}/book.yaml not found (run init first)")
    {"init": cmd_init, "scan": cmd_scan, "extract": cmd_extract,
     "portraits": cmd_portraits, "assemble": cmd_assemble}[a.cmd](a)


if __name__ == "__main__":
    main()
