#!/usr/bin/env python3
# mypy: disable-error-code="import-not-found,misc"
"""
Reproducible micro-benchmarks backing the OKF v0.2 engineering plans in docs/:
  - docs/thai_support_plan.md
  - docs/speed_latency_plan.md

Run with:
    python tools/bench_plans.py
"""
from __future__ import annotations

import bisect
from collections.abc import Callable, Generator, Iterable
import importlib
import platform
import re
import time

import prompt_toolkit
from prompt_toolkit.completion import CompleteEvent, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text.base import StyleAndTextTuples
from prompt_toolkit.formatted_text.utils import split_lines
from prompt_toolkit.lexers.base import Lexer
from prompt_toolkit.lexers.pygments import (
    PygmentsLexer,
    SyncFromStart,
    SyntaxSync,
    _token_cache,
)


# ---------------------------------------------------------------------------
# Reference Thai cell-cluster & syllable helpers (from docs/thai_support_plan.md)
# ---------------------------------------------------------------------------

_THAI_COMBINING_CPS: frozenset[int] = frozenset({
    # Thai combining marks (U+0E30..U+0E4E)
    0x0E31,
    0x0E34, 0x0E35, 0x0E36, 0x0E37,
    0x0E38, 0x0E39, 0x0E3A,
    0x0E47, 0x0E48, 0x0E49, 0x0E4A, 0x0E4B, 0x0E4C, 0x0E4D, 0x0E4E,
    # Lao combining marks (U+0EB1..U+0ECD)
    0x0EB1,
    0x0EB4, 0x0EB5, 0x0EB6, 0x0EB7,
    0x0EB8, 0x0EB9, 0x0EBB, 0x0EBC,
    0x0EC8, 0x0EC9, 0x0ECA, 0x0ECB, 0x0ECC, 0x0ECD,
})


def is_thai_combining(cp: int) -> bool:
    return cp in _THAI_COMBINING_CPS


def is_sara_am(cp: int) -> bool:
    return cp == 0x0E33 or cp == 0x0EB3


def next_cell_offset(line: str, col: int, count: int = 1) -> int:
    n = len(line)
    if col >= n or count <= 0:
        return n
    if line.isascii():
        return min(n, col + count)
    idx = col
    comb = _THAI_COMBINING_CPS
    for _ in range(count):
        if idx >= n:
            break
        idx += 1
        while idx < n and ord(line[idx]) in comb:
            idx += 1
    return idx


def prev_cell_offset(line: str, col: int, count: int = 1) -> int:
    if col <= 0 or count <= 0:
        return 0
    if line.isascii():
        return max(0, col - count)
    idx = col
    comb = _THAI_COMBINING_CPS
    for _ in range(count):
        if idx <= 0:
            break
        idx -= 1
        while idx > 0 and ord(line[idx]) in comb:
            idx -= 1
    return idx


def cell_stops(line: str) -> list[int]:
    stops = [0]
    col = 0
    while col < len(line):
        col = next_cell_offset(line, col, 1)
        stops.append(col)
    return stops


class _DummyEditorBuffer:
    def __init__(self, location: str) -> None:
        self.location = location
        self.in_file_explorer_mode = False


class _StreamingPygmentsLexer(PygmentsLexer):
    """
    Subclass of prompt_toolkit's PygmentsLexer that streams `get_text_fragments()`
    lazily into `split_lines(...)` instead of materializing `list(get_text_fragments())`
    all the way to EOF (`prompt_toolkit/lexers/pygments.py:264`).
    """

    def lex_document(self, document: Document) -> Callable[[int], StyleAndTextTuples]:
        LineGenerator = Generator[tuple[int, StyleAndTextTuples], None, None]
        cache: dict[int, StyleAndTextTuples] = {}
        line_generators: dict[LineGenerator, int] = {}

        def get_syntax_sync() -> SyntaxSync:
            if self.sync_from_start():
                return SyncFromStart()
            return self.syntax_sync

        def find_closest_generator(i: int) -> LineGenerator | None:
            for generator, lineno in line_generators.items():
                if lineno < i and i - lineno < self.REUSE_GENERATOR_MAX_DISTANCE:
                    return generator
            return None

        def create_line_generator(
            start_lineno: int, column: int = 0
        ) -> LineGenerator:
            def get_text_fragments() -> Iterable[tuple[str, str]]:
                chunk_size = 100
                doc_lines = document.lines
                total = len(doc_lines)
                pos = start_lineno
                first = True
                while pos < total:
                    end = min(total, pos + chunk_size)
                    chunk = "\n".join(doc_lines[pos:end])
                    if end < total:
                        chunk += "\n"
                    if first and column:
                        chunk = chunk[column:]
                        first = False
                    for _, t, v in self.pygments_lexer.get_tokens_unprocessed(chunk):
                        yield _token_cache[t], v
                    pos = end

            yield from enumerate(split_lines(get_text_fragments()), start_lineno)

        def get_generator(i: int) -> LineGenerator:
            generator = find_closest_generator(i)
            if generator:
                return generator
            i = max(0, i - self.MIN_LINES_BACKWARDS)
            if i == 0:
                row, column = 0, 0
            else:
                row, column = get_syntax_sync().get_sync_start_position(document, i)
            generator = find_closest_generator(i)
            if not generator:
                generator = create_line_generator(row, column)
            if column:
                next(generator)
                row += 1
            line_generators[generator] = row
            return generator

        def get_line(i: int) -> StyleAndTextTuples:
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


