// Galley "continue in my style": flows content.json into the OPEN document, after its last page, using the
// designer's own paragraph styles (a role -> style mapping confirmed in the copilot). Nothing is restyled:
// the document's styles decide the look; Galley adds pages, text, anchored figures, tables and keep rules.
// Run from the copilot as one undo step. Arguments (app.scriptArgs): galley_content, galley_map, galley_report.
#target indesign
(function () {
  var SA = app.scriptArgs;
  function arg(k, d) { return SA.isDefined(k) && SA.getValue(k) != '' ? SA.getValue(k) : d; }
  function readJSON(f) { f.encoding = 'UTF-8'; f.open('r'); var s = f.read(); f.close(); return eval('(' + s + ')'); }
  var CONTENT = File(arg('galley_content', '')), MAP = eval('(' + arg('galley_map', '{}') + ')');
  var D = readJSON(CONTENT), M = D.meta, BL = D.blocks, BASE = CONTENT.parent;
  var doc = app.activeDocument, LOG = [], USED = {}, FALLBACK = {}, k, i;
  app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
  // work in mm, restore the designer's units at the end
  var VH = doc.viewPreferences.horizontalMeasurementUnits, VV = doc.viewPreferences.verticalMeasurementUnits;
  doc.viewPreferences.horizontalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  doc.viewPreferences.verticalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  // page rulers while we work (designer files often use spread rulers; anchored pictures misbehave on right pages)
  var RO = doc.viewPreferences.rulerOrigin; doc.viewPreferences.rulerOrigin = RulerOrigin.PAGE_ORIGIN;

  // ---------------------------------------------------------------- styles: mapped role -> designer's style, with fallbacks
  var FB = { chapter_label: ['h3'], chapter_title: ['h2'], objectives_head: ['h3', 'h2'], objective: ['list', 'body'], h3: ['h2'], list: ['body'],
    figure: ['body'], caption: ['body'], table: ['body'], table_head: ['table_body', 'body'], table_body: ['body'], note: ['body'],
    example_head: ['h3', 'h2'], example_body: ['body'], example_step: ['example_body', 'body'],
    activity_head: ['example_head', 'h3'], activity_body: ['example_body', 'body'], activity_step: ['activity_body', 'example_step', 'example_body', 'body'],
    exercise_head: ['example_head', 'h3'], exercise_instruction: ['exercise_body', 'body'], exercise_body: ['body'],
    question: ['exercise_body', 'body'], options: ['question', 'exercise_body', 'body'], answer_line: [] };
  var byName = {}, all = doc.allParagraphStyles;
  for (i = 0; i < all.length; i++) if (!byName[all[i].name]) byName[all[i].name] = all[i];
  var cAll = doc.allCharacterStyles, cByName = {};
  for (i = 0; i < cAll.length; i++) if (!cByName[cAll[i].name]) cByName[cAll[i].name] = cAll[i];
  function styleFor(role) {
    var tried = [role].concat(FB[role] || []);
    for (var q = 0; q < tried.length; q++) if (MAP[tried[q]] && byName[MAP[tried[q]]]) {
      if (q > 0) FALLBACK[role] = tried[q]; USED[role] = MAP[tried[q]]; return byName[MAP[tried[q]]]; }
    FALLBACK[role] = '[Basic Paragraph]'; return doc.paragraphStyles.itemByName('[Basic Paragraph]');
  }
  function has(role) { return MAP[role] && byName[MAP[role]]; }
  function cstyle(role) { return MAP[role] && cByName[MAP[role]] ? cByName[MAP[role]] : null; }

  // ---------------------------------------------------------------- pages and frames that follow the document's own margins and columns
  var master = MAP._master ? doc.masterSpreads.itemByName(MAP._master) : doc.pages[-1].appliedMaster;
  if (MAP._master && !master.isValid) master = doc.pages[-1].appliedMaster;
  function newPage() {
    var pg = doc.pages.add(LocationOptions.AT_END); try { pg.appliedMaster = master; } catch (e) {}
    // page rulers are on, so this page runs from 0,0 (page.bounds would still report spread coordinates)
    var b = [0, 0, doc.documentPreferences.pageHeight, doc.documentPreferences.pageWidth], mp = pg.marginPreferences, left = pg.side == PageSideOptions.LEFT_HAND;
    var x0 = b[1] + (left ? mp.right : mp.left), x1 = b[3] - (left ? mp.left : mp.right);
    var f = pg.textFrames.add({ geometricBounds: [b[0] + mp.top, x0, b[2] - mp.bottom, x1] });
    try { f.textFramePreferences.textColumnCount = mp.columnCount; f.textFramePreferences.textColumnGutter = mp.columnGutter; } catch (e) {}
    return f;
  }
  var firstPageIndex = doc.pages.length, fr = newPage(), story = fr.parentStory, last = fr, guard = 0;
  var COLW = (function () { var g = fr.geometricBounds, n = fr.textFramePreferences.textColumnCount || 1;
    return ((g[3] - g[1]) - (n - 1) * (fr.textFramePreferences.textColumnGutter || 0)) / n; })();
  var FH = fr.geometricBounds[2] - fr.geometricBounds[0];
  function flow() { doc.recompose(); while (last.overflows && guard < 400) { var nf = newPage(); last.nextTextFrame = nf; last = nf; guard++; doc.recompose(); } }

  // ---------------------------------------------------------------- inserting text
  var BOXES = [], PENDING = [];
  function placeImage(r, f) {
    try { r.frameFittingOptions.fittingOnEmptyFrame = EmptyFrameFittingOptions.PROPORTIONALLY; r.frameFittingOptions.fittingAlignment = AnchorPoint.CENTER_ANCHOR; } catch (fe) {}
    try { r.place(f); r.fit(FitOptions.PROPORTIONALLY); r.fit(FitOptions.CENTER_CONTENT); return true; } catch (e) { return false; }
  }
  function add(text, role) {
    var s0 = story.characters.length; story.insertionPoints[-1].contents = text + '\r';
    var t = story.characters.itemByRange(s0, story.characters.length - 1).texts[0];
    t.appliedParagraphStyle = styleFor(role); try { t.clearOverrides(OverrideType.ALL); } catch (e) {}
    return s0;
  }
  function para(s0) { return story.characters[s0].paragraphs[0]; }
  function labelled(label, text, role, csRole) {
    var s0 = add(label + ' ' + text, role), cs = cstyle(csRole);
    try { var r = story.characters.itemByRange(s0, s0 + label.length - 1); if (cs) r.appliedCharacterStyle = cs; else r.fontStyle = 'Bold'; } catch (e) {}
    return s0;
  }
  function figure(b, maxW) {
    var w = Math.min(b.mm[0], maxW), h = b.mm[1] * w / b.mm[0]; if (h > FH * 0.45) { w = w * FH * 0.45 / h; h = FH * 0.45; }
    var s0 = add('', 'figure'); try { para(s0).justification = Justification.CENTER_ALIGN; } catch (e) {}
    flow(); var r = story.insertionPoints[s0].rectangles.add({ geometricBounds: [0, 0, h, w], strokeWeight: 0 }); flow();
    // a picture can land in a frame that is not threaded yet: re-flow and try once more
    // placing can fail while the layout is still moving; such pictures are placed again once everything has settled
    if (!placeImage(r, File(BASE + '/' + b.src))) PENDING.push([r, File(BASE + '/' + b.src)]);
    try { para(s0).leading = h * 2.8346 + 2; para(s0).keepWithNext = b.caption ? 2 : 0; } catch (e) {}
    if (b.caption) add(b.caption, 'caption');
    return s0;
  }
  function table(b) {
    var rows = b.rows, nc = 0, r; for (r = 0; r < rows.length; r++) nc = Math.max(nc, rows[r].length);
    var lines = []; for (r = 0; r < rows.length; r++) { var row = rows[r].slice(0); while (row.length < nc) row.push(''); lines.push(row.join('\t')); }
    var s0 = story.characters.length; story.insertionPoints[-1].contents = lines.join('\r') + '\r';
    var t = story.characters.itemByRange(s0, story.characters.length - 2).texts[0]; t.appliedParagraphStyle = styleFor('table_body'); flow();
    t.convertToTable('\t', '\r'); var tb = story.tables[-1]; para(s0).appliedParagraphStyle = styleFor('table'); flow();
    // a table style from the designer wins; otherwise column widths follow content
    var wts = [], tot = 0, c; for (c = 0; c < nc; c++) { var mx = 4; for (r = 0; r < rows.length; r++) mx = Math.max(mx, Math.min(40, (rows[r][c] || '').length)); wts.push(mx); tot += mx; }
    for (c = 0; c < nc; c++) try { tb.columns[c].width = COLW * wts[c] / tot; } catch (e) {}
    if (MAP.table_style) try { tb.appliedTableStyle = doc.tableStyles.itemByName(MAP.table_style); } catch (e) {}
    if (b.header) { try { tb.rows[0].rowType = RowTypes.HEADER_ROW; } catch (e) {}
      var hc = tb.rows[0].cells.everyItem().getElements(); for (c = 0; c < hc.length; c++) hc[c].texts[0].appliedParagraphStyle = styleFor('table_head'); }
    for (r = 0; r < tb.rows.length - 1; r++) try { tb.rows[r].keepWithNextRow = true; } catch (e) {}
    flow(); return s0;
  }

  // ---------------------------------------------------------------- the content
  var CHW = MAP._chapter_word || '';
  if (!CHW && has('chapter_label')) { var stz = doc.stories.everyItem().getElements();
    for (var z = 0; z < stz.length && !CHW; z++) { var pz0 = stz[z].paragraphs.everyItem().getElements();
      for (var z2 = 0; z2 < pz0.length; z2++) if (pz0[z2].appliedParagraphStyle.name == MAP.chapter_label) {
        var w0 = pz0[z2].contents.replace(/[\s\d:.\-]+$/, '').replace(/^\s+/, ''); if (w0) { CHW = w0; LOG.push('chapter label learned from sample: ' + w0); } break; } } }
  CHW = CHW || 'Chapter';
  if (M.chapter_title) {
    if (has('chapter_label') && M.chapter_no) add(CHW + ' ' + M.chapter_no, 'chapter_label');
    add(has('chapter_label') || !M.chapter_no ? M.chapter_title : CHW + ' ' + M.chapter_no + ': ' + M.chapter_title, 'chapter_title');
  }
  if (M.objectives && M.objectives.length) {
    var os = add(M.objectives_intro || 'In this chapter you will learn:', 'objectives_head');
    for (k = 0; k < M.objectives.length; k++) add((has('objective') || has('list') ? '' : String.fromCharCode(8226) + ' ') + M.objectives[k], 'objective');
    BOXES.push({ kind: 'Objectives', s: os, e: story.characters.length - 1 });
  }
  var bullet = function (role) { return has(role) ? '' : String.fromCharCode(8226) + '\t'; };
  for (var bi = 0; bi < BL.length; bi++) {
    var b = BL[bi], s0;
    if (b.type == 'h2') add(b.text, 'h2');
    else if (b.type == 'h3') add(b.text, 'h3');
    else if (b.type == 'body') { s0 = add(b.text, 'body'); if (b.lead_in) para(s0).keepWithNext = 2; }
    else if (b.type == 'list') for (k = 0; k < b.items.length; k++) { s0 = add(bullet('list') + b.items[k], 'list'); if (k < b.items.length - 1) para(s0).keepWithNext = 1; }
    else if (b.type == 'figure') { s0 = figure(b, COLW * 0.85); BOXES.push({ kind: 'Figure', s: s0, e: story.characters.length - 1 }); }
    else if (b.type == 'table') { s0 = table(b); BOXES.push({ kind: 'Table', s: s0, e: story.characters.length - 1 }); }
    else if (b.type == 'note') { s0 = labelled(b.label, b.text, 'note', 'note_label'); BOXES.push({ kind: 'Note', s: s0, e: story.characters.length - 1 }); }
    else if (b.type == 'example') {
      var act = b.kind == 'activity', P = act ? 'activity_' : 'example_', xs = story.characters.length;
      add(b.title ? b.label + ': ' + b.title : b.label, P + 'head');
      for (k = 0; k < b.items.length; k++) { var it = b.items[k];
        if (it.type == 'step') labelled(it.label + ':', it.text, P + 'step', 'step_label');
        else if (it.type == 'figure') figure(it, COLW * 0.6);
        else if (it.type == 'list') for (var li = 0; li < it.items.length; li++) add(bullet('list') + it.items[li], P + 'body');
        else add(it.text, P + 'body'); }
      BOXES.push({ kind: act ? 'Activity' : 'Example', s: xs, e: story.characters.length - 1 });
    }
    else if (b.type == 'exercise') {
      var es = story.characters.length, grp = [];
      add(b.label + (b.title ? ': ' + b.title : ''), 'exercise_head');
      for (k = 0; k < b.items.length; k++) {
        var q = b.items[k];
        if (q.type == 'instruction') { s0 = add(q.text, 'exercise_instruction'); para(s0).keepWithNext = 2; continue; }
        var qs = add((q.n ? q.n + '.' : String.fromCharCode(8226)) + '\t' + q.text, 'question'), lastP = qs;
        if (cstyle('question_number') && q.n) try { story.characters.itemByRange(qs, qs + q.n.length).appliedCharacterStyle = cstyle('question_number'); } catch (e) {}
        if (q.options && q.options.length) {
          para(qs).keepWithNext = 2;
          // options on tab columns: 4, then 2, then 1, measured on the designer's own type
          var tries = [Math.min(4, q.options.length), 2, 1];
          for (var ti = 0; ti < tries.length; ti++) {
            var cols = tries[ti]; if (ti > 0 && cols >= tries[ti - 1]) continue;
            var starts = [], fits = true, oi;
            for (oi = 0; oi < q.options.length; oi += cols) {
              var cells = []; for (var j = oi; j < Math.min(oi + cols, q.options.length); j++) cells.push('(' + String.fromCharCode(97 + j) + ') ' + q.options[j]);
              lastP = add('\t' + cells.join('\t'), 'options'); starts.push(lastP);
              var pp = para(lastP), ind = 0; try { ind = pp.leftIndent; } catch (e) {}
              var tl = []; for (var c2 = 0; c2 < cols; c2++) tl.push({ alignment: TabStopAlignment.LEFT_ALIGN, position: ind + 7 + (COLW - ind - 9) * c2 / cols });
              try { pp.tabList = tl; } catch (e) {} pp.keepWithNext = 2;
            }
            if (cols == 1) break;
            flow();
            for (oi = 0; oi < starts.length && fits; oi++) if (para(starts[oi]).lines.length > 1) fits = false;
            if (fits) break;
            story.characters.itemByRange(starts[0], story.characters.length - 1).remove(); lastP = qs;
          }
        }
        var nl = { lines1: 1, lines2: 2, lines3: 3 }[q.answer] || 0;
        for (var al = 0; al < nl; al++) { para(lastP).keepWithNext = 2;
          lastP = has('answer_line') ? add(String.fromCharCode(160), 'answer_line') : add('\t____________________________________________', 'question'); }
        try { para(lastP).keepWithNext = 0; } catch (e) {}
        grp.push([qs, lastP]);
      }
      BOXES.push({ kind: 'Exercise', s: es, e: story.characters.length - 1, groups: grp });
    }
  }
  try { if (story.characters[-1].contents == '\r') story.characters[-1].remove(); } catch (e) {}
  flow();

  // ---------------------------------------------------------------- keep rules: a box never splits; long exercises break only between questions
  function range(bx) { var out = [], p = para(bx.s); while (p.isValid) { out.push(p); var nx = p.index + p.characters.length; if (nx > bx.e || nx >= story.characters.length) break; p = story.characters[nx].paragraphs[0]; } return out; }
  function fid(p) { try { return p.parentTextFrames[0].id; } catch (e) { return -1; } }
  for (k = 0; k < BOXES.length; k++) { var ps = BOXES[k].paras = range(BOXES[k]);
    for (i = 0; i < ps.length; i++) try { ps[i].keepLinesTogether = true; ps[i].keepAllLinesTogether = true; if (i < ps.length - 1) ps[i].keepWithNext = 5; } catch (e) {} }
  flow();
  for (k = 0; k < BOXES.length; k++) {
    var bx = BOXES[k], pz = bx.paras; if (bx.kind != 'Exercise' || fid(pz[0]) == fid(pz[pz.length - 1])) continue;
    for (i = 0; i < pz.length; i++) try { pz[i].keepWithNext = 0; } catch (e) {}
    var fq = bx.groups.length ? bx.groups[0][1] : bx.s;
    for (i = 0; i < pz.length - 1; i++) { if (pz[i].index <= fq) pz[i].keepWithNext = 5;
      for (var g = 0; g < bx.groups.length; g++) if (pz[i].index >= bx.groups[g][0] && pz[i].index < bx.groups[g][1]) pz[i].keepWithNext = 5; }
    bx.continues = true;
  }
  flow();
  // stranded headings move to the next frame
  var HEADR = ['h2', 'h3', 'chapter_title', 'example_head', 'activity_head', 'exercise_head', 'objectives_head'], HN = {};
  for (k = 0; k < HEADR.length; k++) if (MAP[HEADR[k]]) HN[MAP[HEADR[k]]] = 1;
  for (var pass = 0; pass < 3; pass++) {
    var moved = 0, TFs = story.textContainers;
    for (i = 0; i < TFs.length - 1; i++) try {
      var lp = TFs[i].paragraphs[-1]; if (!TFs[i + 1].characters.length || lp.parentTextFrames.length > 1) continue;
      if (HN[lp.appliedParagraphStyle.name] && lp.startParagraph != StartParagraph.NEXT_FRAME) { lp.startParagraph = StartParagraph.NEXT_FRAME; moved++; LOG.push('moved stranded heading: ' + lp.contents.substr(0, 40)); }
    } catch (e) {}
    flow(); if (!moved) break;
  }
  while (last.characters.length == 0 && last.previousTextFrame) { var pg = last.parentPage, pv = last.previousTextFrame; last.remove(); pg.remove(); last = pv; doc.recompose(); }

  // ---------------------------------------------------------------- remember what was built, for QA and the next chapter
  var bo = []; for (k = 0; k < BOXES.length; k++) bo.push('{"kind":"' + BOXES[k].kind + '","s":' + BOXES[k].s + ',"e":' + BOXES[k].e + ',"continues":' + (BOXES[k].continues ? 'true' : 'false') + '}');
  story.insertLabel('galley_boxes', '[' + bo.join(',') + ']');
  doc.insertLabel('galley_map', arg('galley_map', '{}'));
  doc.viewPreferences.horizontalMeasurementUnits = VH; doc.viewPreferences.verticalMeasurementUnits = VV; doc.viewPreferences.rulerOrigin = RO;
  doc.recompose();
  for (k = 0; k < PENDING.length; k++) if (!placeImage(PENDING[k][0], PENDING[k][1])) LOG.push('image ' + PENDING[k][1].name + ': could not be placed, frame left empty');
  try { app.activeWindow.activePage = doc.pages[firstPageIndex]; } catch (e) {}
  var usedArr = [], fbArr = [];
  for (k in USED) usedArr.push('"' + k + '":"' + String(USED[k]).replace(/"/g, '\\"') + '"');
  for (k in FALLBACK) fbArr.push('"' + k + '":"' + String(FALLBACK[k]).replace(/"/g, '\\"') + '"');
  var lg = []; for (k = 0; k < LOG.length; k++) lg.push('"' + LOG[k].replace(/\\/g, '/').replace(/"/g, "'") + '"');
  var rep = '{"ok":true,"firstPage":"' + doc.pages[firstPageIndex].name + '","lastPage":"' + doc.pages[-1].name + '","pagesAdded":' + (doc.pages.length - firstPageIndex) +
    ',"overset":' + story.overflows + ',"used":{' + usedArr.join(',') + '},"fallbacks":{' + fbArr.join(',') + '},"log":[' + lg.join(',') + ']}';
  var rf = File(arg('galley_report', Folder.temp + '/galley_flow_report.json')); rf.encoding = 'UTF-8'; rf.open('w'); rf.write(rep); rf.close();
  app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;
})();
