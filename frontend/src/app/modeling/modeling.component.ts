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
  selectedSfsStep: any | null = null;  // For modal display
  showSfsModal: boolean = false;

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
    this.dataService.startModeling(this.currentFileId, this.processedFilePath, this.selectedAlgorithm || undefined, excludedVariables).pipe(
      finalize(() => this.isStarting = false)
    ).subscribe({
      next: (resp) => {
        console.log('Modeling started:', resp);
        this.modelingStatus = resp;
        // Debug: Check SHAP data
        console.log('SHAP beeswarm present?', !!resp?.model?.shap_beeswarm);
        console.log('Selected features count:', resp?.model?.selected_features?.length || 0);
        // Check if SFS is ready (training data saved)
        this.sfsReady = resp?.model?.sfs_ready || false;
        console.log('SFS ready?', this.sfsReady);
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
          // Check if SFS is ready
          this.sfsReady = status?.model?.sfs_ready || false;
          const s = status?.job_status || status?.status;
          if (s === 'completed' || s === 'error') {
            this.stopStatusPolling();
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
          traces.push({
            type: 'scatter',
            mode: 'markers',
            name: features[i],
            x: idxNonNull.map(j => xs[j]),
            y: idxNonNull.map(j => yvals[j]),
            customdata: idxNonNull.map(j => rawArr[j]),
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
            hovertemplate: `Feature=${features[i]}<br>SHAP=%{x:.4f}<br>Value=%{customdata:.4f}<extra></extra>`,
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
              qualitySummary: qualitySummary || undefined
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
              dateColumn: dateColumn
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
    
    console.log('[SFS] Starting with config:', { methods, stoppingCriteria });
    
    this.sfsRunning = true;
    this.sfsProgress = 0;
    this.sfsMessage = 'Starting SFS...';
    this.sfsCurrentMetrics = {};
    this.sfsCompletedSteps = [];
    
    this.dataService.startSfs(this.currentFileId, methods, stoppingCriteria).subscribe({
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
      },
      error: (err: any) => {
        console.warn('[SFS] Failed to fetch results:', err);
        this.sfsResults = null;
        this.sfsForwardResults = [];
        this.sfsBackwardResults = [];
      }
    });
  }

  /**
   * Open modal to show detailed impact of adding/dropping a feature
   */
  openSfsDetailModal(step: any): void {
    this.selectedSfsStep = step;
    this.showSfsModal = true;
  }

  /**
   * Close SFS detail modal
   */
  closeSfsModal(): void {
    this.showSfsModal = false;
    this.selectedSfsStep = null;
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
}
