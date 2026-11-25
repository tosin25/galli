"""Readers for the parts of a .docx that naive extractors lose.

- Numbering: Word's automatic list numbers live in word/numbering.xml, not in the text. A reader that only
  collects <w:t> drops every "1.", "(a)", "(iv)". Numbering.label() recomputes them exactly as Word shows them.
- Text: paragraph text without the text of drawn shapes (text boxes, callouts), so a diagram's labels are
  not repeated as body text; Word equation fractions (OMML m:f) come out as "num/den".
- Shapes: drawn diagrams (DrawingML wps/wpg groups and legacy VML): rectangles, rounded boxes, ovals, lines
  and text boxes, with their positions and sizes in mm, so the layout can redraw them as real InDesign objects.
"""
import re
import xml.etree.ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
WP = '{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}'
WPS = '{http://schemas.microsoft.com/office/word/2010/wordprocessingShape}'
WPG = '{http://schemas.microsoft.com/office/word/2010/wordprocessingGroup}'
MC = '{http://schemas.openxmlformats.org/markup-compatibility/2006}'
V = '{urn:schemas-microsoft-com:vml}'
M = '{http://schemas.openxmlformats.org/officeDocument/2006/math}'
EMU_MM = 1 / 36000.0
PT_MM = 25.4 / 72.0

# ---------------------------------------------------------------- numbering


def _roman(n, upper):
    vals = [(1000, 'm'), (900, 'cm'), (500, 'd'), (400, 'cd'), (100, 'c'), (90, 'xc'), (50, 'l'), (40, 'xl'), (10, 'x'), (9, 'ix'), (5, 'v'), (4, 'iv'), (1, 'i')]
    out = ''
    for v, s in vals:
        while n >= v:
            out += s
            n -= v
    return out.upper() if upper else out


def _letter(n, upper):
    s = ''
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(97 + r) + s
    return s.upper() if upper else s


def fmt_number(n, fmt):
    if fmt in ('lowerLetter', 'upperLetter'):
        return _letter(n, fmt == 'upperLetter')
    if fmt in ('lowerRoman', 'upperRoman'):
        return _roman(n, fmt == 'upperRoman')
    if fmt == 'decimalZero':
        return '%02d' % n
    return str(n)


class Numbering:
    """Recomputes Word list labels: counters per list instance (numId) and level, with start overrides."""

    def __init__(self, xml_bytes):
        self.abstract, self.nums = {}, {}
        self.count = {}
        if not xml_bytes:
            return
        root = ET.fromstring(xml_bytes)
        for an in root.iter(W + 'abstractNum'):
            lv = {}
            for l in an.iter(W + 'lvl'):
                il = int(l.get(W + 'ilvl', '0'))
                g = lambda tag, d='': (l.find(W + tag).get(W + 'val') if l.find(W + tag) is not None else d)  # noqa: E731
                lv[il] = {'start': int(g('start', '1') or 1), 'fmt': g('numFmt', 'decimal'), 'text': g('lvlText', '%1.')}
            self.abstract[an.get(W + 'abstractNumId')] = lv
        for n in root.iter(W + 'num'):
            a = n.find(W + 'abstractNumId')
            ovr = {}
            for o in n.iter(W + 'lvlOverride'):
                so = o.find(W + 'startOverride')
                if so is not None:
                    ovr[int(o.get(W + 'ilvl', '0'))] = int(so.get(W + 'val'))
            self.nums[n.get(W + 'numId')] = {'abs': a.get(W + 'val') if a is not None else None, 'start': ovr}

    def label(self, num_id, ilvl):
        """Next label for this list instance and level, e.g. '3.', '(b)', '(iv)' or a bullet character.
        Returns (label, kind) with kind in decimal/letter/roman/bullet/none."""
        num = self.nums.get(num_id)
        if not num or num_id == '0':
            return '', 'none'
        lvls = self.abstract.get(num['abs'], {})
        lv = lvls.get(ilvl, {'start': 1, 'fmt': 'decimal', 'text': '%%%d.' % (ilvl + 1)})
        if lv['fmt'] == 'bullet':
            return '•', 'bullet'
        if lv['fmt'] == 'none':
            return '', 'none'
        c = self.count.setdefault(num_id, {})
        if ilvl in c:
            c[ilvl] += 1
        else:
            c[ilvl] = num['start'].get(ilvl, lv['start'])
        for deeper in [k for k in c if k > ilvl]:  # a higher level restarts the levels below it
            del c[deeper]

        def sub(m):
            k = int(m.group(1)) - 1
            if k not in c:
                c[k] = num['start'].get(k, lvls.get(k, {'start': 1})['start'])
            return fmt_number(c[k], lvls.get(k, lv)['fmt'])
        text = re.sub(r'%(\d)', sub, lv['text'])
        kind = 'roman' if 'Roman' in lv['fmt'] else 'letter' if 'Letter' in lv['fmt'] else 'decimal'
        return text, kind


