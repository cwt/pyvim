"""
Unit tests for Thai (`U+0E00..U+0E7F`) and Lao (`U+0E80..U+0EFF`) script support
(`pyvim/thai.py`, `pyvim/key_bindings.py`, `pyvim/editor.py`).
"""

from __future__ import annotations

import prompt_toolkit.renderer as ptk_renderer
import pytest
from prompt_toolkit.application.current import set_app
from prompt_toolkit.data_structures import Point, Size
from prompt_toolkit.document import Document
from prompt_toolkit.input import DummyInput
from prompt_toolkit.key_binding.key_processor import KeyPress
from prompt_toolkit.key_binding.vi_state import InputMode
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.mouse_handlers import MouseHandlers
from prompt_toolkit.layout.screen import Char, Screen, WritePosition
from prompt_toolkit.output import ColorDepth, DummyOutput
from prompt_toolkit.styles import DummyStyle, DummyStyleTransformation

import pyvim.thai as thai
from pyvim.editor import Editor
from pyvim.thai import (
    _SARA_AM_POISON,
    _THAI_COMBINING_CPS,
    _sanitize_and_invalidate_sara_am,
    cell_starts,
    cell_stops,
    find_thai_cluster_end,
    find_thai_word_breaks,
    install_prompt_toolkit_thai_patches,
    is_combining_char,
    is_lao,
    is_sara_am,
    is_thai,
    is_thai_base,
    is_thai_combining,
    is_thai_following_vowel,
    is_thai_or_lao,
    next_cell_offset,
    prev_cell_offset,
    snap_to_cell_start,
)


def _feed_keys(editor: Editor, *keys: str | Keys) -> None:
    """Feed a sequence of keys through `editor.application.key_processor`."""
    kp = editor.application.key_processor
    with set_app(editor.application):
        for k in keys:
            if isinstance(k, Keys):
                kp.feed(KeyPress(k))
            else:
                kp.feed(KeyPress(k))
        kp.process_keys()


def _make_editor_with_text(text: str, cursor_position: int = 0) -> Editor:
    editor = Editor(output=DummyOutput(), input=DummyInput())
    editor.load_initial_files([None])
    editor.sync_with_prompt_toolkit()
    editor.application.vi_state.input_mode = InputMode.NAVIGATION
    buff = editor.current_editor_buffer.buffer
    buff.document = Document(text, cursor_position=cursor_position)
    return editor


def test_all_34_thai_lao_combining_marks() -> None:
    expected_thai = {
        0x0E31,
        0x0E34,
        0x0E35,
        0x0E36,
        0x0E37,
        0x0E38,
        0x0E39,
        0x0E3A,
        0x0E47,
        0x0E48,
        0x0E49,
        0x0E4A,
        0x0E4B,
        0x0E4C,
        0x0E4D,
        0x0E4E,
    }
    expected_lao = {
        0x0EB1,
        0x0EB4,
        0x0EB5,
        0x0EB6,
        0x0EB7,
        0x0EB8,
        0x0EB9,
        0x0EBA,
        0x0EBB,
        0x0EBC,
        0x0EC7,
        0x0EC8,
        0x0EC9,
        0x0ECA,
        0x0ECB,
        0x0ECC,
        0x0ECD,
        0x0ECE,
    }
    assert len(expected_thai) == 16
    assert len(expected_lao) == 18
    assert _THAI_COMBINING_CPS == (expected_thai | expected_lao)
    assert len(_THAI_COMBINING_CPS) == 34

    for cp in _THAI_COMBINING_CPS:
        assert is_thai_combining(cp), f"Expected U+{cp:04X} to be combining"
        assert is_combining_char(chr(cp)), f"Expected chr(0x{cp:04X}) to be combining"

    # Explicit check for Lao PALI VIRAMA, MAITAIKHU, and YAMAKKAN:
    for cp in (0x0EBA, 0x0EC7, 0x0ECE):
        assert is_thai_combining(cp)
        assert is_combining_char(chr(cp))

    # Latin combining acute accent fallback:
    assert is_combining_char("\u0301") is True
    assert is_combining_char("a") is False
    assert is_combining_char("") is False

    # SARA AM (U+0E33 / U+0EB3) and FONGMAN (U+0E4F) are spacing characters, NOT Mn:
    assert is_thai_combining(0x0E33) is False
    assert is_thai_combining(0x0EB3) is False
    assert is_thai_combining(0x0E4F) is False
    assert is_combining_char("\u0e33") is False
    assert is_combining_char("\u0eb3") is False

    # Block range checks:
    assert is_thai(0x0E01) is True
    assert is_lao(0x0E81) is True
    assert is_thai_or_lao(0x0E01) is True
    assert is_thai_or_lao(0x0E81) is True
    assert is_thai_or_lao(0x0041) is False


