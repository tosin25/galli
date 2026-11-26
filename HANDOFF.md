# Hand-over: continuing Galley on a Mac

Written 2026-11-25 on the Windows PC, updated 2026-11-26, for the next Claude Code session (on a MacBook).
Read this first, then README.md, RELEASING.md, TESTING.md and ISSUES.md.

## Update 2026-11-26 (read this before the rest)
- **The two "open failures" below are fixed** (flow report JSON; numbered points in designer styles). Both
  `tests/smoke_copilot.py` runs (plants, maths) PASS on Windows.
- **Galley is now an installable desktop app (v0.3.1, commit e311735):** `desktop/` (Electron: engine start,
  docked always-on-top window, tray, start with the computer, appears when InDesign opens, auto-update with
  electron-updater), `packaging/galley-engine.spec` (PyInstaller engine), `copilot/paths.py` (program files vs
  user work in `~/Library/Application Support/Galley` on a Mac). See RELEASING.md. Tested on Windows: installer,
  0.3.0 -> 0.3.1 auto-update, maths chapter through the installed app (QA pass).
- **Users see model tiers only** (Galley / Galley Fast / Galley Pro in `copilot/assistant.py`); never show model
  or provider names in the UI.
- **Mac plan, in order:** (1) macOS branch in `copilot/bridge.py` (osascript `do script`, below), (2) run the
  smoke tests on the Mac, (3) build the Mac app: `pip install pyinstaller anthropic pillow`, `cd desktop && npm install`,
  `npm run engine && npm run dist` (dmg + zip; signing/notarization needs an Apple Developer ID, see RELEASING.md),
  (4) the Mac launcher pieces in `galley.ps1` / `tools/*.ps1` are only needed for the batch builder, not the app.
- The Electron app already handles macOS (`pgrep` for InDesign, dock icon hidden, data folder); untested there.

## Where things stand

| Version | What | State |
|---|---|---|
| v0.1 (`main`, 6e2fdcf) | ingest .docx, style specs, InDesign builder, QA, variants, web UI, pitch | done, tested on Windows |
| v0.2 (`main`, 4873137) | copilot window beside InDesign: continue in the designer's own styles, Check, apply look to all, chat with tools, references; one-step undo | done, tested on Windows; chat untested (no API key yet) |
| house rules (branch `house-rules-wip`) | the publisher's layout rules turned into generic behaviour (below) | done, tested on Windows (both smoke tests PASS) |
| v0.3.1 desktop app (branch `house-rules-wip`, e311735) | installable Electron app with bundled engine and auto-update | done, tested on Windows; Mac build not done |

### House rules (branch `house-rules-wip`)
A publisher's layout review was turned into general Galley behaviour (no client branding):
- **Ingest** (`ingest/docx_parts.py`): Word's automatic list numbers are recomputed from numbering.xml (the
  main cause of lost numbers); drawn Word shapes (DrawingML groups and legacy VML) become `diagram` blocks;
  shape text is no longer repeated as body text; Word equation fractions read as `1/2`; "=" continuation lines,
  Th/H/T/U column sums, teaching notes and rule/example pairs are recognised.
- **Layout** (`indesign/house.jsx`, shared by `build_chapter.jsx` and `flow_into.jsx`): number columns sized to the
  widest number (hanging indent), Roman example lists optionally set 1, 2, 3, "=" lines aligned under the first
  "=", column sums on centred tabs with a rule above the answer, stacked fractions, diagrams redrawn and scaled to
  the column, no widows/orphans (2 lines), a section that would only just start at a page foot moves to the next
  page, teaching notes with bold label + italic body, rule boxes with plainer examples.
- **Spec**: new `style/primary.json` (no running header, footer folio, side-tab colour per part via
  `side_tab.color_by_part`, 14 pt spaced body, stacked fractions, Roman examples to 1, 2, 3).
- **QA** (`indesign/qa_export.jsx`): widows/orphans, every manuscript number present before the right text,
  number wider than its column, "=" alignment, drawings sticking out of the column (error > 2 mm), under-filled
  pages (note). Boxes, calculations and numbers are now found from styles and text, not saved character positions,
  so the checks stay right after the designer edits.
- **Tests**: `samples/make_maths_sample.py` writes `samples/maths_chapter.docx` (Word auto-numbering, drawn shapes,
  VML, OMML fraction, calculations...). `tests/qa_negative.py` breaks a built chapter on purpose and checks QA catches
  each break: **PASS** on Windows.

