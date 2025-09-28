import { Component, OnInit, Inject } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { PLATFORM_ID } from '@angular/core';
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
  isBrowser: boolean = false;

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

  constructor(private sharedService: SharedService, private dataService: DataService, private router: Router, @Inject(PLATFORM_ID) platformId: Object) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  ngOnInit(): void {
    if (this.isBrowser) {
      this.loadPlotly();
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
            // draw CV charts when available
            setTimeout(() => this.drawCvCharts(), 0);
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
        const Plotly = await import('plotly.js-dist-min');
        (window as any).Plotly = Plotly.default;
      }
    } catch (e) {
      console.warn('Failed to load Plotly for CV charts:', e);
    }
  }

  private drawCvCharts(): void {
    try {
      if (!this.isBrowser) return;
      const Plotly = (window as any).Plotly; if (!Plotly) return;
      const cv = this.modelingStatus?.model?.cv; if (!cv) return;
      if (cv.roc_curve) this.drawRocCurvePlot(cv);
      if (cv.pr_curve) this.drawPrCurvePlot(cv);
      // SHAP beeswarm
      this.drawShapBeeswarm();
    } catch (e) {
      console.warn('drawCvCharts failed:', e);
    }
  }

  private drawRocCurvePlot(cv: any): void {
    const Plotly = (window as any).Plotly; if (!Plotly) return;
    const roc = cv.roc_curve; if (!roc) return;
    const el = document.getElementById('cv-roc-plot'); if (!el) return;
    const fpr: number[] = roc.fpr || [];
    const meanTpr: number[] | null = roc.mean_tpr || null;
    const stdTpr: number[] | null = roc.std_tpr || null;
    const foldTpr: number[][] = roc.fold_tpr || [];
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
  private drawShapBeeswarm(): void {
    try {
      if (!this.isBrowser) return;
      const Plotly = (window as any).Plotly; if (!Plotly) return;
      const payload = this.modelingStatus?.model?.shap_beeswarm; if (!payload) return;
      const el = document.getElementById('shap-beeswarm'); if (!el) return;

      const features: string[] = payload.features || [];
      const shapValues: number[][] = payload.shap_values || [];
      const featureValues: number[][] = payload.feature_values || [];
      const nFeat = features.length;
      if (!nFeat) return;

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

      for (let i = 0; i < nFeat; i++) {
        const xs = (shapValues[i] || []).map(v => Number(v));
        const vsRaw = (featureValues[i] || []).map(v => Number(v));
        const vs = vsRaw.map(v => Number.isFinite(v) ? v : 0);
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
        // Robust min/max per feature (like SHAP): use [5th,95th] pct to avoid outliers dominating
        let vmin = q(vs, 0.05);
        let vmax = q(vs, 0.95);
        if (!isFinite(vmin) || !isFinite(vmax) || vmin === vmax) {
          vmin = Math.min(...vs);
          vmax = Math.max(...vs);
          if (vmin === vmax) { vmin = vmax - 1; }
        }
        const denom = (vmax - vmin) !== 0 ? (vmax - vmin) : 1e-12;
        const cnorm = vs.map(v => (v - vmin) / denom).map(u => u < 0 ? 0 : (u > 1 ? 1 : u));
        if (i === 0) {
          try { console.debug('[SHAP] feature', features[i], 'min/max', vmin, vmax); } catch {}
        }
        traces.push({
          type: 'scatter',
          mode: 'markers',
          name: features[i],
          x: xs,
          y: yvals,
          customdata: vs,
          marker: {
            color: cnorm,
            colorscale,
            cmin: 0,
            cmax: 1,
            showscale: i === 0,
            colorbar: i === 0 ? { title: { text: 'Feature value' }, thickness: 14, tickmode: 'array', tickvals: [0, 1], ticktext: ['Low', 'High'] } : undefined,
            size: 6,
            opacity: 0.8
          },
          hovertemplate: `Feature=${features[i]}<br>SHAP=%{x:.4f}<br>Value=%{customdata:.4f}<extra></extra>`,
          showlegend: false
        } as any);
      }

      const tickvals = Array.from({ length: nFeat }, (_, idx) => idx);
      const ticktext = Array.from({ length: nFeat }, (_, idx) => features[nFeat - 1 - idx]);
      const layout = {
        title: { text: '' },
        margin: { l: 160, r: 48, t: 12, b: 40 },
        xaxis: { title: { text: 'SHAP value (impact on model output)' }, zeroline: true, zerolinecolor: '#888', zerolinewidth: 1 },
        yaxis: { tickmode: 'array', tickvals, ticktext, range: [-0.6, nFeat - 0.4] },
        showlegend: false,
        hovermode: 'closest',
        shapes: [{ type: 'line', x0: 0, x1: 0, y0: -0.5, y1: nFeat - 0.5, line: { color: '#888', width: 1 } }]
      } as any;
      const config = { responsive: true, displayModeBar: true } as any;
      try { Plotly.react(el, traces, layout, config); } catch { Plotly.newPlot(el, traces, layout, config); }
    } catch (e) {
      console.warn('drawShapBeeswarm failed:', e);
    }
  }

  private drawPrCurvePlot(cv: any): void {
    const Plotly = (window as any).Plotly; if (!Plotly) return;
    const pr = cv.pr_curve; if (!pr) return;
    const el = document.getElementById('cv-pr-plot'); if (!el) return;
    const recall: number[] = pr.recall || [];
    const meanPrec: number[] | null = pr.mean_precision || null;
    const stdPrec: number[] | null = pr.std_precision || null;
    const foldPrec: number[][] = pr.fold_precision || [];
    const rawFolds: Array<{precision:number[]; recall:number[]; auc?: number}> = pr.folds_raw || [];
    const baseline: number | null = pr.baseline ?? null;
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
}
