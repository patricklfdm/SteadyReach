"""Clickable DOCX contents/bookmarks and table captions; no page-number guesses."""
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


def finish(doc, chinese=False, contents=True):
    headings = [p for p in doc.paragraphs if p.style.name == 'Heading 1']
    for i, p in enumerate(headings):
        start = OxmlElement('w:bookmarkStart'); start.set(qn('w:id'), str(i+100)); start.set(qn('w:name'), 'section_'+str(i))
        end = OxmlElement('w:bookmarkEnd'); end.set(qn('w:id'), str(i+100))
        p._p.insert(0, start); p._p.append(end)
    for i, table in enumerate(doc.tables, 1):
        p = doc.add_paragraph(('表 ' if chinese else 'Table ')+str(i), 'Caption')
        p.paragraph_format.keep_with_next = True; table._tbl.addprevious(p._p)
    if not contents or not headings: return doc
    first_break = next((p for p in doc.paragraphs if p.paragraph_format.page_break_before or p._p.xpath('.//w:br[@w:type="page"]')), None)
    if first_break is None: return doc
    title=doc.add_paragraph('目录' if chinese else 'Contents', 'Title');title.paragraph_format.page_break_before=True
    nodes = [title._p]
    for i, heading in enumerate(headings):
        p = doc.add_paragraph(); link = OxmlElement('w:hyperlink'); link.set(qn('w:anchor'), 'section_'+str(i)); link.set(qn('w:history'), '1')
        run = OxmlElement('w:r'); props = OxmlElement('w:rPr'); style = OxmlElement('w:rStyle'); style.set(qn('w:val'), 'Hyperlink'); props.append(style); run.append(props)
        text = OxmlElement('w:t'); text.text = heading.text; run.append(text); link.append(run); p._p.append(link); nodes.append(p._p)
    for node in nodes: first_break._p.addprevious(node)
    return doc
