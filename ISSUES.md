# Galley issues

Log findings here using the template in TESTING.md. Newest first.

### (fixed in v0.2) Flow was not one undo step
- Who / when: engineering smoke test, 2026-11-17
- Got: Ctrl+Z removed only the last placement; the Check tab also added "Set Measure Units" steps on top.
- Fix: undo block opened inside InDesign (`app.doScript(..., UndoModes.ENTIRE_SCRIPT)`); QA uses script-only units. Covered by tests/smoke_copilot.py.

### (fixed in v0.2) Designer files with spread rulers
- Who / when: engineering smoke test, 2026-11-17
- Got: QA reported right-hand pages as "off the page"; flowed frames and pictures misplaced on right-hand pages.
- Fix: QA measures against each page's bounds; flow works in page rulers and restores the designer's setting.
