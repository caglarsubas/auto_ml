import { Component, Inject, OnInit, OnDestroy, PLATFORM_ID } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { MAT_DIALOG_DATA, MatDialogRef, } from '@angular/material/dialog';
import { DataService } from '../services/data.service';
import { HttpErrorResponse } from '@angular/common/http';
import * as math from 'mathjs';  // Optional: using math.js for easier percentile calculation
import { forkJoin } from 'rxjs';
import { MatTabsModule } from '@angular/material/tabs';
import { MatSelectModule } from '@angular/material/select';

declare var Plotly: any;

interface FeatureData {
  Feature_Name: string;
  Feature_Description: string;
  Level_of_Measurement: string;
  Descriptive_Stats: {
    [key: string]: any;
  };
  histogram_data?: number[];  // Add this line
  value_counts?: { [key: string]: number };
  Target_Classes?: string[];
  Stacked_Stats?: { [targetClass: string]: { [stat: string]: any } };
}

interface FeatureInfo {
  Feature_Name: string;
  Feature_Description: string;
}

interface SfsImportanceContext {
  label: string;  // e.g. "Final Model (12 features)" or "Step 5 — Added: feature_x"
  gain: Array<{ feature: string; score: number }>;
  shap: Array<{ feature: string; score: number }>;
  modelPath?: string;  // For explainability — saved SFS model path
  selectedFeatures?: string[];  // For on-demand step explainability
}

interface FeatureCardDialogData {
  fileId: string;
  columnName: string;
  features: FeatureInfo[];
  processedFile?: string;
  encodedFile?: string;
  dateColumn?: string;
  qualitySummary?: { [key: string]: any };
  catLabelLookup?: { [feature: string]: { [encoded: string]: string } };
  // Optional: pre-loaded importance data from SFS final model
  importanceOverrides?: {
    gain: Array<{ feature: string; score: number }>;
    shap: Array<{ feature: string; score: number }>;
  };
  importanceContext?: string; // Label like "SFS Forward — Final Model"
  sfsModelPath?: string; // Relative path to SFS final model for explainability
  // SFS dual-context: Final Model Fit + Feature Added Step
  sfsContexts?: SfsImportanceContext[];
}


@Component({
  selector: 'app-feature-card',
  templateUrl: './feature-card.component.html',
  styleUrls: ['./feature-card.component.css']
})

export class FeatureCardComponent implements OnInit, OnDestroy {
  
  numericalStats = [
    'Mean', 'Min', '1st_Quantile', '5th_Quantile', '25th_Q1', 
    '50th_Median', '75th_Q3', '95th_Quantile', '99th_Quantile', 
    'Max', 'Std', 'Skewness', 'Kurtosis'
  ];

  categoricalStats = [
    '#_of_Categories', 'Mode_Value', 'Mode_Ratio', 'Missing_Ratio', '#_of_Outlier_Categories'
  ];

  isBrowser: boolean;
  featureData: FeatureData | null = null;
  errorMessage: string | null = null;
  usePercentageYAxis: boolean = false;
  outlierCleaningEnabled: boolean = false;
  sparsityCleaningEnabled: boolean = false;
  stackedWrtTarget: boolean = false;
  public originalPlotSize = { width: 500, height: 300 };
  isFullScreen: boolean = false;
  private resizeListener: () => void;
  private resizeDebounce: any = null;
  isCategorical: boolean = false;
  tooltipPosition: 'above' | 'below' | 'left' | 'right' = 'above';
  private originalHistogramData: number[] | null = null;
  private originalStackedData: any | null = null;
  targetAverages: any[] | null = null;
  features: FeatureInfo[] = [];
  selectedFeatureName: string;
  catLabelLookup: { [feature: string]: { [encoded: string]: string } } = {};
  qualitySummary: { [key: string]: any } | null = null;
  // Preserve the initially provided quality row so the Quality tab is not empty on first open
  private initialQualitySummary: { [key: string]: any } | null = null;

  // Quality timeseries (supports dynamic windows like 1m/3m/6m)
  qualityTimeseries: any[] = [];
  qualityTimeseriesMetric: 'psi' | 'csi' | 'ks' | 'jsd' | 'wd' = 'psi';
  qualityTimeseriesLoading: boolean = false;
  qualityTimeseriesError: string | null = null;
  qualityTimeseriesOverall: number | null = null;
  // Controls
  selectedQualityWindows: number[] = [1, 3, 6];
  minBinShareAllowed: number = 0.05;
  // Legend handling for thresholds
  private qualityLegendHandlersAttached: boolean = false;
  private qualityThresholdTraceIndices: number[] = [];
  private qualityGraphDiv: any = null;
  showWindowCounts: boolean = true;
  private metricLockedByUser: boolean = false;
  // Cached dropdown options for current feature type
  metricOptions: Array<{ value: 'psi' | 'csi' | 'ks' | 'jsd' | 'wd', label: string }> = [];
  // Cached labels to avoid heavy template calls
  metricLabelText: string = 'PSI';
  qualityWindowsLabelText: string = '1m/3m/6m';
  // Modeling / Importance state
  modelingLoading: boolean = false;
  modelingError: string | null = null;
  modelInfo: any = null;
  importanceGain: Array<{ feature: string; score: number }> = [];
  importanceShap: Array<{ feature: string; score: number }> = [];
  selectedImportanceType: 'shap' | 'gain' = 'shap';
  importanceLimit: number = 20;
  importanceContext: string | null = null; // e.g. "SFS Forward Step 3"

  // SFS dual-context state (dropdown: Final Model Fit / Feature Added Step)
  sfsContexts: SfsImportanceContext[] = [];
  sfsViewMode: number = 0; // Index into sfsContexts (0 = Final Model, 1 = Step)
  hasSfsContexts: boolean = false;
  // True when opened before any model is trained (e.g. from Data Quality step)
  preModelingMode: boolean = false;

  // Explainability state
  explainabilityData: any = null;
  explainabilityLoading: boolean = false;
  explainabilityError: string | null = null;
  explainabilityFetched: boolean = false;  // Track if we've already fetched
  showNullsBeeswarm: boolean = false;  // Control showing null values in SHAP Beeswarm (Single Feature)
  beeswarmMissingRatio: number = 0;  // Missing ratio for current feature in beeswarm plot
  
  // Track current tab index (0=Descriptives, 1=Quality, 2=Importance, 3=Explainability)
  currentTabIndex: number = 0;

  // Data version dropdown state
  dataVersion: 'raw' | 'preprocessed' | 'encoded' = 'raw';
  dataVersionOptions: Array<{ value: 'raw' | 'preprocessed' | 'encoded'; label: string; disabled: boolean }> = [];
  
  constructor(
    @Inject(MAT_DIALOG_DATA) public data: FeatureCardDialogData,
    @Inject(PLATFORM_ID) platformId: Object,
    private dataService: DataService,
    public dialogRef: MatDialogRef<FeatureCardComponent>,
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
    this.resizeListener = () => {
      // Redraw charts on resize
      if (this.isBrowser) {
        if (this.resizeDebounce) clearTimeout(this.resizeDebounce);
        this.resizeDebounce = setTimeout(() => {
          this.createVisualization();
          this.drawQualityTimeseries();
          this.drawExplainabilityPlots();
        }, 200);
      }
    };
    this.features = data.features;
    this.selectedFeatureName = data.columnName;
    this.qualitySummary = data.qualitySummary || null;
    this.initialQualitySummary = data.qualitySummary || null;
    this.catLabelLookup = data.catLabelLookup || {};
    // Initialize data version options based on available files
    this.dataVersionOptions = [
      { value: 'raw', label: 'Raw', disabled: false },
      { value: 'preprocessed', label: 'Preprocessed', disabled: !data.processedFile },
      { value: 'encoded', label: 'Encoded/Scaled', disabled: !data.encodedFile },
    ];
    // Auto-select the most advanced available version
    if (data.encodedFile) {
      this.dataVersion = 'encoded';
    } else if (data.processedFile) {
      this.dataVersion = 'preprocessed';
    }
    // SFS dual-context mode: dropdown between Final Model Fit / Feature Added Step
    if (data.sfsContexts && data.sfsContexts.length > 0) {
      this.sfsContexts = data.sfsContexts;
      this.hasSfsContexts = true;
      this.sfsViewMode = 0; // Default to first context (Final Model)
      const ctx = this.sfsContexts[0];
      this.importanceGain = ctx.gain || [];
      this.importanceShap = ctx.shap || [];
      this.importanceContext = ctx.label || null;
      if (this.importanceShap.length) this.selectedImportanceType = 'shap';
      else if (this.importanceGain.length) this.selectedImportanceType = 'gain';
    } else if (data.importanceOverrides) {
      // Legacy single-context mode (backward compat)
      this.importanceGain = data.importanceOverrides.gain || [];
      this.importanceShap = data.importanceOverrides.shap || [];
      if (this.importanceShap.length) this.selectedImportanceType = 'shap';
      else if (this.importanceGain.length) this.selectedImportanceType = 'gain';
      this.importanceContext = data.importanceContext || null;
    } else {
      this.importanceContext = data.importanceContext || null;
      // No importance data provided — opened before modeling (e.g. Data Quality step)
      this.preModelingMode = true;
    }
  }

  /**
   * Switch SFS view mode (dropdown changed) — updates importance data and resets explainability.
   */
  onSfsViewModeChange(index: number): void {
    if (index < 0 || index >= this.sfsContexts.length) return;
    this.sfsViewMode = index;
    const ctx = this.sfsContexts[index];
    this.importanceGain = ctx.gain || [];
    this.importanceShap = ctx.shap || [];
    this.importanceContext = ctx.label || null;
    if (this.importanceShap.length) this.selectedImportanceType = 'shap';
    else if (this.importanceGain.length) this.selectedImportanceType = 'gain';
    // Redraw importance plot if the Importance tab is active
    if (this.currentTabIndex === 2) {
      setTimeout(() => this.drawImportancePlot(), 0);
    }
    // Reset explainability so it re-fetches with the new context
    this.explainabilityData = null;
    this.explainabilityFetched = false;
    this.explainabilityError = null;
    // If the Explainability tab is active, fetch immediately
    if (this.currentTabIndex === 3) {
      this.fetchFeatureExplainability();
    }
  }

  // Robust description getter for dropdown display
  getFeatureDescription(featureName: string): string {
    try {
      const f: any = this.features.find(x => x.Feature_Name === featureName);
      const desc = f?.Feature_Description ?? f?.Description ?? f?.description ?? f?.Variable_Description;
      const s = desc != null ? String(desc).trim() : '';
      return s !== '' ? s : 'No description available';
    } catch { return 'No description available'; }
  }

