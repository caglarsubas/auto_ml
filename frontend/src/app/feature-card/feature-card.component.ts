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

interface FeatureCardDialogData {
  fileId: string;
  columnName: string;
  features: FeatureInfo[];
  processedFile?: string;
  dateColumn?: string;
  qualitySummary?: { [key: string]: any };
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
  features: FeatureInfo[] = [];
  selectedFeatureName: string;
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
        }, 200);
      }
    };
    this.features = data.features;
    this.selectedFeatureName = data.columnName;
    this.qualitySummary = data.qualitySummary || null;
    this.initialQualitySummary = data.qualitySummary || null;
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
  proceedModeling(): void {
    try {
      if (!this.isBrowser) return;
      this.modelingError = null;
      if (!this.data.processedFile) {
        this.modelingError = 'Processed file is required to start modelling.';
        return;
      }
      const fid = Number(this.data.fileId);
      if (!isFinite(fid)) {
        this.modelingError = 'Invalid file id';
        return;
      }
      this.modelingLoading = true;
      this.dataService.startModeling(fid, this.data.processedFile, 'xgboost').subscribe({
        next: (resp: any) => {
          this.modelInfo = resp?.model || null;
          const imps = this.modelInfo?.importances || {};
          this.importanceGain = Array.isArray(imps.gain) ? imps.gain : [];
          this.importanceShap = Array.isArray(imps.shap_mean_abs) ? imps.shap_mean_abs : [];
          if (this.importanceShap.length) this.selectedImportanceType = 'shap';
          else if (this.importanceGain.length) this.selectedImportanceType = 'gain';
          this.drawImportancePlot();
        },
        error: (err: any) => {
          console.error('Modeling failed:', err);
          this.modelingError = 'Failed to run modelling';
        },
        complete: () => {
          this.modelingLoading = false;
        }
      });
    } catch (e) {
      console.warn('proceedModeling failed:', e);
      this.modelingError = 'Failed to start modelling';
      this.modelingLoading = false;
    }
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

      const trace = {
        x,
        y,
        type: 'bar',
        orientation: 'h',
        marker: { color: '#4E79A7' },
        hovertemplate: '%{y}: %{x:.6f}<extra></extra>'
      } as any;
      const layout = {
        margin: { l: 180, r: 24, t: 36, b: 36 },
        height: Math.max(320, 28 * top.length + 120),
        title: { text: title, font: { size: 14 } },
        xaxis: { title: 'Score' },
        yaxis: { automargin: true },
        showlegend: false
      } as any;
      const config = { responsive: true, displayModeBar: false } as any;
      try { (window as any).Plotly.react(el, [trace], layout, config); }
      catch { Plotly.newPlot(el, [trace], layout, config); }
    } catch (e) {
      console.warn('drawImportancePlot failed:', e);
    }
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
  
  loadFeatureData() {
    console.log(`Loading feature data for fileId: ${this.data.fileId}, columnName: ${this.data.columnName}`);
    forkJoin({
      featureCard: this.dataService.getFeatureCard(this.data.fileId, this.data.columnName),
      stackedData: this.dataService.getStackedFeatureData(this.data.fileId, this.data.columnName)
    }).subscribe({
      next: ({ featureCard, stackedData }) => {
        this.featureData = featureCard;
        if (this.featureData) {
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
      if (!this.data.processedFile || !this.data.dateColumn) {
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
        this.data.processedFile,
        this.data.columnName,
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
          this.qualityTimeseriesOverall = (overallFromSummary != null) ? overallFromSummary : overallFromApi;
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
    const categories = Object.keys(valueCounts);
    const counts = Object.values(valueCounts);
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
    if (this.isNumerical()) {
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
          Object.keys(data).forEach(key => allCategories.add(key));
        }
      });
      const categories = Array.from(allCategories);
      const traces = Object.keys(stackedData).map(targetClass => {
        const data = stackedData[targetClass];
        const values = categories.map(cat => (data[cat] || 0));
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
      layout.bargap = 0.15;  // Add some gap between bars
      layout.bargroupgap = 0.1;  // Gap between bars in a group
      layout.showlegend = true;  // Ensure the legend is shown
      layout.legend = { title: this.stackedWrtTarget ? { text: 'Target Classes' } : undefined, traceorder: 'normal' };  // Ensure legend is visible
      layout.yaxis.title = this.usePercentageYAxis ? 'Percentage' : 'Count';
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
    this.dataService.getStackedFeatureData(this.data.fileId, this.data.columnName).subscribe(
      (stackedData: any) => {
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
        processedData[key] = this.cleanData(Object.values(value) as number[]);
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
}