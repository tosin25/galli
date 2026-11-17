"""InDesign bridge: the only place that talks to InDesign.

Works with any InDesign version that exposes Windows COM scripting (CS3 and later): it sends ExtendScript
to the running application with DoScript and reads back a JSON string. It never starts InDesign by itself;
if InDesign is not running, status() says so.

Every call that changes the document runs as ONE undo step ("Galley: ..."), so the designer can press
Ctrl+Z in InDesign to take back anything the copilot did.
"""
import json
import os
import subprocess
import threading

import pythoncom
import win32com.client

G = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = 1246973031            # ScriptLanguage.JAVASCRIPT
_lock = threading.Lock()   # InDesign runs one script at a time

# tiny JSON writer for ExtendScript (which has no JSON object)
PRELUDE = r"""
function __j(v){var t=typeof v;if(v===null||v===undefined)return 'null';if(t=='number')return isFinite(v)?String(v):'null';
if(t=='boolean')return v?'true':'false';if(t=='string')return '"'+v.replace(/\\/g,'\\\\').replace(/"/g,'\\"').replace(/\r|\n/g,'\\n').replace(/\t/g,'\\t')+'"';
if(v instanceof Array){var a=[];for(var i=0;i<v.length;i++)a.push(__j(v[i]));return '['+a.join(',')+']';}
var o=[];for(var k in v){if(v.hasOwnProperty(k))o.push(__j(String(k))+':'+__j(v[k]));}return '{'+o.join(',')+'}';}
"""


class InDesignNotRunning(Exception):
    pass


def running():
    """True when an InDesign process exists (checked without starting InDesign)."""
    try:
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq InDesign.exe', '/NH'], capture_output=True, text=True, timeout=5).stdout
        return 'InDesign.exe' in out
    except Exception:  # noqa: BLE001 - treat any failure as "not known to be running"
        return False


def _app():
    if not running():
        raise InDesignNotRunning('InDesign is not open. Open InDesign (any version) and Galley will connect.')
    pythoncom.CoInitialize()
    return win32com.client.Dispatch('InDesign.Application')


def js(code, undo_name=None, args=None):
    """Run ExtendScript code; the code's last expression must be a value built with __j(...). Returns parsed JSON."""
    with _lock:
        app = _app()
        if args:
            for k, v in args.items():
                app.ScriptArgs.SetValue(k, v if isinstance(v, str) else json.dumps(v))
        body = '(function(){try{' + code + '}catch(e){return __j({error:e.message,line:e.line});}})()'
        if undo_name:  # one undo step, opened from inside InDesign (the COM undo arguments are not applied reliably)
            src = (PRELUDE + '\nvar __r; app.doScript(function(){ __r = ' + body + '; }, ScriptLanguage.JAVASCRIPT, undefined, '
                   'UndoModes.ENTIRE_SCRIPT, ' + json.dumps('Galley: ' + undo_name) + '); __r;')
        else:
            src = PRELUDE + '\n' + body + ';'
        res = app.DoScript(src, JS)
    try:
        return json.loads(res) if isinstance(res, str) and res else res
    except ValueError:
        return {'error': 'unexpected reply from InDesign', 'raw': str(res)[:300]}


def run_file(path, args=None, undo_name=None):
    """Run a .jsx file through indesign/run.jsx (errors come back as text instead of a dialog)."""
    args = dict(args or {})
    result = os.path.join(os.environ.get('TEMP', G), 'galley_copilot_result.txt')
    if os.path.exists(result):
        os.remove(result)
    # run.jsx opens the single undo step itself when galley_undo is set (always set it: script args persist)
    args.update(galley_target=path, galley_result=result, galley_undo=('Galley: ' + undo_name) if undo_name else '')
    with _lock:
        app = _app()
        for k, v in args.items():
            app.ScriptArgs.SetValue(k, v if isinstance(v, str) else json.dumps(v))
        app.DoScript(os.path.join(G, 'indesign', 'run.jsx'), JS)
    with open(result, encoding='utf-8-sig') as f:
        return f.read()


# ---------------------------------------------------------------- read-only queries

