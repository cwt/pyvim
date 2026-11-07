"""
Tests for `pyvim/commands/preview.py` (docs/bugs/028.md): the `:set`
preview is table-driven and covers the toggle options, the integer-valued
options (tabstop/scrolloff) and colorcolumn.
"""

from __future__ import annotations

from pyvim.commands.preview import CommandPreviewer

SAMPLE_STATE = {
    'show_line_numbers': False,
    'highlight_search': False,
    'show_ruler': True,
    'relative_number': False,
    'cursorline': False,
    'cursorcolumn': False,
    'colorcolumn': [],
    'tabstop': 4,
    'scroll_offset': 0,
}


def get_previewer(editor):
    """A previewer with the sample state snapshotted."""
    for attribute, value in SAMPLE_STATE.items():
        setattr(editor, attribute, value)
    previewer = CommandPreviewer(editor)
    previewer.save()
    return previewer


def test_toggle_options_preview(editor):
    previewer = get_previewer(editor)

    previewer.preview(':set nu')
    assert editor.show_line_numbers is True
    previewer.preview(':set nonumber')
    assert editor.show_line_numbers is False

    previewer.preview(':set hls')
    assert editor.highlight_search is True
    previewer.preview(':set nohls')
    assert editor.highlight_search is False

    previewer.preview(':set cursorline')
    assert editor.cursorline is True
    previewer.preview(':set nocul')
    assert editor.cursorline is False

    previewer.preview(':set cursorcolumn')
    assert editor.cursorcolumn is True
    previewer.preview(':set nocuc')
    assert editor.cursorcolumn is False

    previewer.preview(':set relativenumber')
    assert editor.relative_number is True
    previewer.preview(':set nornu')
    assert editor.relative_number is False

    previewer.preview(':set ruler')
    assert editor.show_ruler is True
    previewer.preview(':set noru')
    assert editor.show_ruler is False


def test_int_value_options_preview(editor):
    previewer = get_previewer(editor)

    # docs/bugs/028.md: tabstop/scrolloff were not previewed at all before.
    previewer.preview(':set tabstop=8')
    assert editor.tabstop == 8

    # Each preview restores first, so applying scrolloff drops tabstop=8:
    previewer.preview(':set scrolloff=3')
    assert editor.scroll_offset == 3
    assert editor.tabstop == 4

    # No value / invalid value: leave the option at its restored state.
    previewer.preview(':set tabstop')
    assert editor.tabstop == 4
    previewer.preview(':set ts=oops')
    assert editor.tabstop == 4

    # colorcolumn keeps its own value parsing semantics:
    # Invalid tokens are rejected, matching `:set cc` on <Enter>:
    previewer.preview(':set colorcolumn=80,40,xx')
    assert editor.colorcolumn == []
    previewer.preview(':set colorcolumn=80,40')
    assert editor.colorcolumn == [80, 40]
    assert editor.scroll_offset == 0


def test_restore_undoes_the_preview(editor):
    previewer = get_previewer(editor)

    previewer.preview(':set nu tabstop=8')  # grammar takes the first form
    previewer.preview(':set nu')
    assert editor.show_line_numbers is True

    previewer.restore()
    for attribute, value in SAMPLE_STATE.items():
        assert getattr(editor, attribute) == value, attribute
