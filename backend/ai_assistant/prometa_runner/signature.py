"""
Ed25519 signature verification for Prometa deployment bundles.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
from typing import Any

from ai_assistant.prometa_runner.canonicalization import (
    canonicalize_bundle_content,
    require_supported_canonicalization,
)


class BundleVerificationError(ValueError):
    """Raised when a Prometa bundle cannot be trusted."""


def verify_bundle_signature(
    envelope: Mapping[str, Any],
    *,
    require_signature: bool = True,
) -> bool:
    """Verify a Prometa bundle envelope.

    The envelope is the response from:
    ``GET /api/agent-manifests/{id}/bundle``.

    Prometa signs the canonical ``content`` bytes with Ed25519. ``publicKey`` is
    a base64 SPKI public key, and ``signature`` is a detached base64 signature.
    """
    content = envelope.get("content")
    if not isinstance(content, Mapping):
        raise BundleVerificationError("Prometa bundle is missing object content.")

    try:
        require_supported_canonicalization(envelope)
    except Exception as exc:
        raise BundleVerificationError(str(exc)) from exc

    signed = bool(envelope.get("signed"))
    algorithm = envelope.get("algorithm")
    public_key = envelope.get("publicKey")
    signature = envelope.get("signature")
    if not signed:
        if require_signature:
            raise BundleVerificationError("Prometa bundle is unsigned.")
        return False
    if algorithm != "ed25519":
        raise BundleVerificationError(
            f"Unsupported Prometa bundle signature algorithm: {algorithm!r}."
        )
    if not isinstance(public_key, str) or not public_key.strip():
        raise BundleVerificationError("Prometa bundle is missing publicKey.")
    if not isinstance(signature, str) or not signature.strip():
        raise BundleVerificationError("Prometa bundle is missing signature.")

    try:
        key = _load_ed25519_public_key(public_key)
        sig_bytes = base64.b64decode(signature, validate=True)
        key.verify(sig_bytes, canonicalize_bundle_content(content))
        return True
    except BundleVerificationError:
        raise
    except Exception as exc:
        raise BundleVerificationError(
            "Prometa bundle signature verification failed."
        ) from exc


def _load_ed25519_public_key(public_key_b64: str):
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise BundleVerificationError(
            "cryptography is required to verify Prometa Ed25519 bundles."
        ) from exc

    pem = (
        "-----BEGIN PUBLIC KEY-----\n"
        f"{public_key_b64.strip()}\n"
        "-----END PUBLIC KEY-----"
    ).encode("ascii")
    key = load_pem_public_key(pem)
    if not isinstance(key, Ed25519PublicKey):
        raise BundleVerificationError("Prometa bundle publicKey is not Ed25519.")
    return key
