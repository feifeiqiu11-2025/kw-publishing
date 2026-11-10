# kw-publishing — KindleWood print books (Claude Code skill)

Turns KindleWood story exports into a print-ready class book for
**Mixam** perfect-bound paperbacks:

- cover spread (plus separate front, back and spine files)
- About This Book, Meet Our Young Authors, and a one-page contents
- chapters of 4-per-page numbered scenes with the children's
  "Meet the Character Designers" cards
- a Keep Imagining page

It also makes **single-author books** (one child's story as a gift book:
Meet the Author, zigzag 2-per-page whole pictures, story-only contents), and
it can resize a single PDF for print with bleed. Claude first asks which
kind of book it is.

## Install

```bash
git clone https://github.com/feifeiqiu11-2025/kw-publishing ~/.claude/skills/kw-publishing
```

Then in Claude Code, run `/kw-publishing` and say "make a new class book".
Claude walks you through onboarding one step at a time.

**Requirements:** macOS with Google Chrome, poppler (`brew install poppler`)
and Python 3. On first use, the Python libraries are installed into
`scripts/.venv` (see SKILL.md, Setup).

## What's inside

| file | what it is |
|---|---|
| `SKILL.md` | the onboarding steps Claude follows |
| `book-rules.md` | the approved design and content rules (the defaults) |
| `book-assembly.md` | how the build works: layout, parsing, rendering, checks |
| `book.template.yaml` | the per-book settings file, with every option |
| `background-library.md`, `assets/backgrounds/` | page background templates and catalog |
| `assets/spark*` | Spark the dragon poses |
| `fonts/` | ZCOOL KuaiLe (Chinese), under the SIL Open Font License |
| `scripts/book_assemble.py` | builds the book (`init`, `scan`, `extract`, `portraits`, `assemble`) |
| `scripts/pdf_print_size.py` | resizes a single PDF for print, with bleed |
| `scripts/scene_trim.py` | trims plain photo background around photographed artwork |
| `scripts/kw-export/` | clean re-export of one story from the KindleWood DB (fixes broken exports) |
| `assets/back-cover/` | the standard KindleWood Families back cover, used on every book |

## Notes

- Story PDFs, class photos and finished books are not part of this repo.
  Each book lives in its own folder on your computer.
- The KindleWood artwork, backgrounds and Spark images are © KindleWood Studio.