  onMetricChange(metric: 'psi' | 'csi' | 'ks' | 'jsd' | 'wd') {
    this.metricLockedByUser = true;
    this.qualityTimeseriesMetric = metric;
    this.metricLabelText = this.computeMetricLabel();
    // Force re-attachment of legend handlers on next draw
    this.qualityLegendHandlersAttached = false;
    this.fetchQualityTimeseries();
  }

  private computeMetricLabel(): string {
    switch (this.qualityTimeseriesMetric) {
      case 'psi': return 'PSI';
      case 'csi': return 'CSI';
      case 'ks': return 'KS';
      case 'jsd': return 'JSD';
      case 'wd': return 'Wasserstein';
      default: return String(this.qualityTimeseriesMetric).toUpperCase();
    }
  }

  // ===== Modeling / Importance =====
  private _applyModelingResponse(resp: any): void {
    this.modelInfo = resp?.model || null;
    const imps = this.modelInfo?.importances || {};
    this.importanceGain = Array.isArray(imps.gain) ? imps.gain : [];
    this.importanceShap = Array.isArray(imps.shap_mean_abs) ? imps.shap_mean_abs : [];
    if (this.importanceShap.length) this.selectedImportanceType = 'shap';
    else if (this.importanceGain.length) this.selectedImportanceType = 'gain';
    this.drawImportancePlot();
  }

  proceedModeling(): void {
    try {
      if (!this.isBrowser) return;
      this.modelingError = null;
      const fid = Number(this.data.fileId);
      if (!isFinite(fid)) {
        this.modelingError = 'Invalid file id';
        return;
      }
      this.modelingLoading = true;

      // 1) Try cached results first (instant — no re-training)
      this.dataService.getModelingStatus(fid).subscribe({
        next: (cached: any) => {
          if (cached?.job_status === 'completed' && cached?.model?.importances) {
            console.log('[FeatureCard] Using cached modeling results');
            this._applyModelingResponse(cached);
            this.modelingLoading = false;
            return;
          }
          // 2) No cache — fall back to full training
          this._runFullModeling(fid);
        },
        error: () => {
          // Status endpoint failed — fall back to full training
          this._runFullModeling(fid);
        }
      });
    } catch (e) {
      console.warn('proceedModeling failed:', e);
      this.modelingError = 'Failed to start modelling';
      this.modelingLoading = false;
    }
  }

  private _runFullModeling(fid: number): void {
    if (!this.data.processedFile) {
      this.modelingError = 'Processed file is required to start modelling.';
      this.modelingLoading = false;
      return;
    }
    this.dataService.startModeling(fid, this.data.processedFile, 'xgboost').subscribe({
      next: (resp: any) => {
        this._applyModelingResponse(resp);
      },
      error: (err: any) => {
        console.error('Modeling failed:', err);
        this.modelingError = 'Failed to run modelling';
      },
      complete: () => {
        this.modelingLoading = false;
      }
    });
  }

  onImportanceTypeChange(t: 'shap' | 'gain') {
    this.selectedImportanceType = t;
    this.drawImportancePlot();
  }

  drawImportancePlot(): void {
    try {
      if (!this.isBrowser) return;
      const Plotly = (window as any).Plotly;
      if (!Plotly) return;
      const el = document.getElementById('importance-plot');
      if (!el) return;

      const items = (this.selectedImportanceType === 'shap') ? this.importanceShap : this.importanceGain;
      if (!Array.isArray(items) || items.length === 0) {
        (el as any).innerHTML = '<div style="color:#777; font-size:12px;">No importances available.</div>';
        return;
      }
      const sorted = [...items].sort((a, b) => (b.score - a.score));
      const top = sorted.slice(0, Math.max(5, Math.min(100, this.importanceLimit || 20)));
      const y = top.map(d => d.feature).reverse();
      const x = top.map(d => d.score).reverse();
      const title = this.selectedImportanceType === 'shap' ? 'SHAP mean |impact|' : 'XGBoost gain';

      // Highlight the selected feature
      const selFeat = this.selectedFeatureName;
      const barColors = y.map(f => f === selFeat ? '#C02942' : '#4E79A7');

      const trace = {
        x,
        y,
        type: 'bar',
        orientation: 'h',
        marker: { color: barColors },
        hovertemplate: '%{y}: %{x:.6f}<extra></extra>'
      } as any;

      // Annotation arrow pointing to the selected feature bar
      const annotations: any[] = [];
      const selIdx = y.indexOf(selFeat);
      if (selIdx >= 0) {
        annotations.push({
          x: x[selIdx], y: y[selIdx],
          xanchor: 'left', yanchor: 'middle',
          text: ` ← ${selFeat}`,
          showarrow: false,
          font: { size: 11, color: '#C02942', weight: 'bold' }
        });
      }

      const layout = {
        margin: { l: 180, r: 24, t: 36, b: 36 },
        height: Math.max(320, 28 * top.length + 120),
        title: { text: title, font: { size: 14 } },
        xaxis: { title: 'Score' },
        yaxis: { automargin: true },
        showlegend: false,
        annotations
      } as any;
      const config = { responsive: true, displayModeBar: false } as any;
      try { (window as any).Plotly.react(el, [trace], layout, config); }
      catch { Plotly.newPlot(el, [trace], layout, config); }
    } catch (e) {
      console.warn('drawImportancePlot failed:', e);
    }
  }

  /**
   * Get the selected feature's rank and score for a given importance type
   */
  getFeatureImportanceRank(type: 'gain' | 'shap'): { rank: number; score: number; total: number } | null {
    const items = type === 'shap' ? this.importanceShap : this.importanceGain;
    if (!Array.isArray(items) || items.length === 0) return null;
    const sorted = [...items].sort((a, b) => b.score - a.score);
    const idx = sorted.findIndex(d => d.feature === this.selectedFeatureName);
    if (idx < 0) return null;
    return { rank: idx + 1, score: sorted[idx].score, total: sorted.length };
  }

  // Determine if current feature is numerical
  isNumerical(): boolean {
    const lom = this.featureData?.Level_of_Measurement;
    return lom === 'continuous' || lom === 'cardinal';
  }

  /**
   * Return the list of metrics available for the currently selected feature type.
   * - Numerical: PSI, KS, JSD, Wasserstein
   * - Categorical: CSI, JSD
   */
  availableMetrics(): Array<{ value: 'psi' | 'csi' | 'ks' | 'jsd' | 'wd', label: string }> {
    if (this.isNumerical()) {
      return [
        { value: 'psi', label: 'Population Stability Index (PSI)' },
        { value: 'ks', label: 'Kolmogorov-Smirnov (KS)' },
        { value: 'jsd', label: 'Jensen-Shannon Divergence (JSD)' },
        { value: 'wd', label: 'Wasserstein Distance' },
      ];
    }
    // Categorical by default
    return [
      { value: 'csi', label: 'Characteristic Stability Index (CSI)' },
      { value: 'jsd', label: 'Jensen-Shannon Divergence (JSD)' },
    ];
  }

  /** Default metric for the current feature type */
  private defaultMetricForFeature(): 'psi' | 'csi' | 'ks' | 'jsd' | 'wd' {
    return this.isNumerical() ? 'psi' : 'csi';
  }

  /** Refresh cached options according to current feature type */
  private refreshMetricOptions(): void {
    this.metricOptions = this.availableMetrics();
  }

  private computeQualityWindowsLabel(): string {
    try {
      return [...this.selectedQualityWindows].sort((a,b)=>a-b).map(w => `${w}m`).join('/');
    } catch { return '3m/6m'; }
  }

  // Magnitude categories per metric (heuristics for non-PSI/CSI)
  // Returns two thresholds for the three bands: low < T1, T1..T2 mid, >= T2 high
  private metricThresholds(metric: 'psi' | 'csi' | 'ks' | 'jsd' | 'wd'):
    Array<{ y: number; band: 'low' | 'high'; color: string; dash?: 'dash' | 'dot' | 'dashdot' }>
  {
    // PSI/CSI: industry convention
    if (metric === 'psi' || metric === 'csi') {
      return [
        { y: 0.10, band: 'low', color: '#388e3c', dash: 'dot' },
        { y: 0.25, band: 'high', color: '#d32f2f', dash: 'dash' },
      ];
    }
    // KS: common guidance — <0.10 small, 0.10–0.20 moderate, >0.20 strong
    if (metric === 'ks') {
      return [
        { y: 0.10, band: 'low', color: '#388e3c', dash: 'dot' },
        { y: 0.20, band: 'high', color: '#d32f2f', dash: 'dash' },
      ];
    }
    // JSD (base 2): heuristic bands — <0.10 low, 0.10–0.30 medium, ≥0.30 high
    if (metric === 'jsd') {
      return [
        { y: 0.10, band: 'low', color: '#388e3c', dash: 'dot' },
        { y: 0.30, band: 'high', color: '#d32f2f', dash: 'dash' },
      ];
    }
    // Wasserstein (normalized): heuristic — <0.10 low, 0.10–0.30 medium, ≥0.30 high
    if (metric === 'wd') {
      return [
        { y: 0.10, band: 'low', color: '#388e3c', dash: 'dot' },
        { y: 0.30, band: 'high', color: '#d32f2f', dash: 'dash' },
      ];
    }
    return [];
  }

  toggleQualityWindow(w: number, checked: boolean): void {
    const set = new Set(this.selectedQualityWindows);
    if (checked) set.add(w); else set.delete(w);
    this.selectedQualityWindows = Array.from(set).sort((a,b)=>a-b);
    this.qualityWindowsLabelText = this.computeQualityWindowsLabel();
    // Redraw immediately for responsiveness
    this.drawQualityTimeseries();
    this.fetchQualityTimeseries();
  }

  onMinBinShareChange(val: any): void {
    const n = Number(val);
    if (!isFinite(n) || isNaN(n)) return;
    const clamped = Math.max(0, Math.min(0.5, n));
    this.minBinShareAllowed = clamped;
    this.fetchQualityTimeseries();
  }

  // Fetch quality summary row from backend when not available locally
  fetchQualitySummaryRow(): void {
    const fid = Number(this.data.fileId);
    if (!isFinite(fid)) return;
    this.dataService.getDatqSummaryRow(fid, this.selectedFeatureName || this.data.columnName).subscribe({
      next: (resp: any) => {
        if (resp?.row) {
          this.qualitySummary = resp.row;
          this.initialQualitySummary = resp.row;
          this.fetchQualityTimeseries();
        }
      },
      error: () => { /* Quality stays as placeholder */ }
    });
  }

  // Quality helpers
  hasQuality(): boolean {
    const q = this.qualitySummary ?? this.initialQualitySummary;
    return !!q && Object.keys(q).length > 0;
  }

