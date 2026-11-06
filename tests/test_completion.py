"""
Tests for `pyvim/completion.py` (P3: singleton + line-cached word completer).
"""
from __future__ import unicode_literals

from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from pyvim.completion import DocumentCompleter, DocumentWordsCompleter


def _completions(completer, text, cursor):
    doc = Document(text, cursor)
    return [c.text for c in completer.get_completions(doc, CompleteEvent())]


def test_words_from_other_lines():
    # 'f' on the cursor line matches 'foo' found in other lines:
    comps = _completions(DocumentWordsCompleter(), 'foo bar baz\nf', 13)
    assert 'foo' in comps


def test_words_from_current_line():
    # 'foobar' on the non-cursor lines completes 'fo' typed on the
    # current line:
    comps = _completions(DocumentWordsCompleter(), 'foobar\nfo', 9)
    assert comps == ['foobar']


def test_exact_word_before_cursor_not_offered():
    # The word itself is never offered as its own completion:
    comps = _completions(DocumentWordsCompleter(), 'foo bar\nfoo', 11)
    assert comps == []


def test_no_word_before_cursor_yields_nothing():
    comps = _completions(DocumentWordsCompleter(), 'foo bar\n ', 9)
    assert comps == []


def test_cache_key_stable_while_typing_on_current_line():
    comp = DocumentWordsCompleter()
    assert comp._cached_key is None

    c1 = _completions(comp, 'alpha beta\nal', 13)
    assert c1 == ['alpha']
    key = comp._cached_key
    assert key is not None

    # Typing on the current line leaves the prefix/suffix around that line
    # unchanged: the non-cursor word cache must *not* be recomputed.
    c2 = _completions(comp, 'alpha beta\nalp', 14)
    assert c2 == ['alpha']
    assert comp._cached_key == key, \
        'typing on the current line must not rescan the other lines'


def test_cache_invalidated_when_other_lines_change():
    comp = DocumentWordsCompleter()
    _completions(comp, 'alpha beta\nal', 13)
    key_before = comp._cached_key

    # 'alpine' appears on a non-cursor line of the *new* text:
    c3 = _completions(comp, 'alpha zebra alpine\nal', 21)
    assert c3 == ['alpha', 'alpine']
    assert comp._cached_key != key_before, \
        'changed other lines must invalidate the non-cursor word cache'


def test_document_completer_persists_words_completer(editor, editor_buffer):
    # P3: `DocumentCompleter` must reuse a single `DocumentWordsCompleter`
    # across invocations (the cache is only useful if it persists).
    editor.enable_jedi = False
    editor_buffer.location = None  # treated as '.txt' -> words completer

    completer = DocumentCompleter(editor, editor_buffer)
    assert isinstance(completer._words_completer, DocumentWordsCompleter)
    assert completer._words_completer._cached_key is None

    doc = Document('gamma alpha\ngamm', 16)
    assert 'gamma' in [c.text for c in completer.get_completions(doc,
                                                                 CompleteEvent())]
    assert completer._words_completer._cached_key is not None

    words_completer = completer._words_completer
    list(completer.get_completions(doc, CompleteEvent()))
    assert completer._words_completer is words_completer, \
        'the words completer instance must persist across calls'


def test_document_completer_python_uses_jedi(editor, editor_buffer, tmp_path):
    pytest = __import__('pytest')
    pytest.importorskip('jedi')

    p = tmp_path / 'mod.py'
    p.write_text('import os\n')
    editor.enable_jedi = True
    editor_buffer.location = str(p)

    completer = DocumentCompleter(editor, editor_buffer)
    doc = Document('import o', 8)
    # Iterate: this must exercise the Jedi path (both old `completions()`
    # and new `complete(line, column)` APIs) and not the words completer.
    names = [c.text for c in completer.get_completions(doc, CompleteEvent())]
    assert 'os' in names
    assert completer._words_completer._cached_key is None, \
        '.py files with Jedi enabled must not use the words completer'
