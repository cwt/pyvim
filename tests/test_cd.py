import os

from pyvim.commands.handler import handle_command


def test_cd_no_arg_and_expanduser(editor, tmp_path):
    editor.load_initial_files([None])
    home = os.path.expanduser('~')
    # :cd with no argument goes home.
    handle_command(editor, ':cd')
    assert os.getcwd() == home
    # :cd with ~/ path expands.
    d = tmp_path / 'sub'
    d.mkdir()
    handle_command(editor, ':cd %s' % d)
    assert os.getcwd() == str(d)
    # restore
    os.chdir(home)
