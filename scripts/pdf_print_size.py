#!/usr/bin/env python3
"""Resize a PDF to a target print trim size, with text-safe measurement
and print-shop bleed generation.

Subcommands:
  inspect  IN                    -- page sizes, aspect vs target, image ppi
  measure  IN                    -- max text-safe side crop (fraction of width)
  convert  IN OUT --mode ...     -- lossless page-box transform (no re-encode)
  bleed    IN OUT                -- raster rebuild with white|extend bleed + TrimBox

Requires poppler (pdfinfo/pdfimages/pdftoppm) on PATH and a venv with
pypdf, pillow, img2pdf (see SKILL.md bootstrap).
"""
import argparse
import glob
import io
import os
import re
import subprocess
import sys
import tempfile


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def page_sizes(src):
    out = sh(["pdfinfo", "-f", "1", "-l", "99999", src]).stdout
    sizes = [(float(w), float(h)) for w, h in
             re.findall(r"Page +\d+ +size: +([\d.]+) x ([\d.]+)", out)]
    if not sizes:
        m = re.search(r"Page size: +([\d.]+) x ([\d.]+)", out)
        n = int(re.search(r"Pages: +(\d+)", out).group(1))
        sizes = [(float(m.group(1)), float(m.group(2)))] * n
    return sizes


def cmd_inspect(a):
    sizes = page_sizes(a.src)
    uniq = sorted(set(sizes))
    print(f"pages: {len(sizes)}")
    for w, h in uniq:
        n = sizes.count((w, h))
        print(f"  {n} pages @ {w:.0f}x{h:.0f}pt = {w/72:.2f}x{h/72:.2f}in "
              f"(aspect {w/h:.4f})")
    tw, th = a.width, a.height
    print(f"target: {tw}x{th}in (aspect {tw/th:.4f})")
    w, h = uniq[0]
    if abs((w/h) / (tw/th) - 1) < 0.005:
        print("aspect MATCHES target: plain uniform scale, no tradeoffs")
    else:
        fitw_h = tw * h / w
        print(f"aspect mismatch: fit-to-width leaves {(th-fitw_h):.2f}in "
              f"vertical gap (or crop {(th/ (h/w) - tw)/2:.2f}in per side, "
              f"or stretch {abs(th/fitw_h-1)*100:.1f}%)")
    print(sh(["pdfimages", "-list", "-f", "1", "-l", "3", a.src]).stdout)


TEXT_DARK, TEXT_BG = 100, 200


def _textish_count(im, blur, x_range):
    px, bx = im.load(), blur.load()
    return sum(1 for y in range(im.height) for x in x_range
               if px[x, y] < TEXT_DARK and bx[x, y] > TEXT_BG)


def _pages_with_text_near_edge(src, fx, fy=0.0):
    """Pages having text-like pixels within fx of the left/right edges
    (and fy of top/bottom), as fractions of width/height."""
    from PIL import Image, ImageFilter
    bad = []
    with tempfile.TemporaryDirectory() as td:
        sh(["pdftoppm", "-png", "-r", "20", src, os.path.join(td, "p")])
        for path in sorted(glob.glob(os.path.join(td, "p-*.png"))):
            im = Image.open(path).convert("L")
            blur = im.filter(ImageFilter.BoxBlur(8))
            w, h = im.size
            s, t = max(1, int(w * fx)), int(h * fy)
            px, bx = im.load(), blur.load()
            n = 0
            for y in range(h):
                for x in range(w):
                    if (x < s or x >= w - s or y < t or y >= h - t) and \
                            px[x, y] < TEXT_DARK and bx[x, y] > TEXT_BG:
                        n += 1
            if n > 5:
                bad.append(os.path.basename(path).split("-")[-1].split(".")[0])
    return bad