class _CachedDocumentLexer:
    def __init__(self, editor_buffer: _DummyEditorBuffer) -> None:
        self.editor_buffer = editor_buffer
        self._cached_key: tuple[str | None, str] | None = None
        self._cached_lexer: Lexer | None = None

    def lex_document(self, document: Document) -> Callable[[int], StyleAndTextTuples]:
        location = self.editor_buffer.location
        key = (location, document.text[:100])
        if self._cached_key != key or self._cached_lexer is None:
            self._cached_key = key
            self._cached_lexer = _StreamingPygmentsLexer.from_filename(
                location or ".txt", sync_from_start=False
            )
        assert self._cached_lexer is not None
        get_line: Callable[[int], StyleAndTextTuples] = (
            self._cached_lexer.lex_document(document)
        )
        return get_line


class _SingletonCachedWordsCompleter:
    _WORD_RE = re.compile(r"\w+")

    def __init__(self) -> None:
        self._cached_key: tuple[int, int, str, str] | None = None
        self._other_words_sorted: list[str] = []

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
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
        if key != self._cached_key:
            other_words = set(self._WORD_RE.findall(prefix_text))
            other_words.update(self._WORD_RE.findall(suffix_text))
            self._other_words_sorted = sorted(other_words)
            self._cached_key = key

        neg_len = -len(word_before_cursor)
        yielded = {word_before_cursor}
        for w in sorted(set(self._WORD_RE.findall(doc_lines[row]))):
            if w.startswith(word_before_cursor) and w not in yielded:
                yielded.add(w)
                yield Completion(w, start_position=neg_len)

        words = self._other_words_sorted
        lo = bisect.bisect_left(words, word_before_cursor)
        n = len(words)
        while lo < n and words[lo].startswith(word_before_cursor):
            w = words[lo]
            if w not in yielded:
                yield Completion(w, start_position=neg_len)
            lo += 1


def bench_thai_plan() -> None:
    print("=== 1. Thai Cell-Cluster Verification & Micro-Benchmarks ===")
    samples = [
        ("ที่ดิน", [0, 3, 5, 6]),
        ("ผู้ใหญ่", [0, 3, 4, 5, 7]),
        ("เกาะ", [0, 1, 2, 3, 4]),
        ("น้ำ", [0, 2, 3]),
        ("กำ", [0, 1, 2]),
        ("ๆฯ", [0, 1, 2]),
    ]
    for word, expected in samples:
        actual = cell_stops(word)
        assert actual == expected, f"{word}: expected {expected}, got {actual}"
        cell_starts = actual[:-1]
        print(
            f"  {word!r:<10} len={len(word)} cells={len(cell_starts)} "
            f"cell_starts={cell_starts} stops_with_eol={actual}"
        )

    ascii_line = "def calculate_cursor_position(document, count=1): return 0"
    thai_line = "การเดินทางในที่ดินของผู้ใหญ่บ้านและการพัฒนาโปรแกรมภาษาไทยในเทอร์มินัล"
    iters = 200_000

    t0 = time.perf_counter_ns()
    for _ in range(iters):
        next_cell_offset(ascii_line, 10, 1)
    ascii_ns = (time.perf_counter_ns() - t0) / iters

    t0 = time.perf_counter_ns()
    for _ in range(iters):
        next_cell_offset(thai_line, 12, 1)
    thai_ns = (time.perf_counter_ns() - t0) / iters

    print(f"  next_cell_offset (ASCII fast-path): {ascii_ns:.1f} ns/call")
    print(f"  next_cell_offset (Thai cluster):    {thai_ns:.1f} ns/call\n")