  qualityPairs(): Array<{ key: string, value: any }> {
    const src = this.qualitySummary ?? this.initialQualitySummary;
    if (!src) return [];
    const entries = Object.entries(src);
    const preferred = ['Variable', 'variable', 'index', 'Datq_Decision', 'Variable_Type', 'PSI', 'CSI', 'KS', 'JSD', 'Wasserstein'];
    const score = (k: string) => {
      const i = preferred.indexOf(k);
      return i === -1 ? 1000 : i;
    };
    entries.sort((a, b) => score(a[0]) - score(b[0]));
    return entries.map(([key, value]) => ({ key, value }));
  }

  ngOnInit() {
    this.loadFeatureData();
    if (this.isBrowser) {
      this.loadPlotly().then(() => {
        window.addEventListener('resize', this.resizeListener);
        // Once Plotly is available, attempt to draw quality timeseries
        this.fetchQualityTimeseries();
      }).catch(error => {
        console.error('Error loading Plotly:', error);
        this.errorMessage = 'An error occurred while loading the visualization library. Please try again.';
      });
    }
  }

  ngOnDestroy() {
    if (this.isBrowser) {
      window.removeEventListener('resize', this.resizeListener);
    }
  }

  onFeatureChange() {
    const prev = this.data.columnName;
    const changed = String(this.selectedFeatureName) !== String(prev);
    this.data.columnName = this.selectedFeatureName;
    this.loadFeatureData();
    // We only have quality for the initially clicked feature from Data Quality summary.
    // Clear quality panel ONLY if the user actually changed the feature selection.
    if (changed) {
      this.qualitySummary = null;
      this.initialQualitySummary = null;
      // Reset explainability data so it reloads for new feature
      this.explainabilityData = null;
      this.explainabilityFetched = false;
      this.explainabilityError = null;
      
      // If user is currently on Quality tab, fetch quality for new feature
      if (this.currentTabIndex === 1) {
        this.fetchQualitySummaryRow();
      }
      // If user is currently on Explainability tab, trigger fetch immediately
      if (this.currentTabIndex === 3) {
        this.fetchFeatureExplainability();
      }
    }
    // Refresh timeseries for the newly selected variable
    // Reset metric lock so we can apply proper default per feature type
    this.metricLockedByUser = false;
    // Ensure selected metric is valid for new feature type
    this.refreshMetricOptions();
    const allowed = new Set(this.metricOptions.map(m => m.value));
    if (!allowed.has(this.qualityTimeseriesMetric)) {
      this.qualityTimeseriesMetric = this.defaultMetricForFeature();
      this.metricLabelText = this.computeMetricLabel();
    }
    this.fetchQualityTimeseries();
  }
  
  getFileOverride(): string | undefined {
    if (this.dataVersion === 'preprocessed' && this.data.processedFile) return this.data.processedFile;
    if (this.dataVersion === 'encoded' && this.data.encodedFile) return this.data.encodedFile;
    return undefined;
  }

  onDataVersionChange(version: 'raw' | 'preprocessed' | 'encoded'): void {
    this.dataVersion = version;
    this.originalHistogramData = null;
    this.originalStackedData = null;
    this.targetAverages = null;
    this.stackedWrtTarget = false;
    this.loadFeatureData();
    // Refresh Quality tab data for the new data version
    this.qualitySummary = null;
    this.initialQualitySummary = null;
    this.qualityTimeseries = [];
    this.qualityTimeseriesOverall = null;
    this.metricLockedByUser = false;
    if (this.currentTabIndex === 1) {
      this.fetchQualitySummaryRow();
    }
  }

  loadFeatureData() {
    const fileOverride = this.getFileOverride();
    console.log(`Loading feature data for fileId: ${this.data.fileId}, columnName: ${this.data.columnName}, version: ${this.dataVersion}`);
    forkJoin({
      featureCard: this.dataService.getFeatureCard(this.data.fileId, this.data.columnName, fileOverride),
      stackedData: this.dataService.getStackedFeatureData(this.data.fileId, this.data.columnName, fileOverride)
    }).subscribe({
      next: ({ featureCard, stackedData: stackedResp }) => {
        this.featureData = featureCard;
        if (this.featureData) {
          // Extract stacked_data and target_averages from response
          const stackedData = stackedResp?.stacked_data ?? stackedResp;
          this.targetAverages = stackedResp?.target_averages ?? null;

          // Store the original histogram data
          this.originalHistogramData = this.featureData.Descriptive_Stats['histogram_data'] as number[] || null;
          this.originalStackedData = this.preprocessStackedData(stackedData);
          this.isCategorical = this.featureData.Level_of_Measurement === 'nominal' || this.featureData.Level_of_Measurement === 'ordinal';
          this.refreshMetricOptions();
          // Ensure metric consistency with detected feature type if user hasn't explicitly chosen
          if (!this.metricLockedByUser) {
            const allowed = new Set(this.metricOptions.map(m => m.value));
            if (!allowed.has(this.qualityTimeseriesMetric)) {
              this.qualityTimeseriesMetric = this.defaultMetricForFeature();
            }
          }
          // Update cached labels
          this.metricLabelText = this.computeMetricLabel();
          this.qualityWindowsLabelText = this.computeQualityWindowsLabel();
          
          // Disable cleaning options for categorical data
          if (this.isCategorical) {
            this.outlierCleaningEnabled = false;
            this.sparsityCleaningEnabled = false;
          }
          
          // Process stacked data
          this.featureData.Target_Classes = Object.keys(stackedData);
          this.featureData.Stacked_Stats = {};
          
          for (const targetClass of this.featureData.Target_Classes) {
            const classData = stackedData[targetClass];
            if (this.featureData.Stacked_Stats) {
              this.featureData.Stacked_Stats[targetClass] = this.calculateDescriptiveStats(classData);
            }
          }
  
          // If Descriptive_Stats is not calculated by the backend, calculate it here
          if (!this.featureData.Descriptive_Stats || Object.keys(this.featureData.Descriptive_Stats).length === 0) {
            const rawData = this.featureData['histogram_data'] || [];
            this.featureData.Descriptive_Stats = this.calculateDescriptiveStats(rawData);
          }
        }
        
        if (this.isBrowser) {
          this.loadPlotly().then(() => {
            setTimeout(() => {
              this.createVisualization();
            }, 0);
          });
        }
      },

      error: (error: HttpErrorResponse) => {
        console.error('Error loading feature data:', error);
        // If the encoded version 404s (column missing from encoded file), fallback to preprocessed
        if (error.status === 404 && this.dataVersion === 'encoded' && this.data.processedFile) {
          console.warn(`[FeatureCard] Column '${this.data.columnName}' not found in encoded file, falling back to preprocessed`);
          this.dataVersion = 'preprocessed';
          this.loadFeatureData();
          return;
        }
        if (error.status === 404) {
          this.errorMessage = `File or column not found. Please check the fileId (${this.data.fileId}) and columnName (${this.data.columnName}).`;
        } else {
          this.errorMessage = 'An error occurred while loading the feature data. Please try again.';
        }
      }
    });
  }

  async loadPlotly(): Promise<void> {
    if (!(window as any).Plotly) {
      try {
        const Plotly = await import('plotly.js-dist-min');
        (window as any).Plotly = Plotly.default;
      } catch (error: unknown) {
        console.error('Error loading Plotly:', error);
        if (error instanceof Error) {
          this.errorMessage = `An error occurred while loading the visualization library: ${error.message}. Please try again.`;
        } else {
          this.errorMessage = 'An unknown error occurred while loading the visualization library. Please try again.';
        }
        throw error;
      }
    }
  }

  createVisualization(data?: any) {
    console.log('Creating visualization with data:', data);
    if (!this.featureData || !this.featureData.Descriptive_Stats) {
      console.error('No feature data available for visualization');
      this.errorMessage = 'No data available for visualization';
      return;
    }

    const histogramData = this.featureData.Descriptive_Stats['histogram_data'];
    const valueCounts = this.featureData.Descriptive_Stats['value_counts'];

    if (!histogramData && !valueCounts) {
      console.error('No histogram or value counts data available for visualization');
      this.errorMessage = 'No suitable data available for visualization';
      return;
    }

    console.log('Histogram data for visualization:', histogramData);

    const Plotly = (window as any).Plotly;
    if (!Plotly) {
      console.error('Plotly is not loaded');
      return;
    }

    const plotElement = document.getElementById('visualization');
    if (!plotElement) {
      console.error('Visualization element not found');
      return;
    }

    const layout: any = {
      title: `Distribution of ${this.featureData.Feature_Name}`,
      xaxis: { 
        title: this.isNumerical() ? `Values of ${this.featureData.Feature_Name}` : 'Categories',
        domain: [0, 1]  // Full width for x-axis
      },
      yaxis: {
        title: this.usePercentageYAxis ? 'Percentage' : 'Count',
        domain: [0, 0.85]
      },
      yaxis2: {
        domain: [0.87, 1],
        showticklabels: false,
        zeroline: false,
        showgrid: false,
        title: ''
      },
      height: this.isFullScreen ? window.innerHeight * 0.40 : this.originalPlotSize.height,
      width: this.isFullScreen ? window.innerWidth * 0.90 : this.originalPlotSize.width,
      showlegend: true,
      legend: {
        title: this.stackedWrtTarget ? { text: 'Target Classes' } : undefined,
        traceorder: 'normal'
      },
      // Add margin to accommodate the box plot
      margin: { t: 50, b: 50, l: 50, r: 50 },
      colorway: this.stackedWrtTarget 
        ? ['#740505', '#a34203', '#d28100', '#f7b538'] // Complementary colors for stacked
        : ['#740505'], // Single maroon color for non-stacked
      plot_bgcolor: 'rgba(0,0,0,0)',
      paper_bgcolor: 'rgba(0,0,0,0)',
    };
  
    if (this.stackedWrtTarget) {
      const stackedData = data || this.processStackedData(this.originalStackedData);
      if (Object.keys(stackedData).length === 0) {
        console.error('No stacked data available for visualization');
        this.errorMessage = 'No stacked data available for visualization';
        return;
      }
      this.plotStackedData(stackedData, layout);
    } else {
      if (this.isNumerical()) {
        const histogramData = data || this.cleanData(this.originalHistogramData || []);
        if (histogramData.length === 0) {
          console.error('No histogram data available for visualization');
          this.errorMessage = 'No data available for visualization';
          return;
        }
        this.plotNonStackedData(histogramData, layout);
      } else {
        // For categorical data
        if (valueCounts && Object.keys(valueCounts).length > 0) {
          this.plotCategoricalData(valueCounts, layout);
        } else {
          console.error('No value counts data available for categorical visualization');
          this.errorMessage = 'No data available for categorical visualization';
          return;
        }
      }
    }
  }