def cmd_measure(a):
    fractions = [0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05]
    safe = None
    for f in fractions:
        bad = _pages_with_text_near_edge(a.src, f)
        print(f"side crop {f*100:.1f}% of width: "
              f"{len(bad)} pages hit text {bad[:6]}")
        if not bad:
            safe = f
    print(f"max text-safe side crop: {safe*100 if safe else 0:.1f}% of width")
    print("NOTE: for trim printing keep text >=0.125in from the cut line -- "
          "prefer zero crop + stretch when margins are tight")


def cmd_convert(a):
    from pypdf import PdfReader, PdfWriter, Transformation
    TW, TH = a.width * 72, a.height * 72
    crop = a.crop_per_side * 72
    reader = PdfReader(a.src)
    writer = PdfWriter()
    stretch = 0
    for page in reader.pages:
        w, h = float(page.mediabox.width), float(page.mediabox.height)
        if a.mode == "fit":
            s = min(TW / w, TH / h)
            sx = sy = s
            tx, ty = (TW - w * s) / 2, (TH - h * s) / 2
        elif a.mode == "fill":
            s = max(TW / w, TH / h)
            sx = sy = s
            tx, ty = (TW - w * s) / 2, (TH - h * s) / 2
        elif a.mode == "stretch":
            sx, sy, tx, ty = TW / w, TH / h, 0, 0
        else:  # hybrid: crop N in per side, stretch the rest vertically
            sx, sy = (TW + 2 * crop) / w, TH / h
            tx, ty = -crop, 0
        stretch = max(stretch, abs(sy / sx - 1) * 100)
        page.add_transformation(Transformation().scale(sx, sy).translate(tx, ty))
        for box in (page.mediabox, page.cropbox):
            box.lower_left = (0, 0)
            box.upper_right = (TW, TH)
        writer.add_page(page)
    with open(a.dst, "wb") as f:
        writer.write(f)
    print(f"wrote {a.dst}: {len(writer.pages)} pages @ {a.width}x{a.height}in, "
          f"mode={a.mode}, max stretch {stretch:.1f}% (lossless, no re-encode)")


def _extract_or_render(src, ppi, td):
    """One raster image per page. Lossless pdfimages extraction when every
    page is a single full-page image; otherwise render at target ppi."""
    n_pages = len(page_sizes(src))
    listing = sh(["pdfimages", "-list", src]).stdout.splitlines()[2:]
    per_page = {}
    for line in listing:
        parts = line.split()
        if parts:
            per_page[parts[0]] = per_page.get(parts[0], 0) + 1
    if len(per_page) == n_pages and all(v == 1 for v in per_page.values()):
        sh(["pdfimages", "-all", src, os.path.join(td, "x")])
        files = sorted(glob.glob(os.path.join(td, "x-*")))
        if len(files) == n_pages:
            print("using lossless per-page image extraction")
            return files
    print(f"rendering pages at {ppi}ppi (multi-object or vector pages)")
    sh(["pdftoppm", "-jpeg", "-jpegopt", "quality=95", "-r", str(ppi),
        src, os.path.join(td, "r")])
    return sorted(glob.glob(os.path.join(td, "r-*.jpg")))


