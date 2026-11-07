from .grammar import COMMAND_GRAMMAR

__all__ = ('CommandPreviewer',)


#: (attribute, option names, value to set when the option is toggled).
_TOGGLE_PREVIEW_SPECS = (
    ('highlight_search', ('hlsearch', 'hls'), True),
    ('highlight_search', ('nohlsearch', 'nohls'), False),
    ('show_line_numbers', ('nu', 'number'), True),
    ('show_line_numbers', ('nonu', 'nonumber'), False),
    ('show_ruler', ('ruler', 'ru'), True),
    ('show_ruler', ('noruler', 'noru'), False),
    ('relative_number', ('relativenumber', 'rnu'), True),
    ('relative_number', ('norelativenumber', 'nornu'), False),
    ('cursorline', ('cursorline', 'cul'), True),
    ('cursorline', ('nocursorline', 'nocul'), False),
    ('cursorcolumn', ('cursorcolumn', 'cuc'), True),
    ('cursorcolumn', ('nocursorcolumn', 'nocuc'), False),
)

#: (attribute, option names) for integer-valued options; their actual
#: value belongs to the `set_value` variable of the typed command.
_INT_VALUE_PREVIEW_SPECS = (
    ('tabstop', ('tabstop', 'ts')),
    ('scroll_offset', ('scrolloff', 'so')),
)


class CommandPreviewer(object):
    """
    Already show the effect of Vi commands before enter is pressed.
    """

    def __init__(self, editor):
        self.editor = editor
        self.save()

    def save(self):
        """
        Back up current editor state.
        """
        e = self.editor

        self._style = e.current_style
        self._show_line_numbers = e.show_line_numbers
        self._highlight_search = e.highlight_search
        self._show_ruler = e.show_ruler
        self._relative_number = e.relative_number
        self._cursorcolumn = e.cursorcolumn
        self._cursorline = e.cursorline
        self._colorcolumn = e.colorcolumn
        self._tabstop = e.tabstop
        self._scroll_offset = e.scroll_offset

    def restore(self):
        """
        Focus of Vi command line lost, undo preview.
        """
        e = self.editor

        e.current_style = self._style
        e.show_line_numbers = self._show_line_numbers
        e.highlight_search = self._highlight_search
        e.show_ruler = self._show_ruler
        e.relative_number = self._relative_number
        e.cursorcolumn = self._cursorcolumn
        e.cursorline = self._cursorline
        e.colorcolumn = self._colorcolumn
        e.tabstop = self._tabstop
        e.scroll_offset = self._scroll_offset

    def preview(self, input_string):
        """
        Show effect of current Vi command.
        """
        # First, the apply.
        self.restore()
        self._apply(input_string)

    def _apply(self, input_string):
        """Apply command."""
        e = self.editor

        # Parse command.
        m = COMMAND_GRAMMAR.match(input_string)
        if m is None:
            return

        variables = m.variables()

        command = variables.get('command')
        set_option = variables.get('set_option')

        # Preview colorschemes.
        if command in ('colorscheme', 'colo'):
            colorscheme = variables.get('colorscheme')
            if colorscheme:
                e.use_colorscheme(colorscheme)

        # Preview `:set` commands through a compact spec table instead of a
        # hand-written elif chain, so the options covered here stay in sync
        # with the `:set` handlers (docs/bugs/028.md).
        if command == 'set':
            for attribute, names, value in _TOGGLE_PREVIEW_SPECS:
                if set_option in names:
                    setattr(e, attribute, value)
                    return

            for attribute, names in _INT_VALUE_PREVIEW_SPECS:
                if set_option in names:
                    self._preview_int_value(e, attribute, variables)
                    return

            if set_option in ('colorcolumn', 'cc'):
                self._preview_colorcolumn(e, variables)

    @staticmethod
    def _preview_int_value(e, attribute, variables):
        raw_value = variables.get('set_value')
        minimum = 0 if attribute == 'scroll_offset' else 1
        if raw_value and raw_value.isdigit() and int(raw_value) >= minimum:
            setattr(e, attribute, int(raw_value))

    @staticmethod
    def _preview_colorcolumn(e, variables):
        value = variables.get('set_value', '')
        if not value:
            e.colorcolumn = []
            return
        try:
            e.colorcolumn = [int(v) for v in value.split(',')]
        except ValueError:
            return
