"""Writes samples/plants_chapter.docx: a short, generic science-workbook chapter used to test Galley.

It is written the way real manuscripts arrive: Word heading styles for some headings, typed markers
("Example 1", "Exercise 3.1", "Did you know?") for the boxes, typed question numbers, a bullet list,
a Word table and two pictures. Only the Python standard library is used.
"""
import os
import zipfile
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
PNG = os.path.join(HERE, 'src', 'png')

# (kind, text) - kinds: h1 h2 h3 p bullet table img caption
DOC = [
    ('p', 'Discover Science - Book 4'),
    ('h1', 'Chapter 3: How Plants Grow'),
    ('p', 'In this chapter you will learn:'),
    ('bullet', 'the main parts of a plant and what each part does'),
    ('bullet', 'what a seed needs before it can start to grow'),
    ('bullet', 'how plants make their own food using sunlight'),
    ('h2', '3.1 The parts of a plant'),
    ('p', 'Most plants you see around you have four main parts: roots, a stem, leaves and flowers. '
          'Each part has its own job, and the parts work together to keep the plant alive.'),
    ('img', 'plant_parts.png'),
    ('caption', 'Figure 3.1 The main parts of a flowering plant'),
    ('p', 'The roots hold the plant firmly in the soil. They also take in water and minerals. '
          'The stem carries water from the roots up to the leaves and holds the plant upright so that the leaves can reach the light.'),
    ('h3', 'What each part does'),
    ('table', [['Part', 'Job', 'Example'],
               ['Roots', 'Hold the plant in the soil and take in water', 'Carrot'],
               ['Stem', 'Carries water and holds the plant up', 'Sugar cane'],
               ['Leaves', 'Make food for the plant using sunlight', 'Spinach'],
               ['Flower', 'Makes seeds so new plants can grow', 'Hibiscus']]),
    ('p', 'Did you know? Some plants store food in their roots or stems. When you eat a carrot or a yam, you are eating food the plant saved for itself.'),
    ('p', 'Example 1: Matching a part to its job'),
    ('p', 'Question: Which part of a plant takes in water from the soil?'),
    ('p', 'Think: Water is in the soil. Only one part of the plant lives under the ground.'),
    ('p', 'Answer: The roots take in water from the soil.'),
    ('p', 'Exercise 3.1'),
    ('p', 'Choose the correct answer.'),
    ('p', '1. Which part of a plant makes food? (a) root (b) stem (c) leaf (d) flower'),
    ('p', '2. Which part of a plant holds it upright? (a) stem (b) seed (c) petal (d) root'),
    ('p', '3. Which part makes seeds? (a) leaf (b) flower (c) root (d) stem'),
    ('p', 'Fill in the blanks.'),
    ('p', '4. The ________ carry water from the soil into the plant.'),
    ('p', '5. Leaves need ________ to make food.'),
    ('h2', '3.2 From seed to plant'),
    ('p', 'A seed is a tiny baby plant with its own packed lunch. Inside the seed coat there is a young plant and a store of food. '
          'When the conditions are right, the seed swells, splits its coat and begins to grow. This is called germination.'),
    ('p', 'A seed needs three things before it can germinate:'),
    ('bullet', 'water, to soften the seed coat and wake the seed up'),
    ('bullet', 'warmth, because most seeds will not grow in the cold'),
    ('bullet', 'air, because the young plant needs oxygen'),
    ('p', 'Note: A seed does not need light to germinate. It starts growing in the dark soil using its own food store. '
          'Once its first leaves appear above the ground, it needs light to make more food.'),
    ('p', 'Example 2: Planning a fair test'),
    ('p', 'Ada wants to find out if bean seeds need water to germinate. She puts five seeds on wet cotton wool in one dish and five seeds on dry cotton wool in another dish.'),
    ('p', 'She keeps both dishes in the same warm room, so the only thing that is different is the water.'),
    ('p', 'After four days the seeds on the wet cotton wool have started to grow. The seeds on the dry cotton wool have not changed.'),
    ('p', 'Conclusion: Bean seeds need water to germinate.'),
    ('h3', 'Growing up'),
    ('p', 'After germination, the root grows down and the shoot grows up towards the light. '
          'The first leaves open and the young plant, called a seedling, starts to make its own food. '
          'Over weeks and months the seedling grows into an adult plant that can make flowers and seeds of its own, and the life cycle begins again.'),
    ('p', 'Exercise 3.2'),
    ('p', 'Answer these questions in full sentences.'),
    ('p', '1. What three things does a seed need to germinate?'),
    ('p', '2. Why did Ada keep both dishes in the same room?'),
    ('p', '3. What is a seedling?'),
    ('p', '4. Put these stages in order: seedling, seed, adult plant, germination.'),
    ('h2', '3.3 Plants and water'),
    ('p', 'Plants take in water through their roots and lose water through tiny holes in their leaves. '
          'The water that leaves the plant goes into the air as water vapour. It becomes part of the water cycle, '
          'which moves water between the land, the sea and the sky.'),
    ('img', 'water_cycle.png'),
    ('caption', 'Figure 3.2 The water cycle'),
    ('p', 'Remember: Plants, animals and people all depend on the water cycle. Clean water today means healthy plants tomorrow.'),
    ('p', 'Activity: Watch water move'),
    ('p', 'You need: a small potted plant, a clear plastic bag and a piece of string.'),
    ('p', 'Cover one leafy stem with the plastic bag and tie it loosely. Leave the plant in a sunny place for one day.'),
    ('p', 'Look at the inside of the bag. What do you see? Where do you think the water came from?'),
    ('p', 'Exercise 3.3'),
    ('p', 'Write true or false.'),
    ('p', '1. Plants lose water through their leaves. ________'),
    ('p', '2. Water vapour is a kind of solid. ________'),
    ('p', '3. Rain is part of the water cycle. ________'),
    ('p', '4. Plants do not need water on cloudy days. ________'),
    ('p', 'Think and write.'),
    ('p', '5. Explain why a plant left in a dark cupboard for two weeks will start to look weak and pale.'),
    ('h2', 'Chapter summary'),
    ('bullet', 'Roots, stems, leaves and flowers each have a job.'),
    ('bullet', 'Seeds need water, warmth and air to germinate.'),
    ('bullet', 'Leaves use sunlight to make food for the plant.'),
    ('bullet', 'Plants are part of the water cycle.'),
]

