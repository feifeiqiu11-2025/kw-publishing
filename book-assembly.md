# Story-collection book assembly (built 2026-11)

A class anthology made from many KindleWood story exports, printed at
Mixam as a **perfect-bound paperback**. The *what* (the approved design rules)
is in [book-rules.md](book-rules.md); this file is the *how*.

| size | trim | scenes per page | 1024px art prints at |
|---|---|---|---|
| `letter` | 8.5 x 11in | default `scenes_per_page: 4` = flowing half-page rows (see Flow layout). `2` = older "zigzag" rows, one story per page run | 4: 3.71in -> ~276ppi; 2: 5.0in -> ~205ppi |
| `digest` | 5.5 x 8.5in (half letter) | 1 (art on top, caption below) | 4.72in -> ~217ppi |
| `a5` | 5.83 x 8.27in | 1 (art on top, caption below) | 5.05in -> ~203ppi |

Both sizes were checked against mixam.com/paperbackbooks. Every page gets
0.125in bleed plus TrimBox/BleedBox. Margins are kept tight (the user
does not want much white space): outer 0.28-0.3in (just past Mixam's 0.25in
quiet area), gutter 0.5-0.55in on the binding side (Mixam asks 0.5in),
alternating sides on odd and even pages.

## Book folder

```
BOOK_DIR/
  book.yaml                 everything is configured here (see book.template.yaml)
  Chapter 1/ …              the teacher's own story folders (chapters[].dir points here),
                            or chapters/NN-theme/ from `init`; one PDF per story
  cover/front.png           a finished front cover (cover.front_image), or:
  cover/background.png, cover/characters/, cover/scenes/   parts for a composed cover
  about-book/background.png, about-book/emails/   class emails / source notes
  authors/background.png, authors/photos/<Name>.jpg
  contents/background.png
  imagine/background.png
  inserts/                  teacher-supplied scene pictures (insert_scenes)
  candidates/               extract / portraits output to choose from
  out/                      <slug>-<size>-interior.pdf, -cover.pdf,
                            -cover-front/-back/-spine .pdf + .png
```

## Flow layout (`scenes_per_page: 4`, the default for class books)

Pages are built from **half-page rows**. Each chapter starts on a new page,
but stories inside a chapter run on, so there are no half-empty pages:
- **story opener** = 1 row: cover art on one side (it alternates), and the
  kicker, a "Story N" pill, the title and the byline on the other
- **designer cards** = 1 row per 2-3 children (`pack_units`: 3 when every
  text is ≤6 lines). Pages are **re-typeset** rather than pasted as images:
  `designer_units()` crops each picture from a 300ppi render at the position
  the PDF gives (`_draw_boxes`, which follows form XObjects), reads the name
  caption and the "In X's Own Words" text (`_text_blocks`), and rebuilds
  them as cards in the book fonts. A lone card with words lays out sideways;
  a lone group drawing ("Farm") spans the row.
  Card layout per row: `card_weights()` gives a drawing-pair card 1.6x the
  width of a text-free standing child next to it; `stack_pair()` estimates
  the picture size of the pair stacked vs side by side from the card width
  and the height its text leaves, and tags the card `stk` or `sbs`.
  "Own Words" attach to the child's exact-name card first, so they never
  land on a "<Child>'s Rescue Mission" drawing card.
- **scenes** = 2 per row (zigzag cells). A story's odd last scene gets a
  **Spark cell**: a blue-line pose from `assets/spark/` plus an encouraging
  line (`FILLERS`, rotated).
- A chapter's half-filled last page is closed with a wide Spark row.
- Authors with no notes become a **portrait grid** (round crops of the
  character art, 20 per page).

## Book order (interior)

1. About This Book: text straight on the background art, English (+ 中文 when
   `text_zh` is set and fits), signed in the signature font (`fonts.signature`)
2. Meet Our Young Authors, **English only**. Without notes, it is a round
   portrait grid (20 per page). With notes, it is up to 10 per page in 2
   columns x 5 rows, each a small round photo with the name underneath and
   the note wrapping around it.
3. Contents, **English only**: ONE page listing chapters, their stories with
   page numbers, and Keep Imagining!. There are no per-chapter contents pages
   (the user dropped them), so the book goes straight into Chapter 1, Story 1.
4. The chapters, laid out as in Flow layout above (letter, 4 per page). With
   1 or 2 per page, each story instead gets a full-page opener, then pasted
   designer pages (trimmed and packed when they stay ≥62% size,
   `DESIGNER_MIN_SCALE`), then its scenes.
5. Keep Imagining!, **English only**: "Congratulations on your writing journey,
   we are so proud of you! ... your stories and your voice matter.", then
   "What are you going to draw and write next?", a dashed drawing box,
   writing lines, and Spark writing at a desk in the bottom-right corner
   (`assets/spark-writing.png`, the blue-line Spark with quill + open book the user supplied)
6. If the page count is odd, a **Story Idea** page (a different prompt from
   `EXTRA_PROMPTS` or `imagine.extra_prompts`, plus a drawing box and Spark).
   The user never wants blank pages.

