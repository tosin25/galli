"""Galley copilot chat: a model that works on the open InDesign document through a small set of tools.

The layout itself is done by Galley's deterministic scripts (bridge.py); the model reads the request, decides
which tool to use, and explains results. Providers are pluggable: Anthropic (Claude) works today; OpenAI,
DeepSeek and a future Galley model register here when they are added, without touching the UI or the tools.
"""
import base64
import json
import mimetypes
import os

from . import bridge, mapping, paths, settings

# What designers see is Galley's own tiers; which model runs behind each tier is an internal detail
# (change it here without touching the app). 'model' is never sent to the UI.
MODELS = [
    {'id': 'galley', 'label': 'Galley', 'model': 'claude-opus-5-5', 'available': True, 'default': True},
    {'id': 'galley-fast', 'label': 'Galley Fast', 'model': 'claude-sonnet-5-5', 'available': True},
    {'id': 'galley-pro', 'label': 'Galley Pro', 'model': 'claude-fable-5-2', 'available': True},
]
LEGACY = {'claude-opus-5-5': 'galley', 'claude-sonnet-5-5': 'galley-fast', 'claude-haiku-5-5': 'galley-fast', 'claude-fable-5-2': 'galley-pro'}


def public_models():
    """the tier list for the UI, without the underlying model names"""
    return [{k: v for k, v in m.items() if k != 'model'} for m in MODELS]

FALLBACK_MODELS = {'claude-opus-5-5', 'claude-sonnet-5-5', 'claude-fable-5-2'}  # models with server-side refusal fallback

SYSTEM = """You are Galley, a layout copilot for book designers working in Adobe InDesign. You work on the document the \
designer has open, through tools. The designer is a professional: be brief, concrete and practical.

How to work:
- Look before you act: call get_document_info when you need the document's styles, pages or the current selection.
- Prefer changing paragraph styles over local formatting, so the change applies everywhere the style is used.
- Every change you make is one undo step in InDesign (Ctrl+Z / Edit > Undo "Galley: ..."). Say so after a change.
- Flowing a whole manuscript adds pages: only do it when the designer asks for it.
- Colours are given as #RRGGBB or an existing swatch name; sizes in points; spacing and indents in millimetres.
- When the designer shares reference images, describe the style they show (type, palette, box treatments, density) \
and suggest concrete style values. References inform the style; never copy artwork or a page layout from them.
- If a tool returns an error, explain it in plain words and suggest the fix.
- Fixes by page ("page 4: the heading is too big"): call describe_page first, then change the paragraph on that page
  (change_paragraph) or, if the same problem will appear everywhere, the paragraph style (update_paragraph_style).
  Say which one you changed. If the request is unclear, ask one short question instead of guessing.
- You are Galley's assistant. If asked which AI model or company is behind you, say that you are Galley's
  assistant and that details of the underlying model aren't shared; do not name or deny a provider."""

