"""Writes samples/maths_chapter.docx: a generic primary maths unit that exercises Galley's house rules.

It is built the way real maths manuscripts arrive, which is what breaks naive readers:
- list numbers come from Word's automatic numbering (numbering.xml), NOT from the text: 1. 2. 3., (a) (b),
  (i) (ii); one example list is numbered in Roman numerals; an exercise restarts its numbering;
- diagrams are drawn Word shapes: a DrawingML group (ovals joined by lines to a box) with its VML fallback,
  a legacy VML-only shape, and a row of empty answer boxes inside a question;
- a Word equation fraction (OMML), "=" continuation lines, an "Or ..." line, a Th/H/T/U column sum,
  a Teaching Guide note and rule/example pairs.
Only the Python standard library is used.
"""
import os
import zipfile
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
EMU = 36000  # per mm

NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
      'xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" '
      'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
      'xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office" '
      'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" mc:Ignorable="wps wpg"')


def run(t):
    return '<w:r><w:t xml:space="preserve">%s</w:t></w:r>' % escape(t)


def p(text='', style=None, num=None, extra=''):
    ppr = ''
    if style:
        ppr += '<w:pStyle w:val="%s"/>' % style
    if num:
        ppr += '<w:numPr><w:ilvl w:val="%d"/><w:numId w:val="%d"/></w:numPr>' % (num[1], num[0])
    return '<w:p><w:pPr>%s</w:pPr>%s%s</w:p>' % (ppr, run(text) if text else '', extra)


def omml_frac(num, den):
    return ('<m:oMath><m:f><m:num><m:r><m:t>%s</m:t></m:r></m:num><m:den><m:r><m:t>%s</m:t></m:r></m:den></m:f></m:oMath>' % (num, den))


_id = [100]


def wsp(prst, x, y, w, h, text='', fill='FFFFFF', line=True):
    _id[0] += 1
    sp = ('<a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm><a:prstGeom prst="%s"><a:avLst/></a:prstGeom>'
          % (x * EMU, y * EMU, w * EMU, h * EMU, prst))
    sp += '<a:solidFill><a:srgbClr val="%s"/></a:solidFill>' % fill if fill else '<a:noFill/>'
    sp += '<a:ln w="9525"><a:solidFill><a:srgbClr val="000000"/></a:solidFill></a:ln>' if line else '<a:ln><a:noFill/></a:ln>'
    tx = ('<wps:txbx><w:txbxContent>%s</w:txbxContent></wps:txbx>' % p(text)) if text else ''
    return '<wps:wsp><wps:cNvPr id="%d" name="Shape %d"/><wps:cNvSpPr/><wps:spPr>%s</wps:spPr>%s<wps:bodyPr/></wps:wsp>' % (_id[0], _id[0], sp, tx)


def group_drawing(w, h, shapes, vml_fallback=''):
    _id[0] += 1
    grp = ('<wpg:wgp><wpg:cNvGrpSpPr/><wpg:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="%d" cy="%d"/>'
           '<a:chOff x="0" y="0"/><a:chExt cx="%d" cy="%d"/></a:xfrm></wpg:grpSpPr>%s</wpg:wgp>') % (w * EMU, h * EMU, w * EMU, h * EMU, ''.join(shapes))
    drawing = ('<w:drawing><wp:inline><wp:extent cx="%d" cy="%d"/><wp:docPr id="%d" name="Group %d"/><a:graphic>'
               '<a:graphicData uri="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup">%s</a:graphicData></a:graphic></wp:inline></w:drawing>'
               ) % (w * EMU, h * EMU, _id[0], _id[0], grp)
    return ('<w:r><mc:AlternateContent><mc:Choice Requires="wpg">%s</mc:Choice><mc:Fallback>%s</mc:Fallback></mc:AlternateContent></w:r>'
            % (drawing, vml_fallback or '<w:pict><v:rect style="width:10pt;height:10pt"/></w:pict>'))


def vml_only(xml):
    return '<w:r><w:pict>%s</w:pict></w:r>' % xml


