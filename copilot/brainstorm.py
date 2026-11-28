"""Brainstorm: the designer's reference pins + one chapter -> 3 different design directions -> 3 drafts.

The AI only chooses among things Galley can actually build (installed fonts, the treatments the builder knows,
valid colours); every answer is checked and completed from a base spec, so a bad suggestion can't break a build.
References inform the direction; the prompt forbids copying any pin's layout, artwork or text.
"""
import copy
import json
import os
import re
import time

from . import bridge, drafts, gemini, paths, settings

# font families Galley may suggest; only those installed in the designer's InDesign are offered to the AI
CANDIDATE_FONTS = ['Poppins', 'Nunito', 'Inter', 'Google Sans', 'Playfair Display', 'Georgia', 'Merriweather', 'Lora', 'Montserrat',
                   'Open Sans', 'Lato', 'Roboto', 'Roboto Slab', 'Source Sans 3', 'Source Serif 4', 'Fraunces', 'DM Sans', 'DM Serif Display',
                   'Work Sans', 'Raleway', 'Quicksand', 'Baloo 2', 'Fredoka', 'Comic Neue', 'Andika', 'Atkinson Hyperlegible', 'Literata',
                   'Crimson Pro', 'EB Garamond', 'Libre Baskerville', 'Bitter', 'Mulish', 'Rubik', 'Segoe UI', 'Arial', 'Cambria', 'Calibri',
                   'Verdana', 'Trebuchet MS', 'Century Gothic']

FONTS_JS = r"""
var names = eval('(' + app.scriptArgs.getValue('g_fonts') + ')'), out = {}, i;
var all = app.fonts.everyItem().getElements(), want = {};
for (i = 0; i < names.length; i++) want[names[i]] = [];
for (i = 0; i < all.length; i++) { try { var f = all[i]; if (want[f.fontFamily] && f.status == FontStatus.INSTALLED) want[f.fontFamily].push(f.fontStyleName); } catch (e) {} }
for (var k in want) if (want[k].length) out[k] = want[k];
return __j(out);"""

SYSTEM = """You are the art director of a book design studio. A book designer gives you reference images (pins they like)
and one chapter of a manuscript. Propose THREE clearly different design directions for laying out this book in InDesign.

Rules:
- Take mood, colour, type character and density from the references, but never copy any reference's layout, artwork,
  characters, logos or text. The designs must be original.
- Fit the audience and subject of the manuscript (e.g. a primary-school maths workbook needs large, clear type and calm boxes).
- Make the three directions genuinely different from each other (e.g. playful / classic / modern), each still fitting the references.
- Use ONLY the fonts listed as installed, and ONLY the option values listed below.
- Colours are #RRGGBB. Tints must be very light (for box backgrounds). Text colour "ink" must be dark enough to read.

Answer with JSON only, in exactly this shape:
{"questions": ["optional short question for the designer, if something important is unclear"],
 "designs": [
  {"name": "2-4 word name", "why": "one or two sentences: what in the references and the manuscript led to this",
   "trim": {"width": mm, "height": mm},
   "heading_font": "installed family", "body_font": "installed family",
   "body_size": pt (9-15), "h2_size": pt, "opener_title_size": pt,
   "palette": {"primary": "#", "secondary": "#", "accent": "#", "ink": "#", "primary_tint": "#", "secondary_tint": "#", "note": "#"},
   "opener": "banner | band | minimal",
   "h2": "band | rule | number_rule",
   "example": "shaded | outlined | sidebar", "example_head": "pill | band | label",
   "exercise": "shaded | open | sidebar", "exercise_head": "pill | band | ruled",
   "note": "shaded | sidebar",
   "folio": "circle | block | plain",
   "side_tab": true or false, "running_header": true or false}
 ]}"""

TRIMS_OK = (140, 297)


def installed_fonts():
    r = bridge.js(FONTS_JS, args={'g_fonts': json.dumps(CANDIDATE_FONTS)})
    return r if isinstance(r, dict) and not r.get('error') else {}


