// Test fixture for "continue in my style": makes the kind of document a designer starts from: their own
// style names (not Galley's), their own colours and master, and one sample page set by hand.
// Saves to the path in scriptArgs "galley_out" (default: work/designer_sample.indd) and leaves it open.
#target indesign
(function () {
  var out = app.scriptArgs.isDefined('galley_out') ? app.scriptArgs.getValue('galley_out') : File($.fileName).parent.parent + '/work/designer_sample.indd';
  app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
  var doc = app.documents.add();
  doc.viewPreferences.horizontalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  doc.viewPreferences.verticalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  with (doc.documentPreferences) { pageWidth = 200; pageHeight = 265; facingPages = true; documentBleedTopOffset = 3; documentBleedUniformSize = true; }
  doc.marginPreferences.properties = { top: 20, bottom: 24, left: 20, right: 16 };
  function col(n, v) { return doc.colors.add({ name: n, model: ColorModel.PROCESS, space: ColorSpace.RGB, colorValue: v }); }
  var teal = col('Series Teal', [0, 121, 140]), coral = col('Series Coral', [237, 106, 90]), sand = col('Series Sand', [252, 241, 222]),
      mint = col('Series Mint', [225, 244, 243]), ink = col('Series Ink', [33, 37, 41]), paper = doc.swatches.itemByName('Paper');
  function set(o, p) { for (var k in p) try { o[k] = p[k]; } catch (e) {} return o; }
  function PS(name, p) { return set(doc.paragraphStyles.add({ name: name }), p); }
  var body = PS('Body Text', { appliedFont: 'Segoe UI', fontStyle: 'Regular', pointSize: 10.5, leading: 15, fillColor: ink, spaceAfter: 2.5, hyphenation: false });
  function S(name, p) { p.basedOn = body; return PS(name, p); }
  var shade = function (c, t) { return { paragraphShadingOn: true, paragraphShadingColor: c, paragraphShadingTint: 100, paragraphShadingWidth: ParagraphShadingWidthEnum.COLUMN_WIDTH,
    paragraphShadingTopOffset: t || 1.8, paragraphShadingBottomOffset: t || 1.8, mergeConsecutiveParaBorders: true }; };
  S('Chapter Number', { appliedFont: 'Segoe UI', fontStyle: 'Bold', pointSize: 12, tracking: 200, fillColor: coral, spaceBefore: 20, spaceAfter: 1 });
  S('Chapter Head', { appliedFont: 'Segoe UI', fontStyle: 'Bold', pointSize: 30, leading: 34, fillColor: teal, spaceAfter: 8, keepWithNext: 2,
    ruleBelow: true, ruleBelowColor: coral, ruleBelowLineWeight: 3, ruleBelowOffset: 4, ruleBelowWidth: RuleWidth.TEXT_WIDTH });
  S('A Head', { appliedFont: 'Segoe UI', fontStyle: 'Bold', pointSize: 16, leading: 20, fillColor: teal, spaceBefore: 8, spaceAfter: 3, keepWithNext: 3 });
  S('B Head', { appliedFont: 'Segoe UI', fontStyle: 'Bold', pointSize: 12, fillColor: coral, spaceBefore: 4, spaceAfter: 1.5, keepWithNext: 3 });
  var bl = S('Bullet', { leftIndent: 5, firstLineIndent: -5, spaceAfter: 1, bulletsAndNumberingListType: ListType.BULLET_LIST, bulletsTextAfter: '^t' });
  S('Example Title', set({ appliedFont: 'Segoe UI', fontStyle: 'Bold', fillColor: coral, spaceBefore: 6, leftIndent: 4, rightIndent: 4, spaceAfter: 0, keepWithNext: 5 }, shade(sand, 2.4)));
  S('Example Text', set({ leftIndent: 4, rightIndent: 4, spaceAfter: 0, spaceBefore: 0 }, shade(sand)));
  S('Exercise Title', set({ appliedFont: 'Segoe UI', fontStyle: 'Bold', fillColor: paper, spaceBefore: 7, spaceAfter: 2.5, leftIndent: 3, keepWithNext: 5 }, shade(teal, 1.6)));
  S('Exercise Q', { leftIndent: 7, firstLineIndent: -7, spaceAfter: 1.5 });
  S('Exercise Options', { leftIndent: 7, spaceAfter: 2.5 });
  S('Tip', set({ leftIndent: 4, rightIndent: 4, spaceBefore: 3, spaceAfter: 5, pointSize: 10 }, shade(mint, 2.4)));
  S('Fig', { justification: Justification.CENTER_ALIGN, spaceBefore: 2, spaceAfter: 1 });
  S('Caption', { pointSize: 8.5, fontStyle: 'Italic', justification: Justification.CENTER_ALIGN, spaceAfter: 4 });
  doc.characterStyles.add({ name: 'Label Bold', fontStyle: 'Bold', fillColor: coral });
  // master: running folio and a coral rule (drawn with page rulers, then back to InDesign's default spread ruler)
  doc.viewPreferences.rulerOrigin = RulerOrigin.PAGE_ORIGIN;
  var ms = doc.masterSpreads[0];
  for (var i = 0; i < 2; i++) {
    var mp = ms.pages[i], left = i == 0;
    mp.graphicLines.add({ geometricBounds: [12, left ? 16 : 20, 12, left ? 180 : 184], strokeColor: coral, strokeWeight: 1 });
    var f = mp.textFrames.add({ geometricBounds: [253, left ? 16 : 164, 259, left ? 36 : 184] });
    f.insertionPoints[0].contents = SpecialCharacters.AUTO_PAGE_NUMBER;
    set(f.paragraphs[0], { appliedFont: 'Segoe UI', fontStyle: 'Bold', pointSize: 9, fillColor: teal, justification: left ? Justification.LEFT_ALIGN : Justification.RIGHT_ALIGN });
  }
  // one sample page, set by hand
  var pg = doc.pages[0], fr = pg.textFrames.add({ geometricBounds: [20, 20, 241, 184] }), st = fr.parentStory;
  var lines = [['Chapter Number', 'CHAPTER 2'], ['Chapter Head', 'Living Things'], ['A Head', '2.1 What is alive?'],
    ['Body Text', 'Living things grow, need food and water, and make young of their own. A rock does none of these things, so it is not alive.'],
    ['Bullet', 'Plants make their own food.'], ['Bullet', 'Animals eat plants or other animals.'],
    ['Example Title', 'Example 1: Is a seed alive?'], ['Example Text', 'A seed looks still, but inside it is a tiny plant waiting for water and warmth.'],
    ['Tip', 'Tip: Ask three questions: does it grow, does it feed, does it make young?'],
    ['Exercise Title', 'Exercise 2.1'], ['Exercise Q', '1.\tName two things that all living things need.']];
  for (i = 0; i < lines.length; i++) { var s0 = st.characters.length; st.insertionPoints[-1].contents = lines[i][1] + (i < lines.length - 1 ? '\r' : '');
    st.characters.itemByRange(s0, st.characters.length - 1).texts[0].appliedParagraphStyle = doc.paragraphStyles.itemByName(lines[i][0]); }
  doc.viewPreferences.rulerOrigin = RulerOrigin.SPREAD_ORIGIN;
  doc.save(File(out));
  app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;
})();
