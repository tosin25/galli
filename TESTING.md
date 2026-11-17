# Testing Galley

Two rounds: a **smoke test** (does it work?) and a **designer test** (is it useful, and is the InDesign
structure right?). Log every finding in `ISSUES.md` using the template at the bottom.

Before you start:
- Windows, InDesign (any version from 2022 on is tested; older versions should work but are untested).
- Python 3 with `pip install -r requirements.txt` done once.
- **Save your own InDesign work first.** Galley only changes the document you point it at, but be safe.
- For chat: a Claude API key (copilot ⚙ Settings). Everything else works without one.

## 1. Smoke test (engineer, about 30 minutes)

| # | Do this | Expect |
|---|---|---|
| S1 | `python tests\smoke_copilot.py` with InDesign open | `PASS`, and the line `undo: top step 'Galley: flow manuscript', pages 6 -> 1` |
| S2 | `.\galley.ps1 variants -Styles bright,classic,modern` | three lines, each `0 errors`; `out\report.md` written |
| S3 | `.\galley.ps1 copilot` | a narrow "Galley Copilot" window on the right edge, on top of InDesign; green dot with the open document's name |
| S4 | Close all documents in InDesign | copilot says "no document open" within 3 s; quit InDesign → "InDesign is not open" (it never starts InDesign itself) |
| S5 | Your own manuscript: copilot › Continue › Choose .docx | chapter title and counts appear; open "How Galley read it" and note anything tagged wrong |
| S6 | Chat (with a key): "check this document" | it runs the check and summarises; the tool chips under the reply show ✓ check_document |

## 2. Designer test (layout designer, 60-90 minutes)

Give the designer the tasks, not a tour. Watch the first 15 minutes (or screen share) and write down where
they hesitate. Their words matter more than their score.

**Setup:** they open a real document of theirs with 1-3 pages already designed with their own paragraph
styles, and have a real chapter manuscript (.docx) of the same book. Start the copilot: `.\galley.ps1 copilot`.

| # | Task for the designer | What we learn |
|---|---|---|
| D1 | "Use Galley to continue this book with the next chapter." (Continue tab) | Can they find the flow without help? Are the suggested style matches right for *their* style names? |
| D2 | Look through the new pages. Mark anything you would fix before sending to an editor. | Layout quality: breaks, spacing, figures, tables, exercises |
| D3 | Press Ctrl+Z once in InDesign. | Everything Galley added disappears in one step |
| D4 | Flow it again. Then restyle one heading by hand, select it, click "Apply look to all" in the copilot. | Does the "change one, apply to all" copilot move feel natural? |
| D5 | Check tab › Run check. Click an issue. | Are the checks the ones they care about? Does jumping to the page help? |
| D6 | (with key) Ask in chat: "make the exercise headings use the coral colour", "why is page 7 so empty?" | Do they trust it to change their file? Are the answers useful? |
| D7 | References tab: drop 3-5 reference images (screenshots, Pinterest saves), select them, "Ask Galley about these". | Is the style read-out useful? What would they want it to *do* next? |
| D8 | Open the generated pages' paragraph styles, object layers, text threading. | "Is this built the way I would build it?" |

**Questions at the end (write down the answers word for word):**
1. How long would this chapter have taken you by hand? How long with Galley, including fixes?
2. What would stop you using it on a real job tomorrow?
3. What is the one thing you'd want it to do next?
4. Would you rather have this as a panel inside InDesign or a window beside it?

## 3. What we fix first (triage)

- **Blocker:** crashes, InDesign errors, content lost or wrongly tagged, undo not working, wrong document changed.
- **Quality:** layout that a designer would correct (gaps, breaks, sizes, spacing).
- **Feature:** new capability (more models, panel inside InDesign, whole book, reference reading).

Blockers first; after every fix re-run S1 and S2 so nothing that worked breaks.

## Issue template (`ISSUES.md`)

```
### <short title>
- Who / when: designer A, 2026-11-18
- Version: (git log -1 --oneline)
- Steps: 1. ... 2. ...
- Expected:
- Got:              (page number, screenshot path, copilot message)
- Severity: blocker | quality | feature
```
