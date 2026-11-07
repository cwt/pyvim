import os

from prompt_toolkit.application import get_app
from prompt_toolkit.filters import (
    Condition,
    has_focus,
    is_read_only,
    vi_insert_mode,
    vi_navigation_mode,
    vi_selection_mode,
)
from prompt_toolkit.filters.app import (
    vi_replace_single_mode,
    vi_waiting_for_text_object_mode,
)
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.vi_state import InputMode
from prompt_toolkit.keys import Keys

from .thai import next_cell_offset, prev_cell_offset

__all__ = ('create_key_bindings',)


def _keep_keysync_disabled(event):
    """
    Never record the partially-typed key buffer with the redo binding
    (progressive typing should stay redo-friendly).
    """
    return False


def _delete_cell_clusters(event, backward):
    """
    Delete `event.arg` cell clusters before/after the cursor on the current line.
    """
    buff = event.current_buffer
    doc = buff.document
    line = doc.current_line
    col = doc.cursor_position_col
    if backward:
        span = col - prev_cell_offset(line, col, event.arg)
    else:
        span = next_cell_offset(line, col, event.arg) - col
    if span > 0:
        text = buff.delete_before_cursor(count=span) if backward else buff.delete(count=span)
        event.app.clipboard.set_text(text)


def create_key_bindings(editor):
    """
    Create custom key bindings.

    This starts with the key bindings, defined by `prompt-toolkit`, but adds
    the ones which are specific for the editor.
    """
    kb = KeyBindings()

    # Filters.
    @Condition
    def vi_buffer_focussed():
        app = get_app()
        if app.layout.has_focus(editor.search_buffer) or app.layout.has_focus(
            editor.command_buffer
        ):
            return False
        return True

    in_insert_mode = vi_insert_mode & vi_buffer_focussed
    in_navigation_mode = vi_navigation_mode & vi_buffer_focussed

    @kb.add('c-t')
    def _(event):
        """
        Override default behaviour of prompt-toolkit.
        (Control-T will swap the last two characters before the cursor, because
        that's what readline does.)
        """
        pass

    @kb.add('c-t', filter=in_insert_mode)
    def indent_line(event):
        """
        Indent current line.
        """
        b = event.current_buffer

        # Move to start of line.
        pos = b.document.get_start_of_line_position(after_whitespace=True)
        b.cursor_position += pos

        # Insert tab.
        if editor.expand_tab:
            b.insert_text(' ' * editor.tabstop)
        else:
            b.insert_text('\t')

        # Restore cursor.
        b.cursor_position -= pos

    @kb.add('c-r', filter=in_navigation_mode, save_before=_keep_keysync_disabled)
    def redo(event):
        """
        Redo.
        """
        event.app.current_buffer.redo()

    @kb.add(':', filter=in_navigation_mode)
    def enter_command_mode(event):
        """
        Entering command mode.
        """
        editor.enter_command_mode()

    @kb.add(
        'tab',
        filter=vi_insert_mode
        & ~has_focus(editor.command_buffer)
        & whitespace_before_cursor_on_line,
    )
    def autocomplete_or_indent(event):
        """
        When the 'tab' key is pressed with only whitespace character before the
        cursor, do autocompletion. Otherwise, insert indentation.
        """
        b = event.app.current_buffer
        if editor.expand_tab:
            b.insert_text(' ' * editor.tabstop)
        else:
            b.insert_text('\t')

    def command_buffer_is_empty():
        return editor.command_buffer.text == ''

    @kb.add('escape', filter=has_focus(editor.command_buffer))
    @kb.add('c-c', filter=has_focus(editor.command_buffer))
    @kb.add(
        'backspace',
        filter=has_focus(editor.command_buffer) & Condition(command_buffer_is_empty),
    )
    def leave_command_mode(event):
        """
        Leaving command mode.
        """
        editor.leave_command_mode()

    @kb.add('c-w', 'c-w', filter=in_navigation_mode)
    def focus_next_window(event):
        editor.window_arrangement.cycle_focus()
        editor.sync_with_prompt_toolkit()

    @kb.add('c-w', 'n', filter=in_navigation_mode)
    def horizontal_split(event):
        """
        Split horizontally.
        """
        editor.window_arrangement.hsplit(None)
        editor.sync_with_prompt_toolkit()

    @kb.add('c-w', 'v', filter=in_navigation_mode)
    def vertical_split(event):
        """
        Split vertically.
        """
        editor.window_arrangement.vsplit(None)
        editor.sync_with_prompt_toolkit()

    @kb.add('g', 't', filter=in_navigation_mode)
    def focus_next_tab(event):
        editor.window_arrangement.go_to_next_tab()
        editor.sync_with_prompt_toolkit()

    @kb.add('g', 'T', filter=in_navigation_mode)
    def focus_previous_tab(event):
        editor.window_arrangement.go_to_previous_tab()
        editor.sync_with_prompt_toolkit()

    @kb.add('f1')
    def show_help(event):
        editor.show_help()

    @Condition
    def in_file_explorer_mode():
        return bool(
            editor.current_editor_buffer and editor.current_editor_buffer.in_file_explorer_mode
        )

    @kb.add('enter', filter=in_file_explorer_mode)
    def open_path(event):
        """
        Open file/directory in file explorer mode.
        """
        name_under_cursor = event.current_buffer.document.current_line
        if not name_under_cursor.strip() or name_under_cursor.lstrip().startswith('"'):
            return
        new_path = os.path.normpath(
            os.path.join(editor.current_editor_buffer.location, name_under_cursor)
        )

        editor.window_arrangement.open_buffer(new_path, show_in_current_window=True)
        editor.sync_with_prompt_toolkit()

    @kb.add('-', filter=in_file_explorer_mode)
    def to_parent_directory(event):
        new_path = os.path.normpath(os.path.join(editor.current_editor_buffer.location, '..'))

        editor.window_arrangement.open_buffer(new_path, show_in_current_window=True)
        editor.sync_with_prompt_toolkit()

    # Cell-cluster Vi editing and motion overrides (Phase 3):
    # Ensure `x`, `X`, `s`, `r`, `~`, `$`, `e`, and `E` operate on whole
    # visual cell clusters (`base + comb*`) rather than slicing raw codepoints.

    @kb.add('x', filter=vi_navigation_mode)
    def delete_cell_after_cursor(event):
        """
        Delete `event.arg` cell clusters at/after the cursor on the current line.
        """
        _delete_cell_clusters(event, backward=False)

    @kb.add('X', filter=vi_navigation_mode)
    def delete_cell_before_cursor(event):
        """
        Delete `event.arg` cell clusters before the cursor on the current line.
        """
        _delete_cell_clusters(event, backward=True)

    @kb.add('s', filter=vi_navigation_mode & ~is_read_only)
    def substitute_cell(event):
        """
        Substitute `event.arg` cell clusters at the cursor and enter insert mode.
        """
        buff = event.current_buffer
        doc = buff.document
        line = doc.current_line
        col = doc.cursor_position_col
        span = next_cell_offset(line, col, event.arg) - col
        text = buff.delete(count=span) if span > 0 else ''
        event.app.clipboard.set_text(text)
        event.app.vi_state.input_mode = InputMode.INSERT

    @kb.add(Keys.Any, filter=vi_replace_single_mode)
    def replace_single_cell(event):
        """
        Replace `event.arg` cell clusters at the cursor position with `event.data`.
        """
        buff = event.current_buffer
        doc = buff.document
        line = doc.current_line
        col = doc.cursor_position_col
        span = next_cell_offset(line, col, event.arg) - col
        if span > 0:
            buff.delete(count=span)
        buff.insert_text(event.data * event.arg, overwrite=False)
        buff.cursor_position += buff.document.get_cursor_left_position(count=1)
        event.app.vi_state.input_mode = InputMode.NAVIGATION

    @kb.add('~', filter=vi_navigation_mode & ~Condition(lambda: get_app().vi_state.tilde_operator))
    def reverse_case_cell(event):
        """
        Swap case of the current cell cluster and advance one cell cluster.
        """
        buff = event.current_buffer
        doc = buff.document
        line = doc.current_line
        col = doc.cursor_position_col
        if col >= len(line):
            return
        end_col = next_cell_offset(line, col, event.arg)
        span = end_col - col
        if span > 0:
            cluster = line[col:end_col]
            buff.delete(count=span)
            buff.insert_text(cluster.swapcase(), overwrite=False)

    @kb.add('$', filter=(vi_navigation_mode | vi_selection_mode) & ~vi_waiting_for_text_object_mode)
    def move_to_end_of_line_cell(event):
        """
        Move cursor to the start of the last cell cluster on the current line.
        Operator-pending `$` (`d$`, `c$`, `y$`) remains handled by `vi.py` so
        that trailing combining marks are included in the operator range.
        """
        buff = event.current_buffer
        doc = buff.document
        line = doc.current_line
        target_col = prev_cell_offset(line, len(line), 1)
        buff.cursor_position += target_col - doc.cursor_position_col

    def _move_to_end_of_word_cell(event, WORD):
        "Move cursor to the base character of the last cell cluster of the word."
        buff = event.current_buffer
        doc = buff.document
        end = doc.find_next_word_ending(count=event.arg, WORD=WORD)
        if end:
            buff.cursor_position = prev_cell_offset(doc.text, buff.cursor_position + end, 1)

    @kb.add('e', filter=(vi_navigation_mode | vi_selection_mode) & ~vi_waiting_for_text_object_mode)
    def move_to_end_of_word_cell(event):
        """
        Move cursor to the base character of the last cell cluster of the word.
        """
        _move_to_end_of_word_cell(event, WORD=False)

    @kb.add('E', filter=(vi_navigation_mode | vi_selection_mode) & ~vi_waiting_for_text_object_mode)
    def move_to_end_of_big_word_cell(event):
        """
        Move cursor to the base character of the last cell cluster of the WORD.
        """
        _move_to_end_of_word_cell(event, WORD=True)

    return kb


@Condition
def whitespace_before_cursor_on_line():
    """
    Filter which evaluates to True when the characters before the cursor are
    whitespace, or we are at the start of the line.
    """
    b = get_app().current_buffer
    before_cursor = b.document.current_line_before_cursor

    return bool(not before_cursor or before_cursor[-1].isspace())
