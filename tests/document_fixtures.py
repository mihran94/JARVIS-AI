"""Builders for real document files, used by the document tests.

A test that reads a document needs a document that is really there, not
a mock of one. These write a small but genuine PDF and a small but
genuine DOCX, so the reading code is exercised against the real format.

They need no library beyond the standard library, so the tests run
wherever the application runs.
"""
import zipfile


def make_pdf(path, lines=('Hello from the PDF', 'The second line')):
    """Write a small, real PDF with the given text lines."""
    content = ['BT /F1 12 Tf 20 160 Td']
    for index, line in enumerate(lines):
        if index:
            content.append('0 -20 Td')
        content.append('(' + line.replace('(', '').replace(')', '') + ') Tj')
    content.append('ET')
    stream = '\n'.join(content).encode('latin-1')

    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] '
        b'/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
        b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    out = bytearray(b'%PDF-1.4\n')
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += str(number).encode() + b' 0 obj\n' + body + b'\nendobj\n'
    start = len(out)
    out += b'xref\n0 ' + str(len(objects) + 1).encode() + b'\n'
    out += b'0000000000 65535 f \n'
    for offset in offsets:
        out += f'{offset:010d} 00000 n \n'.encode()
    out += b'trailer\n<< /Size ' + str(len(objects) + 1).encode() + b' /Root 1 0 R >>\n'
    out += b'startxref\n' + str(start).encode() + b'\n%%EOF\n'
    path.write_bytes(bytes(out))
    return path


def make_docx(path, paragraphs=('First paragraph', 'Second paragraph'),
              table=(('Name', 'Value'), ('alpha', '1'), ('beta', '2'))):
    """Write a small, real DOCX with paragraphs and a table."""
    body = []
    for paragraph in paragraphs:
        body.append('<w:p><w:r><w:t>' + paragraph + '</w:t></w:r></w:p>')
    rows = ''.join(
        '<w:tr>' + ''.join('<w:tc><w:p><w:r><w:t>' + cell + '</w:t></w:r></w:p></w:tc>'
                            for cell in row) + '</w:tr>'
        for row in table)
    body.append('<w:tbl>' + rows + '</w:tbl>')
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>' + ''.join(body) + '</w:body></w:document>')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('word/document.xml', document)
    return path
