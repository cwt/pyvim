from unittest.mock import MagicMock

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document

from pyvim.key_bindings import _delete_cell_clusters


def test_delete_cell_clusters_no_crash_at_col0_or_empty_line():
    clipboard = MagicMock()
    app = MagicMock()
    app.clipboard = clipboard

    class Event:
        pass

    event = Event()
    event.app = app
    event.arg = 1

    # X at column 0: nothing to delete, must not raise UnboundLocalError.
    buff = Buffer(document=Document("abc", 0))
    event.current_buffer = buff
    _delete_cell_clusters(event, backward=True)
    assert buff.document.text == "abc"

    # x on an empty line: nothing to delete, must not raise.
    buff2 = Buffer(document=Document("", 0))
    event.current_buffer = buff2
    _delete_cell_clusters(event, backward=False)
    assert buff2.document.text == ""

    # When something is deleted, clipboard is updated.
    buff3 = Buffer(document=Document("abc", 1))
    event.current_buffer = buff3
    _delete_cell_clusters(event, backward=True)
    clipboard.set_text.assert_called()


def test_indent_line_uses_event_current_buffer():
    # Smoke: indent_line must reference event.current_buffer, not event.application.
    import inspect

    from pyvim.key_bindings import create_key_bindings

    src = inspect.getsource(create_key_bindings)
    assert "event.application.current_buffer" not in src
