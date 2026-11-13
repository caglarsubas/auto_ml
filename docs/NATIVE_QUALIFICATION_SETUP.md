# Reuse synthetic credential setup in native qualification

The independently triggered P176 main workflow reached the unchanged
900-second PostgreSQL process cap on all three attempts. The second
attempt's worker receipts matched all 7,772 case and skip identities from
the qualified PR, but its controller did not produce the final JUnit
report. These attempts remain failed.

The project-authority and assistant-approval fixtures reuse a real encoded
synthetic credential per test account and configured hasher instance.
Each case still creates its own database users, project assignments and
sessions. Login and CSRF handling continue through the same real server
paths, including credential verification. This removes redundant hash
generation during fixture setup without changing the password verifier,
test assertions, production behavior, or any application credential.

All 47 test function syntax trees in the two changed files are unchanged.
A focused local comparison kept the exact same 150 cases and zero skips:
43.882 seconds before and 11.386 seconds after. These Mac timings establish
only the setup improvement. Full native qualification requires the
original 7,772 cases, six skips, branch coverage, two loadfile workers,
zero worker restarts, and all original process and job limits. The
independent main run must publish complete passing reports.
