"""Regression + locality tests for the Thai/Lao word-motion engine.

Pins the exact pre-optimization semantics of ``pyvim.thai`` word motions
(captured at hg rev 166, Tier-2 segmentation with libthai disabled) and
verifies the per-line span cache: word motions must scan only the lines
they actually touch, not the whole document (``docs/bugs/001.md``).
"""

from __future__ import annotations

import json
import pathlib

from prompt_toolkit.document import Document

import pyvim.thai as thai

# Captured from the whole-document scan implementation before introducing
# the per-line span cache (Tier-2 segmentation, ``_get_libthai`` disabled).
_FIXTURE = json.loads(
    (pathlib.Path(__file__).parent / "data" / "thai_motion_fixture.json").read_text("utf-8")
)

_TEXT = "\n".join(
    [
        "ที่ดิน",
        "",
        "abc  def x",
        "ผู้ใหญ่ บ้าน",
        "เกาะ",
        "lao ນ້ຳ ກຳ",
        "\t001",
        "alpha_beta=a/b*x",
        "ธรรม ดีๆ ๆฯ",
    ]
)


def _plain_doc(monkeypatch):
    """A Document over the fixture text with Tier-2 (deterministic) breaking."""
    monkeypatch.setattr(thai, "_get_libthai", lambda: None)
    # Drop spans cached under Tier-1 (or other) segmentation by earlier tests.
    thai._word_spans_for_line.cache_clear()
    return Document(_TEXT, 0)


def test_motion_results_match_pre_optimization_fixture(monkeypatch):
    _ = _plain_doc(monkeypatch)
    fns = {
        "next_begin": lambda d: d.find_next_word_beginning(1),
        "next_begin_2": lambda d: d.find_next_word_beginning(2),
        "next_end": lambda d: d.find_next_word_ending(1),
        "next_end_ipc": lambda d: d.find_next_word_ending(include_current_position=True),
        "prev_begin": lambda d: d.find_previous_word_beginning(1),
        "prev_end": lambda d: d.find_previous_word_ending(1),
        "boundaries": lambda d: d.find_boundaries_of_current_word(),
        "boundaries_tw": lambda d: d.find_boundaries_of_current_word(
            include_trailing_whitespace=True
        ),
    }
    word_fns = {
        "next_begin": lambda d: d.find_next_word_beginning(1, WORD=True),
        "next_end": lambda d: d.find_next_word_ending(1, WORD=True),
        "prev_begin": lambda d: d.find_previous_word_beginning(1, WORD=True),
        "prev_end": lambda d: d.find_previous_word_ending(1, WORD=True),
        "boundaries": lambda d: d.find_boundaries_of_current_word(WORD=True),
    }
    for rec in _FIXTURE["records"]:
        doc = Document(_TEXT, cursor_position=rec["pos"])
        assert doc.cursor_position_row == rec["row"]
        assert doc.cursor_position_col == rec["col"]
        for name, fn in fns.items():
            got = fn(doc)
            expected = rec[name]
            if isinstance(expected, list):  # boundaries come back as tuples
                got = list(got)
            assert got == expected, f"{name} @ {rec['pos']}: {got!r} != {expected!r}"
    for rec in _FIXTURE["word_records"]:
        doc = Document(_TEXT, cursor_position=rec["pos"])
        for name, fn in word_fns.items():
            got = fn(doc)
            expected = rec[name]
            if isinstance(expected, list):
                got = list(got)
            assert got == expected, f"WORD {name} @ {rec['pos']}: {got!r} != {expected!r}"


def test_only_touched_lines_are_scanned_forward(monkeypatch):
    # A 400-line mostly-ASCII document: one ``w`` step must not touch more
    # lines than it can reach (cursor line + at most the next one).
    _ = _plain_doc(monkeypatch)
    lines = ["ที่ดิน หมู"] + [f"word{i} word{i + 1} word{i + 2}" for i in range(400)]
    doc = Document("\n".join(lines), cursor_position=0)
    thai._word_spans_for_line.cache_clear()
    before = thai._word_spans_for_line.cache_info().misses
    result = doc.find_next_word_beginning(1)
    misses = thai._word_spans_for_line.cache_info().misses - before

    # The first qualifying span starts on the cursor line (ดิ, at col 3):
    assert result == 3
    # The Thai line splits into two chunks (ที่ดิน, หมู) but the motion must
    # only scan the cursor line (at most plus the next one).
    assert misses <= 2, f"expected cursor-line locality, scanned {misses} lines"