STATUS_JS = r"""
var o = {version: app.version, docs: app.documents.length};
if (!app.documents.length) return __j(o);
var d = app.activeDocument; o.name = d.name; o.saved = d.saved;
try { o.path = d.fullName.fsName; } catch (e) { o.path = ''; }
o.pages = d.pages.length;
try { o.activePage = app.activeWindow.activePage.name; } catch (e) {}
try { o.trim = [d.documentPreferences.pageWidth, d.documentPreferences.pageHeight]; } catch (e) {}
var styles = [], ps = d.allParagraphStyles;
for (var i = 0; i < ps.length; i++) { var n = ps[i].name; if (n.charAt(0) != '[') styles.push(n); }
o.paragraphStyles = styles;
var cs = [], cc = d.allCharacterStyles; for (i = 0; i < cc.length; i++) if (cc[i].name.charAt(0) != '[') cs.push(cc[i].name);
o.characterStyles = cs;
var m = []; for (i = 0; i < d.masterSpreads.length; i++) m.push(d.masterSpreads[i].name); o.masters = m;
o.mapping = d.extractLabel('galley_map') || '';
var sel = app.selection; o.selection = null;
if (sel.length) {
  var s = sel[0], t = s.constructor.name, info = {type: t};
  try { if (s.hasOwnProperty('paragraphs') && s.paragraphs.length) { var p = s.paragraphs[0];
    info.style = p.appliedParagraphStyle.name; info.text = p.contents.substr(0, 80);
    info.overrides = p.styleOverridden; } } catch (e) {}
  try { info.page = s.parentTextFrames[0].parentPage.name; } catch (e) { try { info.page = s.parentPage.name; } catch (e2) {} }
  o.selection = info;
}
return __j(o);
"""


def status():
    if not running():
        return {'connected': False, 'message': 'InDesign is not open.'}
    if _lock.locked():  # a long job (flow, QA) is running: answer at once instead of queueing behind it
        return {'connected': True, 'busy': True}
    try:
        s = js(STATUS_JS)
        s['connected'] = True
        return s
    except Exception as e:  # noqa: BLE001 - surface COM errors (busy dialogs etc.) to the UI
        return {'connected': False, 'message': 'InDesign is busy or not responding (%s).' % str(e)[:120]}


def go_to_page(page):
    return js("""
var d = app.activeDocument, pg = d.pages.itemByName(%s);
if (!pg.isValid) return __j({ok:false, error:'no page ' + %s});
app.activeWindow.activePage = pg; try { app.activeWindow.zoom(ZoomOptions.FIT_PAGE); } catch (e) {}
return __j({ok:true, page: pg.name});""" % (json.dumps(str(page)), json.dumps(str(page))))


def check_document():
    """QA on the open document, no export. Returns the qa.json dict."""
    out = os.path.join(G, 'work', 'copilot')
    os.makedirs(out, exist_ok=True)
    qa = os.path.join(out, 'qa.json')
    if os.path.exists(qa):
        os.remove(qa)
    r = run_file(os.path.join(G, 'indesign', 'qa_export.jsx'), {'galley_doc': '', 'galley_out': out, 'galley_export': '0'})
    if r.strip() != 'OK':
        return {'error': r}
    with open(qa, encoding='utf-8-sig') as f:
        return json.load(f)


# ---------------------------------------------------------------- changes (each one undoable)

ALLOWED = {'pointSize', 'leading', 'spaceBefore', 'spaceAfter', 'leftIndent', 'rightIndent', 'firstLineIndent', 'tracking',
           'appliedFont', 'fontStyle', 'fillColor', 'justification', 'paragraphShadingOn', 'paragraphShadingColor',
           'paragraphShadingTint', 'ruleAbove', 'ruleBelow', 'ruleAboveColor', 'ruleBelowColor', 'keepWithNext', 'hyphenation'}


