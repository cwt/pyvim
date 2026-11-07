#!/usr/bin/env python3
# mypy: disable-error-code="import-not-found,import-untyped,misc"
"""
Reproducible verification & micro-benchmarks backing the OKF v0.2 plans in docs/:
  - docs/thai_support_plan.md
  - docs/speed_latency_plan.md

Everything is verified against the *shipped* modules (pyvim.thai, pyvim.lexer,
pyvim.style, pyvim.completion) instead of duplicated copies, so the printed
figures always describe the code in this repository (see docs/bugs/008.md).

Run with:
    python tools/bench_plans.py
"""

from __future__ import annotations

import platform
import time

import prompt_toolkit
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document
from prompt_toolkit.lexers.pygments import PygmentsLexer
from pygments.styles import get_all_styles

import pyvim.completion as pyvim_completion
import pyvim.lexer as pyvim_lexer
import pyvim.style as pyvim_style
import pyvim.thai as pyvim_thai


class _DummyEditorBuffer:
    def __init__(self, location: str) -> None:
        self.location = location
        self.in_file_explorer_mode = False


# ---------------------------------------------------------------------------
# 1. Thai & Lao cell-cluster / syllable verification (pyvim.thai)
# ---------------------------------------------------------------------------


def bench_thai_plan() -> None:
    thai = pyvim_thai
    print("=== 1. Thai & Lao Cell-Cluster / Syllable Verification & Benchmarks ===")
    assert len(thai._THAI_COMBINING_CPS) == 34, "Expected 16 Thai + 18 Lao combining marks"
    for cp in (0x0EBA, 0x0EC7, 0x0ECE):
        assert thai.is_thai_combining(cp), f"Missing Lao combining mark U+{cp:04X}"
        assert thai.is_combining_char(chr(cp)), f"is_combining_char failed for U+{cp:04X}"
    assert thai.is_combining_char("\u0301"), "Expected Latin combining U+0301 to be combining"
    assert thai.is_combining_char("") is False

    # Verify prev_cell_offset from both cell boundaries and mid-cluster positions:
    assert thai.prev_cell_offset("ที่ดิน", 4, 1) == 3, "Mid-cluster col=4 must snap to 3, not 0"
    assert thai.prev_cell_offset("ที่ดิน", 3, 1) == 0
    assert thai.prev_cell_offset("ที่ดิน", 5, 1) == 3

    samples = [
        ("ที่ดิน", [0, 3, 5, 6], 3),
        ("ผู้ใหญ่", [0, 3, 4, 5, 7], 3),
        ("เกาะ", [0, 1, 2, 3, 4], 4),
        ("น้ำ", [0, 2, 3], 3),
        ("กำ", [0, 1, 2], 2),
        ("ธรรม", [0, 1, 2, 3, 4], 3),  # Ro Han (ธรร = 3 codepoints, followed by ม)
        ("ดีๆ", [0, 2, 3], 3),  # Right-attaching ๆ attached to preceding syllable ดี
        ("ๆฯ", [0, 1, 2], 1),  # Standalone right-attaching symbols
        ("ທີ່ດິນ", [0, 3, 5, 6], 3),  # Lao: ທ + ◌ີ + ◌່ | ດ + ◌ິ | ນ
    ]
    for word, expected_stops, expected_first_cluster_end in samples:
        actual = thai.cell_stops(word)
        assert actual == expected_stops, f"{word}: expected {expected_stops}, got {actual}"

        # Verify reverse traversal via prev_cell_offset matches cell_starts in reverse:
        rev_starts: list[int] = []
        c = len(word)
        while c > 0:
            c = thai.prev_cell_offset(word, c, 1)
            rev_starts.append(c)
        assert rev_starts[::-1] == actual[:-1], (
            f"{word}: reverse starts {rev_starts[::-1]} != {actual[:-1]}"
        )
        cluster_end = thai.find_thai_cluster_end(word, 0)
        assert cluster_end == expected_first_cluster_end, (
            f"{word}: expected first syllable end {expected_first_cluster_end}, got {cluster_end}"
        )
        print(
            f"  {word!r:<10} len={len(word)} cells={len(actual) - 1} "
            f"cell_starts={actual[:-1]} stops={actual} first_syllable_end={cluster_end}"
        )

    ascii_line = "def calculate_cursor_position(document, count=1): return 0"
    thai_line = "การเดินทางในที่ดินของผู้ใหญ่บ้านและการพัฒนาโปรแกรมภาษาไทยในเทอร์มินัล"
    iters = 200_000

    t0 = time.perf_counter_ns()
    for _ in range(iters):
        thai.next_cell_offset(ascii_line, 10, 1)
    ascii_ns = (time.perf_counter_ns() - t0) / iters

    t0 = time.perf_counter_ns()
    for _ in range(iters):
        thai.next_cell_offset(thai_line, 12, 1)
    thai_ns = (time.perf_counter_ns() - t0) / iters

    print(f"  next_cell_offset (ASCII fast-path): {ascii_ns:.1f} ns/call")
    print(f"  next_cell_offset (Thai cluster):    {thai_ns:.1f} ns/call\n")