def test_cell_offsets_thi_din_and_lao() -> None:
    for word in ("ที่ดิน", "ທີ່ດິນ"):
        assert len(word) == 6
        assert cell_starts(word) == [0, 3, 5]
        assert cell_stops(word) == [0, 3, 5, 6]

        # Forward steps:
        assert next_cell_offset(word, 0, 1) == 3
        assert next_cell_offset(word, 3, 1) == 5
        assert next_cell_offset(word, 5, 1) == 6
        assert next_cell_offset(word, 0, 2) == 5
        assert next_cell_offset(word, 0, 3) == 6

        # Backward steps from cell boundaries:
        assert prev_cell_offset(word, 6, 1) == 5
        assert prev_cell_offset(word, 5, 1) == 3
        assert prev_cell_offset(word, 3, 1) == 0

    # Mid-cluster col=4 (◌ิ inside ดิ at [3:5]) steps back to 3 (ด), NOT 0:
    assert prev_cell_offset("ที่ดิน", 4, 1) == 3
    assert snap_to_cell_start("ที่ดิน", 1) == 0
    assert snap_to_cell_start("ที่ดิน", 2) == 0
    assert snap_to_cell_start("ที่ดิน", 4) == 3


def test_cell_offsets_phu_yai() -> None:
    word = "ผู้ใหญ่"
    assert len(word) == 7
    assert cell_starts(word) == [0, 3, 4, 5]
    assert cell_stops(word) == [0, 3, 4, 5, 7]

    # Reverse traversal from len(word) back to 0 matches cell_starts in reverse:
    rev: list[int] = []
    col = len(word)
    while col > 0:
        col = prev_cell_offset(word, col, 1)
        rev.append(col)
    assert rev[::-1] == [0, 3, 4, 5]


def test_cell_vs_syllable_ko_ro_han_mai_yamok() -> None:
    # "เกาะ": 4 visual cells [0, 1, 2, 3, 4], 1 orthographic syllable [0, 4]
    assert cell_stops("เกาะ") == [0, 1, 2, 3, 4]
    assert find_thai_cluster_end("เกาะ", 0) == 4
    assert find_thai_word_breaks("เกาะ", use_libthai=False) == [0, 4]
    assert find_thai_word_breaks("เกาะ", use_libthai=True) == [0, 4]

    # "ธรรม": 4 visual cells [0, 1, 2, 3, 4], Tier 2 syllables "ธรร" [0, 3] + "ม" [3, 4]
    assert cell_stops("ธรรม") == [0, 1, 2, 3, 4]
    assert find_thai_cluster_end("ธรรม", 0) == 3
    assert find_thai_cluster_end("ธรรม", 3) == 4
    assert find_thai_word_breaks("ธรรม", use_libthai=False) == [0, 3, 4]

    # "ดีๆ": 2 visual cells [0, 2, 3], 1 syllable cluster [0, 3] (trailing ๆ attaches to ดี)
    assert cell_stops("ดีๆ") == [0, 2, 3]
    assert find_thai_cluster_end("ดีๆ", 0) == 3
    assert find_thai_word_breaks("ดีๆ", use_libthai=False) == [0, 3]
    assert find_thai_word_breaks("ดีๆ", use_libthai=True) == [0, 3]

    # "ๆฯ": standalone right-attaching symbols at cluster start step 1 cell at a time
    assert cell_stops("ๆฯ") == [0, 1, 2]
    assert find_thai_cluster_end("ๆฯ", 0) == 1
    assert find_thai_cluster_end("ๆฯ", 1) == 2
    assert find_thai_word_breaks("ๆฯ", use_libthai=False) == [0, 1, 2]
    assert find_thai_word_breaks("ๆฯ", use_libthai=True) == [0, 1, 2]


