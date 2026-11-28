"""OpenRouter over its REST API (standard library only): one prepaid account that reaches Claude, Gemini and others.

Galley's tiers map to Claude models here as they do with an Anthropic key, so switching between an Anthropic key
and an OpenRouter key changes nothing for the designer. Errors carry OpenRouter's own reason.
"""
import base64
import json
import mimetypes
import urllib.error
import urllib.request

API = 'https://openrouter.ai/api/v1'
# Galley tier model (Anthropic name) -> OpenRouter name; the first one that answers wins
TIER = {
    'claude-opus-5-5': ['anthropic/claude-opus-5.5', 'anthropic/claude-sonnet-5.5'],
    'claude-sonnet-5-5': ['anthropic/claude-sonnet-5.5', 'anthropic/claude-sonnet-5'],
    'claude-fable-5-2': ['anthropic/claude-fable-5.2', 'anthropic/claude-opus-5.5'],
}
VISION = ['anthropic/claude-sonnet-5.5', 'anthropic/claude-sonnet-5']  # for one-shot jobs like the brainstorm


class OpenRouterError(Exception):
    code = None


def _error(code, raw):
    try:
        msg = json.loads(raw)['error']['message']
    except (ValueError, KeyError, TypeError):
        msg = raw[:300] or 'error %s' % code
    if code == 401:
        msg = 'The OpenRouter key was refused. Check it in Settings.'
    elif code == 402:
        msg = 'The OpenRouter balance is used up. Top up at openrouter.ai/credits. (%s)' % msg
    e = OpenRouterError('OpenRouter said: %s' % msg if code not in (401,) else msg)
    e.code = code
    return e


def call(key, body, timeout=300):
    req = urllib.request.Request(API + '/chat/completions', method='POST', data=json.dumps(body).encode(),
                                 headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', 'X-Title': 'Galley'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        raise _error(e.code, e.read().decode('utf-8', 'replace')) from e
    except urllib.error.URLError as e:
        raise OpenRouterError('Cannot reach OpenRouter. Check the internet connection.') from e
    except (TimeoutError, OSError) as e:
        raise OpenRouterError('OpenRouter took too long to answer. Try again.') from e
    if out.get('error'):  # some failures come back as 200 with an error object
        raise _error(out['error'].get('code') or 500, json.dumps(out))
    return out


def complete(key, models, body, timeout=300):
    """try the models in order; move on only when a model is missing or unavailable, not on account problems"""
    last = None
    for m in models:
        try:
            return call(key, dict(body, model=m), timeout)
        except OpenRouterError as e:
            last = e
            if e.code not in (400, 404, 502, 503):
                raise
    raise last


def image_url(path):
    mt = mimetypes.guess_type(path)[0] or 'image/png'
    with open(path, 'rb') as f:
        return {'type': 'image_url', 'image_url': {'url': 'data:%s;base64,%s' % (mt, base64.b64encode(f.read()).decode('ascii'))}}


def from_gemini_parts(parts):
    """the brainstorm builds Gemini-style parts; turn them into OpenAI-style content"""
    out = []
    for p in parts:
        if 'text' in p:
            out.append({'type': 'text', 'text': p['text']})
        elif 'inline_data' in p:
            d = p['inline_data']
            out.append({'type': 'image_url', 'image_url': {'url': 'data:%s;base64,%s' % (d['mime_type'], d['data'])}})
    return out


def generate_json(key, system, parts, temperature=1.0):
    r = complete(key, VISION, {'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': from_gemini_parts(parts)}],
                               'temperature': temperature, 'max_tokens': 8000, 'response_format': {'type': 'json_object'}})
    text = (r['choices'][0]['message'].get('content') or '').strip()
    try:
        return json.loads(text)
    except ValueError:
        a, b = text.find('{'), text.rfind('}')
        if a >= 0 and b > a:
            return json.loads(text[a:b + 1])
        raise OpenRouterError('The AI did not return a design.')
