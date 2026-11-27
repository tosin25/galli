"""Google Gemini over its REST API (standard library only): the free-tier option for testing Galley's AI.

Used for the reference brainstorm (it can look at images). The model is picked from what the key can use,
preferring a fast "flash" model, so nothing breaks when Google renames models. Free-tier note: Google may use
what is sent to improve its products, so test with your own pins and samples, not client manuscripts.
"""
import base64
import json
import mimetypes
import urllib.error
import urllib.request

API = 'https://generativelanguage.googleapis.com/v1beta'
_model_cache = {}


class GeminiError(Exception):
    pass


def _call(method, path, key, body=None, timeout=180):
    req = urllib.request.Request(API + path, method=method, headers={'x-goog-api-key': key, 'Content-Type': 'application/json'},
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', 'replace')[:400]
        if e.code in (401, 403):
            raise GeminiError('The Google AI key was refused. Check it in Settings.') from e
        if e.code == 429:
            raise GeminiError('The free Google AI limit was reached. Wait a minute and try again.') from e
        raise GeminiError('Google AI error %s: %s' % (e.code, detail)) from e
    except urllib.error.URLError as e:
        raise GeminiError('Cannot reach Google AI. Check the internet connection.') from e


def pick_model(key):
    """a current multimodal 'flash' model this key may use (cached)"""
    if key in _model_cache:
        return _model_cache[key]
    models = _call('GET', '/models?pageSize=200', key).get('models', [])
    ok = [m for m in models if 'generateContent' in m.get('supportedGenerationMethods', [])]
    names = [m['name'].split('/', 1)[1] for m in ok]

    def score(n):
        s = 0
        if 'flash' in n:
            s += 100
        if 'image' in n or 'tts' in n or 'live' in n or 'embedding' in n or 'lite' in n or 'thinking' in n:
            s -= 200  # special-purpose variants
        if 'preview' in n or 'exp' in n:
            s -= 20
        digits = [int(x) for x in __import__('re').findall(r'\d+', n)[:2]]
        return s + (digits[0] * 10 + (digits[1] if len(digits) > 1 else 0) if digits else 0)
    if not names:
        raise GeminiError('No usable Google AI model for this key.')
    best = max(names, key=score)
    _model_cache[key] = best
    return best


def image_part(path):
    mt = mimetypes.guess_type(path)[0] or 'image/png'
    with open(path, 'rb') as f:
        return {'inline_data': {'mime_type': mt, 'data': base64.b64encode(f.read()).decode('ascii')}}


def generate_json(key, system, parts, temperature=1.0):
    """one request that must answer with JSON; returns the parsed object"""
    model = pick_model(key)
    body = {'system_instruction': {'parts': [{'text': system}]},
            'contents': [{'role': 'user', 'parts': parts}],
            'generationConfig': {'temperature': temperature, 'responseMimeType': 'application/json'}}
    r = _call('POST', '/models/%s:generateContent' % model, key, body)
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
