# Honest saved SFS state (P55)

When process-local SFS progress disappeared, the UI status reader treated saved errors, unknown states and even JSON read failures as completed. The assistant separately treated unreadable files as no run and inferred completion when status was missing. This could hide a failed publication after a restart or encourage a new run without inspecting existing evidence.

A shared recorded-state reader now requires an explicit supported status and valid JSON object. Duplicate keys, nonfinite JSON constants, malformed direction lists and contradictory completion/error records are unavailable. Status/results endpoints return HTTP 503 with a safe reason code and no completion claim for invalid evidence; the assistant reports unavailable and asks for inspection. Error records retain the exact recorded operation ID, exception stage and failure detail across all readers. Supported stopped/completed records keep their existing semantics; a recorded running state with no local owner is interrupted. Live process progress retains precedence, and an absent file remains no run.

Results expose the recorded state while progress/assistant readers interpret the absence of a live owner. Neither reader edits saved history, repairs records, retrains or approves a model. Missing historical status is disclosed as unavailable; it is not reconstructed as successful execution. Existing dataset/project authorization remains in force. These checks validate state shape, not a cryptographic signature or independent scientific assessment.

Nineteen regression cases exercise cross-reader error retention, corrupt/unknown/missing/contradictory states, duplicate keys, nonfinite values, valid outcomes, live precedence, unreadable-file refusal and absence. Fifteen fail against the preceding views and assistant readers. Full-suite/native qualification remains mandatory; budgets and scientific fixtures are unchanged.

Thread-based SFS is not a qualified distributed worker service. An interrupted state does not authorize automatic resume; existing versioned search-basis checks and human authority still apply. D07 lifecycle/recovery, expert isolation and release/customer gates remain open.

Local source receipts: [P55 qualification](evidence/p55-qualification-2026-10-14.json). Exact-head all-six checks, complete private/Linux receipts and separate main verification are required before adoption claims.
