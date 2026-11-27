"""Galley server: accounts, the AI key kept in one place, and daily usage limits per plan.

The desktop app never holds the company AI key. A user signs in with a Galley account token (gly_...), and the
app sends its AI requests here; the server checks the token and the plan's daily limit, adds the real key and
forwards the request to Google AI. Standard library only (http.server + sqlite3), so it runs on any small host.

Run:     GOOGLE_API_KEY=... python server/galley_server.py serve [--port 8790]
Users:   python server/galley_server.py add-user designer@example.com --plan pro     (prints the token to give them)
         python server/galley_server.py list
         python server/galley_server.py set-plan designer@example.com free
         python server/galley_server.py revoke designer@example.com
Put it behind HTTPS (any host's TLS proxy) before real users connect.
"""
import argparse
import datetime
import json
import os
import secrets
import sqlite3
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GOOGLE = 'https://generativelanguage.googleapis.com/v1beta'
DB = os.environ.get('GALLEY_SERVER_DB', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'galley.db'))
# daily limits per plan: AI requests (chat steps, brainstorms) and generated pictures
PLANS = {'free': {'calls': 60, 'images': 0}, 'pro': {'calls': 1500, 'images': 60}, 'team': {'calls': 5000, 'images': 300}}
_lock = threading.Lock()


def db():
    c = sqlite3.connect(DB)
    c.execute('CREATE TABLE IF NOT EXISTS users (email TEXT PRIMARY KEY, token TEXT UNIQUE, plan TEXT, created TEXT, active INTEGER DEFAULT 1)')
    c.execute('CREATE TABLE IF NOT EXISTS usage (token TEXT, day TEXT, calls INTEGER DEFAULT 0, images INTEGER DEFAULT 0, PRIMARY KEY (token, day))')
    return c


def today():
    return datetime.date.today().isoformat()


def user_for(token):
    with db() as c:
        r = c.execute('SELECT email, plan FROM users WHERE token=? AND active=1', (token,)).fetchone()
    return {'email': r[0], 'plan': r[1]} if r else None


def usage(token):
    with db() as c:
        r = c.execute('SELECT calls, images FROM usage WHERE token=? AND day=?', (token, today())).fetchone()
    return {'calls': r[0], 'images': r[1]} if r else {'calls': 0, 'images': 0}


def take(token, plan, kind):
    """count one request of this kind; False when the plan's daily limit is used up"""
    limit = PLANS.get(plan, PLANS['free'])[kind]
    with _lock, db() as c:
        c.execute('INSERT OR IGNORE INTO usage (token, day) VALUES (?, ?)', (token, today()))
        used = c.execute('SELECT %s FROM usage WHERE token=? AND day=?' % kind, (token, today())).fetchone()[0]
        if used >= limit:
            return False
        c.execute('UPDATE usage SET %s=%s+1 WHERE token=? AND day=?' % (kind, kind), (token, today()))
    return True


class Handler(BaseHTTPRequestHandler):
    server_version = 'Galley/1'

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _auth(self):
        h = self.headers.get('Authorization', '')
        token = h[7:].strip() if h.startswith('Bearer ') else ''
        u = user_for(token) if token else None
        if not u:
            self._send(401, {'error': {'message': 'This Galley account is not recognised. Check the account key in Settings.'}})
        return token, u

    def do_GET(self):
        self._route('GET')

    def do_POST(self):
        self._route('POST')

    def _route(self, method):
        if self.path == '/health':
            return self._send(200, {'ok': True})
        token, u = self._auth()
        if not u:
            return
        if self.path == '/v1/me':
            return self._send(200, {'email': u['email'], 'plan': u['plan'], 'today': usage(token), 'limits': PLANS.get(u['plan'], PLANS['free'])})
        if not self.path.startswith('/v1/google/'):
            return self._send(404, {'error': {'message': 'unknown address'}})
        sub = '/' + self.path[len('/v1/google/'):]
        body = self.rfile.read(int(self.headers.get('Content-Length') or 0)) if method == 'POST' else None
        if method == 'POST':  # model listings are free; generation is counted
            kind = 'images' if 'image' in sub.split(':')[0] else 'calls'
            if not take(token, u['plan'], kind):
                what = 'pictures' if kind == 'images' else 'AI requests'
                return self._send(429, {'error': {'message': 'Today\'s %s on the %s plan are used up. They reset tomorrow, or upgrade the plan.' % (what, u['plan'])}})
        key = os.environ.get('GOOGLE_API_KEY', '')
        if not key:
            return self._send(503, {'error': {'message': 'The Galley server has no AI key configured.'}})
        req = urllib.request.Request(GOOGLE + sub, data=body, method=method, headers={'x-goog-api-key': key, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=280) as r:
                return self._send(r.status, json.loads(r.read().decode('utf-8')))
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read().decode('utf-8'))
            except ValueError:
                detail = {'error': {'message': 'AI service error %s' % e.code}}
            if e.code in (401, 403) or 'API key' in json.dumps(detail):  # never pass on "the server's key is bad"
                sys.stderr.write('upstream refused the server key (%s)\n' % e.code)
                return self._send(502, {'error': {'message': 'The Galley server could not use its AI key. Tell the Galley team.'}})
            return self._send(e.code, detail)
        except urllib.error.URLError:
            return self._send(502, {'error': {'message': 'The Galley server cannot reach the AI service.'}})

    def log_message(self, fmt, *args):  # no request bodies or tokens in logs
        sys.stderr.write('%s %s\n' % (self.command, self.path.split('?')[0]))


def main(argv=None):
    ap = argparse.ArgumentParser(description='Galley server')
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('serve')
    s.add_argument('--port', type=int, default=int(os.environ.get('PORT', 8790)))
    s.add_argument('--host', default='127.0.0.1')
    a = sub.add_parser('add-user')
    a.add_argument('email')
    a.add_argument('--plan', default='free', choices=sorted(PLANS))
    sub.add_parser('list')
    p = sub.add_parser('set-plan')
    p.add_argument('email')
    p.add_argument('plan', choices=sorted(PLANS))
    r = sub.add_parser('revoke')
    r.add_argument('email')
    args = ap.parse_args(argv)
    if args.cmd == 'serve':
        print('Galley server on http://%s:%d  (db %s)' % (args.host, args.port, DB), flush=True)
        ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
    elif args.cmd == 'add-user':
        token = 'gly_' + secrets.token_urlsafe(24)
        with db() as c:
            c.execute('INSERT OR REPLACE INTO users VALUES (?, ?, ?, ?, 1)', (args.email.lower(), token, args.plan, today()))
        print(token)
    elif args.cmd == 'list':
        with db() as c:
            for e, t, pl, cr, act in c.execute('SELECT * FROM users ORDER BY created'):
                print('%-36s %-5s %s %s used today: %s' % (e, pl, cr, 'active' if act else 'revoked', usage(t)))
    elif args.cmd == 'set-plan':
        with db() as c:
            c.execute('UPDATE users SET plan=? WHERE email=?', (args.plan, args.email.lower()))
    elif args.cmd == 'revoke':
        with db() as c:
            c.execute('UPDATE users SET active=0 WHERE email=?', (args.email.lower(),))


if __name__ == '__main__':
    main()