STYLE = {'h1': 'Heading1', 'h2': 'Heading2', 'h3': 'Heading3', 'caption': 'Caption', 'bullet': 'ListParagraph'}


def para(kind, text):
    ppr = ''
    if kind in STYLE:
        ppr = '<w:pStyle w:val="%s"/>' % STYLE[kind]
    if kind == 'bullet':
        ppr += '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>'
    return '<w:p><w:pPr>%s</w:pPr><w:r><w:t xml:space="preserve">%s</w:t></w:r></w:p>' % (ppr, escape(text))


def table(rows):
    out = ['<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="0" w:type="auto"/></w:tblPr>']
    for r in rows:
        out.append('<w:tr>' + ''.join('<w:tc><w:p><w:r><w:t>%s</w:t></w:r></w:p></w:tc>' % escape(c) for c in r) + '</w:tr>')
    out.append('</w:tbl>')
    return ''.join(out)


def image(rid, n, name, cx, cy):
    emu_w, emu_h = cx * 9525, cy * 9525
    return ('<w:p><w:r><w:drawing><wp:inline><wp:extent cx="%d" cy="%d"/><wp:docPr id="%d" name="%s"/>'
            '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:nvPicPr><pic:cNvPr id="%d" name="%s"/><pic:cNvPicPr/></pic:nvPicPr>'
            '<pic:blipFill><a:blip r:embed="%s"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            '<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="%d" cy="%d"/></a:xfrm><a:prstGeom prst="rect"/></pic:spPr></pic:pic></a:graphicData></a:graphic>'
            '</wp:inline></w:drawing></w:r></w:p>') % (emu_w, emu_h, n, name, n, name, rid, emu_w, emu_h)


def main(out=os.path.join(HERE, 'plants_chapter.docx')):
    body, rels, media = [], [], []
    n = 0
    for kind, val in DOC:
        if kind == 'table':
            body.append(table(val))
        elif kind == 'img':
            n += 1
            rid = 'rIdImg%d' % n
            rels.append('<Relationship Id="%s" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/%s"/>' % (rid, val))
            media.append(val)
            body.append(image(rid, n, val, 500, 380 if 'parts' in val else 310))
        else:
            body.append(para(kind, val))
    ns = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
          'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"')
    document = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document %s><w:body>%s<w:sectPr/></w:body></w:document>' % (ns, ''.join(body))
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
              + ''.join('<w:style w:type="paragraph" w:styleId="%s"><w:name w:val="%s"/></w:style>' % (sid, name) for sid, name in
                        [('Normal', 'Normal'), ('Heading1', 'heading 1'), ('Heading2', 'heading 2'), ('Heading3', 'heading 3'),
                         ('Caption', 'caption'), ('ListParagraph', 'List Paragraph')])
              + '<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/></w:style></w:styles>')
    numbering = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                 '<w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/><w:lvlText w:val="&#8226;"/></w:lvl></w:abstractNum>'
                 '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num></w:numbering>')
    ctypes = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/>'
              '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
              '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
              '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/></Types>')
    root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    doc_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                '<Relationship Id="rIdNum" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'
                + ''.join(rels) + '</Relationships>')
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', ctypes)
        z.writestr('_rels/.rels', root_rels)
        z.writestr('word/document.xml', document)
        z.writestr('word/styles.xml', styles)
        z.writestr('word/numbering.xml', numbering)
        z.writestr('word/_rels/document.xml.rels', doc_rels)
        for m in media:
            z.write(os.path.join(PNG, m), 'word/media/' + m)
    print(out)


if __name__ == '__main__':
    main()
