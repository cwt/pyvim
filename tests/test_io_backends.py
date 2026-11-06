"""
Tests for `pyvim/io/backends.py` (P5: `codecs.open` deprecation removal,
`FileIO`/`GZipFileIO` behaviour).
"""
from __future__ import unicode_literals

import io
import warnings

from pyvim.io.backends import FileIO, GZipFileIO


def test_fileio_write_read_utf8_roundtrip(tmp_path):
    f = FileIO()
    p = str(tmp_path / 'file.txt')

    f.write(p, 'héllo wörld', 'utf-8')
    text, encoding = f.read(p)

    assert text == 'héllo wörld'
    assert encoding == 'utf-8'


def test_fileio_latin1_fallback(tmp_path):
    p = tmp_path / 'latin1.txt'
    # A byte that is not valid UTF-8: falls back to latin-1 (which accepts
    # any byte sequence).
    p.write_bytes(b'caf\xe9')

    text, encoding = FileIO().read(str(p))

    assert text == 'café'
    assert encoding == 'latin-1'


def test_fileio_no_deprecation_warning(tmp_path):
    # P5: `codecs.open` is deprecated in Python 3.14+; the C-buffered
    # `io.open` must be used instead, so no DeprecationWarning may be
    # emitted while reading or writing.
    p = str(tmp_path / 'deprecation.txt')
    f = FileIO()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        f.write(p, 'plain text', 'utf-8')
        f.read(p)

    deprecations = [w for w in caught if issubclass(w.category,
                                                    DeprecationWarning)]
    assert deprecations == [], \
        'FileIO read/write must not emit DeprecationWarnings: %r' % deprecations


def test_fileio_uses_io_open(tmp_path, monkeypatch):
    # Explicitly: reads/writes go through `io.open`, not `codecs.open`.
    p = str(tmp_path / 'tracked.txt')
    f = FileIO()

    calls = []
    original = io.open

    def tracking_open(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr('pyvim.io.backends.io.open', tracking_open)

    f.write(p, 'data', 'utf-8')
    f.read(p)

    assert [args[1] for args, _kw in calls] == ['w', 'r']
    assert [kw.get('encoding') for _args, kw in calls] == ['utf-8', 'utf-8']


def test_gzip_roundtrip(tmp_path):
    p = str(tmp_path / 'data.txt.gz')
    g = GZipFileIO()

    g.write(p, 'compressed content', 'utf-8')
    text, encoding = g.read(p)

    assert text == 'compressed content'
    assert encoding == 'utf-8'


def test_gzip_can_open_location():
    g = GZipFileIO()
    assert g.can_open_location('/tmp/some-file.txt.gz') is True
    assert g.can_open_location('/tmp/some-file.txt') is False
