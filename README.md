# Galley: manuscript in, book out

Galley turns a Word manuscript plus a style spec into a laid-out, editable InDesign chapter. It builds the
same chapter in several looks, checks every page automatically, and exports PDFs and page previews for review.
It is meant for in-house book designers, not engineers. This folder is a working prototype for Windows and
InDesign 2022+.

**v0.3 is an installable desktop app**: `Galley-Setup.exe` installs Galley for the user; it starts the engine
itself, docks the copilot beside InDesign, lives in the tray and updates itself. No Python or Terminal on the
designer's laptop. Build and release steps: [RELEASING.md](RELEASING.md). Development: `cd desktop && npm start`.

**v0.2 adds the Galley Copilot**: a window docked beside InDesign that works on the document you have open:
continue the book in *your* paragraph styles, check every page, change styles by asking, and collect references.
Start it with `.\galley.ps1 copilot`. See [Copilot](#copilot) and [TESTING.md](TESTING.md).

```
Galley/
  galley.ps1               one command for everything (ingest, build, variants, check, ui)
  ingest/ingest.py         .docx -> work/content.json   (Python standard library only)
  style/*.json             style specs: bright, classic, modern (+ custom.json written by the UI)
  indesign/build_chapter.jsx   builds the chapter in InDesign from content.json + a style spec
  indesign/qa_export.jsx       QA checks + PDF + PNG previews (also works on any open document)
  indesign/run.jsx             runs a script and reports errors back to PowerShell
  ui/index.html, ui/server.py  local web UI (checklist -> ingest -> variants -> pick); also serves the copilot
  ui/copilot.html          the copilot window (Assist, Check, Continue, References)
  copilot/bridge.py        the only code that talks to InDesign (COM + ExtendScript, one undo step per change)
  copilot/mapping.py       matches the designer's style names to Galley roles
  copilot/assistant.py     chat: models, tools, provider layer (Claude today; others plug in here)
  copilot/copilot_api.py   HTTP handlers for the copilot window
  indesign/flow_into.jsx   "continue in my style": flows content into the open document with its own styles
  samples/make_designer_sample.jsx   test fixture: a designer's document with their own style names
  tests/smoke_copilot.py   end-to-end test of the copilot path, including the one-step undo
  tools/sheet.ps1          page previews on one contact sheet
  samples/                 plants_chapter.docx (generic sample) + make_sample.py
  art/                     generic spot illustrations (SVG sources in art/src)
  work/                    content.json, extracted media, ingest_report.txt, UI project state
  out/<style>/             <style>_chapter.indd, .pdf, previews/pNN.png, contact_sheet.png, qa.json, qa.txt, build_log.txt
  out/report.md            side-by-side summary of the variants
```

## Requirements

- Windows with Adobe InDesign (tested on 2022; it is driven through COM scripting, which every version since
  CS3 supports). The copilot never starts InDesign; the batch commands start it if needed.
- Python 3, then once: `python -m pip install -r requirements.txt` (pywin32 for COM, anthropic for chat).
- For chat only: a Claude API key, entered in the copilot's settings (stored in `%APPDATA%\Galley`, not here).
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
.\galley.ps1 copilot                                    # copilot window beside InDesign
python tests\smoke_copilot.py                           # end-to-end copilot test (needs InDesign open)
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

## Copilot

`.\galley.ps1 copilot` starts the local server and opens a narrow app window on the right edge of the screen,
pinned above InDesign. It connects to the running InDesign (any version with COM scripting) and follows the
document you have open: name, pages, styles and your current selection, refreshed every few seconds.

- **Continue**: choose a .docx (or the sample). Galley matches the manuscript's roles (chapter title, section
  heading, body, example box, exercise, question, note...) to the paragraph styles already in your document
  and shows its guesses for you to confirm. **Flow into this document** adds pages after the last page and
  pours the chapter in with *your* styles plus Galley's keep rules, figure fitting, option columns and
  stranded-heading fixes, then runs the check. The confirmed mapping is saved in the document, so the next
  chapter needs no setup. It even copies your chapter label ("CHAPTER 2" -> "CHAPTER 3").
- **Check**: every QA check on the open document; click an issue to jump to its page.
- **Apply look to all**: restyle one paragraph by hand, select it, and the bar at the top turns that look into
  the paragraph style everywhere.
- **Assist**: chat with a model that acts through tools: read the document, check it, go to a page, change a
  paragraph style, apply a look to all, suggest the mapping, flow the manuscript. Pick the model at the top
  (Claude Opus 5.5 by default; OpenAI, DeepSeek and a Galley model are listed as coming).
- **References**: drop images (screenshots, Pinterest saves, sample pages), keep board links, select images
  and ask Galley to describe the style and suggest style changes.
- **Undo**: every change Galley makes is ONE undo step in InDesign ("Galley: flow manuscript", "Galley: change
  style ..."). Checks never add undo steps. This is covered by the smoke test.

## Limits (honest)

- Reference images are collected but not yet read automatically. In this prototype the designer turns them
  into parameters (trim, fonts, palette, structure). Reading them with a vision model is the next step, and it
  should only ever set style parameters, never copy a reference's artwork or layout.
- Illustrations are not generated. Galley places supplied art (here a small generic set). New characters or
  diagrams need illustrators or an image model, plus the publisher's rights checks.
- "Style from sample pages" works through the copilot's Continue tab (your styles, matched by name). It does
  not yet infer styles from pages formatted only with local overrides.
- The copilot window is a browser app window pinned on top, not yet a panel inside InDesign or an installed
  app with a tray icon. Pinterest boards can't be embedded (Pinterest blocks it): save or screenshot pins.
- Chat needs a Claude API key; only Claude models are connected so far.
- Ingest is heuristic. Odd manuscripts need the review list, and later Claude-assisted tagging.
- One chapter per run. Whole-book assembly is listed below.
- Windows + COM only. macOS would drive the same JSX via AppleScript.
- PNG previews flatten transparency, so text on pages with transparent art can look slightly heavier than
  in the PDF.

## Next steps

1. **Installable copilot** (Tauri/Electron wrapper: tray icon, auto-start, updates) and/or a **UXP panel** for
   InDesign 2023+, with a CEP fallback for older versions. Same flow inside InDesign: drop a manuscript, pick a spec, build, see QA with
   click-to-page links. Mode A: read paragraph/object styles from the designer's sample pages into a spec.
2. **Reference reading**: a vision model proposes spec values (palette, type scale, box treatments) from the
   uploaded references; the designer approves each one.
3. **Claude-assisted tagging** for manuscripts without clear markers, only for the paragraphs in the review list.
4. **Whole book**: chapter list, continuous folios, an InDesign Book file, TOC and index hooks.
5. **More treatments**: two-column layouts, margin notes, worked-example steps with numbers, answer keys.
6. **Round trip**: re-flow after copy edits without losing the designer's manual tweaks (tag manual overrides).
