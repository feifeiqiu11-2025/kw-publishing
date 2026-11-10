---
name: kw-publishing
description: Make a printed KindleWood book. First ask - classroom story book or single-author book? Both use the same book path and rules. (1) Story-collection class book - onboard the teacher (story PDFs per chapter, curriculum, class emails, teachers' and children's names, cover) and build a Mixam perfect-bound anthology - finished or composed cover, About This Book, Meet Our Young Authors, one-page contents, chapters of flowing 4-per-page numbered scenes with re-typeset character designer cards, Keep Imagining, KindleWood back cover - following the approved rules in book-rules.md. (1b) Single-author book - one child's story (e.g. a gift book for Mom) with the same front matter, Meet the Author page, zigzag 2-per-page whole pictures, story-only contents. (2) Single PDF -> print (only when the user explicitly asks for a plain resize) - resize one PDF to a trim size, quality check, and print-shop bleed. Use when the user wants to make/print/publish a book, combine stories into a book, convert a PDF for Mixam or KDP, or fix a "missing bleed" preflight warning.
---

# KindleWood Publishing

**First question, every time someone hands over story PDFs** (AskUserQuestion,
before anything else): *"Is this a classroom story book (many children) or a
single-author book (one child's story)?"*

- **A. Classroom story book.** Many KindleWood story PDFs become one printed
  class book. Run the **guided interview below**.
- **A1. Single-author book.** One child's story (or a few by the same child)
  printed as a real book. It runs the **same guided interview and the same
  rules**; only the differences in "A1. Single-author book" below change.
- **B. Single PDF to print.** Resize one finished PDF and add bleed, with no
  book pages added. Use it **only when the user explicitly asks for a plain
  resize**. A PDF that will be printed as a book goes through A or A1. See
  "Single PDF -> print trim size" further down.

Setup (both jobs). This needs poppler (`pdfinfo`/`pdfimages`/`pdftoppm`),
Google Chrome, and this venv:

```bash
SKILL=~/.claude/skills/kw-publishing
[ -x $SKILL/scripts/.venv/bin/python ] || python3 -m venv $SKILL/scripts/.venv
PY=$SKILL/scripts/.venv/bin/python
# always `$PY -m pip` -- the venv's bin/pip shebang is stale (old skill path)
$PY -c "import pypdf, PIL, img2pdf, yaml" 2>/dev/null || \
  $PY -m pip -q install pypdf pillow img2pdf pyyaml
BA="$PY $SKILL/scripts/book_assemble.py"
```

---

# A. Story-collection book: onboarding + build

**Read [book-rules.md](book-rules.md) first.** It holds every layout and
content decision the teacher has approved. They are the defaults, so don't
ask about them again unless the teacher wants a change. Technical details
are in [book-assembly.md](book-assembly.md); background choices are in
[background-library.md](background-library.md).

How to run it:
- Go through the steps **in order, one step per turn**. Ask with
  **AskUserQuestion** wherever there are choices, putting the default first
  and marking it "(Recommended)". Free text (titles, emails, notes) is
  asked for in plain chat.
- Never ask for something the conversation or `book.yaml` already answers.
  "Use defaults" or "you decide" means: take the defaults and keep going.
- After each step, write the answers into `BOOK_DIR/book.yaml` (format:
  [book.template.yaml](book.template.yaml)) so the book can be resumed or rebuilt.

## Step 0: welcome + what to prepare

Send this checklist in the first message. The teacher can gather it all at
once or answer step by step:

> To make your class book I'll need:
> 1. **Story PDFs**: export each story from KindleWood (Classic layout), one PDF
>    per story, in folders named `Chapter 1`, `Chapter 2`, … (one per class theme)
> 2. **Curriculum / chapter themes**: the topic names in order (a table or list is fine)
> 3. **Class emails or notes**: we summarize them into "About This Book"
> 4. **Teachers' names** for the signature
> 5. **School / class name**: printed as "Created by ___ Storytellers" on the cover
> 6. **Children's names**, spelled the way they should be printed
> 7. **Front cover**: a finished cover image if you have one, or the kids'
>    character pictures and a few scene pictures for us to compose one
> 8. *(optional)* a short note about each child, and any caption fixes
>
> Not ready with everything? No problem. We can start with Chapters 1-2 and add the rest later.

Then create the folder: the default is `~/Documents/KindleWood Books/<book name>/`,
or the folder the teacher already uses. If no `book.yaml` exists there yet,
run `$BA init BOOK_DIR`. Point `chapters[].dir` at the teacher's own
`Chapter N` folders instead of moving their files.

## Step 1: stories + chapters
1. Get the chapter titles from the curriculum (English is what gets printed;
   polish them lightly and say so). Story order defaults to alphabetical by
   file name; ask whether that is fine.
2. Run `$BA scan BOOK_DIR` and report each story in one line: scenes,
   designer pages, and what gets dropped (QR, app-promo and blank pages).
   Look into anything odd: a story with 0 scenes, a designer page marked as
   dropped, or a child whose "Own Words" are missing. Use `pages:` overrides,
   or ask the teacher for the missing words (`designer_words`).
3. **Build only Chapters 1-2 first** (rule 32) unless the teacher wants it all.

## Step 2: title + cover
- **Book title** (English; Chinese is optional) and the **school/class
  name** (`school`). The footer is fixed: "Created by <school> Storytellers"
  over "© Powered by KindleWood Studio". Never put children's names on the cover.
- **Front cover:** "I have a finished cover image" (Recommended when one
  exists): save it as `cover/front.png` with `cover.front_image`, used as is.
  Otherwise "Compose one for me": read [cover-example.md](cover-example.md),
  pick a background from the catalog, and use the characters and scenes the
  teacher provided (or `$BA extract`: propose about 6-8 characters and up to
  6 scenes, never anything LOW-RES).
- **Back cover:** the KindleWood Families page, as is. Mention the © year printed on it.

## Step 3: About This Book
- Get the class emails or notes (any language) and the curriculum. Save a
  summary of the sources in `about-book/emails/`.
- Draft 120-200 warm words: what the children explored, how they grew, and
  that every idea is theirs. Also write a natural 中文 version, not a
  word-for-word translation. Show both and revise until approved.
- **Teachers' names** for the signature (signature font, e.g. "Teacher A, B & C").
- **Language:** bilingual if it fits on one page, otherwise English only
  (keep the Chinese commented out in book.yaml).

## Step 4: Meet Our Young Authors
- **Names** as they should be printed. Start from the bylines and flag spelling
  mismatches across stories (rule 28).
- **Portraits:** "Their in-story character" (Recommended). Run
  `$BA portraits BOOK_DIR` and send `candidates/portraits_sheet.jpg`. Ask
  which chapter to use, plus any per-child exceptions, then copy the picks
  to `authors/photos/<Name>.jpg`. The other options are "Upload real photos"
  and "No photos".
- **Notes** (optional, one or two sentences per child). Without notes, every
  child fits on one page.
- **Privacy:** when real photos or full names are used, ask: "Do parents
  agree to printing their child's photo and name?"

## Step 5: backgrounds + Keep Imagining
- Send `assets/backgrounds/catalog.jpg`. Ask for one template each for
  **About, Authors, Contents, Keep Imagining**, all different (rule 17).
  The answer "You pick" is fine; then choose frames whose decorations stay
  clear of the text. Copy the picks into the book and record
  `background_choices`.
- **Keep Imagining:** show the default wording (rule 30) and ask whether to
  change it. The teacher can also supply extra Story Idea prompts.

## Step 6: size + layout
| option | trim | layout | art prints at |
|---|---|---|---|
| **Letter** (Recommended) | 8.5 x 11in | 4 scenes/page, flowing (book-rules 19-24) | ~276ppi |
| Digest | 5.5 x 8.5in | 1 scene/page | ~217ppi |
| A5 | 5.83 x 8.27in | 1 scene/page | ~205ppi |

Defaults: `scenes_per_page: 4` and `scene_numbers: true`. To try a new
style on one story first, use `scene_numbers: first-story`.

## Step 7: build, check, review
1. `$BA assemble BOOK_DIR --size letter`. A full book takes about a minute;
   it is printed in batches.
2. **MANDATORY check** before showing the teacher (book-assembly.md "Verify"):
   a contact sheet of every page, close-ups of the front matter, a designer
   row and a scene page, the cover parts, and `pdfinfo -box`.
3. Open the PDF for the teacher and iterate. Typical requests and where they go:
   - caption fix → `scene_edits` (exported scene number)
   - new picture → `insert_scenes` (`after:` exported number; save the image in `inserts/`)
   - missing "Own Words" → `designer_words`
   - wrong page type → `pages:`
   These all go in the chapter's `overrides: {"<file>.pdf": {...}}`.
4. When the teacher approves Chapters 1-2, add the remaining chapters the same way.

## Step 8: order at Mixam
- What to order: **Paperback, Perfect bound**, the size, and the interior
  page count (printed by assemble; always even). The cover is a separate upload.
- Ask the teacher to add the book to the Mixam cart and read the **spine
  width**. Then rebuild with `--spine <inches>`.
- Upload `out/<slug>-<size>-interior.pdf` and `out/<slug>-<size>-cover.pdf`.
  The separate `-cover-front/-back/-spine` PDFs and PNGs are for other uses.
  A ~130-page interior is about 230 MB, so the upload takes a few minutes.

---

# A1. Single-author book: what changes

Worked out on *Mom, I Love You Forever* (Alice, age 6; Letter hardcover,
Nov 2026). Everything in A and book-rules.md still applies (front matter,
backgrounds, no blank pages, Keep Imagining, the standard back cover, never
rewriting the child's words). Only these change; set them in `book.yaml`:

| topic | classroom (A) | single-author (A1) |
|---|---|---|
| Step 0 checklist | class emails, teachers, school, children's names | notes about how the child made the book, who signs About (e.g. "Mom & Dad"), the child's name and age as printed, optional bio |
| layout | `scenes_per_page: 4` (flowing 2x2) | `scenes_per_page: 2` (zigzag rows: picture and caption swap sides row by row) |
| pictures | square crop (KindleWood 1024px art) | `scene_fit: contain`: each picture whole at its own aspect, with an equal visual area so tall, wide and square pictures read as one size |
| photo edges | n/a | trim plain photo backgrounds/paper with `scripts/scene_trim.py`, review every picture by eye, keep any picture whose key visual reaches the edge untrimmed; wire the trimmed copies in with `scene_images` |
| chapters | "Chapter N" kicker + chapter rows in contents | `single_chapter: true`: contents lists "Story 1: <title> By <byline>", the opener has no chapter label |
| opener | 5.5in art | `opener_art: 6.6` (bigger story-cover picture) |
| authors page | "Meet Our Young Authors" portrait grid | automatic with one author: "Meet the Author" (`authors.heading`), a 2.4in photo top-left with the name under it, the rest of the page left for a short bio (`note`, written by the family, never invented) |
| photo | in-story character | the child's in-story character, a real photo, or a crop of the child's own cover drawing |
| cover footer | "Created by <school> Storytellers" | `school: ""` (credit only) unless the family names one |
| byline page | n/a | drop the export's "By <name>" scene page (it repeats the cover) with `pages: {2: "drop:extra"}` |

Source PDF notes for one-child books:
- **Photo-page stories** (real artwork photos, 1190x896 or 896x1190) are not
  square, so `scan` calls them "designer". Force them with
  `pages: {3: scene, ...}` and mark the KindleWood page `ad`.
- **Check the export before building**: duplicate scenes (prod can hold
  duplicate scene rows), captions that spill onto an extra page, and a blank
  last page all mean the export is broken. Re-export it clean (see
  book-assembly.md "Clean re-export") rather than patching pages.
- **Hardcover (casebound):** the interior is the same file. The cover
  builder still makes the paperback spread (0.125in bleed, page-count spine
  estimate); a casebound case needs 0.8in wrap + 0.2in hinges and Mixam's
  spine value, so say so and don't ship the paperback spread as a case.

Example: `~/Documents/KindleWood Books/Mom, I Love You Forever/book.yaml`.

---

# B. Single PDF -> print trim size

Converts an arbitrary PDF (typically an image-per-page picture book) to a
target trim size with the least-destructive geometry, and optionally makes a
print-shop-ready file with white bleed. Commands: `scripts/pdf_print_size.py`.

## Workflow

### 1. Inspect

```bash
$PY $SKILL/scripts/pdf_print_size.py inspect IN.pdf --width 5.5 --height 8.5
```

Reports page sizes, aspect vs target, and embedded-image ppi. If aspect
matches within 0.5%, a plain `convert --mode fit` is perfect — skip to
step 4. Quality rule of thumb: effective ppi at target size >= 300 is
print-grade (embedded px width / target inches).

### 2. Measure text-safe margins (only if aspect mismatches)

```bash
$PY $SKILL/scripts/pdf_print_size.py measure IN.pdf
```

Finds how much of the width can be cropped per side before hitting text
(dark-pixels-on-white heuristic over all pages).

### 3. Choose geometry — decision rules learned the hard way

- **Digital/PDF-only delivery** (no physical trimming):
  - White-backed pages, gap tolerable -> `convert --mode fit` (lossless,
    white bands read as margins).
  - No white bands wanted -> `convert --mode hybrid --crop-per-side <safe>`
    where `<safe>` is just under the measured limit; remaining stretch
    should stay <= ~6%.
- **Physical printing (print shop / KDP, anything that gets trimmed)**:
  - Use `bleed` mode. Default to `--crop-per-side 0`: cutters wander
    +-1/16in, so text must keep >= 0.125in from the trim line. Cropping up
    to the measured text limit puts text ON the cut line — letters get
    shaved. A larger vertical stretch (even ~9%) is safer and less
    noticeable than clipped text on illustrated content.
  - Only crop sides if measured margins leave >= 0.125in AFTER the crop.

Never use `--mode stretch`/vertical stretch above ~10% distortion; prefer
`fit` with bands and tell the user.

### 4. Convert

```bash
# lossless page-box transform (fit | fill | stretch | hybrid):
$PY $SKILL/scripts/pdf_print_size.py convert IN.pdf OUT.pdf \
    --width 5.5 --height 8.5 --mode fit

# print-shop file: trim + white bleed + TrimBox (fixes "missing bleed"):
$PY $SKILL/scripts/pdf_print_size.py bleed IN.pdf OUT_bleed.pdf \
    --width 5.5 --height 8.5 --bleed 0.125
```

`convert` never re-encodes images (zero quality loss). `bleed` re-rasters
once at 400ppi/JPEG-q95 (visually lossless, well above the 300ppi print
standard); it extracts original JPEGs losslessly when pages are single
full-page images, else renders.

Bleed zone content (`--bleed-style`):
- `white` (DEFAULT — the user's explicit preference): blank bleed zone.
  Honest trade-off to mention: where art runs edge-to-edge, an outward-
  drifting cut can leave a hairline white edge.
- `extend`: smear the outermost pixel row outward (hides that hairline).
- NEVER mirror the edges: mirrored bleed puts readable ghost text in the
  bleed zone when text runs near the trim line (user caught this in a
  Mixam preview).

The bleed command also auto-warns (--quiet-area, default 0.25in) listing
every page with text inside the printer's quiet/safe area — report these
to the user instead of silently shipping; fixing them is a source-layout
decision, not a conversion setting.

### 5. Verify with previews — MANDATORY, this catches real bugs

```bash
pdftoppm -png -r 40 -f <n> -l <n> OUT.pdf /path/to/scratch/prev
```

Render and LOOK AT (Read tool) at least: page 1, one text-heavy page, one
page whose art bleeds to the edges. Check: no clipped letters near edges,
text keeps visible margin from the trim line (bleed mode), faces/shapes
not noticeably distorted, `pdfinfo` shows the exact expected page size.
In past runs previews caught text clipped by a "safe" crop twice.

### 6. Report to user

State: original vs new dimensions, which geometry was used and why, crop/
stretch amounts, effective ppi vs the 300 print standard, and (for shops)
that the file is trim+bleed with TrimBox set. KDP note: KDP wants bleed on
3 sides only (not the gutter) at 0.125in — the 4-side file is normally
accepted, but mention it.

## KindleWood book -> Mixam: THE settled recipe (2026-08)

For a KindleWood app export headed to Mixam, skip the decision tree — this
was worked out end-to-end on TwoNinjas_1.pdf:

1. User exports **A4 page size** (any layout — Classic/Comic/Grid). A4
   exports are A-series ratio at ~2380x3368px per page. Do NOT target
   Digest 5.5x8.5 (9.2% stretch); the book is printed as **A5** (same
   ratio -> zero distortion, ~400ppi).
2. One command:
   `$PY $SKILL/scripts/pdf_print_size.py bleed IN.pdf OUT_A5_bleed.pdf --width 5.827 --height 8.268`
   (A5 trim 148x210mm + default 0.125in white bleed + quiet-area check.)
3. Render 2-3 preview pages, Read them, confirm no clipping/distortion.
4. Expect the quiet-area warning (KindleWood text sits ~0.11in from trim);
   relay it — it's advisory, letters are beyond cutter drift. Permanent
   fix = print-ready export option in the app (text >=0.25in inside trim),
   planned but not built.
5. User sets the Mixam order size to **A5** and uploads.

## Publisher preset: Mixam (mixam.com) — the user's current printer

Verified 2026-08 from mixam.com/support/filesetup + /support/bleed:

- Inner pages: single-page PDF (not spreads), 300dpi min, **0.125in bleed
  on all four sides** -> the default `bleed` command output is correct.
- **Quiet/safe area: 0.25in inside trim** (0.5in at the bound/spine edge
  for perfect-bound). KindleWood exports have text as close as ~0.11in to
  trim — Mixam may warn; the text placement is inherent to the layout, so
  tell the user rather than crop/shrink (shrinking content is a design
  decision, not a conversion step).
- Cover: separate artwork — paperback perfect-bound wants ONE spread PDF
  (back + spine + front) at 300dpi; spine needs 0.125in bleed top/bottom.
  Hardcover covers need 0.8in wrap bleed and 0.2in hinge each side of the
  spine. Spine width depends on page count/paper — get it from Mixam's
  product page calculator before building a cover.
- Page-count rules: saddle-stitch needs a multiple of 4 pages; perfect
  bound needs an even count. Check and warn (e.g. 42 pages = perfect-bound
  OK, saddle-stitch needs 44).
