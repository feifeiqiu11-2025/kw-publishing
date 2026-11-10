# KindleWood class book: the rules

Decisions the teacher approved while building the first class book
(*My Imagination Journey*, Nov 2026). Treat them as the defaults for every
new class book. Change one only when the teacher asks.

## Print + files

1. **Printer: Mixam** (mixam.com). Order a **Paperback, Perfect bound** book.
   The default size is **US Letter 8.5 x 11in**; Digest 5.5 x 8.5 and A5 also work.
2. Every page gets **0.125in bleed** with TrimBox/BleedBox set. The page
   count is always **even**.
3. **No blank pages, ever.** An odd page count gets a "Story Idea" page.
   Gaps in a page get Spark filler (see Scenes).
4. **Margins:** the wider margin goes on the **binding side** and alternates
   left/right. Keep white space to a minimum: outer about 0.3in, gutter about 0.55in.
5. **Cover files:** the one-piece spread Mixam wants (back + spine + front),
   **plus** separate front, back and spine files, each as a PDF and a 300ppi PNG.
6. **Spine width** comes from the Mixam cart. Until then it is an estimate,
   so rebuild with the real value before ordering.
7. **Delete old versions.** Every build overwrites `out/`, so no history is kept.
8. **No drop shadows** anywhere: Mac Preview shows them as gray boxes.
9. KindleWood art is 1024px, so recommend **one proof copy** before the class order.

## Cover

10. **Front:** a finished cover image (e.g. one made in Codex) is used
    **as is**. The style to aim for: a watercolor frame, a painted title,
    the kids' characters as stickers, and the story scenes as tilted windows.
11. The **front footer** says "Created by **<School> Storytellers**" on one
    line and "© Powered by KindleWood Studio" under it, both in a clearly
    readable size (school line about 32px and credit about 22px on the
    1102px-wide design). It sits ≥0.25in above the trim. **Never list the children's names on
    the cover**; that would be far too long.
12. **Back:** always the standard **KindleWood Families** back cover,
    `assets/back-cover/kindlewood-families-back.png` (from *My Imagination
    Journey*, user rule 2026-11-10). The assembler uses it by default; set
    `back_cover:` only when the user asks for a different back. Its © year
    reads 2025, so mention it.
13. **Spine:** its color is taken from the front art's left edge so the art
    wraps around. The text is the **book title** followed by
    **"© Powered by KindleWood Studio"**.

## Front matter (in this order)

14. **About This Book:** a warm 120-200-word summary drawn from the teacher's
    class emails and curriculum, in **English + 中文 if both fit on one
    page, otherwise English only**. The text sits **directly on the
    background art** with no white box. It is signed with the teachers'
    names in a **handwritten signature font**.
15. **Meet Our Young Authors:** English only, with **all children on one page**.
    Each child gets a **round portrait of their in-story character** (not
    their original drawing) with their name underneath. The teacher picks
    which chapter the portraits come from, and can make exceptions per child.
    Notes about each child are optional.
16. **Contents:** English only, always **one page**. It lists the chapters,
    each story with its authors and page number, and Keep Imagining.
    There are **no per-chapter contents pages**.
17. **Backgrounds:** use a **different** library template for each special
    page (About, Authors, Contents, Keep Imagining). Choose frames whose
    decorations don't run into the text.

## Chapters + stories

18. **One chapter = one class theme**, titled from the curriculum (e.g. This
    Is Me! / My Fall Adventure / Who Do I Want to Be? / Welcome Spark to
    Our Community / Space Explorers).
19. **Each chapter starts on a new page.** Stories **within** a chapter
    **run on**, so a new story can start halfway down a page and no page
    is left half empty.
20. **Story opener = half a page:** the story's cover art on one side
    (alternating sides), and on the other the chapter name, a "Story N"
    badge, the title and the authors.
21. **Meet the Character Designers** sits right under the opener, rebuilt as
    cards in the book's own font. Each card shows the original drawing and
    the in-story character, the name, and "In <child>'s Own Words". Two or
    three children share a row.
22. **Scenes: 4 per page** (2 x 2) for classroom books, in a zigzag: the left
    picture has its caption below, the right picture has its caption above.
    Single-author books use 2 per page (rule 36). Captions sit on
    pastel cards in **English + 中文**.
23. **Comic-style number badges** count the scenes within each story (1, 2, 3…).
24. When a story's last scene is left alone, the spare cell gets **Spark**
    (the blue-line set: reading, cheering, waving, thinking, laughing) with
    an encouraging line, e.g. "Keep reading — more adventures ahead!".
    A half-empty last page of a chapter gets a wide Spark row.
25. **Removed automatically:** QR pages, "Download Mobile App" pages, QR
    blocks printed inside designer pages, blank pages, and the in-book
    KindleWood ad (it goes on the back cover).

## Text + edits

26. **The children's words are theirs.** Fix only clear typos (and ask
    first). Never invent facts about a child.
27. Teacher corrections go into `book.yaml` and are never made by editing the
    PDFs: caption rewrites (`scene_edits`), new pictures
    (`insert_scenes`), missing "Own Words" (`designer_words`), and story
    titles.
28. **Names are spelled the way the teacher wants** everywhere: authors page,
    captions, bylines. Flag mismatches such as "Sara" vs "Sarah".

## Look + feel

29. **Fonts:** English **Chalkboard SE** (comic-style but easy to read),
    Chinese **ZCOOL KuaiLe**, and **Snell Roundhand** for the teacher signature.
30. **Keep Imagining!** (English only): "Congratulations on your writing
    journey — we are so proud of you! Keep imagining, keep drawing, keep
    writing — your stories and your voice matter." then "What are you going
    to draw and write next?", a drawing box, writing lines, and Spark
    writing in the bottom-right corner. The text sits directly on the
    background, with no white box.
31. **Spark** is always the **blue-line** Spark (`assets/spark*`), never the
    green app Spark.

## Way of working

32. **Build chapters 1-2 first** for the teacher to review, then add the rest.
33. Preview a new style on **one story first** (e.g. scene numbers on
    Chapter 1, Story 1), then roll it out to the whole book.
34. Look at every build yourself (contact sheet + close-ups) **before**
    showing the teacher.

## Single-author books (approved on *Mom, I Love You Forever*, Nov 2026)

Every rule above applies to single-author books too. These add to them:

35. **Ask first:** classroom story book or single-author book (SKILL.md A / A1).
36. **2 scenes per page, zigzag:** picture and caption swap sides row by row.
    Captions sit on pastel cards (rule 22) and every picture gets its comic
    number badge (rule 23).
37. **Never cut the art:** photographed artwork is shown whole
    (`scene_fit: contain`). Plain photo background and empty paper may be
    trimmed, but nothing the child drew, wrote or glued; check every trim
    by eye. A picture whose faint pencil runs to the edge stays untrimmed.
38. **Even sizes:** pictures get about the same visual area, whatever their shape.
39. **No chapter labels** for one story: contents shows "Story 1: <title>"
    and the story opener has no "Chapter 1 · Story 1" kicker. The opener
    picture is larger (6.6in on Letter).
40. **Meet the Author** (singular): the photo sits top-left, larger (2.4in),
    with the name under it, and the rest of the page is for a short bio
    written by the family. Leave it empty rather than inventing one.
41. **About This Book** is drafted only from what the story shows and what
    the family says. Its signature line comes from the family; until then
    it is a visible placeholder, and say so.
