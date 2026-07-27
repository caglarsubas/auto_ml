import { Component, OnDestroy, OnInit } from '@angular/core';
import { Subscription } from 'rxjs';
import { DataService } from '../services/data.service';
import { SharedService } from '../services/shared.service';

@Component({
  selector: 'app-evaluation',
  templateUrl: './evaluation.component.html',
  styleUrl: './evaluation.component.css'
})
export class EvaluationComponent implements OnInit, OnDestroy {
  currentFileId: number | null = null;
  threshold = 0.5;
  isRunning = false;
  error: string | null = null;
  result: any = null;

  private subs: Subscription[] = [];

  constructor(
    private dataService: DataService,
    private sharedService: SharedService,
  ) {}

  ngOnInit(): void {
    this.subs.push(
      this.sharedService.currentFileId$.subscribe((id) => {
        this.currentFileId = id;
        if (id != null) {
          this.dataService.getEvaluationStatus(id).subscribe({
            next: (resp) => {
              if (resp?.status === 'ok' || resp?.evaluation) {
                this.result = resp;
                this.sharedService.setEvaluationCompleted(true);
              }
            },
            error: () => {},
          });
        } else {
          this.result = null;
          this.sharedService.setEvaluationCompleted(false);
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
    this.dataService.runEvaluation(this.currentFileId, this.threshold).subscribe({
      next: (resp) => {
        this.result = resp;
        this.isRunning = false;
        this.sharedService.setEvaluationCompleted(true);
        try { this.sharedService.triggerCheckpoint('evaluation_completed'); } catch {}
      },
      error: (err) => {
        this.error = err?.message || 'Evaluation failed';
        this.isRunning = false;
      },
    });
  }

  get metrics(): any {
    return this.result?.evaluation?.metrics || null;
  }

  get modelCard(): any {
    return this.result?.model_card || null;
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
      'roc_auc', 'pr_auc', 'ks', 'gini', 'f1', 'f2', 'precision', 'recall',
      'accuracy', 'mcc', 'brier', 'log_loss',
    ];
  }
}
