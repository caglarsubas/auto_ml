import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable, Subject } from 'rxjs';

export interface LegacyExecutionProposal {
  fileId: number;
  operation: 'training' | 'sfs' | 'hpo';
  options: Record<string, any>;
  preview: any;
}

export class LegacyExecutionCancelled extends Error {
  readonly executionCancelled = true;
  constructor() {
    super('Execution canceled before submission.');
  }
}

@Injectable({ providedIn: 'root' })
export class LegacyExecutionReviewService {
  readonly pending$ = new BehaviorSubject<LegacyExecutionProposal | null>(null);
  private decision: Subject<boolean> | null = null;

  request(proposal: LegacyExecutionProposal): Observable<boolean> {
    return new Observable((subscriber) => {
      if (this.decision) {
        subscriber.error(new Error('Finish the current execution review first.'));
        return;
      }
      const decision = new Subject<boolean>();
      this.decision = decision;
      const subscription = decision.subscribe(subscriber);
      this.pending$.next(proposal);
      return () => {
        subscription.unsubscribe();
        if (this.decision === decision) this.resolve(false);
      };
    });
  }

  resolve(accepted: boolean): void {
    const decision = this.decision;
    this.decision = null;
    this.pending$.next(null);
    decision?.next(accepted);
    decision?.complete();
  }
}
