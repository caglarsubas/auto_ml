#!/usr/bin/env python3
"""Check CI trigger isolation and retained supersession using representative events.

This checks the simple scalar/context-substitution form used by this workflow,
not arbitrary YAML or the general GitHub expression language. Unsupported forms
fail for explicit review rather than producing an unverified policy result.
"""

import argparse
import itertools
import json
import re
from pathlib import Path


def concurrency(source):
    blocks = re.findall(r"(?m)^concurrency:[ \t]*\n((?:[ \t][^\n]*\n|\n)*)", source)
    if len(blocks) != 1:
        raise ValueError("Expected one workflow concurrency block")
    fields = {}
    for line in blocks[0].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"  (group|cancel-in-progress): (.+)", line)
        if not match or match[1] in fields:
            raise ValueError("Unsupported or duplicate concurrency field")
        fields[match[1]] = match[2]
    if set(fields) != {"group", "cancel-in-progress"} or fields["cancel-in-progress"] != "true":
        raise ValueError("Retain explicit within-group cancellation")
    return fields["group"]


def group(template, context):
    def substitute(match):
        if match[1] not in context:
            raise ValueError("Unsupported concurrency expression context")
        return context[match[1]]

    rendered = re.sub(r"\$\{\{ github\.([a-z_]+) \}\}", substitute, template)
    if not rendered or not re.fullmatch(r"[A-Za-z0-9_./ -]+", rendered):
        raise ValueError("Unsupported concurrency scalar/expression")
    # GitHub treats concurrency keys as case insensitive.
    return rendered.casefold()


def check(source):
    template = concurrency(source)
    failures = []
    checks = 0

    def event(trigger, ref="refs/heads/main"):
        return dict(workflow="CI", ref=ref, event_name=trigger,
                    sha="a" * 40, run_id="100")

    def relation(name, left, right, equal):
        nonlocal checks
        checks += 1
        if (group(template, left) == group(template, right)) != equal:
            failures.append(name)

    main_events = [event(name) for name in ("push", "schedule", "workflow_dispatch")]
    for left, right in itertools.combinations(main_events, 2):
        relation("isolate " + left["event_name"] + " / " + right["event_name"], left, right, False)
    contexts = main_events + [event("pull_request", "refs/pull/205/merge")]
    for context in contexts:
        relation("supersede older " + context["event_name"], context,
                 context | {"sha": "b" * 40, "run_id": "101"}, True)
        relation("isolate workflows for " + context["event_name"], context,
                 context | {"workflow": "Other workflow"}, False)
        relation("isolate refs for " + context["event_name"], context,
                 context | {"ref": "refs/heads/other"}, False)
        relation("case-insensitive identity for " + context["event_name"], context,
                 context | {"workflow": "ci"}, True)
    relation("isolate different pull requests", event("pull_request", "refs/pull/205/merge"),
             event("pull_request", "refs/pull/206/merge"), False)
    relation("isolate pull request and push", event("pull_request", "refs/pull/205/merge"),
             event("push"), False)
    return dict(checks=checks, failed=len(failures), failures=failures)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", type=Path,
                        default=Path(__file__).resolve().parents[1] / "workflows/ci.yml")
    args = parser.parse_args()
    try:
        result = check(args.workflow.read_text())
    except (OSError, ValueError) as exc:
        print(json.dumps(dict(error=str(exc))))
        return 1
    print(json.dumps(result))
    return int(bool(result["failed"]))


if __name__ == "__main__":
    raise SystemExit(main())
