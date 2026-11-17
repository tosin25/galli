"""Galley local UI server (Python standard library only).

    python ui/server.py            -> http://localhost:8765

Serves ui/index.html, keeps the designer's checklist (uploads + parameters) in work/project.json,
writes style/custom.json from the checklist, and runs galley.ps1 steps in the background.
Binds to 127.0.0.1 only.
"""
import json
import os
import re
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from copilot import copilot_api  # noqa: E402  (copilot routes: /copilot, /api/c/...)

G = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK, OUT, STYLE = os.path.join(G, 'work'), os.path.join(G, 'out'), os.path.join(G, 'style')
PROJECT = os.path.join(WORK, 'project.json')
PORT = 8765

# the reference checklist for "Style from references"; required items gate the variants step
CHECKLIST = [
    ('manuscript', 'Manuscript (.docx)', True, 'The full chapter or book text, in Word.'),
    ('trim', 'Trim size', True, 'Finished page size in mm. Filled in below.'),
    ('opener', 'Chapter / unit opener', True, 'A page you like for how a chapter starts.'),
    ('body', 'Body page', True, 'A typical text page: column, headings, spacing.'),
    ('example', 'Example box', True, 'How worked examples are boxed and labelled.'),
    ('exercise', 'Exercise box', True, 'Questions, answer lines, option layout.'),
    ('folio', 'Page number / folio', True, 'Where and how page numbers sit.'),
    ('fonts', 'Fonts', True, 'Heading and body typefaces. Filled in below.'),
    ('palette', 'Colour palette', True, 'Brand or series colours. Filled in below.'),
    ('notes', 'Notes / callouts', False, '"Did you know?", tips, warnings.'),
    ('header', 'Running header', False, 'Book or chapter name at the top of pages.'),
    ('sidetab', 'Side tab', False, 'Coloured thumb tab on the page edge.'),
    ('table', 'Table style', False, 'Header row, rules, shading.'),
    ('characters', 'Characters / mascots', False, 'Recurring characters that appear in the book.'),
    ('illustrations', 'Illustration style', False, 'Spot art and diagrams style.'),
    ('cover', 'Cover or series look', False, 'For overall mood only.'),
]
FILLED_BY_FORM = {'trim', 'fonts', 'palette'}

job = {'running': False, 'step': '', 'log': '', 'code': None}


def load_project():
    if os.path.exists(PROJECT):
        with open(PROJECT, encoding='utf-8') as f:
            return json.load(f)
    return {'mode': 'references', 'refs': {}, 'params': {}, 'picked': ''}


def save_project(p):
    os.makedirs(WORK, exist_ok=True)
    with open(PROJECT, 'w', encoding='utf-8') as f:
        json.dump(p, f, indent=1)


def styles():
    out = []
    for fn in sorted(os.listdir(STYLE)):
        if fn.endswith('.json'):
            with open(os.path.join(STYLE, fn), encoding='utf-8') as f:
                s = json.load(f)
            out.append({'id': s['id'], 'name': s['name'], 'description': s.get('description', ''), 'trim': s['trim'],
                        'fonts': s['fonts'], 'palette': s['palette'], 'type': s['type']})
    return out


def state():
    p = load_project()
    items = []
    for key, label, req, hint in CHECKLIST:
        if key in FILLED_BY_FORM:
            done = bool(p['params'].get(key))
        else:
            done = bool(p['refs'].get(key))
        items.append({'key': key, 'label': label, 'required': req, 'hint': hint, 'done': done,
                      'files': p['refs'].get(key, []), 'form': key in FILLED_BY_FORM})
    content = None
    cj = os.path.join(WORK, 'content.json')
    if os.path.exists(cj):
        with open(cj, encoding='utf-8') as f:
            c = json.load(f)
        counts = {}
        for b in c['blocks']:
            counts[b['type']] = counts.get(b['type'], 0) + 1
        rep = ''
        rp = os.path.join(WORK, 'ingest_report.txt')
        if os.path.exists(rp):
            with open(rp, encoding='utf-8') as f:
                rep = f.read()
        content = {'meta': c['meta'], 'counts': counts, 'report': rep}
    variants = []
    vj = os.path.join(OUT, 'variants.json')
    if os.path.exists(vj):
        with open(vj, encoding='utf-8-sig') as f:
            v = json.load(f)
        variants = v if isinstance(v, list) else [v]
    return {'project': p, 'checklist': items, 'styles': styles(), 'content': content, 'variants': variants, 'job': job}


