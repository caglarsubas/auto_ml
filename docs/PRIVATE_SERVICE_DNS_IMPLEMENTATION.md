# Reserved private service DNS identities (P84)

Private dependency reuse and application adoption previously checked network
membership and required a dependency's own alias, but allowed a container to
advertise another service's name. In an owned internal Docker network, giving
the broker an additional `cache` alias made the configured cache name resolve
to both cache and broker endpoints. This reproduces ambiguous routing; it does
not demonstrate bypass of the existing TLS or authentication controls.

A shared controller guard now reserves `postgres`, `cache`, `job-broker`, `api`,
`worker`, `dispatcher` and `ingress` for their corresponding roles. Dependency,
application and temporary probe/preflight validators inspect container `Name`
and each network endpoint's reported `Aliases` and `DNSNames`. Case and trailing
root dots are normalized for this comparison. Another role's name or malformed
reported name metadata blocks with `installation_service_dns_conflict`, without
printing supplied names. Temporary helpers may not advertise any reserved role.
Own-role and generated names remain usable. Existing network membership, labels,
TLS/authentication, resource limits and readiness requirements still apply.

The controllers check observed Docker metadata before starting helpers or
accepting/reusing services. They do not reserve names transactionally against
later Docker administration, rewrite existing containers or change the Docker
control-plane trust model. Nonreserved aliases retain their existing behavior.
No generated composition, credentials, workload, model calculation, resource
budget, retry policy or workflow changes. Customer installations are untouched.

Forty-seven new metadata-boundary cases exercise the real dependency, application,
probe and shared preflight validators. Thirty-six fail against the predecessor;
eleven valid references pass. The existing dependency probe fixture is extracted
for reuse, with its actual unique helper identity rather than an inherited
PostgreSQL alias; all original profile assertions remain. The owned local DNS
reproduction uses no public ports or customer data, cleans up all its resources
and is separate from private TLS qualification. Its runner tag was observed after
the run and is not claimed as an exact sealed-image identity.

See [P84 source evidence](evidence/p84-qualification-2026-10-16.json).
Exact-head six-check CI, complete private/native receipts and separate merged-main
qualification remain required. D07 remains in progress, including dependency
findings, durable search, complete upgrade/restore, expert and release/customer
gates. P83's actual merge and main qualification are retained in the ledger.