The cover is a separate file: one spread (back + spine + front) with bleed
all around. **The back cover defaults to the KindleWood Families page**:
whichever story export has the highest-resolution version of it is
rendered, its white margins are trimmed, and it is fitted on white. Use
`back_cover.image` only to override that. That page is no longer
included inside the book (`kindlewood_page: true` adds it back).

## Defaults that need no teacher input

- Any `background` that is missing or set to `auto` gets a generated soft pastel
  backdrop (`auto_bg`, cached in `.build/bg-*.jpg`). This applies to the cover,
  About and Imagine pages.
- When `book.yaml` has no `cover:` section, the cover uses `cover/characters/` and
  `cover/scenes/`.
- The back cover is the KindleWood Families page.

## `extract` (picking cover / author images from the stories)

`$BA extract BOOK_DIR` writes `candidates/` with:
- `characters/`: the in-story character art from the designer pages. On those
  pages the smaller images are the story characters and the large photos are
  the kids' drawings. Each character also gets a `-cutout.png` with its plain
  light background flood-filled to transparent. The cut-out is clean when the
  background is plain cream or white, but keeps the box when the background is
  coloured or textured.
- `drawings/`: photos of the kids' original drawings
- `scenes/`: every story scene. `story-covers/`: each story's cover art.
- `*_sheet.jpg`: contact sheets labelled with filename and pixel size, with
  **LOW-RES** in red under 700px. Never put a LOW-RES image on the cover.

Names come from the quoted names on a designer page (“Sam”). If the counts
don't match, files are numbered instead and you identify them by eye.

## Claude's jobs before `assemble` (see SKILL.md onboarding)

- **About the Book:** read `about-book/emails/*.txt` and draft a warm note
  (about 120-200 words) on what the book means, plus a natural Chinese
  version. Do not translate word for word. Show the draft to the teacher
  and only then put it into `about_book.text_en` / `text_zh`. If both don't
  fit on one page, go English only and keep the Chinese commented out.
- **Teacher edits:** `scene_edits` / `insert_scenes` / `designer_words` /
  `pages` / `title` go under the chapter's `overrides: {"<file>.pdf": …}`.
  Scene numbers in them are the **exported** numbers (before any inserts).
- **Author notes:** English only, one or two sentences per child, written
  by the teacher. Polish the wording lightly, but do not translate.
- **Chapter titles:** English is what gets printed (contents page and story openers).
- **Story titles:** the default title is the PDF filename, so set `title:`
  for each story when filenames repeat (e.g. "This Is Me!" by several
  groups).

## How story PDFs are parsed (`scan` shows the result)

Exports are 7 x 8.5in react-pdf files. `classify()` labels each page:
- page 1 = **cover** (square art, and the "By ..." text becomes the byline)
- **scene** = exactly one square image of 512px or more, plus text. The
  image is extracted losslessly. In the caption text, lines containing CJK
  characters become 中文, the rest English, and page-number lines are dropped.
- pages with text before the first scene = **designer** pages, rendered at 300ppi
- pages with images but no text before the first scene = **QR page**, dropped
- pages with no images and no text = **blank**, dropped
- a page whose text says "Meet the Character" or "Own Words" is always a
  designer page, even when it holds one square character image (newer
  exports with "In Sam's Own Words" pages)
- a "Scan the QR code" block printed at the bottom of a designer page (wide
  banner and/or non-1024 square images in the lower half) is whited out,
  and the page is trimmed (`_qr_top`)
- the page with images but no text after the last scene = the **ad** page
  (only one is used, at the back of the book)

If a page is misclassified, override it per story in book.yaml:
`pages: {4: designer, 7: "drop:extra"}`. With auto-discovered chapters
(`dir:`), put per-story settings under the chapter's
`overrides: {"<file>.pdf": {title:, pages:, designer_words:}}`.
`designer_words: {Sam: [lines]}` supplies "Own Words" text an export is
missing (KindleWood sometimes exports only the name).

Text that overlaps a designer picture's box is whited out before the
picture is cropped, so stray words never end up inside a card.

**No CSS shadows anywhere**: Mac Preview draws box-shadow / drop-shadow as a
solid gray rectangle behind the element.

## Fonts (user-approved 2026-11)

- English: **Chalkboard SE**, a built-in Mac font that is comic-style but readable
- Chinese, titles AND captions: **ZCOOL KuaiLe** (站酷快乐体), bundled in `fonts/` under the OFL licence.
  The user picked it to try out. KuaiLe draws some characters in non-standard
  shapes (e.g. 我), so `fonts: {zh_body: "PingFang SC"}` switches captions back
  to standard character shapes.

To override, set `fonts: {en, zh_heading, zh_body}` in book.yaml. To add a
bundled font, put the TTF in `fonts/` and add it to `BUNDLED_FONTS`. The
fonts are embedded as **data URIs with `format("truetype")`**, and the
page waits for `document.fonts.load()` of every family before the fit
pass. Loading them through file:// URLs silently fell back to the regular
weight in headless Chrome.

## Rendering

