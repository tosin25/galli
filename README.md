# Galley: manuscript in, book out

Galley turns a Word manuscript plus a style spec into a laid-out, editable InDesign chapter. It builds the
same chapter in several looks, checks every page automatically, and exports PDFs and page previews for review.
It is meant for in-house book designers, not engineers. This folder is a working prototype for Windows and
InDesign 2022+.

```
Galley/
  galley.ps1               one command for everything (ingest, build, variants, check, ui)
  ingest/ingest.py         .docx -> work/content.json   (Python standard library only)
  style/*.json             style specs: bright, classic, modern (+ custom.json written by the UI)
  indesign/build_chapter.jsx   builds the chapter in InDesign from content.json + a style spec
  indesign/qa_export.jsx       QA checks + PDF + PNG previews (also works on any open document)
  indesign/run.jsx             runs a script and reports errors back to PowerShell
  ui/index.html, ui/server.py  local web UI (checklist -> ingest -> variants -> pick)
  samples/                 plants_chapter.docx (generic sample) + make_sample.py
  art/                     generic spot illustrations (SVG sources in art/src)
  work/                    content.json, extracted media, ingest_report.txt, UI project state
  out/<style>/             <style>_chapter.indd, .pdf, previews/pNN.png, contact_sheet.png, qa.json, qa.txt, build_log.txt
  out/report.md            side-by-side summary of the variants
```

## Requirements

- Windows with Adobe InDesign 2022 or later (driven through COM; InDesign opens if it is not running).
- Python 3 (for ingest and the UI). No packages to install.
- The fonts named in the style specs. The three samples use Poppins, Nunito, Georgia, Playfair Display,
  Inter and Google Sans.

## Run it

From PowerShell in this folder:

```powershell
.\galley.ps1 all                                        # sample manuscript -> 3 variants + report
.\galley.ps1 ingest -Manuscript D:\books\chapter4.docx   # your own manuscript
.\galley.ps1 variants                                   # every spec in style\
.\galley.ps1 variants -Styles bright,modern             # some of them
.\galley.ps1 build -Style classic                       # one look only
.\galley.ps1 check                                      # QA + export the document open in InDesign
.\galley.ps1 ui                                         # web UI at http://localhost:8765
```

If PowerShell blocks the script, run it with `powershell -ExecutionPolicy Bypass -File .\galley.ps1 all`.
A three-look build of the sample chapter takes about a minute.

## How the pieces work

**Ingest** reads the .docx XML directly. Word heading styles become chapter title / h2 / h3. Typed markers are
recognised: `Example 2:`, `Activity:`, `Exercise 3.1`, `Did you know?`, `Note:`, `Remember:`, numbered questions,
`(a) (b) (c)` options, `____` blanks, bullet lists, Word tables and pictures with their `Figure` captions. The
bullets after "In this chapter you will learn:" become the opener objectives. Every non-obvious decision is
written to `work/ingest_report.txt`, with a "please review" list for anything uncertain.

**Style spec** (`style/*.json`): trim, bleed, margins, heading/body fonts, type scale, palette, plus a treatment
for each element: opener (`banner` / `band` / `minimal`), h2 (`band` / `rule` / `number_rule`), example and
activity boxes (`shaded` / `outlined` / `sidebar`, with `pill` / `band` / `label` / `ruled` heads), exercises,
notes (optional icon), tables, bullets, folio (`circle` / `block` / none; centre or outer), running header,
side tab, figure sizing and spot illustrations. Copy a spec and change values to make a new look.

**Build** (`build_chapter.jsx`) makes real, editable InDesign structure:
- one threaded story; every element is a named paragraph or character style, so a designer restyles the whole
  chapter by editing a style;
- boxes are paragraph shading / borders, not loose frames, so they move with the text;
- figures and note icons are inline anchored objects; tables are real tables with header rows;
- keep rules so boxes, figures + captions and tables never split; an exercise longer than a page may continue
  only between questions;
- answer options are laid out on 4, 2 or 1 tab columns, chosen by measuring the set text;
- fixes: stranded headings move to the next page, a figure pushed to the next page is scaled down (to
  `figures.min_scale`) if that keeps it in place, a table's lead-in travels with the table, empty end pages
  are removed;
- masters hold the running header, folio and side tab; the opener master holds the banner;
- the opener character and spot art go on their own **Illustrations** layer, placed in big white gaps after
  the text has settled.

**QA** (`qa_export.jsx`) runs after each build and on demand. It checks for overset text (stories and table
cells), boxes, figures or tables split across pages, headings stranded at the foot of a page, objects off the
page (content cut by the trim, or anything outside the bleed; anchored objects outside the column are notes),
missing or changed links, images under 150 ppi, and empty pages. Results go to `qa.json` / `qa.txt` and
`out/report.md`.

## The UI

`.\galley.ps1 ui` opens a one-page app that walks through the "style from references" flow:
1. choose the mode;
2. fill the reference checklist (9 required items: manuscript, trim, opener, body page, example box,
   exercise box, folio, fonts, palette; 7 optional) and the parameters; uploads are stored in `work/refs/`;
3. ingest the manuscript and review the decisions;
4. build the looks (the three specs plus "Custom", made from the checklist's trim, fonts and palette over a
   chosen structure), see page previews and QA for each;
5. pick one. The pick is saved in `work/project.json`.

## Limits (honest)

- Reference images are collected but not yet read automatically. In this prototype the designer turns them
  into parameters (trim, fonts, palette, structure). Reading them with a vision model is the next step, and it
  should only ever set style parameters, never copy a reference's artwork or layout.
- Illustrations are not generated. Galley places supplied art (here a small generic set). New characters or
  diagrams need illustrators or an image model, plus the publisher's rights checks.
- "Style from sample pages" (reading styles from pages the designer lays out) is designed but not built: it
  needs the InDesign panel below.
- Ingest is heuristic. Odd manuscripts need the review list, and later Claude-assisted tagging.
- One chapter per run. Whole-book assembly is listed below.
- Windows + COM only. macOS would drive the same JSX via AppleScript.
- PNG previews flatten transparency, so text on pages with transparent art can look slightly heavier than
  in the PDF.

## Next steps

1. **InDesign UXP panel**: the same flow inside InDesign: drop a manuscript, pick a spec, build, see QA with
   click-to-page links. Mode A: read paragraph/object styles from the designer's sample pages into a spec.
2. **Reference reading**: a vision model proposes spec values (palette, type scale, box treatments) from the
   uploaded references; the designer approves each one.
3. **Claude-assisted tagging** for manuscripts without clear markers, only for the paragraphs in the review list.
4. **Whole book**: chapter list, continuous folios, an InDesign Book file, TOC and index hooks.
5. **More treatments**: two-column layouts, margin notes, worked-example steps with numbers, answer keys.
6. **Round trip**: re-flow after copy edits without losing the designer's manual tweaks (tag manual overrides).