# ---------------------------------------------------------------- text

SKIP = {W + 'drawing', W + 'pict', MC + 'AlternateContent', W + 'object', W + 'txbxContent', W + 'delText'}


def text_of(el):
    """Visible paragraph text, skipping the text inside drawn shapes; OMML fractions as num/den."""
    out = []

    def walk(n):
        if n.tag in SKIP:
            return
        if n.tag == M + 'f':
            num, den = n.find(M + 'num'), n.find(M + 'den')
            t = lambda x: ''.join(e.text or '' for e in x.iter(M + 't')) if x is not None else ''  # noqa: E731
            out.append('%s/%s' % (t(num), t(den)))
            return
        if n.tag in (W + 't', M + 't') and n.text:
            out.append(n.text)
        elif n.tag == W + 'tab':
            out.append('\t')
        elif n.tag in (W + 'br', W + 'cr'):
            out.append('\n')
        for ch in n:
            walk(ch)
    walk(el)
    return ''.join(out).strip()


def _shape_text(el):
    paras = []
    for p in el.iter(W + 'p'):
        t = ''.join(x.text or '' for x in p.iter(W + 't')).strip()
        if t:
            paras.append(t)
    return '\n'.join(paras)


# ---------------------------------------------------------------- DrawingML shapes

def _xfrm(sppr):
    x = sppr.find(A + 'xfrm') if sppr is not None else None
    if x is None:
        return None
    off, ext = x.find(A + 'off'), x.find(A + 'ext')
    return {'x': int(off.get('x', 0)) if off is not None else 0, 'y': int(off.get('y', 0)) if off is not None else 0,
            'cx': int(ext.get('cx', 0)) if ext is not None else 0, 'cy': int(ext.get('cy', 0)) if ext is not None else 0,
            'flipH': x.get('flipH') == '1', 'flipV': x.get('flipV') == '1',
            'chx': int(x.find(A + 'chOff').get('x', 0)) if x.find(A + 'chOff') is not None else None,
            'chy': int(x.find(A + 'chOff').get('y', 0)) if x.find(A + 'chOff') is not None else None,
            'chcx': int(x.find(A + 'chExt').get('cx', 1)) if x.find(A + 'chExt') is not None else None,
            'chcy': int(x.find(A + 'chExt').get('cy', 1)) if x.find(A + 'chExt') is not None else None}


def _style(sppr):
    fill, stroke = None, '#000000'
    if sppr is not None:
        if sppr.find(A + 'noFill') is not None:
            fill = None
        sf = sppr.find(A + 'solidFill')
        if sf is not None and sf.find(A + 'srgbClr') is not None:
            fill = '#' + sf.find(A + 'srgbClr').get('val')
        ln = sppr.find(A + 'ln')
        if ln is not None:
            if ln.find(A + 'noFill') is not None:
                stroke = None
            elif ln.find(A + 'solidFill') is not None and ln.find(A + 'solidFill').find(A + 'srgbClr') is not None:
                stroke = '#' + ln.find(A + 'solidFill').find(A + 'srgbClr').get('val')
    return fill, stroke


def _kind(sppr):
    g = sppr.find(A + 'prstGeom') if sppr is not None else None
    prst = g.get('prst') if g is not None else 'rect'
    if prst in ('line', 'straightConnector1', 'bentConnector2', 'curvedConnector3'):
        return 'line'
    if prst in ('ellipse', 'oval'):
        return 'ellipse'
    if prst in ('roundRect', 'flowChartAlternateProcess'):
        return 'roundRect'
    return 'rect'


def _wsp(wsp, mapf, out):
    sppr = wsp.find(WPS + 'spPr')
    xf = _xfrm(sppr) or {'x': 0, 'y': 0, 'cx': 0, 'cy': 0, 'flipH': False, 'flipV': False}
    x0, y0 = mapf(xf['x'], xf['y'])
    x1, y1 = mapf(xf['x'] + xf['cx'], xf['y'] + xf['cy'])
    fill, stroke = _style(sppr)
    kind = _kind(sppr)
    txt = _shape_text(wsp.find(WPS + 'txbx')) if wsp.find(WPS + 'txbx') is not None else ''
    if kind == 'rect' and txt and fill is None and stroke is None:
        kind = 'text'
    s = {'kind': kind, 'x': x0, 'y': y0, 'w': x1 - x0, 'h': y1 - y0, 'text': txt, 'fill': fill, 'stroke': stroke}
    if kind == 'line':
        s['flipH'], s['flipV'] = xf['flipH'], xf['flipV']
    out.append(s)


