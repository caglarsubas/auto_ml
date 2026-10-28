"""Fresh native JSON decoding; optional acceleration never retains row values."""

import json
from functools import partial
import sys

from django.db.models import JSONField
from deployment.runtime_metadata import package_version

try:
    from pydantic_core import from_json as _from_json
except ImportError:
    _from_json = None

_FAST_LOADS = partial(_from_json, allow_inf_nan=False, cache_strings=False, allow_partial=False) if _from_json is not None else None
_STOCK_FROM_DB = JSONField.from_db_value
_STOCK_LOADS = json.loads
_STOCK_DECODER_CLASS = json.JSONDecoder
_STOCK_DECODE = json.JSONDecoder.decode
_STOCK_RAW_DECODE = json.JSONDecoder.raw_decode
_STOCK_ERROR = json.JSONDecodeError
_STOCK_DECODER = json._default_decoder
_STOCK_DECODER_STATE = vars(_STOCK_DECODER).copy()
_MAX_FAST_CHARACTERS = 1024 * 1024


def _standard_decoder():
    return (json.loads is _STOCK_LOADS and json.JSONDecoder is _STOCK_DECODER_CLASS
            and json.JSONDecoder.decode is _STOCK_DECODE and json.JSONDecoder.raw_decode is _STOCK_RAW_DECODE
            and json.JSONDecodeError is _STOCK_ERROR and json._default_decoder is _STOCK_DECODER
            and vars(json._default_decoder) == _STOCK_DECODER_STATE
            and sys.get_int_max_str_digits() == sys.int_info.default_max_str_digits)


def accelerated_value(value):
    """Return (used, value); declined inputs keep Django's original boundary."""
    if (_FAST_LOADS is None or type(value) is not str or len(value) > _MAX_FAST_CHARACTERS
            or not _standard_decoder()):
        return False, None
    try:
        return True, _FAST_LOADS(value)
    except (ValueError, UnicodeError):
        # Nonstandard numbers, unsupported nesting/Unicode and malformed JSON
        # must retain the standard parser's exact value/error behavior.
        return False, None


def runtime_profile():
    if _FAST_LOADS is None:
        return {'implementation': 'stdlib-json', 'version': sys.version.split()[0]}
    # A loaded extension without fresh installed provenance is not a profile.
    return {'implementation': 'pydantic-core.from_json', 'version': package_version('pydantic-core')}


class NativeJSONField(JSONField):
    """Same JSON storage/migration contract, with compatible reads accelerated."""

    def deconstruct(self):
        name, _, args, kwargs = super().deconstruct()
        return name, 'django.db.models.JSONField', args, kwargs

    def from_db_value(self, value, expression, connection):
        if self.decoder is None and JSONField.from_db_value is _STOCK_FROM_DB:
            used, parsed = accelerated_value(value)
            if used:
                return parsed
        return super().from_db_value(value, expression, connection)
