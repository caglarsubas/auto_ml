import { ComponentFixture, TestBed } from '@angular/core/testing';
import { FormsModule } from '@angular/forms';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { of, Subject, throwError } from 'rxjs';

import { EvaluationComponent } from './evaluation.component';
import { SharedService } from '../services/shared.service';
import { DataService } from '../services/data.service';

describe('EvaluationComponent', () => {
  let component: EvaluationComponent;
  let fixture: ComponentFixture<EvaluationComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [EvaluationComponent],
      imports: [
        FormsModule,
        HttpClientTestingModule,
        NoopAnimationsModule,
        MatFormFieldModule,
        MatInputModule,
        MatButtonModule,
      ],
      providers: [SharedService, DataService],
    }).compileComponents();

    fixture = TestBed.createComponent(EvaluationComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('shows exploratory reuse counts with expandable access records', () => {
    component.selectedExecutionId = 'version-2';
    component.holdoutHistory = {
      same_final_rows_accesses: 2,
      overlapping_final_rows_accesses: 1,
      unknown_history_accesses: 3,
      limitation: 'Independent confirmation remains required.',
      records: [
        {
          access_id: 'receipt-1',
          actor: { username: 'reviewer' },
          attempt_state: 'failed',
          relation: 'same_final_rows',
          execution_id: 'version-1',
        },
      ],
    };
    fixture.detectChanges();
    const section: HTMLElement = fixture.nativeElement.querySelector(
      '[aria-label="Final-outcome access history"]',
    );
    expect(section.textContent).toContain('2 accesses to the same final rows');
    expect(section.textContent).toContain('1 accesses to overlapping final rows');
    expect(section.textContent).toContain('3 accesses with unknown historical identity');
    expect(section.querySelector('details')?.open).toBeFalse();
    expect(section.querySelector('summary')?.textContent).toContain(
      'Access records and limitations',
    );
    expect(section.textContent).toContain('failed');
  });

  it('pins assessment to the selected execution and refreshes access after failure', () => {
    const service = TestBed.inject(DataService);
    component.currentFileId = 7;
    component.selectedExecutionId = 'version-2';
    const run = spyOn(service, 'runEvaluation').and.returnValue(
      throwError(() => new Error('read failed')),
    );
    const refresh = spyOn(component, 'refreshHoldoutHistory');
    component.runEvaluation();
    expect(run).toHaveBeenCalledWith(7, 0.5, undefined, 'version-2');
    expect(refresh).toHaveBeenCalled();
    expect(component.error).toBe('read failed');
    expect(component.isRunning).toBeFalse();
  });

  it('ignores a history response after the selected file changes', () => {
    const service = TestBed.inject(DataService);
    const response = new Subject<any>();
    spyOn(service, 'getHoldoutHistory').and.returnValue(response);
    component.currentFileId = 7;
    component.selectedExecutionId = 'version-2';
    component.refreshHoldoutHistory();
    component.currentFileId = 8;
    component.selectedExecutionId = 'version-3';
    response.next({ records: [], same_final_rows_accesses: 90 });
    expect(component.holdoutHistory).toBeNull();
  });

  it('discloses unavailable history without describing the holdout as unused', () => {
    const service = TestBed.inject(DataService);
    spyOn(service, 'getHoldoutHistory').and.returnValue(throwError(() => new Error('offline')));
    component.currentFileId = 7;
    component.selectedExecutionId = 'version-2';
    component.refreshHoldoutHistory();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alert"]').textContent).toContain(
      'An unused holdout cannot be assumed',
    );
    expect(component.historyLoading).toBeFalse();
  });

  it('loads the current model and discards assessment from an older execution', () => {
    const service = TestBed.inject(DataService);
    spyOn(service, 'getModelingStatus').and.returnValue(of({ execution_id: 'version-2' }));
    spyOn(service, 'getEvaluationStatus').and.returnValue(
      of({ evaluation: { execution_id: 'version-1' } }),
    );
    spyOn(service, 'getHoldoutHistory').and.returnValue(
      of({ records: [], same_final_rows_accesses: 1 }),
    );
    TestBed.inject(SharedService).setCurrentFileId(7);
    expect(component.result).toBeNull();
    expect(component.selectedExecutionId).toBe('version-2');
    expect(component.holdoutHistory.same_final_rows_accesses).toBe(1);
  });
});
