# Private installation data policy

The sealed private profile applies `private_local_data_v1`. Run
`python manage.py private_data_policy describe` inside the application image
to obtain the policy and its SHA-256. Refused application requests carry
the same version and digest.

## Egress and logs

The profile denies LLM inference, model discovery, embeddings, Prometa
telemetry and feedback, and remote bundle retrieval before using credentials,
caches, or clients. It allows authorized same-origin browser responses and the
installation's PostgreSQL and Redis dependencies. Installed services use the
existing internal network, TLS dependency configuration, and same-origin
ingress. Native typed assistant actions retain their existing scoped approval
path. Provider-assisted chat requires a future governed provider policy.

The fixed API, worker, and dispatcher launch discards raw stdout and stderr
after preflight. The ingress disables access and request error logging.
Operators can still observe preflight codes, service state, queue incidents,
and structured database receipts. Use these surfaces for diagnosis. Database
and broker operations remain in the installation custody boundary.

## Reviewed upload removal

Private dataset and pipeline deletion through the browser API returns a
retention refusal. Private upload metadata is immutable through that API.
Only unused managed CSV uploads registered by this version are eligible.
A file-specific use receipt, dictionary, grant, job, pipeline reference,
artifact, review, or holdout receipt retains the source. Historical and
unclassified data, derived evidence, audit receipts, and backup or recovery
copies remain under operator custody.

Use the sealed application image with its installed metadata credentials and
media mount. Stop the API, worker, dispatcher, and all other writers and
readers, including MCP. Keep PostgreSQL available to the maintenance command.
The flag records your assertion of exclusive custody. The command also
checks for other sessions on the installation database.

```sh
python manage.py private_data_policy review-upload --file-id FILE_ID --quiescent
python manage.py private_data_policy purge-upload --file-id FILE_ID --quiescent \
  --expected REVIEW_DIGEST --request-id REQUEST_UUID --operator-label LOCAL_OPERATOR
```

Review the returned project, file ID, size, and digest before submitting the
purge. The digest binds the binding revision, exact storage identity and bytes,
and active policy. The command first commits metadata removal and a pending
receipt, then removes the exact live CSV and records the outcome. Preserve
the request UUID and digest. If interrupted, retry the same command. If the
file was already removed, the receipt records observed absence. If the bytes
or custody changed, stop and reconcile the pending receipt before resuming
services. Operator labels are local assertions. Historical backup expiry
follows the installation's separately managed backup schedule.

## Verify captured audit history

Keep an installation-specific 32-byte random key in an absolute regular
single-link file, encoded as 64 hex digits with mode 0400 or 0600. Store the
key, the original receipt, and its reported digest independently of the
database and application. Use a stable, unique installation scope. Seal after
pending operations settle so expected status transitions do not invalidate the
checkpoint.

```sh
python manage.py private_data_policy seal-audit --scope INSTALLATION \
  --key-file /secure/audit.key --checkpoint /secure/checkpoint.json
python manage.py private_data_policy verify-audit --scope INSTALLATION \
  --key-file /secure/audit.key --checkpoint /secure/checkpoint.json
```

The checkpoint binds captured authentication, project, MCP, assistant,
native job and adoption, holdout, and package review rows in one consistent
database snapshot. It exports row identifiers and keyed hashes. Additional
rows are counted. A changed or missing captured row, wrong scope or key,
edited checkpoint, or changed policy fails verification. The command creates
a new mode-0600 file and caps one checkpoint at 20,000 rows and 8 MiB.
The operator must retain the trusted original. This verifies captured
database rows as of the checkpoint, with earlier history and privileged host
or key access outside its guarantees.

P171 qualifies these controls on the synthetic private installation profile.
Customer-specific retention periods, provider allowlists, legal-hold rules,
backup disposal, and the integrated D06-T03 threat-model exercise require
separate acceptance.
