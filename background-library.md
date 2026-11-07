# Selectable background library

Use this library when choosing a cover or special-page background. Send [the catalog](assets/backgrounds/catalog.jpg) to the teacher with SendUserFile, then ask for a template name or number. If the teacher wants a closer look, send the full-resolution image. Machine-readable entries are in [catalog.json](assets/backgrounds/catalog.json).

Ask at each relevant step: front cover, About the Book, Meet Our Young Authors, and Keep Imagining. Options: choose a library template, reuse a previous choice, upload an image, generate a custom background, or no background. Do not ask again when the conversation or book.yaml already specifies the choice; a request to use one theme throughout applies to every page. Templates are not tied to a page purpose.

Copy the chosen PNG from the skill into the book folder, then save a relative path in book.yaml:

| Page | Copy to | YAML field |
|---|---|---|
| Cover | cover/background.png | cover.background |
| About the Book | about-book/background.png | about_book.background |
| Young authors | authors/background.png | authors.background |
| Keep Imagining | imagine/background.png | imagine.background |

Keep selected background IDs in a separate `background_choices` mapping in book.yaml for resuming, while the actual background fields contain the image paths used by the assembler. Preserve existing files by versioning when making a new selection. For no background, use a plain cream/white image at the same path, rather than `auto`, which generates a pastel backdrop.

The original My Imagination Journey image CONTAINS its title. It is a titled cover option and style reference, not a text-free interior background. Do not render a second title over it. The current assembler always draws the title: have a text-free version made first, or adapt cover title rendering explicitly before assembling with this original. For a different book title, make a text-free version first; never silently reuse the wrong title. All other supplied backgrounds are text-free.

Layout and readability: keep text in the quiet cream areas, adjust padding for each image and trim size, and use a light opaque or translucent text panel if necessary. Border motifs can extend farther inward near corners; inspect actual heading and paragraph placements. Keep the cover title, school name, and publisher credit editable for text-free templates. Verify the composed pages at the final trim size; the catalog is not print QA. Portrait templates need individual review when cropped to Digest/A5. These are raster source artworks, not print-ready PDFs.

## Cover example versus interior templates

See [cover-example.md](cover-example.md) for the approved finished collage cover. Use it to guide new cover compositions, replacing the title, characters, scenes and authors for each book. For interior pages, offer the text-free backgrounds in this library; do not use a finished collage cover as an interior background. The publisher credit is **© Powered by KindleWood Studio**.
