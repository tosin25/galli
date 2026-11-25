"""QA must catch what it claims to catch. Needs InDesign open and out/maths/primary/primary_chapter.indd built.

    python tests/qa_negative.py

Opens the built maths chapter, breaks it on purpose (a lost number, a misaligned "=", a number too wide for
its column), runs QA, and checks each break is reported. The document is closed without saving.
"""
import json
import os
import sys

G = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, G)
from copilot import bridge  # noqa: E402

DOC = os.path.join(G, 'out', 'maths', 'primary', 'primary_chapter.indd').replace('\\', '/')


def main():
    r = bridge.js("""
var d = app.open(File(%s)), st = null, all = d.stories.everyItem().getElements();
for (var i = 0; i < all.length; i++) if (all[i].extractLabel('galley_labels')) st = all[i];
var P = st.paragraphs.everyItem().getElements(), done = {};
for (i = 0; i < P.length; i++) {
  var c = P[i].contents;
  if (c.indexOf('(b)\\t') == 0 && !done.label) { P[i].characters.itemByRange(0, 3).remove(); done.label = 1; }
  else if (/^= 375/.test(c) && !done.calc) { P[i].leftIndent = P[i].leftIndent + 6; done.calc = 1; }
  else if (c.indexOf('3.\\t') == 0 && !done.hang) { P[i].insertionPoints[0].contents = '33'; done.hang = 1; }
}
return __j({broke: done});""" % json.dumps(DOC))
    print('broke:', r)
    out = os.path.join(G, 'work', 'qa_negative')
    os.makedirs(out, exist_ok=True)
    res = bridge.run_file(os.path.join(G, 'indesign', 'qa_export.jsx'), {'galley_doc': '', 'galley_out': out, 'galley_export': '0'})
    bridge.js("for (var i = app.documents.length - 1; i >= 0; i--) if (app.documents[i].name == 'primary_chapter.indd') app.documents[i].close(SaveOptions.NO); return __j({});")
    if res.strip() != 'OK':
        sys.exit('QA failed to run: ' + res)
    qa = json.load(open(os.path.join(out, 'qa.json'), encoding='utf-8-sig'))
    got = {e['check'] for e in qa['errors']}
    for e in qa['errors']:
        print('  caught:', e['check'], '-', e['msg'])
    missing = [c for c in ('numbering', 'calc_alignment') if c not in got]
    hang = any('wider than its number column' in e['msg'] for e in qa['errors'])
    if not hang:
        missing.append('numbering (number wider than its column)')
    print('PASS' if not missing else 'FAIL: not caught: ' + ', '.join(missing))
    sys.exit(1 if missing else 0)


if __name__ == '__main__':
    main()
