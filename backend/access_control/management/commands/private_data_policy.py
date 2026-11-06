"""Offline installation-operator commands for the sealed data policy."""

import json
import re
import uuid

from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connection

from access_control import audit_checkpoint, retention
from access_control.data_policy import policy, policy_digest, private
from backend.runtime_config import _secret


class Command(BaseCommand):
    help = "Inspect policy, review/purge unused private uploads, and seal/verify audit checkpoints."

    def add_arguments(self, parser):
        actions = parser.add_subparsers(dest="operation", required=True)
        actions.add_parser("describe")
        for name in ("review-upload", "purge-upload"):
            action = actions.add_parser(name)
            action.add_argument("--file-id", type=int, required=True)
            action.add_argument("--quiescent", action="store_true", required=True)
            if name == "purge-upload":
                action.add_argument("--expected", required=True)
                action.add_argument("--request-id", type=uuid.UUID, required=True)
                action.add_argument("--operator-label", required=True)
        for name in ("seal-audit", "verify-audit"):
            action = actions.add_parser(name)
            action.add_argument("--scope", required=True)
            action.add_argument("--key-file", required=True)
            action.add_argument("--checkpoint", required=True)

    def handle(self, *args, **options):
        op = options["operation"]
        try:
            if op == "describe":
                result = {"policy": policy(), "policy_sha256": policy_digest(), "active": private()}
            elif not private() or connection.vendor != "postgresql":
                raise CommandError("private_postgresql_runtime_required")
            elif op in ("review-upload", "purge-upload"):
                file_id = options["file_id"]
                if not options["quiescent"] or not 0 < file_id <= 2**63 - 1:
                    raise CommandError("retention_requires_quiescence_and_valid_file_id")
                if op == "review-upload":
                    result = retention.review(file_id)
                else:
                    label = options["operator_label"].strip()
                    expected = options["expected"]
                    if not label or len(label) > 100 or not label.isprintable() or not re.fullmatch("[0-9a-f]{64}", expected):
                        raise CommandError("retention_requires_operator_label_and_review_digest")
                    result = retention.purge(file_id, expected, options["request_id"], label)
            else:
                scope = options["scope"]
                secret = _secret({"AUDIT_KEY_FILE": options["key_file"]}, "AUDIT_KEY", private=True)
                if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", scope) or not re.fullmatch("[0-9a-fA-F]{64}", secret):
                    raise CommandError("audit_requires_scope_and_32_byte_hex_key")
                operation = audit_checkpoint.seal if op == "seal-audit" else audit_checkpoint.verify
                result = operation(bytes.fromhex(secret), scope, options["checkpoint"])
        except retention.RetentionError as exc:
            raise CommandError(str(exc)) from None
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            code = str(exc)
            safe = code in {
                "audit_checkpoint_invalid", "audit_checkpoint_unreadable", "audit_checkpoint_row_limit",
                "audit_checkpoint_byte_limit", "audit_captured_rows_changed_or_missing",
                "audit_requires_independent_snapshot",
            }
            raise CommandError(code if safe else "private_data_policy_input_invalid") from None
        except (OSError, DatabaseError, ImproperlyConfigured):
            raise CommandError("private_data_policy_storage_or_configuration_failed") from None
        self.stdout.write(json.dumps(result, sort_keys=True))
