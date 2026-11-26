"""Smoke test for the copilot path ("continue in my style"). Needs InDesign open.

    python tests/smoke_copilot.py                              # the plants chapter
    python tests/smoke_copilot.py work/maths/content.json      # the maths chapter (numbers, calculations, diagrams)

1. builds the designer fixture (samples/make_designer_sample.jsx) -> work/designer_sample.indd
2. reads status and suggests a style mapping; checks the key roles are matched
3. flows work/content.json into the document with that mapping
4. runs QA, exports previews to work/copilot/previews, and fails on any QA error
Only the fixture document is closed or changed; other open documents are left alone.
"""
import json
import os
import shutil
import sys

G = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, G)
from copilot import bridge, mapping  # noqa: E402

EXPECT = {'chapter_title': 'Chapter Head', 'h2': 'A Head', 'body': 'Body Text', 'example_head': 'Example Title',
          'exercise_head': 'Exercise Title', 'question': 'Exercise Q', 'note': 'Tip'}


def main():
    fails = []
    fixture = os.path.join(G, 'work', 'designer_sample.indd')
    bridge.js("for (var i = app.documents.length - 1; i >= 0; i--) if (app.documents[i].name == 'designer_sample.indd') app.documents[i].close(SaveOptions.NO); return __j({ok:true});")
    r = bridge.run_file(os.path.join(G, 'samples', 'make_designer_sample.jsx'), {'galley_out': fixture})
    if r.strip() != 'OK':
        sys.exit('fixture failed: ' + r)
    st = bridge.status()
    sug = mapping.suggest(st['paragraphStyles'], st['characterStyles'])
    m = {x['role']: x['style'] for x in sug['paragraph'] + sug['character'] if x['style']}
    for role, want in EXPECT.items():
        if m.get(role) != want:
            fails.append('mapping %s -> %r, expected %r' % (role, m.get(role), want))
    if not os.path.exists(os.path.join(G, 'work', 'content.json')):
        os.system('python "%s" "%s" "%s"' % (os.path.join(G, 'ingest', 'ingest.py'), os.path.join(G, 'samples', 'plants_chapter.docx'), os.path.join(G, 'work')))
    content = sys.argv[1] if len(sys.argv) > 1 else os.path.join(G, 'work', 'content.json')
    flow = bridge.flow_manuscript(os.path.abspath(content), m)
    if not flow.get('ok'):
        sys.exit('flow failed: %s' % flow)
    print('flowed: pages %s-%s (%d added), overset=%s' % (flow['firstPage'], flow['lastPage'], flow['pagesAdded'], flow['overset']))
    for line in flow.get('log', []):
        print('  log:', line)
        if line.startswith('image'):
            fails.append(line)
    out = os.path.join(G, 'work', 'copilot')
    shutil.rmtree(os.path.join(out, 'previews'), ignore_errors=True)
    r = bridge.run_file(os.path.join(G, 'indesign', 'qa_export.jsx'), {'galley_doc': '', 'galley_out': out, 'galley_export': '1'})
    if r.strip() != 'OK':
        sys.exit('qa failed: ' + r)
    qa = json.load(open(os.path.join(out, 'qa.json'), encoding='utf-8-sig'))
    print('QA: %d pages, %d errors, %d warnings' % (qa['pages'], len(qa['errors']), len(qa['warnings'])))
    for e in qa['errors']:
        fails.append('QA p%s: %s' % (e['page'], e['msg']))
    for w in qa['warnings']:
        print('  note p%s: %s' % (w['page'], w['msg']))
    if flow['overset']:
        fails.append('overset text after flow')
    # the promise to designers: after a flow (and a Check), ONE undo removes everything Galley added
    bridge.check_document()
    u = bridge.js("var d = app.activeDocument, n = d.undoName, b = d.pages.length; d.undo(); return __j({name: n, before: b, after: d.pages.length});")
    if 'name' not in u:
        sys.exit('undo check failed: %s' % u)
    print('undo: top step %r, pages %s -> %s' % (u['name'], u['before'], u['after']))
    if u['name'] != 'Galley: flow manuscript' or u['after'] != 1:
        fails.append('one undo should remove the whole flow (got %s)' % u)
    print('\n'.join(['FAIL ' + f for f in fails]) or 'PASS')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