def _weights(styles):
    def find(*names):
        for n in names:
            for s in styles:
                if s.lower() == n.lower():
                    return s
        return None
    regular = find('Regular', 'Book', 'Roman', 'Normal') or styles[0]
    bold = find('Bold', 'SemiBold', 'Semi Bold', 'Semibold', 'Medium') or regular
    semibold = find('SemiBold', 'Semi Bold', 'Semibold', 'Medium', 'Bold') or bold
    italic = find('Italic', 'Regular Italic', 'Book Italic') or regular
    return {'regular': regular, 'bold': bold, 'semibold': semibold, 'italic': italic}


def _hex(v, default):
    return v.upper() if isinstance(v, str) and re.match(r'^#[0-9a-fA-F]{6}$', v) else default


def _num(v, lo, hi, default):
    try:
        v = float(v)
        return max(lo, min(hi, v))
    except (TypeError, ValueError):
        return default


def to_spec(d, n, fonts, base):
    """one AI design -> a complete, buildable Galley style spec"""
    s = copy.deepcopy(base)
    sid = 'idea-%d' % n
    s['id'], s['name'] = sid, (d.get('name') or 'Idea %d' % n)[:40]
    s['description'] = (d.get('why') or '')[:300]
    tw = _num((d.get('trim') or {}).get('width'), TRIMS_OK[0], 230, base['trim']['width'])
    th = _num((d.get('trim') or {}).get('height'), 200, TRIMS_OK[1], base['trim']['height'])
    s['trim'] = {'width': round(tw, 2), 'height': round(th, 2)}
    for role, key in (('heading', 'heading_font'), ('body', 'body_font')):
        fam = d.get(key)
        if fam not in fonts:
            fam = s['fonts'][role]['family'] if s['fonts'][role]['family'] in fonts else next(iter(fonts), s['fonts'][role]['family'])
        w = _weights(fonts.get(fam, ['Regular', 'Bold', 'Italic']))
        s['fonts'][role] = {'family': fam, 'regular': w['regular'], 'bold': w['bold'], 'semibold': w['semibold'], 'italic': w['italic']}
    body = _num(d.get('body_size'), 9, 15, s['type']['body'])
    s['type'].update(body=body, leading=round(body * 1.45, 1), h2=_num(d.get('h2_size'), body + 2, 26, s['type']['h2']),
                     h3=round(body + 2, 1), box_head=body, small=round(body - 1.5, 1), caption=round(body - 2, 1),
                     opener_title=_num(d.get('opener_title_size'), 22, 44, s['type']['opener_title']))
    pal = d.get('palette') or {}
    for k in ('primary', 'secondary', 'accent', 'ink', 'primary_tint', 'secondary_tint', 'note'):
        s['palette'][k] = _hex(pal.get(k), s['palette'][k])
    pick = lambda v, ok, dflt: v if v in ok else dflt  # noqa: E731
    s['opener']['layout'] = pick(d.get('opener'), ('banner', 'band', 'minimal'), s['opener']['layout'])
    s['opener']['character'] = ''
    if s['opener']['layout'] == 'band':
        s['type']['opener_number'] = 60
    s['h2']['treatment'] = pick(d.get('h2'), ('band', 'rule', 'number_rule'), s['h2']['treatment'])
    s['h2']['text'] = 'paper' if s['h2']['treatment'] == 'band' else 'primary'
    s['example']['treatment'] = pick(d.get('example'), ('shaded', 'outlined', 'sidebar'), s['example']['treatment'])
    s['example']['head'] = pick(d.get('example_head'), ('pill', 'band', 'label'), s['example']['head'])
    s['activity'] = dict(s['example'], color='accent', head_text='ink', label_color='primary', fill='note')
    s['exercise']['treatment'] = pick(d.get('exercise'), ('shaded', 'open', 'sidebar'), s['exercise']['treatment'])
    s['exercise']['head'] = pick(d.get('exercise_head'), ('pill', 'band', 'ruled'), s['exercise']['head'])
    s['note']['treatment'] = pick(d.get('note'), ('shaded', 'sidebar'), s['note']['treatment'])
    s['note']['icon'] = ''
    folio = pick(d.get('folio'), ('circle', 'block', 'plain'), 'circle')
    s['folio'] = {'position': 'center' if folio == 'circle' else 'outer', 'shape': 'none' if folio == 'plain' else folio,
                  'color': 'primary', 'text': 'primary' if folio == 'plain' else 'paper'}
    s['side_tab']['show'] = bool(d.get('side_tab', s['side_tab'].get('show')))
    s['header'] = {'show': bool(d.get('running_header')), 'left': 'book', 'right': 'chapter', 'rule': True, 'color': 'primary'}
    return s