def bench_speed_plan() -> None:
    print("=== 2. Speed & Latency Plan Micro-Benchmarks ===")
    pyvim_completion = importlib.import_module("pyvim.completion")
    pyvim_lexer = importlib.import_module("pyvim.lexer")
    pyvim_style = importlib.import_module("pyvim.style")
    DocumentWordsCompleter = pyvim_completion.DocumentWordsCompleter
    DocumentLexer = pyvim_lexer.DocumentLexer
    generate_built_in_styles = pyvim_style.generate_built_in_styles
    get_editor_style_by_name = pyvim_style.get_editor_style_by_name

    lines = [
        f"def func_{i}(x, y):\n    return x * {i} + y  # comment {i}"
        for i in range(2000)
    ]
    text = "\n".join(lines)
    doc = Document(text, cursor_position=0)
    _ = doc.lines  # pre-populate Document.lines as in normal rendering

    eb = _DummyEditorBuffer("sample.py")

    # P1a: DocumentLexer at top of 4,000-line file (viewport lines 0..39)
    uncached_lexer = DocumentLexer(eb)
    t0 = time.perf_counter()
    for _ in range(10):
        get_line = uncached_lexer.lex_document(doc)
        for row in range(40):
            get_line(row)
    p1_top_uncached_ms = (time.perf_counter() - t0) / 10 * 1000

    cached_lexer = _CachedDocumentLexer(eb)
    t0 = time.perf_counter()
    for _ in range(20):
        get_line = cached_lexer.lex_document(doc)
        for row in range(40):
            get_line(row)
    p1_top_cached_ms = (time.perf_counter() - t0) / 20 * 1000
    print(
        f"  P1a DocumentLexer (top 40 lines of 4000-line file): "
        f"current={p1_top_uncached_ms:.2f} ms -> cached+streaming={p1_top_cached_ms:.2f} ms"
    )

    # P1b: DocumentLexer at middle of 4,000-line file (viewport lines 2000..2039)
    t0 = time.perf_counter()
    for _ in range(10):
        get_line = uncached_lexer.lex_document(doc)
        for row in range(2000, 2040):
            get_line(row)
    p1_mid_uncached_ms = (time.perf_counter() - t0) / 10 * 1000

    t0 = time.perf_counter()
    for _ in range(20):
        get_line = cached_lexer.lex_document(doc)
        for row in range(2000, 2040):
            get_line(row)
    p1_mid_cached_ms = (time.perf_counter() - t0) / 20 * 1000
    print(
        f"  P1b DocumentLexer (middle 40 lines @ 2000 of 4000-line file): "
        f"current={p1_mid_uncached_ms:.2f} ms -> cached+streaming={p1_mid_cached_ms:.2f} ms"
    )

    # P1c: DocumentLexer at bottom of 4,000-line file (viewport lines 3960..3999)
    t0 = time.perf_counter()
    for _ in range(20):
        get_line = uncached_lexer.lex_document(doc)
        for row in range(3960, 4000):
            get_line(row)
    p1_bot_uncached_ms = (time.perf_counter() - t0) / 20 * 1000

    t0 = time.perf_counter()
    for _ in range(20):
        get_line = cached_lexer.lex_document(doc)
        for row in range(3960, 4000):
            get_line(row)
    p1_bot_cached_ms = (time.perf_counter() - t0) / 20 * 1000
    print(
        f"  P1c DocumentLexer (bottom 40 lines of 4000-line file): "
        f"current={p1_bot_uncached_ms:.2f} ms -> cached+streaming={p1_bot_cached_ms:.2f} ms"
    )

    # P2: Style loading
    t0 = time.perf_counter()
    styles = generate_built_in_styles()
    p2_eager_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    get_editor_style_by_name("vim")
    p2_lazy_ms = (time.perf_counter() - t0) * 1000
    print(
        f"  P2 Style init ({len(styles)} styles): "
        f"eager={p2_eager_ms:.2f} ms -> lazy('vim')={p2_lazy_ms:.2f} ms"
    )

    # P5: DocumentWordsCompleter fresh vs singleton line-cached
    docs = []
    for i in range(20):
        s = text + f"\ndef my_var_{i}"
        d = Document(s, cursor_position=len(s))
        _ = d.lines
        docs.append(d)
    ev = CompleteEvent()

    t0 = time.perf_counter()
    for d in docs:
        list(DocumentWordsCompleter().get_completions(d, ev))
    p5_uncached_ms = (time.perf_counter() - t0) / len(docs) * 1000

    singleton_comp = _SingletonCachedWordsCompleter()
    list(singleton_comp.get_completions(docs[0], ev))  # warm non-cursor lines
    t0 = time.perf_counter()
    for d in docs:
        list(singleton_comp.get_completions(d, ev))
    p5_cached_ms = (time.perf_counter() - t0) / len(docs) * 1000
    print(
        f"  P5 DocumentWordsCompleter (4000 lines, typing on current line): "
        f"fresh={p5_uncached_ms:.2f} ms -> singleton_cached={p5_cached_ms:.3f} ms"
    )


if __name__ == "__main__":
    print(
        f"Python {platform.python_version()} ({platform.machine()}), "
        f"prompt_toolkit {prompt_toolkit.__version__}\n"
    )
    bench_thai_plan()
    bench_speed_plan()
