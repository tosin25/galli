// Galley house rules: layout behaviours shared by build_chapter.jsx (Galley's own styles) and flow_into.jsx
// (the designer's styles). Load with $.evalFile; everything hangs off the global GalleyHouse.
// Each function works on text already in a story; callers recompose (flow) before calling the measuring ones.
// Units: the caller has set millimetres; type sizes stay in points.
var GalleyHouse = (function () {
  var PT = 2.8346; // points per mm

  // ---- numbers ---------------------------------------------------------------------------------------
  function roman(s) { // 'iv' -> 4 (for "example lists numbered i, ii, iii are set 1, 2, 3")
    var v = { i: 1, v: 5, x: 10, l: 50, c: 100, d: 500, m: 1000 }, n = 0, t = String(s).toLowerCase();
    for (var k = 0; k < t.length; k++) { var a = v[t.charAt(k)] || 0, b = v[t.charAt(k + 1)] || 0; n += a < b ? -a : a; }
    return n;
  }
  function toArabic(label) { // '(iv)' -> '4.'   'iv.' -> '4.'
    var m = String(label).match(/^\(?([ivxlc]+)[.)]?$/i); return m ? roman(m[1]) + '.' : label;
  }
  // width the number column needs: widest label at this size, plus a clear gap
  function hang(labels, pt, minMM) {
    var w = 0; for (var k = 0; k < labels.length; k++) w = Math.max(w, String(labels[k]).length);
    return Math.max(minMM || 6, Math.round((w * pt * 0.56 / PT + 2.5) * 2) / 2);
  }

  // ---- flow ------------------------------------------------------------------------------------------
  // no widows or orphans: at least n lines at both ends of every paragraph
  function keepLines(story, n) {
    try { var ps = story.paragraphs.everyItem(); ps.keepFirstLines = n; ps.keepLastLines = n; } catch (e) {}
  }
  // a section (heading + what follows, up to the next heading) that would start with only a small part at the
  // foot of a page, but fits on one page, starts on the next page instead
  function moveCutSections(story, isHead, frameH, flow, log) {
    for (var pass = 0; pass < 3; pass++) {
      var moved = 0, P = story.paragraphs.everyItem().getElements();
      for (var i = 0; i < P.length; i++) {
        var h = P[i]; if (!isHead(h.appliedParagraphStyle.name) || h.startParagraph == StartParagraph.NEXT_FRAME) continue;
        var f0; try { f0 = h.parentTextFrames[0].id; } catch (e) { continue; }
        var first = 0, total = 0, j = i;
        for (; j < P.length; j++) {
          if (j > i && isHead(P[j].appliedParagraphStyle.name)) break;
          var L = P[j].lines.everyItem().getElements();
          for (var q = 0; q < L.length; q++) { total++; try { if (L[q].parentTextFrames[0].id == f0) first++; } catch (e) {} }
        }
        if (first == total || first == 0) continue;
        // height of the whole section, from its first to its last baseline (rough when it spans frames)
        var lead = 5; try { lead = h.leading == Leading.AUTO ? h.pointSize * 1.2 / PT : h.leading / PT; } catch (e) {}
        if (total * lead < frameH * 0.8 && first / total < 0.45) {
          h.startParagraph = StartParagraph.NEXT_FRAME; flow(); moved++;
          if (log) log.push('section moved to next page (only ' + first + ' of ' + total + ' lines fitted): ' + h.contents.substr(0, 40));
        }
      }
      if (!moved) break;
    }
  }

  // ---- calculations ----------------------------------------------------------------------------------
  function eqX(p) { // x of the first "=" in a paragraph, relative to its frame's left edge
    var k = p.contents.indexOf('='); if (k < 0) return null;
    try { var f = p.parentTextFrames[0]; return p.characters[k].horizontalOffset - f.geometricBounds[1]; } catch (e) { return null; }
  }
  // continuation lines start with "=" (or "Or ... =") and their "=" sits under the first "=" of the calculation
  function alignCalc(head, conts, flow) {
    for (var pass = 0; pass < 2; pass++) {
      var x0 = eqX(head); if (x0 === null) return false;
      for (var k = 0; k < conts.length; k++) {
        var x = eqX(conts[k]); if (x === null) continue;
        conts[k].leftIndent = Math.max(0, conts[k].leftIndent + (x0 - x)); conts[k].firstLineIndent = 0;
      }
      flow();
    }
    return true;
  }
  // a Th / H / T / U column sum: header row, digit rows, rule above the answer row; centred tab columns
  function columnSumRows(head, rows) {
    var n = head.length, out = [{ text: '\t' + head.join('\t'), head: true }];
    for (var r = 0; r < rows.length; r++) {
      var op = '', digits = [];
      for (var c = 0; c < rows[r].length; c++) { var t = rows[r][c]; if (/^\d$/.test(t)) digits.push(t); else op = t == 'x' ? String.fromCharCode(215) : t; }
      while (digits.length < n) digits.unshift('');
      out.push({ text: op + '\t' + digits.slice(digits.length - n).join('\t'), answer: r == rows.length - 1 && rows.length > 1 });
    }
    return out;
  }
  function columnSumFormat(p, n, indent, colW, ruleColor, isAnswer, isHead) {
    var tabs = []; for (var c = 0; c < n; c++) tabs.push({ alignment: TabStopAlignment.CENTER_ALIGN, position: indent + 8 + colW * (c + 0.5) });
    try { p.tabList = tabs; p.leftIndent = indent; p.firstLineIndent = 0; } catch (e) {}
    if (isHead) try { p.fontStyle = 'Bold'; } catch (e) {}
    if (isAnswer) try {
      var fw = p.parentTextFrames[0].geometricBounds; fw = fw[3] - fw[1];
      p.properties = { ruleAbove: true, ruleAboveColor: ruleColor, ruleAboveLineWeight: 1, ruleAboveOffset: p.pointSize / PT + 1.2,
        ruleAboveWidth: RuleWidth.COLUMN_WIDTH, ruleAboveLeftIndent: indent, ruleAboveRightIndent: Math.max(0, fw - indent - 8 - colW * n - 2), spaceBefore: 1.5 };
    } catch (e) {}
  }

  // ---- fractions -------------------------------------------------------------------------------------
  // "3/4" set as a stacked fraction (numerator over a bar over denominator) in an inline frame
  var FRAC = /(^|[^\d\/])(\d{1,4})\s*\/\s*(\d{1,4})(?![\d\/])/g;
  function stackFractions(para, ink, log) {
    var txt = para.contents, m, found = [];
    FRAC.lastIndex = 0;
    while ((m = FRAC.exec(txt))) found.push({ at: m.index + m[1].length, len: m[0].length - m[1].length, num: m[2], den: m[3] });
    if (!found.length) return 0;
    var size = para.pointSize, maxH = 0;
    for (var k = found.length - 1; k >= 0; k--) {
      var f = found[k];
      try {
        var ip = para.characters[f.at].insertionPoints[0];
        para.characters.itemByRange(f.at, f.at + f.len - 1).remove();
        var tf = ip.textFrames.add({ geometricBounds: [0, 0, 12, 12] });
        tf.contents = f.num + '\r' + f.den;
        var ps = tf.parentStory.paragraphs.everyItem();
        ps.appliedFont = para.appliedFont; try { ps.fontStyle = para.fontStyle; } catch (e) {}
        ps.pointSize = size * 0.8; ps.leading = size * 0.86; ps.justification = Justification.CENTER_ALIGN; ps.fillColor = para.fillColor;
        ps.spaceBefore = 0; ps.spaceAfter = 0; ps.leftIndent = 0; ps.firstLineIndent = 0; ps.keepFirstLines = 1; ps.keepLastLines = 1;
        var p0 = tf.parentStory.paragraphs[0];
        p0.properties = { ruleBelow: true, ruleBelowColor: ink, ruleBelowLineWeight: 0.6, ruleBelowOffset: 0.9, ruleBelowWidth: RuleWidth.COLUMN_WIDTH };
        tf.textFramePreferences.insetSpacing = [0, 0.6, 0.3, 0.6];
        tf.textFramePreferences.autoSizingReferencePoint = AutoSizingReferenceEnum.CENTER_POINT;
        tf.textFramePreferences.autoSizingType = AutoSizingTypeEnum.HEIGHT_AND_WIDTH;
        tf.textFramePreferences.useNoLineBreaksForAutoSizing = true;
        var b = tf.geometricBounds, h = b[2] - b[0]; maxH = Math.max(maxH, h);
        // centre the fraction bar on the middle of the lower-case letters
        tf.anchoredObjectSettings.anchoredPosition = AnchorPosition.INLINE_POSITION;
        tf.anchoredObjectSettings.anchorYoffset = -(h / 2 - size * 0.25 / PT);
      } catch (e) { if (log) log.push('fraction ' + f.num + '/' + f.den + ': ' + e.message); }
    }
    // make room for the taller line
    try { if (para.leading != Leading.AUTO && para.leading < maxH * PT + 4) para.leading = maxH * PT + 4; } catch (e) {}
    return found.length;
  }

  // ---- drawn diagrams --------------------------------------------------------------------------------
  // redraw the manuscript's shapes as InDesign objects, scaled to fit, grouped, anchored inline at insertion point ip
  function drawDiagram(doc, story, at, d, maxW, maxH, opts, flow) {
    flow();
    var ip = story.insertionPoints[at], page = ip.parentTextFrames[0].parentPage;
    var sc = Math.min(1, maxW / Math.max(d.w, 1), maxH / Math.max(d.h, 1)), items = [], ox = 0, oy = 0;
    var ink = opts.ink, none = doc.swatches.itemByName('None');
    var fontPt = Math.max(7, (opts.textPt || 11) * Math.max(sc, 0.75));
    for (var k = 0; k < d.shapes.length; k++) {
      var s = d.shapes[k], x = ox + s.x * sc, y = oy + s.y * sc, w = Math.max(s.w * sc, 0.1), h = Math.max(s.h * sc, 0.1), it;
      var fill = s.fill ? opts.color(s.fill) : none, stroke = s.stroke ? ink : none;
      if (s.kind == 'line') {
        it = page.graphicLines.add({ strokeColor: ink, strokeWeight: 0.9 });
        var x1 = x, x2 = x + w, y1 = y, y2 = y + h; if (s.flipH) { x1 = x + w; x2 = x; } if (s.flipV) { y1 = y + h; y2 = y; }
        it.paths[0].entirePath = [[x1, y1], [x2, y2]];
        items.push(it); continue;
      }
      if (s.kind == 'ellipse') {
        items.push(page.ovals.add({ geometricBounds: [y, x, y + h, x + w], fillColor: fill, strokeColor: stroke, strokeWeight: s.stroke ? 0.9 : 0 }));
        if (!s.text) continue;
        it = page.textFrames.add({ geometricBounds: [y, x, y + h, x + w], fillColor: none, strokeWeight: 0 });
      } else if (s.text) {
        it = page.textFrames.add({ geometricBounds: [y, x, y + h, x + w], fillColor: s.kind == 'text' ? none : fill,
          strokeColor: s.kind == 'text' ? none : stroke, strokeWeight: s.kind == 'text' || !s.stroke ? 0 : 0.9 });
      } else {
        it = page.rectangles.add({ geometricBounds: [y, x, y + h, x + w], fillColor: fill, strokeColor: stroke, strokeWeight: s.stroke ? 0.9 : 0 });
      }
      if (s.kind == 'roundRect') try { it.topLeftCornerOption = it.topRightCornerOption = it.bottomLeftCornerOption = it.bottomRightCornerOption = CornerOptions.ROUNDED_CORNER;
        it.topLeftCornerRadius = it.topRightCornerRadius = it.bottomLeftCornerRadius = it.bottomRightCornerRadius = Math.min(3, h / 4); } catch (e) {}
      if (s.text && it.hasOwnProperty('parentStory')) {
        it.contents = s.text;
        var tp = it.parentStory.paragraphs.everyItem();
        tp.appliedFont = opts.font; try { tp.fontStyle = opts.fontStyle || 'Regular'; } catch (e) {}
        tp.pointSize = fontPt; tp.leading = fontPt * 1.15; tp.fillColor = ink; tp.justification = Justification.CENTER_ALIGN;
        tp.spaceBefore = 0; tp.spaceAfter = 0; tp.leftIndent = 0; tp.firstLineIndent = 0;
        it.textFramePreferences.insetSpacing = [0.5, 0.8, 0.5, 0.8];
        it.textFramePreferences.verticalJustification = VerticalJustification.CENTER_ALIGN;
        // labels must never be clipped: shrink the type until the text fits its shape
        var pt = fontPt; while (it.overflows && pt > 5.5) { pt -= 0.5; tp.pointSize = pt; tp.leading = pt * 1.12; }
      }
      items.push(it);
    }
    var obj = items.length > 1 ? page.groups.add(items) : items[0];
    var gb = obj.geometricBounds, gh = gb[2] - gb[0];
    obj.anchoredObjectSettings.insertAnchoredObject(ip, AnchorPosition.INLINE_POSITION);
    flow();
    try { var para = story.insertionPoints[at].paragraphs[0]; para.leading = gh * PT + 3; para.justification = Justification.CENTER_ALIGN; } catch (e) {}
    return { obj: obj, scale: sc };
  }

  // ---- teaching notes and rule pairs -----------------------------------------------------------------
  // label bold (via the label character style), the rest italic
  function italicBody(para, labelLen, italicName) {
    try { para.characters.itemByRange(labelLen, para.characters.length - 1).fontStyle = italicName || 'Italic'; } catch (e) {}
  }

  return { roman: roman, toArabic: toArabic, hang: hang, keepLines: keepLines, moveCutSections: moveCutSections,
    eqX: eqX, alignCalc: alignCalc, columnSumRows: columnSumRows, columnSumFormat: columnSumFormat,
    stackFractions: stackFractions, drawDiagram: drawDiagram, italicBody: italicBody, PT: PT };
})();
