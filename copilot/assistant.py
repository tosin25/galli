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
    key = settings.get('anthropic_api_key') or os.environ.get('ANTHROPIC_API_KEY', '')
    gkey = settings.get('gemini_api_key')
    if not key and gkey:  # no main AI key yet: use the free Google key (testing)
        from . import gemini
        try:
            return GeminiProvider(gkey).chat(model['id'], history, content, on_tool)
        except gemini.GeminiError as e:
            return {'error': str(e)}
    try:
        provider = AnthropicProvider(key)
        return provider.chat(model['model'], history, content, on_tool)
    except Exception as e:  # noqa: BLE001 - map SDK errors to plain advice below
        a = __import__('anthropic')
        if isinstance(e, a.AuthenticationError) or 'api_key' in str(e).lower() or 'authentication' in str(e).lower():
            return {'error': 'Galley needs its AI key to chat. Add it in Settings (gear icon).'}
        if isinstance(e, a.RateLimitError):
            return {'error': 'Rate limited by the API. Wait a moment and try again.'}
        if isinstance(e, a.APIConnectionError):
            return {'error': 'Cannot reach the AI service. Check the internet connection.'}
        if isinstance(e, a.APIStatusError):
            try:
                reason = e.body['error']['message']
            except (TypeError, KeyError):
                reason = ''
            # the account itself is blocked (identity check, no credit): keep working on the Google key if there is one
            if gkey and e.status_code in (400, 402, 403):
                from . import gemini
                try:
                    r = GeminiProvider(gkey).chat(model['id'], history, content, on_tool)
                    r['note'] = 'Answered with the backup AI because the main AI account says: %s' % (reason or 'error %s' % e.status_code)
                    return r
                except gemini.GeminiError:
                    pass
            return {'error': 'The AI service said: %s' % reason if reason else 'The AI service returned an error (%s). Try again in a moment.' % e.status_code}
        return {'error': '%s: %s' % (type(e).__name__, e)}
