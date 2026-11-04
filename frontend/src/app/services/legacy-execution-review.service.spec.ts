import { LegacyExecutionReviewService } from './legacy-execution-review.service';

describe('Execution review lifecycle', () => {
  const proposal = { fileId: 1, operation: 'training' as const, options: {}, preview: {} };
  it('requires subscription and an explicit decision', () => {
    const service = new LegacyExecutionReviewService();
    const result = jasmine.createSpy('decision');
    const request = service.request(proposal);
    expect(service.pending$.value).toBeNull();
    request.subscribe(result);
    expect(service.pending$.value).toBe(proposal);
    expect(result).not.toHaveBeenCalled();
    service.resolve(true);
    expect(result).toHaveBeenCalledOnceWith(true);
    expect(service.pending$.value).toBeNull();
    service.resolve(true);
    expect(result).toHaveBeenCalledTimes(1);
  });
  it('refuses overlapping proposals and cancels abandoned review', () => {
    const service = new LegacyExecutionReviewService();
    const first = service.request(proposal).subscribe();
    let error: any;
    service.request(proposal).subscribe({ error: (reason) => (error = reason) });
    expect(error.message).toContain('Finish the current');
    first.unsubscribe();
    expect(service.pending$.value).toBeNull();
    const decision = jasmine.createSpy('decision');
    service.request(proposal).subscribe(decision);
    service.resolve(false);
    expect(decision).toHaveBeenCalledOnceWith(false);
  });
});