def test_sara_am_cell_and_syllable() -> None:
    assert is_sara_am(0x0E33) is True
    assert is_sara_am(0x0EB3) is True
    assert is_sara_am(0x0E32) is False
    assert is_thai_combining(0x0E33) is False
    assert is_thai_combining(0x0EB3) is False
    assert is_thai_following_vowel(0x0E33) is True
    assert is_thai_following_vowel(0x0EB3) is True
    assert is_thai_base(0x0E33) is False
    assert is_thai_base(0x0EB3) is False

    # "น้ำ" (น + ◌้ + ำ, len=3): 2 cells ("น้" [0:2], "ำ" [2:3]), 1 syllable [0, 3]
    assert cell_stops("น้ำ") == [0, 2, 3]
    assert find_thai_cluster_end("น้ำ", 0) == 3
    assert find_thai_word_breaks("น้ำ", use_libthai=False) == [0, 3]
    assert find_thai_word_breaks("น้ำ", use_libthai=True) == [0, 3]

    # "กำ" (ก + ำ, len=2): 2 cells ("ก" [0:1], "ำ" [1:2]), 1 syllable [0, 2]
    assert cell_stops("กำ") == [0, 1, 2]
    assert find_thai_cluster_end("กำ", 0) == 2
    assert find_thai_word_breaks("กำ", use_libthai=False) == [0, 2]
    assert find_thai_word_breaks("กำ", use_libthai=True) == [0, 2]

    # Lao "ນ້ຳ" (len=3) and "ກຳ" (len=2):
    assert cell_stops("ນ້ຳ") == [0, 2, 3]
    assert find_thai_cluster_end("ນ້ຳ", 0) == 3
    assert cell_stops("ກຳ") == [0, 1, 2]
    assert find_thai_cluster_end("ກຳ", 0) == 2


class _RecordingOutput(DummyOutput):
    def __init__(self) -> None:
        super().__init__()
        self.written: list[str] = []

    def write(self, data: str) -> None:
        self.written.append(data)


def _gate_fixture(monkeypatch):
    """Save/restore the sticky Thai-text renderer gate around a test."""
    saved = thai._THAI_GATE.value
    thai._THAI_GATE.value = False
    try:
        yield thai._THAI_GATE
    finally:
        thai._THAI_GATE.reset()
        thai._THAI_GATE.value = saved


@pytest.fixture
def sticky_gate(monkeypatch):
    """Force the sticky Thai-text renderer gate off for a deterministic test."""
    saved = thai._THAI_GATE.value
    monkeypatch.setattr(thai._THAI_GATE, "value", False)
    yield thai._THAI_GATE
    thai.reset_thai_text_gate()
    thai._THAI_GATE.value = saved


