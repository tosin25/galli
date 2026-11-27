"""Pictures for the book: find where the manuscript asks for one, describe it, generate it, place it.

1. plan()     reads work/content.json and lists the picture slots: lines like "[Picture: a girl counting apples]",
              "Illustration: ...", "Insert a picture of ...". Each slot gets a description built from its own words
              and the text around it, which the designer can edit.
2. generate() makes the chosen pictures with Google's image model (via the same Google AI key), in a consistent
              style for the whole book; reference pins guide the style only.
3. place()    puts each picture into the open InDesign document right where its placeholder text is (inline,
              so it moves with the text), as one undo step.
Generated pictures are labelled AI-generated in their file names; a person approves every one before print.
"""
import base64
import json
import os
import re

from . import bridge, gemini, paths, settings

IMG_DIR = os.path.join(paths.WORK, 'images')
PLAN = os.path.join(IMG_DIR, 'plan.json')
SLOT_RX = re.compile(r'^\s*[\[(]?\s*(?:insert\s+(?:a\s+)?)?(picture|illustration|image|drawing|photo|diagram)s?\b\s*(?:of)?\s*[:\-–]?\s*(.+?)[\])]?\s*$', re.I)
NOTE_RX = re.compile(r'call me|lead graphics|graphic artist|designer to|see me', re.I)
STYLE = ('Children\'s textbook illustration, clean friendly flat style with soft shading, simple shapes, clear outlines, '
         'white background, no text or letters in the picture, suitable for print.')


def _texts(content):
    """(where, text) for every paragraph-like piece of the manuscript, in reading order"""
    out = []
    for bi, b in enumerate(content['blocks']):
        if b.get('text'):
            out.append(('b%d' % bi, b['text']))
        for ii, it in enumerate(b.get('items') or []):
            if isinstance(it, dict) and it.get('text'):
                out.append(('b%d.%d' % (bi, ii), it['text']))
    return out


def plan():
    """picture slots found in the manuscript (keeps descriptions the designer already edited)"""
    cj = os.path.join(paths.WORK, 'content.json')
    if not os.path.exists(cj):
        return {'error': 'Choose a manuscript first.'}
    with open(cj, encoding='utf-8') as f:
        content = json.load(f)
    old = {}
    if os.path.exists(PLAN):
        with open(PLAN, encoding='utf-8') as f:
            old = {s['id']: s for s in json.load(f).get('slots', [])}
    texts, slots = _texts(content), []
    for k, (where, t) in enumerate(texts):
        m = SLOT_RX.match(t)
        if not m or len(t) > 240:
            continue
        before = texts[k - 1][1] if k else ''
        after = texts[k + 1][1] if k + 1 < len(texts) else ''
        sid = 'pic-%d' % (len(slots) + 1)
        desc = m.group(2).strip().rstrip('.')
        if NOTE_RX.search(desc):  # a note to the designer, not a description: ask the person to describe it
            desc = ''
        s = {'id': sid, 'where': where, 'placeholder': t.strip(), 'kind': m.group(1).lower(),
             'description': desc, 'context': (before[-160:] + ' … ' + after[:160]).strip(' …')}
        if sid in old and old[sid].get('placeholder') == s['placeholder']:
            s.update({k2: old[sid][k2] for k2 in ('description', 'file') if old[sid].get(k2)})
        slots.append(s)
    os.makedirs(IMG_DIR, exist_ok=True)
    with open(PLAN, 'w', encoding='utf-8') as f:
        json.dump({'chapter': content['meta'].get('chapter_title'), 'slots': slots}, f, indent=1, ensure_ascii=False)
    return {'chapter': content['meta'].get('chapter_title'), 'slots': [_public(s) for s in slots]}


def _public(s):
    p = dict(s)
    if s.get('file'):
        p['url'] = '/work/images/' + os.path.basename(s['file'])
    return p


def _image_model(key):
    models = gemini._call('GET', '/models?pageSize=200', key).get('models', [])
    names = [m['name'].split('/', 1)[1] for m in models if 'generateContent' in m.get('supportedGenerationMethods', [])]
    found = []
    for n in names:  # plain "gemini-<version>-flash-image" models, newest stable first
        m = re.fullmatch(r'gemini-(\d+(?:\.\d+)?)-flash-image(-preview)?', n)
        if m:
            found.append((not m.group(2), tuple(int(x) for x in m.group(1).split('.')), n))
    if not found:
        raise gemini.GeminiError('This Google AI key has no image model (image generation may need billing on the Google account).')
    return max(found)[2]


