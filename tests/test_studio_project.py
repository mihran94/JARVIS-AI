import pytest

from quantum_core.studio_project import STUDIO_ID, STUDIO_URL, studio_update_prompt, validate_studio_url


def test_imported_link_and_canonical_build_address():
    canonical = f'https://aistudio.google.com/apps/{STUDIO_ID}?showPreview=true'
    assert validate_studio_url(STUDIO_URL) == STUDIO_URL
    assert validate_studio_url(canonical) == canonical
    text = studio_update_prompt('Make the pricing cards easier to read on mobile.', canonical)
    assert 'Update AI Creative Studio' in text
    assert canonical in text
    assert 'src/components' in text
    assert 'pricing cards easier to read' in text


@pytest.mark.parametrize('url', [
    'http://ai.studio/apps/project',
    'https://ai.studio.example.com/apps/project',
    'https://user@ai.studio/apps/project',
    'https://ai.studio/apps',
    'https://ai.studio/apps/../project',
])
def test_only_google_ai_studio_app_links_are_accepted(url):
    with pytest.raises(ValueError, match='Build project link'):
        validate_studio_url(url)


def test_custom_project_has_its_own_context():
    url = 'https://aistudio.google.com/apps/drive/custom-project'
    prompt = studio_update_prompt('Fix the contact page', url)
    assert 'the linked website' in prompt
    assert url in prompt
    assert 'Express' not in prompt
    with pytest.raises(ValueError, match='update brief'):
        studio_update_prompt('  ', url)