def run_step(step, extra):
    def worker():
        job.update(running=True, step=step, log='', code=None)
        cmd = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', os.path.join(G, 'galley.ps1'), step] + extra
        try:
            pr = subprocess.Popen(cmd, cwd=G, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
            for line in pr.stdout:
                job['log'] += line
            job['code'] = pr.wait()
        except Exception as e:  # noqa: BLE001 - surface any launch problem to the UI
            job['log'] += 'could not run: %s\n' % e
            job['code'] = 1
        job['running'] = False
    threading.Thread(target=worker, daemon=True).start()


def write_custom_style(p):
    """style/custom.json = the chosen base spec with the checklist's trim, fonts and palette applied"""
    base = p['params'].get('base') or 'bright'
    with open(os.path.join(STYLE, base + '.json'), encoding='utf-8') as f:
        s = json.load(f)
    s['id'], s['name'] = 'custom', 'Custom (from your references)'
    s['description'] = 'Built from the checklist: %s structure with your trim, fonts and palette.' % base
    pr = p['params']
    if pr.get('trim'):
        s['trim'] = {'width': float(pr['trim']['width']), 'height': float(pr['trim']['height'])}
    if pr.get('fonts'):
        s['fonts']['heading']['family'] = pr['fonts'].get('heading') or s['fonts']['heading']['family']
        s['fonts']['body']['family'] = pr['fonts'].get('body') or s['fonts']['body']['family']
    if pr.get('palette'):
        for k, v in pr['palette'].items():
            if re.match(r'^#[0-9a-fA-F]{6}$', v or ''):
                s['palette'][k] = v
    with open(os.path.join(STYLE, 'custom.json'), 'w', encoding='utf-8') as f:
        json.dump(s, f, indent=2)


TYPES = {'.html': 'text/html; charset=utf-8', '.json': 'application/json', '.png': 'image/png', '.pdf': 'application/pdf',
         '.txt': 'text/plain; charset=utf-8', '.md': 'text/plain; charset=utf-8', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.svg': 'image/svg+xml'}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype='application/json'):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def file(self, root, rel):
        path = os.path.normpath(os.path.join(root, unquote(rel)))
        if not path.startswith(root) or not os.path.isfile(path):
            return self.send(404, {'error': 'not found'})
        with open(path, 'rb') as f:
            self.send(200, f.read(), TYPES.get(os.path.splitext(path)[1].lower(), 'application/octet-stream'))

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ('/', '/index.html'):
            return self.file(os.path.join(G, 'ui'), 'index.html')
        if u.path in ('/copilot', '/copilot.html'):
            return self.file(os.path.join(G, 'ui'), 'copilot.html')
        if u.path.startswith('/api/c/'):
            code, body = copilot_api.get(u.path[7:], parse_qs(u.query))
            return self.send(code, body)
        if u.path.startswith('/refs/'):
            return self.file(os.path.join(WORK, 'refs', 'board'), u.path[6:])
        if u.path == '/api/state':
            return self.send(200, state())
        if u.path.startswith('/out/'):
            return self.file(OUT, u.path[5:])
        if u.path.startswith('/work/'):
            return self.file(WORK, u.path[6:])
        self.send(404, {'error': 'not found'})

    def body(self):
        n = int(self.headers.get('Content-Length') or 0)
        return self.rfile.read(n) if n else b''

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path.startswith('/api/c/'):
            code, body = copilot_api.post(u.path[7:], q, self.body(), unquote(self.headers.get('X-Filename', '')))
            return self.send(code, body)
        p = load_project()
        if u.path == '/api/upload':
            slot = q.get('slot', [''])[0]
            name = os.path.basename(unquote(self.headers.get('X-Filename', 'file')))
            if slot not in dict((c[0], 1) for c in CHECKLIST) or not name:
                return self.send(400, {'error': 'bad slot'})
            d = os.path.join(WORK, 'refs', slot)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, name), 'wb') as f:
                f.write(self.body())
            if slot == 'manuscript':
                p['refs']['manuscript'] = [name]
                p['manuscript_path'] = os.path.join(d, name)
            else:
                p['refs'].setdefault(slot, [])
                if name not in p['refs'][slot]:
                    p['refs'][slot].append(name)
            save_project(p)
            return self.send(200, state())
        if u.path == '/api/sample':
            p['refs']['manuscript'] = ['plants_chapter.docx (sample)']
            p['manuscript_path'] = os.path.join(G, 'samples', 'plants_chapter.docx')
            save_project(p)
            return self.send(200, state())
        if u.path == '/api/params':
            p['params'].update(json.loads(self.body() or b'{}'))
            p['mode'] = p['params'].pop('mode', p.get('mode', 'references'))
            save_project(p)
            return self.send(200, state())
        if u.path == '/api/run':
            if job['running']:
                return self.send(409, {'error': 'a step is already running'})
            req = json.loads(self.body() or b'{}')
            step = req.get('step')
            if step == 'ingest':
                ms = p.get('manuscript_path') or os.path.join(G, 'samples', 'plants_chapter.docx')
                run_step('ingest', ['-Manuscript', ms])
            elif step == 'variants':
                ids = [s for s in req.get('styles', []) if re.match(r'^[a-z0-9_-]+$', s)]
                if 'custom' in ids:
                    write_custom_style(p)
                run_step('variants', ['-Styles', ','.join(ids)] if ids else [])
            else:
                return self.send(400, {'error': 'unknown step'})
            return self.send(200, state())
        if u.path == '/api/pick':
            p['picked'] = json.loads(self.body() or b'{}').get('id', '')
            save_project(p)
            return self.send(200, state())
        self.send(404, {'error': 'not found'})


class Server(ThreadingHTTPServer):
    # On Windows, address reuse lets a second server share the port silently; refuse instead.
    allow_reuse_address = False


if __name__ == '__main__':
    try:
        srv = Server(('127.0.0.1', PORT), H)
    except OSError:
        sys.exit('Galley is already running on http://localhost:%d (close that window first).' % PORT)
    url = 'http://localhost:%d' % PORT
    print('Galley on ' + url + '  (copilot: ' + url + '/copilot)  Ctrl+C to stop')
    if '--no-browser' not in sys.argv:
        webbrowser.open(url + ('/copilot' if '--copilot' in sys.argv else ''))
    srv.serve_forever()