def _group(g, mapf, out):
    gp = g.find(WPG + 'grpSpPr')
    xf = _xfrm(gp)
    if xf and xf['chcx']:
        sx = xf['cx'] / float(xf['chcx'] or 1)
        sy = xf['cy'] / float(xf['chcy'] or 1)
        inner = lambda x, y, xf=xf, sx=sx, sy=sy: mapf(xf['x'] + (x - xf['chx']) * sx, xf['y'] + (y - xf['chy']) * sy)  # noqa: E731
    else:
        inner = mapf
    for ch in g:
        if ch.tag == WPS + 'wsp':
            _wsp(ch, inner, out)
        elif ch.tag in (WPG + 'grpSp', WPG + 'wgp'):
            _group(ch, inner, out)


def drawing_shapes(drawing):
    """Shapes of one <w:drawing> (no pictures), in mm; plus the drawing's own box and anchor offset."""
    cont = drawing.find(WP + 'anchor')
    if cont is None:
        cont = drawing.find(WP + 'inline')
    if cont is None or next(cont.iter(A + 'blip'), None) is not None:
        return None
    ext = cont.find(WP + 'extent')
    w = int(ext.get('cx', 0)) * EMU_MM if ext is not None else 0
    h = int(ext.get('cy', 0)) * EMU_MM if ext is not None else 0
    ox = oy = 0.0
    if cont.tag == WP + 'anchor':
        for axis in ('positionH', 'positionV'):
            pe = cont.find(WP + axis)
            po = pe.find(WP + 'posOffset') if pe is not None else None
            if po is not None and po.text:
                if axis == 'positionH':
                    ox = int(po.text) * EMU_MM
                else:
                    oy = int(po.text) * EMU_MM
    gd = next(cont.iter(A + 'graphicData'), None)
    if gd is None:
        return None
    shapes = []
    top = lambda x, y: (x * EMU_MM, y * EMU_MM)  # noqa: E731
    for ch in gd:
        if ch.tag == WPS + 'wsp':
            sppr = ch.find(WPS + 'spPr')
            xf = _xfrm(sppr)
            if xf is not None and (xf['x'] or xf['y']):  # a lone shape draws at its own box, not at its xfrm offset
                xf0 = xf
                _wsp(ch, lambda x, y, xf0=xf0: ((x - xf0['x']) * EMU_MM, (y - xf0['y']) * EMU_MM), shapes)
            else:
                _wsp(ch, top, shapes)
            if shapes and not shapes[-1]['w'] and not shapes[-1]['h']:
                shapes[-1].update(w=w, h=h)
        elif ch.tag == WPG + 'wgp':
            _group(ch, lambda x, y: (x * EMU_MM, y * EMU_MM), shapes)
    if not shapes:
        return None
    return {'shapes': shapes, 'w': w, 'h': h, 'ox': ox, 'oy': oy, 'anchored': cont.tag == WP + 'anchor'}


# ---------------------------------------------------------------- VML (older Word files)

def _css(style):
    d = {}
    for part in (style or '').split(';'):
        if ':' in part:
            k, v = part.split(':', 1)
            d[k.strip().lower()] = v.strip()
    return d


def _len(v, unit_mm):
    """'12pt' / '3.5mm' / '1in' / '20px' / bare coordinate units (scaled by unit_mm)."""
    m = re.match(r'^(-?[\d.]+)\s*(pt|mm|cm|in|px)?$', v or '')
    if not m:
        return 0.0
    n, u = float(m.group(1)), m.group(2)
    return {'pt': n * PT_MM, 'mm': n, 'cm': n * 10, 'in': n * 25.4, 'px': n * 0.75 * PT_MM}.get(u, n * unit_mm)


