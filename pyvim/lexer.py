from typing import Any, Dict

from prompt_toolkit.formatted_text.utils import split_lines
from prompt_toolkit.lexers import Lexer, PygmentsLexer, SimpleLexer
from pygments.lexer import RegexLexer
from pygments.token import Token

try:
    # Streaming sync support (prompt_toolkit >= 3.0.35, used by P1).
    from prompt_toolkit.lexers.pygments import RegexSync
    from prompt_toolkit.styles.pygments import pygments_token_to_classname

    _STREAMING_AVAILABLE = True
except ImportError:
    _STREAMING_AVAILABLE = False

__all__ = ('DocumentLexer',)

# Cache from Pygments token type to prompt_toolkit style class name.
# (`pygments_token_to_classname` does a chain of `isinstance` checks, which
# adds up over hundreds of tokens per keystroke.)
_STYLE_TOKEN_CACHE: Dict[Any, str] = {}


def _style_classname(token):
    try:
        return _STYLE_TOKEN_CACHE[token]
    except KeyError:
        style_cls = 'class:' + pygments_token_to_classname(token)
        _STYLE_TOKEN_CACHE[token] = style_cls
        return style_cls


class DocumentLexer(Lexer):
    """
    Lexer that depending on the filetype, uses another pygments lexer.

    The Pygments lexer instance (and its `RegexSync`) is cached per location,
    so it is only looked up in the Pygments registry when the buffer location
    changes. The document itself is lexed lazily/streaming from the sync
    position near the cursor, instead of eagerly tokenizing everything up to
    EOF on every edit.
    """

    MIN_LINES_BACKWARDS = 50
    REUSE_GENERATOR_MAX_DISTANCE = 100

    def __init__(self, editor_buffer):
        self.editor_buffer = editor_buffer
        self._cached_location = None
        self._pygments_lexer = None
        self._syntax_sync = None
        self._directory_lexer = None

    def invalidation_hash(self):
        # Invalidate the fragment cache when the buffer location (or file
        # explorer mode) changes, e.g. after `:w newname.py`.
        return (
            self.editor_buffer.location,
            getattr(self.editor_buffer, 'in_file_explorer_mode', False),
        )

    def _get_directory_lexer(self):
        """
        Cached `PygmentsLexer` for directory listing buffers.

        Creating a `PygmentsLexer` scans the Pygments registry, so doing
        that per keystroke in file-explorer mode paid ~0.6 ms for every
        keypress (docs/bugs/030.md).
        """
        if self._directory_lexer is None:
            self._directory_lexer = PygmentsLexer(DirectoryListingLexer, sync_from_start=False)
        return self._directory_lexer

    def _ensure_lexer(self, location):
        """Load/cache the Pygments lexer for this location."""
        if self._cached_location == location:
            # Already looked up: reuse the result (including a cached miss,
            # so we don't re-scan the Pygments registry on every edit).
            return self._pygments_lexer is not None

        from pygments.lexers import get_lexer_for_filename
        from pygments.util import ClassNotFound

        try:
            lexer_inst = get_lexer_for_filename(
                location, stripnl=False, stripall=False, ensurenl=False
            )
        except ClassNotFound:
            self._cached_location = location
            self._pygments_lexer = None
            self._syntax_sync = None
            return False

        self._cached_location = location
        self._pygments_lexer = lexer_inst
        self._syntax_sync = RegexSync.from_pygments_lexer_cls(lexer_inst.__class__)
        return True

    def lex_document(self, document):
        """
        Call the lexer and return a get_tokens_for_line function.
        """
        location = self.editor_buffer.location

        if location:
            if getattr(self.editor_buffer, 'in_file_explorer_mode', False):
                return self._get_directory_lexer().lex_document(document)

            if not _STREAMING_AVAILABLE:
                # Fallback for older prompt_toolkit versions.
                return PygmentsLexer.from_filename(location, sync_from_start=False).lex_document(
                    document
                )

            if self._cached_location != location or self._pygments_lexer is None:
                if not self._ensure_lexer(location):
                    # No Pygments lexer found for this location (or Pygments
                    # could not guess one): fall back to no highlighting.
                    return SimpleLexer().lex_document(document)

            pygments_lexer = self._pygments_lexer
            syntax_sync = self._syntax_sync

            cache = {}
            line_generators = {}

            def create_line_generator(start_lineno, column=0):
                def get_text_fragments():
                    start_index = document.translate_row_col_to_index(start_lineno, column)
                    text = document.text[start_index:]
                    for _, t, v in pygments_lexer.get_tokens_unprocessed(text):
                        yield _style_classname(t), v

                # NOTE: `split_lines` is iterated lazily here (no `list()`):
                # `get_tokens_unprocessed` is a single continuous generator
                # starting from `start_lineno`, so multiline
                # strings/docstrings are never split across sync chunks, and
                # text past the visible area is only lexed when requested.
                yield from enumerate(split_lines(get_text_fragments()), start_lineno)

            def find_closest_generator(i):
                for generator, lineno in line_generators.items():
                    if lineno < i and i - lineno < self.REUSE_GENERATOR_MAX_DISTANCE:
                        return generator
                return None

            def get_generator(i):
                # Reuse a generator that already covers `i` when possible;
                # only create a fresh one (from the sync position) otherwise:
                # the reuse keeps each render frame to a handful of lexed
                # tokens instead of re-lexing per visible line.
                generator = find_closest_generator(i)
                if generator:
                    return generator
                start = max(0, i - self.MIN_LINES_BACKWARDS)
                if start == 0:
                    row, column = 0, 0
                else:
                    row, column = syntax_sync.get_sync_start_position(document, start)
                generator = create_line_generator(row, column)
                if column:
                    next(generator)
                    row += 1
                line_generators[generator] = row
                return generator

            def get_line(i):
                try:
                    return cache[i]
                except KeyError:
                    generator = get_generator(i)
                    for num, line in generator:
                        cache[num] = line
                        if num == i:
                            line_generators[generator] = i
                            if num + 1 in cache:
                                del cache[num + 1]
                            return cache[num]
                    return []

            return get_line

        return SimpleLexer().lex_document(document)


_DirectoryListing = Token.DirectoryListing


class DirectoryListingLexer(RegexLexer):
    """
    Highlighting of directory listings.
    """

    name = 'directory-listing'
    tokens = {
        str('root'): [  # Conversion to `str` because of Pygments on Python 2.
            (r'^".*', _DirectoryListing.Header),
            (r'^\.\./$', _DirectoryListing.ParentDirectory),
            (r'^\./$', _DirectoryListing.CurrentDirectory),
            (r'^[^"].*/$', _DirectoryListing.Directory),
            (r'^[^"].*\.(txt|rst|md)$', _DirectoryListing.Textfile),
            (r'^[^"].*\.(py)$', _DirectoryListing.PythonFile),
            (r'^[^"].*\.(pyc|pyd)$', _DirectoryListing.Tempfile),
            (r'^\..*$', _DirectoryListing.Dotfile),
        ]
    }
