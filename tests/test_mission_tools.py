"""The mission tools: what JARVIS may use, and what each one refuses.

WHAT IS COVERED
    * The catalogue contains the real capabilities and nothing else.
    * A tool that only reads is marked read-only, and a tool that
      changes something is not.
    * The arguments are checked against the schema: an argument the tool
      does not take is refused, and so is one of the wrong type.
    * The file tools stay inside the mission folder, and a link is
      refused.
    * The calculation tool does arithmetic and nothing else.
    * The memory tools work against the real memory service.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest

from core.mission_tools import (
    ToolError, build_registry,
)
from memory.memory_service import MemoryService


@pytest.fixture
def root(tmp_path):
    (tmp_path / 'notes.txt').write_text('The launch is on Friday.\n', encoding='utf-8')
    (tmp_path / 'sub').mkdir()
    (tmp_path / 'sub' / 'inner.txt').write_text('Inner note.\n', encoding='utf-8')
    return tmp_path


@pytest.fixture
def memory(tmp_path):
    return MemoryService(tmp_path / 'history.sqlite3')


@pytest.fixture
def registry(root, memory):
    return build_registry(root=root, memory=memory)


# ── the catalogue ──────────────────────────────────────────────────────────

def test_the_catalogue_has_the_real_capabilities(registry):
    assert set(registry.names()) == {
        'current_time', 'system_status', 'evaluate_expression', 'research_fetch',
        'launch_app', 'browser_draft', 'type_notepad', 'export_text', 'list_directory', 'read_text_file',
        'memory_search', 'memory_remember',
    }


def test_only_the_tools_that_change_something_need_approval(registry):
    assert set(registry.read_only_names()) == {
        'current_time', 'system_status', 'evaluate_expression', 'research_fetch',
        'list_directory', 'read_text_file', 'memory_search',
    }
    assert registry.get('launch_app').read_only is False
    assert registry.get('memory_remember').read_only is False


def test_a_tool_that_is_not_registered_does_not_exist(registry):
    assert registry.get('run_shell') is None
    assert registry.get('delete_everything') is None
    assert registry.get(42) is None


def test_the_launch_tool_only_offers_the_allowlisted_applications(registry):
    schema = registry.get('launch_app').parameters
    assert schema['properties']['app']['enum'] == ['Notepad', 'Calculator']


def test_the_catalogue_describes_itself_for_the_model(registry):
    described = registry.describe()
    assert 'system_status' in described
    assert 'changes something and needs approval' in described
    assert 'launch_app' in described


# ── the arguments ──────────────────────────────────────────────────────────

def test_an_argument_the_tool_does_not_take_is_refused(registry):
    tool = registry.get('current_time')
    with pytest.raises(ToolError) as error:
        registry.check_arguments(tool, {'path': 'C:/Windows'})
    assert 'does not take' in str(error.value)


def test_an_argument_of_the_wrong_type_is_refused(registry):
    tool = registry.get('evaluate_expression')
    with pytest.raises(ToolError) as error:
        registry.check_arguments(tool, {'expression': 12})
    assert 'must be text' in str(error.value)


def test_a_missing_required_argument_is_refused(registry):
    tool = registry.get('evaluate_expression')
    with pytest.raises(ToolError) as error:
        registry.check_arguments(tool, {})
    assert 'needs the argument' in str(error.value)


def test_an_argument_outside_the_allowed_values_is_refused(registry):
    tool = registry.get('launch_app')
    with pytest.raises(ToolError) as error:
        registry.check_arguments(tool, {'app': 'cmd.exe'})
    assert 'must be one of' in str(error.value)


def test_good_arguments_are_accepted(registry):
    tool = registry.get('read_text_file')
    assert registry.check_arguments(tool, {'path': 'notes.txt'}) == {'path': 'notes.txt'}


# ── the file tools ─────────────────────────────────────────────────────────

def test_a_file_inside_the_mission_folder_is_read(registry):
    tool = registry.get('read_text_file')
    assert 'launch is on Friday' in tool.run({'path': 'notes.txt'})


def test_a_path_outside_the_mission_folder_is_refused(registry, tmp_path):
    outside = tmp_path.parent / 'outside.txt'
    outside.write_text('Not yours.\n', encoding='utf-8')
    tool = registry.get('read_text_file')
    with pytest.raises(ToolError) as error:
        tool.run({'path': str(outside)})
    assert 'outside the mission folder' in str(error.value)


def test_a_link_is_refused(registry, root):
    link = root / 'link.txt'
    try:
        link.symlink_to(root / 'notes.txt')
    except (OSError, NotImplementedError):
        pytest.skip('This system does not allow links.')
    tool = registry.get('read_text_file')
    with pytest.raises(ToolError) as error:
        tool.run({'path': 'link.txt'})
    assert 'link' in str(error.value).lower()


def test_the_folder_listing_names_what_is_in_it(registry):
    tool = registry.get('list_directory')
    listing = tool.run({})
    assert 'notes.txt' in listing
    assert 'sub' in listing


# ── the calculation ────────────────────────────────────────────────────────

def test_the_calculation_is_done(registry):
    tool = registry.get('evaluate_expression')
    assert tool.run({'expression': '(120 * 3) / 4'}) == '(120 * 3) / 4 = 90.0'


def test_the_calculation_refuses_anything_that_is_not_arithmetic(registry):
    tool = registry.get('evaluate_expression')
    for expression in ('__import__("os")', 'open("x")', 'name', '"text"'):
        with pytest.raises(ToolError):
            tool.run({'expression': expression})


def test_a_huge_power_is_refused(registry):
    tool = registry.get('evaluate_expression')
    with pytest.raises(ToolError) as error:
        tool.run({'expression': '9 ** 9 ** 9'})
    assert 'too large' in str(error.value)


def test_a_division_by_zero_is_refused(registry):
    tool = registry.get('evaluate_expression')
    with pytest.raises(ToolError) as error:
        tool.run({'expression': '1 / 0'})
    assert 'no answer' in str(error.value)


# ── the memory tools ───────────────────────────────────────────────────────

def test_the_memory_tools_work_against_the_real_service(registry, memory):
    remember = registry.get('memory_remember')
    saved = remember.run({'title': 'Launch', 'body': 'The launch is on Friday.',
                          'tags': ['Work']})
    assert 'Launch' in saved

    search = registry.get('memory_search')
    found = search.run({'query': 'launch'})
    assert 'Friday' in found


def test_a_memory_search_that_finds_nothing_says_so(registry):
    tool = registry.get('memory_search')
    assert 'No memory matches' in tool.run({'query': 'zebra'}) or 'No memory' in tool.run({'query': 'zebra'})


def test_a_memory_needs_a_title_and_a_body(registry):
    tool = registry.get('memory_remember')
    with pytest.raises(ToolError):
        tool.run({'title': '', 'body': 'text'})
    with pytest.raises(ToolError):
        tool.run({'title': 'Title', 'body': '  '})


# ── the real readings ──────────────────────────────────────────────────────

def test_the_system_status_is_a_real_reading(registry):
    tool = registry.get('system_status')
    report = tool.run({})
    assert 'CPU' in report
    assert 'RAM' in report


def test_the_time_is_the_time_of_this_computer(registry):
    tool = registry.get('current_time')
    assert tool.run({})


def test_a_page_that_is_not_https_is_refused_without_a_network_call(registry):
    tool = registry.get('research_fetch')
    with pytest.raises(ToolError):
        tool.run({'url': 'http://example.com/page'})


def test_a_private_address_is_refused_without_a_network_call(registry):
    tool = registry.get('research_fetch')
    with pytest.raises(ToolError):
        tool.run({'url': 'https://127.0.0.1/secret'})


# ── the registry itself ────────────────────────────────────────────────────

def test_the_same_tool_cannot_be_registered_twice(registry):
    tool = registry.get('current_time')
    with pytest.raises(ValueError):
        registry.register(tool)


def test_a_registry_without_memory_has_no_memory_tools(tmp_path):
    registry = build_registry(root=tmp_path)
    assert 'memory_search' not in registry.names()
    assert 'memory_remember' not in registry.names()


@pytest.mark.parametrize('observed', [True, False])
def test_launch_requires_foreground_evidence(registry, monkeypatch, observed):
    from automation import windows

    request = windows.LaunchRequest('Notepad', 123)
    monkeypatch.setattr(windows, 'launch_app', lambda _: request)
    monkeypatch.setattr(windows, 'launch_is_foreground', lambda result: result is request and observed)
    ticks = iter([0.0, 1.0])
    monkeypatch.setattr('core.mission_tools.time.monotonic', lambda: next(ticks))
    tool = registry.get('launch_app')
    if observed:
        assert 'foreground process (PID 123)' in tool.run({'app': 'Notepad'})
    else:
        with pytest.raises(ToolError, match='window could not be verified'):
            tool.run({'app': 'Notepad'})


def test_export_writes_tamil_without_overwriting(registry, root):
    tool = registry.get('export_text')
    assert not tool.read_only
    args = {'filename': 'jarvis-test.txt', 'text': 'வணக்கம்'}
    assert 'verified' in tool.run(args)
    assert (root / args['filename']).read_bytes() == args['text'].encode('utf-8')
    with pytest.raises(ToolError, match='already exists'):
        tool.run({**args, 'text': 'different'})
    assert (root / args['filename']).read_text(encoding='utf-8') == args['text']


def test_export_refuses_a_path_outside_mission_folder(registry):
    with pytest.raises(ToolError, match='simple'):
        registry.get('export_text').run({'filename': '../outside.txt', 'text': 'text'})