def vml_shapes(pict):
    """Shapes of a legacy <w:pict> (v:group, v:rect, v:roundrect, v:oval, v:line, v:shape) in mm."""
    out = []

    def walk(el, ox, oy, unit_mm, coordorigin=(0.0, 0.0)):
        for ch in el:
            tag = ch.tag.replace(V, '')
            css = _css(ch.get('style'))
            if tag == 'group':
                gx = ox + _len(css.get('left', css.get('margin-left', '0')), unit_mm)
                gy = oy + _len(css.get('top', css.get('margin-top', '0')), unit_mm)
                gw = _len(css.get('width', '0'), unit_mm)
                cs = [float(x) for x in (ch.get('coordsize') or '1000,1000').split(',')]
                co = [float(x) for x in (ch.get('coordorigin') or '0,0').split(',')]
                walk(ch, gx - co[0] * (gw / cs[0] if cs[0] else 1), gy - co[1] * (gw / cs[0] if cs[0] else 1), gw / cs[0] if cs[0] else unit_mm)
                continue
            if tag not in ('rect', 'roundrect', 'oval', 'line', 'shape'):
                continue
            stroke = None if ch.get('stroked') in ('f', 'false') else '#' + (ch.get('strokecolor') or '#000000').lstrip('#')[:6]
            fill = None if ch.get('filled') in ('f', 'false') or not ch.get('fillcolor') else '#' + ch.get('fillcolor').lstrip('#')[:6]
            if tag == 'line':
                fx, fy = [float(v.replace('pt', '')) for v in (ch.get('from') or '0,0').split(',')]
                tx, ty = [float(v.replace('pt', '')) for v in (ch.get('to') or '0,0').split(',')]
                u = PT_MM if unit_mm == PT_MM else unit_mm
                x0, y0, x1, y1 = ox + fx * u, oy + fy * u, ox + tx * u, oy + ty * u
                out.append({'kind': 'line', 'x': min(x0, x1), 'y': min(y0, y1), 'w': abs(x1 - x0), 'h': abs(y1 - y0), 'text': '',
                            'fill': None, 'stroke': stroke or '#000000', 'flipH': (x1 < x0) != (y1 < y0), 'flipV': False})
                continue
            x = ox + _len(css.get('left', css.get('margin-left', '0')), unit_mm)
            y = oy + _len(css.get('top', css.get('margin-top', '0')), unit_mm)
            w, h = _len(css.get('width', '0'), unit_mm), _len(css.get('height', '0'), unit_mm)
            tb = ch.find(V + 'textbox')
            txt = _shape_text(tb) if tb is not None else ''
            kind = {'rect': 'rect', 'roundrect': 'roundRect', 'oval': 'ellipse'}.get(tag, 'rect')
            if txt and fill is None and stroke is None:
                kind = 'text'
            out.append({'kind': kind, 'x': x, 'y': y, 'w': w, 'h': h, 'text': txt, 'fill': fill, 'stroke': stroke})
    walk(pict, 0.0, 0.0, PT_MM)
    if not out:
        return None
    x1 = max(s['x'] + s['w'] for s in out)
    y1 = max(s['y'] + s['h'] for s in out)
    return {'shapes': out, 'w': x1, 'h': y1, 'ox': 0.0, 'oy': 0.0, 'anchored': False}


def paragraph_diagram(p):
    """All drawn shapes of one paragraph merged into one diagram (None if it has none).
    Floating shapes keep their positions; inline ones are laid side by side."""
    parts = []
    # DrawingML (also the mc:Choice side of AlternateContent); VML only where it is not a fallback copy
    fallback_picts = set()
    for ac in p.iter(MC + 'AlternateContent'):
        fb = ac.find(MC + 'Fallback')
        if fb is not None:
            fallback_picts.update(id(pc) for pc in fb.iter(W + 'pict'))
    for d in p.iter(W + 'drawing'):
        r = drawing_shapes(d)
        if r:
            parts.append(r)
    for pc in p.iter(W + 'pict'):
        if id(pc) in fallback_picts:
            continue
        r = vml_shapes(pc)
        if r:
            parts.append(r)
    if not parts:
        return None
    shapes, cursor = [], 0.0
    for part in parts:
        dx, dy = (part['ox'], part['oy']) if part['anchored'] else (cursor, 0.0)
        for s in part['shapes']:
            s = dict(s)
            s['x'] += dx
            s['y'] += dy
            shapes.append(s)
        if not part['anchored']:
            cursor += part['w'] + 3
    x0 = min(s['x'] for s in shapes)
    y0 = min(s['y'] for s in shapes)
    for s in shapes:
        s['x'], s['y'] = round(s['x'] - x0, 2), round(s['y'] - y0, 2)
        s['w'], s['h'] = round(max(s['w'], 0), 2), round(max(s['h'], 0), 2)
    w = max(s['x'] + s['w'] for s in shapes)
    h = max(s['y'] + s['h'] for s in shapes)
    return {'type': 'diagram', 'w': round(w, 2), 'h': round(h, 2), 'shapes': shapes}