def cmd_bleed(a):
    from PIL import Image
    import img2pdf
    from pypdf import PdfReader, PdfWriter
    ppi = a.ppi
    TW, TH = round(a.width * ppi), round(a.height * ppi)
    B = round(a.bleed * ppi)
    PW, PH = TW + 2 * B, TH + 2 * B
    crop_frac = a.crop_per_side / a.width
    jpegs = []
    with tempfile.TemporaryDirectory() as td:
        for path in _extract_or_render(a.src, ppi, td):
            im = Image.open(path).convert("RGB")
            cw = round(im.width * crop_frac)
            if cw:
                im = im.crop((cw, 0, im.width - cw, im.height))
            im = im.resize((TW, TH), Image.LANCZOS)
            canvas = Image.new("RGB", (PW, PH), "white")
            canvas.paste(im, (B, B))
            if a.bleed_style == "extend":
                # Pixel-smear the outer row/col outward. NEVER mirror:
                # mirroring puts ghost text in the bleed zone when content
                # runs near trim.
                canvas.paste(im.crop((0, 0, 1, TH)).resize(
                    (B, TH), Image.NEAREST), (0, B))
                canvas.paste(im.crop((TW - 1, 0, TW, TH)).resize(
                    (B, TH), Image.NEAREST), (TW + B, B))
                canvas.paste(canvas.crop((0, B, PW, B + 1)).resize(
                    (PW, B), Image.NEAREST), (0, 0))
                canvas.paste(canvas.crop((0, PH - B - 1, PW, PH - B)).resize(
                    (PW, B), Image.NEAREST), (0, PH - B))
            buf = io.BytesIO()
            canvas.save(buf, "JPEG", quality=95, dpi=(ppi, ppi))
            jpegs.append(buf.getvalue())
    page_pts = (img2pdf.in_to_pt(a.width + 2 * a.bleed),
                img2pdf.in_to_pt(a.height + 2 * a.bleed))
    pdf = img2pdf.convert(jpegs, layout_fun=img2pdf.get_layout_fun(page_pts))
    reader = PdfReader(io.BytesIO(pdf))
    writer = PdfWriter()
    bpt = a.bleed * 72
    for page in reader.pages:
        page.trimbox.lower_left = (bpt, bpt)
        page.trimbox.upper_right = (float(page.mediabox.width) - bpt,
                                    float(page.mediabox.height) - bpt)
        writer.add_page(page)
    with open(a.dst, "wb") as f:
        writer.write(f)
    print(f"wrote {a.dst}: {len(jpegs)} pages, page "
          f"{a.width + 2*a.bleed}x{a.height + 2*a.bleed}in "
          f"(trim {a.width}x{a.height} + {a.bleed}in {a.bleed_style} bleed) "
          f"@ {ppi}ppi")
    if a.quiet_area > 0:
        # Content shown at trim maps linearly from the source page, so the
        # quiet area is the same FRACTION of source width/height.
        eff_w = a.width + 2 * a.crop_per_side
        bad = _pages_with_text_near_edge(a.src, a.quiet_area / eff_w,
                                         a.quiet_area / a.height)
        if bad:
            print(f"WARNING: text inside the {a.quiet_area}in quiet/safe "
                  f"area on {len(bad)} pages: {bad}")
            print("  The printer may flag these; fixing requires layout "
                  "changes in the source, not conversion settings.")
        else:
            print(f"quiet-area check: no text within {a.quiet_area}in of "
                  "the trim line on any page")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, dst=False):
        sp.add_argument("src")
        if dst:
            sp.add_argument("dst")
        sp.add_argument("--width", type=float, default=5.5)
        sp.add_argument("--height", type=float, default=8.5)

    common(sub.add_parser("inspect"))
    common(sub.add_parser("measure"))
    c = sub.add_parser("convert")
    common(c, dst=True)
    c.add_argument("--mode", choices=["fit", "fill", "stretch", "hybrid"],
                   default="fit")
    c.add_argument("--crop-per-side", type=float, default=0.0,
                   help="inches cropped per side (hybrid mode)")
    b = sub.add_parser("bleed")
    common(b, dst=True)
    b.add_argument("--bleed", type=float, default=0.125)
    b.add_argument("--ppi", type=int, default=400)
    b.add_argument("--crop-per-side", type=float, default=0.0)
    b.add_argument("--bleed-style", choices=["white", "extend"],
                   default="white",
                   help="white: blank bleed zone (user's preference); "
                        "extend: smear edge pixels outward")
    b.add_argument("--quiet-area", type=float, default=0.25,
                   help="warn if text sits within this many inches of the "
                        "trim line (0 disables)")
    a = p.parse_args()
    if not os.path.isfile(a.src):
        sys.exit(f"error: source PDF not found: {a.src}")
    {"inspect": cmd_inspect, "measure": cmd_measure,
     "convert": cmd_convert, "bleed": cmd_bleed}[a.cmd](a)


if __name__ == "__main__":
    main()
