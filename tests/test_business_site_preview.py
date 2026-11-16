import json
from zipfile import ZipFile

import pytest

from business.site_preview import EDITABLE, HERO, TRANSLATIONS, WebsiteExport, copy_matches


@pytest.fixture
def website(tmp_path):
    source = tmp_path / 'original.zip'
    text = 'export const translations = {\n' + ''.join(
        '  ' + lang + ': {\n' + ''.join(f"    {field}: '{lang} copy',\n" for field in EDITABLE)
        + '  },\n' for lang in ('en', 'fr', 'ta')
    ) + '};\n'
    heading = '<h1>Turn Your Vision Into{\' \'}<span className="gradient">Stunning Digital Content.</span></h1>'
    with ZipFile(source, 'w') as archive:
        archive.writestr(TRANSLATIONS, text)
        archive.writestr(HERO, heading)
        archive.writestr('server.ts', 'original-server')
    return WebsiteExport.load(source, 'en')


def test_preview_escapes_text_and_patches_only_supported_copy(website, tmp_path):
    draft = website.draft(json.dumps({'heroHeading': 'A <strong>bright</strong> idea'}))
    assert '&lt;strong&gt;bright&lt;/strong&gt;' in draft.preview_html()
    with pytest.raises(ValueError, match='separate ZIP'):
        draft.export_zip(website.path)
    destination = tmp_path / 'updated.zip'
    draft.export_zip(destination)
    with ZipFile(destination) as archive:
        translations = archive.read(TRANSLATIONS).decode()
        assert copy_matches(translations, 'en')['heroHeading'][2] == 'A <strong>bright</strong> idea'
        assert copy_matches(translations, 'fr')['heroHeading'][2] == 'fr copy'
        assert '{t.heroHeading}' in archive.read(HERO).decode()
        assert archive.read('server.ts') == b'original-server'
    with ZipFile(website.path) as archive:
        assert '{t.heroHeading}' not in archive.read(HERO).decode()


@pytest.mark.parametrize('response', ['{"price":"2"}', '{"heroHeading":7}', '{}', 'bad response'])
def test_invalid_or_empty_updates_are_refused(website, response):
    with pytest.raises(ValueError):
        website.draft(response)
