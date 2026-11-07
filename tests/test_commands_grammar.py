from pyvim.commands.grammar import COMMAND_GRAMMAR
from pyvim.commands.handler import handle_command


def test_colo_matches_grammar():
    m = COMMAND_GRAMMAR.match('colo default')
    assert m is not None
    assert m.variables().get('command') == 'colo'
    assert m.variables().get('colorscheme') == 'default'


def test_unknown_multiword_command_shows_message(editor):
    handle_command(editor, ':foo bar')
    assert editor.message is not None
