"""
Tests for `pyvim/style.py` (P2: lazy style mapping).
"""

from __future__ import unicode_literals

from collections.abc import Mapping

from pygments.styles import get_all_styles
from pygments.util import ClassNotFound

from pyvim.style import (
    _LazyStylesDict,
    generate_built_in_styles,
    get_editor_style_by_name,
)


def test_generate_built_in_styles_returns_lazy_mapping():
    styles = generate_built_in_styles()
    assert isinstance(styles, _LazyStylesDict)
    assert isinstance(styles, Mapping)
    # Nothing may be eagerly compiled at construction time:
    assert styles._loaded == {}


def test_lazy_styles_names_match_get_all_styles():
    styles = generate_built_in_styles()
    assert len(styles) == len(list(get_all_styles()))
    assert list(styles) == list(get_all_styles())


def test_lazy_styles_caches_compiled_styles():
    styles = generate_built_in_styles()
    first = styles['monokai']
    second = styles['monokai']
    assert first is second  # cached, not recompiled
    assert styles._loaded == {'monokai': first}


def test_lazy_styles_vim_scheme():
    # `vim` is a Pygments scheme name that pyvim overrides with its own
    # merged vim style: the lazy dict must resolve it through
    # `get_editor_style_by_name` and cache that result.
    styles = generate_built_in_styles()
    first = styles['vim']
    second = styles['vim']
    assert _is_prompt_toolkit_style(first)
    assert first is second


def test_unknown_style_raises_class_not_found():
    styles = generate_built_in_styles()
    try:
        styles['no-such-style-name']
    except ClassNotFound:
        pass
    else:
        raise AssertionError('Expected ClassNotFound')


def _is_prompt_toolkit_style(style):
    # `get_editor_style_by_name` returns a merged PTK style object:
    return type(style).__module__.startswith('prompt_toolkit.styles')


def test_editor_style_by_name_vim():
    style = get_editor_style_by_name('vim')
    assert _is_prompt_toolkit_style(style)


def test_editor_style_by_name_pygments_style():
    assert _is_prompt_toolkit_style(get_editor_style_by_name('monokai'))