# a tree diagram: two numbers in ovals joined by lines to the box with their total
TREE = group_drawing(70, 40, [
    wsp('ellipse', 0, 0, 18, 12, '12'), wsp('ellipse', 52, 0, 18, 12, '8'),
    wsp('line', 9, 12, 26, 16, fill=None), wsp('line', 35, 12, 26, 16, fill=None),
    wsp('rect', 25, 28, 20, 12, '20')])
# the same pair, mirrored line (flipH), so both directions are tested
TREE2 = group_drawing(70, 40, [
    wsp('ellipse', 0, 0, 18, 12, '15'), wsp('ellipse', 52, 0, 18, 12, '6'),
    wsp('line', 9, 12, 26, 16, fill=None), wsp('line', 35, 12, 26, 16, fill=None),
    wsp('rect', 25, 28, 20, 12, '')])
TREE2 = TREE2.replace('<a:xfrm><a:off x="%d" y="%d"/>' % (35 * EMU, 12 * EMU), '<a:xfrm flipH="1"><a:off x="%d" y="%d"/>' % (35 * EMU, 12 * EMU))
TREE = TREE.replace('<a:xfrm><a:off x="%d" y="%d"/>' % (35 * EMU, 12 * EMU), '<a:xfrm flipH="1"><a:off x="%d" y="%d"/>' % (35 * EMU, 12 * EMU))
# three empty answer boxes in a row
BOXES = group_drawing(60, 12, [wsp('rect', 0, 0, 16, 12), wsp('rect', 22, 0, 16, 12), wsp('rect', 44, 0, 16, 12)])
# a legacy VML number machine: a box with text and an arrow line into it
MACHINE = vml_only('<v:group style="width:150pt;height:50pt" coordsize="1500,500">'
                   '<v:line from="0,250" to="400,250" strokecolor="#000000"/>'
                   '<v:rect style="position:absolute;left:400;top:50;width:700;height:400" strokecolor="#000000" fillcolor="#FFF2CC">'
                   '<v:textbox><w:txbxContent>' + p('Machine: add 5') + '</w:txbxContent></v:textbox></v:rect>'
                   '<v:line from="1100,250" to="1500,250" strokecolor="#000000"/></v:group>')

BODY = [
    p('Bright Steps Mathematics, Book 4'),
    p('Theme 1: Numbers and Numeration', 'Heading1'),
    p('Unit 2: Place Value and Comparing Numbers', 'Heading1'),
    p('In this unit you will learn:'),
    p('the value of each digit in a four-digit number', num=(4, 0)),
    p('how to compare and order numbers', num=(4, 0)),
    p('how two numbers join to make a total', num=(4, 0)),
    p('2.1 Place value', 'Heading2'),
    p('Every digit in a number has a value that depends on where it sits. In 4 528 the digit 4 sits in the thousands '
      'place, so it stands for four thousand. The digit 5 sits in the hundreds place and stands for five hundred. '
      'Reading numbers this way helps us to add, subtract and compare them without mistakes.'),
    p('A place value chart shows the columns clearly. We write Th for thousands, H for hundreds, T for tens and U for '
      'units. When a number has no tens, we still write a zero in the tens column so that every digit stays in its place.'),
    p('Example 1: Place value of digits'),
    p('The 4 in 4 528 stands for 4 thousands.', num=(3, 0)),
    p('The 5 in 4 528 stands for 5 hundreds.', num=(3, 0)),
    p('The 2 in 4 528 stands for 2 tens.', num=(3, 0)),
    p('The 8 in 4 528 stands for 8 units.', num=(3, 0)),
    p('Example 2: Adding in columns'),
    p('Th H T U'),
    p('2 4 5 6'),
    p('+ 1 3 2 1'),
    p('3 7 7 7'),
    p('Teaching Guide: Let pupils say each number aloud before they write it in the chart.'),
    p('2.2 Comparing numbers', 'Heading2'),
    p('We use these symbols to compare numbers:'),
    p('< means "is less than".', num=(5, 0)),
    p('> means "is greater than".', num=(5, 0)),
    p('= means "is equal to".', num=(5, 0)),
    p('Example 3: Sharing equally'),
    p('12 sweets shared among 4 children = 12 ÷ 4'),
    p('= 3 sweets each'),
    p('Or 4 × 3 = 12, so each child gets 3 sweets.'),
    p('Ada ate 3/4 of the cake and Bola ate 1/8 of it.'),
    p('', extra=run('Half of the class is ') + omml_frac('1', '2') + run(' of the pupils.')),
    p('Addition Rule: When a smaller numeral comes after a bigger one, add them.'),
    p('Example: VI = 5 + 1 = 6'),
    p('Subtraction Rule: When a smaller numeral comes before a bigger one, subtract it.'),
    p('Example: IV = 5 − 1 = 4'),
    p('2.3 Quantitative reasoning', 'Heading2'),
    p('Look at how the two numbers join to make the number in the box:'),
    p('', extra=TREE),
    p('A number machine changes every number that goes into it:'),
    p('', extra=MACHINE),
    p('Exercise 2.1'),
    p('Write the value of the underlined digit.'),
    p('3 742', num=(1, 0)),
    p('6 105', num=(1, 0)),
    p('Write the numbers in figures:', num=(1, 0)),
    p('four thousand and six', num=(1, 1)),
    p('two thousand, three hundred and ten', num=(1, 1)),
    p('Fill in the missing number in each box:', num=(1, 0)),
    p('', extra=BOXES),
    p('Work out:', num=(1, 0)),
    p('245 + 130 = 300 + 70 + 5', num=(1, 1)),
    p('= 375'),
    p('Which numbers join to make the box below?', num=(1, 0)),
    p('', extra=TREE2),
    p('Exercise 2.2'),
    p('Use <, > or = to compare.'),
    p('4 506 ___ 4 650', num=(2, 0)),
    p('7 001 ___ 7 010', num=(2, 0)),
    p('3 333 ___ 3 333', num=(2, 0)),
    p('Order from the smallest:', num=(2, 0)),
    p('2 341, 2 314, 2 431', num=(2, 1)),
    p('9 090, 9 009, 9 900', num=(2, 1)),
    p('Explain why 5 000 is greater than 4 999.', num=(2, 0)),
]

