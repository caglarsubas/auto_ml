"""Fixtures for opt-in live Inference Engine tests (gemma4:26b, etc.)."""
from __future__ import annotations

import pytest


ENGINE_MODEL_KEY = "engine-gemma4-26b"
ENGINE_MODEL_ID = "gemma4:26b"


def _engine_ready() -> tuple[bool, str]:
    """Return (ok, reason). Never raises."""
    try:
        from ai_assistant import model_registry as mr
    except Exception as exc:  # pragma: no cover - import env issues
        return False, f"model_registry import failed: {exc}"

    if mr._fetch_engine_models() is None:
        return False, "engine /v1/models unreachable or unauthorized"

    try:
        mr._refresh_engine_models(force=True)
        cfg = mr.get_model_config(ENGINE_MODEL_KEY)
    except Exception as exc:
        return False, f"get_model_config({ENGINE_MODEL_KEY}) failed: {exc}"

    if cfg.get("provider") != "engine":
        return False, f"{ENGINE_MODEL_KEY} is not an engine provider"
    if cfg.get("model_id") != ENGINE_MODEL_ID:
        return False, (
            f"expected model_id={ENGINE_MODEL_ID!r}, got {cfg.get('model_id')!r}"
        )
    return True, "ok"


@pytest.fixture(scope="session")
def require_gemma4_26b():
    ok, reason = _engine_ready()
    if not ok:
        pytest.skip(f"live gemma4:26b unavailable: {reason}")
    return ENGINE_MODEL_KEY
