# Native job pagination input bounds (P80)

Job listing converted the offset to an integer and rejected negative values,
but passed larger positive integers to database pagination. PostgreSQL rejected
values outside its signed 64-bit range, which the API reported as database
unavailability. A malformed request could therefore look like an operational
storage failure.

The API now checks the supported signed 64-bit offset range before querying
native jobs. Unsupported offsets receive the existing static request error.
Authentication and project authorization still run first. Valid integer syntax,
including signs, whitespace and Unicode digits, is preserved. Page size remains
50, with the same newest-first ordering, total, next-offset and response fields.

Twenty-five new cases cover oversized offsets for all three project roles,
absence of job queries after refusal, existing invalid-input behavior, denied
access, valid pagination and the largest supported offset. Tests use owned queue
summary metadata without model training, dispatch or scoring. The predecessor
fails nine cases and passes sixteen references; its invalid requests return 503
through the actual PostgreSQL path.

No execution, scientific, timeout, retry, coverage or skip budget changes.
This does not provide query-rate limiting or qualify larger deployment capacity.
D07 remains in progress; durable search, lifecycle/upgrade/restore, expert and
release/customer gates remain open.