NUMBERING = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
             # 0: exercises: 1.  (a)  (i)
             '<w:abstractNum w:abstractNumId="0">'
             '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/></w:lvl>'
             '<w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="lowerLetter"/><w:lvlText w:val="(%2)"/></w:lvl>'
             '<w:lvl w:ilvl="2"><w:start w:val="1"/><w:numFmt w:val="lowerRoman"/><w:lvlText w:val="(%3)"/></w:lvl></w:abstractNum>'
             # 1: an example list in Roman numerals
             '<w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="lowerRoman"/><w:lvlText w:val="(%1)"/></w:lvl></w:abstractNum>'
             # 2: bullets
             '<w:abstractNum w:abstractNumId="2"><w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/><w:lvlText w:val="•"/></w:lvl></w:abstractNum>'
             '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
             '<w:num w:numId="2"><w:abstractNumId w:val="0"/><w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride></w:num>'
             '<w:num w:numId="3"><w:abstractNumId w:val="1"/></w:num>'
             '<w:num w:numId="4"><w:abstractNumId w:val="2"/></w:num>'
             '<w:num w:numId="5"><w:abstractNumId w:val="0"/></w:num>'
             '</w:numbering>')


def main(out=os.path.join(HERE, 'maths_chapter.docx')):
    document = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document %s><w:body>%s<w:sectPr/></w:body></w:document>' % (NS, ''.join(BODY))
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
              + ''.join('<w:style w:type="paragraph" w:styleId="%s"><w:name w:val="%s"/></w:style>' % (sid, name)
                        for sid, name in [('Normal', 'Normal'), ('Heading1', 'heading 1'), ('Heading2', 'heading 2'), ('ListParagraph', 'List Paragraph')])
              + '</w:styles>')
    ctypes = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
              '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
              '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
              '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    doc_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rS" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                '<Relationship Id="rN" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/></Relationships>')
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', ctypes)
        z.writestr('_rels/.rels', rels)
        z.writestr('word/document.xml', document)
        z.writestr('word/styles.xml', styles)
        z.writestr('word/numbering.xml', NUMBERING)
        z.writestr('word/_rels/document.xml.rels', doc_rels)
    print(out)


if __name__ == '__main__':
    main()
