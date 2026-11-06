"""
Tests for the `:w` / `:wq` / `:wqa` write flow (docs/bugs/006.md and
docs/bugs/007.md): failed writes must be reported without quitting.
"""

from __future__ import annotations

from pyvim.commands.handler import handle_command


def _editor_with_text(editor, editor_buffer, text):
    editor_buffer.buffer.text = text
    editor.window_arrangement._add_editor_buffer(editor_buffer)
    editor.sync_with_prompt_toolkit()
    return editor_buffer


def test_w_reports_file_exists_failure(editor, editor_buffer, tmp_path):
    _ = _editor_with_text(editor, editor_buffer, 'unsaved edits')
    existing = tmp_path / 'exists.txt'
    existing.write_text('occupado')

    handle_command(editor, ':w %s' % existing)

    assert editor.message == 'File exists (add ! to overriwe)'
    assert existing.read_text() == 'occupado'


def test_wq_quits_only_after_successful_write(editor, editor_buffer, tmp_path, monkeypatch):
    _ = _editor_with_text(editor, editor_buffer, 'unsaved edits')
    existing = tmp_path / 'exists.txt'
    existing.write_text('occupado')

    exits = []

    def record_exit(*args, **kwargs):
        exits.append(1)

    monkeypatch.setattr(editor.application, 'exit', record_exit)

    # Failed write ("File exists"): stay in the editor.
    handle_command(editor, ':wq %s' % existing)
    assert editor.message == 'File exists (add ! to overriwe)'
    assert exits == []
    assert existing.read_text() == 'occupado'

    # Successful write to a new file: quit exactly once.
    fresh = tmp_path / 'fresh.txt'
    handle_command(editor, ':wq %s' % fresh)
    assert exits == [1]
    assert fresh.read_text() == 'unsaved edits\n'


def test_wqa_quits_only_after_successful_write(editor, editor_buffer, tmp_path, monkeypatch):
    eb = _editor_with_text(editor, editor_buffer, 'wqa contents')
    eb.location = str(tmp_path / 'missing-dir' / 'wqa.txt')

    exits = []
    monkeypatch.setattr(editor.application, 'exit', lambda *a, **kw: exits.append(1))

    # A failing write (unwritable location) aborts the wqa:
    handle_command(editor, ':wqa')
    assert editor.message, 'failed write must surface a message'
    assert exits == []
    assert not (tmp_path / 'missing-dir' / 'wqa.txt').exists()

    # A successful write quits all and writes the buffer:
    eb.location = str(tmp_path / 'wqa_other.txt')
    handle_command(editor, ':wqa')
    assert exits == [1]
    assert (tmp_path / 'wqa_other.txt').read_text() == 'wqa contents\n'