def test_sara_am_renderer_neighbor_refresh() -> None:
    install_prompt_toolkit_thai_patches()
    # The wrapper only sanitizes once the session reported Thai-capable text;
    # this test renders กำ/ກຳ frames, so latch the sticky gate.
    thai.note_document_text("\u0e33")
    editor = _make_editor_with_text("")
    app = editor.application
    size = Size(rows=24, columns=80)
    attrs_cache = ptk_renderer._StyleStringToAttrsCache(
        DummyStyle().get_attrs_for_style_str, DummyStyleTransformation()
    )
    has_style_cache = ptk_renderer._StyleStringHasStyleCache(attrs_cache)

    for base_ch, other_base_ch, sara_am_ch in (
        ("ก", "ข", "\u0e33"),  # Thai กำ -> ขำ
        ("ກ", "ຂ", "\u0eb3"),  # Lao  ກຳ -> ຂຳ
    ):
        # Frame 2a: Delete SARA AM at x=1 -> neighbor at x=0 must be poisoned and re-emitted
        prev_screen_a = Screen()
        prev_screen_a.height = 1
        prev_screen_a.data_buffer[0][0] = Char(base_ch, "")
        prev_screen_a.data_buffer[0][1] = Char(sara_am_ch, "")

        new_screen_a = Screen()
        new_screen_a.height = 1
        new_screen_a.data_buffer[0][0] = Char(base_ch, "")
        new_screen_a.data_buffer[0][1] = Char(" ", "")

        out_a = _RecordingOutput()
        ptk_renderer._output_screen_diff(
            app,
            out_a,
            new_screen_a,
            Point(0, 0),
            ColorDepth.DEPTH_8_BIT,
            prev_screen_a,
            None,
            False,
            full_screen=True,
            attrs_for_style_string=attrs_cache,
            style_string_has_style=has_style_cache,
            size=size,
            previous_width=size.columns,
        )
        assert prev_screen_a.data_buffer[0][0] == _SARA_AM_POISON
        assert base_ch in "".join(out_a.written)

        # Frame 2b: Modify preceding consonant at x=0 -> SARA AM at x=1 must be poisoned and re-emitted
        prev_screen_b = Screen()
        prev_screen_b.height = 1
        prev_screen_b.data_buffer[0][0] = Char(base_ch, "")
        prev_screen_b.data_buffer[0][1] = Char(sara_am_ch, "")

        new_screen_b = Screen()
        new_screen_b.height = 1
        new_screen_b.data_buffer[0][0] = Char(other_base_ch, "")
        new_screen_b.data_buffer[0][1] = Char(sara_am_ch, "")

        out_b = _RecordingOutput()
        ptk_renderer._output_screen_diff(
            app,
            out_b,
            new_screen_b,
            Point(0, 0),
            ColorDepth.DEPTH_8_BIT,
            prev_screen_b,
            None,
            False,
            full_screen=True,
            attrs_for_style_string=attrs_cache,
            style_string_has_style=has_style_cache,
            size=size,
            previous_width=size.columns,
        )
        assert prev_screen_b.data_buffer[0][1] == _SARA_AM_POISON
        written_b = "".join(out_b.written)
        assert other_base_ch in written_b
        assert sara_am_ch in written_b


def test_document_jk_vertical_snap() -> None:
    install_prompt_toolkit_thai_patches()
    # Row 0: "abcdef" (cursor at col=2 'c')
    # Row 1: "ที่ดิน" (codepoint index 2 is '่' combining mark inside Cell 0 "ที่")
    doc = Document("abcdef\nที่ดิน", cursor_position=2)
    assert doc.cursor_position_row == 0
    assert doc.cursor_position_col == 2

    down_delta = doc.get_cursor_down_position(1)
    doc_down = Document(doc.text, cursor_position=doc.cursor_position + down_delta)
    assert doc_down.cursor_position_row == 1
    assert doc_down.cursor_position_col == 0
    assert doc_down.current_char == "ท"

    # Also test upward motion from row 1 col=2 of "abcdef" onto row 0 "ที่ดิน":
    doc2 = Document("ที่ดิน\nabcdef", cursor_position=len("ที่ดิน\n") + 2)
    assert doc2.cursor_position_row == 1
    assert doc2.cursor_position_col == 2
    up_delta = doc2.get_cursor_up_position(1)
    doc_up = Document(doc2.text, cursor_position=doc2.cursor_position + up_delta)
    assert doc_up.cursor_position_row == 0
    assert doc_up.cursor_position_col == 0
    assert doc_up.current_char == "ท"


