"""
Reporting.

This is a way to highlight syntax errors in an open files.
Reporters are run in an executor (in a thread) to ensure not blocking the
input.

Usage::

    errors = report('location.py', Document('file content'))
"""

import string

import pyflakes.api

__all__ = ('report', 'checks_python_file')


def checks_python_file(location):
    """
    Single source of truth for the `.py` gate.

    `EditorBuffer.run_reporter` probes this to avoid spawning background
    work for non-Python files; `report` uses the same predicate inside the
    worker thread, so the two sides can never diverge (see docs/bugs/010.md
    of the findings bundle).
    """
    return bool(location) and location.endswith('.py')


class ReporterError(object):
    """
    Error found by a reporter.
    """

    def __init__(self, lineno, start_column, end_column, formatted_text):
        self.lineno = lineno  # Zero based line number.
        self.start_column = start_column
        self.end_column = end_column
        self.formatted_text = formatted_text

    def __eq__(self, other):
        if not isinstance(other, ReporterError):
            return NotImplemented
        return (
            self.lineno,
            self.start_column,
            self.end_column,
            self.formatted_text,
        ) == (
            other.lineno,
            other.start_column,
            other.end_column,
            other.formatted_text,
        )


def report(location, document):
    """
    Run reporter on document and return list of ReporterError instances.
    (Depending on the location it will or won't run anything.)

    Returns a list of `ReporterError`.
    """
    assert isinstance(location, str)

    if checks_python_file(location):
        return report_pyflakes(document)
    else:
        return []


WORD_CHARACTERS = string.ascii_letters + '0123456789_'


def report_pyflakes(document):
    """
    Run pyflakes on document and return list of ReporterError instances.
    """
    # Run pyflakes on input.
    reporter = _FlakesReporter()
    pyflakes.api.check(document.text, '', reporter=reporter)

    def format_flake_message(message):
        return [
            ('class:flakemessage.prefix', 'pyflakes:'),
            ('', ' '),
            ('class:flakemessage', message.message % message.message_args),
        ]

    def message_to_reporter_error(message):
        """Turn pyflakes message into ReporterError."""
        row = message.lineno - 1
        if row < len(document.lines):
            line = document.lines[row]
        else:
            line = ''
        # `message.col` is a UTF-8 byte offset (Python 3.8+ ast col_offset);
        # convert it to a character column.
        char_col = len(line.encode('utf-8')[: message.col].decode('utf-8', errors='replace'))
        start_index = document.translate_row_col_to_index(row, char_col)
        line_start = document.translate_row_col_to_index(row, 0)
        line_end = line_start + len(line)
        end_index = start_index
        while end_index < line_end:
            ch = document.text[end_index]
            if ch == '_' or ch.isalnum():
                end_index += 1
            else:
                break

        return ReporterError(
            lineno=row,
            start_column=char_col,
            end_column=char_col + (end_index - start_index),
            formatted_text=format_flake_message(message),
        )

    # Construct list of ReporterError instances.
    return [message_to_reporter_error(m) for m in reporter.messages]


class _FlakesReporter(object):
    """
    Reporter class to be passed to pyflakes.api.check.
    """

    def __init__(self):
        self.messages = []

    def unexpectedError(self, location, msg):
        pass

    def syntaxError(self, location, msg, lineno, offset, text):
        pass

    def flake(self, message):
        self.messages.append(message)
