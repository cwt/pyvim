import bisect
import re
import weakref
from importlib.util import find_spec

from prompt_toolkit.completion import Completer, Completion

__all__ = (
    'DocumentCompleter',
    'DocumentWordsCompleter',
)

# Shape of the jedi API, cached on first use: `Script()` accepted
# `line`/`column` keyword arguments until jedi 0.20 (docs/bugs/030.md).
_JEDI_TAKES_COLUMN = None


def _jedi_available():
    """
    Return whether the optional jedi dependency is importable.

    `importlib.util.find_spec` is a cheap, side-effect-free probe (it does
    not import jedi - importing jedi is slow and must stay deferred to the
    first Python completion), so this stays resilient even when jedi is
    missing from the environment.
    """
    try:
        return find_spec('jedi') is not None
    except (ImportError, ValueError):
        # `find_spec` raises ValueError for e.g. 'sys' masked names;
        # treat as unavailable. (ImportError covers pkgutil-only setups.)
        return False


class DocumentWordsCompleter(Completer):
    """
    Completer that completes on words that appear already in the open
    document.

    Words from the *non-cursor* lines are cached (keyed on the document
    length, cursor row and the text around the cursor line) and kept sorted,
    so that while typing on the current line each keystroke only regex-scans
    that one line and binary-searches the pre-sorted word list. This completer
    is most effective as a persistent instance (see `DocumentCompleter`),
    where the cache actually gets a chance to hit.
    """

    _WORD_RE = re.compile(r'[\w\u0e31-\u0e3a\u0e47-\u0e4e\u0eb1-\u0ebc\u0ec7-\u0ece]+')

    def __init__(self):
        self._cached_key = None
        self._other_words_sorted = []

    def get_completions(self, document, complete_event):
        word_before_cursor = document.get_word_before_cursor()
        if not word_before_cursor:
            return

        row = document.cursor_position_row
        doc_lines = document.lines
        line_start = document.translate_row_col_to_index(row, 0)
        line_end = line_start + len(doc_lines[row])
        prefix_text = document.text[:line_start]
        suffix_text = document.text[line_end:]
        key = (len(doc_lines), row, prefix_text, suffix_text)

        # Cache the words from all *other* lines; only recompute them when
        # the surrounding text (or the cursor line) changed.
        if key != self._cached_key:
            other_words = set(self._WORD_RE.findall(prefix_text))
            other_words.update(self._WORD_RE.findall(suffix_text))
            self._other_words_sorted = sorted(other_words)
            self._cached_key = key

        neg_len = -len(word_before_cursor)
        yielded = {word_before_cursor}

        # First: words from the current (cursor) line.
        for w in sorted(set(self._WORD_RE.findall(doc_lines[row]))):
            if w.startswith(word_before_cursor) and w not in yielded:
                yielded.add(w)
                yield Completion(w, start_position=neg_len)

        # Then: the cached words from all other lines, via binary search.
        words = self._other_words_sorted
        lo = bisect.bisect_left(words, word_before_cursor)
        n = len(words)
        while lo < n and words[lo].startswith(word_before_cursor):
            w = words[lo]
            if w not in yielded:
                yielded.add(w)
                yield Completion(w, start_position=neg_len)
            lo += 1


class DocumentCompleter(Completer):
    """
    This is the general completer for EditorBuffer completions.
    Depending on the file type and settings, it selects another completer to
    call.
    """

    def __init__(self, editor, editor_buffer):
        # (Weakrefs, they are already pointing to us.)
        self._editor_ref = weakref.ref(editor)
        self._editor_buffer_ref = weakref.ref(editor_buffer)

        # Persistent word completer, so that its non-cursor-line word cache
        # survives across completion invocations.
        self._words_completer = DocumentWordsCompleter()

    def get_completions(self, document, complete_event):
        editor = self._editor_ref()
        location = self._editor_buffer_ref().location or '.txt'

        # Select completer. jedi is optional (not in install_requires): when
        # it is missing, fall back to the words completer instead of crashing
        # with an ImportError on the first Tab press (docs/bugs/003.md).
        if location.endswith('.py') and editor.enable_jedi and _jedi_available():
            completer = _PythonCompleter(location)
        else:
            completer = self._words_completer

        # Call completer.
        return completer.get_completions(document, complete_event)


class _PythonCompleter(Completer):
    """
    Wrapper around the Jedi completion engine.
    """

    def __init__(self, location):
        self.location = location

    def get_completions(self, document, complete_event):
        script = self._get_jedi_script_from_document(document)
        if script:
            try:
                if hasattr(script, 'complete'):
                    # jedi >= 0.20: the cursor position moved from the
                    # `Script()` constructor to `Script.complete()`.
                    completions = script.complete(
                        document.cursor_position_row + 1, document.cursor_position_col
                    )
                else:
                    # jedi < 0.20.
                    completions = script.completions()
            except TypeError:
                # Issue #9: bad syntax causes completions() to fail in jedi.
                # https://github.com/jonathanslenders/python-prompt-toolkit/issues/9
                # (`Script.complete()` also raises TypeError on bad syntax
                # in jedi >= 0.20.)
                pass
            except UnicodeDecodeError:
                # Issue #43: UnicodeDecodeError on OpenBSD
                # https://github.com/jonathanslenders/python-prompt-toolkit/issues/43
                pass
            except AttributeError:
                # Jedi issue #513: https://github.com/davidhalter/jedi/issues/513
                pass
            except ValueError:
                # Jedi issue: "ValueError: invalid \x escape"
                pass
            except KeyError:
                # Jedi issue: "KeyError: u'a_lambda'."
                # https://github.com/jonathanslenders/ptpython/issues/89
                pass
            except IOError:
                # Jedi issue: "IOError: No such file or directory."
                # https://github.com/jonathanslenders/ptpython/issues/71
                pass
            else:
                for c in completions:
                    yield Completion(
                        c.name_with_symbols,
                        len(c.complete) - len(c.name_with_symbols),
                        display=c.name_with_symbols,
                    )

    def _get_jedi_script_from_document(self, document):
        import inspect

        try:
            import jedi  # We keep this import in-line, to improve start-up time.
            # Importing Jedi is 'slow'.
        except ImportError:
            # jedi is an optional dependency; completer selection already
            # falls back to the words completer when it is missing.
            return None

        # `Script()` accepted `line`/`column` keyword arguments until jedi
        # 0.20; detect which API we are talking to. The answer is constant
        # for the whole process, so introspect jedi only once per session
        # (docs/bugs/030.md).
        global _JEDI_TAKES_COLUMN
        if _JEDI_TAKES_COLUMN is None:
            _JEDI_TAKES_COLUMN = 'column' in inspect.signature(jedi.Script).parameters
        takes_column = _JEDI_TAKES_COLUMN

        try:
            if takes_column:
                return jedi.Script(
                    document.text,
                    column=document.cursor_position_col,
                    line=document.cursor_position_row + 1,
                    path=self.location,
                )
            else:
                return jedi.Script(document.text, path=self.location)
        except ValueError:
            # Invalid cursor position.
            # ValueError('`column` parameter is not in a valid range.')
            return None
        except AttributeError:
            # Workaround for #65: https://github.com/jonathanslenders/python-prompt-toolkit/issues/65
            # See also: https://github.com/davidhalter/jedi/issues/508
            return None
        except IndexError:
            # Workaround Jedi issue #514: for https://github.com/davidhalter/jedi/issues/514
            return None
        except KeyError:
            # Workaround for a crash when the input is "u'", the start of a unicode string.
            return None
