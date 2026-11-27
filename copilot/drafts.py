"""Design drafts: build the chapter in several looks, show the first pages as JPEGs, open the one the designer picks.

Each draft is a full InDesign build (indesign/build_chapter.jsx) of the current manuscript (work/content.json)
in one style spec. The first pages are exported as JPEGs for the copilot to show side by side; picking a draft
simply opens its .indd in InDesign. For now the looks are the built-in specs in style/; the AI brainstorm
(references + manuscript -> 3 new specs) will write its specs to the same place and reuse everything here.
"""
import json
import os
import shutil
import threading
import time

from . import bridge, paths

DRAFTS = os.path.join(paths.OUT, 'drafts')
job = {'running': False, 'step': '', 'done': 0, 'total': 0, 'error': '', 'started': 0}
_lock = threading.Lock()

EXPORT_JS = r"""
var d = app.activeDocument, out = Folder(app.scriptArgs.getValue('g_out'));
with (app.jpegExportPreferences) {
  jpegExportRange = ExportRangeOrAllPages.EXPORT_RANGE; pageString = '1-' + Math.min(3, d.pages.length);
  exportResolution = 80; jpegQuality = JPEGOptionsQuality.HIGH; exportingSpread = false; antiAlias = true;
}
d.exportFile(ExportFormat.JPG, File(out + '/page.jpg'), false);
var n = d.pages.length, name = d.fullName.fsName; d.close(SaveOptions.YES);
return __j({ pages: n, indd: name });"""


def spec_path(style_id):
    for d in (paths.USER_STYLES, os.path.join(paths.RES, 'style')):
        p = os.path.join(d, style_id + '.json')
        if os.path.exists(p):
            return p
    return None


def _spec_meta(style_id):
    with open(spec_path(style_id), encoding='utf-8') as f:
        s = json.load(f)
    return {'id': style_id, 'name': s.get('name', style_id), 'description': s.get('description', ''),
            'trim': '%g x %g mm' % (s['trim']['width'], s['trim']['height'])}


def state():
    """drafts built so far (newest first) and the job progress"""
    out = []
    if os.path.isdir(DRAFTS):
        for sid in sorted(os.listdir(DRAFTS)):
            d = os.path.join(DRAFTS, sid)
            info = os.path.join(d, 'draft.json')
            if os.path.exists(info):
                with open(info, encoding='utf-8') as f:
                    out.append(json.load(f))
    out.sort(key=lambda x: x.get('order', 0))
    return {'drafts': out, 'job': dict(job)}


def _build_one(style_id, order, content):
    d = os.path.join(DRAFTS, style_id)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    # close a previous draft of this look if it is still open in InDesign (never other documents)
    bridge.js("var n = %s; for (var i = app.documents.length - 1; i >= 0; i--) if (app.documents[i].name == n) app.documents[i].close(SaveOptions.NO); return __j({});"
              % json.dumps(style_id + '_chapter.indd'))
    r = bridge.run_file(os.path.join(paths.RES, 'indesign', 'build_chapter.jsx'),
                        {'galley_content': content, 'galley_style': spec_path(style_id),
                         'galley_art': os.path.join(paths.RES, 'art'), 'galley_out': d})
    if r.strip() != 'OK':
        raise RuntimeError(r)
    res = bridge.js(EXPORT_JS, args={'g_out': d})
    if not isinstance(res, dict) or res.get('error'):
        raise RuntimeError('export: %s' % res)
    jpgs = sorted((f for f in os.listdir(d) if f.lower().endswith('.jpg')),
                  key=lambda f: int(''.join(ch for ch in f if ch.isdigit()) or 1))
    meta = _spec_meta(style_id)
    meta.update(order=order, pages=res['pages'], indd=res['indd'], previews=['/out/drafts/%s/%s' % (style_id, f) for f in jpgs],
                built=time.time())
    with open(os.path.join(d, 'draft.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=1)


def start(style_ids):
    """build the drafts in the background; the copilot polls state()"""
    content = os.path.join(paths.WORK, 'content.json')
    if not os.path.exists(content):
        return {'error': 'Choose a manuscript first (Continue tab).'}
    style_ids = [s for s in style_ids if spec_path(s)][:4]
    if not style_ids:
        return {'error': 'No looks to draft.'}
    if job['running']:
        return {'error': 'Drafts are already being made.'}
    shutil.rmtree(DRAFTS, ignore_errors=True)

    def work():
        with _lock:
            job.update(running=True, done=0, total=len(style_ids), error='', started=time.time())
            for k, sid in enumerate(style_ids):
                job['step'] = 'Drafting %s (%d of %d)' % (_spec_meta(sid)['name'], k + 1, len(style_ids))
                try:
                    _build_one(sid, k, content)
                except Exception as e:  # noqa: BLE001 - one failed look should not stop the others
                    job['error'] += '%s: %s\n' % (sid, str(e)[:300])
                job['done'] = k + 1
            job.update(running=False, step='')
    threading.Thread(target=work, daemon=True).start()
    return {'ok': True}


def open_draft(style_id):
    """open the picked draft's InDesign file and bring it to the front"""
    info = os.path.join(DRAFTS, os.path.basename(style_id), 'draft.json')
    if not os.path.exists(info):
        return {'error': 'That draft is not built yet.'}
    with open(info, encoding='utf-8') as f:
        meta = json.load(f)
    return bridge.js("var f = File(%s); if (!f.exists) return __j({ok:false, error:'file missing'}); var d = app.open(f); "
                     "try { app.activeWindow.activePage = d.pages[0]; } catch (e) {} return __j({ok:true, name: d.name});"
                     % json.dumps(meta['indd'].replace('\\', '/')))
