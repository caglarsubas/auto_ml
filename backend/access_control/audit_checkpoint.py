"""Operator-held tamper evidence for captured database audit rows."""

import hashlib
import hmac
import json
import os
import re
import stat
from datetime import date, datetime
from uuid import UUID

from django.db import connection, transaction

from access_control.data_policy import canonical, policy_digest
from access_control.models import (
    AssistantActionApproval, AuthenticationEvent, MCPAccessEvent, ProjectAuthorityEvent,
)
from deployment.models import PackageReviewEvent
from execution_jobs.models import JobEvent, NativeAdoptionEvent
from modeling.models import HoldoutAccess

TABLES = (
    AuthenticationEvent, ProjectAuthorityEvent, MCPAccessEvent, AssistantActionApproval,
    JobEvent, NativeAdoptionEvent, HoldoutAccess, PackageReviewEvent,
)
MAX_ROWS = 20_000
MAX_BYTES = 8 * 1024**2
SCHEMA = "private_audit_checkpoint_v1"


def _mac(key, domain, value):
    return hmac.new(key, domain + b"\0" + canonical(value), hashlib.sha256).hexdigest()


def _serialize(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def capture(key):
    if connection.in_atomic_block:
        raise ValueError("audit_requires_independent_snapshot")
    rows = {}
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        for model in TABLES:
            name = model._meta.label_lower
            for row in model.objects.order_by("pk").values().iterator(chunk_size=128):
                if len(rows) == MAX_ROWS:
                    raise ValueError("audit_checkpoint_row_limit")
                identifier = f"{name}:{row[model._meta.pk.attname]}"
                rows[identifier] = _mac(key, b"row", [identifier, {k: _serialize(v) for k, v in row.items()}])
    return rows


def seal(key, scope, path):
    rows = capture(key)
    payload = {"schema": SCHEMA, "scope": scope, "policy_sha256": policy_digest(), "rows": rows}
    data = canonical({"payload": payload, "hmac_sha256": _mac(key, b"checkpoint", payload)}) + b"\n"
    if len(data) > MAX_BYTES:
        raise ValueError("audit_checkpoint_byte_limit")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return {"scope": scope, "captured_rows": len(rows), "checkpoint_sha256": hashlib.sha256(data).hexdigest()}


def verify(key, scope, path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BYTES:
            raise ValueError("audit_checkpoint_unreadable")
        data = stream.read(MAX_BYTES + 1)
    envelope = json.loads(data)
    payload = envelope["payload"]
    signature = envelope["hmac_sha256"]
    if (len(data) > MAX_BYTES or data != canonical(envelope) + b"\n"
            or set(envelope) != {"payload", "hmac_sha256"}
            or set(payload) != {"schema", "scope", "policy_sha256", "rows"}
            or payload["schema"] != SCHEMA or payload["scope"] != scope
            or payload["policy_sha256"] != policy_digest()
            or not isinstance(signature, str) or not re.fullmatch("[0-9a-f]{64}", signature)
            or not hmac.compare_digest(signature, _mac(key, b"checkpoint", payload))):
        raise ValueError("audit_checkpoint_invalid")
    expected = payload["rows"]
    current = capture(key)
    if any(identifier not in current or not hmac.compare_digest(digest, current[identifier])
           for identifier, digest in expected.items()):
        raise ValueError("audit_captured_rows_changed_or_missing")
    return {"scope": scope, "verified_rows": len(expected), "additional_rows": len(current) - len(expected),
            "checkpoint_sha256": hashlib.sha256(data).hexdigest()}