def test_only_touched_lines_are_scanned_backward(monkeypatch):
    _ = _plain_doc(monkeypatch)
    lines = [f"word{i} word{i + 1}" for i in range(400)]
    lines.append("เกาะ")
    text = "\n".join(lines)
    doc = Document(text, cursor_position=len(text))
    thai._word_spans_for_line.cache_clear()
    before = thai._word_spans_for_line.cache_info().misses
    doc.find_previous_word_beginning(1)
    doc.find_previous_word_ending(1)
    misses = thai._word_spans_for_line.cache_info().misses - before

    # Both motions operate on the last line only.
    assert misses <= 2, f"expected cursor-line locality, scanned {misses} lines"


def test_line_span_cache_is_reused_between_presses(monkeypatch):
    _ = _plain_doc(monkeypatch)
    doc = Document(_TEXT, 0)
    thai._word_spans_for_line.cache_clear()
    doc.find_next_word_beginning(1)
    misses_first = thai._word_spans_for_line.cache_info().misses
    assert misses_first >= 1

    doc.find_next_word_beginning(1)
    doc.find_next_word_ending(1)
    info = thai._word_spans_for_line.cache_info()
    assert info.hits >= 1, "repeat presses on unchanged text must hit the line cache"


def test_line_local_matches_full_text_scan_equivalence(monkeypatch):
    """Line-local results must equal the reference whole-text composition."""
    _ = _plain_doc(monkeypatch)
    text = "ที่ดิน\nabc def\n\nเกาะ น้ำ\nx y z\n\t\nธรรม"
    spans = thai._iter_word_spans(text)

    def ref_next_begin(pos):
        matched = 0
        for start, _end in spans:
            if start > pos:
                matched += 1
                if matched == 1:
                    return start - pos
        return None

    def ref_prev_begin(pos):
        matched = 0
        for start, _end in reversed(spans):
            if start < pos:
                matched += 1
                if matched == 1:
                    return start - pos
        return None

    def multiple(ref):
        matched = 0
        for item in ref:
            if item[0]:
                matched += 1
                if matched == 1:
                    return item[1]
        return None

    def ref_next_end_ipc(pos):
        # ``find_next_word_ending(include_current_position=True)`` semantics:
        # the first span whose exclusive end is beyond the cursor.
        return multiple((end > pos, end - pos) for _s, end in spans)

    def ref_next_end(pos):
        # ``include_current_position=False``: the first span whose last cell
        # cluster starts beyond the cursor.
        return multiple((thai.prev_cell_offset(text, end, 1) > pos, end - pos) for _s, end in spans)

    def ref_prev_end(pos):
        matched = 0
        for _start, end in reversed(spans):
            if end <= pos:
                matched += 1
                if matched == 1:
                    return end - pos
        return None

    for pos in range(len(text) + 1):
        doc = Document(text, cursor_position=pos)
        assert doc.find_next_word_beginning(1) == ref_next_begin(pos), f"next_begin @ {pos}"
        assert doc.find_previous_word_beginning(1) == ref_prev_begin(pos), f"prev_begin @ {pos}"
        assert doc.find_next_word_ending(include_current_position=True) == ref_next_end_ipc(pos), (
            f"next_end(ipc) @ {pos}"
        )
        assert doc.find_next_word_ending(count=1) == ref_next_end(pos), f"next_end @ {pos}"
        assert doc.find_previous_word_ending(1) == ref_prev_end(pos), f"prev_end @ {pos}"


def test_full_scan_composition_keeps_spans_within_lines():
    # Guard the reference composition against drift: spans must stay within
    # their own line (never include the newline).
    text = "abc\nที่ดิน\nx"
    line_starts = [0, 4, 11]
    for row, line_start in enumerate(line_starts):
        line = text.split("\n")[row]
        for s, e in thai._word_spans_for_line(line):
            assert 0 <= s <= len(line) and s < e <= len(line), (row, s, e)
            assert text[line_start + s : line_start + e] == line[s:e]