# ---------------------------------------------------------------------------
# 2. Speed plan verification (pyvim.lexer / pyvim.style / pyvim.completion)
# ---------------------------------------------------------------------------


def bench_speed_plan() -> None:
    print("=== 2. Speed & Latency Plan Verification & Micro-Benchmarks ===")
    DocumentWordsCompleter = pyvim_completion.DocumentWordsCompleter
    DocumentLexer = pyvim_lexer.DocumentLexer
    generate_built_in_styles = pyvim_style.generate_built_in_styles
    get_editor_style_by_name = pyvim_style.get_editor_style_by_name

    # P2: the shipped mapping is lazy - measure what an Editor pays at startup.
    t0 = time.perf_counter()
    style_names = list(get_all_styles())
    p2_get_all_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    styles = generate_built_in_styles()
    _ = [styles[name] for name in get_all_styles()]
    p2_eager_ms = p2_get_all_ms + (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    _ = get_editor_style_by_name("vim")
    p2_startup_ms = (time.perf_counter() - t0) * 1000
    assert len(styles) == len(style_names), "shipped styles mapping must be complete"

    # Build a 4,000-line Python file including a 50-line multiline docstring
    # spanning lines 80..130:
    lines: list[str] = []
    for i in range(2000):
        if i == 40:
            lines.append('def doc_func():\n    """start multiline docstring')
        elif 40 < i < 65:
            lines.append(f"    inside multiline docstring {i}\n    still string {i}")
        elif i == 65:
            lines.append('    end multiline docstring"""\n    return 42')
        else:
            lines.append(f"def func_{i}(x, y):\n    return x * {i} + y  # comment {i}")
    text = "\n".join(lines)
    doc = Document(text, cursor_position=0)
    _ = doc.lines

    eb = _DummyEditorBuffer("sample.py")
    document_lexer = DocumentLexer(eb)

    # Verify 100% token parity across the multiline docstring (lines 75..140):
    ref_get_line = PygmentsLexer.from_filename("sample.py", sync_from_start=False).lex_document(doc)
    stream_get_line = document_lexer.lex_document(doc)
    for row in range(75, 140):
        assert stream_get_line(row) == ref_get_line(row), (
            f"Token mismatch at multiline string row {row}"
        )

    # P1: per-frame lexing latency of the shipped (cached + streaming) lexer.
    def time_rows(row_from: int, row_to: int, runs: int) -> float:
        t0 = time.perf_counter()
        for _ in range(runs):
            get_line = document_lexer.lex_document(doc)
            for row in range(row_from, row_to):
                get_line(row)
        return (time.perf_counter() - t0) / runs * 1000

    p1_top_ms = time_rows(0, 40, 20)
    p1_mid_ms = time_rows(2000, 2040, 20)
    p1_bot_ms = time_rows(3960, 4000, 20)
    print("  Verified P1 multiline docstring token parity (lines 75..140): PASS")
    print(f"    P1a DocumentLexer (top 40 of 4000-line file): {p1_top_ms:.2f} ms")
    print(f"    P1b DocumentLexer (mid 40 lines @ 2000):      {p1_mid_ms:.2f} ms")
    print(f"    P1c DocumentLexer (bottom 40 of 4000-line):   {p1_bot_ms:.2f} ms")

    print(
        f"  P2 Style init ({len(styles)} styles): "
        f"cold_eager={p2_eager_ms:.2f} ms (cold get_all_styles={p2_get_all_ms:.2f} ms) "
        f"-> deferred startup={p2_startup_ms:.2f} ms"
    )

    # P3: DocumentWordsCompleter fresh vs singleton (line-cached) latency.
    docs = []
    for i in range(20):
        s = text + f"\ndef my_var_{i}"
        d = Document(s, cursor_position=len(s))
        _ = d.lines
        docs.append(d)
    ev = CompleteEvent()

    # "fresh" = a new completer instance per keystroke (pre-P3 behaviour):
    t0 = time.perf_counter()
    for d in docs:
        fresh = DocumentWordsCompleter()
        list(fresh.get_completions(d, ev))
    p3_fresh_ms = (time.perf_counter() - t0) / len(docs) * 1000

    # "singleton" = the DocumentCompleter-managed instance (P3 behaviour):
    singleton = DocumentWordsCompleter()
    list(singleton.get_completions(docs[0], ev))  # warm the non-cursor-line cache
    t0 = time.perf_counter()
    for d in docs:
        list(singleton.get_completions(d, ev))
    p3_cached_ms = (time.perf_counter() - t0) / len(docs) * 1000
    print(
        f"  P3 DocumentWordsCompleter (4000 lines, typing on current line): "
        f"fresh={p3_fresh_ms:.2f} ms -> singleton_cached={p3_cached_ms:.3f} ms"
    )


if __name__ == "__main__":
    print(
        f"Python {platform.python_version()} ({platform.machine()}), "
        f"prompt_toolkit {prompt_toolkit.__version__}\n"
    )
    bench_thai_plan()
    bench_speed_plan()