def generate(ids, descriptions=None, ref_paths=None, palette=None):
    """make the chosen pictures; returns the updated slots"""
    key = settings.get('gemini_api_key')
    if not key:
        return {'error': 'Add the free Google AI key in Settings first.'}
    if not os.path.exists(PLAN):
        plan()
    with open(PLAN, encoding='utf-8') as f:
        data = json.load(f)
    descriptions = descriptions or {}
    try:
        model = _image_model(key)
    except gemini.GeminiError as e:
        return {'error': str(e)}
    style = STYLE + (' Colour palette: %s.' % ', '.join(palette) if palette else '')
    refs = [gemini.image_part(p) for p in (ref_paths or [])[:3]]
    errors = []
    for s in data['slots']:
        if s['id'] not in ids:
            continue
        if descriptions.get(s['id']):
            s['description'] = descriptions[s['id']].strip()
        if not s['description']:
            errors.append('%s: describe this picture first' % s['id'])
            continue
        prompt = ('Create one illustration for a book page. Picture: %s.\nWhat the page is about: %s\nStyle: %s\n'
                  'Use any reference images only as a guide to mood and colour; do not copy them.' % (s['description'], s['context'], style))
        body = {'contents': [{'role': 'user', 'parts': refs + [{'text': prompt}]}],
                'generationConfig': {'responseModalities': ['IMAGE', 'TEXT']}}
        try:
            r = gemini._call('POST', '/models/%s:generateContent' % model, key, body, timeout=240)
            parts = ((r.get('candidates') or [{}])[0].get('content') or {}).get('parts', [])
            img = next((p.get('inline_data') or p.get('inlineData') for p in parts if p.get('inline_data') or p.get('inlineData')), None)
            if not img:
                raise gemini.GeminiError('no picture came back')
            path = os.path.join(IMG_DIR, '%s_ai-generated.png' % s['id'])
            with open(path, 'wb') as f:
                f.write(base64.b64decode(img['data']))
            s['file'] = path
        except gemini.GeminiError as e:
            errors.append('%s: %s' % (s['id'], e))
    with open(PLAN, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    return {'slots': [_public(s) for s in data['slots']], 'errors': errors, 'model_used': 'Google image model'}


PLACE_JS = r"""
var d = app.activeDocument, items = eval('(' + app.scriptArgs.getValue('g_items') + ')'), done = [], missing = [];
var SMU = app.scriptPreferences.measurementUnit; app.scriptPreferences.measurementUnit = MeasurementUnits.MILLIMETERS;
var st = d.stories.everyItem().getElements();
for (var i = 0; i < items.length; i++) {
  var it = items[i], found = null;
  for (var s = 0; s < st.length && !found; s++) { var ps = st[s].paragraphs.everyItem().getElements();
    for (var p = 0; p < ps.length; p++) if (ps[p].contents.indexOf(it.placeholder.substr(0, 40)) >= 0) { found = ps[p]; break; } }
  if (!found) { missing.push(it.id); continue; }
  try {
    var col = found.parentTextFrames[0], b = col.geometricBounds, w = Math.min(90, (b[3] - b[1]) * 0.7), h = w * 0.75;
    // the placeholder line becomes the picture (its words are kept as the frame's name for reference)
    var ip = found.insertionPoints[0]; found.characters.itemByRange(0, Math.max(0, found.characters.length - 2)).remove();
    var r = ip.rectangles.add({ geometricBounds: [0, 0, h, w], strokeWeight: 0, name: it.id + ' ' + it.placeholder.substr(0, 60) });
    try { r.frameFittingOptions.fittingOnEmptyFrame = EmptyFrameFittingOptions.PROPORTIONALLY; } catch (e) {}
    r.place(File(it.file)); r.fit(FitOptions.PROPORTIONALLY); r.fit(FitOptions.CENTER_CONTENT);
    found.justification = Justification.CENTER_ALIGN; found.leading = h * 2.8346 + 2;
    done.push(it.id);
  } catch (e) { missing.push(it.id + ' (' + e.message + ')'); }
}
app.scriptPreferences.measurementUnit = SMU;
return __j({ok: done.length > 0, placed: done, not_found: missing});"""


def place(ids=None):
    """put generated pictures into the open document at their placeholders (one undo step)"""
    if not os.path.exists(PLAN):
        return {'error': 'No pictures planned yet.'}
    with open(PLAN, encoding='utf-8') as f:
        data = json.load(f)
    items = [{'id': s['id'], 'placeholder': s['placeholder'], 'file': s['file'].replace('\\', '/')}
             for s in data['slots'] if s.get('file') and (not ids or s['id'] in ids)]
    if not items:
        return {'error': 'Generate some pictures first.'}
    return bridge.js(PLACE_JS, undo_name='place pictures', args={'g_items': json.dumps(items)})