  // ===== Quality timeseries (3m/6m rolling PSI/CSI) =====
  private inferQualityMetric(): 'psi' | 'csi' | 'ks' | 'jsd' | 'wd' {
    try {
      // 1) Prefer explicit summary keys (ensures consistency with Data Quality table)
      const qs = this.qualitySummary ?? this.initialQualitySummary;
      if (qs && (qs['PSI'] !== undefined || qs['psi'] !== undefined)) return 'psi';
      if (qs && (qs['CSI'] !== undefined || qs['csi'] !== undefined)) return 'csi';
      // 2) If feature type known, choose type default
      if (this.featureData) return this.defaultMetricForFeature();
      // 3) Safe fallback to PSI to avoid unexpected CSI on numerics before feature loads
      return 'psi';
    } catch { return 'psi'; }
  }

  fetchQualityTimeseries(): void {
    try {
      if (!this.isBrowser) return;
      // Use the data-version-appropriate file for quality computation
      const qualityFile = this.getFileOverride() || this.data.processedFile;
      if (!qualityFile || !this.data.dateColumn) {
        this.qualityTimeseriesError = 'Date column or processed file not available for timeseries.';
        return;
      }
      const fid = Number(this.data.fileId);
      if (!isFinite(fid)) {
        this.qualityTimeseriesError = 'Invalid file id';
        return;
      }
      if (!this.metricLockedByUser) {
        this.qualityTimeseriesMetric = this.inferQualityMetric();
        this.metricLabelText = this.computeMetricLabel();
      }
      this.qualityTimeseriesLoading = true;
      this.qualityTimeseriesError = null;
      this.dataService.getDatqTimeseries(
        fid,
        qualityFile,
        this.selectedFeatureName || this.data.columnName,
        this.data.dateColumn,
        this.qualityTimeseriesMetric,
        this.selectedQualityWindows,
        this.minBinShareAllowed
      ).subscribe({
        next: (resp: any) => {
          const series = Array.isArray(resp?.series) ? resp.series : [];
          this.qualityTimeseries = series;
          // Prefer the PSI/CSI value from the qualitySummary row to ensure exact match with the summary table
          let overallFromSummary: number | null = null;
          try {
            const qs = this.qualitySummary ?? this.initialQualitySummary;
            if (qs) {
              const metric = this.qualityTimeseriesMetric;
              let key: string | null = null;
              if (metric === 'psi') key = ('PSI' in qs) ? 'PSI' : (('psi' in qs) ? 'psi' : null);
              else if (metric === 'csi') key = ('CSI' in qs) ? 'CSI' : (('csi' in qs) ? 'csi' : null);
              else if (metric === 'ks') key = 'KS';
              else if (metric === 'jsd') key = 'JSD';
              else if (metric === 'wd') key = 'Wasserstein';
              if (key) {
                const v = (qs as any)[key];
                const n = Number(v);
                overallFromSummary = (isFinite(n) && !isNaN(n)) ? n : null;
              }
            }
          } catch {}
          const overallFromApi = (resp && resp.overall != null && resp.overall !== '') ? Number(resp.overall) : null;
          // For non-preprocessed data versions, prefer the API-computed overall
          // because the pre-saved summary was computed on preprocessed data only.
          if (this.dataVersion !== 'preprocessed') {
            this.qualityTimeseriesOverall = (overallFromApi != null) ? overallFromApi : overallFromSummary;
          } else {
            this.qualityTimeseriesOverall = (overallFromSummary != null) ? overallFromSummary : overallFromApi;
          }
          this.drawQualityTimeseries();
        },
        error: (err: any) => {
          console.error('Failed to fetch quality timeseries:', err);
          this.qualityTimeseriesError = 'Failed to fetch timeseries';
        },
        complete: () => { this.qualityTimeseriesLoading = false; }
      });
    } catch (e) {
      console.warn('fetchQualityTimeseries failed:', e);
      this.qualityTimeseriesError = 'Failed to compute timeseries';
      this.qualityTimeseriesLoading = false;
    }
  }

  drawQualityTimeseries(): void {
    try {
      if (!this.isBrowser) return;
      const Plotly = (window as any).Plotly;
      if (!Plotly) return;
      const el = document.getElementById('quality-timeseries');
      if (!el) {
        // Tab content may be lazy-rendered; retry shortly after activation
        setTimeout(() => this.drawQualityTimeseries(), 250);
        return;
      }
      const series = Array.isArray(this.qualityTimeseries) ? this.qualityTimeseries : [];
      const x = series.map((r: any) => r?.month || null).filter((v: any) => v != null);
      const traces: any[] = [];
      // add rolling windows dynamically
      const windowStyles: {[w: number]: {color: string; dash?: string}} = {
        1: { color: '#388e3c' },
        3: { color: '#1976d2' },
        6: { color: '#d32f2f', dash: 'dot' },
      };
      let hasAnyRolling = false;
      for (const w of this.selectedQualityWindows.sort((a,b)=>a-b)) {
        const prefix = (this.qualityTimeseriesMetric === 'psi' || this.qualityTimeseriesMetric === 'csi') ? 'psi' : this.qualityTimeseriesMetric;
        const key = `${prefix}_${w}m`;
        const y = series.map((r: any) => (r && r[key] != null ? Number(r[key]) : null));
        const has = y.some(v => v != null);
        if (has) {
          hasAnyRolling = true;
          const st = windowStyles[w] || { color: '#455a64' };
          traces.push({
            x,
            y,
            mode: 'lines+markers',
            name: `${w}-month ${this.metricLabelText} rolling`,
            line: { color: st.color, width: 2, ...(st.dash ? { dash: st.dash } : {}) },
            connectgaps: false
          });
          if (this.showWindowCounts) {
            const nkey = `n_${w}m`;
            const ny = series.map((r: any) => (r && r[nkey] != null ? Number(r[nkey]) : null));
            const baseColor = st.color;
            traces.push({
              x,
              y: ny,
              type: 'bar',
              name: `${w}m N`,
              yaxis: 'y2',
              opacity: 0.25,
              marker: { color: baseColor },
              hovertemplate: `${w}m N: %{y}<extra></extra>`
            });
          }
        }
      }
      if (!hasAnyRolling && this.qualityTimeseriesOverall == null) {
        (el as any).innerHTML = '<div style="color:#777; font-size:12px;">No series available.</div>';
        return;
      }
      if (this.qualityTimeseriesOverall != null && x.length) {
        traces.push({
          x,
          y: x.map(() => this.qualityTimeseriesOverall as number),
          mode: 'lines',
          name: `overall ${this.metricLabelText}`,
          line: { color: '#455a64', width: 2, dash: 'dash' },
          hovertemplate: `Overall ${this.metricLabelText}: %{y:.6f}<extra></extra>`
        });
      }
      const layout: any = {
        margin: { t: 24, r: 64, b: 100, l: 56 },
        height: this.isFullScreen ? Math.floor(window.innerHeight * 0.50) : 560,
        width: this.isFullScreen ? Math.floor(window.innerWidth * 0.85) : undefined,
        xaxis: { title: 'Month' },
        yaxis: { title: { text: `Rolling ${this.metricLabelText} (${this.qualityWindowsLabelText})`, standoff: 12 }, tickformat: '.6f', automargin: true, rangemode: 'tozero' },
        yaxis2: { title: { text: 'N (test)', standoff: 12 }, overlaying: 'y', side: 'right', rangemode: 'tozero', automargin: true },
        showlegend: true,
        legend: { orientation: 'h', y: -0.3, x: 0.5, xanchor: 'center', itemclick: 'toggle', itemdoubleclick: 'toggleothers' }
      };

      // Reset threshold trace indices before adding new ones
      this.qualityThresholdTraceIndices = [];
      // Add magnitude guidance using line traces (appear in legend) and concise annotations
      const guides = this.metricThresholds(this.qualityTimeseriesMetric);
      if (guides && guides.length) {
        const xGuide = x.length >= 2 ? [x[0], x[x.length - 1]] : (x.length === 1 ? [x[0], x[0]] : ['0','1']);
        // low and high threshold lines
        for (const g of guides) {
          traces.push({
            x: xGuide,
            y: [g.y, g.y],
            mode: 'lines',
            name: g.band, // legend label: low or high
            line: { color: g.color, width: 2, dash: g.dash || 'dash' },
            hoverinfo: 'skip',
            meta: { threshold: true, band: g.band }
          });
          this.qualityThresholdTraceIndices.push(traces.length - 1);
        }
        // Add a legend-only entry for mid band
        traces.push({
          x: xGuide,
          y: [null, null],
          mode: 'lines',
          name: 'mid',
          line: { color: '#9e9e9e', width: 1.5, dash: 'dashdot' },
          visible: 'legendonly',
          hoverinfo: 'skip'
        });
        // concise annotations at right edge
        layout.annotations = (layout.annotations || []).concat(
          guides.map(g => ({
            xref: 'paper', x: 1.005, xanchor: 'left',
            yref: 'y', y: g.y,
            text: g.band,
            showarrow: false,
            font: { size: 10, color: g.color },
            align: 'left'
          }))
        );
        // shapes removed; rely on trace-only for legend-driven on/off behavior
      }
      const gd: any = document.getElementById('quality-timeseries');
      try { (gd as any).style.pointerEvents = 'auto'; } catch {}
      // If graph div changed (e.g., metric switched), allow reattaching handlers
      if (this.qualityGraphDiv !== gd) {
        this.qualityLegendHandlersAttached = false;
        this.qualityGraphDiv = gd;
      }
      const config = { responsive: true, displayModeBar: false, staticPlot: false } as any;
      // Purge any previous plot to ensure clean listeners/state across metric switches
      try { (window as any).Plotly.purge(gd); } catch {}
      Plotly.newPlot(gd, traces, layout, config).then(() => {
        this.attachQualityLegendHandlers(gd);
        // Ensure annotations match visibility on first render
        this.updateThresholdAnnotationsFromVisibility(gd);
        // Let Plotly compute initial autorange and then apply robust rescale
        (window as any).Plotly.relayout(gd, { 'yaxis.autorange': true, 'yaxis2.autorange': true }).then(() => {
          this.recomputeYAxisFromVisible(gd);
        });
      });
    } catch (e) {
      console.warn('drawQualityTimeseries failed:', e);
    }
  }

