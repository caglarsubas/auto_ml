"""
Canonical byte representation for Prometa deployment bundle signatures.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


CANONICALIZATION_ALGORITHM = "json-sorted-keys-utf8"
LEGACY_CANONICALIZATION_ALGORITHMS = frozenset(
    {None, "", "json-stable-sort-keys-utf8-no-ascii-escape-v1"}
)
SUPPORTED_CANONICALIZATION_ALGORITHMS = frozenset(
    {CANONICALIZATION_ALGORITHM, *LEGACY_CANONICALIZATION_ALGORITHMS}
)


class CanonicalizationError(ValueError):
    """Raised when a bundle declares an unsupported canonicalization."""


def canonicalization_from_envelope(envelope: Mapping[str, Any]) -> str | None:
    value = envelope.get("canonicalization")
    if value is None:
        return None
    if not isinstance(value, str):
        raise CanonicalizationError("Bundle canonicalization must be a string.")
    return value


def require_supported_canonicalization(envelope: Mapping[str, Any]) -> str:
    declared = canonicalization_from_envelope(envelope)
    if declared not in SUPPORTED_CANONICALIZATION_ALGORITHMS:
        raise CanonicalizationError(
            f"Unsupported Prometa bundle canonicalization: {declared!r}."
        )
    return declared or CANONICALIZATION_ALGORITHM


def canonicalize_bundle_content(content: Mapping[str, Any]) -> bytes:
    """Return the exact bytes Prometa signs for ``content``.

    Mirrors Prometa's TypeScript helper:

    ``JSON.stringify(stable(content))``

    where ``stable`` recursively sorts object keys, preserves array order, and
    leaves primitive values unchanged. Python details that matter:

    - ``sort_keys=True`` recurses through dictionaries;
    - compact separators match ``JSON.stringify`` spacing;
    - ``ensure_ascii=False`` keeps non-ASCII text as UTF-8 bytes;
    - ``allow_nan=False`` rejects NaN/Infinity instead of emitting invalid
      JavaScript-compatible values.
    """
    return json.dumps(
        content,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
