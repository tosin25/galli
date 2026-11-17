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
  doc.viewPreferences.horizontalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  doc.viewPreferences.verticalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  doc.recompose();
  var PW = doc.documentPreferences.pageWidth, PH = doc.documentPreferences.pageHeight, BL = doc.documentPreferences.documentBleedTopOffset;
  var errors = [], warns = [], checks = { overset: 0, split_boxes: 0, stranded_headings: 0, off_page: 0, links: 0, empty_pages: 0 };
  function pgName(o) { try { return o.parentPage ? o.parentPage.name : '?'; } catch (e) { return '?'; } }
  function E(check, page, msg) { errors.push({ check: check, page: String(page), msg: msg }); checks[check] = (checks[check] || 0) + 1; }
  function Wn(check, page, msg) { warns.push({ check: check, page: String(page), msg: msg }); }
  function esc(s) { return String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/[\r\n\t]/g, ' '); }
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

  // 2. boxes split across frames (box ranges come from the build; otherwise found from style names)
  var boxes = [];
  try { boxes = eval('(' + doc.extractLabel('galley_boxes') + ')') || []; } catch (e) { boxes = []; }
  for (i = 0; i < boxes.length && main; i++) {
    var bx = boxes[i];
    try {
      var p0 = main.characters[bx.s].paragraphs[0], p1 = main.characters[Math.max(bx.s, bx.e - 1)].paragraphs[0];
      var f0 = frameOf(p0), f1 = frameOf(p1);
      if (bx.kind == 'Table') { var tb = main.characters[bx.s].tables.length ? main.characters[bx.s].tables[0] : null;
        if (tb) { f0 = tb.cells[0].insertionPoints[0].parentTextFrames[0]; f1 = tb.cells[-1].insertionPoints[0].parentTextFrames[0]; } }
      if (f0 && f1 && f0.id != f1.id) {
        if (bx.continues) Wn('split_boxes', f0.parentPage.name, bx.kind + ' continues onto page ' + f1.parentPage.name + ' (longer than a page; breaks only between questions)');
        else E('split_boxes', f0.parentPage.name, bx.kind + ' box split across pages ' + f0.parentPage.name + '-' + f1.parentPage.name + ': ' + clip(p0.contents));
      }
    } catch (e) { Wn('split_boxes', '?', 'could not check box ' + bx.kind + ': ' + e.message); }
  }
  // 3. stranded headings: a heading style that is the last paragraph of a frame while the story continues
  var HEADS = /^(H2|H3|Example Head|Activity Head|Exercise Head|Objectives Head|Chapter Title)$/;
  if (main) {
    var tc = main.textContainers;
    for (i = 0; i < tc.length - 1; i++) {
      try { var lp = tc[i].paragraphs[-1]; if (!tc[i + 1].characters.length || lp.parentTextFrames.length > 1) continue;
        if (HEADS.test(lp.appliedParagraphStyle.name)) E('stranded_headings', tc[i].parentPage.name, 'heading at the foot of the page: ' + clip(lp.contents)); } catch (e) {}
    }
  }
  // 4. objects off the page: outside the bleed = error; content (text, anchored art) outside the margins = warning
  function inspect(items, page, isMaster) {
    var mp = page.marginPreferences, side = page.side == PageSideOptions.LEFT_HAND;
    var mL = side ? mp.right : mp.left, mR = side ? mp.left : mp.right; // facing pages: left/right = inside/outside
    for (var j = 0; j < items.length; j++) {
      var it = items[j], gb;
      try { gb = it.visibleBounds; } catch (e) { continue; }
      var out = gb[0] < -BL - 0.5 || gb[1] < -BL - 0.5 || gb[2] > PH + BL + 0.5 || gb[3] > PW + BL + 0.5;
      var label = it.constructor.name + (it.hasOwnProperty('contents') && typeof it.contents == 'string' && it.contents ? ' "' + clip(it.contents) + '"' : '');
      var hasContent = (it.hasOwnProperty('contents') && typeof it.contents == 'string' && it.contents != '') || (it.hasOwnProperty('allGraphics') && it.allGraphics.length > 0);
      var offTrim = gb[0] < -0.5 || gb[1] < -0.5 || gb[2] > PH + 0.5 || gb[3] > PW + 0.5;
      var gone = gb[2] < -BL || gb[0] > PH + BL || gb[3] < -BL || gb[1] > PW + BL;
      if (gone) E('off_page', (isMaster ? 'master ' : '') + page.name, label + ' lies completely off the page');
      else if (hasContent && offTrim && !(it instanceof TextFrame && it.contents == '')) E('off_page', (isMaster ? 'master ' : '') + page.name, label + ' is cut by the trim edge');
      else if (out) Wn('off_page', (isMaster ? 'master ' : '') + page.name, label + ' (decoration) extends beyond the bleed');
      else if (!isMaster && it.parent instanceof Character) {
        if (gb[1] < mL - 1 || gb[3] > PW - mR + 1) Wn('off_page', page.name, 'anchored ' + label + ' sticks out of the text column');
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
  app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;
})();