  private attachQualityLegendHandlers(gd: any): void {
    try {
      if (this.qualityLegendHandlersAttached || !gd || !gd.on) return;
      const refresh = () => {
        try {
          this.updateThresholdAnnotationsFromVisibility(gd);
          // Trigger autorange based on current visibility after legend toggle
          (window as any).Plotly.relayout(gd, { 'yaxis.autorange': true, 'yaxis2.autorange': true }).then(() => {
            this.recomputeYAxisFromVisible(gd);
          });
        } catch {}
      };
      const schedule = () => { setTimeout(refresh, 0); setTimeout(refresh, 80); };
      // Manually handle legend clicks only for threshold traces (low/high).
      // For all other traces, let Plotly perform its default toggling.
      gd.on('plotly_legendclick', (eventData: any) => {
        const curveNumber = eventData.curveNumber;
        const trace = gd.data[curveNumber];
        if (!trace) return false; // Should not happen
        const nm = String(trace.name || '').toLowerCase();
        if (nm === 'low' || nm === 'high') {
          const currentlyVisible = trace.visible !== 'legendonly' && trace.visible !== false;
          const newVisibility = currentlyVisible ? 'legendonly' : true;
          Plotly.restyle(gd, { visible: newVisibility }, [curveNumber]).then(() => {
            schedule();
          });
          return false; // prevent default only for thresholds
        }
        setTimeout(schedule, 0);
        return true; // allow default for non-threshold traces
      });

      gd.on('plotly_legenddoubleclick', (eventData: any) => {
        const curveNumber = eventData.curveNumber;
        const trace = gd.data[curveNumber];
        if (!trace) return false;
        const nm = String(trace.name || '').toLowerCase();
        if (nm === 'low' || nm === 'high') {
          const traceCount = gd.data.length;
          const newVisibilities = Array(traceCount).fill('legendonly');
          newVisibilities[curveNumber] = true;
          Plotly.restyle(gd, { visible: newVisibilities }).then(() => {
            schedule();
          });
          return false; // prevent default only for thresholds
        }
        setTimeout(schedule, 0);
        return true; // allow default for non-threshold traces
      });

      // Also listen to restyle to catch other visibility changes
      gd.on('plotly_restyle', schedule);
      this.qualityLegendHandlersAttached = true;
    } catch {}
  }

  private updateThresholdAnnotationsFromVisibility(gd: any): void {
    try {
      if (!gd) return;
      const guides = this.metricThresholds(this.qualityTimeseriesMetric);
      if (!guides || guides.length === 0) {
        (window as any).Plotly.relayout(gd, { annotations: [], shapes: [] });
        return;
      }
      const visibleBands = new Set<string>();
      // evaluate visibility by scanning traces with names 'low'/'high'
      let foundThresholdTraces = false;
      for (const t of gd.data || []) {
        if (!t || !t.name) continue;
        const nm = String(t.name);
        if (nm !== 'low' && nm !== 'high') continue;
        foundThresholdTraces = true;
        if (t.visible === false || t.visible === 'legendonly') continue;
        visibleBands.add(nm);
      }
      if (!foundThresholdTraces) {
        // Fallback: if traces not present (e.g., filtered by Plotly), assume both visible
        visibleBands.add('low');
        visibleBands.add('high');
      }
      const ann = guides
        .filter(g => visibleBands.has(g.band))
        .map(g => ({
          xref: 'paper', x: 1.005, xanchor: 'left',
          yref: 'y', y: g.y,
          text: g.band,
          showarrow: false,
          font: { size: 10, color: g.color },
          align: 'left'
        }));
      (window as any).Plotly.relayout(gd, { annotations: ann, shapes: [] });
    } catch {}
  }

  // Robust rescaling after legend toggles: compute range from visible non-threshold traces
  private recomputeYAxisFromVisible(gd: any): void {
    try {
      const Plotly = (window as any).Plotly;
      if (!gd || !Plotly) return;
      const data = Array.isArray(gd.data) ? gd.data : [];
      let ymin = Number.POSITIVE_INFINITY;
      let ymax = Number.NEGATIVE_INFINITY;
      let found = false;
      for (const t of data) {
        if (!t) continue;
        const nm = String(t.name || '').toLowerCase();
        // skip only the legend-only helper trace 'mid'
        if (nm === 'mid') continue;
        const axis = t.yaxis || 'y';
        if (axis !== 'y' && axis !== 'y1') continue; // ignore y2 (counts)
        const vis = t.visible;
        if (vis === 'legendonly' || vis === false) continue;
        const ys: any[] = Array.isArray(t.y) ? t.y : [];
        for (const v of ys) {
          const n = Number(v);
          if (Number.isFinite(n)) {
            if (n < ymin) ymin = n;
            if (n > ymax) ymax = n;
            found = true;
          }
        }
      }
      if (!found) return;
      // enforce to-zero bottom unless negative values are present
      if (!(ymin < 0)) ymin = 0;
      const span = Math.max(1e-12, ymax - ymin);
      const pad = Math.max(0.02, 0.10 * span);
      const yMaxPadded = ymax + pad;
      Plotly.relayout(gd, { 'yaxis.autorange': false, 'yaxis.range': [ymin, yMaxPadded] });
    } catch {}
  }

  plotCategoricalData(valueCounts: { [key: string]: number }, layout: any) {
    const Plotly = (window as any).Plotly;
    const categories = Object.keys(valueCounts).map(k => k === 'nan' || k === 'NaN' ? '(null)' : String(k));
    const counts: number[] = Object.values(valueCounts);
    const total = counts.reduce((sum, val) => sum + val, 0);

    const trace = {
      x: categories,
      y: this.usePercentageYAxis 
        ? counts.map(v => (v / total) * 100)
        : counts,
      type: 'bar',
      marker: {
        color: layout.colorway[0],
        line: {
          color: 'rgba(100, 149, 237, 1)',
          width: 1
        },
      },
    };

    layout.yaxis.title = this.usePercentageYAxis ? 'Percentage' : 'Count';
    layout.xaxis.title = 'Categories';
    // Force categorical x-axis so each distinct value gets its own tick
    if (categories.length <= 20) {
      layout.xaxis.type = 'category';
    }

    Plotly.newPlot('visualization', [trace], layout).catch((error: Error) => {
      console.error('Error plotting categorical data:', error);
      this.errorMessage = 'An error occurred while creating the visualization. Please try again.';
    });
  }

  preprocessStackedData(data: any): any {
    return Object.keys(data).reduce((acc, key) => {
      if (Array.isArray(data[key])) {
        acc[key] = data[key].map((value: any) => 
          value === null || value === 'NaN' ? 'NaN' : parseFloat(value) || 0
        );
      } else {
        acc[key] = Object.entries(data[key]).reduce((innerAcc, [innerKey, innerValue]) => {
          innerAcc[innerKey] = innerValue === null || innerValue === 'NaN' ? 'NaN' : parseFloat(innerValue as string) || 0;
          return innerAcc;
        }, {} as {[key: string]: number | string});
      }
      return acc;
    }, {} as any);
  }

  plotStackedData(stackedData: any, layout: any) {
    console.log('Plotting stacked data:', stackedData);
    const Plotly = (window as any).Plotly;
    if (!Plotly) {
      console.error('Plotly is not loaded');
      this.errorMessage = 'Visualization library not loaded';
      return;
    }
    // Detect data shape: if any target class value is a dict (not array), use categorical bar chart
    const firstVal = Object.values(stackedData)[0];
    const isDictFormat = firstVal && !Array.isArray(firstVal) && typeof firstVal === 'object';

    if (this.isNumerical() && !isDictFormat) {
      const histogramTraces: any[] = [];
      const boxplotTraces: any[] = [];
      //const colors = Plotly.d3 ? Plotly.d3.schemeCategory10 : ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'];
      
      Object.keys(stackedData).forEach((targetClass, index) => {
        const data = stackedData[targetClass];
        const filteredData = data.filter((v: any) => v !== 'NaN' && !isNaN(v)).map(Number);
        
        // Histogram trace
        histogramTraces.push({
          x: filteredData,
          type: 'histogram',
          name: `${targetClass}`,
          opacity: 0.7,
          histnorm: this.usePercentageYAxis ? 'percent' : '',
          marker: { color: layout.colorway[index % layout.colorway.length] }
        });
        
        // Box plot trace
        boxplotTraces.push({
          x: filteredData,
          type: 'box',
          name: `${targetClass} (Box)`,
          marker: { color: layout.colorway[index % layout.colorway.length] },
          boxpoints: 'outliers',
          boxmean: true,
          line: { width: 1 },
          yaxis: 'y2',
          showlegend: false
        });
      });
      
      layout.barmode = 'group';
      layout.bargap = 0.1;
      layout.bargroupgap = 0.05;
      layout.showlegend = true;
      layout.legend = { title: this.stackedWrtTarget ? { text: 'Target Classes' } : undefined, traceorder: 'normal' };

      // Adjust layout for combined plot
      layout.yaxis = {
        title: this.usePercentageYAxis ? 'Percentage' : 'Count',
        domain: [0, 0.85]
      };
      layout.yaxis2 = {
        domain: [0.87, 1],
        showticklabels: false,
        zeroline: false,
        showgrid: false,
        title: ''
      };

      const allTraces = [...boxplotTraces, ...histogramTraces];  // Box plots first to be behind histograms

      Plotly.newPlot('visualization', allTraces, layout).catch((error: Error) => {
        console.error('Error plotting data:', error);
        this.errorMessage = 'An error occurred while creating the visualization. Please try again.'});
      console.log('Plotly.newPlot called with:', allTraces, layout);
    } else {
      // For categorical data, create grouped bar chart
      const allCategories = new Set<string>();
      Object.values(stackedData).forEach((data: any) => {
        if (typeof data === 'object') {
          Object.keys(data).forEach(key => allCategories.add(key === 'nan' || key === 'NaN' ? '(null)' : String(key)));
        }
      });
      const categories = Array.from(allCategories);
      const traces = Object.keys(stackedData).map(targetClass => {
        const data = stackedData[targetClass];
        const values = categories.map(cat => {
          const origKey = cat === '(null)' ? 'NaN' : cat;
          return data[origKey] || data[cat] || 0;
        });
        const total = values.reduce((sum, val) => sum + (typeof val === 'number' ? val : 0), 0);
        return {
          x: categories,
          y: this.usePercentageYAxis 
          ? values.map(v => (typeof v === 'number' ? (v / total) * 100 : 0))
          : values,
          type: 'bar',
          name: targetClass,
          opacity: 0.7,
        };
      });
      layout.barmode = 'group';
      layout.bargap = 0.15;
      layout.bargroupgap = 0.1;
      layout.showlegend = true;
      layout.legend = { title: this.stackedWrtTarget ? { text: 'Target Classes' } : undefined, traceorder: 'normal' };
      layout.yaxis.title = this.usePercentageYAxis ? 'Percentage' : 'Count';
      // Force categorical x-axis so each distinct value gets its own tick
      if (categories.length <= 20) {
        layout.xaxis.type = 'category';
      }
      Plotly.newPlot('visualization', traces, layout);
      console.log('Plotly.newPlot called with:', traces, layout);
    }
  }
  