Last results on Windows:
- `galley.ps1 build -Style primary` on the maths chapter: 6 pages, 0 errors (notes: one exercise continues between
  questions; one page 38 % full after a moved section).
- `tests/qa_negative.py`: PASS (lost number, changed number, number too wide, misaligned "=" all caught).
- `tests/smoke_copilot.py` (plants): **crashes** reading `work/copilot/flow_report.json` (invalid control character).
- `tests/smoke_copilot.py work/maths/content.json`: flows and undoes in one step, but **3 QA errors**: the numbered
  points (`1. < means ...`) are "wider than their number column" in the designer's styles.
- Not yet re-run after these changes: `galley.ps1 variants -Styles bright,classic,modern` (regression).

## First job on the Mac: a macOS InDesign bridge

Everything that talks to InDesign is Windows-only; everything that runs *inside* InDesign is cross-platform.

| Cross-platform, no change | Windows-only, needs a Mac version |
|---|---|
| `indesign/*.jsx` (ExtendScript), `ingest/`, `copilot/mapping.py`, `copilot/assistant.py`, `ui/*.html`, `ui/server.py` | `copilot/bridge.py` (pywin32 COM), `galley.ps1` (PowerShell), the copilot launcher (Edge + Windows topmost), `tools/*.ps1` (System.Drawing previews/contact sheets) |

Plan:
1. `copilot/bridge.py`: keep the same functions (`running`, `js`, `run_file`, `status`, ...) and add a macOS branch:
   - running: `pgrep -x "Adobe InDesign 20xx"` or AppleScript `application id "com.adobe.InDesign" is running`.
   - run code: write the script to a temp `.jsx` and call
     `osascript -e 'tell application id "com.adobe.InDesign" to do script (POSIX file "/tmp/x.jsx") language javascript'`.
     The script's last value comes back on stdout. Pass arguments by prepending `app.scriptArgs.setValue(k, v);` lines.
   - one undo step: keep the in-InDesign `app.doScript(fn, ..., UndoModes.ENTIRE_SCRIPT, name)` wrapper (already in
     `js()` and `indesign/run.jsx`), so the COM undo arguments are not needed.
2. A cross-platform `galley.py` CLI (ingest / build / variants / check / copilot) replacing `galley.ps1`
   (keep the .ps1 for Windows or make it call galley.py). Previews and contact sheets: use Pillow (`pip install pillow`)
   instead of System.Drawing.
3. Copilot window on the Mac: `open -na "Google Chrome" --args --app=http://127.0.0.1:8765/copilot --window-size=440,900`
   (or Safari/Edge). Keeping it on top needs a small native wrapper later; not essential for testing.
4. Then re-run: `python3 tests/smoke_copilot.py`, `python3 tests/qa_negative.py`, and the four-style regression.

## Then: the two open failures
1. **flow_report.json control character** (`indesign/flow_into.jsx`, end of file): the report is hand-built JSON;
   the `log` entries can contain characters like `\u0016` or tabs. Escape all control characters the same way
   `qa_export.jsx`'s `esc()` does (`/[\x00-\x1f﻿]/g`).
2. **Numbered points "wider than their number column" in designer styles** (`numbered()` in `flow_into.jsx`): the
   flow sets `leftIndent`/`firstLineIndent` from the designer's style + `GalleyHouse.hang`, but the designer's list
   style probably carries its own bullets/numbering or tab stops, so the text does not start at the indent. Inspect
   the flowed paragraph (`bulletsAndNumberingListType`, `tabList`, `firstLineIndent`) and either switch off the
   style's own list numbering on those paragraphs or align the tab to the new indent.

## Environment notes
- Python 3 with `anthropic` (`pip install -r requirements.txt` will fail on `pywin32` on a Mac: install
  `anthropic` and `pillow` directly, and make requirements platform-conditional:
  `pywin32>=306; sys_platform == "win32"`).
- Fonts used by the specs: Poppins, Nunito, Inter, Google Sans, Playfair Display (Google Fonts), Georgia (macOS has it).
- The copilot's API key lives in the user's profile (`%APPDATA%\Galley` on Windows); on macOS use
  `~/Library/Application Support/Galley` (`copilot/settings.py` needs that branch).
- Never edit the publisher's own book files; Galley stays generic (no client branding).
- Work in small commits; after each change re-run the relevant test. Commit and push before switching machines.