def test_vi_x_X_s_r_tilde_dollar_via_key_processor() -> None:
    # 1. 'x' at col=0 on "ที่ดิน" deletes entire cell cluster "ที่" -> "ดิน"
    editor = _make_editor_with_text("ที่ดิน", cursor_position=0)
    buff = editor.current_editor_buffer.buffer
    _feed_keys(editor, "x")
    assert buff.text == "ดิน"
    assert buff.cursor_position == 0
    assert editor.application.clipboard.get_data().text == "ที่"

    # 2. 'X' at col=3 on "ที่ดิน" deletes cell cluster "ที่" before cursor -> "ดิน"
    editor = _make_editor_with_text("ที่ดิน", cursor_position=3)
    buff = editor.current_editor_buffer.buffer
    _feed_keys(editor, "X")
    assert buff.text == "ดิน"
    assert buff.cursor_position == 0
    assert editor.application.clipboard.get_data().text == "ที่"

    # 3. 's' at col=0 on "ที่ดิน" deletes "ที่" and switches to INSERT mode
    editor = _make_editor_with_text("ที่ดิน", cursor_position=0)
    buff = editor.current_editor_buffer.buffer
    _feed_keys(editor, "s")
    assert buff.text == "ดิน"
    assert editor.application.vi_state.input_mode == InputMode.INSERT
    assert editor.application.clipboard.get_data().text == "ที่"

    # 4. 'r' + 'ข' at col=0 on "ที่ดิน" replaces "ที่" with "ข" -> "ขดิน"
    editor = _make_editor_with_text("ที่ดิน", cursor_position=0)
    buff = editor.current_editor_buffer.buffer
    _feed_keys(editor, "r", "ข")
    assert buff.text == "ขดิน"
    assert buff.cursor_position == 0
    assert editor.application.vi_state.input_mode == InputMode.NAVIGATION

    # 5. '~' at col=0 on "ที่ดิน" advances 1 cell cluster (0 -> 3), never parking on ◌ี
    editor = _make_editor_with_text("ที่ดิน", cursor_position=0)
    buff = editor.current_editor_buffer.buffer
    _feed_keys(editor, "~")
    assert buff.text == "ที่ดิน"
    assert buff.cursor_position == 3

    # 6. '$' lands on start of last cell cluster (col=5 on "ที่ดิน", col=5 on "ผู้ใหญ่", col=0 on "ที่")
    editor = _make_editor_with_text("ที่ดิน", cursor_position=0)
    buff = editor.current_editor_buffer.buffer
    _feed_keys(editor, "$")
    assert buff.cursor_position == 5

    editor = _make_editor_with_text("ผู้ใหญ่", cursor_position=0)
    buff = editor.current_editor_buffer.buffer
    _feed_keys(editor, "$")
    assert buff.cursor_position == 5

    editor = _make_editor_with_text("ที่", cursor_position=0)
    buff = editor.current_editor_buffer.buffer
    _feed_keys(editor, "$")
    assert buff.cursor_position == 0

    # Operator-pending 'd$' from col=0 on "ผู้ใหญ่" still deletes all 7 codepoints including ◌่:
    editor = _make_editor_with_text("ผู้ใหญ่", cursor_position=0)
    buff = editor.current_editor_buffer.buffer
    _feed_keys(editor, "d", "$")
    assert buff.text == ""