  plotNonStackedData(histogramData: any[], layout: any) {
    const Plotly = (window as any).Plotly;
    const traces: any[] = [];
    if (this.isNumerical()) {
      if (histogramData && histogramData.length > 0) {
        // Box plot trace (add first to be behind histogram)
        traces.push({
          x: histogramData,
          type: 'box',
          name: 'Box Plot',
          marker: { color: layout.colorway[0] },
          boxpoints: 'outliers',
          boxmean: true,
          line: { color: '#ffffff', width: 1 },
          ysrc: 'y2',
          showlegend: false
        });
        // Histogram trace
        traces.push({
          x: histogramData,
          type: 'histogram',
          name: 'Distribution',
          opacity: 0.7,
          histnorm: this.usePercentageYAxis ? 'percent' : '',
          marker: {
            color: layout.colorway[0],
            line: {
              color: 'black',
              width: 1
            },
          },
        });
      } else {
        console.warn('No histogram data available');
      }
    } else {
      const valueCounts = this.featureData?.Descriptive_Stats['value_counts'] as { [key: string]: number } | undefined;
      if (valueCounts && Object.keys(valueCounts).length > 0) {
        const categories = Object.keys(valueCounts);
        const counts = Object.values(valueCounts);
        const total = counts.reduce((sum: number, val: number) => sum + val, 0);
        traces.push({
          x: categories,
          y: this.usePercentageYAxis 
            ? counts.map((v: number) => ((v / total) * 100))
            : counts,
          type: 'bar',
          marker: {
            color: layout.colorway[0],
            line: {
              color: 'black',
              width: 1
            },
          },
        });
      } else {
        console.warn('No value counts data available');
      }
    }

    // Adjust layout for combined plot
    layout.yaxis = {
      title: this.usePercentageYAxis ? 'Percentage' : 'Count',
      domain: [0, 0.85]
    };
    layout.yaxis2 = {
      domain: [0.87, 1],
      showticklabels: false,
      zeroline: false,
      showgrid: false,
      title: ''
    };

    Plotly.newPlot('visualization', traces, layout).catch((error: Error) => {
      console.error('Error plotting data:', error);
      this.errorMessage = 'An error occurred while creating the visualization. Please try again.'});
    console.log('Plotly.newPlot called with:', traces, layout);
  }

  // UI handlers referenced by template controls
  onOutlierCleaningChange() {
    this.updateVisualizationAndStats();
  }

  onSparsityCleaningChange() {
    this.updateVisualizationAndStats();
  }

  onStackedWrtTargetChange() {
    if (this.stackedWrtTarget && !this.originalStackedData) {
      this.fetchStackedData();
    } else {
      this.updateVisualizationAndStats();
    }
  }

  fetchStackedData() {
    const fileOverride = this.getFileOverride();
    this.dataService.getStackedFeatureData(this.data.fileId, this.data.columnName, fileOverride).subscribe(
      (resp: any) => {
        const stackedData = resp?.stacked_data ?? resp;
        this.targetAverages = resp?.target_averages ?? null;
        this.originalStackedData = this.preprocessStackedData(stackedData);
        this.updateVisualizationAndStats();
      },
      error => {
        console.error('Error fetching stacked data:', error);
        this.errorMessage = 'Failed to fetch stacked data. Please try again.';
        this.stackedWrtTarget = false;
      }
    );
  }

  updateVisualizationAndStats() {
    if (this.featureData && this.featureData.Descriptive_Stats) {
      if (this.stackedWrtTarget && this.originalStackedData) {
        const processedData = this.processStackedData(this.originalStackedData);
        this.updateStackedStats(processedData);
        this.createVisualization(processedData);
      } else {
        if (this.isNumerical()) {
          if (this.originalHistogramData) {
            const processedData = this.cleanData(this.originalHistogramData);
            this.featureData.Descriptive_Stats = this.calculateDescriptiveStats(processedData);
            this.featureData.Descriptive_Stats['histogram_data'] = processedData;
            this.createVisualization(processedData);
          } else {
            console.warn('No histogram data available for numerical feature');
            this.errorMessage = 'No histogram data available for visualization';
          }
        } else {
          const valueCounts = this.featureData.Descriptive_Stats['value_counts'];
          if (valueCounts) {
            this.createVisualization(valueCounts);
          } else {
            console.warn('No value counts data available for categorical feature');
            this.errorMessage = 'No value counts data available for visualization';
          }
        }
      }
    } else {
      console.warn('Feature data or descriptive stats not available');
      this.errorMessage = 'Feature data not available';
    }
  }

  // Process stacked arrays/objects and apply cleaning toggles
  processStackedData(stackedData: any): any {
    if (!stackedData) return {};
    const processedData: any = {};
    for (const [key, value] of Object.entries(stackedData)) {
      if (Array.isArray(value)) {
        processedData[key] = this.cleanData(value as number[]);
      } else if (typeof value === 'object' && value !== null) {
        // Preserve dict structure for categorical data (category → count)
        processedData[key] = { ...value };
      } else {
        processedData[key] = [];
      }
    }
    return processedData;
  }

  // Apply outlier and sparsity cleaning depending on toggles
  cleanData(data: number[]): number[] {
    let cleanedData = [...data];
    if (this.outlierCleaningEnabled) cleanedData = this.cleanOutliers(cleanedData);
    if (this.sparsityCleaningEnabled) cleanedData = this.cleanSparsity(cleanedData) as number[];
    return cleanedData;
  }

  updateStackedStats(stackedData: any) {
    if (!this.featureData) return;
    this.featureData.Stacked_Stats = {};
    for (const [key, value] of Object.entries(stackedData)) {
      this.featureData.Stacked_Stats[key] = this.calculateDescriptiveStats(value as number[]);
    }
  }

  calculateDescriptiveStats(data: any): { [stat: string]: any } {
    const stats: { [stat: string]: any } = {};
    let processedData: any[];
    if (Array.isArray(data)) {
      processedData = data;
    } else if (typeof data === 'object' && data !== null) {
      processedData = Object.values(data);
    } else {
      return stats;
    }

    if (this.isNumerical()) {
      const numericData = processedData.filter((v): v is number => typeof v === 'number' && !isNaN(v));
      try {
        stats['Mean'] = math.mean(numericData);
        stats['Min'] = math.min(numericData);
        stats['1st_Quantile'] = math.quantileSeq(numericData, 0.01);
        stats['5th_Quantile'] = math.quantileSeq(numericData, 0.05);
        stats['25th_Q1'] = math.quantileSeq(numericData, 0.25);
        stats['50th_Median'] = math.median(numericData);
        stats['75th_Q3'] = math.quantileSeq(numericData, 0.75);
        stats['95th_Quantile'] = math.quantileSeq(numericData, 0.95);
        stats['99th_Quantile'] = math.quantileSeq(numericData, 0.99);
        stats['Max'] = math.max(numericData);
        stats['Std'] = math.std(numericData);
        stats['Skewness'] = this.calculateSkewness(numericData);
        stats['Kurtosis'] = this.calculateKurtosis(numericData);
      } catch (error) {
        console.error('Error calculating numerical stats:', error);
      }
    } else {
      try {
        const valueCounts = this.calculateValueCounts(processedData);
        stats['#_of_Categories'] = Object.keys(valueCounts).length;
        const modeEntry = Object.entries(valueCounts).reduce((a, b) => a[1] > b[1] ? a : b);
        stats['Mode_Value'] = modeEntry[0];
        stats['Mode_Ratio'] = (modeEntry[1] / processedData.length) * 100;
        stats['Missing_Ratio'] = (processedData.filter((v: number | null | undefined) => v === null || v === undefined).length / processedData.length) * 100;
        stats['#_of_Outlier_Categories'] = Object.values(valueCounts).filter(count => (count / processedData.length) < 0.005).length;
      } catch (error) {
        console.error('Error calculating categorical stats:', error);
      }
    }

    return stats;
  }

  private calculateValueCounts(data: any): { [key: string]: number } {
    const dataArray = Array.isArray(data) ? data : Object.values(data);
    return dataArray.reduce((acc: { [key: string]: number }, val: any) => {
      const key = String(val);
      acc[key] = (acc[key] || 0) + 1;
      return acc;
    }, {});
  }

  calculateSkewness(data: number[]): number {
    const n = data.length;
    const mean = this.ensureNumber(math.mean(data));
    const std = this.ensureNumber(math.std(data));
    
    if (std === 0) return 0; // Avoid division by zero

    let sumCubedDeviations = 0;
    for (let i = 0; i < n; i++) {
      const deviation = this.ensureNumber((data[i] - mean) / std);
      sumCubedDeviations += Math.pow(deviation, 3);
    }
    return sumCubedDeviations / n;
  }

  calculateKurtosis(data: number[]): number {
    const n = data.length;
    const mean = this.ensureNumber(math.mean(data));
    const std = this.ensureNumber(math.std(data));
    
    if (std === 0) return 0; // Avoid division by zero

    let sumFourthPowerDeviations = 0;
    for (let i = 0; i < n; i++) {
      const deviation = this.ensureNumber((data[i] - mean) / std);
      sumFourthPowerDeviations += Math.pow(deviation, 4);
    }
    return (sumFourthPowerDeviations / n) - 3;
  }
  
  getStats(): string[] {
    return this.isNumerical() ? this.numericalStats : this.categoricalStats;
  }

  getStatValue(stat: string, targetClass?: string): string | number {
    if (this.stackedWrtTarget && targetClass) {
      const value = this.featureData?.Stacked_Stats?.[targetClass]?.[stat];
      return value !== undefined ? this.formatValue(value) : 'N/A';
    } else {
      const value = this.featureData?.Descriptive_Stats[stat];
      return value !== undefined ? this.formatValue(value) : 'N/A';
    }
  }

  formatValue(value: any): string | number {
    if (typeof value === 'number') {
      return Number(value.toFixed(2));
    }
    return value;
  }

  // Function to clean outliers below 5th and above 95th percentiles
  cleanOutliers(data: number[]): number[] {
    if (!Array.isArray(data) || data.length === 0) {
      console.warn('Invalid data for outlier cleaning');
      return data;
    }
    const lowerBound = this.getPercentile(data, 5);
    const upperBound = this.getPercentile(data, 95);
    return data.filter(value => value >= lowerBound && value <= upperBound);
  }

  // Helper function to calculate percentile
  getPercentile(data: number[], percentile: number): number {
    const sortedData = [...data].sort((a, b) => a - b);
    const index = Math.floor((percentile / 100) * sortedData.length);
    return sortedData[index];
  }

