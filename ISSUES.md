# Galley issues

Log findings here using the template in TESTING.md. Newest first.

### (note) Apps started from inside the Claude desktop app's terminal see a private AppData
- Who / when: desktop app test, 2026-11-26
- Got: the installed Galley, started from Claude's PowerShell, saved its work into
  `%LOCALAPPDATA%\Packages\Claude_...\LocalCache\Roaming\Galley` (Windows app virtualization), which InDesign
  cannot see, so flows failed with ") does not have a value".
- Not a Galley bug: started from the Start menu / Explorer it uses the real `%APPDATA%\Galley` (verified).
  When testing from a Claude session, start Galley with `explorer.exe "%LOCALAPPDATA%\Programs\galley\Galley.exe"`.
- Hardening idea: the engine could check InDesign can read the content file and say so plainly.

### (seen once) Installer crashed in NSIS System.dll
- Who / when: desktop app test, 2026-11-26
- Got: `Galley-Setup-0.3.0.exe /S` crashed (0xc0000005 in System.dll) right after the development copy of Galley
  was force-closed. Re-running the same installer from the same folder worked, three times. Probably the
  installer's "is Galley running?" check meeting a process that was still shutting down. Watch for it.

### (fixed) Copilot flow report JSON and numbered points in designer styles
- Fixed 2026-11-26: control characters escaped in flow_into.jsx's report; Galley switches off the designer
  style's own automatic bullet/number on paragraphs it numbers itself. Both smoke tests PASS.

### (open) Galley's InDesign connection is Windows-only
- Who / when: moving development to a Mac, 2026-11-25
- Got: `copilot/bridge.py` (COM), `galley.ps1`, the copilot launcher and `tools/*.ps1` need Windows.
- Plan: macOS branch in bridge.py via `osascript` + `do script`; cross-platform `galley.py`; Pillow previews. See HANDOFF.md.
- Severity: blocker (on the Mac)

### (open) Copilot flow: numbered points "wider than their number column"
- Who / when: tests/smoke_copilot.py work/maths/content.json, 2026-11-25
- Got: QA errors on `1. < means ...` items flowed into the designer fixture's styles; Galley's own builder is fine.
- Likely cause: the designer's list style keeps its own numbering/tabs; `numbered()` in flow_into.jsx must override them.
- Severity: blocker (house-rules branch)

### (open) Copilot flow report is invalid JSON
- Who / when: tests/smoke_copilot.py (plants), 2026-11-25
- Got: `Invalid control character` reading work/copilot/flow_report.json.
- Fix: escape control characters in the hand-built JSON at the end of flow_into.jsx.
- Severity: blocker (house-rules branch)

### (open) House rules not done yet (publisher layout review)
Generic behaviours from the review that Galley cannot do yet, or only partly:
- **Section-heading icons** (a small relevant graphic in a section heading): planned as a spec option
  (`h2.icons`: keyword -> art), not built.
- **A fraction whose numerator is a whole expression laid out over two lines** in the manuscript
  ("(30×1) + (12×2) ..." over "60"): only inline `a/b` and Word equation fractions are stacked.
- **"Never repeat as text what a picture shows"**: Galley no longer copies shape text into the body, but it cannot
  tell when a manuscript *paragraph* restates a picture (e.g. the numbers along a number line). Needs a review
  step (later: Claude-assisted) or the editor's mark-up.
- **"Check every generated picture against the manuscript"**: QA checks drawings are not clipped and their labels
  fit (overset), not that they match the manuscript's meaning. Needs a visual comparison step.
- **Diagrams drawn by the designers** (their own shape library, separated graphics): Galley redraws the manuscript's
  shapes; it cannot yet reuse a designer's drawn version of the same diagram. Plan: a library of placed graphics
  keyed by figure id, used when present.
- **Answer-box grids, calendars, number lines** as special diagram types: drawn only when the manuscript draws them
  as shapes; Word tables become tables. No number-line generator yet.
- **Example boxes absorb following plain paragraphs** (ingest heuristic: a box runs to the next heading/marker).
- **Hand-drawn illustrations** in each unit: needs an illustrator or an image model; Galley only places supplied art.
- **"Or ..." lines aligned on their "=" can wrap far to the right** when long; consider aligning them under the
  calculation's start instead (designer's call).

### (fixed in v0.2) Flow was not one undo step
- Who / when: engineering smoke test, 2026-11-17
- Got: Ctrl+Z removed only the last placement; the Check tab also added "Set Measure Units" steps on top.
- Fix: undo block opened inside InDesign (`app.doScript(..., UndoModes.ENTIRE_SCRIPT)`); QA uses script-only units. Covered by tests/smoke_copilot.py.

### (fixed in v0.2) Designer files with spread rulers
- Who / when: engineering smoke test, 2026-11-17
- Got: QA reported right-hand pages as "off the page"; flowed frames and pictures misplaced on right-hand pages.
- Fix: QA measures against each page's bounds; flow works in page rulers and restores the designer's setting.
