import { Component, OnInit, Inject, AfterViewInit, ChangeDetectorRef } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { PLATFORM_ID } from '@angular/core';
import { Router } from '@angular/router';
import { SharedService } from '../services/shared.service';
import { DataService } from '../services/data.service';
import { finalize } from 'rxjs/operators';
import { Subscription, interval } from 'rxjs';
import { MatDialog } from '@angular/material/dialog';
import { FeatureCardComponent } from '../feature-card/feature-card.component';

interface PurifierOption { id: number; name: string; }

@Component({
  selector: 'app-modeling',
  templateUrl: './modeling.component.html',
  styleUrls: ['./modeling.component.css']
})
export class ModelingComponent implements OnInit, AfterViewInit {
  selectedOptionIds: number[] = [];
  selectedOptionNames: string[] = [];
  runPreview: any | null = null;
  tableColumns: string[] = [];
  processedFilePath: string | null = null;
  currentFileId: number | null = null;
  isStarting: boolean = false;
  modelingStatus: any | null = null;
  private pollingSub: Subscription | null = null;
  isBrowser: boolean = false;
  showNulls: boolean = false;
  private plotlyReady: Promise<void> | null = null;
  private chartsDrawn: boolean = false;

  // SFS (Sequential Feature Selection) configuration and results
  sfsReady: boolean = false;  // Training data saved, ready to run SFS
  sfsRunning: boolean = false;
  sfsProgress: number = 0;
  sfsMessage: string = '';
  sfsCurrentMetrics: { [key: string]: number } = {};
  sfsCompletedSteps: any[] = [];  // Real-time completed steps during SFS
  showSfsProgressModal: boolean = false;  // Modal for viewing details during SFS
  private sfsPolling: Subscription | null = null;
  
  // SFS method selection
  sfsMethodForward: boolean = true;
  sfsMethodBackward: boolean = false;
  
  // SFS stopping criteria - multiple metrics
  sfsMetrics: Array<{ metric: string, pct_change: number }> = [
    { metric: 'roc_auc', pct_change: 1.0 }
  ];
  sfsMinFeatures: number = 3;
  sfsMaxFeatures: number = 10;
  
  // SFS results
  sfsResults: any | null = null;
  sfsForwardResults: any[] = [];
  sfsBackwardResults: any[] = [];
  sfsBackwardRemainingFeatures: string[] = [];  // Features remaining after backward elimination
  sfsBackwardCutStep: number | null = null;  // User-selected cutting point step in backward results
  sfsBackwardCutFeatures: string[] = [];  // Features remaining at the selected cut step
  sfsForwardFromBackwardResults: any[] = [];  // Forward selection results starting from backward cut features
  selectedSfsStep: any | null = null;  // For modal display
  previousSfsStep: any | null = null;  // Previous step for comparison
  showSfsModal: boolean = false;
  sfsModalExpanded: boolean = false;

  // Utility for template
  Object = Object;

  // Pipeline and algorithm selection
  selectedPipeline: string = '';
  availableAlgorithms: string[] = [];
  selectedAlgorithm: string | null = null;

  // Data quality summary and date columns for feature-card
  datqSummary: any[] | null = null;
  dateColumns: string[] = [];
  splitDateColumn: string | null = null;

  // Model_Usage settings (variables to exclude from modeling)
  variableModelUsage: { [variable: string]: string } = {};

  // Encoding plan state (shown after algorithm selection, before Start Modeling)
  encodingPlan: any[] = [];
  encodingAnalyzing: boolean = false;
  encodingError: string | null = null;
  dataDictionaryCache: any[] = [];

  // Encoding report with category mappings (for SHAP beeswarm labels)
  encodingReport: any[] = [];
  // Quick lookup: featureName -> { encoded_value -> original_label }
  catLabelLookup: { [feature: string]: { [encoded: string]: string } } = {};

  // Feature usage tracking for Selected Features table
  featureUsage: { [feature: string]: string } = {};
  featureDropReason: { [feature: string]: string } = {};

  // Sort state for Selected Features table
  sfSortColumn: string = 'combined_score';
  sfSortDirection: 'asc' | 'desc' = 'desc';
  sortedSelectedFeatures: any[] = [];

  // VIF detail modal state
  showVifDetailModal: boolean = false;
  vifDetailFeature: string = '';
  vifDetailVif: number | null = null;
  vifDetailContributions: any[] = [];
  vifDetailLoading: boolean = false;
  vifDetailError: string | null = null;
  vifDetailSortColumn: string = 'correlation';
  vifDetailSortDirection: 'asc' | 'desc' = 'desc';

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