  // Function to clean sparsity by removing mode if its ratio is greater than 25%
  cleanSparsity(data: number[] | { [key: string]: number }): number[] | { [key: string]: number } {
    if (Array.isArray(data)) {
      const modeValue = this.getMode(data);
      const modeCount = data.filter(value => value === modeValue).length;
      const modeRatio = (modeCount / data.length) * 100;
      return modeRatio > 25 ? data.filter(value => value !== modeValue) : data;
    } else {
      const values = Object.values(data);
      const modeValue = this.getMode(values);
      const modeCount = values.filter(value => value === modeValue).length;
      const modeRatio = (modeCount / values.length) * 100;
      return modeRatio > 25 
        ? Object.fromEntries(Object.entries(data).filter(([_, value]) => value !== modeValue))
        : data;
    }
  }

  // Helper function to calculate mode
  getMode(data: number[]): number {
    const frequencyMap: { [key: number]: number } = {};

    // Create a frequency map for the data
    data.forEach(value => {
      if (!frequencyMap[value]) {
        frequencyMap[value] = 0;
      }
      frequencyMap[value]++;
    });

    // Find the mode (most frequent value)
    let mode = data[0];
    let maxCount = frequencyMap[mode];

    for (const key in frequencyMap) {
      if (frequencyMap[key] > maxCount) {
        mode = +key;  // Convert key to number and assign to mode
        maxCount = frequencyMap[key];
      }
    }

    return mode;
  }

  toggleFullScreen() {
    this.isFullScreen = !this.isFullScreen;
    if (this.isFullScreen) {
      this.dialogRef.updateSize('100vw', '100vh');
      this.dialogRef.updatePosition({ top: '0', left: '0' });
      this.tooltipPosition = 'above'; // Change tooltip position for full-screen
    } else {
      this.dialogRef.updateSize('400px', 'auto');
      this.dialogRef.updatePosition(); // Reset to default position
      this.tooltipPosition = 'above'; // Reset tooltip position
    }
    setTimeout(() => {
      this.createVisualization();
    }, 0);
  }

  getOutlierCleaningTooltip(): string {
    if (this.isCategorical) {
      return "Outlier cleaning is only available for numerical features";
    } else {
      return "Datapoints falling outside 5th-95th percentile interval are removed from the numerical features.";
    }
  }

  getSparsityCleaningTooltip(): string {
    if (this.isCategorical) {
      return "Sparsity cleaning is only available for numerical features";
    } else {
      return "Datapoints equal the Sparse-Value (mode-value having greater than 25% share) are removed from the numerical features.";
    }
  }

  private ensureNumber(value: any): number {
    const num = Number(value);
    return isNaN(num) ? 0 : num;
  }

  // Handle tab change to auto-load explainability
  onTabChange(event: any): void {
    const tabIndex = event.index;
    this.currentTabIndex = tabIndex;  // Track current tab
    
    // Tab indices: 0=Descriptives, 1=Quality, 2=Importance, 3=Explainability
    if (tabIndex === 1) {
      // Quality tab — fetch summary from backend if not available
      if (!this.hasQuality()) {
        this.fetchQualitySummaryRow();
      } else {
        this.fetchQualityTimeseries();
      }
    }
    if (tabIndex === 2) {
      if (this.preModelingMode) {
        // No model trained yet — message shown in template
        return;
      }
      if (this.importanceGain.length || this.importanceShap.length) {
        // Data already loaded (e.g. from overrides) — just redraw
        setTimeout(() => this.drawImportancePlot(), 0);
      } else if (!this.modelingLoading) {
        this.proceedModeling();
      }
    }
    if (tabIndex === 3) {
      console.log('[Explainability] Tab activated. preModelingMode=', this.preModelingMode, 'fetched=', this.explainabilityFetched, 'loading=', this.explainabilityLoading, 'hasSfsContexts=', this.hasSfsContexts, 'sfsViewMode=', this.sfsViewMode);
      if (this.preModelingMode) {
        // No model trained yet — message shown in template
        return;
      }
      if (!this.explainabilityFetched && !this.explainabilityLoading) {
        this.fetchFeatureExplainability();
      }
    }
  }

  // ===== Explainability (SHAP beeswarm + Partial Dependence) =====
  fetchFeatureExplainability(): void {
    try {
      console.log('[Explainability] fetchFeatureExplainability called. isBrowser=', this.isBrowser, 'processedFile=', this.data.processedFile, 'fileId=', this.data.fileId);
      if (!this.isBrowser) return;
      if (!this.data.processedFile) {
        this.explainabilityError = 'Processed file required. Please run preprocessing first.';
        console.warn('[Explainability] No processedFile — aborting.');
        return;
      }
      const fid = Number(this.data.fileId);
      if (!isFinite(fid)) {
        this.explainabilityError = 'Invalid file id';
        return;
      }
      this.explainabilityLoading = true;
      this.explainabilityError = null;
      this.explainabilityFetched = true;
      
      // Determine model source: SFS context (dropdown) → legacy sfsModelPath → default
      let explModelPath: string | undefined = this.data.sfsModelPath;
      let explSelectedFeatures: string[] | undefined = undefined;
      if (this.hasSfsContexts && this.sfsContexts[this.sfsViewMode]) {
        const ctx = this.sfsContexts[this.sfsViewMode];
        explModelPath = ctx.modelPath || undefined;
        explSelectedFeatures = ctx.selectedFeatures || undefined;
      }

      console.log('[Explainability] API call params: fid=', fid, 'feature=', this.selectedFeatureName, 'modelPath=', explModelPath, 'selectedFeatures=', explSelectedFeatures);
      this.dataService.getFeatureExplainability(fid, this.selectedFeatureName, this.data.processedFile, 500, explModelPath, explSelectedFeatures).subscribe({
        next: (resp: any) => {
          console.log('[Explainability] API response received. Keys:', Object.keys(resp || {}), 'beeswarm?', !!resp?.beeswarm, 'pdp?', !!resp?.partial_dependence);
          if (resp?.beeswarm) console.log('[Explainability] beeswarm shap_values length:', resp.beeswarm.shap_values?.length);
          this.explainabilityData = resp;
          setTimeout(() => this.drawExplainabilityPlots(), 0);
        },
        error: (err: any) => {
          console.error('Fetch explainability failed:', err);
          
          // Check if this is a "feature not in model" case (expected, not an error)
          const reason = err?.error?.reason;
          const detail = err?.error?.detail;
          
          if (reason === 'feature_not_in_model') {
            // This is expected - feature was not selected during modeling
            this.explainabilityError = detail || err?.error?.error || 
              `Feature "${this.selectedFeatureName}" was not selected during the modeling phase. Explainability analysis is only available for features used in the trained model.`;
            this.explainabilityFetched = true;  // Don't allow retry - this is expected
          } else {
            // This is an actual error
            this.explainabilityError = err?.error?.error || err?.message || 
              'Failed to load explainability data. Please ensure a model has been trained.';
            this.explainabilityFetched = false;  // Allow retry on actual error
          }
        },
        complete: () => {
          this.explainabilityLoading = false;
        }
      });
    } catch (e) {
      console.warn('fetchFeatureExplainability failed:', e);
      this.explainabilityError = 'Failed to load explainability data';
      this.explainabilityLoading = false;
      this.explainabilityFetched = false;  // Allow retry on error
    }
  }

  drawExplainabilityPlots(): void {
    console.log('[Explainability] drawExplainabilityPlots called. isBrowser=', this.isBrowser, 'data?', !!this.explainabilityData);
    if (!this.isBrowser || !this.explainabilityData) return;
    const beeEl = document.getElementById('explainability-beeswarm');
    const pdpEl = document.getElementById('explainability-pdp');
    console.log('[Explainability] DOM elements: beeswarm=', !!beeEl, 'pdp=', !!pdpEl, 'Plotly?', !!(window as any).Plotly);
    this.drawShapBeeswarmSingle();
    this.drawPartialDependencePlot();
  }

  getShapStaticImage(): string | null {
    try {
      return this.explainabilityData?.partial_dependence?.shap_static_image || null;
    } catch {
      return null;
    }
  }

  downloadShapPdpImage(): void {
    try {
      const imageData = this.getShapStaticImage();
      if (!imageData) {
        console.warn('No SHAP PDP image available to download');
        return;
      }

      // Extract base64 data from data URI
      const base64Data = imageData.split(',')[1];
      const byteCharacters = atob(base64Data);
      const byteNumbers = new Array(byteCharacters.length);
      for (let i = 0; i < byteCharacters.length; i++) {
        byteNumbers[i] = byteCharacters.charCodeAt(i);
      }
      const byteArray = new Uint8Array(byteNumbers);
      const blob = new Blob([byteArray], { type: 'image/png' });

      // Create download link
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      const featureName = this.explainabilityData?.feature_name || this.selectedFeatureName || 'feature';
      link.href = url;
      link.download = `shap_pdp_${featureName}.png`;
      document.body.appendChild(link);
      link.click();
      
      // Cleanup
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Failed to download SHAP PDP image:', error);
    }
  }

