from pyvim.commands.handler import handle_command

sample_text = """
Roses are red,
    Violets are blue,
Sugar is sweet,
    And so are you.
""".lstrip()


def given_sample_text(editor_buffer, text=None):
    editor = editor_buffer.editor
    editor.window_arrangement._add_editor_buffer(editor_buffer)
    editor_buffer.buffer.text = text or sample_text
    editor.sync_with_prompt_toolkit()


def given_cursor_position(editor_buffer, line_number, column=0):
    editor_buffer.buffer.cursor_position = editor_buffer.buffer.document.translate_row_col_to_index(
        line_number - 1, column
    )


def test_substitute_current_line(editor, editor_buffer):
    given_sample_text(editor_buffer)
    given_cursor_position(editor_buffer, 2)

    handle_command(editor, ':s/s are/ is')

    assert 'Roses are red,' in editor_buffer.buffer.text
    assert 'Violet is blue,' in editor_buffer.buffer.text
    assert 'And so are you.' in editor_buffer.buffer.text
    assert editor_buffer.buffer.cursor_position == editor_buffer.buffer.text.index('Violet')


def test_substitute_single_line(editor, editor_buffer):
    given_sample_text(editor_buffer)
    given_cursor_position(editor_buffer, 1)

    handle_command(editor, ':2s/s are/ is')

    assert 'Roses are red,' in editor_buffer.buffer.text
    assert 'Violet is blue,' in editor_buffer.buffer.text
    assert 'And so are you.' in editor_buffer.buffer.text
    assert editor_buffer.buffer.cursor_position == editor_buffer.buffer.text.index('Violet')


def test_substitute_range(editor, editor_buffer):
    given_sample_text(editor_buffer)
    given_cursor_position(editor_buffer, 1)

    handle_command(editor, ':1,3s/s are/ is')

    assert 'Rose is red,' in editor_buffer.buffer.text
    assert 'Violet is blue,' in editor_buffer.buffer.text
    assert 'And so are you.' in editor_buffer.buffer.text
    # The cursor must land on the last *substituted* line (line 2, "Violets
    # are…"), not the end of the range (docs/bugs/015.md).
    assert editor_buffer.buffer.cursor_position == editor_buffer.buffer.text.index('Violet')


def test_substitute_range_beyond_eof_is_an_error_not_a_crash(editor, editor_buffer):
    given_sample_text(editor_buffer)
    text_before = editor_buffer.buffer.text
    cursor_before = editor_buffer.buffer.cursor_position

    handle_command(editor, ':900s/s are/ is')

    # The out-of-document range reports the vim-like error and changes nothing.
    assert editor.message == 'E19: No such line in current buffer'
    assert editor_buffer.buffer.text == text_before
    assert editor_buffer.buffer.cursor_position == cursor_before


def test_substitute_no_match_keeps_cursor(editor, editor_buffer):
    given_sample_text(editor_buffer, 'Violet\n' * 4)
    cursor_before = editor_buffer.buffer.cursor_position

    handle_command(editor, ':1,4s/zero/nothing')

    # Nothing matched anywhere in the range: text (and cursor) unchanged.
    assert editor_buffer.buffer.text == 'Violet\nViolet\nViolet\nViolet\n'
    assert editor_buffer.buffer.cursor_position == cursor_before


def test_substitute_range_boundaries(editor, editor_buffer):
    given_sample_text(editor_buffer, 'Violet\n' * 4)

    handle_command(editor, ':2,3s/Violet/Rose')

    assert 'Violet\nRose\nRose\nViolet\n' in editor_buffer.buffer.text


def test_substitute_from_search_history(editor, editor_buffer):
    given_sample_text(editor_buffer)
    editor.application.current_search_state.text = 'blue'

    handle_command(editor, ':1,3s//pretty')
    assert 'Violets are pretty,' in editor_buffer.buffer.text


def test_substitute_from_substitute_search_history(editor, editor_buffer):
    given_sample_text(editor_buffer, 'Violet is Violet\n')

    handle_command(editor, ':s/Violet/Rose')
    assert 'Rose is Violet' in editor_buffer.buffer.text

    handle_command(editor, ':s//Lily')
    assert 'Rose is Lily' in editor_buffer.buffer.text


def test_substitute_with_repeat_last_substitution(editor, editor_buffer):
    given_sample_text(editor_buffer, 'Violet is Violet\n')
    editor.application.current_search_state.text = 'Lily'

    handle_command(editor, ':s/Violet/Rose')
    assert 'Rose is Violet' in editor_buffer.buffer.text

    handle_command(editor, ':s')
    assert 'Rose is Rose' in editor_buffer.buffer.text


def test_substitute_without_replacement_text(editor, editor_buffer):
    given_sample_text(editor_buffer, 'Violet Violet Violet \n')
    editor.application.current_search_state.text = 'Lily'

    handle_command(editor, ':s/Violet/')
    assert ' Violet Violet \n' in editor_buffer.buffer.text

    handle_command(editor, ':s/Violet')
    assert '  Violet \n' in editor_buffer.buffer.text

    handle_command(editor, ':s/')
    assert '   \n' in editor_buffer.buffer.text


def test_substitute_with_repeat_last_substitution_without_previous_substitution(
    editor, editor_buffer
):
    original_text = 'Violet is blue\n'
    given_sample_text(editor_buffer, original_text)

    handle_command(editor, ':s')
    assert original_text in editor_buffer.buffer.text

    editor.application.current_search_state.text = 'blue'

    handle_command(editor, ':s')
    assert 'Violet is \n' in editor_buffer.buffer.text


def test_substitute_flags_empty_flags(editor, editor_buffer):
    given_sample_text(editor_buffer, 'Violet is Violet\n')
    handle_command(editor, ':s/Violet/Rose/')
    assert 'Rose is Violet' in editor_buffer.buffer.text


def test_substitute_flags_g(editor, editor_buffer):
    given_sample_text(editor_buffer, 'Violet is Violet\n')
    handle_command(editor, ':s/Violet/Rose/g')
    assert 'Rose is Rose' in editor_buffer.buffer.text


def test_substitute_invalid_regex_does_not_crash(editor, editor_buffer):
    given_sample_text(editor_buffer, 'hello\n')
    handle_command(editor, ':s/[unclosed/x')
    assert editor.message is not None
    assert editor_buffer.buffer.text == 'hello\n'


def test_substitute_invalid_replacement_does_not_crash(editor, editor_buffer):
    given_sample_text(editor_buffer, 'hello\n')
    handle_command(editor, ':s/hello/\\1')
    assert editor.message is not None


def test_substitute_empty_search_history_does_not_mutate(editor, editor_buffer):
    given_sample_text(editor_buffer, 'hello\n')
    editor.application.current_search_state.text = ''
    before = editor_buffer.buffer.text
    handle_command(editor, ':s//X')
    assert editor_buffer.buffer.text == before
    assert editor.message is not None


def test_substitute_zero_matches_does_not_mark_dirty(editor, editor_buffer):
    given_sample_text(editor_buffer, 'hello\n')
    editor_buffer.buffer.text = 'hello'
    editor_buffer._file_content = editor_buffer.buffer.text
    editor_buffer._has_unsaved_changes = False
    assert not editor_buffer.has_unsaved_changes
    handle_command(editor, ':s/notfound/x/g')
    assert not editor_buffer.has_unsaved_changes