  constructor(private sharedService: SharedService, private dataService: DataService, private router: Router, @Inject(PLATFORM_ID) platformId: Object, private cdr: ChangeDetectorRef, private dialog: MatDialog) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  ngOnInit(): void {
    if (this.isBrowser) {
      this.plotlyReady = this.loadPlotly();
    } else {
      this.plotlyReady = Promise.resolve();
    }
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
      // Extract data quality summary
      if (result && Array.isArray(result.datq_summary)) {
        this.datqSummary = result.datq_summary;
      } else {
        this.datqSummary = null;
      }
      // Detect date columns from table columns (common date/datetime patterns)
      if (this.tableColumns.length > 0) {
        this.dateColumns = this.tableColumns.filter(col => {
          const lower = col.toLowerCase();
          return lower.includes('date') || lower.includes('time') || lower.includes('dt_') || 
                 lower.includes('timestamp') || lower === 'month' || lower === 'year';
        });
        // Set first date column as default split date column
        this.splitDateColumn = this.dateColumns.length > 0 ? this.dateColumns[0] : null;
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

    // Subscribe to Model_Usage settings from Data Quality
    this.sharedService.modelUsageSettings$.subscribe((settings) => {
      if (settings) {
        this.variableModelUsage = settings;
        console.log('[Modeling] Received Model_Usage settings:', settings);
      }
    });

    // Subscribe to data dictionary cache for encoding analysis
    this.sharedService.dataDictionaryCache$.subscribe((cache) => {
      this.dataDictionaryCache = cache || [];
    });

  }

  ngAfterViewInit(): void {
    if (!this.isBrowser) return;
    // Defer to ensure *ngIf DOM nodes are present
    setTimeout(() => this.tryDrawChartsIfReady(), 0);
  }

  private tryDrawChartsIfReady(attempt: number = 0): void {
    try {
      if (!this.isBrowser) return;
      if (!this.modelingStatus?.model?.cv) return;
      if (this.chartsDrawn) return;
      const ready = this.plotlyReady || Promise.resolve();
      ready.then(() => {
        try { this.cdr.detectChanges(); } catch {}
        this.drawCvCharts()
          .then(() => { this.chartsDrawn = true; })
          .catch(() => {
            if (attempt < 10) setTimeout(() => this.tryDrawChartsIfReady(attempt + 1), 250);
          });
      });
    } catch {}
  }

  goBackToPreprocessing(): void {
    this.router.navigate(['/model-development/preprocessing']);
  }

  // ===== Encoding Plan Methods =====

  onAlgorithmChange(algo: string): void {
    this.selectedAlgorithm = algo;
    // Auto-trigger encoding analysis when algorithm is selected
    if (algo && this.currentFileId != null && this.processedFilePath) {
      this.ensureDictionaryThenAnalyze();
    }
  }

  private ensureDictionaryThenAnalyze(): void {
    if (this.dataDictionaryCache && this.dataDictionaryCache.length > 0) {
      this.analyzeEncoding();
      return;
    }
    // Dictionary cache is empty — fetch it before analyzing
    if (this.currentFileId != null) {
      this.dataService.getDataDictionary(String(this.currentFileId)).subscribe({
        next: (list: any[]) => {
          this.dataDictionaryCache = Array.isArray(list) ? list : [];
          this.analyzeEncoding();
        },
        error: () => {
          // Proceed without descriptions
          this.analyzeEncoding();
        }
      });
    } else {
      this.analyzeEncoding();
    }
  }

  analyzeEncoding(): void {
    if (!this.currentFileId || !this.processedFilePath) return;
    this.encodingAnalyzing = true;
    this.encodingError = null;
    const excluded = Object.keys(this.variableModelUsage).filter(v => this.variableModelUsage[v] === 'No');
    this.dataService.analyzeEncoding(
      this.currentFileId, this.processedFilePath, this.dataDictionaryCache, excluded
    ).subscribe({
      next: (resp: any) => {
        this.encodingPlan = Array.isArray(resp.plan) ? resp.plan : [];
        this.encodingAnalyzing = false;
      },
      error: (err: any) => {
        this.encodingError = 'Failed to analyze encoding: ' + (err?.message || err);
        this.encodingAnalyzing = false;
      }
    });
  }

  updateEncodingLom(entry: any, newLom: string): void {
    entry.user_lom = newLom;
    const nunique = entry.nunique || 0;
    if (newLom === 'ordinal') {
      if (nunique < 5) {
        entry.fallback_strategy = 'one_hot_encoding';
        entry.fallback_reason = `Ordinal with ${nunique} unique (<5) → One-Hot Encoding`;
        entry.needs_ranking = false;
      } else if (nunique <= 10) {
        entry.fallback_strategy = 'ordinal_encoding';
        entry.fallback_reason = `Ordinal with ${nunique} unique (5–10) → Ordinal Encoding (user ranking)`;
        entry.needs_ranking = true;
      } else {
        entry.fallback_strategy = 'target_encoding';
        entry.fallback_reason = `Ordinal with ${nunique} unique (>10) → Target Encoding`;
        entry.needs_ranking = false;
      }
    } else {
      entry.fallback_strategy = 'label_encoding';
      entry.fallback_reason = 'Nominal feature → Label Encoding';
      entry.needs_ranking = false;
      entry.ranking = null;
    }
  }

  moveRankingUp(entry: any, idx: number): void {
    if (!entry.ranking || idx <= 0) return;
    const tmp = entry.ranking[idx - 1];
    entry.ranking[idx - 1] = entry.ranking[idx];
    entry.ranking[idx] = tmp;
  }

  moveRankingDown(entry: any, idx: number): void {
    if (!entry.ranking || idx >= entry.ranking.length - 1) return;
    const tmp = entry.ranking[idx + 1];
    entry.ranking[idx + 1] = entry.ranking[idx];
    entry.ranking[idx] = tmp;
  }

  initRanking(entry: any): void {
    if (!entry.ranking || !entry.ranking.length) {
      entry.ranking = [...(entry.unique_values || [])];
    }
  }

  getStrategyLabel(strategy: string): string {
    const labels: { [k: string]: string } = {
      'native_categorical': 'Native Categorical',
      'label_encoding': 'Label Encoding',
      'one_hot_encoding': 'One-Hot Encoding',
      'ordinal_encoding': 'Ordinal Encoding',
      'target_encoding': 'Target Encoding',
    };
    return labels[strategy] || strategy;
  }

  getStrategyColor(strategy: string): string {
    const colors: { [k: string]: string } = {
      'native_categorical': '#1976d2',
      'label_encoding': '#7b1fa2',
      'one_hot_encoding': '#00796b',
      'ordinal_encoding': '#e65100',
      'target_encoding': '#c62828',
    };
    return colors[strategy] || '#616161';
  }

  getFeatureDescription(featureName: string): string {
    if (!this.dataDictionaryCache || !this.dataDictionaryCache.length) return '';
    const entry = this.dataDictionaryCache.find((d: any) => d?.Feature_Name === featureName);
    return entry?.Feature_Description || '';
  }

  getAlgorithmLabel(algo: string | null): string {
    const labels: { [k: string]: string } = {
      'xgboost': 'XGBoost',
      'lightgbm': 'LightGBM',
      'catboost': 'CatBoost',
    };
    return labels[algo || ''] || algo || 'Boosting';
  }

  // ===== Selected Features Table Sorting =====

  sortSelectedFeatures(column: string): void {
    if (this.sfSortColumn === column) {
      this.sfSortDirection = this.sfSortDirection === 'asc' ? 'desc' : 'asc';
    } else {
      this.sfSortColumn = column;
      // Default to descending for numeric columns, ascending for text
      this.sfSortDirection = (column === 'feature' || column === 'description') ? 'asc' : 'desc';
    }
    this.applySfSort();
  }

  applySfSort(): void {
    const features = this.modelingStatus?.model?.selected_features;
    if (!features || !features.length) {
      this.sortedSelectedFeatures = [];
      return;
    }
    const col = this.sfSortColumn;
    const dir = this.sfSortDirection === 'asc' ? 1 : -1;
    this.sortedSelectedFeatures = [...features].sort((a: any, b: any) => {
      let va = a[col];
      let vb = b[col];
      // Handle nulls — push them to the end
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      // String comparison for text columns
      if (typeof va === 'string' && typeof vb === 'string') {
        return dir * va.localeCompare(vb);
      }
      // Numeric comparison
      return dir * ((va > vb ? 1 : va < vb ? -1 : 0));
    });
  }

  getSfSortIcon(column: string): string {
    if (this.sfSortColumn !== column) return '⇅';
    return this.sfSortDirection === 'asc' ? '↑' : '↓';
  }

  // ===== VIF Detail Modal =====

  openVifDetail(featureName: string, event: Event): void {
    event.stopPropagation();
    if (this.currentFileId == null) return;
    this.vifDetailFeature = featureName;
    this.vifDetailLoading = true;
    this.vifDetailError = null;
    this.vifDetailContributions = [];
    this.vifDetailVif = null;
    this.vifDetailSortColumn = 'correlation';
    this.vifDetailSortDirection = 'desc';
    this.showVifDetailModal = true;

    this.dataService.getVifDetail(this.currentFileId, featureName).subscribe({
      next: (resp: any) => {
        this.vifDetailVif = resp.vif;
        this.vifDetailContributions = resp.contributions || [];
        this.vifDetailLoading = false;
      },
      error: (err: any) => {
        this.vifDetailError = err?.error?.error || 'Failed to load VIF detail';
        this.vifDetailLoading = false;
      }
    });
  }

  closeVifDetail(): void {
    this.showVifDetailModal = false;
    this.vifDetailFeature = '';
    this.vifDetailContributions = [];
    this.vifDetailError = null;
  }

  sortVifDetail(column: string): void {
    if (this.vifDetailSortColumn === column) {
      this.vifDetailSortDirection = this.vifDetailSortDirection === 'asc' ? 'desc' : 'asc';
    } else {
      this.vifDetailSortColumn = column;
      this.vifDetailSortDirection = column === 'feature' ? 'asc' : 'desc';
    }
    this.applyVifDetailSort();
  }

  applyVifDetailSort(): void {
    const col = this.vifDetailSortColumn;
    const dir = this.vifDetailSortDirection === 'asc' ? 1 : -1;
    this.vifDetailContributions = [...this.vifDetailContributions].sort((a: any, b: any) => {
      let va = a[col];
      let vb = b[col];
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      if (typeof va === 'string' && typeof vb === 'string') return dir * va.localeCompare(vb);
      return dir * (va > vb ? 1 : va < vb ? -1 : 0);
    });
  }

  getVifDetailSortIcon(column: string): string {
    if (this.vifDetailSortColumn !== column) return '⇅';
    return this.vifDetailSortDirection === 'asc' ? '↑' : '↓';
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
    // Get list of variables to exclude (Model_Usage='No')
    const excludedVariables = Object.keys(this.variableModelUsage).filter(v => this.variableModelUsage[v] === 'No');
    if (excludedVariables.length > 0) {
      console.log(`[Modeling] Excluding ${excludedVariables.length} variables with Model_Usage='No':`, excludedVariables);
    }

    this.isStarting = true;
    this.chartsDrawn = false;
    this.dataService.startModeling(this.currentFileId, this.processedFilePath!, this.selectedAlgorithm || undefined, excludedVariables).pipe(
      finalize(() => this.isStarting = false)
    ).subscribe({
      next: (resp) => {
        console.log('Modeling started:', resp);
        this.modelingStatus = resp;
        // Debug: Check SHAP data
        console.log('SHAP beeswarm present?', !!resp?.model?.shap_beeswarm);
        console.log('Selected features count:', resp?.model?.selected_features?.length || 0);
        this.applySfSort();
        // Check if SFS is ready (training data saved)
        this.sfsReady = resp?.model?.sfs_ready || false;
        console.log('SFS ready?', this.sfsReady);
        // Build catLabelLookup from the encoding report returned by the modeling backend
        this.buildCatLabelLookup(resp?.model?.encoding_report);
        // If the response already indicates completion, draw charts immediately
        const js = (resp as any)?.job_status || (resp as any)?.status;
        if (js === 'completed') { 
          setTimeout(() => this.tryDrawChartsIfReady(), 0); 
        }
        else { this.startStatusPolling(); }
      },
      error: (err) => {
        console.error('Failed to start modeling:', err);
      }
    });
  }

  private buildCatLabelLookup(encodingReport: any[] | null | undefined): void {
    this.catLabelLookup = {};
    if (!encodingReport || !Array.isArray(encodingReport)) return;
    this.encodingReport = encodingReport;
    for (const r of encodingReport) {
      const feat = r.feature;
      const cats: string[] = r.categories || [];
      if (!feat || cats.length === 0) continue;
      const lookup: { [encoded: string]: string } = {};
      cats.forEach((c: string, i: number) => { lookup[String(i)] = c; });
      if (Object.keys(lookup).length > 0) {
        this.catLabelLookup[feat] = lookup;
      }
    }
    console.log('[Modeling] Built catLabelLookup from model response:', Object.keys(this.catLabelLookup));
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
          this.applySfSort();
          // Check if SFS is ready
          this.sfsReady = status?.model?.sfs_ready || false;
          const s = status?.job_status || status?.status;
          if (s === 'completed' || s === 'error') {
            this.stopStatusPolling();
            // Build catLabelLookup from encoding report in completed response
            if (status?.model?.encoding_report) {
              this.buildCatLabelLookup(status.model.encoding_report);
            }
            // draw CV charts when available
            this.chartsDrawn = false;
            setTimeout(() => this.tryDrawChartsIfReady(), 0);
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

  // ===== Plotly helpers for CV charts =====
  private async loadPlotly(): Promise<void> {
    try {
      if (!(window as any).Plotly) {
        const mod: any = await import('plotly.js-dist-min');
        const PlotlyObj: any = (mod && (mod.default || mod)) || null;
        if (!PlotlyObj || typeof PlotlyObj.newPlot !== 'function') {
          console.warn('[Plotly] Failed to resolve newPlot from module, module keys:', Object.keys(mod || {}));
        }
        (window as any).Plotly = PlotlyObj;
      }
      if (!(window as any).Plotly || typeof (window as any).Plotly.newPlot !== 'function') {
        console.error('[Plotly] newPlot not available after load');
      }
    } catch (e) {
      console.warn('Failed to load Plotly for CV charts:', e);
    }
  }

  private async drawCvCharts(): Promise<void> {
    try {
      if (!this.isBrowser) return;
      if (this.plotlyReady) { await this.plotlyReady; }
      const Plotly = (window as any).Plotly; if (!Plotly) return;
      const cv = this.modelingStatus?.model?.cv; if (!cv) return;
      // Try drawing regardless of partial availability; functions will fallback gracefully
      this.drawRocCurvePlot(cv);
      this.drawPrCurvePlot(cv);
      // SHAP beeswarm
      this.drawShapBeeswarm();
    } catch (e) {
      console.warn('drawCvCharts failed:', e);
    }
  }

  private drawRocCurvePlot(cv: any, attempt: number = 0): void {
    const Plotly = (window as any).Plotly; if (!Plotly) return;
    const roc = cv.roc_curve || {};
    const el = document.getElementById('cv-roc-plot');
    if (!el) {
      if (attempt < 10) setTimeout(() => this.drawRocCurvePlot(cv, attempt + 1), 250);
      return;
    }
    const fpr: number[] = Array.isArray(roc.fpr) ? roc.fpr : [0, 1];
    const meanTpr: number[] | null = Array.isArray(roc.mean_tpr) ? roc.mean_tpr : null;
    const stdTpr: number[] | null = Array.isArray(roc.std_tpr) ? roc.std_tpr : null;
    const foldTpr: number[][] = Array.isArray(roc.fold_tpr) ? roc.fold_tpr : [];
    const traces: any[] = [];

    // Fold curves (light)
    const foldColor = 'rgba(120,120,120,0.35)';
    foldTpr.forEach((tpr, i) => {
      traces.push({
        x: fpr,
        y: tpr,
        type: 'scatter',
        mode: 'lines',
        line: { color: foldColor, width: 1 },
        name: `ROC fold ${i}${cv?.folds?.[i]?.roc_auc != null ? ` (AUC = ${Number(cv.folds[i].roc_auc).toFixed(2)})` : ''}`,
        hovertemplate: 'FPR=%{x:.3f}<br>TPR=%{y:.3f}<extra></extra>',
        showlegend: i === 0
      } as any);
    });

    // Std shading
    if (meanTpr && stdTpr) {
      const lower = meanTpr.map((v, i) => Math.max(0, Math.min(1, v - stdTpr[i])));
      const upper = meanTpr.map((v, i) => Math.max(0, Math.min(1, v + stdTpr[i])));
      traces.push({ x: fpr, y: lower, type: 'scatter', mode: 'lines', line: {color: 'rgba(0,0,0,0)'}, hoverinfo: 'skip', showlegend: false } as any);
      traces.push({ x: fpr, y: upper, type: 'scatter', mode: 'lines', line: {color: 'rgba(0,0,0,0)'}, fill: 'tonexty', fillcolor: 'rgba(100,100,100,0.18)', name: '± 1 std. dev.', hoverinfo: 'skip' } as any);
    }

    // Mean ROC
    if (meanTpr) {
      traces.push({
        x: fpr, y: meanTpr, type: 'scatter', mode: 'lines', line: { color: '#1f77b4', width: 3 }, name: `Mean ROC (AUC = ${(cv.roc_auc_mean ?? 0).toFixed(3)})`, hovertemplate: 'FPR=%{x:.3f}<br>TPR=%{y:.3f}<extra></extra>'
      } as any);
    }

    // Chance diagonal
    traces.push({ x: [0,1], y: [0,1], type: 'scatter', mode: 'lines', line: { color: '#d32f2f', width: 2, dash: 'dash' }, name: 'Chance', hoverinfo: 'skip' } as any);

    const layout = {
      title: { text: '' },
      margin: { l: 64, r: 24, t: 12, b: 140 },
      xaxis: { title: { text: 'False Positive Rate', font: { size: 13 } }, range: [0, 1] },
      yaxis: { title: { text: 'True Positive Rate', font: { size: 13 } }, range: [0, 1] },
      hovermode: 'closest',
      legend: { orientation: 'h', x: 0, y: -0.35, xanchor: 'left', yanchor: 'top', font: { size: 11 }, bgcolor: 'rgba(255,255,255,0.95)', bordercolor: '#ddd', borderwidth: 1 }
    } as any;
    const config = { responsive: true, displayModeBar: true } as any;
    try { Plotly.react(el, traces, layout, config); } catch { Plotly.newPlot(el, traces, layout, config); }
  }

  // ===== SHAP Beeswarm (interactive) =====
  public drawShapBeeswarm(attempt: number = 0): void {
    try {
      if (!this.isBrowser) return;
      const Plotly = (window as any).Plotly; if (!Plotly) { if (attempt < 10) setTimeout(() => this.drawShapBeeswarm(attempt + 1), 250); return; }
      const payload = this.modelingStatus?.model?.shap_beeswarm; if (!payload) return;
      const el = document.getElementById('shap-beeswarm'); if (!el) { if (attempt < 10) setTimeout(() => this.drawShapBeeswarm(attempt + 1), 250); return; }

      const features: string[] = payload.features || [];
      const shapValues: number[][] = payload.shap_values || [];
      const featureValues: number[][] = payload.feature_values || [];
      const metadata: any[] = payload.metadata || [];
      const nFeat = features.length;
      if (!nFeat) return;
      // Dynamic height based on feature count (35px per feature for better spacing)
      try { (el as HTMLElement).style.height = `${Math.max(480, 35 * nFeat)}px`; } catch {}

      const traces: any[] = [];
      const jitter = 0.35;
      const colorscale: any = [
        [0.0, '#2166ac'],  // blue (low)
        [0.5, '#f7f7f7'],  // white (mid)
        [1.0, '#b2182b']   // red (high)
      ];

      const q = (arr: number[], p: number): number => {
        if (!arr || arr.length === 0) return 0;
        const a = arr.filter(v => Number.isFinite(v)).sort((a, b) => a - b);
        if (a.length === 0) return 0;
        const pos = (a.length - 1) * p;
        const base = Math.floor(pos);
        const rest = pos - base;
        return a[base] + (a[base + 1] !== undefined ? rest * (a[base + 1] - a[base]) : 0);
      };

      let colorbarPlaced = false;
      for (let i = 0; i < nFeat; i++) {
        const xs = (shapValues[i] || []).map(v => Number(v));
        const rawArr: any[] = featureValues[i] || [];
        const isNull = rawArr.map(v => v == null || (typeof v === 'number' && !Number.isFinite(v)));
        const vs = rawArr.map(v => (v == null ? NaN : Number(v)));
        const base = nFeat - 1 - i; // top feature at top
        const N = xs.length;
        // Beeswarm: KDE-based amplitude and uniform placement within the envelope
        const yvals = new Array<number>(N).fill(base);
        if (N > 0) {
          // envelope x-range
          const q05x = q(xs, 0.05);
          const q95x = q(xs, 0.95);
          let xmin = Math.min(q05x, Math.min(...xs));
          let xmax = Math.max(q95x, Math.max(...xs));
          if (xmin === xmax) { xmin -= 1e-6; xmax += 1e-6; }
          const Benv = 200; // grid for KDE/envelope
          const dxenv = (xmax - xmin) / Benv;
          const xgrid: number[] = Array.from({ length: Benv }, (_, b) => xmin + (b + 0.5) * dxenv);
          // Gaussian KDE with Silverman's rule of thumb
          const mean = xs.reduce((a, b) => a + b, 0) / Math.max(1, xs.length);
          const varsum = xs.reduce((a, b) => a + (b - mean) * (b - mean), 0);
          const stdev = Math.sqrt(varsum / Math.max(1, xs.length - 1)) || (xmax - xmin) * 0.1 || 1e-6;
          const bw = 1.06 * stdev * Math.pow(Math.max(1, xs.length), -1/5);
          const sigma = Math.max(1e-6, bw);
          const inv2s2 = 1 / (2 * sigma * sigma);
          const norm = 1 / (Math.sqrt(2 * Math.PI) * sigma * Math.max(1, xs.length));
          const dens: number[] = xgrid.map(xc => xs.reduce((acc, v) => acc + Math.exp(-(v - xc) * (v - xc) * inv2s2), 0) * norm);
          const dmax = Math.max(1e-9, ...dens);
          const maxRadius = 0.48;
          const ampGrid = dens.map(d => maxRadius * Math.pow(d / dmax, 0.85));
          // helper to interpolate amp at any x
          const ampAt = (x: number): number => {
            let u = (x - xmin) / (xmax - xmin);
            if (!Number.isFinite(u)) u = 0.5;
            u = Math.min(0.999, Math.max(0, u));
            const idx = Math.floor(u * (Benv - 1));
            const frac = u * (Benv - 1) - idx;
            const a0 = ampGrid[idx];
            const a1 = ampGrid[Math.min(Benv - 1, idx + 1)];
            return (a0 * (1 - frac) + a1 * frac) || 0;
          };
          // place each point uniformly within [-amp(x), +amp(x)] with tiny noise to avoid banding
          for (let j = 0; j < N; j++) {
            const a = ampAt(xs[j]);
            const noise = (Math.random() - 0.5) * 0.02; // small noise
            const oy = (Math.random() * 2 - 1) * Math.max(0.04, a) + noise;
            yvals[j] = base + oy;
          }
        }
        // Add a custom density envelope behind points for rounded bulges
        // Build histogram and smooth it with a Gaussian kernel to approximate KDE
        const q1 = q(xs, 0.01);
        const q99 = q(xs, 0.99);
        let exmin = Math.min(q1, Math.min(...xs));
        let exmax = Math.max(q99, Math.max(...xs));
        if (exmin === exmax) { exmin -= 1e-6; exmax += 1e-6; }
        const B = 60; // bins for envelope
        const dx = (exmax - exmin) / B;
        const centers: number[] = Array.from({ length: B }, (_, b) => exmin + (b + 0.5) * dx);
        const hist: number[] = Array(B).fill(0);
        for (let t = 0; t < xs.length; t++) {
          let b = Math.floor((xs[t] - exmin) / dx);
          if (b < 0) b = 0; if (b >= B) b = B - 1;
          hist[b]++;
        }
        // Gaussian smoothing kernel in bin units
        const sigma = 1.5; // in bins
        const rad = Math.max(1, Math.ceil(3 * sigma));
        const ker: number[] = [];
        for (let k = -rad; k <= rad; k++) ker.push(Math.exp(-0.5 * (k / sigma) ** 2));
        const ksum = ker.reduce((a, b) => a + b, 0) || 1;
        for (let k = 0; k < ker.length; k++) ker[k] /= ksum;
        const smooth: number[] = new Array(B).fill(0);
        for (let b = 0; b < B; b++) {
          let acc = 0;
          for (let k = -rad; k <= rad; k++) {
            const j = b + k;
            if (j >= 0 && j < B) acc += hist[j] * ker[k + rad];
          }
          smooth[b] = acc;
        }
        const smax = Math.max(1e-6, ...smooth);
        const maxRadius = 0.48; // half-height at densest x region
        const pow = 0.85; // soften the edges
        const amp: number[] = smooth.map(s => maxRadius * Math.pow(s / smax, pow));
        const upperY = amp.map(a => base + a);
        const lowerY = amp.map(a => base - a);
        // Draw envelope as filled area between upper and lower
        traces.push({ x: centers, y: upperY, type: 'scatter', mode: 'lines', line: { width: 0 }, hoverinfo: 'skip', showlegend: false } as any);
        traces.push({ x: centers, y: lowerY, type: 'scatter', mode: 'lines', fill: 'tonexty', fillcolor: 'rgba(120,120,120,0.20)', line: { width: 0 }, hoverinfo: 'skip', showlegend: false } as any);
        // Split indices by null/non-null for coloring
        const idxNonNull: number[] = [];
        const idxNull: number[] = [];
        for (let j = 0; j < N; j++) (isNull[j] ? idxNull : idxNonNull).push(j);

        // Non-null coloring with per-feature normalization
        if (idxNonNull.length > 0) {
          const vsNN = idxNonNull.map(j => vs[j]);
          let vmin = q(vsNN as number[], 0.05);
          let vmax = q(vsNN as number[], 0.95);
          if (!isFinite(vmin) || !isFinite(vmax) || vmin === vmax) {
            vmin = Math.min(...(vsNN as number[]));
            vmax = Math.max(...(vsNN as number[]));
            if (vmin === vmax) { vmin = vmax - 1; }
          }
          const denom = (vmax - vmin) !== 0 ? (vmax - vmin) : 1e-12;
          const cnorm = vsNN.map(v => (Number(v) - vmin) / denom).map(u => u < 0 ? 0 : (u > 1 ? 1 : u));

          // Check if this feature has a categorical encoding mapping
          const catLookup = this.catLabelLookup[features[i]];
          let customdata: any[];
          let hovertemplate: string;
          if (catLookup) {
            // Categorical: show both encoded value and original label
            customdata = idxNonNull.map(j => {
              const enc = String(Math.round(Number(rawArr[j])));
              const label = catLookup[enc] || rawArr[j];
              return [rawArr[j], label];
            });
            hovertemplate = `Feature=${features[i]}<br>SHAP=%{x:.4f}<br>Encoded=%{customdata[0]}<br>Original=%{customdata[1]}<extra></extra>`;
          } else {
            customdata = idxNonNull.map(j => rawArr[j]);
            hovertemplate = `Feature=${features[i]}<br>SHAP=%{x:.4f}<br>Value=%{customdata:.4f}<extra></extra>`;
          }

          traces.push({
            type: 'scatter',
            mode: 'markers',
            name: features[i],
            x: idxNonNull.map(j => xs[j]),
            y: idxNonNull.map(j => yvals[j]),
            customdata,
            marker: {
              color: cnorm,
              colorscale,
              cmin: 0,
              cmax: 1,
              showscale: !colorbarPlaced,
              colorbar: !colorbarPlaced ? { title: { text: 'Feature value' }, thickness: 14, tickmode: 'array', tickvals: [0, 1], ticktext: ['Low', 'High'] } : undefined,
              size: 6,
              opacity: 0.85
            },
            hovertemplate,
            showlegend: false
          } as any);
          if (!colorbarPlaced) colorbarPlaced = true;
        }

        // Null overlay as grey markers, optionally shown
        if (this.showNulls && idxNull.length > 0) {
          traces.push({
            type: 'scatter',
            mode: 'markers',
            x: idxNull.map(j => xs[j]),
            y: idxNull.map(j => yvals[j]),
            marker: { color: 'rgba(130,130,130,0.9)', size: 6, symbol: 'x', line: { width: 0.5, color: 'rgba(80,80,80,0.9)' } },
            hovertemplate: `Feature=${features[i]}<br>SHAP=%{x:.4f}<br>Value=null<extra></extra>`,
            showlegend: false
          } as any);
        }
      }

      const tickvals = Array.from({ length: nFeat }, (_, idx) => idx);
      const ticktext = Array.from({ length: nFeat }, (_, idx) => features[nFeat - 1 - idx]);
      // Build annotations for y-axis labels with hover metadata
      const yAxisAnnotations = Array.from({ length: nFeat }, (_, idx) => {
        const origIdx = nFeat - 1 - idx;
        const fname = features[origIdx];
        const meta = metadata[origIdx] || {};
        const desc = meta.description || '';
        const psi = meta.psi;
        const csi = meta.csi;
        const impact = meta.impact;
        // Build hover text: show description if available, otherwise feature name
        let hoverParts = [];
        if (desc) {
          hoverParts.push(`<b>${desc}</b>`);
        } else {
          hoverParts.push(`<b>${fname}</b>`);
        }
        if (impact != null && Number.isFinite(impact)) hoverParts.push(`Impact: ${Number(impact).toFixed(6)}`);
        if (psi != null && Number.isFinite(psi)) hoverParts.push(`PSI: ${Number(psi).toFixed(4)}`);
        if (csi != null && Number.isFinite(csi)) hoverParts.push(`CSI: ${Number(csi).toFixed(4)}`);
        return {
          x: -0.01,
          y: idx,
          xref: 'paper',
          yref: 'y',
          text: fname,
          showarrow: false,
          xanchor: 'right',
          yanchor: 'middle',
          font: { size: 9, color: '#333' },
          hovertext: hoverParts.join('<br>'),
          hoverlabel: { bgcolor: 'rgba(255,255,255,0.95)', bordercolor: '#999', font: { size: 11 } }
        };
      });
      const layout = {
        title: { text: '' },
        margin: { l: 220, r: 48, t: 12, b: 40 },
        xaxis: { title: { text: 'SHAP value (impact on model output)' }, zeroline: true, zerolinecolor: '#888', zerolinewidth: 1 },
        yaxis: { tickmode: 'array', tickvals, ticktext: [], showticklabels: false, range: [-0.6, nFeat - 0.4] },
        showlegend: false,
        hovermode: 'closest',
        shapes: [{ type: 'line', x0: 0, x1: 0, y0: -0.5, y1: nFeat - 0.5, line: { color: '#888', width: 1 } }],
        annotations: yAxisAnnotations
      } as any;
      const config = { responsive: true, displayModeBar: true } as any;
      try { Plotly.react(el, traces, layout, config); } catch { Plotly.newPlot(el, traces, layout, config); }
    } catch (e) {
      console.warn('drawShapBeeswarm failed:', e);
    }
  }

  private drawPrCurvePlot(cv: any, attempt: number = 0): void {
    const Plotly = (window as any).Plotly; if (!Plotly) return;
    const pr = cv.pr_curve || {};
    const el = document.getElementById('cv-pr-plot');
    if (!el) {
      if (attempt < 10) setTimeout(() => this.drawPrCurvePlot(cv, attempt + 1), 250);
      return;
    }
    const recall: number[] = Array.isArray(pr.recall) ? pr.recall : [0, 1];
    const meanPrec: number[] | null = Array.isArray(pr.mean_precision) ? pr.mean_precision : null;
    const stdPrec: number[] | null = Array.isArray(pr.std_precision) ? pr.std_precision : null;
    const foldPrec: number[][] = Array.isArray(pr.fold_precision) ? pr.fold_precision : [];
    const rawFolds: Array<{precision:number[]; recall:number[]; auc?: number}> = Array.isArray(pr.folds_raw) ? pr.folds_raw : [];
    const baseline: number | null = (pr.baseline ?? cv?.pr_curve?.baseline ?? null);
    const micro: any = cv.pr_curve_micro || null;
    const traces: any[] = [];

    // Fold curves
    const foldColor = 'rgba(120,120,120,0.35)';
    if (rawFolds.length) {
      rawFolds.forEach((rf, i) => {
        traces.push({ x: rf.recall, y: rf.precision, type: 'scatter', mode: 'lines', line: { color: foldColor, width: 1, shape: 'hv' }, name: `PR fold ${i}${(rf as any).auc != null ? ` (AUC = ${Number((rf as any).auc).toFixed(2)})` : (cv?.folds?.[i]?.pr_auc != null ? ` (AUC = ${Number(cv.folds[i].pr_auc).toFixed(2)})` : '')}`, hovertemplate: 'Recall=%{x:.3f}<br>Precision=%{y:.3f}<extra></extra>', showlegend: i === 0 } as any);
      });
    } else {
      // fallback to interpolated grid if raw folds missing
      foldPrec.forEach((prec, i) => {
        traces.push({ x: recall, y: prec, type: 'scatter', mode: 'lines', line: { color: foldColor, width: 1, shape: 'hv' }, name: `PR fold ${i}${cv?.folds?.[i]?.pr_auc != null ? ` (AUC = ${Number(cv.folds[i].pr_auc).toFixed(2)})` : ''}` , hovertemplate: 'Recall=%{x:.3f}<br>Precision=%{y:.3f}<extra></extra>', showlegend: i === 0 } as any);
      });
    }

    // Std shading
    if (meanPrec && stdPrec) {
      const lower = meanPrec.map((v, i) => Math.max(0, Math.min(1, v - stdPrec[i])));
      const upper = meanPrec.map((v, i) => Math.max(0, Math.min(1, v + stdPrec[i])));
      traces.push({ x: recall, y: lower, type: 'scatter', mode: 'lines', line: {color: 'rgba(0,0,0,0)'}, hoverinfo: 'skip', showlegend: false } as any);
      traces.push({ x: recall, y: upper, type: 'scatter', mode: 'lines', line: {color: 'rgba(0,0,0,0)'}, fill: 'tonexty', fillcolor: 'rgba(100,100,100,0.18)', name: '± 1 std. dev.', hoverinfo: 'skip' } as any);
    }

    // Mean PR (grid-based) shading/line: show only if micro-avg is not available
    if (meanPrec && !(micro && Array.isArray(micro.recall) && Array.isArray(micro.precision))) {
      traces.push({ x: recall, y: meanPrec, type: 'scatter', mode: 'lines', line: { color: '#1f77b4', width: 3, shape: 'hv' }, name: `Precision-Recall (AUC = ${(cv.pr_auc_mean ?? 0).toFixed(3)})`, hovertemplate: 'Recall=%{x:.3f}<br>Precision=%{y:.3f}<extra></extra>' } as any);
    }

    // Micro-averaged PR (if available), plotted as the main thick line
    if (micro && Array.isArray(micro.recall) && Array.isArray(micro.precision)) {
      traces.push({ x: micro.recall, y: micro.precision, type: 'scatter', mode: 'lines', line: { color: '#1976d2', width: 4, shape: 'hv' }, name: `Micro-avg PR (AP = ${(micro.ap ?? cv.pr_auc_mean ?? 0).toFixed(3)})`, hovertemplate: 'Recall=%{x:.3f}<br>Precision=%{y:.3f}<extra></extra>' } as any);
    }

    // Baseline
    if (baseline != null && !isNaN(baseline)) {
      traces.push({ x: [0,1], y: [baseline, baseline], type: 'scatter', mode: 'lines', line: { color: '#d32f2f', width: 2, dash: 'dash' }, name: 'Baseline', hovertemplate: 'Baseline=%{y:.3f}<extra></extra>' } as any);
    }

    const layout = {
      title: { text: '' },
      margin: { l: 64, r: 24, t: 12, b: 160 },
      xaxis: { title: { text: 'Recall', font: { size: 13 } }, range: [0, 1] },
      yaxis: { title: { text: 'Precision', font: { size: 13 } }, range: [0, 1] },
      hovermode: 'closest',
      legend: { orientation: 'h', x: 0, y: -0.40, xanchor: 'left', yanchor: 'top', font: { size: 11 }, bgcolor: 'rgba(255,255,255,0.95)', bordercolor: '#ddd', borderwidth: 1 }
    } as any;
    const config = { responsive: true, displayModeBar: true } as any;
    try { Plotly.react(el, traces, layout, config); } catch { Plotly.newPlot(el, traces, layout, config); }
  }

  public downloadBeeswarm(): void {
    try {
      const png = this.modelingStatus?.model?.beeswarm_png;
      if (!png) return;
      const link = document.createElement('a');
      link.href = png;
      const fileId = this.currentFileId != null ? this.currentFileId : 'beeswarm';
      link.download = `shap_beeswarm_${fileId}.png`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (e) {
      console.warn('downloadBeeswarm failed:', e);
    }
  }

  public openFeatureCard(featureName: string): void {
    try {
      if (!featureName || this.currentFileId == null) return;
      const fileId = String(this.currentFileId);
      const processedFile = this.processedFilePath || undefined;
      const dateColumn = this.splitDateColumn || (this.dateColumns.length > 0 ? this.dateColumns[0] : undefined);
      
      // Fetch data dictionary to get descriptions and other metadata
      this.dataService.getDataDictionary(fileId).subscribe({
        next: (dict: any[]) => {
          const features = Array.isArray(dict)
            ? dict.map(item => ({
                Feature_Name: String(item?.Feature_Name || ''),
                Feature_Description: String(item?.Feature_Description || 'No description available')
              })).filter(x => !!x.Feature_Name)
            : [{ Feature_Name: featureName, Feature_Description: 'No description available' }];
          
          // Find complete quality summary from datqSummary (full row with all metrics)
          let qualitySummary: any = null;
          if (this.datqSummary && Array.isArray(this.datqSummary)) {
            const row = this.datqSummary.find(r => 
              String(r['Variable'] || r['variable'] || r['index']) === String(featureName)
            );
            qualitySummary = row ? { ...row } : null;
          }
          
          // If not found in datqSummary, try to build from selected_features (partial data)
          if (!qualitySummary) {
            const selectedFeature = this.modelingStatus?.model?.selected_features?.find(
              (f: any) => f.feature === featureName
            );
            if (selectedFeature) {
              qualitySummary = {
                Variable: featureName,
                impact: selectedFeature.impact,
                signed_impact: selectedFeature.signed_impact,
                psi: selectedFeature.psi,
                csi: selectedFeature.csi
              };
            }
          }
          
          this.dialog.open(FeatureCardComponent, {
            width: '900px',
            data: {
              fileId: fileId,
              columnName: featureName,
              features: features,
              processedFile: processedFile,
              dateColumn: dateColumn,
              qualitySummary: qualitySummary || undefined,
              catLabelLookup: this.catLabelLookup
            }
          });
        },
        error: (err) => {
          console.warn('Failed to fetch data dictionary, opening with minimal data:', err);
          // Fallback: open with minimal data
          this.dialog.open(FeatureCardComponent, {
            width: '900px',
            data: {
              fileId: fileId,
              columnName: featureName,
              features: [{ Feature_Name: featureName, Feature_Description: 'No description available' }],
              processedFile: processedFile,
              dateColumn: dateColumn,
              catLabelLookup: this.catLabelLookup
            }
          });
        }
      });
    } catch (e) {
      console.warn('openFeatureCard failed:', e);
    }
  }

  /**
   * Add a new metric to SFS criteria
   */
  addSfsMetric(): void {
    this.sfsMetrics.push({ metric: 'pr_auc', pct_change: 1.0 });
  }

  /**
   * Remove a metric from SFS criteria
   */
  removeSfsMetric(index: number): void {
    if (this.sfsMetrics.length > 1) {
      this.sfsMetrics.splice(index, 1);
    } else {
      alert('At least one metric is required');
    }
  }

  /**
   * Restart SFS (reset results and show config panel)
   */
  restartSfs(): void {
    this.sfsResults = null;
    this.sfsForwardResults = [];
    this.sfsBackwardResults = [];
    this.sfsForwardFromBackwardResults = [];
    this.sfsBackwardCutStep = null;
    this.sfsBackwardCutFeatures = [];
    this.sfsRunning = false;
    this.sfsProgress = 0;
    this.sfsMessage = '';
    this.sfsCurrentMetrics = {};
    this.sfsCompletedSteps = [];
    this.showSfsProgressModal = false;
  }

  /**
   * Open modal to view SFS progress details
   */
  openSfsProgressModal(): void {
    this.showSfsProgressModal = true;
  }

  /**
   * Close SFS progress modal
   */
  closeSfsProgressModal(): void {
    this.showSfsProgressModal = false;
  }

  /**
   * Start SFS with user-selected configuration
   */
  startSfs(): void {
    if (!this.currentFileId) return;
    
    // Validate: at least one method must be selected
    if (!this.sfsMethodForward && !this.sfsMethodBackward) {
      alert('Please select at least one SFS method (Forward or Backward)');
      return;
    }
    
    // Validate: at least one metric
    if (this.sfsMetrics.length === 0) {
      alert('Please add at least one metric');
      return;
    }
    
    // Build methods array
    const methods: string[] = [];
    if (this.sfsMethodForward) methods.push('forward');
    if (this.sfsMethodBackward) methods.push('backward');
    
    // Build stopping criteria with multiple metrics
    const stoppingCriteria = {
      metrics: this.sfsMetrics,
      min_features: this.sfsMinFeatures,
      max_features: this.sfsMaxFeatures
    };
    
    // Collect features marked as "drop" in the Usage column
    const excludedFeatures = Object.keys(this.featureUsage).filter(f => this.featureUsage[f] === 'drop');
    const excludedReasonsMap: { [feature: string]: string } = {};
    excludedFeatures.forEach(f => {
      if (this.featureDropReason[f]) {
        excludedReasonsMap[f] = this.featureDropReason[f];
      }
    });
    if (excludedFeatures.length > 0) {
      console.log('[SFS] Excluding features marked as "drop":', excludedFeatures, 'Reasons:', excludedReasonsMap);
    }
    
    console.log('[SFS] Starting with config:', { methods, stoppingCriteria, excludedFeatures });
    
    this.sfsRunning = true;
    this.sfsProgress = 0;
    this.sfsMessage = 'Starting SFS...';
    this.sfsCurrentMetrics = {};
    this.sfsCompletedSteps = [];
    
    this.dataService.startSfs(this.currentFileId, methods, stoppingCriteria, excludedFeatures).subscribe({
      next: (resp: any) => {
        console.log('[SFS] Started:', resp);
        this.sfsMessage = resp.message || 'SFS running...';
        // Start polling for progress
        this.startSfsStatusPolling();
      },
      error: (err: any) => {
        console.error('[SFS] Failed to start:', err);
        this.sfsRunning = false;
        this.sfsMessage = 'Failed to start SFS: ' + (err.message || err);
      }
    });
  }

  /**
   * Start forward selection using the remaining features from backward elimination
   */
  startForwardFromBackwardFeatures(): void {
    if (!this.currentFileId) return;
    const featuresToUse = this.sfsBackwardCutFeatures.length > 0
      ? this.sfsBackwardCutFeatures
      : this.sfsBackwardRemainingFeatures;
    if (!featuresToUse || featuresToUse.length === 0) {
      alert('No remaining features available from backward elimination');
      return;
    }

    // Prepare stopping criteria for forward selection
    const stoppingCriteria = {
      metrics: this.sfsMetrics,
      min_features: this.sfsMinFeatures,
      max_features: this.sfsMaxFeatures
    };

    this.sfsRunning = true;
    this.sfsProgress = 0;
    this.sfsMessage = `Starting forward selection with ${featuresToUse.length} features from cut step ${this.sfsBackwardCutStep}...`;
    this.sfsCurrentMetrics = {};
    this.sfsCompletedSteps = [];

    // Call startSfs with initial_features parameter
    this.dataService.startSfsWithInitialFeatures(
      this.currentFileId,
      ['forward'],
      stoppingCriteria,
      featuresToUse
    ).subscribe({
      next: (resp: any) => {
        console.log('[SFS-Chain] Forward from backward started:', resp);
        this.sfsMessage = `Running forward selection on ${featuresToUse.length} features from cut step ${this.sfsBackwardCutStep}...`;
        this.startSfsStatusPolling();
      },
      error: (err: any) => {
        console.error('[SFS-Chain] Failed to start:', err);
        this.sfsRunning = false;
        this.sfsMessage = 'Failed to start forward selection: ' + (err.message || err);
      }
    });
  }

  /**
   * Poll SFS status/progress
   */
  private startSfsStatusPolling(): void {
    if (this.currentFileId == null) return;
    
    // Clear any existing subscription
    if (this.sfsPolling) {
      this.sfsPolling.unsubscribe();
    }
    
    this.sfsPolling = interval(1000).subscribe(() => {
      if (this.currentFileId == null) return;
      
      this.dataService.getSfsStatus(this.currentFileId).subscribe({
        next: (statusData: any) => {
          console.log('[SFS-Status]', statusData);
          
          this.sfsProgress = statusData.progress || 0;
          this.sfsMessage = statusData.message || 'Running...';
          this.sfsCurrentMetrics = statusData.current_metrics || {};
          this.sfsCompletedSteps = statusData.completed_steps || [];
          
          const status = statusData.status;
          if (status === 'completed') {
            this.stopSfsStatusPolling();
            this.sfsRunning = false;
            this.sfsProgress = 1.0;
            this.sfsMessage = 'SFS completed successfully!';
            // Fetch final results
            setTimeout(() => this.fetchSfsResults(), 500);
          } else if (status === 'error') {
            this.stopSfsStatusPolling();
            this.sfsRunning = false;
            this.sfsMessage = 'SFS failed: ' + (statusData.error || 'Unknown error');
          }
        },
        error: (err: any) => {
          console.error('[SFS-Status] Polling error:', err);
          this.stopSfsStatusPolling();
          this.sfsRunning = false;
          this.sfsMessage = 'Failed to get SFS status';
        }
      });
    });
  }

  /**
   * Stop SFS status polling
   */
  private stopSfsStatusPolling(): void {
    if (this.sfsPolling) {
      this.sfsPolling.unsubscribe();
      this.sfsPolling = null;
    }
  }

  /**
   * Fetch SFS (Sequential Feature Selection) results from backend
   */
  fetchSfsResults(): void {
    if (!this.currentFileId) return;
    
    this.dataService.getSfsResults(this.currentFileId).subscribe({
      next: (data: any) => {
        console.log('[SFS] Results received:', data);
        this.sfsResults = data;
        this.sfsForwardResults = data.forward || [];
        this.sfsBackwardResults = data.backward || [];
        this.sfsBackwardRemainingFeatures = data.backward_remaining_features || [];
        this.sfsForwardFromBackwardResults = data.forward_from_backward || [];
        console.log('[SFS] Backward remaining features:', this.sfsBackwardRemainingFeatures);
        console.log('[SFS] Forward-from-backward results:', this.sfsForwardFromBackwardResults.length);
        // Initialize cut point to last backward step (default = all eliminations applied)
        this.initBackwardCutStep();
      },
      error: (err: any) => {
        console.warn('[SFS] Failed to fetch results:', err);
        this.sfsResults = null;
        this.sfsForwardResults = [];
        this.sfsBackwardResults = [];
        this.sfsBackwardRemainingFeatures = [];
        this.sfsBackwardCutStep = null;
        this.sfsBackwardCutFeatures = [];
      }
    });
  }

  /**
   * Initialize backward cut step to the last step (default behavior)
   */
  initBackwardCutStep(): void {
    if (this.sfsBackwardResults.length > 0) {
      const lastStep = this.sfsBackwardResults[this.sfsBackwardResults.length - 1];
      this.sfsBackwardCutStep = lastStep.step;
      this.sfsBackwardCutFeatures = lastStep.selected_features || this.sfsBackwardRemainingFeatures;
    } else {
      this.sfsBackwardCutStep = null;
      this.sfsBackwardCutFeatures = [];
    }
  }

  /**
   * Set the backward elimination cutting point to a specific step.
   * Features remaining at that step become the candidate set for forward selection.
   */
  setBackwardCutStep(step: any): void {
    this.sfsBackwardCutStep = step.step;
    this.sfsBackwardCutFeatures = step.selected_features ? [...step.selected_features] : [];
    console.log(`[SFS] Cut step set to ${step.step}, remaining features (${this.sfsBackwardCutFeatures.length}):`, this.sfsBackwardCutFeatures);
  }

  /**
   * Open modal to show detailed impact of adding/dropping a feature
   */
  openSfsDetailModal(step: any): void {
    this.selectedSfsStep = step;
    this.previousSfsStep = this.findPreviousStep(step);
    this.showSfsModal = true;
    setTimeout(() => this.drawSfsFeatureProgressionCharts(), 50);
  }

  findPreviousStep(currentStep: any): any | null {
    if (!currentStep || currentStep.step <= 1) return null;
    const prevStepNum = currentStep.step - 1;
    const direction = currentStep.direction;
    const resultsArray = direction === 'forward' ? this.sfsForwardResults : this.sfsBackwardResults;
    return resultsArray.find((s: any) => s.step === prevStepNum && s.direction === direction) || null;
  }

  /**
   * Close SFS detail modal
   */
  closeSfsModal(): void {
    this.showSfsModal = false;
    this.sfsModalExpanded = false;
    this.selectedSfsStep = null;
    this.previousSfsStep = null;
  }

  toggleSfsModalExpand(): void {
    this.sfsModalExpanded = !this.sfsModalExpanded;
    setTimeout(() => this.drawSfsFeatureProgressionCharts(), 100);
  }

  /**
   * Get formatted PSI/CSI value for display
   */
  getStabilityDisplay(step: any): string {
    if (!step.stability_value) return 'N/A';
    return `${step.stability_type}=${step.stability_value.toFixed(4)}`;
  }

  /**
   * Get SHAP changes as array for modal display
   */
  getShapChangesArray(shapChanges: any): Array<{feature: string, change: number}> {
    if (!shapChanges) return [];
    return Object.keys(shapChanges).map(key => ({
      feature: key,
      change: shapChanges[key]
    })).sort((a, b) => Math.abs(b.change) - Math.abs(a.change));
  }

  getFeatureImpactRows(step: any, prevStep: any = null): Array<{ feature: string; gain: number; shap: number; prevGain: number | null; prevShap: number | null }> {
    if (!step) return [];
    const selectedFeatures: string[] = step.selected_features || [];
    if (!Array.isArray(selectedFeatures) || selectedFeatures.length === 0) return [];

    const gainRaw = step.feature_importance || {};
    const shapRaw = step.shap_importance_by_feature || {};

    const gainMap: Record<string, number> = {};
    Object.keys(gainRaw || {}).forEach((k) => {
      const v = Number(gainRaw[k] ?? 0);
      gainMap[k] = Number.isFinite(v) ? v : 0;
    });

    const normalizedGainByFeature: Record<string, number> = {};
    for (const k of Object.keys(gainMap)) {
      if (selectedFeatures.includes(k)) {
        normalizedGainByFeature[k] = gainMap[k];
        continue;
      }
      const m = /^f(\d+)$/.exec(k);
      if (m) {
        const idx = Number(m[1]);
        const featName = selectedFeatures[idx];
        if (featName) {
          normalizedGainByFeature[featName] = gainMap[k];
        }
      }
    }

    const prevGainMap: Record<string, number> = {};
    const prevShapMap: Record<string, number> = {};
    if (prevStep) {
      const prevFeatures: string[] = prevStep.selected_features || [];
      const prevGainRaw = prevStep.feature_importance || {};
      const prevShapRaw = prevStep.shap_importance_by_feature || {};
      Object.keys(prevGainRaw || {}).forEach((k) => {
        const v = Number(prevGainRaw[k] ?? 0);
        if (prevFeatures.includes(k)) {
          prevGainMap[k] = Number.isFinite(v) ? v : 0;
        } else {
          const m = /^f(\d+)$/.exec(k);
          if (m) {
            const idx = Number(m[1]);
            const featName = prevFeatures[idx];
            if (featName) prevGainMap[featName] = Number.isFinite(v) ? v : 0;
          }
        }
      });
      Object.keys(prevShapRaw || {}).forEach((k) => {
        const v = Number(prevShapRaw[k] ?? 0);
        prevShapMap[k] = Number.isFinite(v) ? v : 0;
      });
    }

    const rows = selectedFeatures.map((feature) => {
      const gainVal = Number(normalizedGainByFeature[feature] ?? 0);
      const shapVal = Number(shapRaw?.[feature] ?? 0);
      const prevGainVal = prevStep && feature in prevGainMap ? prevGainMap[feature] : null;
      const prevShapVal = prevStep && feature in prevShapMap ? prevShapMap[feature] : null;
      return {
        feature,
        gain: Number.isFinite(gainVal) ? gainVal : 0,
        shap: Number.isFinite(shapVal) ? shapVal : 0,
        prevGain: prevGainVal !== null && Number.isFinite(prevGainVal) ? prevGainVal : null,
        prevShap: prevShapVal !== null && Number.isFinite(prevShapVal) ? prevShapVal : null
      };
    });

    return rows.sort((a, b) => Math.abs(b.shap) - Math.abs(a.shap));
  }

  /**
   * Normalize gain keys (f0, f1... or actual names) to real feature names
   */
  private normalizeGainMap(gainRaw: Record<string, number>, selectedFeatures: string[]): Record<string, number> {
    const result: Record<string, number> = {};
    for (const k of Object.keys(gainRaw)) {
      const v = Number(gainRaw[k] ?? 0);
      if (!Number.isFinite(v)) continue;
      if (selectedFeatures.includes(k)) {
        result[k] = v;
      } else {
        const m = /^f(\d+)$/.exec(k);
        if (m) {
          const idx = Number(m[1]);
          const featName = selectedFeatures[idx];
          if (featName) result[featName] = v;
        }
      }
    }
    return result;
  }

  /**
   * Build per-feature metric progression across all SFS steps for the current direction.
   * Returns { featureNames: string[], steps: number[],
   *   shap: Record<string, (number|null)[]>, gain: Record<string, (number|null)[]>,
   *   stability: { steps: number[], values: (number|null)[], types: string[] },
   *   modelMetrics: { cvRocAuc: number[], cvPrAuc: number[], trainRocAuc: number[], testRocAuc: number[] } }
   */
  buildFeatureProgressionData(): any {
    if (!this.selectedSfsStep) return null;
    const direction = this.selectedSfsStep.direction;
    const allSteps = direction === 'forward' ? this.sfsForwardResults : this.sfsBackwardResults;
    if (!allSteps || allSteps.length === 0) return null;

    const sortedSteps = [...allSteps].sort((a: any, b: any) => a.step - b.step);

    // Collect all feature names that appear in any step
    const allFeatureNames = new Set<string>();
    for (const step of sortedSteps) {
      const feats: string[] = step.selected_features || [];
      feats.forEach((f: string) => allFeatureNames.add(f));
    }

    const stepNumbers = sortedSteps.map((s: any) => s.step);

    // Per-feature SHAP and Gain across steps
    const shapByFeature: Record<string, (number | null)[]> = {};
    const gainByFeature: Record<string, (number | null)[]> = {};
    allFeatureNames.forEach(f => {
      shapByFeature[f] = [];
      gainByFeature[f] = [];
    });

    // Per-step stability and model metrics
    const stabilitySteps: number[] = [];
    const stabilityValues: (number | null)[] = [];
    const stabilityTypes: string[] = [];
    const cvRocAuc: number[] = [];
    const cvPrAuc: number[] = [];
    const trainRocAuc: number[] = [];
    const testRocAuc: number[] = [];

    for (const step of sortedSteps) {
      const feats: string[] = step.selected_features || [];
      const shapRaw = step.shap_importance_by_feature || {};
      const gainRaw = step.feature_importance || {};
      const normalizedGain = this.normalizeGainMap(gainRaw, feats);

      allFeatureNames.forEach(f => {
        if (feats.includes(f)) {
          shapByFeature[f].push(Number(shapRaw[f] ?? 0));
          gainByFeature[f].push(Number(normalizedGain[f] ?? 0));
        } else {
          shapByFeature[f].push(null);
          gainByFeature[f].push(null);
        }
      });

      stabilitySteps.push(step.step);
      stabilityValues.push(step.stability_value != null ? Number(step.stability_value) : null);
      stabilityTypes.push(step.stability_type || 'N/A');

      cvRocAuc.push(Number(step.cv_roc_auc ?? 0));
      cvPrAuc.push(Number(step.cv_pr_auc ?? 0));
      trainRocAuc.push(Number(step.train_roc_auc ?? 0));
      testRocAuc.push(Number(step.test_roc_auc ?? 0));
    }

    return {
      featureNames: Array.from(allFeatureNames),
      steps: stepNumbers,
      shap: shapByFeature,
      gain: gainByFeature,
      stability: { steps: stabilitySteps, values: stabilityValues, types: stabilityTypes },
      modelMetrics: { cvRocAuc, cvPrAuc, trainRocAuc, testRocAuc }
    };
  }

  /**
   * Draw Plotly line charts for feature progression in the SFS detail modal
   */
  drawSfsFeatureProgressionCharts(): void {
    if (!this.isBrowser) return;
    const Plotly = (window as any).Plotly;
    if (!Plotly) return;
    const data = this.buildFeatureProgressionData();
    if (!data) return;

    const currentFeature = this.selectedSfsStep?.feature_name;
    const currentStep = this.selectedSfsStep?.step;

    // Color palette for features
    const colors = [
      '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
      '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
      '#aec7e8', '#ffbb78', '#98df8a', '#ff9896', '#c5b0d5'
    ];

    // Helper: vertical line shape at current step
    const currentStepLine = (yMin: number, yMax: number): any => ({
      type: 'line', x0: currentStep, x1: currentStep, y0: yMin, y1: yMax,
      line: { color: 'rgba(220,20,60,0.4)', width: 2, dash: 'dot' }
    });

    // Helper: annotation for current step
    const currentStepAnnotation = (yPos: number): any => ({
      x: currentStep, y: yPos, xanchor: 'left', yanchor: 'bottom',
      text: ` Step ${currentStep}`, showarrow: false,
      font: { size: 10, color: 'crimson' }, bgcolor: 'rgba(255,255,255,0.8)'
    });

    const baseLayout = {
      margin: { l: 60, r: 20, t: 36, b: 50 },
      hovermode: 'x unified' as const,
      legend: { orientation: 'h' as const, x: 0, y: -0.25, xanchor: 'left' as const, yanchor: 'top' as const, font: { size: 10 } },
      xaxis: { title: { text: 'SFS Step', font: { size: 12 } }, dtick: 1 }
    };
    const config = { responsive: true, displayModeBar: false } as any;

    // --- 1. SHAP Impact Progression ---
    const shapEl = document.getElementById('sfs-progression-shap');
    if (shapEl) {
      const traces: any[] = [];
      data.featureNames.forEach((feat: string, i: number) => {
        const isHighlighted = feat === currentFeature;
        traces.push({
          type: 'scatter', mode: 'lines+markers', connectgaps: false,
          x: data.steps, y: data.shap[feat],
          name: feat,
          line: { color: colors[i % colors.length], width: isHighlighted ? 3 : 1.5, dash: isHighlighted ? 'solid' : 'solid' },
          marker: { size: isHighlighted ? 8 : 4 },
          opacity: isHighlighted ? 1.0 : 0.5,
          hovertemplate: `${feat}: %{y:.6f}<extra></extra>`
        });
      });
      const allShapVals = Object.values(data.shap).flat().filter((v: any) => v != null) as number[];
      const yMin = Math.min(0, ...allShapVals);
      const yMax = Math.max(...allShapVals) * 1.1 || 1;
      const layout = {
        ...baseLayout,
        title: { text: 'SHAP Impact per Feature Across Steps', font: { size: 13 } },
        yaxis: { title: { text: 'Mean |SHAP|', font: { size: 12 } } },
        shapes: [currentStepLine(yMin, yMax)],
        annotations: [currentStepAnnotation(yMax)]
      };
      try { Plotly.react(shapEl, traces, layout, config); } catch { Plotly.newPlot(shapEl, traces, layout, config); }
    }

    // --- 2. Gain Importance Progression ---
    const gainEl = document.getElementById('sfs-progression-gain');
    if (gainEl) {
      const traces: any[] = [];
      data.featureNames.forEach((feat: string, i: number) => {
        const isHighlighted = feat === currentFeature;
        traces.push({
          type: 'scatter', mode: 'lines+markers', connectgaps: false,
          x: data.steps, y: data.gain[feat],
          name: feat,
          line: { color: colors[i % colors.length], width: isHighlighted ? 3 : 1.5 },
          marker: { size: isHighlighted ? 8 : 4 },
          opacity: isHighlighted ? 1.0 : 0.5,
          hovertemplate: `${feat}: %{y:.4f}<extra></extra>`
        });
      });
      const allGainVals = Object.values(data.gain).flat().filter((v: any) => v != null) as number[];
      const yMin = Math.min(0, ...allGainVals);
      const yMax = Math.max(...allGainVals) * 1.1 || 1;
      const layout = {
        ...baseLayout,
        title: { text: 'Gain Importance per Feature Across Steps', font: { size: 13 } },
        yaxis: { title: { text: 'XGBoost Gain', font: { size: 12 } } },
        shapes: [currentStepLine(yMin, yMax)],
        annotations: [currentStepAnnotation(yMax)]
      };
      try { Plotly.react(gainEl, traces, layout, config); } catch { Plotly.newPlot(gainEl, traces, layout, config); }
    }

    // --- 3. Stability (PSI/CSI) Progression ---
    const stabEl = document.getElementById('sfs-progression-stability');
    if (stabEl) {
      const stabVals = data.stability.values;
      const stabTexts = data.stability.types.map((t: string, i: number) =>
        `${t}=${stabVals[i] != null ? Number(stabVals[i]).toFixed(4) : 'N/A'}`
      );
      const traces: any[] = [{
        type: 'scatter', mode: 'lines+markers',
        x: data.steps, y: stabVals,
        name: 'PSI / CSI',
        line: { color: '#e377c2', width: 2 },
        marker: { size: 6 },
        text: stabTexts,
        hovertemplate: '%{text}<extra></extra>'
      }];
      const cleanVals = stabVals.filter((v: any) => v != null) as number[];
      const yMax = cleanVals.length > 0 ? Math.max(...cleanVals) * 1.3 || 0.1 : 0.1;
      const layout = {
        ...baseLayout,
        title: { text: 'Stability Metric (PSI/CSI) per Step', font: { size: 13 } },
        yaxis: { title: { text: 'PSI / CSI', font: { size: 12 } }, rangemode: 'tozero' as const },
        shapes: [
          currentStepLine(0, yMax),
          { type: 'line', x0: data.steps[0], x1: data.steps[data.steps.length - 1], y0: 0.1, y1: 0.1, line: { color: '#ff9800', width: 1, dash: 'dash' } },
          { type: 'line', x0: data.steps[0], x1: data.steps[data.steps.length - 1], y0: 0.25, y1: 0.25, line: { color: '#f44336', width: 1, dash: 'dash' } }
        ],
        annotations: [
          currentStepAnnotation(yMax),
          { x: data.steps[data.steps.length - 1], y: 0.1, xanchor: 'right', yanchor: 'bottom', text: 'Caution (0.1)', showarrow: false, font: { size: 9, color: '#ff9800' } },
          { x: data.steps[data.steps.length - 1], y: 0.25, xanchor: 'right', yanchor: 'bottom', text: 'Unstable (0.25)', showarrow: false, font: { size: 9, color: '#f44336' } }
        ]
      };
      try { Plotly.react(stabEl, traces, layout, config); } catch { Plotly.newPlot(stabEl, traces, layout, config); }
    }

    // --- 4. Model Performance (CV ROC-AUC / PR-AUC) Progression ---
    const perfEl = document.getElementById('sfs-progression-performance');
    if (perfEl) {
      const traces: any[] = [
        { type: 'scatter', mode: 'lines+markers', x: data.steps, y: data.modelMetrics.cvRocAuc, name: 'CV ROC-AUC', line: { color: '#1f77b4', width: 2.5 }, marker: { size: 6 }, hovertemplate: 'CV ROC-AUC: %{y:.4f}<extra></extra>' },
        { type: 'scatter', mode: 'lines+markers', x: data.steps, y: data.modelMetrics.cvPrAuc, name: 'CV PR-AUC', line: { color: '#ff7f0e', width: 2.5 }, marker: { size: 6 }, hovertemplate: 'CV PR-AUC: %{y:.4f}<extra></extra>' },
        { type: 'scatter', mode: 'lines+markers', x: data.steps, y: data.modelMetrics.trainRocAuc, name: 'Train ROC-AUC', line: { color: '#1f77b4', width: 1, dash: 'dash' }, marker: { size: 4 }, opacity: 0.5, hovertemplate: 'Train ROC-AUC: %{y:.4f}<extra></extra>' },
        { type: 'scatter', mode: 'lines+markers', x: data.steps, y: data.modelMetrics.testRocAuc, name: 'Test ROC-AUC', line: { color: '#2ca02c', width: 1, dash: 'dot' }, marker: { size: 4 }, opacity: 0.5, hovertemplate: 'Test ROC-AUC: %{y:.4f}<extra></extra>' }
      ];
      const allPerf = [...data.modelMetrics.cvRocAuc, ...data.modelMetrics.cvPrAuc, ...data.modelMetrics.trainRocAuc, ...data.modelMetrics.testRocAuc].filter((v: number) => Number.isFinite(v));
      const yMin = Math.min(...allPerf) * 0.95 || 0;
      const yMax = Math.max(...allPerf) * 1.02 || 1;
      const layout = {
        ...baseLayout,
        title: { text: 'Model Performance Across Steps', font: { size: 13 } },
        yaxis: { title: { text: 'Metric Value', font: { size: 12 } }, range: [yMin, yMax] },
        shapes: [currentStepLine(yMin, yMax)],
        annotations: [currentStepAnnotation(yMax)]
      };
      try { Plotly.react(perfEl, traces, layout, config); } catch { Plotly.newPlot(perfEl, traces, layout, config); }
    }
  }
}
