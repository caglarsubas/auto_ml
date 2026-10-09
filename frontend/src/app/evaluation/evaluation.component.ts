import { Component, OnDestroy, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { Subscription, forkJoin } from 'rxjs';
import { DataService } from '../services/data.service';
import { SharedService } from '../services/shared.service';

@Component({
  selector: 'app-evaluation',
  templateUrl: './evaluation.component.html',
  styleUrl: './evaluation.component.css',
  changeDetection: ChangeDetectionStrategy.Eager,
  standalone: false,
})
export class EvaluationComponent implements OnInit, OnDestroy {
  currentFileId: number | null = null;
  threshold = 0.5;
  isRunning = false;
  error: string | null = null;
  result: any = null;
  selectedExecutionId: string | null = null;
  holdoutHistory: any = null;
  historyLoading = false;
  historyError: string | null = null;
  governanceChecked: { [key: string]: boolean } = {};
  governanceSaving = false;

  private subs: Subscription[] = [];

  constructor(
    private dataService: DataService,
    private sharedService: SharedService,
  ) {}

  ngOnInit(): void {
    this.subs.push(
      this.sharedService.currentFileId$.subscribe((id) => {
        this.currentFileId = id;
        this.isRunning = false;
        this.error = null;
        this.result = null;
        this.selectedExecutionId = null;
        this.holdoutHistory = null;
        this.historyError = null;
        this.historyLoading = id != null;
        this.governanceChecked = {};
        this.sharedService.setEvaluationCompleted(false);
        if (id != null) {
          this.subs.push(
            forkJoin({
              model: this.dataService.getModelingStatus(id),
              assessment: this.dataService.getEvaluationStatus(id),
            }).subscribe({
              next: ({ model, assessment }) => {
                if (this.currentFileId !== id) return;
                this.selectedExecutionId = model?.execution_id || null;
                if (
                  assessment?.evaluation &&
                  assessment.evaluation.execution_id === this.selectedExecutionId
                ) {
                  this.result = assessment;
                  this.initGovernanceChecks();
                  this.sharedService.setEvaluationCompleted(true);
                }
                this.refreshHoldoutHistory();
              },
              error: () => {
                if (this.currentFileId !== id) return;
                this.historyLoading = false;
                this.historyError = 'Could not load the selected model and assessment history.';
              },
            }),
          );
        }
      }),
    );
  }

  ngOnDestroy(): void {
    this.subs.forEach((s) => s.unsubscribe());
  }

  runEvaluation(): void {
    if (this.currentFileId == null) {
      this.error = 'Select a declaration / processed file before evaluation.';
      return;
    }
    this.isRunning = true;
    this.error = null;
    const fileId = this.currentFileId;
    this.dataService
      .runEvaluation(fileId, this.threshold, undefined, this.selectedExecutionId || undefined)
      .subscribe({
        next: (resp) => {
          if (this.currentFileId !== fileId) return;
          this.result = resp;
          this.initGovernanceChecks();
          this.isRunning = false;
          this.refreshHoldoutHistory();
          this.sharedService.setEvaluationCompleted(true);
          try {
            this.sharedService.triggerCheckpoint('evaluation_completed');
          } catch {}
        },
        error: (err) => {
          if (this.currentFileId !== fileId) return;
          this.error = err?.message || 'Evaluation failed';
          this.isRunning = false;
          this.refreshHoldoutHistory();
        },
      });
  }

  refreshHoldoutHistory(offset = 0): void {
    const fileId = this.currentFileId;
    const executionId = this.selectedExecutionId;
    if (fileId == null || !executionId) {
      this.historyLoading = false;
      return;
    }
    this.historyLoading = true;
    this.subs.push(
      this.dataService.getHoldoutHistory(fileId, executionId, offset).subscribe({
        next: (history) => {
          if (this.currentFileId !== fileId || this.selectedExecutionId !== executionId) return;
          this.holdoutHistory =
            offset && this.holdoutHistory
              ? { ...history, records: [...this.holdoutHistory.records, ...history.records] }
              : history;
          this.historyLoading = false;
          this.historyError = null;
        },
        error: () => {
          if (this.currentFileId !== fileId || this.selectedExecutionId !== executionId) return;
          this.historyLoading = false;
          this.historyError = 'Access history is unavailable. An unused holdout cannot be assumed.';
        },
      }),
    );
  }

  downloadEvaluationPack(): void {
    if (this.currentFileId == null) return;
    const evaluation = this.result?.evaluation;
    this.dataService
      .downloadEvalPack(this.currentFileId, evaluation?.execution_id, evaluation?.holdout_access_id)
      .subscribe({
        next: (blob) => {
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `evaluation_pack_${this.currentFileId}.zip`;
          a.click();
          window.URL.revokeObjectURL(url);
        },
        error: (err) => console.error('Evaluation pack download failed:', err),
      });
  }

  initGovernanceChecks(): void {
    const remaining = this.modelCard?.human_checks_remaining || [];
    const saved = this.result?.governance_checks || this.modelCard?.governance_checks || {};
    const next: { [key: string]: boolean } = {};
    for (const item of remaining) {
      next[item] = !!saved[item];
    }
    this.governanceChecked = next;
  }

  toggleGovernanceCheck(item: string, checked: boolean): void {
    this.governanceChecked[item] = checked;
    if (this.currentFileId == null) return;
    this.governanceSaving = true;
    this.dataService.saveGovernanceChecks(this.currentFileId, this.governanceChecked).subscribe({
      next: () => {
        this.governanceSaving = false;
        try {
          this.sharedService.triggerCheckpoint('evaluation_governance_updated');
        } catch {}
      },
      error: () => {
        this.governanceSaving = false;
      },
    });
  }

  get metrics(): any {
    return this.result?.evaluation?.metrics || null;
  }

  get modelCard(): any {
    return this.result?.model_card || null;
  }

  get successCriteriaResult(): any {
    return (
      this.result?.success_criteria_result ??
      this.result?.evaluation?.success_criteria_result ??
      null
    );
  }

  get deployReadiness(): any {
    return this.modelCard?.sections?.deployment_readiness || null;
  }

  get isDeployReady(): boolean {
    if (this.modelCard?.deploy_ready != null) return !!this.modelCard.deploy_ready;
    return !!this.deployReadiness?.ready;
  }

  get thresholdRows(): any[] {
    return this.result?.evaluation?.threshold_table || [];
  }

  get hasExpectedCost(): boolean {
    return this.thresholdRows.some((r) => r.expected_cost != null);
  }

  get isRegression(): boolean {
    const task = this.result?.evaluation?.task || this.result?.model_card?.task;
    return task === 'regression';
  }

  get taskLabel(): string {
    if (!this.result?.evaluation) return '';
    return this.isRegression ? 'regression' : 'classification';
  }

  get metricKeys(): string[] {
    if (this.isRegression) {
      return ['r2', 'rmse', 'mae', 'mean_residual', 'residual_std', 'y_true_mean', 'y_pred_mean'];
    }
    return [
      'roc_auc',
      'pr_auc',
      'ks',
      'gini',
      'f1',
      'f2',
      'precision',
      'recall',
      'accuracy',
      'mcc',
      'brier',
      'log_loss',
    ];
  }

  get governanceItems(): string[] {
    return this.modelCard?.human_checks_remaining || [];
  }
}
