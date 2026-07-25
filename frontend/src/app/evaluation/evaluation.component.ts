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
              }
            },
            error: () => {},
          });
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

  get thresholdRows(): any[] {
    return this.result?.evaluation?.threshold_table || [];
  }
}
