"""Per-user copilot settings, kept on this machine only: %APPDATA%\\Galley\\settings.json (outside the project folder,
so an API key never ends up in git or in a shared project)."""
import json
import os

PATH = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'Galley', 'settings.json')


def load():
    try:
        with open(PATH, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def get(key, default=None):
    return load().get(key, default)


def update(values):
    s = load()
    for k, v in values.items():
        if v is None:
            s.pop(k, None)
        else:
            s[k] = v
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    with open(PATH, 'w', encoding='utf-8') as f:
        json.dump(s, f, indent=1)
    return public()


def public():
    """Settings safe to send to the UI: the key is masked."""
    s = load()
    k = s.get('anthropic_api_key') or ''
    return {'model': {'claude-opus-5-5': 'galley', 'claude-sonnet-5-5': 'galley-fast', 'claude-haiku-5-5': 'galley-fast', 'claude-fable-5-2': 'galley-pro'}.get(s.get('model', 'galley'), s.get('model', 'galley')), 'has_key': bool(k or os.environ.get('ANTHROPIC_API_KEY')),
            'key_hint': ('…' + k[-4:]) if k else ('from environment' if os.environ.get('ANTHROPIC_API_KEY') else ''),
            'pin_on_top': s.get('pin_on_top', True),
            'has_gemini': bool(s.get('gemini_api_key')), 'gemini_hint': ('…' + s['gemini_api_key'][-4:]) if s.get('gemini_api_key') else '',
            'has_openrouter': bool(s.get('openrouter_api_key')), 'openrouter_hint': ('…' + s['openrouter_api_key'][-4:]) if s.get('openrouter_api_key') else ''}
