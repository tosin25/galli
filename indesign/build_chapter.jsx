// Galley: build one InDesign chapter from content.json + a style spec (style/*.json).
// Everything that belongs to the text lives in ONE threaded story: headings, boxes and exercises are paragraph
// styles (shading / borders / rules), figures and icons are inline anchored objects, tables are real tables.
// Only page furniture (masters) and decorative spot art (layer "Illustrations") sit outside the story.
//
// Arguments (app.scriptArgs): galley_content, galley_style, galley_art, galley_out
#target indesign
(function () {
  var SA = app.scriptArgs;
  function arg(k, d) { return SA.isDefined(k) && SA.getValue(k) != '' ? SA.getValue(k) : d; }
  var here = File($.fileName).parent.parent;
  var CONTENT = File(arg('galley_content', here + '/work/content.json'));
  var STYLEF = File(arg('galley_style', here + '/style/bright.json'));
  var ART = Folder(arg('galley_art', here + '/art'));
  var OUT = Folder(arg('galley_out', here + '/out/test')); if (!OUT.exists) OUT.create();
  function readJSON(f) { f.encoding = 'UTF-8'; f.open('r'); var s = f.read(); f.close(); return eval('(' + s + ')'); }
  var D = readJSON(CONTENT), S = readJSON(STYLEF), M = D.meta, BL = D.blocks, BASE = CONTENT.parent;
  $.evalFile(File(here + '/indesign/house.jsx')); // GalleyHouse: shared house rules
  var LOG = [], i, k;
  app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;

  // ---------------------------------------------------------------- geometry (mm) and type (pt)
  var PW = S.trim.width, PH = S.trim.height, BLEED = S.bleed || 3;
  var MT = S.margins.top, MB = S.margins.bottom, MI = S.margins.inside, MO = S.margins.outside;
  var FW = PW - MI - MO, FH = PH - MT - MB, T = S.type;
  var FH_ = S.fonts.heading, FB_ = S.fonts.body;

  var doc = app.documents.add();
  doc.viewPreferences.horizontalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  doc.viewPreferences.verticalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  doc.viewPreferences.rulerOrigin = RulerOrigin.PAGE_ORIGIN;
  with (doc.documentPreferences) { pageWidth = PW; pageHeight = PH; facingPages = true;
    documentBleedTopOffset = BLEED; documentBleedUniformSize = true; }
  var MARG = { top: MT, bottom: MB, left: MI, right: MO };
  doc.marginPreferences.properties = MARG;
  doc.textDefaults.hyphenation = false;

  // ---------------------------------------------------------------- colours
  function rgb(h) { return [parseInt(h.substr(1, 2), 16), parseInt(h.substr(3, 2), 16), parseInt(h.substr(5, 2), 16)]; }
  var PAPER = doc.swatches.itemByName('Paper'), SW = {};
  for (k in S.palette) {
    if (k == 'paper') { SW[k] = PAPER; continue; }
    var nm = 'Galley ' + k.replace(/_/g, ' ');
    var c = doc.colors.itemByName(nm);
    SW[k] = c.isValid ? c : doc.colors.add({ name: nm, model: ColorModel.PROCESS, space: ColorSpace.RGB, colorValue: rgb(S.palette[k]) });
  }
  function C(key) { return SW[key] || SW.ink; }

  // ---------------------------------------------------------------- styles
  function set(o, props) { for (var p in props) { try { o[p] = props[p]; } catch (e) { LOG.push('set ' + p + ': ' + e.message); } } return o; }
  function merge(a, b) { var o = {}, p; for (p in a) o[p] = a[p]; for (p in b) o[p] = b[p]; return o; }
  function PS(name, props) { var s = doc.paragraphStyles.itemByName(name); if (!s.isValid) s = doc.paragraphStyles.add({ name: name }); return set(s, props); }
  function CS(name, props) { var s = doc.characterStyles.itemByName(name); if (!s.isValid) s = doc.characterStyles.add({ name: name }); return set(s, props); }
  var HF = { appliedFont: FH_.family }, BF = { appliedFont: FB_.family };
  var csBold = CS('Bold', { fontStyle: FB_.bold });
  var csBullet = CS('Bullet', { fillColor: C(S.list.bullet_color), fontStyle: FB_.bold });

  var body = PS('Body', merge(BF, { fontStyle: FB_.regular, pointSize: T.body, leading: T.leading, tracking: T.tracking || 0, fillColor: C('ink'), spaceAfter: 2.4,
    keepFirstLines: 2, keepLastLines: 2, hyphenation: false, justification: Justification.LEFT_ALIGN }));
  function S2(name, base, extra) { return PS(name, merge({ basedOn: base }, extra)); }

  function shading(color, opts) {
    opts = opts || {};
    var o = { paragraphShadingOn: true, paragraphShadingColor: color, paragraphShadingTint: 100,
      paragraphShadingWidth: opts.text ? ParagraphShadingWidthEnum.TEXT_WIDTH : ParagraphShadingWidthEnum.COLUMN_WIDTH,
      paragraphShadingTopOrigin: ParagraphShadingTopOriginEnum.ASCENT_TOP_ORIGIN,
      paragraphShadingBottomOrigin: ParagraphShadingBottomOriginEnum.DESCENT_BOTTOM_ORIGIN,
      paragraphShadingTopOffset: opts.top == undefined ? 2 : opts.top, paragraphShadingBottomOffset: opts.bottom == undefined ? 2 : opts.bottom,
      paragraphShadingLeftOffset: opts.l || 0, paragraphShadingRightOffset: opts.r || 0, mergeConsecutiveParaBorders: true };
    if (opts.radius) {
      var cs = ['TopLeft', 'TopRight', 'BottomLeft', 'BottomRight'];
      for (var q = 0; q < cs.length; q++) { o['paragraphShading' + cs[q] + 'CornerOption'] = CornerOptions.ROUNDED_CORNER; o['paragraphShading' + cs[q] + 'CornerRadius'] = opts.radius; }
    }
    return o;
  }
  function border(color, w, opts) {
    opts = opts || {};
    var o = { paragraphBorderOn: true, paragraphBorderColor: color,
      paragraphBorderTopLineWeight: w.t, paragraphBorderBottomLineWeight: w.b, paragraphBorderLeftLineWeight: w.l, paragraphBorderRightLineWeight: w.r,
      paragraphBorderTopOffset: opts.top == undefined ? 2.5 : opts.top, paragraphBorderBottomOffset: opts.bottom == undefined ? 2.5 : opts.bottom,
      paragraphBorderLeftOffset: 0, paragraphBorderRightOffset: 0, mergeConsecutiveParaBorders: true, paragraphBorderDisplayIfSplits: true,
      paragraphBorderTopOrigin: ParagraphBorderTopOriginEnum.ASCENT_TOP_ORIGIN, paragraphBorderBottomOrigin: ParagraphBorderBottomOriginEnum.DESCENT_BOTTOM_ORIGIN };
    try { o.paragraphBorderWidth = ParagraphBorderEnum.COLUMN_WIDTH; } catch (e) {}
    return o;
  }

  // headings
  var st = {};
  var h2 = S.h2, h2c = C(h2.color);
  var h2base = merge(HF, { fontStyle: FH_.bold, pointSize: T.h2, leading: T.h2 * 1.25, fillColor: C(h2.text || h2.color),
    spaceBefore: 8, spaceAfter: 4, keepWithNext: 3, keepLinesTogether: true, keepAllLinesTogether: true });
  if (h2.treatment == 'band') st.h2 = S2('H2', body, merge(h2base, merge({ leftIndent: 4, rightIndent: 4, spaceBefore: 9, spaceAfter: 5 }, shading(h2c, { top: 2.2, bottom: 2.2, radius: 2.5 }))));
  else if (h2.treatment == 'rule') st.h2 = S2('H2', body, merge(h2base, { spaceBefore: 10, spaceAfter: 5, ruleBelow: true, ruleBelowColor: h2c, ruleBelowLineWeight: 0.75, ruleBelowOffset: 2.2, ruleBelowWidth: RuleWidth.COLUMN_WIDTH }));
  else st.h2 = S2('H2', body, merge(h2base, { fontStyle: FH_.semibold, spaceBefore: 12, spaceAfter: 4, ruleAbove: true, ruleAboveColor: h2c, ruleAboveLineWeight: 4,
    ruleAboveOffset: T.h2 * 0.353 + 3, ruleAboveWidth: RuleWidth.COLUMN_WIDTH, ruleAboveRightIndent: FW - 14 }));
  st.h3 = S2('H3', body, merge(HF, { fontStyle: FH_.semibold, pointSize: T.h3, leading: T.h3 * 1.3, fillColor: C(S.h3.color), spaceBefore: 4, spaceAfter: 2, keepWithNext: 3, keepLinesTogether: true }));
  st.list = S2('List', body, { leftIndent: 6, firstLineIndent: -6, spaceAfter: 1.4, bulletsAndNumberingListType: ListType.BULLET_LIST, bulletsTextAfter: '^t', bulletsCharacterStyle: csBullet });
  try { st.list.bulletChar.characterValue = 8226; } catch (e) {}
  st.numlist = S2('Numbered List', body, { spaceAfter: 1.4 });
  st.calc = S2('Calculation', body, { leftIndent: (S.math && S.math.indent) || 10, spaceAfter: 0.8, keepLinesTogether: true });
  st.figure = S2('Figure', body, { justification: Justification.CENTER_ALIGN, spaceBefore: 2, spaceAfter: 1.5, leading: Leading.AUTO, keepWithNext: 2 });
  st.caption = S2('Caption', body, { pointSize: T.caption, leading: T.caption * 1.35, fontStyle: FB_.italic, justification: Justification.CENTER_ALIGN, fillColor: C('ink'), spaceAfter: 4 });
  st.table = S2('Table Anchor', body, { spaceBefore: 1.5, spaceAfter: 4, leading: Leading.AUTO });
  st.th = S2('Table Head', body, merge(HF, { fontStyle: FH_.semibold, pointSize: T.small + 0.5, leading: (T.small + 0.5) * 1.3, fillColor: C(S.table.head_text), spaceAfter: 0 }));
  st.td = S2('Table Body', body, { pointSize: T.small + 0.5, leading: (T.small + 0.5) * 1.35, spaceAfter: 0 });

  // boxes: one family of styles per box kind, built from the spec's treatment
  function boxStyles(prefix, cfg) {
    var col = C(cfg.color), fill = cfg.fill ? C(cfg.fill) : null, tr = cfg.treatment, r = cfg.radius || 0, L = 4, R = 4, deco = {};
    if (tr == 'shaded') deco = shading(fill, { radius: r });
    else if (tr == 'outlined') { deco = border(col, { t: 0.9, b: 0.9, l: 0.9, r: 0.9 }); if (fill) deco = merge(deco, shading(fill)); }
    else if (tr == 'sidebar') { deco = border(col, { t: 0, b: 0, l: 4, r: 0 }); L = 6; if (fill) deco = merge(deco, shading(fill, { l: 0 })); }
    else { L = 0; R = 0; } // open
    var b = S2(prefix + ' Body', body, merge({ leftIndent: L, rightIndent: R, spaceBefore: 1.6, spaceAfter: 0, keepLinesTogether: true, keepAllLinesTogether: true }, deco));
    var head, ht = { fontStyle: FH_.bold, pointSize: T.box_head, leading: T.box_head * 1.35, keepWithNext: 5, spaceBefore: 6, spaceAfter: 2 };
    if (cfg.head == 'pill') head = S2(prefix + ' Head', body, merge(merge(HF, ht), merge({ leftIndent: 3, fillColor: C(cfg.head_text || 'paper'), spaceAfter: 1.8 },
      shading(col, { text: true, l: 3, r: 4, top: 1.6, bottom: 1.4, radius: 2.2 }))));
    else if (cfg.head == 'band') head = S2(prefix + ' Head', body, merge(merge(HF, ht), merge({ leftIndent: 4, fillColor: C(cfg.head_text || 'paper'), spaceAfter: 2.9 },
      shading(col, { top: 2, bottom: 2 }))));
    else if (cfg.head == 'ruled') head = S2(prefix + ' Head', body, merge(merge(HF, ht), { fillColor: col, tracking: 40, spaceBefore: 8, spaceAfter: 3,
      ruleAbove: true, ruleAboveColor: col, ruleAboveLineWeight: 1.5, ruleAboveOffset: T.box_head * 0.353 + 2, ruleAboveWidth: RuleWidth.COLUMN_WIDTH }));
    else head = S2(prefix + ' Head', b, merge(merge(HF, ht), { fillColor: col, spaceBefore: 6, spaceAfter: 0 })); // label: inside the box
    var step = S2(prefix + ' Step', b, {});
    var listS = S2(prefix + ' List', b, { leftIndent: L + 6, firstLineIndent: -6, bulletsAndNumberingListType: ListType.BULLET_LIST, bulletsTextAfter: '^t', bulletsCharacterStyle: csBullet });
    try { listS.bulletChar.characterValue = 8226; } catch (e) {}
    var fig = S2(prefix + ' Figure', b, { justification: Justification.CENTER_ALIGN, leading: Leading.AUTO });
    var cap = S2(prefix + ' Caption', b, { pointSize: T.caption, leading: T.caption * 1.35, fontStyle: FB_.italic, justification: Justification.CENTER_ALIGN });
    var labelCS = CS(prefix + ' Label', { fontStyle: FB_.bold, fillColor: C(cfg.label_color || cfg.color) });
    return { kind: prefix, cfg: cfg, body: b, head: head, step: step, list: listS, fig: fig, cap: cap, label: labelCS, L: L, R: R, col: col };
  }
  var BX = { example: boxStyles('Example', S.example), activity: boxStyles('Activity', S.activity || S.example), exercise: boxStyles('Exercise', S.exercise) };
  var EX = BX.exercise;
  st.question = S2('Exercise Question', EX.body, { leftIndent: EX.L + 7, firstLineIndent: -7, spaceBefore: 0, spaceAfter: 1.8, keepLinesTogether: true });
  st.options = S2('Exercise Options', EX.body, { leftIndent: EX.L + 7, spaceBefore: 0, spaceAfter: 2.6, keepLinesTogether: true });
  st.answer = S2('Exercise Answer Line', EX.body, { leftIndent: EX.L + 7, rightIndent: EX.R + 2, spaceBefore: 3.5, spaceAfter: 0,
    ruleBelow: true, ruleBelowColor: C(S.exercise.answer_lines || 'line'), ruleBelowLineWeight: 0.6, ruleBelowWidth: RuleWidth.COLUMN_WIDTH,
    ruleBelowLeftIndent: 0, ruleBelowRightIndent: 0, ruleBelowOffset: 1.2 });
  var csNum = CS('Question Number', { fontStyle: FB_.bold, fillColor: EX.col });
  // note
  var N = S.note, ncol = C(N.label_color);
  var nDeco = N.treatment == 'sidebar' ? merge(border(ncol, { t: 0, b: 0, l: 3, r: 0 }), shading(C(N.fill))) : shading(C(N.fill), { radius: N.radius, top: 2.6, bottom: 2.6 });
  st.note = S2('Note', body, merge({ leftIndent: N.icon ? 13 : 5, rightIndent: 4, spaceBefore: 3, spaceAfter: 5, pointSize: T.body - 0.5, leading: T.leading - 0.5,
    keepLinesTogether: true, keepAllLinesTogether: true }, nDeco));
  var csNote = CS('Note Label', merge(HF, { fontStyle: FH_.bold, fillColor: ncol }));
  // opener
  var O = S.opener, ocol = C(O.color), OH = O.height;
  var onLight = O.layout == 'minimal';
  st.chLabel = S2('Chapter Label', body, merge(HF, { fontStyle: FH_.semibold, pointSize: T.opener_number, leading: T.opener_number * 1.15, tracking: 180,
    fillColor: onLight ? C('secondary') : PAPER, spaceAfter: 2, keepWithNext: 2 }));
  st.chTitle = S2('Chapter Title', body, merge(HF, { fontStyle: FH_.bold, pointSize: T.opener_title, leading: T.opener_title * 1.08, fillColor: onLight ? ocol : PAPER, spaceAfter: 0, keepLinesTogether: true }));
  if (O.layout == 'minimal') {
    set(st.chLabel, { justification: Justification.CENTER_ALIGN, ruleAbove: true, ruleAboveColor: C('accent'), ruleAboveLineWeight: 1, ruleAboveOffset: 8,
      ruleAboveWidth: RuleWidth.COLUMN_WIDTH, ruleAboveLeftIndent: FW / 2 - 12, ruleAboveRightIndent: FW / 2 - 12 });
    set(st.chTitle, { justification: Justification.CENTER_ALIGN, ruleBelow: true, ruleBelowColor: ocol, ruleBelowLineWeight: 0.75, ruleBelowOffset: 7,
      ruleBelowWidth: RuleWidth.COLUMN_WIDTH, ruleBelowLeftIndent: FW / 2 - 30, ruleBelowRightIndent: FW / 2 - 30 });
  }
  if (O.layout == 'band') set(st.chLabel, { fontStyle: FH_.bold, tracking: -20, fillColor: C('accent'), leading: T.opener_number * 0.95, spaceAfter: 1 });
  var OB = O.objectives || {}, ofill = C(OB.fill || 'secondary_tint');
  st.objHead = S2('Objectives Head', body, merge(merge(HF, shading(ofill, { top: 3, bottom: 2 })), { fontStyle: FH_.bold, fillColor: C(OB.head || 'secondary'), leftIndent: 5, rightIndent: 5, spaceAfter: 0, keepWithNext: 5 }));
  st.objItem = S2('Objective', body, merge(shading(ofill, { top: 2, bottom: 3 }), { leftIndent: 11, firstLineIndent: -6, rightIndent: 5, spaceAfter: 0.8,
    bulletsAndNumberingListType: ListType.BULLET_LIST, bulletsTextAfter: '^t', bulletsCharacterStyle: csBullet, keepWithNext: 5 }));
  try { st.objItem.bulletChar.characterValue = 8226; } catch (e) {}

  // ---------------------------------------------------------------- masters
  function frameBounds(pg, top) { var left = pg.side == PageSideOptions.LEFT_HAND; return [top || MT, left ? MO : MI, PH - MB, left ? PW - MI : PW - MO]; }
  var msA = doc.masterSpreads[0]; set(msA, { namePrefix: 'A', baseName: 'Body' });
  var msB = doc.masterSpreads.add(2, { namePrefix: 'B', baseName: 'Opener' });
  function tf(pg, gb, txt, props, vj) {
    var f = pg.textFrames.add({ geometricBounds: gb }); f.contents = txt; if (txt !== '') set(f.paragraphs[0], props);
    f.textFramePreferences.insetSpacing = [0, 0, 0, 0]; f.textFramePreferences.verticalJustification = vj || VerticalJustification.CENTER_ALIGN; return f;
  }
  var chapterLine = (M.chapter_no ? 'Chapter ' + M.chapter_no + '  ' + String.fromCharCode(8226) + '  ' : '') + M.chapter_title;
  function folio(mp, leftSide) {
    var F = S.folio, fc = C(F.color), y = PH - MB / 2, props = merge(HF, { fontStyle: FH_.bold, pointSize: T.folio, fillColor: C(F.text), justification: Justification.CENTER_ALIGN });
    var gb;
    if (F.shape == 'circle') { var cx = PW / 2; mp.ovals.add({ geometricBounds: [y - 5, cx - 5, y + 5, cx + 5], fillColor: fc, strokeWeight: 0 }); gb = [y - 5, cx - 6, y + 5, cx + 6]; }
    else if (F.shape == 'block') { gb = leftSide ? [PH - 17, -BLEED, PH - 7, 13] : [PH - 17, PW - 13, PH - 7, PW + BLEED];
      mp.rectangles.add({ geometricBounds: gb, fillColor: fc, strokeWeight: 0 }); gb = leftSide ? [gb[0], 0, gb[2], 13] : [gb[0], PW - 13, gb[2], PW]; }
    else { gb = leftSide ? [y - 3, MO, y + 3, MO + 20] : [y - 3, PW - MO - 20, y + 3, PW - MO]; props.justification = leftSide ? Justification.LEFT_ALIGN : Justification.RIGHT_ALIGN; }
    var f = tf(mp, gb, '', props); f.insertionPoints[0].contents = SpecialCharacters.AUTO_PAGE_NUMBER; set(f.paragraphs[0], props);
  }
  for (i = 0; i < 2; i++) {
    var mp = msA.pages[i], left = i == 0;
    mp.marginPreferences.properties = MARG; msB.pages[i].marginPreferences.properties = MARG;
    var x0 = left ? MO : MI, x1 = left ? PW - MI : PW - MO, H = S.header;
    if (H.show) {
      var hy = MT - 9;
      tf(mp, [hy - 3, x0, hy + 3, x1], left ? (M.book || '') : chapterLine, merge(HF, { fontStyle: FH_.semibold, pointSize: T.header, tracking: 40,
        fillColor: C(H.color), justification: left ? Justification.LEFT_ALIGN : Justification.RIGHT_ALIGN }));
      if (H.rule) mp.graphicLines.add({ geometricBounds: [MT - 4.5, x0, MT - 4.5, x1], strokeColor: C(H.color), strokeWeight: 0.5 });
    }
    folio(mp, left); folio(msB.pages[i], left);
    var TB = S.side_tab;
    if (TB && TB.show) {
      var n = parseInt(M.chapter_no, 10) || 1, ty = MT + 18 + ((n - 1) % 5) * (TB.height + 2);
      var gb = left ? [ty, -BLEED, ty + TB.height, TB.width] : [ty, PW - TB.width, ty + TB.height, PW + BLEED];
      // the tab colour can change with each part / theme of the book
      var tabCol = TB.color_by_part && TB.color_by_part.length && M.part_no ? TB.color_by_part[((parseInt(M.part_no, 10) || 1) - 1) % TB.color_by_part.length] : TB.color;
      mp.rectangles.add({ geometricBounds: gb, fillColor: C(tabCol), strokeWeight: 0 });
      tf(mp, [ty, left ? 0 : PW - TB.width, ty + TB.height, left ? TB.width : PW], M.chapter_no || '', merge(HF, { fontStyle: FH_.bold, pointSize: 13, fillColor: C(TB.text), justification: Justification.CENTER_ALIGN }));
    }
    // opener master: decorations only (title text stays in the story)
    var bp = msB.pages[i];
    if (O.layout == 'banner' || O.layout == 'band') {
      var L0 = left ? -BLEED : 0, R0 = left ? PW : PW + BLEED; // bleed on the outside edge only
      bp.rectangles.add({ geometricBounds: [-BLEED, L0, OH, R0], fillColor: ocol, strokeWeight: 0 });
      if (O.decor == 'bubbles') {
        var dots = [[20, left ? 24 : PW - 24, 22, 'paper', 14], [OH - 16, left ? PW - 16 : 16, 16, 'paper', 12], [20, PW * 0.52, 4, 'accent', 100], [OH - 26, PW * 0.6, 3, 'secondary', 100], [10, PW * 0.3, 2.5, 'accent', 100], [OH - 18, PW * 0.38, 2, 'paper', 80]];
        for (k = 0; k < dots.length; k++) { var d = dots[k], ov = bp.ovals.add({ geometricBounds: [d[0] - d[2], d[1] - d[2], d[0] + d[2], d[1] + d[2]], fillColor: C(d[3]), strokeWeight: 0 });
          try { ov.transparencySettings.blendingSettings.opacity = d[4]; } catch (e) {} }
        bp.ovals.add({ geometricBounds: [OH - 8, L0, OH + 22, R0], fillColor: PAPER, strokeWeight: 0 }); // curved lower edge
      } else {
        bp.rectangles.add({ geometricBounds: [OH - 2.5, L0, OH, R0], fillColor: C('accent'), strokeWeight: 0 });
      }
    }
  }

  // ---------------------------------------------------------------- pages and the story
  var first = doc.pages[0]; first.appliedMaster = msB;
  try { first.appliedSection.properties = { continueNumbering: false, pageNumberStart: parseInt(M.start_page, 10) || 1 }; } catch (e) {}
  var fr = first.textFrames.add({ geometricBounds: frameBounds(first) }), story = fr.parentStory, last = fr, guard = 0;
  var topInset = O.layout == 'banner' ? 10 : O.layout == 'band' ? 4 : 26;
  fr.textFramePreferences.insetSpacing = [topInset, 0, 0, 0];
  function frameOn(pg) { pg.appliedMaster = msA; return pg.textFrames.add({ geometricBounds: frameBounds(pg) }); }
  function flow() {
    doc.recompose();
    while (last.overflows && guard < 300) { var np = doc.pages.add(LocationOptions.AT_END), nf = frameOn(np); last.nextTextFrame = nf; last = nf; guard++; doc.recompose(); }
  }

  var BOXES = []; // {kind, s, e} character ranges of every box, for keep rules and QA
  function add(text, style) {
    var s0 = story.characters.length;
    story.insertionPoints[-1].contents = text + '\r';
    var t = story.characters.itemByRange(s0, story.characters.length - 1).texts[0];
    t.appliedParagraphStyle = style; t.clearOverrides(OverrideType.ALL);
    return s0;
  }
  function para(s0) { return story.characters[s0].paragraphs[0]; }
  function charStyle(s0, len, cs) { try { story.characters.itemByRange(s0, s0 + len - 1).appliedCharacterStyle = cs; } catch (e) {} }
  function labelled(label, text, style, cs, sep) {
    var s0 = add(label + (sep || ' ') + text, style); charStyle(s0, label.length, cs); return s0;
  }
  function anchorImage(s0, file, w, h) {
    flow();
    // the insertion point can still be in overset text while the layout settles: re-flow and try once more
    var r = null;
    for (var at = 0; at < 2 && !r; at++) {
      try { r = story.insertionPoints[s0].rectangles.add({ geometricBounds: [0, 0, h, w], strokeWeight: 0 }); }
      catch (e) { if (at) { LOG.push('picture ' + file.name + ' skipped: ' + e.message + ' (at ' + s0 + ' of ' + story.characters.length + ', overset=' + story.overflows + ')'); return null; }
        doc.recompose(); last.textFramePreferences.autoSizingType = AutoSizingTypeEnum.OFF; flow(); }
    }
    flow();
    try { try { r.frameFittingOptions.fittingOnEmptyFrame = EmptyFrameFittingOptions.PROPORTIONALLY; r.frameFittingOptions.fittingAlignment = AnchorPoint.CENTER_ANCHOR; } catch (fe) {} r.place(file); r.fit(FitOptions.PROPORTIONALLY); r.fit(FitOptions.CENTER_CONTENT); } catch (e) { LOG.push('place ' + file.name + ': ' + e.message); }
    return r;
  }
  function figure(b, figStyle, capStyle, maxW) {
    var w = Math.min(b.mm[0], maxW), h = b.mm[1] * w / b.mm[0];
    if (h > FH * 0.42) { w = w * FH * 0.42 / h; h = FH * 0.42; }
    var s0 = add('', figStyle);
    anchorImage(s0, File(BASE + '/' + b.src), w, h);
    para(s0).leading = h * 2.8346 + 2; // fixed leading = picture height (Auto leading adds 20 % and pushes figures off the page)
    if (b.caption) add(b.caption, capStyle); else set(para(s0), { keepWithNext: 0 });
    return s0;
  }
  function table(b) {
    var rows = b.rows, nc = 0, r, cI;
    for (r = 0; r < rows.length; r++) nc = Math.max(nc, rows[r].length);
    var lines = []; for (r = 0; r < rows.length; r++) { var row = rows[r].slice(0); while (row.length < nc) row.push(''); lines.push(row.join('\t')); }
    var s0 = story.characters.length;
    story.insertionPoints[-1].contents = lines.join('\r') + '\r';
    var t = story.characters.itemByRange(s0, story.characters.length - 2).texts[0];
    t.appliedParagraphStyle = st.td; flow();
    t.convertToTable('\t', '\r'); var tb = story.tables[-1]; flow();
    para(s0).appliedParagraphStyle = st.table;
    // column widths follow the longest text in each column
    var wts = [], tot = 0;
    for (cI = 0; cI < nc; cI++) { var mx = 4; for (r = 0; r < rows.length; r++) mx = Math.max(mx, Math.min(40, (rows[r][cI] || '').length)); wts.push(mx); tot += mx; }
    for (cI = 0; cI < nc; cI++) tb.columns[cI].width = FW * wts[cI] / tot;
    var cells = tb.cells.everyItem().getElements(), TS = S.table;
    for (k = 0; k < cells.length; k++) {
      var cl = cells[k], ri = cl.parentRow.index, hd = b.header && ri == 0;
      set(cl, { topInset: 1.6, bottomInset: 1.6, leftInset: 2, rightInset: 2, verticalJustification: VerticalJustification.CENTER_ALIGN,
        topEdgeStrokeColor: C(TS.stroke), bottomEdgeStrokeColor: C(TS.stroke), leftEdgeStrokeColor: C(TS.stroke), rightEdgeStrokeColor: C(TS.stroke),
        topEdgeStrokeWeight: 0.5, bottomEdgeStrokeWeight: 0.5, leftEdgeStrokeWeight: 0.5, rightEdgeStrokeWeight: 0.5 });
      cl.texts[0].appliedParagraphStyle = hd ? st.th : st.td;
      if (hd) cl.fillColor = C(TS.head_fill); else if (TS.zebra && ri % 2 == 0) cl.fillColor = C(TS.zebra);
    }
    try { if (b.header) tb.rows[0].rowType = RowTypes.HEADER_ROW; } catch (e) {}
    for (r = 0; r < tb.rows.length - 1; r++) try { tb.rows[r].keepWithNextRow = true; } catch (e) {}
    flow();
    return s0;
  }
  function optionsLine(opts, cols, indent) {
    if (indent === undefined) indent = EX.L + 7;
    var avail = FW - EX.R - indent, rows = [], q;
    for (q = 0; q < opts.length; q += cols) {
      var cells = []; for (var j = q; j < Math.min(q + cols, opts.length); j++) cells.push('(' + String.fromCharCode(97 + j) + ')  ' + opts[j]);
      rows.push(cells.join('\t'));
    }
    var tabs = []; for (q = 1; q < cols; q++) tabs.push({ alignment: TabStopAlignment.LEFT_ALIGN, position: indent + avail * q / cols });
    return { rows: rows, tabs: tabs };
  }

  // ---------------------------------------------------------------- opener text
  var sLabel = add(O.layout == 'band' ? (M.chapter_no || '') : (O.label || 'CHAPTER') + ' ' + (M.chapter_no || ''), st.chLabel);
  var sTitle = add(M.chapter_title, st.chTitle);
  if (O.character && O.layout != 'minimal') { para(sTitle).rightIndent = 58; para(sLabel).rightIndent = 58; }
  var sObj = -1;
  if (M.objectives && M.objectives.length) {
    sObj = add(M.objectives_intro || 'In this chapter you will learn:', st.objHead);
    for (k = 0; k < M.objectives.length; k++) add(M.objectives[k], st.objItem);
    set(para(story.characters.length - 2), { keepWithNext: 0, spaceAfter: 6 });
    BOXES.push({ kind: 'Objectives', s: sObj, e: story.characters.length - 1 });
  }

  // ---------------------------------------------------------------- body (house rules are applied as each paragraph is added,
  // so the character ranges recorded for boxes and numbers stay exact)
  var HS = GalleyHouse, LABELS = [], MATH = S.math || {}, NUMS = S.numbering || {};
  var STACK = (MATH.fractions || 'stacked') == 'stacked';
  function frac(s0) { if (STACK && /\d\s*\/\s*\d/.test(para(s0).contents)) { flow(); HS.stackFractions(para(s0), C('ink'), LOG); } return s0; }
  function calcLines(s0, lines, style) {
    // "=" continuation lines sit under the first "=" of their calculation
    if (!lines || !lines.length) return s0;
    var cs = [], last = s0;
    for (var q = 0; q < lines.length; q++) { last = add(lines[q], style); cs.push(last); frac(last); }
    flow(); var ps = []; for (q = 0; q < cs.length; q++) ps.push(para(cs[q]));
    if (!HS.alignCalc(para(s0), ps, flow)) LOG.push('calc without "=": ' + para(s0).contents.substr(0, 30));
    BOXES.push({ kind: 'Calc', s: s0, e: story.characters.length - 1 });
    return last;
  }
  function colsum(b, style, indent) {
    var rows = HS.columnSumRows(b.head, b.rows), s1 = story.characters.length, made = [];
    for (var q = 0; q < rows.length; q++) made.push(add(rows[q].text, style));
    flow();
    for (q = 0; q < rows.length; q++) HS.columnSumFormat(para(made[q]), b.head.length, indent, MATH.column_width || 9, C('ink'), rows[q].answer, rows[q].head);
    flow(); BOXES.push({ kind: 'Calc', s: s1, e: story.characters.length - 1 });
  }
  function diagram(d, style, maxW) {
    var s1 = add('', style);
    try { HS.drawDiagram(doc, story, s1, d, maxW, FH * 0.45, { ink: C('ink'), color: function (hx) { return hexColor(hx); }, font: FB_.family, fontStyle: FB_.regular, textPt: T.body }, flow); }
    catch (e) { LOG.push('diagram: ' + e.message); }
    BOXES.push({ kind: 'Diagram', s: s1, e: story.characters.length - 1 });
    return s1;
  }
  function hexColor(hx) { var nm = 'Galley ' + hx.toUpperCase(), c = doc.colors.itemByName(nm);
    return c.isValid ? c : doc.colors.add({ name: nm, model: ColorModel.PROCESS, space: ColorSpace.RGB, colorValue: rgb(hx) }); }
  function numbered(label, text, style, indent, hangW, csN) {
    var s1 = add(label + '\t' + text, style);
    try { var p = para(s1); p.leftIndent = indent + hangW; p.firstLineIndent = -hangW; p.tabList = [{ alignment: TabStopAlignment.LEFT_ALIGN, position: indent + hangW }]; } catch (e) {}
    if (csN) charStyle(s1, label.length, csN);
    LABELS.push(label + '\u0001' + String(text).substr(0, 24)); return s1; // number + start of its text, for QA
  }
  for (var bi = 0; bi < BL.length; bi++) {
    var b = BL[bi], s0;
    if (b.type == 'h2') add(b.text, st.h2);
    else if (b.type == 'h3') add(b.text, st.h3);
    else if (b.type == 'body') { s0 = frac(add(b.text, body)); calcLines(s0, b.calc, st.calc); if (b.lead_in) para(s0).keepWithNext = 2; }
    else if (b.type == 'list' && b.ordered) {
      // numbered points stay numbered, in a number column with a clear gap (hanging indent)
      var lab = []; for (k = 0; k < b.items.length; k++) lab.push(b.items[k].label);
      var hw = HS.hang(lab, T.body, NUMS.hang || 7);
      for (k = 0; k < b.items.length; k++) { s0 = numbered(b.items[k].label, b.items[k].text, st.numlist, b.items[k].level ? hw : 0, hw, csNum); if (k < b.items.length - 1) para(s0).keepWithNext = 1; }
      para(s0).spaceAfter = 3.5;
    }
    else if (b.type == 'list') { for (k = 0; k < b.items.length; k++) { s0 = add(b.items[k], st.list); if (k < b.items.length - 1) para(s0).keepWithNext = 1; } para(s0).spaceAfter = 3.5; }
    else if (b.type == 'figure') { var fs0 = figure(b, st.figure, st.caption, FW * (S.figures && S.figures.max_width ? S.figures.max_width : 0.82)); BOXES.push({ kind: 'Figure', s: fs0, e: story.characters.length - 1 }); }
    else if (b.type == 'table') { var ts0 = table(b); BOXES.push({ kind: 'Table', s: ts0, e: story.characters.length - 1 }); }
    else if (b.type == 'diagram') diagram(b, st.figure, FW * 0.9);
    else if (b.type == 'colsum') colsum(b, st.calc, MATH.indent || 10);
    else if (b.type == 'rule') {
      // a rule is styled strongly (example-box style); its examples plainer, in bold body text
      var RX = BX.example, rs = story.characters.length;
      add(b.title, RX.head); frac(add(b.text, RX.body));
      for (k = 0; k < b.examples.length; k++) { s0 = frac(add(b.examples[k], body)); try { para(s0).fontStyle = FB_.bold; para(s0).leftIndent = RX.L; } catch (e) {} }
      BOXES.push({ kind: 'Rule', s: rs, e: story.characters.length - 1 });
    }
    else if (b.type == 'note') {
      s0 = labelled(b.label, b.text, st.note, csNote, '  ');
      // teaching notes: bold label, italic body
      if (b.kind == 'teaching' && N.teaching_italic !== false) HS.italicBody(para(s0), b.label.length, FB_.italic);
      if (N.icon) {
        var ic = anchorImage(s0, File(ART + '/' + N.icon), 6.5, 6.5);
        // inline icon hanging in the note's left indent: travels with the text, never leaves the column
        try { ic.anchoredObjectSettings.anchoredPosition = AnchorPosition.INLINE_POSITION; ic.anchoredObjectSettings.anchorYoffset = -1.6;
          story.insertionPoints[s0 + 1].contents = '\t'; set(para(s0), { leftIndent: 13, firstLineIndent: -9.5 }); } catch (e) { LOG.push('icon: ' + e.message); }
      }
      BOXES.push({ kind: 'Note', s: s0, e: story.characters.length - 1 });
    }
    else if (b.type == 'example') {
      var X = b.kind == 'activity' ? BX.activity : BX.example, xs = story.characters.length;
      var ttl = b.title ? b.label + (X.cfg.head == 'pill' ? '  ' + String.fromCharCode(8226) + '  ' : ':  ') + b.title : b.label;
      add(ttl, X.head);
      var exLabels = []; for (k = 0; k < b.items.length; k++) if (b.items[k].type == 'item') exLabels.push(NUMS.example_roman_to_arabic && b.items[k].kind == 'roman' ? HS.toArabic(b.items[k].label) : b.items[k].label);
      var exHang = HS.hang(exLabels, T.body, NUMS.hang || 7);
      for (k = 0; k < b.items.length; k++) {
        var it = b.items[k];
        if (it.type == 'step') { s0 = frac(labelled(it.label + ':', it.text, X.step, X.label)); calcLines(s0, it.calc, X.step); }
        else if (it.type == 'item') {
          var lb = NUMS.example_roman_to_arabic && it.kind == 'roman' ? HS.toArabic(it.label) : it.label;
          s0 = frac(numbered(lb, it.text, X.body, X.L, exHang, X.label)); calcLines(s0, it.calc, X.body);
        }
        else if (it.type == 'figure') figure(it, X.fig, X.cap, FW * 0.6);
        else if (it.type == 'diagram') diagram(it, X.fig, FW - X.L - X.R - 4);
        else if (it.type == 'colsum') colsum(it, X.body, X.L + (MATH.indent || 10));
        else if (it.type == 'list') for (var li = 0; li < it.items.length; li++) add(it.items[li], X.list);
        else { s0 = frac(add(it.text, X.body)); calcLines(s0, it.calc, X.body); }
      }
      BOXES.push({ kind: X.kind, s: xs, e: story.characters.length - 1 });
    }
    else if (b.type == 'exercise') {
      var es = story.characters.length, grp = [], firstQ = true;
      add(b.label + (b.title ? ':  ' + b.title : ''), EX.head);
      // number columns sized to the widest number at each level, so the text always starts after a clear gap
      var l0 = [], l1 = [];
      for (k = 0; k < b.items.length; k++) if (b.items[k].type == 'question') (b.items[k].level ? l1 : l0).push(b.items[k].label || (b.items[k].n ? b.items[k].n + '.' : String.fromCharCode(8226)));
      var h0 = HS.hang(l0, T.body, NUMS.hang || 7), h1 = HS.hang(l1, T.body, 6);
      for (k = 0; k < b.items.length; k++) {
        var q = b.items[k];
        if (q.type == 'instruction') { s0 = add(q.text, EX.step); charStyle(s0, q.text.length, csBold); para(s0).keepWithNext = 2; calcLines(s0, q.calc, EX.step); continue; }
        if (q.type == 'diagram') { var dg = diagram(q, EX.body, FW - EX.L - EX.R - h0 - 4); try { para(dg).leftIndent = EX.L + h0; } catch (e) {}
          if (grp.length) grp[grp.length - 1][1] = dg; continue; }
        if (q.type == 'colsum') { colsum(q, EX.body, EX.L + h0); continue; }
        var qlabel = q.label || (q.n ? q.n + '.' : String.fromCharCode(8226)), lvl = q.level ? 1 : 0;
        var qs = frac(numbered(qlabel, q.text, st.question, EX.L + (lvl ? h0 : 0), lvl ? h1 : h0, csNum));
        if (!lvl && !firstQ) para(qs).spaceBefore = S.exercise.group_space || 2.2; // the same gap before every question group
        firstQ = false;
        var lastP = calcLines(qs, q.calc, st.question);
        var qIndent = para(qs).leftIndent;
        if (q.options && q.options.length) {
          para(qs).keepWithNext = 2;
          // answer options on tab columns: try 4 (or fewer) columns, then 2, then 1, and keep the first layout where
          // every row sets on one line and every option starts exactly on its tab stop (measured, not estimated)
          var tries = [Math.min(4, q.options.length), 2, 1];
          for (var ti = 0; ti < tries.length; ti++) {
            if (ti > 0 && tries[ti] >= tries[ti - 1]) continue;
            var ol = optionsLine(q.options, tries[ti], qIndent), rowStarts = [], fits = true;
            for (var oi = 0; oi < ol.rows.length; oi++) { lastP = add(ol.rows[oi], st.options); rowStarts.push(lastP);
              try { para(lastP).leftIndent = qIndent; para(lastP).tabList = ol.tabs; } catch (e) {} if (oi < ol.rows.length - 1) para(lastP).keepWithNext = 2; }
            if (tries[ti] == 1) break;
            flow();
            for (oi = 0; oi < rowStarts.length && fits; oi++) {
              var rp = para(rowStarts[oi]); if (rp.lines.length > 1) { fits = false; break; }
              var x0 = rp.insertionPoints[0].horizontalOffset - qIndent, chars = rp.characters, tn = 0;
              for (var ci = 0; ci < chars.length - 1; ci++) if (chars[ci].contents == '\t') {
                if (Math.abs(chars[ci + 1].horizontalOffset - x0 - ol.tabs[tn].position) > 1) { fits = false; break; } tn++; }
            }
            if (fits) break;
            story.characters.itemByRange(rowStarts[0], story.characters.length - 1).remove(); lastP = qs;
          }
        }
        var nl = { lines1: 1, lines2: 2, lines3: 3 }[q.answer] || 0;
        for (var al = 0; al < nl; al++) { para(lastP).keepWithNext = 2; lastP = add(String.fromCharCode(160), st.answer); try { para(lastP).leftIndent = qIndent; } catch (e) {} }
        if (nl) para(lastP).spaceAfter = 3;
        grp.push([qs, lastP]);
      }
      BOXES.push({ kind: 'Exercise', s: es, e: story.characters.length - 1, groups: grp });
    }
  }
  // remove the empty paragraph return at the very end
  try { if (story.characters[-1].contents == '\r') story.characters[-1].remove(); } catch (e) {}
  flow();

  // ---------------------------------------------------------------- opener fit: title stays inside the banner, content starts below it
  function baselineOf(s) { var p = para(s); return p.lines[-1].baseline; }
  if (O.layout != 'minimal') {
    var tp = para(sTitle), ps = T.opener_title;
    while (baselineOf(sTitle) > OH - 10 && ps > 18) { ps -= 1; tp.pointSize = ps; tp.leading = ps * 1.08; doc.recompose(); }
    if (ps != T.opener_title) LOG.push('opener title reduced to ' + ps + ' pt to fit the banner');
  }
  var nextS = sObj >= 0 ? sObj : sTitle + para(sTitle).characters.length;
  if (nextS < story.characters.length) {
    var want = (O.layout == 'minimal' ? baselineOf(sTitle) + 16 : OH + 8);
    var np0 = para(nextS), cur = np0.lines[0].baseline - np0.lines[0].ascent;
    np0.spaceBefore = Math.max(4, want - (cur - np0.spaceBefore));
  }
  flow();

  // ---------------------------------------------------------------- keep rules: boxes never split
  function paraRange(bx) { var out = [], p = para(bx.s); while (p.isValid) { out.push(p); var nx = p.index + p.characters.length; if (nx > bx.e || nx >= story.characters.length) break; p = story.characters[nx].paragraphs[0]; } return out; }
  function chain(ps) { for (var q = 0; q < ps.length; q++) { try { ps[q].keepLinesTogether = true; ps[q].keepAllLinesTogether = true; if (q < ps.length - 1) ps[q].keepWithNext = 5; } catch (e) {} } }
  function frameOf(p) { try { return p.parentTextFrames[0].id; } catch (e) { return -1; } }
  // outlined boxes are drawn explicitly (top rule on the first paragraph, bottom rule on the last, sides on all, overlapping
  // offsets) because InDesign stops merging consecutive borders when a box is the last thing in its frame
  function outline(bx) {
    var cfg = bx.kind == 'Example' ? S.example : bx.kind == 'Activity' ? (S.activity || S.example) : null;
    if (!cfg || cfg.treatment != 'outlined') return;
    var ps = bx.paras;
    for (var q = 0; q < ps.length; q++) set(ps[q], { mergeConsecutiveParaBorders: false,
      paragraphBorderTopLineWeight: q == 0 ? 0.9 : 0, paragraphBorderBottomLineWeight: q == ps.length - 1 ? 0.9 : 0,
      paragraphBorderTopOffset: q == 0 ? 2.5 : 3.2, paragraphBorderBottomOffset: q == ps.length - 1 ? 2.5 : 0 });
  }
  for (k = 0; k < BOXES.length; k++) { BOXES[k].paras = paraRange(BOXES[k]); chain(BOXES[k].paras);
    outline(BOXES[k]);
    var lp0 = BOXES[k].paras[BOXES[k].paras.length - 1]; if (/^(Example|Activity|Exercise)/.test(BOXES[k].kind)) try { lp0.spaceAfter = Math.max(lp0.spaceAfter, 4); } catch (e) {} }
  flow();
  // an exercise longer than a page may continue, but only between questions; everything else must fit in one frame
  for (k = 0; k < BOXES.length; k++) {
    var bx = BOXES[k], ps2 = bx.paras;
    if (bx.kind != 'Exercise' || frameOf(ps2[0]) == frameOf(ps2[ps2.length - 1])) continue;
    for (var pi = 0; pi < ps2.length; pi++) try { ps2[pi].keepWithNext = 0; } catch (e) {}
    // head + instruction + first question stay together; each question keeps its options and answer lines
    var firstQ = bx.groups.length ? bx.groups[0][1] : bx.s;
    for (pi = 0; pi < ps2.length; pi++) { if (ps2[pi].index <= firstQ && pi < ps2.length - 1) ps2[pi].keepWithNext = 5; }
    for (var g = 0; g < bx.groups.length; g++) for (pi = 0; pi < ps2.length - 1; pi++) if (ps2[pi].index >= bx.groups[g][0] && ps2[pi].index < bx.groups[g][1]) ps2[pi].keepWithNext = 5;
    bx.continues = true; LOG.push('exercise "' + ps2[0].contents.substr(0, 20) + '" is longer than the space: allowed to continue between questions');
  }
  flow();

  // ---------------------------------------------------------------- figure pull-back: shrink a pushed figure (down to figures.min_scale, default 60 %) if that keeps it on the page before
  var MINSC = S.figures && S.figures.min_scale ? S.figures.min_scale : 0.6;
  for (var pass = 0; pass < 2; pass++) {
    var changed = 0, rects = story.rectangles.everyItem().getElements();
    for (var ri = 0; ri < rects.length; ri++) {
      try {
        var rc = rects[ri], fp = rc.parent.paragraphs[0]; if (!/Figure/.test(fp.appliedParagraphStyle.name)) continue;
        var f2 = fp.parentTextFrames[0]; if (!f2.previousTextFrame) continue;
        var gb2 = rc.geometricBounds; if (gb2[0] - MT > 30) continue;
        var pf = f2.previousTextFrame, free = (PH - MB) - (pf.lines[-1].baseline + 3) - 4, hFig = gb2[2] - gb2[0];
        var capH = fp.keepWithNext ? 9 : 0, room = free - capH;
        if (room < hFig - 1 && room >= MINSC * hFig) {
          var sc = room / hFig; rc.geometricBounds = [gb2[0], gb2[1], gb2[0] + room, gb2[1] + (gb2[3] - gb2[1]) * sc];
          fp.leading = room * 2.8346 + 2;
          rc.fit(FitOptions.PROPORTIONALLY); rc.fit(FitOptions.CENTER_CONTENT); doc.recompose(); changed++;
          LOG.push('figure scaled to ' + Math.round(sc * 100) + '% to stay on page ' + pf.parentPage.name);
        }
      } catch (e) { LOG.push('pull-back: ' + e.message); }
    }
    flow(); if (!changed) break;
  }
  // tables: keep-with-next is unreliable on a table's paragraph; if the table moved on, take its lead-in heading with it
  var tbls = story.tables.everyItem().getElements();
  for (k = 0; k < tbls.length; k++) {
    try {
      var idx = tbls[k].storyOffset.index, tFrame = tbls[k].cells[0].insertionPoints[0].parentTextFrames[0];
      var lead = story.characters[idx - 1].paragraphs[0];
      if (/^H[23]$|Body/.test(lead.appliedParagraphStyle.name) && lead.parentTextFrames[0].id != tFrame.id) {
        lead.startParagraph = StartParagraph.NEXT_FRAME; LOG.push('moved table lead-in to the table page: ' + lead.contents.substr(0, 30)); flow();
      }
    } catch (e) {}
  }
  // ---------------------------------------------------------------- stranded headings: a heading that ends a frame moves to the next one
  var HEADS = /^(H2|H3|Example Head|Activity Head|Exercise Head|Objectives Head)$/;
  for (var pass2 = 0; pass2 < 3; pass2++) {
    var moved = 0, TFs = story.textContainers;
    for (var hi = 0; hi < TFs.length - 1; hi++) {
      try {
        var lp = TFs[hi].paragraphs[-1]; if (!lp.isValid || !TFs[hi + 1].characters.length || lp.parentTextFrames.length > 1) continue;
        var nm2 = lp.appliedParagraphStyle.name, txt = lp.contents.replace(/\s+$/, '');
        var leadIn = nm2 == 'Body' && /:$/.test(txt);
        if ((HEADS.test(nm2) || leadIn) && lp.startParagraph != StartParagraph.NEXT_FRAME) {
          lp.startParagraph = StartParagraph.NEXT_FRAME; doc.recompose(); moved++; LOG.push('moved stranded heading: ' + txt.substr(0, 40));
        }
      } catch (e) {}
    }
    flow(); if (!moved) break;
  }
  // no widows or orphans anywhere; a section that would only just start at the foot of a page moves to the next page
  GalleyHouse.keepLines(story, (S.flow && S.flow.keep_lines) || 2); flow();
  if (!S.flow || S.flow.move_cut_sections !== false) GalleyHouse.moveCutSections(story, function (n) { return n == 'H2' || n == 'H3'; }, FH, flow, LOG);
  // drop empty pages at the end
  while (doc.pages.length > 1 && last.characters.length == 0 && last.previousTextFrame) { var pg = last.parentPage, pv = last.previousTextFrame; last.remove(); pg.remove(); last = pv; doc.recompose(); }

  // ---------------------------------------------------------------- illustrations layer: opener character + spot art in big gaps
  var artLayer = doc.layers.add({ name: 'Illustrations' });
  function placeArt(pg, name, gb) {
    var r = pg.rectangles.add(artLayer, { geometricBounds: gb, strokeWeight: 0 });
    try { try { r.frameFittingOptions.fittingOnEmptyFrame = EmptyFrameFittingOptions.PROPORTIONALLY; r.frameFittingOptions.fittingAlignment = AnchorPoint.CENTER_ANCHOR; } catch (fe) {} r.place(File(ART + '/' + name)); r.fit(FitOptions.PROPORTIONALLY); r.fit(FitOptions.CENTER_CONTENT); r.fit(FitOptions.FRAME_TO_CONTENT); } catch (e) { LOG.push('art ' + name + ': ' + e.message); }
    return r;
  }
  if (O.character && O.layout != 'minimal') {
    var cw = 50, chh = OH - 18, x1 = PW - MO;
    if (O.layout == 'band') { var cyc = (OH - 4) / 2; var halo = first.ovals.add(artLayer, { geometricBounds: [cyc - 30, x1 - 58, cyc + 30, x1 + 2], fillColor: PAPER, strokeWeight: 0 });
      try { halo.transparencySettings.blendingSettings.opacity = 22; } catch (e) {} placeArt(first, O.character, [cyc - 24, x1 - 52, cyc + 24, x1 - 4]); }
    else placeArt(first, O.character, [8, x1 - cw, 8 + chh, x1]);
  }
  var IL = S.illustrations, set_ = IL.set, artNo = 0, TF = story.textContainers;
  for (var fi = 1; fi < TF.length && set_ && set_.length; fi++) {
    try {
      var tfr = TF[fi]; if (!tfr.lines.length) continue;
      var fb = tfr.geometricBounds, used = tfr.lines[-1].baseline + 5, its = tfr.parentPage.allPageItems;
      for (var ai = 0; ai < its.length; ai++) { var ig = its[ai].geometricBounds; if (its[ai] !== tfr && ig[0] > fb[0] && ig[0] < fb[2] && ig[2] > used) used = Math.max(used, ig[2] + 3); }
      var gap = fb[2] - used; if (gap < IL.gap_min) continue;
      var ah = Math.min(gap - 6, IL.max_height), nmA = set_[artNo % set_.length]; artNo++;
      var leftPg = tfr.parentPage.side == PageSideOptions.LEFT_HAND, aw = ah * 1.25;
      var ax = leftPg ? fb[1] + 4 : fb[3] - aw - 4; // outer side
      placeArt(tfr.parentPage, nmA, [fb[2] - ah, ax, fb[2], ax + aw]);
      LOG.push('illustration ' + nmA + ' on page ' + tfr.parentPage.name + ' (gap ' + Math.round(gap) + ' mm)');
    } catch (e) { LOG.push('art gap: ' + e.message); }
  }
  artLayer.locked = false;

  // ---------------------------------------------------------------- save build data for QA
  var boxesOut = [];
  for (k = 0; k < BOXES.length; k++) boxesOut.push('{"kind":"' + BOXES[k].kind + '","s":' + BOXES[k].s + ',"e":' + BOXES[k].e + ',"continues":' + (BOXES[k].continues ? 'true' : 'false') + '}');
  doc.insertLabel('galley_boxes', '[' + boxesOut.join(',') + ']');
  var labOut = []; for (k = 0; k < LABELS.length; k++) labOut.push('"' + String(LABELS[k]).replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\u0001/g, '\\u0001') + '"');
  story.insertLabel('galley_labels', '[' + labOut.join(',') + ']');
  doc.insertLabel('galley_style', S.id);
  LOG.push('pages=' + doc.pages.length + ' overset=' + story.overflows);
  var docName = (S.id || 'chapter') + '_chapter';
  doc.save(File(OUT + '/' + docName + '.indd'));
  var lf = File(OUT + '/build_log.txt'); lf.encoding = 'UTF-8'; lf.open('w'); lf.write(LOG.join('\n')); lf.close();
  app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;
})();
