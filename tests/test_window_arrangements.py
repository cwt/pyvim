from pyvim.window_arrangement import EditorBuffer, VSplit


def test_initial(window, tab_page):
    assert isinstance(tab_page.root, VSplit)
    assert tab_page.root == [window]


def test_vsplit(editor, tab_page):
    # Create new buffer.
    eb = EditorBuffer(editor)

    # Insert in tab, by splitting.
    tab_page.vsplit(eb)

    assert isinstance(tab_page.root, VSplit)
    assert len(tab_page.root) == 2


def test_new_buffers_are_numbered_right_after_the_active_one(editor):
    # docs/bugs/013.md: `_add_editor_buffer` inserts new buffers right
    # AFTER the active one (matching the docstring and vim `:buffers`
    # growth), not before it.
    arrangement = editor.window_arrangement
    eb_a = EditorBuffer(editor)
    arrangement._add_editor_buffer(eb_a)
    assert arrangement.editor_buffers == [eb_a]
    assert arrangement.active_editor_buffer is eb_a

    eb_b = EditorBuffer(editor)
    arrangement._add_editor_buffer(eb_b)
    assert arrangement.editor_buffers == [eb_a, eb_b]
    # Without `show_in_current_window`, focus stays on the active buffer:
    assert arrangement.active_editor_buffer is eb_a

    # A new split targeting eb_b makes it active; the next insertion again
    # lands right after it.
    arrangement.active_tab.vsplit(eb_b)
    assert arrangement.active_editor_buffer is eb_b
    eb_c = EditorBuffer(editor)
    arrangement._add_editor_buffer(eb_c)
    assert arrangement.editor_buffers == [eb_a, eb_b, eb_c]
    assert arrangement.active_editor_buffer is eb_b


def test_close_editor_buffer_closes_target_window(editor):
    editor.load_initial_files([None])
    wa = editor.window_arrangement
    eb1 = wa.active_editor_buffer
    eb2 = EditorBuffer(editor)
    wa._add_editor_buffer(eb2)
    wa.active_tab.vsplit(eb2)
    assert wa.active_tab.window_count() == 2

    wa.active_tab.show_editor_buffer(eb1)
    assert wa.active_editor_buffer is eb1
    wa.active_tab.close_editor_buffer(eb2)
    assert eb2 not in [w.editor_buffer for w in wa.active_tab.windows()]
    assert eb1 in [w.editor_buffer for w in wa.active_tab.windows()]


def test_close_window_on_last_window_does_not_crash(editor):
    editor.load_initial_files([None])
    wa = editor.window_arrangement
    assert wa.active_tab.window_count() == 1
    assert len(wa.tab_pages) == 1
    wa.close_window()
    assert wa.active_tab.window_count() == 1
    assert editor.message is not None
