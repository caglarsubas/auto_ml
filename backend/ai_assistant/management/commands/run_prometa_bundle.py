"""Verify and run a signed Prometa deployment bundle locally."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from ai_assistant.prometa_runner.runner import PrometaOnPremBundleRunner


class Command(BaseCommand):
    help = "Verify/preflight a signed Prometa bundle and optionally call a bundled MCP tool."

    def add_arguments(self, parser):
        source = parser.add_mutually_exclusive_group(required=True)
        source.add_argument(
            "--bundle-file",
            help="Path to a Prometa bundle JSON file.",
        )
        source.add_argument(
            "--manifest-id",
            help="Prometa agent manifest id to fetch from /api/agent-manifests/{id}/bundle.",
        )
        parser.add_argument(
            "--prometa-url",
            help="Prometa base URL when using --manifest-id.",
        )
        parser.add_argument(
            "--token",
            help="Bearer token for Prometa bundle fetch.",
        )
        parser.add_argument(
            "--timeout",
            type=float,
            default=30.0,
            help="Prometa fetch timeout in seconds.",
        )
        parser.add_argument(
            "--allow-unsigned",
            action="store_true",
            help="Allow unsigned bundles. For local development only.",
        )
        parser.add_argument(
            "--tool",
            help="Bundled MCP operation to call, for example declarai.prepare.update_notes.",
        )
        parser.add_argument(
            "--arguments",
            default="{}",
            help="JSON object arguments for --tool.",
        )
        parser.add_argument(
            "--approval-id",
            help="Human approval record id for approval-required tool calls.",
        )

    def handle(self, *args, **options):
        require_signature = not options["allow_unsigned"]
        try:
            if options["bundle_file"]:
                runner = PrometaOnPremBundleRunner.from_file(
                    options["bundle_file"],
                    require_signature=require_signature,
                )
            else:
                if not options["prometa_url"]:
                    raise CommandError("--prometa-url is required with --manifest-id.")
                runner = PrometaOnPremBundleRunner.from_prometa(
                    base_url=options["prometa_url"],
                    manifest_id=options["manifest_id"],
                    token=options["token"],
                    timeout=options["timeout"],
                    require_signature=require_signature,
                )

            if not options["tool"]:
                self.stdout.write(json.dumps(runner.summary(), indent=2, sort_keys=True))
                return

            try:
                arguments = json.loads(options["arguments"])
            except json.JSONDecodeError as exc:
                raise CommandError("--arguments must be a JSON object.") from exc
            if not isinstance(arguments, dict):
                raise CommandError("--arguments must be a JSON object.")

            result = runner.call_tool(
                options["tool"],
                arguments,
                approval_id=options["approval_id"],
            )
            self.stdout.write(json.dumps(result, indent=2, sort_keys=True))
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(str(exc)) from exc
