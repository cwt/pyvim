"""
Tests for the integer-valued `:set` handlers (shared implementation,
docs/bugs/029.md): tabstop and scrolloff keep their different minimums.
"""

from __future__ import annotations

from pyvim.commands.handler import handle_command
from pyvim.editor_buffer import EditorBuffer


def _with_buffer(editor):
    """Give the editor an active buffer so `:set` commands can run."""
    editor.load_initial_files([None])
    editor.window_arrangement._add_editor_buffer(EditorBuffer(editor))
    editor.sync_with_prompt_toolkit()
    return editor


def test_tabstop_handler(editor):
    _ = _with_buffer(editor)
    handle_command(editor, ':set tabstop=8')
    assert editor.tabstop == 8

    handle_command(editor, ':set ts=2')
    assert editor.tabstop == 2

    # Displaying the current value:
    handle_command(editor, ':set ts')
    assert editor.message == 'tabstop=2'

    # Validation:
    handle_command(editor, ':set ts=oops')
    assert editor.message == 'Number required after ='
    handle_command(editor, ':set ts=0')
    assert editor.message == 'Argument must be positive'
    assert editor.tabstop == 2


def test_scrolloff_handler(editor):
    _ = _with_buffer(editor)
    handle_command(editor, ':set scrolloff=3')
    assert editor.scroll_offset == 3

    handle_command(editor, ':set so')
    assert editor.message == 'scrolloff=3'

    # scrolloff accepts 0 (unlike tabstop):
    handle_command(editor, ':set so=0')
    assert editor.scroll_offset == 0
    assert editor.message != 'Argument must be positive'

    handle_command(editor, ':set so=oops')
    assert editor.message == 'Number required after ='
    handle_command(editor, ':set so=-3')
    assert editor.message == 'Argument must be positive'