def test_formatted_text_stray_combining_cleanup() -> None:
    ctrl = FormattedTextControl([("", "ที่")])
    win = Window(content=ctrl)
    screen = Screen()
    win.write_to_screen(
        screen,
        MouseHandlers(),
        WritePosition(xpos=0, ypos=0, width=20, height=1),
        "",
        erase_bg=False,
        z_index=None,
    )
    # Before cleanup, Window._copy_body leaves a width-0 combining mark in column 1:
    assert screen.data_buffer[0][0].char == "ที่"
    assert screen.data_buffer[0][1].width == 0

    _sanitize_and_invalidate_sara_am(screen, None, 20)
    assert screen.data_buffer[0][0].char == "ที่"
    assert screen.data_buffer[0][1].char == " "
    assert screen.data_buffer[0][1].width == 1


def test_vi_hl_wbe_text_objects_on_thai() -> None:
    # 'l' and 'h' step by cell clusters across "ที่ดิน" (stops: 0 -> 3 -> 5):
    editor = _make_editor_with_text("ที่ดิน", cursor_position=0)
    buff = editor.current_editor_buffer.buffer
    _feed_keys(editor, "l")
    assert buff.cursor_position == 3
    _feed_keys(editor, "l")
    assert buff.cursor_position == 5
    _feed_keys(editor, "h")
    assert buff.cursor_position == 3
    _feed_keys(editor, "h")
    assert buff.cursor_position == 0

    # 'w', 'b', 'e', 'diw' on "เกาะ น้ำ":
    editor = _make_editor_with_text("เกาะ น้ำ", cursor_position=0)
    buff = editor.current_editor_buffer.buffer
    _feed_keys(editor, "w")
    assert buff.cursor_position == 5  # Start of "น้ำ"
    _feed_keys(editor, "b")
    assert buff.cursor_position == 0  # Back to start of "เกาะ"
    _feed_keys(editor, "e")
    assert buff.cursor_position == 3  # Last cell 'ะ' of "เกาะ"
    _feed_keys(editor, "d", "i", "w")
    assert buff.text == " น้ำ"


def test_vi_append_escape_and_operators_on_thai() -> None:
    # 'a' at col=0 on "ที่ดิน" moves past "ที่" (to col=3) and enters INSERT mode;
    # '<Esc>' steps back 1 cell cluster to col=0 (never landing on ◌่ at col=2):
    editor = _make_editor_with_text("ที่ดิน", cursor_position=0)
    buff = editor.current_editor_buffer.buffer
    _feed_keys(editor, "a")
    assert editor.application.vi_state.input_mode == InputMode.INSERT
    assert buff.cursor_position == 3
    _feed_keys(editor, Keys.Escape)
    assert editor.application.vi_state.input_mode == InputMode.NAVIGATION
    assert buff.cursor_position == 0

    # 'dl' at col=0 on "ที่ดิน" deletes 1 cell cluster ("ที่"):
    editor = _make_editor_with_text("ที่ดิน", cursor_position=0)
    buff = editor.current_editor_buffer.buffer
    _feed_keys(editor, "d", "l")
    assert buff.text == "ดิน"
    assert buff.cursor_position == 0

    # 'dh' at col=3 on "ที่ดิน" deletes 1 cell cluster before cursor ("ที่"):
    editor = _make_editor_with_text("ที่ดิน", cursor_position=3)
    buff = editor.current_editor_buffer.buffer
    _feed_keys(editor, "d", "h")
    assert buff.text == "ดิน"
    assert buff.cursor_position == 0

    # 'e' vs 'de' on "ผู้ใหญ่ บ้าน" (where "ผู้ใหญ่" ends with combining mark ◌่ at idx 6):
    editor = _make_editor_with_text("ผู้ใหญ่ บ้าน", cursor_position=0)
    buff = editor.current_editor_buffer.buffer
    _feed_keys(editor, "e")
    assert buff.cursor_position == 5  # Base consonant 'ญ' of last cell "ญ่"

    editor = _make_editor_with_text("ผู้ใหญ่ บ้าน", cursor_position=0)
    buff = editor.current_editor_buffer.buffer
    _feed_keys(editor, "d", "e")
    assert buff.text == " บ้าน"

    # '*' and '#' word search on Thai words:
    editor = _make_editor_with_text("เกาะ น้ำ เกาะ", cursor_position=0)
    buff = editor.current_editor_buffer.buffer
    assert buff.document.get_word_under_cursor() == "เกาะ"
    _feed_keys(editor, "*")
    assert buff.cursor_position == 9
    _feed_keys(editor, "#")
    assert buff.cursor_position == 0