HTML/CSS goes through headless Chrome `--print-to-pdf`, then pypdf
stamps the page boxes. The interior is printed in **batches of 30 pages**
and merged: one Chrome run over a ~130-page picture book crashes (renderer
out of memory). Story art extracted as PNG is re-saved as JPEG q95 first,
because Chrome embeds PNGs uncompressed. The contents is always one page:
the list shrinks to fit.

QR blocks are found by what only they have: a wide "Scan the QR code" banner
image, or "Scan… / Download Mobile App / iOS / Android" text. Square QR and
dragon images next to that anchor are cut too. Image size alone is no proof:
kids' art can be 1254px square like a QR code. A page whose only text is the
app promo is classified `drop:qr`. Chrome embeds PingFang as Type 3; Mixam accepts
that, but if preflight ever complains, switch the captions to a bundled
Noto Sans SC.
Captions shrink to fit through a `.fit` JS pass, so long sentences never
overflow. That overflow was a bug in the hand-made zigzag sample.

## Single-author settings (SKILL.md A1)

| book.yaml | effect |
|---|---|
| `scenes_per_page: 2` | zigzag rows, one scene per half page; picture and caption swap sides; numbered badge + pastel caption card |
| `scene_fit: contain` | pictures shown whole at their own aspect (default `cover` = square crop). Zigzag pictures get an equal visual area: area = 0.75 x box W x box H, box = 64% of safe width x row height |
| `single_chapter: true` | no "Chapter N" kicker on the opener; contents rows read "Story N: <title> <byline>" |
| `opener_art: 6.6` | story-opener picture size in inches (default 5.5 on Letter) |
| `authors.heading` | page title; with exactly one author the page switches to the solo layout (2.4in photo top-left, name under it, bio area) and defaults to "Meet the Author" |
| `caption_lines: keep` | print captions with the author's own line breaks (one rhyme line per line; EN + 中文). Needs a clean export, whose text lines ARE the author's lines; the zigzag picture then takes 52% of the width (`zigzag_art_share` to tune) and captions print at .8em, so only lines over about 45 characters still wrap |
| contents byline | with one author the contents rows drop the "By ..." byline |
| `overrides.<file>.scene_images: {n: path}` | swap scene n's picture for an edited copy (e.g. trimmed); caption + number unchanged |

`scan` honours `pages:` overrides (it used to ignore them).

## Clean re-export (broken exports)

App exports can carry duplicate scene rows, captions spilling onto an extra
page, broken Chinese line breaks and a blank back page.
`scripts/kw-export/export.sh <story-uuid> <out-dir>` re-renders the Classic
A4 layout straight from the DB with those fixed (local copies of the app's
`scripts/generate-story-pdf.tsx` and `StorybookTemplateA4.tsx`, marked
`LOCAL PRINT FIX`; the app code is untouched). It reads **prod** with the
service-role key, so get the user's OK first. When two duplicate rows hold
different images, the `photo-page` (original upload) one wins: check it.

## Trimming photo edges

`scripts/scene_trim.py <.build/<story>/> <BOOK>/scenes-trimmed/` trims plain
backdrop and empty paper from the extracted scene images. Then LOOK at a
before/after sheet of every picture. Tune single files (`--margin 0.045`
for thin strokes near the edge, `--margin 0 --thresh 60` to cut to a sheet
of paper on gray), and leave a picture out of `scene_images` when its
drawing reaches the edge. On *Mom, I Love You Forever*, the default pass
clipped the hamster whiskers and the faint "Mama" on the flower page.

## Spine

Without `--spine`, the spine width is estimated as pages x 0.0035in and
the output is labelled ESTIMATE. After the user adds the book to a Mixam
cart, rerun with `--spine <Mixam's value>`. Spine text is only drawn when
the spine is 0.2in or wider.

## Verify (MANDATORY)

Render a contact sheet (`pdftoppm -r 22` + PIL montage) for each size and
look at it. Then render these at about 50ppi and look closely: the About
page, the authors page, the contents page, one zigzag page, one digest
scene page, and the cover. Check `pdfinfo -box`: the page should be trim
+ 0.25in, and TrimBox should be inset by 9pt.

Test on a small sample book (2-3 story PDFs) before a full class book.

## Cover parts

- `cover.front_image`: a finished front cover (e.g. Codex's composite)
  used as is. The spine gradient is sampled from its left edge.
- `back_cover.background`: art behind the KindleWood Families page.
- `cover.title_baked` / the generated collage are only used without `front_image`.

## Bundled background choices

Pages with a real background image (About, Authors, Contents via
`contents.background`, Imagine) get the `framed` class: content is inset a
further 0.45in (letter) so text stays inside the watercolour border, and cards
turn mostly transparent. `cover.title_baked: true` (e.g. the original My
Imagination Journey art) drops the title card and lays out up to 24
characters with the scenes mixed in, as one collage under the painted title.

At each step that needs a background, offer the catalog in
[background-library.md](background-library.md). Copy the pick into the book
and set the explicit image path; a library pick takes precedence over `auto`.
The original titled cover needs the special handling in that guide.
