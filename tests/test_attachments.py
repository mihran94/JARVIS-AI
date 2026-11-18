"""Local attachment selection: limits, privacy, symlinks and DOCX reading."""
from pathlib import Path
from zipfile import ZipFile
import pytest

from desktop.attachments import (
    AttachmentError, MAX_FILES, MAX_TOTAL_CHARACTERS, as_untrusted_context,
    read_file, stage_files, stage_folder,
)


def test_user_selected_text_files_are_snapshotted_and_never_send_absolute_paths(tmp_path):
    first = tmp_path / "story.md"
    first.write_text("Original history text.\n", encoding="utf-8")
    staged = stage_files([first, first])
    assert len(staged) == 1
    assert staged[0].name == "story.md"
    first.write_text("Changed after selecting.\n", encoding="utf-8")
    assert staged[0].text == "Original history text.\n"
    payload = as_untrusted_context(staged)
    assert "Original history text" in payload
    assert "untrusted reference material" in payload
    assert str(tmp_path) not in payload
    assert "Changed after" not in payload


def test_hidden_and_secret_files_are_refused(tmp_path):
    for name in (".env", "private.key", "secrets.json"):
        file = tmp_path / name
        file.write_text("Sensitive.", encoding="utf-8")
        with pytest.raises(AttachmentError):
            read_file(file)


def test_binary_pdf_and_too_large_files_are_rejected(tmp_path):
    pdf = tmp_path / "invoice.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    with pytest.raises(AttachmentError, match="PDF is not yet supported"):
        read_file(pdf)
    code = tmp_path / "main.py"
    code.write_bytes(b"\x00binary")
    with pytest.raises(AttachmentError, match="Binary"):
        read_file(code)
    large = tmp_path / "large.txt"
    large.write_bytes(b"A" * 26000)
    with pytest.raises(AttachmentError, match="24 KiB"):
        read_file(large)


def test_folder_walk_skips_hidden_directories_symlinks_and_unsupported(tmp_path):
    folder = tmp_path / "project"
    folder.mkdir()
    nested = folder / "src"
    nested.mkdir()
    (nested / "main.py").write_text("print('ready')", encoding="utf-8")
    (folder / "readme.md").write_text("# Hello", encoding="utf-8")
    secrets = folder / ".git"
    secrets.mkdir()
    (secrets / "private.txt").write_text("DO NOT READ", encoding="utf-8")
    (folder / "raw.jpg").write_bytes(b"\x01\x02")
    link = folder / "link.txt"
    try:
        link.symlink_to(nested / "main.py")
    except (OSError, NotImplementedError):
        pass
    files, skipped, truncated = stage_folder(folder)
    assert len(files) == 2
    assert {x.name for x in files} == {"project/readme.md", "project/src/main.py"}
    assert skipped >= 1
    assert truncated is False
    assert "DO NOT READ" not in as_untrusted_context(files)


def test_folder_limits_are_reported_not_hidden(tmp_path):
    folder = tmp_path / "many"
    folder.mkdir()
    for i in range(MAX_FILES + 5):
        (folder / f"{i:02d}.txt").write_text(f"file {i}", encoding="utf-8")
    files, skipped, truncated = stage_folder(folder)
    assert len(files) == MAX_FILES
    assert truncated is True
    assert len(as_untrusted_context(files)) < MAX_TOTAL_CHARACTERS


def test_docx_reader_uses_text_only_and_never_runs_embedded_scripts(tmp_path):
    path = tmp_path / "notes.docx"
    document = ('<w:document xmlns:w="http://schemas.openxmlformats.org/'
                'wordprocessingml/2006/main"><w:body><w:p>'
                '<w:r><w:t>Hello DOCX</w:t></w:r></w:p></w:body></w:document>')
    with ZipFile(path, "w") as output:
        output.writestr("word/document.xml", document)
        output.writestr("word/embeddings/evil.bin", b"not executable")
    item = read_file(path)
    assert item.text == "Hello DOCX"
    assert "evil.bin" not in as_untrusted_context([item])


def test_explicit_selection_respects_maximum_file_count(tmp_path):
    files = []
    for i in range(MAX_FILES + 1):
        file = tmp_path / f"f{i}.txt"
        file.write_text("hello", encoding="utf-8")
        files.append(file)
    with pytest.raises(AttachmentError, match="Maximum 12"):
        stage_files(files)