def manuscript_brief(content_path):
    with open(content_path, encoding='utf-8') as f:
        c = json.load(f)
    m, blocks = c['meta'], c['blocks']
    counts = {}
    for b in blocks:
        counts[b['type']] = counts.get(b['type'], 0) + 1
    heads = [b['text'] for b in blocks if b['type'] in ('h2', 'h3')][:8]
    sample = ' '.join(b['text'] for b in blocks if b['type'] == 'body')[:900]
    return ('Book: %s\nChapter %s: %s\nContains: %s\nSection headings: %s\nSample text: %s'
            % (m.get('book') or '?', m.get('chapter_no') or '', m.get('chapter_title') or '?',
               ', '.join('%d %s' % (v, k) for k, v in counts.items()), '; '.join(heads), sample))


def run(ref_paths):
    """pins + current manuscript -> 3 specs saved as style/idea-1..3 -> drafts started. Returns the designs."""
    okey, key = settings.get('openrouter_api_key'), settings.get('gemini_api_key')
    if not (okey or key):
        return {'error': 'Add an AI key in Settings first (OpenRouter or Google).'}
    content = os.path.join(paths.WORK, 'content.json')
    if not os.path.exists(content):
        return {'error': 'Choose a manuscript first.'}
    if not ref_paths:
        return {'error': 'Select a few reference pins first.'}
    fonts = installed_fonts()
    if not fonts:
        return {'error': 'Could not read the fonts installed in InDesign. Is InDesign open?'}
    parts = [gemini.image_part(p) for p in ref_paths[:8]]
    parts.append({'text': 'Installed fonts (family: styles): ' + json.dumps(fonts) + '\n\nManuscript:\n' + manuscript_brief(content)})
    t0 = time.time()
    from . import openrouter
    answer, reasons = None, []
    for kind, k in (('or', okey), ('g', key)):  # Claude through OpenRouter first, then Google
        if not k:
            continue
        try:
            answer = openrouter.generate_json(k, SYSTEM, parts) if kind == 'or' else gemini.generate_json(key, SYSTEM, parts)
            break
        except (openrouter.OpenRouterError, gemini.GeminiError) as e:
            reasons.append(str(e))
    if answer is None:
        return {'error': '; '.join(reasons)}
    designs = (answer.get('designs') or [])[:3]
    if not designs:
        return {'error': 'The AI did not propose any designs. Try again, or with different pins.'}
    with open(os.path.join(paths.RES, 'style', 'primary.json'), encoding='utf-8') as f:
        base = json.load(f)
    os.makedirs(paths.USER_STYLES, exist_ok=True)
    ids = []
    for n, d in enumerate(designs, 1):
        spec = to_spec(d, n, fonts, base)
        with open(os.path.join(paths.USER_STYLES, spec['id'] + '.json'), 'w', encoding='utf-8') as f:
            json.dump(spec, f, indent=2)
        ids.append(spec['id'])
    started = drafts.start(ids)
    return {'ok': not started.get('error'), 'error': started.get('error'), 'seconds': round(time.time() - t0, 1),
            'questions': answer.get('questions') or [],
            'designs': [{'id': i, 'name': d.get('name'), 'why': d.get('why')} for i, d in zip(ids, designs)]}
