"""
Tests for `pyvim/layout.py` (P4: O(1) `report_errors_by_line` lookups in
`ReportingProcessor` and `ReportMessageToolbar`).
"""
from __future__ import unicode_literals

import types

from prompt_toolkit.document import Document
from prompt_toolkit.layout.processors import TransformationInput

from pyvim.layout import ReportMessageToolbar, ReportingProcessor
from pyvim.reporting import ReporterError


def _identity_source_to_display(source_pos):
    return source_pos


def _transformation_input(lineno, text):
    # `lineno` is the 0-based document row passed by `BufferControl`
    # (see `BufferControl._create_get_processed_line_func` in
    # `prompt_toolkit.layout.controls`), exactly like `ReporterError.lineno`
    # in `pyvim/reporting.py`.
    doc = Document(text, 0)
    return TransformationInput(
        buffer_control=None,
        document=doc,
        lineno=lineno,
        source_to_display=_identity_source_to_display,
        fragments=[('', c) for c in text],
        width=len(text),
        height=1,
    )


def test_reporting_processor_highlights_error_on_matching_line():
    # An error on document row 1 (0-based): that row's fragments are
    # highlighted when the processor is applied to row 1.
    err = ReporterError(lineno=1, start_column=1, end_column=3,
                        formatted_text=[])
    eb = types.SimpleNamespace(report_errors_by_line={1: [err]})
    proc = ReportingProcessor(eb)

    out = proc.apply_transformation(_transformation_input(lineno=1,
                                                          text='efgh'))
    fragments = out.fragments
    # Columns 1..2 (0-based, end exclusive) get the error style:
    assert fragments[1] == ('class:flakeserror', 'f')
    assert fragments[2] == ('class:flakeserror', 'g')
    # Neighbouring fragments are untouched:
    assert fragments[0] == ('', 'e')
    assert fragments[3] == ('', 'h')


def test_reporting_processor_ignores_other_lines():
    err = ReporterError(lineno=0, start_column=0, end_column=2,
                        formatted_text=[])
    eb = types.SimpleNamespace(report_errors_by_line={0: [err]})
    proc = ReportingProcessor(eb)

    # No error on document row 1: fragments are passed through as-is.
    out = proc.apply_transformation(_transformation_input(lineno=1,
                                                          text='efgh'))
    assert out.fragments == [('', 'e'), ('', 'f'), ('', 'g'), ('', 'h')]


def test_reporting_processor_multiple_errors_same_line():
    errs = [
        ReporterError(lineno=0, start_column=0, end_column=1, formatted_text=[]),
        ReporterError(lineno=0, start_column=3, end_column=4, formatted_text=[]),
    ]
    eb = types.SimpleNamespace(report_errors_by_line={0: errs})
    proc = ReportingProcessor(eb)

    out = proc.apply_transformation(_transformation_input(lineno=0,
                                                          text='abcd'))
    fragments = out.fragments
    assert fragments[0] == ('class:flakeserror', 'a')
    assert fragments[1] == ('', 'b')
    assert fragments[2] == ('', 'c')
    assert fragments[3] == ('class:flakeserror', 'd')


def test_reporting_processor_clamps_to_fragment_length():
    # An error reaching past the end of the fragments must be clamped.
    err = ReporterError(lineno=0, start_column=2, end_column=99,
                        formatted_text=[])
    eb = types.SimpleNamespace(report_errors_by_line={0: [err]})
    proc = ReportingProcessor(eb)

    out = proc.apply_transformation(_transformation_input(lineno=0, text='ab'))
    assert out.fragments == [('', 'a'), ('', 'b')]


def _get_formatted_text(toolbar):
    # `ReportMessageToolbar` is a `ConditionalContainer` wrapping a
    # `FormattedTextToolbar` (a `Window`) whose control holds the
    # `get_formatted_text` closure.
    return toolbar.content.content.text


def test_report_message_toolbar_shows_error_for_cursor_line(editor, editor_buffer):
    eb = editor_buffer
    editor.window_arrangement._add_editor_buffer(eb)
    editor.sync_with_prompt_toolkit()

    err = ReporterError(lineno=0, start_column=0, end_column=1,
                        formatted_text=[('class:flakemessage.prefix', 'pyflakes:'),
                                        ('', ' '),
                                        ('class:flakemessage', 'unused import')])
    eb.report_errors = [err]
    eb.report_errors_by_line = {0: [err]}
    # Cursor is on line 0 (the empty buffer's default cursor position).
    assert eb.buffer.document.cursor_position_row == 0

    get_formatted_text = _get_formatted_text(ReportMessageToolbar(editor))
    fragments = get_formatted_text()
    assert fragments == err.formatted_text
    assert 'pyflakes:' in [text for _style, text in fragments]


def test_report_message_toolbar_picks_error_of_cursor_line(editor, editor_buffer):
    eb = editor_buffer
    editor.window_arrangement._add_editor_buffer(eb)
    editor.sync_with_prompt_toolkit()

    err_line0 = ReporterError(lineno=0, start_column=0, end_column=1,
                              formatted_text=[('class:flakemessage', 'line-0 error')])
    err_line1 = ReporterError(lineno=1, start_column=0, end_column=1,
                              formatted_text=[('class:flakemessage', 'line-1 error')])
    eb.buffer.text = 'import os\nimport re\n'
    eb.report_errors = [err_line0, err_line1]
    eb.report_errors_by_line = {0: [err_line0], 1: [err_line1]}

    get_formatted_text = _get_formatted_text(ReportMessageToolbar(editor))

    # Move the cursor to line 1: that line's error must be shown now.
    eb.buffer.cursor_position = eb.buffer.document.translate_row_col_to_index(1, 0)
    fragments = get_formatted_text()
    assert fragments == err_line1.formatted_text

    # And back to line 0:
    eb.buffer.cursor_position = 0
    fragments = get_formatted_text()
    assert fragments == err_line0.formatted_text


def test_report_message_toolbar_empty_without_errors(editor, editor_buffer):
    eb = editor_buffer
    editor.window_arrangement._add_editor_buffer(eb)
    editor.sync_with_prompt_toolkit()

    get_formatted_text = _get_formatted_text(ReportMessageToolbar(editor))
    assert get_formatted_text() == []
