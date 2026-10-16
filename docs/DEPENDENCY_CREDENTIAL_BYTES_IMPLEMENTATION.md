# Dependency credential byte preservation (P76)

Fresh dependency provisioning decoded broker/cache URL passwords and then used
its password-file parser. That parser stripped trailing CR/LF, silently replacing
an encoded credential with different bytes in `requirepass`. Runtime rejects
these encoded controls, so provisioning could publish a configuration that the
application could never authenticate against.

Password-file parsing now makes newline stripping explicit. Direct delivered
password files retain their established newline behavior. Redis URL files also
retain their normal trailing file delimiters, removed before URL parsing; the
decoded password is validated without trimming. Encoded CR/LF therefore fails
with the existing static `dependency_password_invalid` error. Valid credential
bytes, strength rules and escaping remain unchanged; valid inputs generate
identical Redis configuration bytes.

Thirty-two new cases cover broker and cache parsers, configuration generation,
and initialization order. Encoded controls block before certificates or dependency
staging; controlled capture/host seams exercise the real initialization function
against an owned empty temporary directory. Literal URL-file newlines, Unicode,
reserved characters, spaces and a literal percent-encoded-looking suffix remain
supported without double decoding. The predecessor fails eighteen negative cases
and passes fourteen compatibility references. Existing full Linux-root private
qualification remains required for real valid deliveries, TLS, schema/accounts,
adoption, recovery, exact images and owned cleanup.

No existing secret, dependency directory or installation is rewritten. No
password generation, rotation, credential recovery or migration is introduced.
D07 remains in progress; durable search, lifecycle/upgrade/rollback/restore,
expert isolation, release and customer acceptance remain open. Exact-head and
independent main CI are separate qualification states.
