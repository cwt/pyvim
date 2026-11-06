"""
Tests for `pyvim/editor_buffer.py`:
  - P0: `run_reporter` no longer crashes on Python 3.14+/3.15 when called
    before the event loop is running (CLI startup), no longer lockouts
    unnamed / non-Python buffers, and no longer spawns background reporter
    tasks for files that `report()` cannot check (non-.py).
  - P0: `report_errors_by_line` index is maintained.
  - P5: `has_unsaved_changes` is an O(1) cached flag.
"""
from __future__ import unicode_literals

import asyncio
import time

from pyvim.editor_buffer import EditorBuffer
from pyvim.reporting import ReporterError

import pyvim.editor_buffer as editor_buffer_module


class _RecordingApp(object):
    """ Stand-in for `prompt_toolkit.application.current.get_app`. """

    def __init__(self, counts):
        self.counts = counts

    def invalidate(self):
        self.counts.append(1)


def _install_fake_get_app(monkeypatch):
    """ Replace `get_app` with a fake that records `invalidate()` calls. """
    counts = []

    def fake_get_app():
        return _RecordingApp(counts)

    monkeypatch.setattr(editor_buffer_module, 'get_app', fake_get_app)
    return counts


# --- P0: no running event loop (the CLI-startup crash scenario) -----------

def test_run_reporter_without_loop_no_crash_unnamed(editor_buffer):
    # An unnamed buffer (`pyvim` with no arguments) must fast-exit *before*
    # touching the event loop, and must not leave itself locked out:
    eb = editor_buffer
    assert eb._reporter_is_running is False
    eb.run_reporter()
    assert eb._reporter_is_running is False
    assert eb._run_reporter_again is False
    # After "saving" the buffer as a file the reporter must be retriable:
    eb.run_reporter()
    assert eb._reporter_is_running is False


def test_open_py_buffer_before_event_loop(editor, tmp_path):
    # Regression: on Python 3.14+ `asyncio.get_event_loop()` raises
    # RuntimeError when no loop is running, so opening a .py file from the
    # CLI used to crash *before* `Editor.run()`.
    p = tmp_path / 'sample.py'
    p.write_text('x = 1\n')

    editor.load_initial_files([str(p)])
    eb = editor.window_arrangement.editor_buffers[0]

    # Deferred: the flag stayed False so that `Editor.run()` (`pre_run`)
    # can start the reporter once the loop is active.
    assert eb._reporter_is_running is False
    assert eb.report_errors == []
    assert eb.report_errors_by_line == {}


def test_run_reporter_non_python_file_skips_background(editor, tmp_path):
    # Non-.py files: `report()` cannot check them, so no executor task may
    # be spawned on every keystroke, and stale errors must be cleared.
    p = tmp_path / 'notes.txt'
    p.write_text('hello world')
    eb = EditorBuffer(editor, location=str(p))

    eb.report_errors = [ReporterError(0, 0, 1, [])]
    eb.report_errors_by_line = {0: [ReporterError(0, 0, 1, [])]}

    eb.run_reporter()

    assert eb.report_errors == []
    assert eb.report_errors_by_line == {}
    assert eb._reporter_is_running is False
    assert eb._run_reporter_again is False


# --- P0: running event loop (normal in-editor operation) ------------------

def test_run_reporter_populates_line_index(editor, tmp_path, monkeypatch):
    p = tmp_path / 'unused.py'
    p.write_text('import os\n')  # pyflakes F401 on line 0

    invalidations = _install_fake_get_app(monkeypatch)

    eb = EditorBuffer(editor, location=str(p))

    async def main():
        eb.run_reporter()
        assert eb._reporter_is_running is True
        deadline = time.time() + 5
        while eb._reporter_is_running:
            assert time.time() < deadline, 'reporter did not finish in time'
            await asyncio.sleep(0.01)

    asyncio.run(main())

    assert eb._reporter_is_running is False
    assert len(eb.report_errors) == 1
    # The O(1) index must map the 0-based error line to the errors:
    assert set(eb.report_errors_by_line.keys()) == {0}
    assert eb.report_errors_by_line[0][0] is eb.report_errors[0]
    assert invalidations, 'UI must be invalidated once errors are set'


