"""
Tests for `pyvim/lexer.py` (P1: cached, streaming `DocumentLexer`).
"""

from __future__ import unicode_literals

from prompt_toolkit.document import Document
from prompt_toolkit.lexers.pygments import PygmentsLexer

from pyvim.lexer import DocumentLexer


class _StubEditorBuffer(object):
    def __init__(self, location, in_file_explorer_mode=False):
        self.location = location
        self.in_file_explorer_mode = in_file_explorer_mode


def _make_python_doc(num_lines=120):
    # Includes a 40-line multiline docstring (lines 40..80) to exercise
    # continuous tokenization across string boundaries.
    lines = []
    for i in range(num_lines):
        if i == 40:
            lines.append('def doc_func():\n    """start multiline docstring')
        elif 40 < i < 80:
            lines.append('    inside multiline docstring %i' % i)
        elif i == 80:
            lines.append('    end multiline docstring"""\n    return 42')
        else:
            lines.append('def func_%i(x):\n    return x * %i  # c %i' % (i, i, i))
    text = '\n'.join(lines)
    doc = Document(text, 0)
    _ = doc.lines
    return doc


def test_lex_document_matches_pygments_lexer():
    """Token-for-token parity with prompt_toolkit's `PygmentsLexer`."""
    doc = _make_python_doc()
    stub = _StubEditorBuffer('sample.py')

    new_get_line = DocumentLexer(stub).lex_document(doc)
    ref_get_line = PygmentsLexer.from_filename('sample.py', sync_from_start=False).lex_document(doc)

    for row in range(len(doc.lines)):
        assert new_get_line(row) == ref_get_line(row), 'Token mismatch at row %i: %r != %r' % (
            row,
            new_get_line(row),
            ref_get_line(row),
        )


def test_lexer_instance_is_cached():
    """The Pygments lexer instance must not be re-looked-up on every edit."""
    doc = _make_python_doc()
    stub = _StubEditorBuffer('sample.py')
    lexer = DocumentLexer(stub)

    get_line = lexer.lex_document(doc)
    get_line(5)

    assert lexer._pygments_lexer is not None
    first = lexer._pygments_lexer
    assert lexer._cached_location == 'sample.py'

    # A new `lex_document` call (simulating the next keystroke) reuses it:
    get_line = lexer.lex_document(doc)
    get_line(5)
    assert lexer._pygments_lexer is first


def test_unknown_extension_falls_back_to_simple_lexer():
    doc = _make_python_doc()
    stub = _StubEditorBuffer('sample.unknownext')
    lexer = DocumentLexer(stub)

    get_line = lexer.lex_document(doc)
    # No Pygments lexer is found (ClassNotFound): plain text highlighting,
    # and the miss must be cached (no re-scan of the Pygments registry).
    for style, _text in get_line(0):
        assert style == '', 'Expected no highlighting, got %r' % style
    assert lexer._pygments_lexer is None
    assert lexer._cached_location == 'sample.unknownext'


def test_no_location_falls_back_to_simple_lexer():
    doc = Document('def f():\n    return 1\n', 0)
    stub = _StubEditorBuffer(None)
    get_line = DocumentLexer(stub).lex_document(doc)
    for style, _text in get_line(0):
        assert style == ''


def test_directory_listing_mode_still_uses_directory_lexer():
    lines = [
        '" ==================================\n',
        '" Directory Listing\n',
        '../\n',
        './\n',
        'subdir/\n',
        'file.py\n',
        'file.md\n',
    ]
    doc = Document('\n'.join(lines), 0)
    _ = doc.lines
    stub = _StubEditorBuffer('/some/dir', in_file_explorer_mode=True)

    from pyvim.lexer import DirectoryListingLexer

    new_get_line = DocumentLexer(stub).lex_document(doc)
    # The directory-listing mode must keep using the `DirectoryListingLexer`
    # via `PygmentsLexer`, exactly as before the P1 streaming change:
    ref_get_line = PygmentsLexer(DirectoryListingLexer, sync_from_start=False).lex_document(doc)

    for row in range(len(doc.lines)):
        assert new_get_line(row) == ref_get_line(row)


def test_directory_listing_lexer_is_cached():
    # docs/bugs/030.md: constructing a `PygmentsLexer` scans the Pygments
    # registry; file-explorer buffers must reuse one instance instead of
    # rebuilding it on every keystroke.
    doc = Document('" Directory Listing\n../\nsubdir/\n', 0)
    _ = doc.lines
    stub = _StubEditorBuffer('/some/dir', in_file_explorer_mode=True)
    lexer = DocumentLexer(stub)

    first = lexer._get_directory_lexer()
    second = lexer._get_directory_lexer()
    assert first is second
    # Two `lex_document` calls (keystrokes) reuse it as well:
    lexer.lex_document(doc)
    assert lexer._get_directory_lexer() is first
