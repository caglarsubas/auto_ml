export interface SearchOperation {
  readonly fileId: number;
  readonly operationId: string;
}

export type SearchKind = 'sfs' | 'hyperparam';

export function isSearchOperationId(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value)
  );
}

export function readSearchOperation(reply: any, fileId: number): SearchOperation | null {
  return reply?.file_id === fileId && isSearchOperationId(reply?.operation_id)
    ? { fileId, operationId: reply.operation_id }
    : null;
}
