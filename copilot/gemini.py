"""Google Gemini over its REST API (standard library only): the free-tier option for testing Galley's AI.

Used for the reference brainstorm (it can look at images). The model is picked from what the key can use,
preferring a fast "flash" model, so nothing breaks when Google renames models. Free-tier note: Google may use
what is sent to improve its products, so test with your own pins and samples, not client manuscripts.
"""
import base64
import json
import mimetypes
import os
import re
import urllib.error
import urllib.request

API = 'https://generativelanguage.googleapis.com/v1beta'
_model_cache = {}


class GeminiError(Exception):
    pass


def server_url():
    """the Galley server, for account keys (gly_...): Settings, then GALLEY_SERVER, then a server on this machine"""
    from . import settings
    return (settings.get('server_url') or os.environ.get('GALLEY_SERVER') or 'http://127.0.0.1:8790').rstrip('/')


def _call(method, path, key, body=None, timeout=180):
    account = key.startswith('gly_')  # a Galley account: the server holds the AI key and the limits
    url, headers = (server_url() + '/v1/google' + path, {'Authorization': 'Bearer ' + key}) if account else (API + path, {'x-goog-api-key': key})
    headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, method=method, headers=headers, data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        raise _http_error(e, account) from e
    except urllib.error.URLError as e:
        raise GeminiError('Cannot reach the Galley server.' if account else 'Cannot reach Google AI. Check the internet connection.') from e
    except (TimeoutError, OSError) as e:  # a slow answer: say so instead of crashing
        raise GeminiError('The AI service took too long to answer. Try again.') from e


def _http_error(e, account):
    """a friendly GeminiError for an HTTP error, carrying its code"""
    raw = e.read().decode('utf-8', 'replace')
    if account:
        try:
            msg = json.loads(raw)['error']['message']
        except (ValueError, KeyError, TypeError):
            msg = 'Galley server error %s.' % e.code
    elif e.code in (401, 403):
        msg = 'The Google AI key was refused. Check it in Settings.'
    elif e.code == 429:
        msg = 'The free Google AI limit was reached. Wait a minute and try again.'
    elif e.code == 503:
        msg = 'Google AI is busy right now. Try again in a minute.'
    else:
        msg = 'Google AI error %s: %s' % (e.code, raw[:400])
    err = GeminiError(msg)
    err.code = e.code
    return err


def models(key):
    """usable chat models for this key, best first (cached): plain "gemini-<version>-flash" models, newest first,
    then Google's own alias; never special-purpose ones (image, speech, previews of other products)"""
    if key in _model_cache:
        return _model_cache[key]
    names = {m['name'].split('/', 1)[1] for m in _call('GET', '/models?pageSize=200', key).get('models', [])
             if 'generateContent' in m.get('supportedGenerationMethods', [])}
    plain = [(tuple(int(x) for x in m.group(1).split('.')), n) for n in names for m in [re.fullmatch(r'gemini-(\d+(?:\.\d+)?)-flash', n)] if m]
    order = list(dict.fromkeys([n for _, n in sorted(plain, reverse=True)] + [n for n in ('gemini-flash-latest',) if n in names]))
    if not order:
        raise GeminiError('No usable Google AI model for this key.')
    _model_cache[key] = order
    return order


def pick_model(key):
    return models(key)[0]


def generate(key, body, timeout=240):
    """generateContent on the best model this key can use; a model that refuses (not open to the key, busy) is
    skipped and the one that works is remembered. A slow answer is waited for, not retried on another model."""
    order = models(key)
    last = None
    for n in list(order)[:5]:
        try:
            r = _call('POST', '/models/%s:generateContent' % n, key, body, timeout=timeout)
            if order[0] != n:  # remember the one that works
                order.remove(n)
                order.insert(0, n)
            return r
        except GeminiError as e:
            last = e
            if getattr(e, 'code', None) not in (400, 403, 404, 503):
                raise
    raise last


def image_part(path):
    mt = mimetypes.guess_type(path)[0] or 'image/png'
    with open(path, 'rb') as f:
        return {'inline_data': {'mime_type': mt, 'data': base64.b64encode(f.read()).decode('ascii')}}


def generate_json(key, system, parts, temperature=1.0):
    """one request that must answer with JSON; returns the parsed object"""
    body = {'system_instruction': {'parts': [{'text': system}]},
            'contents': [{'role': 'user', 'parts': parts}],
            'generationConfig': {'temperature': temperature, 'responseMimeType': 'application/json'}}
    r = generate(key, body)
    cands = r.get('candidates') or []
    if not cands:
        raise GeminiError('Google AI returned nothing (%s).' % (r.get('promptFeedback') or 'no reason given'))
    text = ''.join(p.get('text', '') for p in cands[0].get('content', {}).get('parts', []))
    try:
        return json.loads(text)
    except ValueError:
        # tolerate a fenced or chatty answer: take the outermost JSON object
        a, b = text.find('{'), text.rfind('}')
        if a >= 0 and b > a:
            return json.loads(text[a:b + 1])
        raise GeminiError('Google AI did not return a design.')
