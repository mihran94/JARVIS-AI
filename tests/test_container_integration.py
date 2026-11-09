"""Explicit opt-in acceptance tests; never installs Docker or downloads an image."""
import os
import pytest
from developer_studio.runner import run_python, approval_digest

pytestmark = pytest.mark.skipif(os.environ.get('JARVIS_CONTAINER_TESTS') != '1',
                                reason='Requires explicitly enabled local Docker acceptance testing')

@pytest.mark.parametrize('source,expected',[
    ('print(6 * 7)', '42'),
    ('import socket\ns=socket.socket()\ntry:\n s.connect(("1.1.1.1",443))\nexcept OSError:\n print("network blocked")\nelse:\n raise AssertionError("network available")', 'network blocked'),
    ('from pathlib import Path\ntry:\n Path("/should-not-write").write_text("test")\nexcept OSError:\n print("root write blocked")\nelse:\n raise AssertionError("root writable")','root write blocked'),
])
def test_local_container_acceptance(source,expected):
    image=os.environ['JARVIS_TEST_IMAGE_ID']
    result=run_python(source,image,approval_digest(source,image))
    assert result.status=='completed' and expected in result.output
