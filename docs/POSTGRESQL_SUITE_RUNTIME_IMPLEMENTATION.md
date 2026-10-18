# PostgreSQL suite execution budget

The first merged-main run after P102 timed out at 900 seconds near 99%.
The predecessor PR suite passed 4,205 tests with six existing skips in
864.682 seconds. The failed first attempt remains failed and retained;
this follow-up requires a new exact-head and independent merged-main workflow.

## Execution and isolation

The complete marked native suite runs with `pytest-xdist -n 2 --dist=loadfile
--max-worker-restart=0` within the existing two-CPU profile. Each file stays
on one worker with its original fixtures/assertions. A lost worker fails
qualification without an automatic restart or test retry.

[pytest-django creates a separate migrated database for each worker](https://pytest-django.readthedocs.io/en/stable/usage.html#running-tests-in-parallel-with-pytest-xdist).
[pytest-cov combines worker coverage](https://pytest-cov.readthedocs.io/en/stable/xdist.html).
An explicitly loaded test plugin assigns Redis databases 2/3 to the workers,
checks actual Redis connectivity and records actual PostgreSQL database names.
Missing, shared or incomplete isolation receipts fail qualification. Fixture
cache database 0 and job broker database 1 are untouched. Missing pytest-xdist
fails invocation; the private API lock and production execution are unchanged.

All 154 original test/helper/configuration files remain byte-identical. The
same marker selection, password hashers, scientific datasets/rounds, per-test
120-second timeout, native thread pools and resource limits remain in place.
The parent enforces one unchanged 900-second deadline, including both workers
and combined coverage finalization. Coverage remains gated at 50%, with the
same 15-skip budget. The ordinary backend CI suite remains a serial reference.

## Local evidence

Full native PostgreSQL: 4,205 passed, six existing skips, zero failures/errors,
in 250.316 seconds. All 4,211 case/skip identities match P102's
passing native report. Line coverage is 75.77%, branch coverage
66.12%. Actual worker PostgreSQL/Redis databases are distinct;
unavailable worker Redis blocks qualification before tests run.

Three local fixture failures remain retained: the first omitted Redis and
exhausted a 128 MiB focused database mount; the second exhausted a 256 MiB
focused temporary mount; the third macOS bind mount failed three original
temporary-directory permission/file-lock/replacement assertions. The final
fixture uses a native Linux ext filesystem volume with normal 1777 root-owned
/tmp permissions and real Redis. CPU/memory limits remain unchanged. These
fixture corrections do not modify CI limits or product/test assertions.

Source hashes, counts, coverage and preliminary outcomes are in
[the qualification receipt](evidence/postgresql-suite-runtime-2026-10-18.json).
The local suite uses disposable development PostgreSQL/Redis; it does not
establish private TLS, ordinary-role production or installation qualification.
All six exact-head CI jobs and complete native/private receipts must pass before
merge, followed by independently qualified main before P103. D07 stays in
progress; deployment/release/customer gates remain open.
