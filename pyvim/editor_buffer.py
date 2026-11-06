from __future__ import unicode_literals

import os
import weakref

from prompt_toolkit import __version__ as ptk_version
from prompt_toolkit.application.current import get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from six import string_types

from pyvim.completion import DocumentCompleter
from pyvim.reporting import report

PTK3 = ptk_version.startswith('3.')

if PTK3:
    import asyncio
else:
    # `prompt_toolkit.eventloop` only exists in prompt_toolkit 2.x;
    # `# type: ignore` because mypy only sees the installed (3.x) package.
    from prompt_toolkit.eventloop import call_from_executor, run_in_executor  # type: ignore[attr-defined]

__all__ = ('EditorBuffer',)


class EditorBuffer(object):
    """
    Wrapper around a `prompt-toolkit` buffer.

    A 'prompt-toolkit' `Buffer` doesn't know anything about files, changes,
    etc... This wrapper contains the necessary data for the editor.
    """

    def __init__(self, editor, location=None, text=None):
        assert location is None or isinstance(location, string_types)
        assert text is None or isinstance(text, string_types)
        assert not (location and text)

        self._editor_ref = weakref.ref(editor)
        self.location = location
        self.encoding = 'utf-8'

        #: is_new: True when this file does not yet exist in the storage.
        self.is_new = True

        # Empty if not in file explorer mode, directory path otherwise.
        self.isdir = False

        # Read text.
        if location:
            text = self._read(location)
        else:
            text = text or ''

        self._file_content = text

        # Create Buffer.
        self.buffer = Buffer(
            multiline=True,
            completer=DocumentCompleter(editor, self),
            document=Document(text, 0),
            on_text_changed=self._on_text_changed,
        )

        # List of reporting errors, and index of those errors by line.
        self.report_errors = []
        self.report_errors_by_line = {}
        self._reporter_is_running = False
        self._run_reporter_again = False

        # True when some changes are not yet written to file.
        self._has_unsaved_changes = False

    @property
    def editor(self):
        """Back reference to the Editor."""
        return self._editor_ref()

    def _on_text_changed(self, *args):
        "Buffer text changed."
        # Update the dirty flag once per text change, so that per-frame
        # `has_unsaved_changes` lookups are O(1).
        self._has_unsaved_changes = self.buffer.text != self._file_content

        self.run_reporter()

    @property
    def has_unsaved_changes(self):
        """
        True when some changes are not yet written to file.
        """
        return self._has_unsaved_changes

    @property
    def in_file_explorer_mode(self):
        """
        True when we are in file explorer mode (when this is a directory).
        """
        return self.isdir

    def _read(self, location):
        """
        Read file I/O backend.
        """
        for io in self.editor.io_backends:
            if io.can_open_location(location):
                # Found an I/O backend.
                exists = io.exists(location)
                self.isdir = io.isdir(location)

                if exists in (True, NotImplemented):
                    # File could exist. Read it.
                    self.is_new = False
                    try:
                        text, self.encoding = io.read(location)

                        # Replace \r\n by \n.
                        text = text.replace('\r\n', '\n')

                        # Drop trailing newline while editing.
                        # (prompt-toolkit doesn't enforce the trailing newline.)
                        if text.endswith('\n'):
                            text = text[:-1]
                    except Exception as e:
                        self.editor.show_message('Cannot read %r: %r' % (location, e))
                        return ''
                    else:
                        return text
                else:
                    # File doesn't exist.
                    self.is_new = True
                    return ''

        self.editor.show_message('Cannot read: %r' % location)
        return ''

    def reload(self):
        """
        Reload file again from storage.
        """
        text = self._read(self.location)
        cursor_position = min(self.buffer.cursor_position, len(text))

        self.buffer.document = Document(text, cursor_position)
        self._file_content = text
        self._has_unsaved_changes = False

    def write(self, location=None):
        """
        Write file to I/O backend.
        """
        # Take location and expand tilde.
        if location is not None:
            self.location = location
        assert self.location

        # Find I/O backend that handles this location.
        for io in self.editor.io_backends:
            if io.can_open_location(self.location):
                break
        else:
            self.editor.show_message('Unknown location: %r' % location)

        # Write it.
        try:
            io.write(self.location, self.buffer.text + '\n', self.encoding)
            self.is_new = False
        except Exception as e:
            # E.g. "No such file or directory."
            self.editor.show_message('%s' % e)
        else:
            # When the save succeeds: update: _file_content.
            self._file_content = self.buffer.text
            self._has_unsaved_changes = False

    def get_display_name(self, short=False):
        """
        Return name as displayed.
        """
        if self.location is None:
            return '[New file]'
        elif short:
            return os.path.basename(self.location)
        else:
            return self.location

    def __repr__(self):
        return '%s(buffer=%r)' % (self.__class__.__name__, self.buffer)

    def run_reporter(self):
        "Buffer text changed."
        # 1. Fast exit BEFORE touching _reporter_is_running:
        #    Skip unnamed buffers and non-Python files immediately. (report()
        #    in reporting.py only knows how to check .py files.)
        if not self.location or not self.location.endswith('.py'):
            if self.report_errors:
                self.report_errors = []
                self.report_errors_by_line = {}
            return

        # 2. Acquire the running event loop BEFORE setting _reporter_is_running.
        #    If called before Application.run() (e.g. CLI startup on Python
        #    3.14+, where asyncio.get_event_loop() raises RuntimeError when no
        #    loop is running), leave _reporter_is_running = False so that
        #    Editor.run() can trigger the reporter once the loop is active.
        if PTK3:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return

        if self._reporter_is_running:
            self._run_reporter_again = True
            return

        self._reporter_is_running = True
        text = self.buffer.text
        location = self.location
        document = self.buffer.document

        def in_executor():
            # Call reporter with (location, document), as in reporting.report.
            report_errors = report(location, document)

            def ready():
                self._reporter_is_running = False

                # If the text has not changed while running in the worker
                # thread, update report_errors and only invalidate the UI
                # when the errors actually changed. (report_errors was NOT
                # cleared before the background check, so unchanged errors
                # do not cause flicker.)
                if text == self.buffer.text and not self._run_reporter_again:
                    if report_errors != self.report_errors:
                        self.report_errors = report_errors
                        by_line = {}
                        for err in report_errors:
                            by_line.setdefault(err.lineno, []).append(err)
                        self.report_errors_by_line = by_line
                        get_app().invalidate()
                else:
                    self._run_reporter_again = False
                    self.run_reporter()

            # Dispatch the callback back to the main thread in a thread-safe
            # way, from the executor thread (never from inside `ready`).
            if PTK3:
                loop.call_soon_threadsafe(ready)
            else:
                call_from_executor(ready)

        if PTK3:
            loop.run_in_executor(None, in_executor)
        else:
            run_in_executor(in_executor)
