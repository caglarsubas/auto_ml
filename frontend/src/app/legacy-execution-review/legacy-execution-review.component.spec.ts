import { TestBed, fakeAsync, tick } from '@angular/core/testing';
import { LegacyExecutionReviewComponent } from './legacy-execution-review.component';
import { LegacyExecutionReviewService } from '../services/legacy-execution-review.service';

describe('Execution review dialog', () => {
  beforeEach(() => TestBed.configureTestingModule({ imports: [LegacyExecutionReviewComponent] }));
  const proposal = {
    fileId: 4,
    operation: 'hpo' as const,
    options: { algorithm: 'xgboost', n_iter: 2 },
    preview: {
      inputs_sha256: 'a'.repeat(64),
      plan_sha256: 'b'.repeat(64),
      budget: { seconds: 120, max_active: 2 },
    },
  };
  it('opens a named modal with the exact budget and cancels by native keyboard event', fakeAsync(() => {
    const fixture = TestBed.createComponent(LegacyExecutionReviewComponent);
    const review = TestBed.inject(LegacyExecutionReviewService);
    fixture.detectChanges();
    const decision = jasmine.createSpy('decision');
    review.request(proposal).subscribe(decision);
    fixture.detectChanges();
    tick();
    const dialog: HTMLDialogElement = fixture.nativeElement.querySelector('dialog');
    expect(dialog.open).toBeTrue();
    expect(dialog.textContent).toContain('120 seconds');
    expect(dialog.getAttribute('aria-labelledby')).toBe('legacy-execution-title');
    dialog.dispatchEvent(new Event('cancel', { cancelable: true }));
    expect(decision).toHaveBeenCalledOnceWith(false);
    expect(dialog.open).toBeFalse();
    fixture.destroy();
  }));
  it('confirming emits one decision and destroys no outstanding request', fakeAsync(() => {
    const fixture = TestBed.createComponent(LegacyExecutionReviewComponent);
    const review = TestBed.inject(LegacyExecutionReviewService);
    fixture.detectChanges();
    const decision = jasmine.createSpy('decision');
    review.request(proposal).subscribe(decision);
    fixture.detectChanges();
    tick();
    const buttons = [...fixture.nativeElement.querySelectorAll('button')] as HTMLButtonElement[];
    buttons.find((button) => button.textContent?.includes('Submit reviewed'))!.click();
    expect(decision).toHaveBeenCalledOnceWith(true);
    fixture.destroy();
    expect(decision).toHaveBeenCalledTimes(1);
  }));
});