def update_paragraph_style(style, props):
    """Change properties of a paragraph style. Colours are '#RRGGBB' (a swatch is made) or a swatch name."""
    bad = [k for k in props if k not in ALLOWED]
    if bad:
        return {'ok': False, 'error': 'not allowed: ' + ', '.join(bad), 'allowed': sorted(ALLOWED)}
    return js(r"""
var d = app.activeDocument, P = eval('(' + app.scriptArgs.getValue('g_props') + ')'), name = app.scriptArgs.getValue('g_style');
var all = d.allParagraphStyles, s = null; for (var i = 0; i < all.length; i++) if (all[i].name == name) s = all[i];
if (!s) return __j({ok:false, error:'no paragraph style called ' + name});
function sw(v) { if (!/^#[0-9a-fA-F]{6}$/.test(v)) { var x = d.swatches.itemByName(v); if (!x.isValid) throw Error('no swatch ' + v); return x; }
  var nm = 'Galley ' + v.toUpperCase(), c = d.colors.itemByName(nm); if (c.isValid) return c;
  return d.colors.add({name:nm, model:ColorModel.PROCESS, space:ColorSpace.RGB, colorValue:[parseInt(v.substr(1,2),16),parseInt(v.substr(3,2),16),parseInt(v.substr(5,2),16)]}); }
var done = [], errs = [];
for (var k in P) { try { var v = P[k]; if (/Color$/.test(k)) v = sw(v);
  if (k == 'justification') v = Justification[String(v).toUpperCase() + '_ALIGN'] || v;
  s[k] = v; done.push(k); } catch (e) { errs.push(k + ': ' + e.message); } }
return __j({ok: errs.length == 0, style: name, changed: done, errors: errs});""",
              undo_name='change style ' + style, args={'g_style': style, 'g_props': json.dumps(props)})


def redefine_style_from_selection():
    """Copilot move: the designer tweaks one paragraph by hand, then 'apply to all' makes that look the style."""
    return js(r"""
if (!app.selection.length || !app.selection[0].hasOwnProperty('paragraphs')) return __j({ok:false, error:'Select some text in the paragraph you styled first.'});
var p = app.selection[0].paragraphs[0], s = p.appliedParagraphStyle;
if (s.name.charAt(0) == '[') return __j({ok:false, error:'The paragraph uses ' + s.name + '. Apply a named style first.'});
var keys = ['appliedFont','fontStyle','pointSize','leading','tracking','fillColor','justification','spaceBefore','spaceAfter','leftIndent','rightIndent',
  'firstLineIndent','paragraphShadingOn','paragraphShadingColor','paragraphShadingTint','ruleAbove','ruleAboveColor','ruleAboveLineWeight',
  'ruleBelow','ruleBelowColor','ruleBelowLineWeight','capitalization','underline'];
var changed = [];
for (var i = 0; i < keys.length; i++) { try { var a = p[keys[i]], b = s[keys[i]];
  var same = (a && a.hasOwnProperty && a.hasOwnProperty('name') && b && b.hasOwnProperty && b.hasOwnProperty('name')) ? a.name == b.name : a == b;
  if (!same) { s[keys[i]] = a; changed.push(keys[i]); } } catch (e) {} }
// count where the style is used; the edited paragraph now matches its style, so drop its local overrides
var n = 0, st = app.activeDocument.stories.everyItem().getElements();
for (var j = 0; j < st.length; j++) { var ps = st[j].paragraphs.everyItem().getElements();
  for (var q = 0; q < ps.length; q++) if (ps[q].appliedParagraphStyle.id == s.id) n++; }
p.clearOverrides(OverrideType.PARAGRAPH_ONLY);
return __j({ok:true, style: s.name, changed: changed, paragraphs: n});""", undo_name='apply look to all')


def save_mapping(mapping):
    return js(r"""app.activeDocument.insertLabel('galley_map', app.scriptArgs.getValue('g_map')); return __j({ok:true});""",
              undo_name='save style mapping', args={'g_map': json.dumps(mapping)})


def flow_manuscript(content_path, mapping):
    """Mode A: flow content.json into the OPEN document after its last page, using the designer's own styles."""
    out = os.path.join(G, 'work', 'copilot')
    os.makedirs(out, exist_ok=True)
    rep = os.path.join(out, 'flow_report.json')
    if os.path.exists(rep):
        os.remove(rep)
    r = run_file(os.path.join(G, 'indesign', 'flow_into.jsx'),
                 {'galley_content': content_path, 'galley_map': json.dumps(mapping), 'galley_art': os.path.join(G, 'art'), 'galley_report': rep},
                 undo_name='flow manuscript')
    if r.strip() != 'OK':
        return {'ok': False, 'error': r}
    with open(rep, encoding='utf-8-sig') as f:
        return json.load(f)
