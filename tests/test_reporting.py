from prompt_toolkit.document import Document

from pyvim.reporting import report_pyflakes


def test_report_pyflakes_utf8_column():
    doc = Document('x = "ที่ดิน" + undefined_var\n')
    err = report_pyflakes(doc)[0]
    # Character column should point at 'undefined_var', not a byte offset.
    assert doc.lines[0][err.start_column : err.end_column] == 'undefined_var'


def test_reporter_error_equality():
    from pyvim.reporting import ReporterError

    assert [ReporterError(0, 0, 1, 'u')] == [ReporterError(0, 0, 1, 'u')]
