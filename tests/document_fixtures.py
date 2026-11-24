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


def make_scanned_pdf(path, image_path, *, width=480, height=155):
    """Write a PDF that holds only a picture of a page.

    This is what a scanner produces: the page is an image and there is
    no text layer at all, so a document reader finds nothing in it.

    The picture is written into the PDF as raw samples, because a PDF
    cannot hold PNG data: PNG filters every row and a PDF does not
    understand that. The PDF is written by hand so that the fixture
    needs no extra package.
    """
    import struct
    import zlib

    with open(image_path, 'rb') as handle:
        raw = handle.read()
    if raw[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('That is not a PNG file.')
    image_width, image_height = struct.unpack('>II', raw[16:24])
    colour_type = raw[25]
    if colour_type != 2:
        raise ValueError('Only a true-colour PNG can go in a PDF here.')

    position = 8
    data = b''
    while position < len(raw):
        length = struct.unpack('>I', raw[position:position + 4])[0]
        kind = raw[position + 4:position + 8]
        payload = raw[position + 8:position + 8 + length]
        if kind == b'IDAT':
            data += payload
        position += 12 + length
    if not data:
        raise ValueError('That PNG has no image data.')

    # The PNG's own filters have to come off, because a PDF holds plain
    # samples. Every row is unfiltered here, which is what a picture
    # written by the document fixture is.
    samples = zlib.decompress(data)
    stride = image_width * 3
    rows = []
    previous = bytearray(stride)
    offset = 0
    for _ in range(image_height):
        filter_type = samples[offset]
        offset += 1
        row = bytearray(samples[offset:offset + stride])
        offset += stride
        if filter_type == 0:
            pass
        elif filter_type == 1:
            for index in range(3, stride):
                row[index] = (row[index] + row[index - 3]) & 0xff
        elif filter_type == 2:
            for index in range(stride):
                row[index] = (row[index] + previous[index]) & 0xff
        elif filter_type == 3:
            for index in range(stride):
                left = row[index - 3] if index >= 3 else 0
                row[index] = (row[index] + ((left + previous[index]) >> 1)) & 0xff
        elif filter_type == 4:
            for index in range(stride):
                left = row[index - 3] if index >= 3 else 0
                above = previous[index]
                upper_left = previous[index - 3] if index >= 3 else 0
                estimate = left + above - upper_left
                distance_left = abs(estimate - left)
                distance_above = abs(estimate - above)
                distance_upper = abs(estimate - upper_left)
                if distance_left <= distance_above and distance_left <= distance_upper:
                    predictor = left
                elif distance_above <= distance_upper:
                    predictor = above
                else:
                    predictor = upper_left
                row[index] = (row[index] + predictor) & 0xff
        else:
            raise ValueError('That PNG uses a filter this fixture does not read.')
        previous = row
        rows.append(bytes(row))

    # PNG is top-down and RGB; the PDF wants the same order, so the rows
    # are simply joined.
    plain = b''.join(rows)
    compressed = zlib.compress(plain, 6)

    objects = []
    objects.append(b'<< /Type /Catalog /Pages 2 0 R >>')
    objects.append(b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>')
    objects.append(
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources '
        b'<< /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>')
    objects.append(
        b'<< /Type /XObject /Subtype /Image /Width ' + str(image_width).encode()
        + b' /Height ' + str(image_height).encode()
        + b' /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length '
        + str(len(compressed)).encode() + b' >>\nstream\n' + compressed
        + b'\nendstream')
    content = (f'q {width} 0 0 {height} 60 500 cm /Im0 Do Q').encode('ascii')
    objects.append(b'<< /Length ' + str(len(content)).encode() + b' >>\nstream\n'
                   + content + b'\nendstream')

    out = bytearray(b'%PDF-1.4\n')
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += str(number).encode() + b' 0 obj\n' + body + b'\nendobj\n'
    start = len(out)
    out += b'xref\n0 ' + str(len(objects) + 1).encode() + b'\n'
    out += b'0000000000 65535 f \n'
    for offset in offsets:
        out += f'{offset:010d} 00000 n \n'.encode('ascii')
    out += (b'trailer\n<< /Size ' + str(len(objects) + 1).encode()
            + b' /Root 1 0 R >>\nstartxref\n' + str(start).encode() + b'\n%%EOF\n')
    with open(path, 'wb') as handle:
        handle.write(bytes(out))
    return path
