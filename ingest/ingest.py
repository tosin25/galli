"""Galley ingest: turn a .docx manuscript into a structured content.json.

    python ingest/ingest.py manuscript.docx work/            -> work/content.json, work/media/*, work/ingest_report.txt

Reads the .docx directly (it is a zip of XML), so nothing has to be installed. Tagging is heuristic and
deliberately explainable: every decision that was not obvious is written to ingest_report.txt so the
designer can check it. Word styles win over guesses: a paragraph styled "Example", "Exercise" or "Note"
(or "Heading 1-3") is taken at its word; otherwise typed markers such as "Example 2:", "Exercise 3.1",
"Did you know?" are recognised.

Block types written: h2, h3, body, list, figure, table, note, example, exercise, rule, calc continuation
lines (calc), column sums (colsum) and drawn diagrams (diagram).

House rules built in: Word's automatic list numbers are recomputed from numbering.xml (never lost);
the text of drawn shapes is not repeated as body text; "=" continuation lines are kept with their calculation;
Th/H/T/U column sums, teaching notes and rule/example pairs are recognised.
Later: ambiguous paragraphs (listed under "review" in the report) can be sent to Claude for tagging.
"""
import json
import os
import re
import struct
import sys
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from docx_parts import Numbering, paragraph_diagram, text_of  # noqa: E402

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
WP = '{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}'

EXAMPLE_RX = re.compile(r'^(Worked example|Example|Activity|Investigation|Try this|Case study)\b\s*([\d.]*\d)?\s*[:.\-–]?\s*(.*)$', re.I)
EXERCISE_RX = re.compile(r'^(Exercise|Practice|Check your understanding|Test yourself|Review questions|Questions)\b\s*([\d.]*\d)?\s*[:.\-–]?\s*(.*)$', re.I)
NOTE_RX = re.compile(r"^(Did you know\??|Note|Remember|Tip|Fun fact|Key words?|Safety|Hint|Teaching (?:guide|note)|Teacher'?s? (?:note|guide)|Note to (?:the )?teachers?)\s*[:?!.]\s*(.*)$", re.I)
TEACHING_RX = re.compile(r'^(teaching|teacher|note to)', re.I)
RULE_RX = re.compile(r'^(.{2,40}?\bRule)\s*[:.\-–]\s*(.+)$')
RULE_EX_RX = re.compile(r'^(Examples?|e\.g\.|For example)\s*[:.\-–]?\s*(.*)$', re.I)
PART_RX = re.compile(r'^(Theme|Part|Strand|Module)\s+(\w+)\s*[:.\-–]?\s*(.*)$', re.I)
LABEL_RX = re.compile(r'^\s*(\(?(\d{1,3}|[a-zA-Z]|[ivxlcIVXLC]{1,6})[.)]|\((\d{1,3}|[a-zA-Z]|[ivxlcIVXLC]{1,6})\))\s+(.*)$')
PV_HEADS = {'TTh', 'HTh', 'Th', 'H', 'T', 'U', 'O', 'M', 'TM', 'HM', 'Tth', 'Hth'}
SUM_ROW_RX = re.compile(r'^[\d\s+\-−×x=]+$')
STEP_RX = re.compile(r'^(Question|Think|Answer|Solution|Conclusion|Result|You need|Method|Step \d+)\s*:\s*(.*)$', re.I)
CLOSERS = ('answer', 'solution', 'conclusion', 'result')
CAPTION_RX = re.compile(r'^(Figure|Fig\.|Picture|Diagram)\s*[\d.]+', re.I)
QNUM_RX = re.compile(r'^\s*(\d{1,3})[.)]\s+(.*)$')
ROMAN_RX = re.compile(r'^[ivxlc]+$', re.I)
OPT_RX = re.compile(r'\(([a-h])\)\s*')
BULLET_RX = re.compile(r'^\s*[•\-*●]\s+(.*)$')
CHAPTER_RX = re.compile(r'^(Chapter|Unit|Module|Lesson)\s+(\w+)\s*[:.\-–]?\s*(.*)$', re.I)