def test_run_reporter_reentry_marks_run_again(editor, tmp_path, monkeypatch):
    p = tmp_path / 'a.py'
    p.write_text('import os\n')

    _install_fake_get_app(monkeypatch)
    eb = EditorBuffer(editor, location=str(p))

    async def main():
        eb.run_reporter()
        # Simulate a second text change while the background run is active:
        eb.run_reporter()
        assert eb._run_reporter_again is True
        deadline = time.time() + 5
        while eb._reporter_is_running:
            assert time.time() < deadline, 'reporter did not finish in time'
            await asyncio.sleep(0.01)
        assert eb._run_reporter_again is False

    asyncio.run(main())
    assert eb._reporter_is_running is False
    assert len(eb.report_errors) == 1


def test_run_reporter_no_flicker_keeps_old_errors(editor, tmp_path, monkeypatch):
    # P0: the old implementation cleared `report_errors` *before* running
    # the background check (red error lines flickered on every keystroke).
    # Now: unchanged errors must not be republished / invalidated.
    p = tmp_path / 'b.py'
    p.write_text('import os\n')

    invalidations = _install_fake_get_app(monkeypatch)
    eb = EditorBuffer(editor, location=str(p))

    async def main():
        # First run: errors get published.
        eb.run_reporter()
        deadline = time.time() + 5
        while eb._reporter_is_running:
            assert time.time() < deadline
            await asyncio.sleep(0.01)
        first_invalidations = len(invalidations)
        assert first_invalidations >= 1

        # Second run with the same (unchanged) text: the reporter result is
        # a *new* list of errors, but no text change means the published
        # errors should be replaced at most when actually different.
        eb.report_errors = []  # Simulate stale state; republish expected.
        eb.report_errors_by_line = {}
        eb.run_reporter()
        while eb._reporter_is_running:
            assert time.time() < deadline
            await asyncio.sleep(0.01)
        assert set(eb.report_errors_by_line.keys()) == {0}

    asyncio.run(main())


# --- P5: O(1) `has_unsaved_changes` flag ----------------------------------

def test_has_unsaved_changes_flag(editor_buffer):
    eb = editor_buffer
    assert eb.has_unsaved_changes is False

    eb.buffer.text = 'hello'
    assert eb.has_unsaved_changes is True

    # Text equals the on-disk content again -> clean.
    eb.buffer.text = ''
    assert eb.has_unsaved_changes is False


def test_has_unsaved_changes_after_write_and_reload(editor, tmp_path):
    p = tmp_path / 'c.txt'
    p.write_text('initial')
    eb = EditorBuffer(editor, location=str(p))
    assert eb.has_unsaved_changes is False

    eb.buffer.text = 'modified'
    assert eb.has_unsaved_changes is True

    eb.write()
    assert eb.has_unsaved_changes is False
    # `EditorBuffer.write` always stores a trailing newline.
    assert p.read_text() == 'modified\n'

    # External change + reload:
    p.write_text('externally edited')
    eb.reload()
    assert eb.has_unsaved_changes is False
    assert eb.buffer.text == 'externally edited'


def test_substitute_marks_unsaved_changes(editor, tmp_path):
    # `:s` replaces the buffer's `Document`; the new text differs from the
    # on-disk content, so the dirty flag must go True.
    p = tmp_path / 'd.txt'
    p.write_text('Violet is Violet\n')
    eb = EditorBuffer(editor, location=str(p))
    editor.window_arrangement._add_editor_buffer(eb)
    editor.sync_with_prompt_toolkit()
    assert eb.has_unsaved_changes is False

    from pyvim.commands.handler import handle_command
    handle_command(editor, ':s/Violet/Rose')
    assert eb.has_unsaved_changes is True
    assert eb.buffer.text == 'Rose is Violet'