TOOLS = [
    {'name': 'get_document_info', 'description': 'Name, page count, trim, paragraph and character styles, masters, the saved style mapping and the current selection of the open InDesign document.',
     'input_schema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
    {'name': 'check_document', 'description': 'Run Galley QA on the open document: overset text, boxes split across pages, stranded headings, objects off the page, missing links, empty pages. Returns errors and notes with page numbers.',
     'input_schema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
    {'name': 'go_to_page', 'description': 'Show a page of the open document in the InDesign window.',
     'input_schema': {'type': 'object', 'properties': {'page': {'type': 'string', 'description': 'Page name as shown in InDesign, e.g. "4"'}}, 'required': ['page'], 'additionalProperties': False}},
    {'name': 'update_paragraph_style', 'description': 'Change properties of one paragraph style (applies wherever the style is used). Allowed keys: '
     + ', '.join(sorted(bridge.ALLOWED)) + '. Colours as #RRGGBB or swatch name; pointSize/leading in pt; spacing/indents in mm; justification left|center|right.',
     'input_schema': {'type': 'object', 'properties': {'style': {'type': 'string'}, 'changes': {'type': 'object', 'description': 'property -> value'}},
                      'required': ['style', 'changes'], 'additionalProperties': False}},
    {'name': 'apply_selection_look_to_style', 'description': 'The designer restyled one paragraph by hand and has its text selected: make that look the paragraph style, so every paragraph with that style matches.',
     'input_schema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
    {'name': 'suggest_style_mapping', 'description': "Which of the document's paragraph styles Galley would use for each content role (chapter title, section heading, body, example box, exercise, question, note...).",
     'input_schema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
    {'name': 'describe_page', 'description': 'What is on one page of the open document: each paragraph (number, paragraph style, size, start of the text, local changes), pictures and how full the page is. Use it before fixing something on a page.',
     'input_schema': {'type': 'object', 'properties': {'page': {'type': 'string', 'description': 'page name as shown in InDesign'}}, 'required': ['page'], 'additionalProperties': False}},
    {'name': 'change_paragraph', 'description': 'Change ONE paragraph (or the few that match) on a given page, found by a piece of its text. For a fix that should apply everywhere use update_paragraph_style instead. Keys: '
     + ', '.join(sorted(bridge.ALLOWED)) + ', start_on_next_page (true moves the paragraph to the next page).',
     'input_schema': {'type': 'object', 'properties': {'page': {'type': 'string'}, 'contains': {'type': 'string', 'description': 'a few words from the paragraph'},
                                                       'changes': {'type': 'object', 'description': 'property -> value'}},
                      'required': ['page', 'contains', 'changes'], 'additionalProperties': False}},
    {'name': 'flow_manuscript', 'description': "Flow the ingested manuscript into the open document after its last page, using the document's own styles (the saved mapping, or the suggested one). Adds pages. Only when the designer asks.",
     'input_schema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
]


def _map_for_doc(st):
    saved = {}
    try:
        saved = json.loads(st.get('mapping') or '{}')
    except ValueError:
        pass
    sug = mapping.suggest(st.get('paragraphStyles', []), st.get('characterStyles', []), saved)
    m = {x['role']: x['style'] for x in sug['paragraph'] + sug['character'] if x['style']}
    for k, v in saved.items():
        if k.startswith('_'):
            m[k] = v
    return m, sug


def run_tool(name, inp):
    """Execute one tool; always returns a JSON-able dict."""
    if name == 'get_document_info':
        st = bridge.status()
        st.pop('characterStyles', None) if len(st.get('characterStyles', [])) > 40 else None
        return st
    if name == 'check_document':
        qa = bridge.check_document()
        return {k: qa.get(k) for k in ('pages', 'passed', 'checks', 'errors', 'warnings', 'error') if k in qa}
    if name == 'go_to_page':
        return bridge.go_to_page(inp.get('page', ''))
    if name == 'update_paragraph_style':
        return bridge.update_paragraph_style(inp.get('style', ''), inp.get('changes') or {})
    if name == 'apply_selection_look_to_style':
        return bridge.redefine_style_from_selection()
    if name == 'suggest_style_mapping':
        st = bridge.status()
        return _map_for_doc(st)[1]
    if name == 'describe_page':
        return bridge.describe_page(inp.get('page', ''))
    if name == 'change_paragraph':
        ch = inp.get('changes') or {}
        if isinstance(ch, str):  # some providers send the object as JSON text
            try:
                ch = json.loads(ch)
            except ValueError:
                return {'ok': False, 'error': 'changes must be an object'}
        return bridge.change_paragraph(inp.get('page', ''), inp.get('contains', ''), ch)
    if name == 'flow_manuscript':
        content = os.path.join(paths.WORK, 'content.json')
        if not os.path.exists(content):
            return {'ok': False, 'error': 'No manuscript yet. Open the Continue tab and choose a .docx first.'}
        st = bridge.status()
        m = _map_for_doc(st)[0]
        return bridge.flow_manuscript(content, m)
    return {'error': 'unknown tool ' + name}


def _image_block(path):
    mt = mimetypes.guess_type(path)[0] or 'image/png'
    if mt not in ('image/png', 'image/jpeg', 'image/gif', 'image/webp'):
        return None
    with open(path, 'rb') as f:
        data = base64.standard_b64encode(f.read()).decode('ascii')
    return {'type': 'image', 'source': {'type': 'base64', 'media_type': mt, 'data': data}}


class AnthropicProvider:
    """Claude through the official Anthropic SDK; manual tool loop so every tool call is visible to the designer."""

    def __init__(self, api_key):
        import anthropic
        self.anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    def chat(self, model, history, user_content, on_tool):
        messages = list(history) + [{'role': 'user', 'content': user_content}]
        steps = []
        for _ in range(12):  # tool rounds per message
            kwargs = dict(model=model, max_tokens=16000, system=SYSTEM, tools=TOOLS, messages=messages,
                          output_config={'effort': 'medium' if 'haiku' not in model else 'low'})
            # refusal fallback: let the API retry on a suitable model instead of stopping (Claude 5.x models)
            if model in FALLBACK_MODELS:
                resp = self.client.beta.messages.create(betas=['server-side-fallback-2026-07-01'], fallbacks='default', **kwargs)
            else:
                resp = self.client.beta.messages.create(**kwargs)
            if resp.stop_reason == 'refusal':
                return {'text': 'The model declined this request. Try rephrasing it.', 'steps': steps}
            content = [b for b in resp.content if b.type != 'fallback']
            messages.append({'role': 'assistant', 'content': [b.model_dump(exclude_none=True) for b in content]})
            uses = [b for b in content if b.type == 'tool_use']
            if not uses:
                text = '\n'.join(b.text for b in content if b.type == 'text').strip()
                if resp.stop_reason == 'max_tokens':
                    text += '\n\n(The answer was cut off. Ask me to continue.)'
                return {'text': text, 'steps': steps}
            results = []
            for u in uses:
                on_tool(u.name, u.input)
                try:
                    out = run_tool(u.name, u.input or {})
                    err = isinstance(out, dict) and (out.get('error') or out.get('ok') is False)
                except bridge.InDesignNotRunning as e:
                    out, err = {'error': str(e)}, True
                except Exception as e:  # noqa: BLE001 - report tool failures to the model instead of crashing the chat
                    out, err = {'error': '%s: %s' % (type(e).__name__, e)}, True
                steps.append({'tool': u.name, 'input': u.input, 'ok': not err})
                results.append({'type': 'tool_result', 'tool_use_id': u.id, 'content': json.dumps(out, default=str)[:20000], 'is_error': bool(err)})
            messages.append({'role': 'user', 'content': results})
        return {'text': 'I stopped after many steps. Tell me what to do next.', 'steps': steps}


class OpenRouterProvider:
    """Claude (and others) through OpenRouter's OpenAI-style API, with the same tools and the same visible steps."""

    def __init__(self, key):
        from . import openrouter
        self.o, self.key = openrouter, key

    def chat(self, model, history, user_content, on_tool):
        tools = [{'type': 'function', 'function': {'name': t['name'], 'description': t['description'], 'parameters': t['input_schema']}} for t in TOOLS]
        content = []
        for blk in user_content:
            if blk['type'] == 'image':
                content.append({'type': 'image_url', 'image_url': {'url': 'data:%s;base64,%s' % (blk['source']['media_type'], blk['source']['data'])}})
            else:
                content.append({'type': 'text', 'text': blk['text']})
        messages = [{'role': 'system', 'content': SYSTEM}] + [{'role': h['role'], 'content': h['content']} for h in history]
        messages.append({'role': 'user', 'content': content})
        models = self.o.TIER.get(model, self.o.VISION)
        steps = []
        for _ in range(12):
            r = self.o.complete(self.key, models, {'messages': messages, 'tools': tools, 'max_tokens': 8000})
            choice = r['choices'][0]
            msg = choice['message']
            models = [r.get('model') or models[0]]  # keep the model that answered for the rest of this message
            calls = msg.get('tool_calls') or []
            messages.append({'role': 'assistant', 'content': msg.get('content') or '', **({'tool_calls': calls} if calls else {})})
            if not calls:
                text = (msg.get('content') or '').strip()
                if choice.get('finish_reason') == 'length':
                    text += '\n\n(The answer was cut off. Ask me to continue.)'
                return {'text': text or '(no answer)', 'steps': steps}
            for c in calls:
                name = c['function']['name']
                try:
                    args = json.loads(c['function'].get('arguments') or '{}')
                except ValueError:
                    args = {}
                on_tool(name, args)
                try:
                    out = run_tool(name, args)
                    err = isinstance(out, dict) and (out.get('error') or out.get('ok') is False)
                except bridge.InDesignNotRunning as e:
                    out, err = {'error': str(e)}, True
                except Exception as e:  # noqa: BLE001 - tool failures go back to the model
                    out, err = {'error': '%s: %s' % (type(e).__name__, e)}, True
                steps.append({'tool': name, 'input': args, 'ok': not err})
                messages.append({'role': 'tool', 'tool_call_id': c['id'], 'content': json.dumps(out, default=str)[:20000]})
        return {'text': 'I stopped after many steps. Tell me what to do next.', 'steps': steps}


def _gemini_schema(sch):
    """our JSON-Schema tool inputs -> the OpenAPI subset Gemini accepts (free-form objects become JSON text)"""
    props = {}
    for k, v in (sch.get('properties') or {}).items():
        if v.get('type') == 'object' and not v.get('properties'):
            props[k] = {'type': 'string', 'description': (v.get('description', '') + ' (a JSON object, e.g. {"pointSize": 14})').strip()}
        else:
            props[k] = {kk: vv for kk, vv in v.items() if kk in ('type', 'description', 'enum')}
    if not props:
        return None
    out = {'type': 'object', 'properties': props}
    if sch.get('required'):
        out['required'] = sch['required']
    return out


class GeminiProvider:
    """Google Gemini (free tier for testing) with the same tools, through its REST API."""

    def __init__(self, key):
        from . import gemini
        self.g, self.key = gemini, key

    def chat(self, tier, history, user_content, on_tool):
        decls = []
        for t in TOOLS:
            d = {'name': t['name'], 'description': t['description']}
            ps = _gemini_schema(t['input_schema'])
            if ps:
                d['parameters'] = ps
            decls.append(d)
        contents = [{'role': 'model' if h['role'] == 'assistant' else 'user', 'parts': [{'text': h['content']}]} for h in history]
        parts = []
        for blk in user_content:
            if blk['type'] == 'image':
                parts.append({'inline_data': {'mime_type': blk['source']['media_type'], 'data': blk['source']['data']}})
            else:
                parts.append({'text': blk['text']})
        contents.append({'role': 'user', 'parts': parts})
        steps = []
        for _ in range(10):
            body = {'system_instruction': {'parts': [{'text': SYSTEM}]}, 'contents': contents,
                    'tools': [{'function_declarations': decls}], 'generationConfig': {'temperature': 0.4}}
            r = self.g.generate(self.key, body)
            cand = (r.get('candidates') or [{}])[0]
            mparts = cand.get('content', {}).get('parts', [])
            contents.append({'role': 'model', 'parts': mparts})
            calls = [p['functionCall'] for p in mparts if 'functionCall' in p]
            if not calls:
                text = '\n'.join(p.get('text', '') for p in mparts).strip()
                return {'text': text or '(no answer)', 'steps': steps}
            answers = []
            for c in calls:
                args = c.get('args') or {}
                on_tool(c['name'], args)
                try:
                    out = run_tool(c['name'], args)
                    err = isinstance(out, dict) and (out.get('error') or out.get('ok') is False)
                except bridge.InDesignNotRunning as e:
                    out, err = {'error': str(e)}, True
                except Exception as e:  # noqa: BLE001 - tool failures go back to the model
                    out, err = {'error': '%s: %s' % (type(e).__name__, e)}, True
                steps.append({'tool': c['name'], 'input': args, 'ok': not err})
                answers.append({'functionResponse': {'name': c['name'], 'response': {'result': json.loads(json.dumps(out, default=str))}}})
            contents.append({'role': 'user', 'parts': answers})
        return {'text': 'I stopped after many steps. Tell me what to do next.', 'steps': steps}


def chat(model_id, history, text, ref_paths, on_tool=lambda n, i: None):
    """history: [{'role','content'(text)}]; returns {'text','steps'} or {'error'}."""
    model_id = LEGACY.get(model_id, model_id)
    model = next((m for m in MODELS if m['id'] == model_id), MODELS[0])
    if not model['available']:
        return {'error': '%s is not available yet.' % model['label']}
    content = []
    for p in ref_paths[:8]:
        blk = _image_block(p)
        if blk:
            content.append(blk)
    content.append({'type': 'text', 'text': text})
    # keys in order of preference: Claude direct, Claude through OpenRouter, Google. If one account refuses
    # (identity check, no credit, limit reached) the next one answers and the reply says why.
    chain = []
    key = settings.get('anthropic_api_key') or os.environ.get('ANTHROPIC_API_KEY', '')
    if key:
        chain.append(('Claude', lambda: AnthropicProvider(key).chat(model['model'], history, content, on_tool)))
    okey = settings.get('openrouter_api_key')
    if okey:
        chain.append(('OpenRouter', lambda: OpenRouterProvider(okey).chat(model['model'], history, content, on_tool)))
    gkey = settings.get('gemini_api_key')
    if gkey:
        chain.append(('Google AI', lambda: GeminiProvider(gkey).chat(model['id'], history, content, on_tool)))
    if not chain:
        return {'error': 'Galley needs an AI key to chat. Add one in Settings (gear icon).'}
    reasons = []
    for i, (name, run) in enumerate(chain):
        try:
            r = run()
            if reasons:
                r['note'] = 'Answered with the backup AI (%s): %s' % (name, '; '.join(reasons))
            return r
        except Exception as e:  # noqa: BLE001 - each provider's error becomes plain words
            msg, account = _explain(name, e)
            if not account or i == len(chain) - 1:  # a problem with this request, or no backup left: say why
                return {'error': msg + ('' if not reasons else ' (also: %s)' % '; '.join(reasons))}
            reasons.append(msg)


def _explain(name, e):
    """(plain-words reason, whether the account itself is the problem so a backup key should be tried)"""
    from . import gemini, openrouter
    if isinstance(e, (gemini.GeminiError, openrouter.OpenRouterError)):
        return str(e), getattr(e, 'code', None) in (400, 401, 402, 403, 429, 503) or 'too long' in str(e)
    if isinstance(e, bridge.InDesignNotRunning):
        return str(e), False
    try:
        a = __import__('anthropic')
    except ImportError:
        return '%s: %s' % (type(e).__name__, e), False
    if isinstance(e, a.AuthenticationError):
        return 'The Claude key was refused. Check it in Settings.', True
    if isinstance(e, a.RateLimitError):
        return 'Claude is rate limited. Wait a moment and try again.', True
    if isinstance(e, a.APIConnectionError):
        return 'Cannot reach Claude. Check the internet connection.', True
    if isinstance(e, a.APIStatusError):
        try:
            reason = e.body['error']['message']
        except (TypeError, KeyError):
            reason = 'error %s' % e.status_code
        return '%s said: %s' % (name, reason), e.status_code in (400, 401, 402, 403, 429, 529)
    return '%s: %s' % (type(e).__name__, e), False
