import gzip
import io
import os
import urllib.request

from .base import EditorIO

__all__ = (
    'FileIO',
    'GZipFileIO',
    'DirectoryIO',
    'HttpIO',
)


ENCODINGS = ['utf-8', 'latin-1']


class FileIO(EditorIO):
    """
    I/O backend for the native file system.
    """

    def can_open_location(self, location):
        # We can handle all local files.
        location = os.path.expanduser(location)
        return '://' not in location and not os.path.isdir(location)

    def exists(self, location):
        return os.path.exists(os.path.expanduser(location))

    def read(self, location):
        """
        Read file from disk.
        """
        location = os.path.expanduser(location)

        with open(location, 'rb') as f:
            data = f.read()
        return _auto_decode(data)

    def write(self, location, text, encoding):
        """
        Write file to disk.
        """
        location = os.path.expanduser(location)

        with io.open(location, 'w', encoding=encoding) as f:
            f.write(text)


class GZipFileIO(EditorIO):
    """
    I/O backend for gzip files.

    It is possible to edit this file as if it were not compressed.
    The read and write call will decompress and compress transparently.
    """

    def can_open_location(self, location):
        location = os.path.expanduser(location)
        return '://' not in location and not os.path.isdir(location) and location.endswith('.gz')

    def exists(self, location):
        return os.path.exists(os.path.expanduser(location))

    def read(self, location):
        location = os.path.expanduser(location)

        with gzip.open(location, 'rb') as f:
            data = f.read()
        return _auto_decode(data)

    def write(self, location, text, encoding):
        """
        Write file to disk.
        """
        location = os.path.expanduser(location)

        with gzip.open(location, 'wb') as f:
            f.write(text.encode(encoding))


class DirectoryIO(EditorIO):
    """
    Create a textual listing of the directory content.
    """

    def can_open_location(self, location):
        # We can handle all local directories.
        location = os.path.expanduser(location)
        return '://' not in location and os.path.isdir(location)

    def exists(self, location):
        return os.path.isdir(os.path.expanduser(location))

    def read(self, directory):
        directory = os.path.expanduser(directory)
        # Read content.
        content = sorted(os.listdir(directory))
        directories = []
        files = []

        for f in content:
            if os.path.isdir(os.path.join(directory, f)):
                directories.append(f)
            else:
                files.append(f)

        # Construct output.
        result = []
        result.append('" ==================================\n')
        result.append('" Directory Listing\n')
        result.append('"    %s\n' % os.path.abspath(directory))
        result.append('"    Quick help: -: go up dir\n')
        result.append('" ==================================\n')
        result.append('../\n')
        result.append('./\n')

        for d in directories:
            result.append('%s/\n' % d)

        for f in files:
            result.append('%s\n' % f)

        return ''.join(result), 'utf-8'

    def write(self, location, text, encoding):
        raise NotImplementedError('Cannot write to directory.')

    def isdir(self, location):
        return True


class HttpIO(EditorIO):
    """
    I/O backend that reads from HTTP.
    """

    def can_open_location(self, location):
        # True when the location is an http:// or https:// URL.
        return location.startswith('http://') or location.startswith('https://')

    def exists(self, location):
        return NotImplemented  # We don't know.

    def read(self, location):
        # Do Http request.
        with urllib.request.urlopen(location) as response:
            data = response.read()

        # Return decoded.
        return _auto_decode(data)

    def write(self, location, text, encoding):
        raise NotImplementedError('Cannot write to HTTP.')


def _auto_decode(data):
    """
    Decode bytes. Return a (text, encoding) tuple.
    """
    assert isinstance(data, bytes)

    for e in ENCODINGS:
        try:
            return data.decode(e), e
        except UnicodeDecodeError:
            pass
