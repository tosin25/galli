"""HTTP handlers for the copilot window (served by ui/server.py under /api/c/...).

Each handler returns (status_code, json_body). InDesign work goes through bridge.py; nothing here starts InDesign.
"""
import json
import os
import re
import sys
import time

from . import assistant, brainstorm, bridge, drafts, images, mapping, paths, settings

sys.path.insert(0, os.path.join(paths.RES, 'ingest'))
import ingest  # noqa: E402

G = paths.RES
WORK = paths.WORK
BOARD = os.path.join(WORK, 'refs', 'board')
LINKS = os.path.join(BOARD, 'links.json')
IMG_EXT = ('.png', '.jpg', '.jpeg', '.gif', '.webp')


def _content_summary():
    cj = os.path.join(WORK, 'content.json')
    if not os.path.exists(cj):
        return None
    with open(cj, encoding='utf-8') as f:
        c = json.load(f)
    counts = {}
    for b in c['blocks']:
        counts[b['type']] = counts.get(b['type'], 0) + 1
    review = ''
    rp = os.path.join(WORK, 'ingest_report.txt')
    if os.path.exists(rp):
        with open(rp, encoding='utf-8') as f:
            review = f.read()
    return {'meta': c['meta'], 'counts': counts, 'report': review, 'updated': os.path.getmtime(cj)}


def _board():
    os.makedirs(BOARD, exist_ok=True)
    imgs = sorted((f for f in os.listdir(BOARD) if f.lower().endswith(IMG_EXT)), key=lambda f: -os.path.getmtime(os.path.join(BOARD, f)))
    links = []
    if os.path.exists(LINKS):
        with open(LINKS, encoding='utf-8') as f:
            links = json.load(f)
    return {'images': imgs, 'links': links}


def get(path, q):
    if path == 'status':
        st = bridge.status()
        if st.get('connected') and not st.get('busy') and st.get('docs'):
            saved = {}
            try:
                saved = json.loads(st.get('mapping') or '{}')
            except ValueError:
                pass
            st['suggestion'] = mapping.suggest(st.get('paragraphStyles', []), st.get('characterStyles', []), saved)
            st['savedMapping'] = saved
        return 200, st
    if path == 'drafts':
        return 200, drafts.state()
    if path == 'state':
        return 200, {'content': _content_summary(), 'board': _board(), 'settings': settings.public(), 'models': assistant.public_models(),
                     'version': paths.version(), 'frozen': paths.FROZEN}
    return 404, {'error': 'not found'}