def img_size(data):
    """pixel width/height of a PNG or JPEG"""
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return struct.unpack('>II', data[16:24])
    if data[:2] == b'\xff\xd8':
        i = 2
        while i < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            m = data[i + 1]
            if m in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack('>HH', data[i + 5:i + 9])
                return w, h
            i += 2 + struct.unpack('>H', data[i + 2:i + 4])[0]
    return 0, 0


class Ingest:
    def __init__(self, docx, outdir):
        self.z = zipfile.ZipFile(docx)
        self.outdir = outdir
        self.report, self.review = [], []
        self.styles = self._styles()
        self.rels = self._rels()
        try:
            self.numbering = Numbering(self.z.read('word/numbering.xml'))
        except KeyError:
            self.numbering = Numbering(None)
        os.makedirs(os.path.join(outdir, 'media'), exist_ok=True)

    def _styles(self):
        names = {}
        try:
            root = ET.fromstring(self.z.read('word/styles.xml'))
            for s in root.iter(W + 'style'):
                n = s.find(W + 'name')
                names[s.get(W + 'styleId')] = (n.get(W + 'val') if n is not None else s.get(W + 'styleId')).lower()
        except KeyError:
            pass
        return names

    def _rels(self):
        rels = {}
        try:
            root = ET.fromstring(self.z.read('word/_rels/document.xml.rels'))
            for r in root:
                rels[r.get('Id')] = r.get('Target')
        except KeyError:
            pass
        return rels

    # ---- pass 1: flat list of raw items in document order
    def raw(self):
        root = ET.fromstring(self.z.read('word/document.xml'))
        body = root.find(W + 'body')
        items = []
        for el in body:
            if el.tag == W + 'tbl':
                rows = []
                for tr in el.iter(W + 'tr'):
                    rows.append([' '.join(text_of(p) for p in tc.iter(W + 'p')).strip() for tc in tr.iter(W + 'tc')])
                items.append({'k': 'table', 'rows': rows})
                continue
            if el.tag != W + 'p':
                continue
            ppr = el.find(W + 'pPr')
            sid, label, lkind, level = '', '', 'none', 0
            if ppr is not None:
                ps = ppr.find(W + 'pStyle')
                if ps is not None:
                    sid = ps.get(W + 'val')
                npr = ppr.find(W + 'numPr')
                if npr is not None:
                    nid = npr.find(W + 'numId')
                    il = npr.find(W + 'ilvl')
                    level = int(il.get(W + 'val')) if il is not None else 0
                    # Word's automatic number, recomputed from numbering.xml (it is not in the text)
                    label, lkind = self.numbering.label(nid.get(W + 'val') if nid is not None else '0', level)
            style = self.styles.get(sid, sid).lower()
            for blip in el.iter(A + 'blip'):
                items.append(self._image(blip.get(R + 'embed'), el))
            t = text_of(el)
            if t:
                items.append({'k': 'p', 'style': style, 'text': t, 'numbered': lkind != 'none',
                              'label': '' if lkind == 'bullet' else label, 'lkind': lkind, 'level': level})
            dg = paragraph_diagram(el)
            if dg:
                items.append({'k': 'diagram', 'd': dg})
        return items

    def _image(self, rid, p):
        target = self.rels.get(rid, '')
        name = os.path.basename(target)
        data = self.z.read('word/' + target)
        with open(os.path.join(self.outdir, 'media', name), 'wb') as f:
            f.write(data)
        w, h = img_size(data)
        ext = next(p.iter(WP + 'extent'), None)
        if ext is not None:  # size the designer set in Word (EMU -> mm)
            wmm, hmm = int(ext.get('cx')) / 36000.0, int(ext.get('cy')) / 36000.0
        else:
            wmm, hmm = 120.0, 120.0 * h / w if w else 90.0
        return {'k': 'img', 'src': 'media/' + name, 'px': [w, h], 'mm': [round(wmm, 1), round(hmm, 1)]}

    # ---- pass 2: structure
    def build(self):
        items = self.raw()
        meta = {'book': '', 'chapter_no': '', 'chapter_title': '', 'objectives_intro': '', 'objectives': [], 'part_no': '', 'part_title': ''}
        blocks = []
        box = None  # open example / exercise being filled
        self.labels = []  # every list number in reading order, for the QA "no number lost" check

        def close():
            nonlocal box
            if box is not None:
                blocks.append(box)
            box = None

        def label_of(it):
            """(label, text, kind, level): Word's automatic number first, then a number typed in the text."""
            t = it['text']
            if it.get('label'):
                return it['label'], t, it['lkind'], it['level']
            m = LABEL_RX.match(t)
            if m:
                core = m.group(2) or m.group(3)
                kind = 'decimal' if core.isdigit() else ('roman' if ROMAN_RX.match(core) and len(core) > 1 else 'letter')
                return m.group(1), m.group(4), kind, 0 if kind == 'decimal' else 1
            return '', t, 'none', 0

        def calc_cont(i):
            """'=' continuation lines (and 'Or ... = ...' lines) that belong to the calculation before them."""
            lines = []
            while i < len(items) and items[i]['k'] == 'p' and not items[i].get('label') and \
                    (items[i]['text'].lstrip().startswith('=') or re.match(r'^Or\b.*=', items[i]['text'])):
                lines.append(items[i]['text'].strip())
                i += 1
            return lines, i

        def colsum(i):
            """rows of digits under a Th/H/T/U heading row -> one column-sum block"""
            rows = []
            while i < len(items) and items[i]['k'] == 'p' and SUM_ROW_RX.match(items[i]['text']) and items[i]['text'].strip():
                rows.append(re.findall(r'[+\-−×x=]|\d', items[i]['text']))
                i += 1
            return {'type': 'colsum', 'head': [], 'rows': rows}, i

        def add(block):
            """into the open box when there is one, else as a page-level block"""
            if box is not None and box['type'] in ('example', 'exercise'):
                box['items'].append(block)
            else:
                blocks.append(block)

        i = 0
        while i < len(items):
            it = items[i]
            i += 1
            if it['k'] == 'table':
                close()
                rows = [r for r in it['rows'] if any(c.strip() for c in r)]
                head = len(rows) > 1 and all(c and len(c) < 30 and not re.search(r'\d', c) for c in rows[0])
                blocks.append({'type': 'table', 'rows': rows, 'header': head})
                continue
            if it['k'] == 'diagram':
                d = it['d']
                self.report.append('drawn diagram: %d shapes, %.0f x %.0f mm' % (len(d['shapes']), d['w'], d['h']))
                add(d)
                continue
            if it['k'] == 'img':
                fig = {'type': 'figure', 'src': it['src'], 'mm': it['mm'], 'px': it['px'], 'caption': ''}
                if i < len(items) and items[i]['k'] == 'p' and ('caption' in items[i]['style'] or CAPTION_RX.match(items[i]['text'])):
                    fig['caption'] = items[i]['text']
                    i += 1
                if box is not None and box['type'] == 'example':
                    box['items'].append(fig)
                else:
                    close()
                    blocks.append(fig)
                continue

            t, style = it['text'], it['style']
            # headings: Word styles first
            hm = re.match(r'heading (\d)', style) or (re.match(r'title', style) and [None, '1'])
            if hm:
                close()
                lvl = int(hm[1])
                cm = CHAPTER_RX.match(t)
                pm = PART_RX.match(t)
                if lvl == 1 and pm and not meta['chapter_title']:
                    meta['part_no'], meta['part_title'] = pm.group(2), pm.group(3).strip()
                    self.report.append('part/theme: %r' % t)
                    continue
                if lvl == 1 and not meta['chapter_title']:
                    meta['chapter_no'] = cm.group(2) if cm else ''
                    meta['chapter_title'] = (cm.group(3) if cm else t).strip()
                    self.report.append('chapter title from Heading 1: %r' % t)
                    # "In this chapter you will learn:" + bullets -> objectives
                    if i < len(items) and items[i]['k'] == 'p' and items[i]['text'].endswith(':'):
                        j = i + 1
                        objs = []
                        while j < len(items) and items[j]['k'] == 'p' and (items[j]['numbered'] or BULLET_RX.match(items[j]['text'])):
                            objs.append(BULLET_RX.sub(r'\1', items[j]['text']))
                            j += 1
                        if objs:
                            meta['objectives_intro'], meta['objectives'] = items[i]['text'], objs
                            self.report.append('objectives: %d bullets after %r' % (len(objs), items[i]['text']))
                            i = j
                    continue
                blocks.append({'type': 'h2' if lvl <= 2 else 'h3', 'text': t})
                continue
            if not meta['chapter_title'] and not blocks:
                cm, pm = CHAPTER_RX.match(t), PART_RX.match(t)
                if pm and not meta['part_no']:
                    meta['part_no'], meta['part_title'] = pm.group(2), pm.group(3).strip()
                    self.report.append('part/theme from typed line: %r' % t)
                elif cm:  # typed chapter line without a heading style
                    meta['chapter_no'], meta['chapter_title'] = cm.group(2), cm.group(3).strip()
                    self.report.append('chapter title from typed line: %r' % t)
                else:
                    meta['book'] = meta['book'] or t
                    self.report.append('book/running head from first line: %r' % t)
                continue

            # column sums: a Th / H / T / U heading row
            toks = t.split()
            if len(toks) >= 2 and all(x in PV_HEADS for x in toks):
                cs, j = colsum(i)
                if cs['rows']:
                    cs['head'] = toks
                    i = j
                    self.report.append('column sum: %s, %d rows' % (' '.join(toks), len(cs['rows'])))
                    add(cs)
                    continue

            # rule / example pairs ("Addition Rule: ..." then "Example: ...")
            if blocks and blocks[-1]['type'] == 'rule' and box is None:
                rx = RULE_EX_RX.match(t)
                if rx or (len(t) < 70 and '=' in t and not it.get('label')):
                    blocks[-1]['examples'].append(rx.group(2) if rx else t)
                    continue
            rm = RULE_RX.match(t)
            if rm and not it.get('label'):
                close()
                blocks.append({'type': 'rule', 'title': rm.group(1).strip(), 'text': rm.group(2).strip(), 'examples': []})
                self.report.append('rule: %r' % rm.group(1))
                continue

            # box markers (a Word style named example/exercise/note also counts)
            em, xm, nm = EXAMPLE_RX.match(t), EXERCISE_RX.match(t), NOTE_RX.match(t)
            if 'example' in style or 'activity' in style or (em and len(t) < 90):
                close()
                label = (em.group(1).capitalize() + (' ' + em.group(2) if em.group(2) else '')) if em else 'Example'
                box = {'type': 'example', 'kind': 'activity' if label.lower().startswith(('activity', 'investigation', 'try')) else 'example',
                       'label': label, 'title': em.group(3).strip() if em else t, 'items': []}
                self.report.append('example box: %r' % t)
                continue
            if 'exercise' in style or (xm and len(t) < 70):
                close()
                box = {'type': 'exercise', 'label': (xm.group(1).capitalize() + (' ' + xm.group(2) if xm.group(2) else '')) if xm else 'Exercise',
                       'title': xm.group(3).strip() if xm else '', 'items': []}
                self.report.append('exercise box: %r' % t)
                continue
            if 'note' in style or nm:
                close()
                label = nm.group(1) if nm else 'Note'
                label = label[0].upper() + label[1:]
                if label.lower().startswith('did you know') and not label.endswith('?'):
                    label += '?'
                note = {'type': 'note', 'label': label, 'text': nm.group(2) if nm else t}
                if TEACHING_RX.match(label):
                    note['kind'] = 'teaching'
                blocks.append(note)
                self.report.append('note: %r%s' % (label, ' (teaching)' if note.get('kind') else ''))
                continue

            lab, body, lkind, level = label_of(it)
            calc, i = calc_cont(i)
            if lab:
                self.labels.append(lab)
            is_bullet = it.get('lkind') == 'bullet' or 'list' in style or BULLET_RX.match(t)
            if box is not None and box['type'] == 'exercise':
                if lab:
                    # a typed letter/roman item only counts as a sub-question after a numbered question
                    if not it.get('label') and lkind != 'decimal' and \
                            not any(q.get('type') == 'question' and q.get('kind') == 'decimal' for q in box['items']):
                        level = 0
                    q = self.question(lab, body)
                    q.update(label=lab, kind=lkind, level=level)
                    if calc:
                        q['calc'] = calc
                    box['items'].append(q)
                elif is_bullet:
                    box['items'].append(self.question('', BULLET_RX.sub(r'\1', t)))
                else:
                    ins = {'type': 'instruction', 'text': t}
                    if calc:
                        ins['calc'] = calc
                    box['items'].append(ins)
                continue
            if box is not None and box['type'] == 'example':
                sm = STEP_RX.match(t)
                if sm:
                    box['items'].append({'type': 'step', 'label': sm.group(1), 'text': sm.group(2), 'calc': calc})
                    if sm.group(1).lower() in CLOSERS:
                        close()
                elif lab:
                    box['items'].append({'type': 'item', 'label': lab, 'kind': lkind, 'level': level, 'text': body, 'calc': calc})
                elif is_bullet:
                    box['items'].append({'type': 'list', 'items': [BULLET_RX.sub(r'\1', t)]})
                else:
                    box['items'].append({'type': 'body', 'text': t, 'calc': calc})
                continue
            if lab:
                # numbered points stay numbered (never turned into bullets)
                item = {'label': lab, 'text': body, 'level': level, 'kind': lkind}
                if blocks and blocks[-1]['type'] == 'list' and blocks[-1].get('ordered'):
                    blocks[-1]['items'].append(item)
                else:
                    blocks.append({'type': 'list', 'ordered': True, 'items': [item]})
                continue
            if is_bullet:
                txt = BULLET_RX.sub(r'\1', t)
                if blocks and blocks[-1]['type'] == 'list' and not blocks[-1].get('ordered'):
                    blocks[-1]['items'].append(txt)
                else:
                    blocks.append({'type': 'list', 'items': [txt]})
                continue
            if CAPTION_RX.match(t):
                self.review.append('caption with no picture before it: %r' % t[:60])
            if len(t) < 40 and not re.search(r'[.?!:=]$', t) and '=' not in t:
                self.review.append('short line set as body (heading?): %r' % t)
            b = {'type': 'body', 'text': t}
            if calc:
                b['calc'] = calc
            blocks.append(b)
        close()
        # a question followed by its own sub-questions, a drawing or a sum gets no answer lines of its own:
        # the sub-parts or the drawn boxes are where pupils answer
        for b in blocks:
            if b['type'] != 'exercise':
                continue
            its = b['items']
            for k in range(len(its) - 1):
                q, nx = its[k], its[k + 1]
                if q.get('type') == 'question' and (nx.get('type') in ('diagram', 'colsum') or (nx.get('type') == 'question' and nx.get('level', 0) > q.get('level', 0))):
                    q['answer'] = 'none'
        # a lead-in body line ending in ":" belongs with the list, diagram or sum after it
        for k in range(len(blocks) - 1):
            if blocks[k]['type'] == 'body' and blocks[k]['text'].endswith(':') and blocks[k + 1]['type'] in ('list', 'diagram', 'colsum'):
                blocks[k]['lead_in'] = True
        meta['labels'] = self.labels
        return {'meta': meta, 'blocks': blocks}

    def question(self, n, t):
        q = {'type': 'question', 'n': n, 'text': t, 'options': [], 'answer': 'none'}
        parts = OPT_RX.split(t)
        if len(parts) >= 5:  # stem (a) x (b) y ...
            q['text'] = parts[0].strip()
            q['options'] = [parts[k + 1].strip() for k in range(1, len(parts) - 1, 2)]
        elif '___' in t:
            q['answer'] = 'inline'
        elif re.match(r'(explain|describe|why|write|what|how)\b', t, re.I) or t.endswith('?'):
            q['answer'] = 'lines2' if len(t) < 70 else 'lines3'
            if re.match(r'(explain|describe)\b', t, re.I):
                q['answer'] = 'lines3'
        elif re.match(r'put .* in order', t, re.I):
            q['answer'] = 'lines1'
        return q


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    ing = Ingest(src, out)
    data = ing.build()
    data['meta']['source'] = os.path.basename(src)
    with open(os.path.join(out, 'content.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    counts = {}
    for b in data['blocks']:
        counts[b['type']] = counts.get(b['type'], 0) + 1
    lines = ['Galley ingest report', 'source: ' + src, 'blocks: ' + ', '.join('%s=%d' % kv for kv in sorted(counts.items())), '', 'decisions:']
    lines += ['  ' + r for r in ing.report]
    lines += ['', 'please review (%d):' % len(ing.review)] + ['  ' + r for r in ing.review]
    with open(os.path.join(out, 'ingest_report.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print('\n'.join(lines[:3]))


if __name__ == '__main__':
    main()
