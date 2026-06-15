"""
Small in-plane HTTP client for fetching Prometa deployment bundles.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen


class PrometaBundleFetchError(RuntimeError):
    """Raised when the runner cannot fetch a bundle from Prometa."""


def fetch_bundle(
    *,
    base_url: str,
    manifest_id: str,
    token: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Fetch ``GET /api/agent-manifests/{id}/bundle`` from Prometa."""
    root = base_url.rstrip("/") + "/"
    path = f"api/agent-manifests/{quote(manifest_id, safe='')}/bundle"
    url = urljoin(root, path)
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise PrometaBundleFetchError(
            f"Prometa bundle fetch failed with HTTP {exc.code}: {body[:300]}"
        ) from exc
    except URLError as exc:
        raise PrometaBundleFetchError(f"Prometa bundle fetch failed: {exc}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PrometaBundleFetchError("Prometa bundle response was not JSON.") from exc
    if not isinstance(parsed, dict):
        raise PrometaBundleFetchError("Prometa bundle response must be a JSON object.")
    return parsed