def test_two_tier_word_breaks_fallback(monkeypatch) -> None:
    # Tier 2 fallback (when libthai is unavailable or disabled):
    monkeypatch.setattr(thai, "_get_libthai", lambda: None)
    assert find_thai_word_breaks("ที่ดิน") == [0, 3, 5, 6]
    assert find_thai_word_breaks("ผู้ใหญ่") == [0, 3, 5, 7]
    assert find_thai_word_breaks("ທີ່ດິນ") == [0, 3, 5, 6]
    doc = Document("ที่ดิน", cursor_position=0)
    assert doc.find_next_word_beginning(1) == 3
    assert doc.find_next_word_beginning(2) == 5


def test_version_gate_graceful_fallback(monkeypatch) -> None:
    # Simulate an incompatible Document method signature and verify graceful fallback:
    def _bad_sig(self):  # Missing `count` parameter
        return 0

    orig_left = Document.get_cursor_left_position
    monkeypatch.setattr(Document, "get_cursor_left_position", _bad_sig)
    assert thai.install_prompt_toolkit_thai_patches() is False
    assert Document.get_cursor_left_position is _bad_sig

    # Restore and verify re-installation succeeds:
    monkeypatch.setattr(Document, "get_cursor_left_position", orig_left)
    assert thai.install_prompt_toolkit_thai_patches() is True
    assert Document("ที่ดิน", cursor_position=0).get_cursor_right_position(1) == 3


def test_version_gate_rollback_covers_key_processor_patches(monkeypatch) -> None:
    """Failure during the self-test must also undo the KeyProcessor patches."""
    from prompt_toolkit.key_binding.key_processor import KeyProcessor

    # Simulate a pre-installation prompt_toolkit: restore the original
    # Document and KeyProcessor methods recorded at import time.
    for method_name, original in thai._ORIGINAL_DOCUMENT_METHODS.items():
        monkeypatch.setattr(Document, method_name, original)
    for method_name, original in thai._ORIGINAL_KEY_PROCESSOR_METHODS.items():
        if original is not None:
            monkeypatch.setattr(KeyProcessor, method_name, original)

    assert getattr(KeyProcessor._fix_vi_cursor_position, "_pyvim_thai_patched", False) is False, (
        "precondition: KeyProcessor patches uninstalled"
    )

    # Corrupt the primitive used by the patched Document.right method so the
    # startup self-test fails *after* all patches are applied:
    monkeypatch.setattr(thai, "next_cell_offset", lambda line, col, count=1: col + 99)
    assert thai.install_prompt_toolkit_thai_patches() is False

    # Both KeyProcessor patches must be rolled back (docs/bugs/005.md):
    assert getattr(KeyProcessor._fix_vi_cursor_position, "_pyvim_thai_patched", False) is False
    assert getattr(KeyProcessor._start_timeout, "_pyvim_thai_patched", False) is False
    # And the Document methods are the unpatched prompt_toolkit originals
    # (cursor 0 -> first codepoint on "ที่ดิน", no cell-cluster snapping):
    assert Document("ที่ดิน", cursor_position=0).get_cursor_right_position(1) == 1

    # monkeypatch.undo() restores the pre-test (patched) state:
    monkeypatch.undo()
    assert Document("ที่ดิน", cursor_position=0).get_cursor_right_position(1) == 3
    assert getattr(KeyProcessor._fix_vi_cursor_position, "_pyvim_thai_patched", False) is True