def post(path, q, body, filename):
    data = {}
    if body and not filename:
        try:
            data = json.loads(body)
        except ValueError:
            data = {}
    try:
        if path == 'check':
            return 200, bridge.check_document()
        if path == 'goto':
            return 200, bridge.go_to_page(data.get('page', ''))
        if path == 'mapping':
            return 200, bridge.save_mapping(data.get('mapping') or {})
        if path == 'flow':
            cj = os.path.join(WORK, 'content.json')
            if not os.path.exists(cj):
                return 400, {'error': 'Choose a manuscript first.'}
            m = data.get('mapping') or {}
            bridge.save_mapping(m)
            res = bridge.flow_manuscript(cj, m)
            if res.get('ok'):
                res['qa'] = bridge.check_document()
            return 200, res
        if path == 'drafts':
            r = drafts.start(data.get('styles') or ['bright', 'classic', 'modern'])
            return (400 if r.get('error') else 200), r
        if path == 'brainstorm':
            refs = [os.path.join(BOARD, os.path.basename(n)) for n in data.get('refs', []) if os.path.isfile(os.path.join(BOARD, os.path.basename(n)))]
            r = brainstorm.run(refs)
            return (400 if r.get('error') and not r.get('designs') else 200), r
        if path == 'images/plan':
            r = images.plan()
            return (400 if r.get('error') else 200), r
        if path == 'images/generate':
            refs = [os.path.join(BOARD, os.path.basename(n)) for n in data.get('refs', []) if os.path.isfile(os.path.join(BOARD, os.path.basename(n)))]
            r = images.generate(data.get('ids') or [], data.get('descriptions'), refs)
            return (400 if r.get('error') else 200), r
        if path == 'images/place':
            return 200, images.place(data.get('ids'))
        if path == 'drafts/open':
            return 200, drafts.open_draft(data.get('id', ''))
        if path == 'apply_all':
            return 200, bridge.redefine_style_from_selection()
        if path == 'restyle':
            return 200, bridge.update_paragraph_style(data.get('style', ''), data.get('changes') or {})
        if path == 'manuscript':
            # a .docx sent from the copilot (or the sample) -> work/content.json
            if q.get('sample'):
                src = os.path.join(G, 'samples', 'plants_chapter.docx')
            else:
                if not filename.lower().endswith('.docx'):
                    return 400, {'error': 'Please choose a Word .docx file.'}
                d = os.path.join(WORK, 'refs', 'manuscript')
                os.makedirs(d, exist_ok=True)
                src = os.path.join(d, os.path.basename(filename))
                with open(src, 'wb') as f:
                    f.write(body)
            # read it in-process (the installed app has no separate Python to run ingest.py with)
            try:
                ingest.run(src, WORK)
            except Exception as e:  # noqa: BLE001 - a broken .docx should come back as a readable message
                return 500, {'error': 'Could not read the manuscript: %s' % e}
            return 200, {'content': _content_summary()}
        if path == 'refs':
            if filename:
                if not filename.lower().endswith(IMG_EXT):
                    return 400, {'error': 'Images only (PNG, JPG, GIF, WebP).'}
                os.makedirs(BOARD, exist_ok=True)
                name = re.sub(r'[^\w.\- ]', '_', os.path.basename(filename))
                with open(os.path.join(BOARD, name), 'wb') as f:
                    f.write(body)
            return 200, _board()
        if path == 'refs/delete':
            name = os.path.basename(data.get('name', ''))
            p = os.path.join(BOARD, name)
            if name and os.path.isfile(p):
                os.remove(p)
            return 200, _board()
        if path == 'links':
            b = _board()
            url = (data.get('url') or '').strip()
            if data.get('remove'):
                b['links'] = [x for x in b['links'] if x['url'] != data['remove']]
            elif re.match(r'^https?://', url):
                b['links'].insert(0, {'url': url, 'label': data.get('label') or re.sub(r'^https?://(www\.)?', '', url)[:60], 'added': time.time()})
            os.makedirs(BOARD, exist_ok=True)
            with open(LINKS, 'w', encoding='utf-8') as f:
                json.dump(b['links'], f, indent=1)
            return 200, _board()
        if path == 'settings':
            vals = {}
            if 'api_key' in data:
                vals['anthropic_api_key'] = data['api_key'].strip() or None
            if 'gemini_key' in data:
                vals['gemini_api_key'] = data['gemini_key'].strip() or None
            for k in ('model', 'pin_on_top'):
                if k in data:
                    vals[k] = data[k]
            return 200, settings.update(vals)
        if path == 'chat':
            refs = [os.path.join(BOARD, os.path.basename(n)) for n in data.get('refs', []) if os.path.isfile(os.path.join(BOARD, os.path.basename(n)))]
            hist = [{'role': h['role'], 'content': h['content']} for h in data.get('history', [])[-16:] if h.get('role') in ('user', 'assistant') and h.get('content')]
            model = data.get('model') or settings.get('model', 'galley')
            return 200, assistant.chat(model, hist, data.get('text', ''), refs)
    except bridge.InDesignNotRunning as e:
        return 409, {'error': str(e)}
    except Exception as e:  # noqa: BLE001 - every failure goes back to the UI as readable text
        return 500, {'error': '%s: %s' % (type(e).__name__, e)}
    return 404, {'error': 'not found'}