  drawShapBeeswarmSingle(): void {
    try {
      console.log('[Explainability] drawShapBeeswarmSingle: Plotly?', !!Plotly, 'beeswarm?', !!this.explainabilityData?.beeswarm);
      if (!Plotly || !this.explainabilityData?.beeswarm) return;
      const el = document.getElementById('explainability-beeswarm');
      console.log('[Explainability] drawShapBeeswarmSingle: el?', !!el);
      if (!el) return;

      const beeswarm = this.explainabilityData.beeswarm;
      const shapVals: number[] = beeswarm.shap_values || [];
      const featValsRaw: any[] = beeswarm.feature_values_raw || [];
      const featName = this.explainabilityData.feature_name || this.selectedFeatureName;

      if (!shapVals.length) return;

      // Simple seeded random number generator for deterministic jitter
      const seededRandom = (seed: number): number => {
        const x = Math.sin(seed) * 10000;
        return x - Math.floor(x);
      };

      // Filter valid points (check both SHAP values and feature values)
      const isNull = featValsRaw.map((v: any, i: number) => {
        const shapInvalid = shapVals[i] == null || (typeof shapVals[i] === 'number' && !Number.isFinite(shapVals[i]));
        const featInvalid = v == null || (typeof v === 'number' && !Number.isFinite(v));
        return shapInvalid || featInvalid;
      });
      const idxNonNull: number[] = [];
      const idxNull: number[] = [];
      for (let i = 0; i < shapVals.length; i++) {
        (isNull[i] ? idxNull : idxNonNull).push(i);
      }

      // Calculate and store missing ratio for display in checkbox label
      this.beeswarmMissingRatio = shapVals.length > 0 ? (idxNull.length / shapVals.length) : 0;

      // Compute color normalization (5th-95th percentile)
      const nonNullVals = idxNonNull.map(i => Number(featValsRaw[i])).filter(v => Number.isFinite(v));
      let vmin = 0, vmax = 1;
      if (nonNullVals.length > 0) {
        const sorted = nonNullVals.slice().sort((a, b) => a - b);
        const q05idx = Math.floor(sorted.length * 0.05);
        const q95idx = Math.floor(sorted.length * 0.95);
        vmin = sorted[q05idx] || sorted[0];
        vmax = sorted[q95idx] || sorted[sorted.length - 1];
        if (vmin === vmax) { vmin = sorted[0]; vmax = sorted[sorted.length - 1]; }
        if (vmin === vmax) { vmin = vmax - 1; }
      }
      const denom = (vmax - vmin) !== 0 ? (vmax - vmin) : 1e-12;

      // Build traces
      const traces: any[] = [];
      const colorscale: any = [
        [0.0, '#2166ac'],  // blue (low)
        [0.5, '#f7f7f7'],  // white (mid)
        [1.0, '#b2182b']   // red (high)
      ];

      // Non-null points
      if (idxNonNull.length > 0) {
        const xVals = idxNonNull.map(i => shapVals[i]);
        // Use deterministic jitter based on sample index so points stay in same position
        const yVals = idxNonNull.map(i => (seededRandom(i + 1) * 2 - 1) * 0.2);
        const colors = idxNonNull.map(i => {
          const v = Number(featValsRaw[i]);
          const u = (v - vmin) / denom;
          return u < 0 ? 0 : (u > 1 ? 1 : u);
        });

        // Check if this feature has a categorical encoding mapping
        const singleCatLookup = this.catLabelLookup[featName];
        let customdata: any[];
        let hovertemplate: string;
        if (singleCatLookup) {
          customdata = idxNonNull.map(i => {
            const enc = String(Math.round(Number(featValsRaw[i])));
            const label = singleCatLookup[enc] || featValsRaw[i];
            return [featValsRaw[i], label];
          });
          hovertemplate = `${featName}<br>SHAP=%{x:.4f}<br>Encoded=%{customdata[0]}<br>Original=%{customdata[1]}<extra></extra>`;
        } else {
          customdata = idxNonNull.map(i => featValsRaw[i]);
          hovertemplate = `${featName}<br>SHAP=%{x:.4f}<br>Value=%{customdata:.4f}<extra></extra>`;
        }

        traces.push({
          type: 'scatter',
          mode: 'markers',
          x: xVals,
          y: yVals,
          customdata,
          marker: {
            color: colors,
            colorscale: colorscale,
            cmin: 0,
            cmax: 1,
            showscale: true,
            colorbar: { title: { text: 'Feature value' }, thickness: 14, tickmode: 'array', tickvals: [0, 1], ticktext: ['Low', 'High'] },
            size: 8,
            opacity: 0.85
          },
          hovertemplate,
          showlegend: false
        });
      }

      // Null points (grey X markers) - only shown if checkbox is enabled
      if (this.showNullsBeeswarm && idxNull.length > 0) {
        const xVals = idxNull.map(i => shapVals[i]);
        // Use deterministic jitter for null points too
        const yVals = idxNull.map(i => (seededRandom(i + 1) * 2 - 1) * 0.2);
        traces.push({
          type: 'scatter',
          mode: 'markers',
          x: xVals,
          y: yVals,
          marker: { color: 'rgba(130,130,130,0.9)', size: 8, symbol: 'x', line: { width: 0.5, color: 'rgba(80,80,80,0.9)' } },
          hovertemplate: `${featName}<br>SHAP=%{x:.4f}<br>Value=null<extra></extra>`,
          showlegend: false
        });
      }

      const layout = {
        title: { text: `SHAP values for ${featName}`, font: { size: 14 } },
        margin: { l: 60, r: 48, t: 40, b: 50 },
        xaxis: { title: { text: 'SHAP value (impact on model output)' }, zeroline: true, zerolinecolor: '#888', zerolinewidth: 1 },
        yaxis: { showticklabels: false, zeroline: false, range: [-0.3, 0.3] },
        hovermode: 'closest',
        showlegend: false,
        shapes: [{ type: 'line', x0: 0, x1: 0, y0: -0.3, y1: 0.3, line: { color: '#888', width: 1 } }]
      } as any;
      const config = { responsive: true, displayModeBar: true } as any;
      try { Plotly.react(el, traces, layout, config); } catch { Plotly.newPlot(el, traces, layout, config); }
    } catch (e) {
      console.warn('drawShapBeeswarmSingle failed:', e);
    }
  }

  private drawPartialDependencePlot(): void {
    try {
      console.log('[Explainability] drawPDP: Plotly?', !!Plotly, 'pdp?', !!this.explainabilityData?.partial_dependence);
      if (!Plotly || !this.explainabilityData?.partial_dependence) return;
      const el = document.getElementById('explainability-pdp');
      console.log('[Explainability] drawPDP: el?', !!el);
      if (!el) return;

      const pdp = this.explainabilityData.partial_dependence;
      // Filter out null/undefined values from arrays (backend may send null for NaN/Inf values)
      const grid: number[] = (pdp.grid || []).filter((v: any) => v != null && isFinite(v));
      const pdpMean: number[] = (pdp.pdp_mean || []).filter((v: any) => v != null && isFinite(v));
      const iceCurves: number[][] = (pdp.ice_curves || [])
        .map((curve: any[]) => curve.filter((v: any) => v != null && isFinite(v)))
        .filter((curve: any[]) => curve.length > 0);
      const baseValue: number = (pdp.base_value != null && isFinite(pdp.base_value)) ? pdp.base_value : 0;
      const expectedFeatureValue: number = (pdp.expected_feature_value != null && isFinite(pdp.expected_feature_value)) 
        ? pdp.expected_feature_value 
        : grid[Math.floor(grid.length / 2)] || 0;
      const histogram = pdp.histogram || { centers: [], counts: [] };
      // Filter histogram data
      if (histogram.centers && histogram.counts) {
        const validIndices: number[] = [];
        histogram.centers.forEach((v: any, i: number) => {
          if (v != null && isFinite(v) && histogram.counts[i] != null) {
            validIndices.push(i);
          }
        });
        histogram.centers = validIndices.map(i => histogram.centers[i]);
        histogram.counts = validIndices.map(i => histogram.counts[i]);
      }
      const featName = this.explainabilityData.feature_name || this.selectedFeatureName;

      if (!grid.length || !pdpMean.length) return;

      const traces: any[] = [];
      
      // Add histogram as background (if available)
      if (histogram.centers && histogram.centers.length > 0 && histogram.counts && histogram.counts.length > 0) {
        // Normalize histogram counts for better visualization
        const maxCount = Math.max(...histogram.counts);
        const normalizedCounts = histogram.counts.map((c: number) => c / maxCount);
        
        traces.push({
          type: 'bar',
          x: histogram.centers,
          y: normalizedCounts,
          marker: { color: 'rgba(200, 200, 200, 0.3)' },
          name: 'Distribution',
          yaxis: 'y2',
          hoverinfo: 'skip',
          showlegend: false
        });
      }

      // Compute y-axis range based on PDP mean (not ICE curves) for better visibility
      // This matches the SHAP static plot's focused range
      const pdpVals = [...pdpMean, baseValue];
      const yMin = Math.min(...pdpVals);
      const yMax = Math.max(...pdpVals);
      const yPadding = (yMax - yMin) * 0.15 || 0.3;
      const yRangeMin = yMin - yPadding;
      const yRangeMax = yMax + yPadding;

      // Filter ICE curves to only show those within visible range (avoid extreme outliers)
      const filteredIceCurves = iceCurves.filter(curve => {
        const curveMin = Math.min(...curve);
        const curveMax = Math.max(...curve);
        // Keep ICE curves that have at least some overlap with visible range
        return curveMax >= yRangeMin && curveMin <= yRangeMax;
      });

      // ICE curves (individual conditional expectation) - very light grey, clipped to visible range
      if (filteredIceCurves.length > 0) {
        filteredIceCurves.forEach((curve, idx) => {
          traces.push({
            type: 'scatter',
            mode: 'lines',
            x: grid,
            y: curve,
            line: { color: 'rgba(150,150,150,0.1)', width: 0.8 },
            name: idx === 0 ? 'ICE curves' : undefined,
            hoverinfo: 'skip',
            showlegend: idx === 0
          });
        });
      }

      // PDP mean (average effect) - thick blue line
      traces.push({
        type: 'scatter',
        mode: 'lines',
        x: grid,
        y: pdpMean,
        line: { color: '#1f77b4', width: 3 },
        name: 'PDP (mean)',
        hovertemplate: `${featName}=%{x:.4f}<br>E[f(X) | ${featName}]=%{y:.4f}<extra></extra>`
      });

      const layout = {
        title: { text: `Partial Dependence Plot for ${featName}`, font: { size: 14 } },
        margin: { l: 70, r: 48, t: 40, b: 80 },
        xaxis: { title: { text: featName, font: { size: 13 } } },
        yaxis: { 
          title: { text: `E[f(X) | ${featName}]`, font: { size: 13 } }, 
          range: [yRangeMin, yRangeMax],
          side: 'left'
        },
        yaxis2: {
          overlaying: 'y',
          side: 'right',
          showticklabels: false,
          showgrid: false,
          range: [0, 1.2]
        },
        hovermode: 'closest',
        legend: { orientation: 'h', x: 0, y: -0.15, xanchor: 'left', yanchor: 'top', font: { size: 11 } },
        barmode: 'overlay',
        shapes: [
          {
            type: 'line',
            x0: grid[0],
            x1: grid[grid.length - 1],
            y0: baseValue,
            y1: baseValue,
            line: { color: '#888', width: 1.5, dash: 'dash' },
            name: 'E[f(X)]'
          },
          {
            type: 'line',
            x0: expectedFeatureValue,
            x1: expectedFeatureValue,
            y0: yRangeMin,
            y1: yRangeMax,
            line: { color: '#888', width: 1.5, dash: 'dash' },
            name: `E[${featName}]`
          }
        ],
        annotations: [
          {
            x: grid[Math.floor(grid.length * 0.02)],
            y: baseValue,
            xanchor: 'left',
            yanchor: 'bottom',
            text: `E[f(X)]`,
            showarrow: false,
            font: { size: 10, color: '#555' },
            bgcolor: 'rgba(255,255,255,0.8)',
            borderpad: 2
          },
          {
            x: expectedFeatureValue,
            y: yRangeMax - (yRangeMax - yRangeMin) * 0.05,
            xanchor: 'center',
            yanchor: 'top',
            text: `E[${featName}]`,
            showarrow: false,
            font: { size: 10, color: '#555' },
            bgcolor: 'rgba(255,255,255,0.8)',
            borderpad: 2
          }
        ]
      } as any;
      const config = { responsive: true, displayModeBar: true } as any;
      try { Plotly.react(el, traces, layout, config); } catch { Plotly.newPlot(el, traces, layout, config); }
    } catch (e) {
      console.warn('drawPartialDependencePlot failed:', e);
    }
  }
}