def _build_sara_am_frames(base: str, sara_am: str) -> tuple[Screen, Screen]:
    """A previous frame with `base ำ` and a new frame where the ำ is deleted."""
    prev_screen = Screen()
    prev_screen.height = 1
    prev_screen.data_buffer[0][0] = Char(base, "")
    prev_screen.data_buffer[0][1] = Char(sara_am, "")

    new_screen = Screen()
    new_screen.height = 1
    new_screen.data_buffer[0][0] = Char(base, "")
    new_screen.data_buffer[0][1] = Char(" ", "")
    return prev_screen, new_screen


def test_renderer_gate_skips_ascii_frames(sticky_gate) -> None:
    """With no Thai seen yet, the wrapper must not mutate/pre-scan screens."""
    install_prompt_toolkit_thai_patches()
    editor = _make_editor_with_text("")
    app = editor.application
    size = Size(rows=24, columns=80)
    attrs_cache = ptk_renderer._StyleStringToAttrsCache(
        DummyStyle().get_attrs_for_style_str, DummyStyleTransformation()
    )
    has_style_cache = ptk_renderer._StyleStringHasStyleCache(attrs_cache)

    prev_screen, new_screen = _build_sara_am_frames("ก", "\u0e33")
    out = _RecordingOutput()
    ptk_renderer._output_screen_diff(
        app,
        out,
        new_screen,
        Point(0, 0),
        ColorDepth.DEPTH_8_BIT,
        prev_screen,
        None,
        False,
        full_screen=True,
        attrs_for_style_string=attrs_cache,
        style_string_has_style=has_style_cache,
        size=size,
        previous_width=size.columns,
    )
    assert sticky_gate.value is False
    # No poisoning happened: the previous screen stayed untouched.
    assert prev_screen.data_buffer[0][0].char == "ก"
    assert prev_screen.data_buffer[0][1].char == "\u0e33"


def test_buffer_text_latches_gate_and_sanitizer_resumes(sticky_gate) -> None:
    """Typing Thai into the buffer must latch the gate (O(1) for ASCII)."""
    install_prompt_toolkit_thai_patches()
    editor = _make_editor_with_text("")
    app = editor.application
    size = Size(rows=24, columns=80)
    attrs_cache = ptk_renderer._StyleStringToAttrsCache(
        DummyStyle().get_attrs_for_style_str, DummyStyleTransformation()
    )
    has_style_cache = ptk_renderer._StyleStringHasStyleCache(attrs_cache)

    buff = editor.current_editor_buffer.buffer
    buff.text = "กำ"
    assert sticky_gate.value is True, "Thai buffer text must latch the gate"

    prev_screen, new_screen = _build_sara_am_frames("ก", "\u0e33")
    out = _RecordingOutput()
    ptk_renderer._output_screen_diff(
        app,
        out,
        new_screen,
        Point(0, 0),
        ColorDepth.DEPTH_8_BIT,
        prev_screen,
        None,
        False,
        full_screen=True,
        attrs_for_style_string=attrs_cache,
        style_string_has_style=has_style_cache,
        size=size,
        previous_width=size.columns,
    )
    # Once latched, the neighbor refresh is back: ก must be re-emitted.
    assert prev_screen.data_buffer[0][0] == _SARA_AM_POISON
    assert "ก" in "".join(out.written)


def test_sticky_gate_note_document_text(sticky_gate) -> None:
    # ASCII / empty strings are free and never latch.
    thai.note_document_text("plain ascii text")
    thai.note_document_text("")
    thai.note_document_text(None)
    thai.note_document_text("accented é but no Thai")
    assert sticky_gate.value is False
    # Thai text latches; Lao text too.
    thai.note_document_text("กำ")
    assert sticky_gate.value is True
    sticky_gate.value = False
    thai.note_document_text("ຳ")
    assert sticky_gate.value is True
