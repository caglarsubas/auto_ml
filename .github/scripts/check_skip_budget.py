#!/usr/bin/env python3
"""Fail CI when the number of skipped tests exceeds an allowed budget.

Environment-dependent tests (Redis, the LLM engine, the optional ``mcp``
package, frontend contract checks) call ``pytest.skip`` when their dependency
is unavailable. That is fine locally, but in CI those dependencies are provided,
so a large skip count means the suite is silently eroding rather than running.

Usage:
    python check_skip_budget.py <junit-xml> [--max-skips N]
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET


def count_skips(junit_path: str) -> tuple[int, int]:
    """Return (skipped, total) test counts from a JUnit XML report."""
    tree = ET.parse(junit_path)
    root = tree.getroot()

    # pytest emits either a <testsuites> wrapper or a single <testsuite>.
    suites = root.findall("testsuite") if root.tag == "testsuites" else [root]

    skipped = 0
    total = 0
    for suite in suites:
        skipped += int(suite.get("skipped", 0))
        total += int(suite.get("tests", 0))
    return skipped, total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("junit_xml", help="Path to the pytest JUnit XML report")
    parser.add_argument(
        "--max-skips",
        type=int,
        default=15,
        help="Maximum number of skipped tests allowed before failing (default: 15)",
    )
    args = parser.parse_args()

    try:
        skipped, total = count_skips(args.junit_xml)
    except (FileNotFoundError, ET.ParseError) as exc:
        print(f"::warning::Could not read skip budget from {args.junit_xml}: {exc}")
        # Missing/unparseable report should not by itself fail the build here;
        # the test step already reports its own status.
        return 0

    print(f"Skipped {skipped} of {total} tests (budget: {args.max_skips}).")

    if skipped > args.max_skips:
        print(
            f"::error::Skip budget exceeded: {skipped} skipped tests > "
            f"{args.max_skips} allowed. Investigate missing test dependencies "
            f"(Redis, LLM engine, mcp) or lower the number of skipped tests."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
