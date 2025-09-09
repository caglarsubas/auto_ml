import { Component, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { SharedService } from '../services/shared.service';
import { DataService } from '../services/data.service';
import { finalize } from 'rxjs/operators';
import { Subscription, interval } from 'rxjs';

interface PurifierOption { id: number; name: string; }

@Component({
  selector: 'app-modeling',
  templateUrl: './modeling.component.html',
  styleUrls: ['./modeling.component.css']
})
export class ModelingComponent implements OnInit {
  selectedOptionIds: number[] = [];
  selectedOptionNames: string[] = [];
  runPreview: any | null = null;
  tableColumns: string[] = [];
  processedFilePath: string | null = null;
  currentFileId: number | null = null;
  isStarting: boolean = false;
  modelingStatus: any | null = null;
  private pollingSub: Subscription | null = null;

  // Pipeline and algorithm selection
  selectedPipeline: string = '';
  availableAlgorithms: string[] = [];
  selectedAlgorithm: string | null = null;

  // Mirror of options so we can map ids to labels for display
  private purifierOptions: PurifierOption[] = [
    { id: 1, name: 'Column-wise duplicate drop' },
    { id: 2, name: 'Row-wise duplicate drop' },
    { id: 3, name: 'Zero-variance drop' },
    { id: 4, name: 'Perfect-correlation drop' },
    { id: 5, name: 'Corr-drop threshold = 0.95' },
    { id: 6, name: 'Corr-drop threshold = 0.90' },
    { id: 7, name: 'Corr-drop threshold = 0.85' },
    { id: 8, name: 'Corr-drop threshold = 0.80' },
    { id: 9, name: 'Corr-drop threshold = 0.75' },
    { id: 10, name: 'Sparsity-drop threshold = 0.99' },
    { id: 11, name: 'Sparsity-drop threshold = 0.95' },
    { id: 12, name: 'Sparsity-drop threshold = 0.90' },
    { id: 13, name: 'Sparsity-drop threshold = 0.85' },
    { id: 14, name: 'Sparsity-drop threshold = 0.80' },
    { id: 15, name: 'Sparsity-drop threshold = 0.75' },
    { id: 16, name: 'Missing-drop threshold = 0.99' },
    { id: 17, name: 'Missing-drop threshold = 0.95' },
    { id: 18, name: 'Missing-drop threshold = 0.90' },
    { id: 19, name: 'Missing-drop threshold = 0.85' },
    { id: 20, name: 'Missing-drop threshold = 0.80' },
    { id: 21, name: 'Missing-drop threshold = 0.75' },
    { id: 22, name: '[Sparsity+Missing]-drop threshold = 0.99' },
    { id: 23, name: '[Sparsity+Missing]-drop threshold = 0.95' },
    { id: 24, name: '[Sparsity+Missing]-drop threshold = 0.90' },
    { id: 25, name: '[Sparsity+Missing]-drop threshold = 0.85' },
    { id: 26, name: '[Sparsity+Missing]-drop threshold = 0.80' },
    { id: 27, name: '[Sparsity+Missing]-drop threshold = 0.75' },
    { id: 28, name: 'Outlier-cleaning [lower-upper] quantiles = [0.01-0.99]' },
    { id: 29, name: 'Outlier-cleaning [lower-upper] quantiles = [0.05-0.95]' },
    { id: 30, name: 'Outlier-cleaning [lower-upper] quantiles = [0.10-0.90]' },
  ];

  constructor(private sharedService: SharedService, private dataService: DataService, private router: Router) {}

  ngOnInit(): void {
    this.sharedService.selectedPurifierOptions$.subscribe((ids) => {
      this.selectedOptionIds = ids;
      const nameMap = new Map(this.purifierOptions.map(o => [o.id, o.name] as [number, string]));
      this.selectedOptionNames = ids.map(id => nameMap.get(id) || `Option #${id}`);
    });

    this.sharedService.preprocessingRunResult$.subscribe((result) => {
      this.runPreview = result;
      const head = result?.head;
      if (Array.isArray(head) && head.length > 0 && head[0] && typeof head[0] === 'object') {
        this.tableColumns = Object.keys(head[0]);
      } else {
        this.tableColumns = [];
      }
    });

    this.sharedService.processedFilePath$.subscribe((path) => {
      this.processedFilePath = path;
    });

    this.sharedService.currentFileId$.subscribe((id) => {
      this.currentFileId = id;
    });

    this.sharedService.selectedPipeline$.subscribe((p) => {
      this.selectedPipeline = p;
      // Provide algorithm options based on pipeline
      if (p === 'boosting') {
        this.availableAlgorithms = ['xgboost', 'lightgbm', 'catboost'];
      } else if (p === 'logit') {
        this.availableAlgorithms = ['logistic_regression'];
      } else {
        this.availableAlgorithms = [];
      }
      // Reset previous selection if it is not valid anymore
      if (!this.availableAlgorithms.includes(this.selectedAlgorithm || '')) {
        this.selectedAlgorithm = null;
      }
    });
  }

  goBackToPreprocessing(): void {
    this.router.navigate(['/model-development/preprocessing']);
  }

  startModeling(): void {
    if (this.currentFileId == null || !this.processedFilePath) {
      console.error('Missing file ID or processed file path');
      return;
    }
    // If algorithms are available, require a selection
    if (this.availableAlgorithms.length > 0 && !this.selectedAlgorithm) {
      console.error('Please select an algorithm before starting modeling');
      return;
    }
    this.isStarting = true;
    this.dataService.startModeling(this.currentFileId, this.processedFilePath, this.selectedAlgorithm || undefined).pipe(
      finalize(() => this.isStarting = false)
    ).subscribe({
      next: (resp) => {
        console.log('Modeling started:', resp);
        this.modelingStatus = resp;
        // Begin polling status until completed or error
        this.startStatusPolling();
      },
      error: (err) => {
        console.error('Failed to start modeling:', err);
      }
    });
  }

  private startStatusPolling(): void {
    if (this.currentFileId == null) return;
    // Clear any existing subscription
    if (this.pollingSub) {
      this.pollingSub.unsubscribe();
    }
    this.pollingSub = interval(2000).subscribe(() => {
      if (this.currentFileId == null) return;
      this.dataService.getModelingStatus(this.currentFileId).subscribe({
        next: (status) => {
          this.modelingStatus = status;
          const s = status?.status || status?.job_status;
          if (s === 'completed' || s === 'error') {
            this.stopStatusPolling();
          }
        },
        error: (err) => {
          console.error('Polling error:', err);
          this.stopStatusPolling();
        }
      });
    });
  }

  private stopStatusPolling(): void {
    if (this.pollingSub) {
      this.pollingSub.unsubscribe();
      this.pollingSub = null;
    }
  }

  ngOnDestroy(): void {
    this.stopStatusPolling();
  }

  trackByKey(index: number, key: string): string {
    return key;
  }
}
