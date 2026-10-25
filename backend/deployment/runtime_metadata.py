"""Read installed metadata afresh; bound caching to parsing identical text."""

from functools import lru_cache
from importlib.metadata import Distribution, distribution

_MAX_CACHE_CHARACTERS = 256 * 1024


class _MetadataText(Distribution):
    def __init__(self, text):
        self.text = text

    def read_text(self, filename):
        return self.text if filename == "METADATA" else None

    def locate_file(self, path):
        raise NotImplementedError("Metadata text has no installed files")


@lru_cache(maxsize=64)
def _parsed_version(text):
    return _MetadataText(text).version


def package_version(package):
    """Match Distribution.version without retaining an installed-state snapshot."""
    current = distribution(package)
    if (type(current).version is not Distribution.version
            or type(current).metadata is not Distribution.metadata):
        return current.version
    text = current.read_text("METADATA") or current.read_text("PKG-INFO") or current.read_text("")
    if not isinstance(text, str) or len(text) > _MAX_CACHE_CHARACTERS:
        return _MetadataText(text).version
    return _parsed_version(text)
