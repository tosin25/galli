// Galley QA + export for the active document (or the .indd named in scriptArgs galley_doc).
// Checks: overset text, boxes / figures / tables split across pages, stranded headings, objects off the page,
// missing links, low-resolution images, empty pages. Writes qa.json + qa.txt, a PDF and one PNG per page.
#target indesign
(function () {
  var SA = app.scriptArgs;
  function arg(k, d) { return SA.isDefined(k) && SA.getValue(k) != '' ? SA.getValue(k) : d; }
  app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
  var docPath = arg('galley_doc', ''), doc = docPath ? app.open(File(docPath)) : app.activeDocument;
  var OUT = Folder(arg('galley_out', doc.filePath)), exportIt = arg('galley_export', '1') == '1';
  // measure in mm through the script's own units: the document and its undo history are never touched
  var SMU = app.scriptPreferences.measurementUnit; app.scriptPreferences.measurementUnit = MeasurementUnits.MILLIMETERS;
  doc.recompose();
  var PW = doc.documentPreferences.pageWidth, PH = doc.documentPreferences.pageHeight, BL = doc.documentPreferences.documentBleedTopOffset;
  var errors = [], warns = [], checks = { overset: 0, split_boxes: 0, stranded_headings: 0, off_page: 0, links: 0, empty_pages: 0, widows_orphans: 0, numbering: 0, calc_alignment: 0 };
  function pgName(o) { try { return o.parentPage ? o.parentPage.name : '?'; } catch (e) { return '?'; } }
  function E(check, page, msg) { errors.push({ check: check, page: String(page), msg: msg }); checks[check] = (checks[check] || 0) + 1; }
  function Wn(check, page, msg) { warns.push({ check: check, page: String(page), msg: msg }); }
  function esc(s) { return String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/[\x00-\x1f﻿]/g, ' '); }
  function clip(s) { s = String(s).replace(/[\r\n]+/g, ' '); return s.length > 48 ? s.substr(0, 48) + '...' : s; }

  // 1. overset text (stories and table cells)
  var stories = doc.stories.everyItem().getElements(), main = null;
  for (var i = 0; i < stories.length; i++) {
    var s = stories[i];
    if (!main || s.characters.length > main.characters.length) main = s;
    if (s.overflows) E('overset', pgName(s.textContainers[s.textContainers.length - 1]), 'overset text: ' + clip(s.contents.substr(-60)));
    var tbs = s.tables.everyItem().getElements();
    for (var t = 0; t < tbs.length; t++) { var cl = tbs[t].cells.everyItem().getElements();
      for (var c = 0; c < cl.length; c++) if (cl[c].overflows) E('overset', '?', 'table cell overset: ' + clip(cl[c].contents)); }
  }
  function frameOf(p) { try { return p.parentTextFrames[0]; } catch (e) { return null; } }
  function pageOfText(p) { var f = frameOf(p); return f && f.parentPage ? f.parentPage.name : '?'; }

  // 2. boxes split across frames. Boxes are found from paragraph styles, not from positions saved at build time,
  // so the check stays right after the designer edits the text. Designer files: the copilot's mapping says which
  // of their styles belong to which box.
  var MAP = {}; try { MAP = eval('(' + doc.extractLabel('galley_map') + ')') || {}; } catch (e) {}
  var ROLEFAM = { example_head: 'Example', example_body: 'Example', example_step: 'Example', activity_head: 'Activity', activity_body: 'Activity',
    activity_step: 'Activity', exercise_head: 'Exercise', exercise_instruction: 'Exercise', question: 'Exercise', options: 'Exercise', answer_line: 'Exercise',
    note: 'Note', objectives_head: 'Objectives', objective: 'Objectives' };
  var shared = {}, FAM = {}, BOXHEAD = {}, r0;
  for (r0 in MAP) if (r0.charAt(0) != '_' && !ROLEFAM[r0]) shared[MAP[r0]] = 1; // a style also used for plain text marks no box
  for (r0 in ROLEFAM) if (MAP[r0] && !shared[MAP[r0]]) { FAM[MAP[r0]] = ROLEFAM[r0]; if (/_head$/.test(r0)) BOXHEAD[MAP[r0]] = 1; }
  function family(n) {
    if (FAM[n]) return FAM[n];
    var m = n.match(/^(Example|Activity|Exercise|Objectives)\b/); if (m) return m[1];
    if (n == 'Objective') return 'Objectives';
    if (n == 'Note' || n == 'Calculation') return n;
    return '';
  }
  function isBoxHead(n) { return BOXHEAD[n] == 1 || /^(Example|Activity|Exercise|Objectives) Head$/.test(n); }
  var QSTART = /^\(?(\d{1,3})[.)]?\t/; // where a long exercise may continue: before a numbered question
  for (var si = 0; si < stories.length; si++) {
    var SP = stories[si].paragraphs.everyItem().getElements(), runs = [], cur = null;
    for (var q0 = 0; q0 < SP.length; q0++) {
      var nm0 = '', f = ''; try { nm0 = SP[q0].appliedParagraphStyle.name; f = family(nm0); } catch (e) {}
      if (!f) { cur = null; continue; }
      if (f == 'Note') { runs.push({ f: f, ps: [SP[q0]] }); cur = null; continue; }
      if (!cur || cur.f != f || isBoxHead(nm0)) { cur = { f: f, ps: [] }; runs.push(cur); }
      cur.ps.push(SP[q0]);
    }
    for (var ri = 0; ri < runs.length; ri++) {
      var ps = runs[ri].ps, fa = frameOf(ps[0]), fz = frameOf(ps[ps.length - 1]);
      if (!fa || !fz) continue;
      var split = fa.id != fz.id || ps[0].parentTextFrames.length > 1 || ps[ps.length - 1].parentTextFrames.length > 1;
      if (!split) continue;
      var cont = null; // the first paragraph on the later page
      for (var pj = 1; pj < ps.length; pj++) if (frameOf(ps[pj]) && frameOf(ps[pj]).id != fa.id) { cont = ps[pj]; break; }
      var label = runs[ri].f == 'Calc' ? 'Calculation' : runs[ri].f;
      if (runs[ri].f == 'Exercise' && cont && QSTART.test(cont.contents))
        Wn('split_boxes', fa.parentPage.name, label + ' continues onto page ' + fz.parentPage.name + ' before question ' + cont.contents.match(QSTART)[1] + ' (allowed: it breaks between questions)');
      else E('split_boxes', fa.parentPage.name, label + ' box split across pages ' + fa.parentPage.name + '-' + fz.parentPage.name + ': ' + clip(ps[0].contents));
    }
    // figures stay with their captions; tables stay whole
    for (q0 = 0; q0 < SP.length - 1; q0++) {
      var nmF = ''; try { nmF = SP[q0].appliedParagraphStyle.name; } catch (e) {}
      if ((nmF == 'Figure' || nmF == MAP.figure) && SP[q0].allGraphics.length) {
        var capN = ''; try { capN = SP[q0 + 1].appliedParagraphStyle.name; } catch (e) {}
        if ((capN == 'Caption' || capN == MAP.caption) && frameOf(SP[q0]) && frameOf(SP[q0 + 1]) && frameOf(SP[q0]).id != frameOf(SP[q0 + 1]).id)
          E('split_boxes', frameOf(SP[q0]).parentPage.name, 'figure and its caption are on different pages: ' + clip(SP[q0 + 1].contents));
      }
    }
    var TBL = stories[si].tables.everyItem().getElements();
    for (var ti = 0; ti < TBL.length; ti++) {
      try { var c0 = TBL[ti].cells[0].insertionPoints[0].parentTextFrames[0], c1 = TBL[ti].cells[-1].insertionPoints[0].parentTextFrames[0];
        if (c0 && c1 && c0.id != c1.id) E('split_boxes', c0.parentPage.name, 'table split across pages ' + c0.parentPage.name + '-' + c1.parentPage.name); } catch (e) {}
    }
  }
  // 3. stranded headings: a heading style that is the last paragraph of a frame while the story continues
  var HEADS = /^(H2|H3|Example Head|Activity Head|Exercise Head|Objectives Head|Chapter Title)$/;
  // a document styled by the designer: the copilot's style mapping says which of their styles are headings
  var HEADNAMES = {};
  try { var HR = ['h2', 'h3', 'chapter_title', 'example_head', 'activity_head', 'exercise_head', 'objectives_head'];
    for (var hr = 0; hr < HR.length; hr++) if (MAP[HR[hr]]) HEADNAMES[MAP[HR[hr]]] = 1; } catch (e) {}
  function isHead(n) { return HEADS.test(n) || HEADNAMES[n] == 1; }
  for (var sk = 0; sk < stories.length; sk++) {
    var tc = stories[sk].textContainers; if (tc.length < 2) continue;
    for (i = 0; i < tc.length - 1; i++) {
      try { var lp = tc[i].paragraphs[-1]; if (!tc[i + 1].characters.length || lp.parentTextFrames.length > 1) continue;
        if (isHead(lp.appliedParagraphStyle.name)) E('stranded_headings', tc[i].parentPage.name, 'heading at the foot of the page: ' + clip(lp.contents)); } catch (e) {}
    }
  }
  // ---- house rules ------------------------------------------------------------------------------------
  // H1. widows and orphans: a paragraph that breaks across pages keeps at least 2 lines on each side
  function frameId(o) { try { return o.parentTextFrames[0].id; } catch (e) { return -1; } }
  for (var sw = 0; sw < stories.length; sw++) {
    var st0 = stories[sw]; if (st0.textContainers.length < 2) continue;
    var PP = st0.paragraphs.everyItem().getElements();
    for (var pi = 0; pi < PP.length; pi++) {
      var pp = PP[pi]; if (pp.parentTextFrames.length < 2) continue;
      var LL = pp.lines.everyItem().getElements(); if (LL.length < 2) continue;
      var fA = frameId(LL[0]), nA = 0, fZ = frameId(LL[LL.length - 1]), nZ = 0;
      for (var li = 0; li < LL.length; li++) { var fi = frameId(LL[li]); if (fi == fA) nA++; if (fi == fZ) nZ++; }
      var need = Math.min(2, LL.length - 1);
      if (nA < need) E('widows_orphans', pp.parentTextFrames[0].parentPage.name, 'orphan: only ' + nA + ' line at the foot of the page: ' + clip(pp.contents));
      else if (nZ < need) E('widows_orphans', pp.parentTextFrames[pp.parentTextFrames.length - 1].parentPage.name, 'widow: only ' + nZ + ' line at the top of the page: ' + clip(pp.contents));
    }
  }
  // H2. numbering: every number from the manuscript is still there, in front of the right text. Each expected
  // number is stored with the start of its text, and found by that text, so edits elsewhere don't confuse the check.
  for (var sn = 0; sn < stories.length; sn++) {
    var labTxt = stories[sn].extractLabel('galley_labels'); if (!labTxt) continue;
    var want = []; try { want = eval('(' + labTxt + ')'); } catch (e) {}
    var PN = stories[sn].paragraphs.everyItem().getElements(), at = 0;
    for (var wi = 0; wi < want.length; wi++) {
      var parts = String(want[wi]).split('\u0001'), lab = parts[0], txt = parts[1] || '';
      if (!txt) continue;
      for (var pn = at; pn < Math.min(PN.length, at + 60); pn++) if (PN[pn].contents.indexOf(txt) >= 0) break;
      if (pn >= Math.min(PN.length, at + 60)) continue; // text itself was edited: nothing to compare
      if (PN[pn].contents.indexOf(lab + '\t') != 0)
        E('numbering', pageOfText(PN[pn]), 'number "' + lab + '" from the manuscript is missing or changed before: ' + clip(txt));
      at = pn + 1;
    }
  }
  // H2b. a number must fit its number column: the text after the tab starts exactly at the paragraph's indent
  for (var sh = 0; sh < stories.length; sh++) {
    var PAR = stories[sh].paragraphs.everyItem().getElements();
    for (var ph = 0; ph < PAR.length; ph++) {
      var hp = PAR[ph], tab = hp.contents.indexOf('\t');
      if (tab < 1 || tab > 8 || !(hp.firstLineIndent < -0.5) || !/^\(?[\dA-Za-z]{1,6}[.)]/.test(hp.contents)) continue;
      try { var hf = hp.parentTextFrames[0], ch = hp.characters[tab + 1];
        var want0 = hf.geometricBounds[1] + hf.textFramePreferences.insetSpacing[1] + hp.leftIndent;
        if (ch && Math.abs(ch.horizontalOffset - want0) > 1.2) E('numbering', hf.parentPage.name, 'number "' + hp.contents.substr(0, tab) + '" is wider than its number column: ' + clip(hp.contents)); } catch (e) {}
    }
  }
  // H3. calculations: a line that starts with "=" (or "Or ... =") puts its "=" under the first "=" of the calculation above
  function eqX(p) { var k = p.contents.indexOf('='); if (k < 0) return null;
    try { var f = p.parentTextFrames[0]; return p.characters[k].horizontalOffset - f.geometricBounds[1]; } catch (e) { return null; } }
  for (var sc = 0; sc < stories.length; sc++) {
    var PC = stories[sc].paragraphs.everyItem().getElements();
    for (var pc = 1; pc < PC.length; pc++) {
      if (!/^\s*(=|Or\b.*=)/.test(PC[pc].contents)) continue;
      var hd = pc - 1; while (hd > 0 && /^\s*(=|Or\b)/.test(PC[hd].contents)) hd--;
      var x0 = eqX(PC[hd]), xq = eqX(PC[pc]);
      if (x0 !== null && xq !== null && Math.abs(xq - x0) > 0.8) E('calc_alignment', pageOfText(PC[pc]), '"=" is ' + Math.abs(xq - x0).toFixed(1) + ' mm off the first "=": ' + clip(PC[pc].contents));
    }
  }
  // H4. no unnecessary empty space: a page that is mostly empty although the text after it could have moved up
  if (main && main.textContainers.length > 1) {
    var TC = main.textContainers;
    for (i = 0; i < TC.length - 1; i++) {
      try {
        var tf = TC[i], nf = TC[i + 1]; if (!tf.lines.length || !nf.paragraphs.length) continue;
        var g = tf.geometricBounds, used = (tf.lines[-1].baseline - g[0]) / (g[2] - g[0]), np = nf.paragraphs[0];
        var forced = np.startParagraph == StartParagraph.NEXT_FRAME;
        if (used < 0.6 && !forced) Wn('empty_space', tf.parentPage.name, 'page is only ' + Math.round(used * 100) + '% full; what follows could not move up (box or picture too tall?)');
      } catch (e) {}
    }
  }
  // 4. objects off the page: outside the bleed = error; content (text, anchored art) outside the margins = warning
  var PAGE_RULER = doc.viewPreferences.rulerOrigin == RulerOrigin.PAGE_ORIGIN;
  function inspect(items, page, isMaster) {
    var mp = page.marginPreferences, side = page.side == PageSideOptions.LEFT_HAND;
    var mL = side ? mp.right : mp.left, mR = side ? mp.left : mp.right; // facing pages: left/right = inside/outside
    for (var j = 0; j < items.length; j++) {
      var it = items[j], gb;
      try { gb = it.visibleBounds; } catch (e) { continue; }
      // measure relative to this page: designer files usually use a spread ruler, so right-hand pages start at x = page width
      // with page rulers items are already page-relative (page.bounds would still be in spread coordinates)
      var pb = PAGE_RULER ? [0, 0] : page.bounds; gb = [gb[0] - pb[0], gb[1] - pb[1], gb[2] - pb[0], gb[3] - pb[1]];
      var out = gb[0] < -BL - 0.5 || gb[1] < -BL - 0.5 || gb[2] > PH + BL + 0.5 || gb[3] > PW + BL + 0.5;
      var label = it.constructor.name + (it.hasOwnProperty('contents') && typeof it.contents == 'string' && it.contents ? ' "' + clip(it.contents) + '"' : '');
      var hasContent = (it.hasOwnProperty('contents') && typeof it.contents == 'string' && it.contents != '') || (it.hasOwnProperty('allGraphics') && it.allGraphics.length > 0);
      var offTrim = gb[0] < -0.5 || gb[1] < -0.5 || gb[2] > PH + 0.5 || gb[3] > PW + 0.5;
      var gone = gb[2] < -BL || gb[0] > PH + BL || gb[3] < -BL || gb[1] > PW + BL;
      if (gone) E('off_page', (isMaster ? 'master ' : '') + page.name, label + ' lies completely off the page');
      else if (hasContent && offTrim && !(it instanceof TextFrame && it.contents == '')) E('off_page', (isMaster ? 'master ' : '') + page.name, label + ' is cut by the trim edge');
      else if (out) Wn('off_page', (isMaster ? 'master ' : '') + page.name, label + ' (decoration) extends beyond the bleed');
      else if (!isMaster && it.parent instanceof Character) {
        var over = Math.max(mL - gb[1], gb[3] - (PW - mR));
        if (over > 2) E('off_page', page.name, 'anchored ' + label + ' sticks out of the text column by ' + over.toFixed(1) + ' mm (clipped or crowding the margin)');
        else if (over > 1) Wn('off_page', page.name, 'anchored ' + label + ' touches the margin');
      }
    }
  }
  var pages = doc.pages.everyItem().getElements();
  for (i = 0; i < pages.length; i++) {
    inspect(pages[i].allPageItems, pages[i], false);
    var tfs = pages[i].textFrames.everyItem().getElements(), chars = 0;
    for (var q = 0; q < tfs.length; q++) chars += tfs[q].characters.length;
    if (chars == 0 && pages[i].allGraphics.length == 0) E('empty_pages', pages[i].name, 'page has no content');
  }
  var ms = doc.masterSpreads.everyItem().getElements();
  for (i = 0; i < ms.length; i++) for (var mpI = 0; mpI < ms[i].pages.length; mpI++) inspect(ms[i].pages[mpI].allPageItems, ms[i].pages[mpI], true);
  // 5. links
  var links = doc.links.everyItem().getElements();
  for (i = 0; i < links.length; i++) {
    var L = links[i], pg = '?';
    try { pg = L.parent.parent.parentPage.name; } catch (e) {}
    if (L.status == LinkStatus.LINK_MISSING) E('links', pg, 'missing image: ' + L.name);
    else if (L.status == LinkStatus.LINK_OUT_OF_DATE) Wn('links', pg, 'image changed on disk: ' + L.name);
    try { var ppi = L.parent.effectivePpi; if (ppi && ppi[0] < 150) Wn('links', pg, L.name + ' is ' + ppi[0] + ' ppi at this size (150+ wanted for print)'); } catch (e) {}
  }

  // ---- write report
  var json = '{"document":"' + esc(doc.name) + '","pages":' + doc.pages.length + ',"trim_mm":[' + PW + ',' + PH + '],"passed":' + (errors.length == 0) + ',"checks":{';
  var ck = []; for (var key in checks) ck.push('"' + key + '":' + checks[key]); json += ck.join(',') + '},"errors":[';
  function list(a) { var o = []; for (var q = 0; q < a.length; q++) o.push('{"check":"' + a[q].check + '","page":"' + esc(a[q].page) + '","msg":"' + esc(a[q].msg) + '"}'); return o.join(','); }
  json += list(errors) + '],"warnings":[' + list(warns) + ']}';
  function write(name, txt) { var f = File(OUT + '/' + name); f.encoding = 'UTF-8'; f.open('w'); f.write(txt); f.close(); }
  write('qa.json', json);
  var txt = ['QA ' + doc.name + ': ' + doc.pages.length + ' pages, ' + errors.length + ' errors, ' + warns.length + ' warnings'];
  for (i = 0; i < errors.length; i++) txt.push('ERROR  p' + errors[i].page + '  ' + errors[i].msg);
  for (i = 0; i < warns.length; i++) txt.push('warn   p' + warns[i].page + '  ' + warns[i].msg);
  write('qa.txt', txt.join('\n'));

  // ---- export
  if (exportIt) {
    doc.save();
    var preset = app.pdfExportPresets.itemByName('[High Quality Print]'); if (!preset.isValid) preset = app.pdfExportPresets[0];
    app.pdfExportPreferences.pageRange = PageRange.ALL_PAGES;
    try { app.pdfExportPreferences.useDocumentBleedWithPDF = true; } catch (e) {}
    doc.exportFile(ExportFormat.PDF_TYPE, File(OUT + '/' + doc.name.replace(/\.indd$/i, '') + '.pdf'), false, preset);
    var pv = Folder(OUT + '/previews'); if (!pv.exists) pv.create();
    var old = pv.getFiles('*.png'); for (i = 0; i < old.length; i++) old[i].remove();
    with (app.pngExportPreferences) { pngExportRange = PNGExportRangeEnum.EXPORT_ALL; exportResolution = 72; pngQuality = PNGQualityEnum.HIGH;
      antiAlias = true; transparentBackground = false; exportingSpread = false; useDocumentBleeds = false; }
    doc.exportFile(ExportFormat.PNG_FORMAT, File(pv + '/page.png'), false);
  }
  app.scriptPreferences.measurementUnit = SMU;
  app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;
})();
