# P12 — Scoped MCP service identity and access evidence

P12 is a tested foundation for D06/D08. It binds local MCP inspection and proposals to a named active Django account and an explicit grant for each dataset. It records authority before reading customer artifacts, then rechecks the account, process scope, grant role, expiry and revision before returning results. It does not complete either roadmap outcome or authorize an agent to execute a proposal.

## Operator workflow

Apply migrations to the installation database. Existing datasets and users receive no automatic grants; previously configured MCP clients must be configured explicitly. Existing files and evidence remain unchanged.

Create a dedicated, active service account in Django admin using the installation's established administrator process. Use a distinct account for each local integration and keep its credentials under the installation's control. Grant management and audit inspection are available only to active superusers in `/admin/`. Even staff with explicit model permissions cannot change these grants. Audit rows are read-only through that interface; revoke grants instead of deleting them.

An installation administrator can alternatively use the trusted local database CLI:

```bash
cd backend
python manage.py migrate
python manage.py mcp_dataset_grant --actor local-mcp-reviewer --file-id 42 --role read
python manage.py mcp_dataset_grant --actor local-mcp-developer --file-id 42 --role prepare --expires-at 2026-12-01T00:00:00Z
python manage.py mcp_dataset_grant --actor local-mcp-developer --file-id 42 --revoke
```

The usernames and dataset ID are examples; they must exist. `read` permits inspection; `prepare` permits inspection and reviewable proposals. Both roles still require the matching process scope. Accounts without a grant are denied, including superusers. Grant updates rotate a revision and record their outcome atomically with the change. A failed audit write rolls back a grant change.

Configure the **local stdio process** with the account's numeric user ID, obtained by the administrator:

```bash
export DECLARAI_MCP_ACTOR_USER_ID=123
export DECLARAI_MCP_SCOPES=declarai.pipeline.read,declarai.action.prepare
python manage.py run_mcp_server
```

The numeric ID is an installation binding controlled by the trusted operator, not a bearer token or an authenticated remote client's identity. Restrict access to the process, environment and database accordingly. The process authority is shared by its local host; it cannot distinguish multiple remote users. `streamable-http`, SSE and the SDK's network app constructors fail closed until authenticated per-client authority exists. Do not expose the process through a remote bridge as a substitute for that missing boundary.

Discover `declarai.get_mcp_tool_catalog`; call `declarai.get_data_dictionary` with an authorized `file_id`. A read-only grant cannot call `declarai.prepare.update_notes`. A prepare grant returns the action candidate, an access receipt, `execution_available=false` and `execution_blocker=mcp_exact_approval_unavailable`. Proposals do not change notes, configuration or datasets. No `declarai.action.*` tool is registered. `--direct-actions`, invented approval IDs and the legacy enable/approval-bypass environment flags cannot enable execution. Signed Prometa bundles obey the same local boundary; signature verification does not create a dataset grant or an exact action approval.

## Access evidence and failure behavior

The additive `access_control` app stores `MCPDatasetGrant` and `MCPAccessEvent`. A reservation is required before each read, catalog request or preparation. The event records the actor, actor snapshot, grant snapshot/revision, dataset ID, tool, scope, argument digest, authority source, timestamps, outcome and reason code. It stores neither customer outputs nor raw action payloads. Grant snapshots retain the target account and dataset IDs separately from the administrator making a change; these identifiers and actor snapshots survive account, grant and dataset deletion. Argument hashes are correlation evidence, not encryption or proof of action approval; retention and privacy policy still require deployment-specific qualification.

| Outcome | Meaning |
| --- | --- |
| `started` | Access was reserved; it may have started. Interrupted calls or failed completion writes remain unconfirmed. |
| `completed` | The handler finished, authority was rechecked and the audit completion write succeeded before output was released. This is not a delivery acknowledgement or production approval. |
| `denied` | Identity, scope or dataset authority failed before the handler ran. |
| `failed` | An authorized handler failed, or direct execution was rejected. |
| `withheld` | Authority changed or could not be revalidated after the handler; its output was not returned. |

Unauditable access and unavailable authority block customer reads. If the database is unavailable, the application cannot guarantee a denial record was stored. An interrupted or unauditable completion must not be presented as successful delivery. Grant changes through the supported admin/CLI paths rotate revisions; concurrent revocation, expiry, role changes, actor deactivation or scope removal withhold results at revalidation. There is no guarantee that already delivered data can be recalled, nor a distributed transaction spanning output delivery and a later revocation.

FastMCP dispatches synchronous handlers through a database thread so Django's asynchronous safety checks remain enabled. MCP telemetry remains supplementary; the database records are the authoritative local access evidence. Telemetry/LLM/embedding egress has not been qualified under a common data policy.

## Repeatable qualification

Only in a disposable installation with migrations applied and Redis available:

```bash
DECLARAI_TEST_INSTALLATION=1 python scripts/qualify_mcp_stdio.py
```

The script creates synthetic datasets and a dedicated account, launches the actual MCP SDK stdio server/client, exercises allowed and ungranted reads, read-only proposal denial, a role change, a successful proposal, live revocation and account deactivation. It verifies catalog/schema discovery, blocked network/direct startup, audit outcomes and retained snapshots after fixture cleanup. It never uses customer files, grants existing users access or supplies default credentials. It also runs in the disposable CI browser/API job.

Regression checks cover audit reservation/completion failure, authority changes during reads, invalid IDs, legacy approval flags, administrator HTTP permissions and atomic grant rollback. The source qualification receipt is [P12 qualification](evidence/p12-qualification-2026-10-09.json).

## Remaining boundaries

Browser/API sign-in remains the existing installation-wide boundary. Dataset MCP grants do not impose project authorization on REST downloads, browser actions, caches, embeddings or other entrypoints. Developer/reviewer/admin project roles, authenticated MCP HTTP/OAuth, exact code/input/environment approvals, isolated expert Python, full egress/retention policy, tamper-resistant audit storage, distributed recovery and independent security/release/customer qualification remain open. Trusted operating-system/database administrators can rewrite records; these events are not cryptographically signed or append-only against that authority. No D18–D26 progress or autonomy grant is claimed.
