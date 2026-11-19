export const JOB_KINDS = [
  ['package_integrity_v1', 'Package integrity'],
  ['native_csv_scoring_v1', 'Package CSV scoring'],
  ['native_numeric_training_search_v1', 'Development training search'],
  ['legacy_native_execution_v1', 'Durable modeling and search'],
  ['native_training_scoring_v1', 'Native candidate scoring'],
  ['native_protected_assessment_v1', 'Protected assessment'],
];

export function jobKindLabel(kind: string, operation?: string): string {
  const label = JOB_KINDS.find(([value]) => value === kind)?.[1] ?? 'Recorded job';
  return kind === 'legacy_native_execution_v1' && operation ? `${label} · ${operation}` : label;
}

export function jobStateLabel(state: string): string {
  const labels: Record<string, string> = {
    queued: 'Queued',
    running: 'Running',
    cancel_requested: 'Cancellation requested',
    succeeded: 'Completed',
    blocked: 'Blocked',
    failed: 'Failed',
    cancelled: 'Cancelled',
  };
  return labels[state] ?? 'Recorded state unavailable';
}

export function jobNextStep(state: string): string {
  const steps: Record<string, string> = {
    queued: 'Recorded as queued. Refresh jobs to check dispatch of this request.',
    running: 'Recorded as running. Refresh jobs to check its next recorded state.',
    cancel_requested:
      'Cancellation is recorded. Refresh jobs until the worker acknowledges it or its lease expires.',
    cancelled:
      'Cancellation is complete. Retain this receipt and any recorded outcome accesses before preparing another request.',
    blocked:
      'A required control could not be verified. Inspect operational handoff and ask the project owner to review the reason before preparing another request.',
    failed:
      'Execution stopped. Inspect operational handoff with the installation operator and retain this receipt before deciding on recovery.',
    succeeded:
      'The result is ready to inspect. Review the recorded evidence and the required next action below.',
  };
  return steps[state] ?? 'Refresh jobs to retrieve a verified state before taking another action.';
}
