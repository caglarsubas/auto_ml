import { Component, OnInit, HostListener, ViewChild, ElementRef, AfterViewChecked } from '@angular/core';
import { Router } from '@angular/router';
import { switchMap, finalize } from 'rxjs/operators';
import { SharedService } from '../services/shared.service';
import { MatSelectChange } from '@angular/material/select';
import { Subscription } from 'rxjs';
import { DataService } from '../services/data.service';
import { MatDialog } from '@angular/material/dialog';
import { FeatureCardComponent } from '../feature-card/feature-card.component';
import { AiAssistantService } from '../services/ai-assistant.service';

interface PurifierOption {
  id: number;
  name: string;
  group?: number;
}

@Component({
  selector: 'app-model-development',
  templateUrl: './model-development.component.html',
  styleUrls: ['./model-development.component.css']
})

export class ModelDevelopmentComponent implements OnInit, AfterViewChecked {
  @ViewChild('splitValidationCanvas') splitValidationCanvas!: ElementRef<HTMLCanvasElement>;
  private _splitChartDrawn = false;
  currentRoute: string = '';
  menuItems = ['declaration', 'preprocessing', 'data quality', 'modeling', 'evaluation', 'deployment'];
  selectedPipeline: string = '';
  targetDefinition: string = '';
  editingTargetDefinition: boolean = false;
  currentStep: string = 'declaration';
  showDeclaration: boolean = false;
  showSteps: { [key: string]: boolean } = {
    declaration: false,
    preprocessing: false,
    modeling: false,
    evaluation: false,
    deployment: false
  };
  private subscription: Subscription = new Subscription();
  currentFileId: number | null = null;

  // ===== Pipeline Persistence =====
  savedPipelines: any[] = [];
  showSavedPipelines: boolean = false;
  activePipelineRunId: number | null = null;
  pipelineRunName: string = '';
  renamingPipelineId: number | null = null;
  renamingPipelineName: string = '';
  private _checkpointCreating: boolean = false;
  private _pendingCheckpoint: boolean = false;
  private _highWaterStep: string = 'declaration';
  private _lastModelingSubstep: string | null = null;
  detailedStep: string = '1a_pipeline_declaration';
  pipelineNotes: { [position: string]: string } = {};
  editingNotePosition: string | null = null;
  private _noteSaveTimer: any = null;
  private _pipelineConfigSaveTimer: any = null;
  // Autosave toggle & dirty-state tracking (persisted in localStorage)
  autosaveEnabled: boolean = true;
  _unsavedChanges: boolean = false;
  showExitDialog: boolean = false;
  private _pendingNavUrl: string | null = null;
  private readonly _autosaveKey = 'pipeline_autosave_enabled';
  processedFilePath: string | null = null;
  isProcessing: boolean = false;
  // New state flags for progressive reveal
  isStarted: boolean = false;
  modelingAvailable: boolean = false;
  preprocessingAvailable: boolean = false;
  // Purifier breakdown: which columns were dropped at which step, and how many rows were removed
  droppedColumnsByStep: Array<{ step: string; option_ids?: number[]; threshold?: number; columns: string[]; rows_removed?: number; merge_mapping?: { [feature: string]: { [orig: string]: string } }; note?: string }>= [];
  // Total rows removed across all preprocessing steps
  rowsRemovedTotal: number = 0;
  // Row counts before/after preprocessing run (for summary display)
  rowCountBefore: number = 0;
  rowCountAfter: number = 0;
  preprocessingInitiated: boolean = false;
  // Before/after preprocessing per-feature descriptive stats (mean, median, skewness, kurtosis, etc.)
  featureStatsBefore: any[] | null = null;
  featureStatsAfter: any[] | null = null;
  // Per-step before/after stats (e.g. before/after outlier cleaning specifically)
  preprocessingStepStats: any[] | null = null;

  // Split controls
  splitStrategy: 'random' | 'oot' = 'random';
  splitDateColumn: string | null = null;
  splitCutoff: string = '';
  // OOT mode: cutoff vs percent; default cutoff; percent default 25 (last % as test)
  ootMode: 'cutoff' | 'percent' = 'percent';
  ootPercent: number = 25;
  // Random split OOS percent (default 25% goes to test)
  oosPercent: number = 25;
  dateColumns: string[] = [];
  // Cache full data dictionary (to provide Feature_Description to Feature Card)
  dataDictionaryCache: any[] = [];
  currentSplit: { strategy?: string; date_column?: string; cutoff?: string; percent?: number } | null = null;
  // Split validation: target distribution per split (Full, Train, Test)
  splitValidation: any = null;

  // Data Quality summary from backend after preprocessing run
  datqSummary: any[] | null = null;
  datqColumns: string[] = [];
  datqAllColumns: string[] = [];
  datqPreset: 'core' | 'all' = 'core';
  datqPage: number = 1;
  datqPageSize: number = 25;
  datqPageSizes: number[] = [10, 25, 50, 100];
  datqGlobalFilter: string = '';
  datqColumnFilters: { [key: string]: string } = {};
  // Unique-values dropdown filter state
  datqFilterMenuFor: string | null = null; // which column menu is open
  datqFilterMenuSearch: string = '';
  datqUniqueValuesCache: { [col: string]: Array<{ value: string, count: number }> } = {};
  datqSelectedValues: { [col: string]: Set<string> } = {};
  datqShowOnlySelected: { [col: string]: boolean } = {};
  datqSortColumn: string | null = null;
  datqSortDir: 'asc' | 'desc' = 'asc';
  // Pinned columns and layout helpers
  pinnedColumns: string[] = [];
  pinnedColumnWidth = 260; // base px; actual per-col uses colWidth()
  private readonly datqPrefsKey = 'datq_prefs_v1';
  private readonly datqWidthsKey = 'datq_widths_v1';
  // Model_Usage column: track which variables to use in model (variableName -> 'Yes'/'No')
  variableModelUsage: { [variable: string]: string } = {};
  private readonly modelUsageKey = 'datq_model_usage_v1';

  // ===== Encoding step state =====
  encodingPlan: any[] = [];
  encodingReport: any[] = [];
  encodingSummary: any = null;
  encodingAnalyzing: boolean = false;
  encodingApplying: boolean = false;
  encodingError: string | null = null;
  encodingApplied: boolean = false;
  encodedFilePath: string | null = null;
  encodingUseNative: boolean = true;

  // ===== Enhanced Navigation: Collapsible Sub-Steps =====
  navExpandedSteps: { [mainStep: string]: boolean } = {
    declaration: true,
    modeling: false,
    evaluation: false,
    deployment: false,
  };

  navMainSteps = [
    {
      id: 'declaration', label: 'Declaration',
      subSteps: [
        { id: '1a', label: 'Pipeline Type Selection' },
        { id: '1b', label: 'Data Upload' },
        { id: '1c', label: 'Data Dictionary Review' },
        { id: '1d', label: 'Preprocessing' },
        { id: '1e', label: 'Data Quality Summary' },
      ]
    },
    {
      id: 'modeling', label: 'Modeling',
      subSteps: [
        { id: '2a', label: 'Categorical Encoding' },
        { id: '2b', label: 'Model Training & CV' },
        { id: '2c', label: 'Feature Selection (SFS)' },
      ]
    },
    {
      id: 'evaluation', label: 'Evaluation',
      subSteps: [
        { id: '3a', label: 'Model Evaluation' },
      ]
    },
    {
      id: 'deployment', label: 'Deployment',
      subSteps: [
        { id: '4a', label: 'Model Deployment' },
      ]
    },
  ];

  // ===== 3-Layer Panel Layout =====
  showLeftPanel: boolean = true;
  showRightPanel: boolean = false;
  leftPanelWidth: number = 260;
  rightPanelWidth: number = 360;
  private _resizing: 'left' | 'right' | null = null;
  private _resizeStartX: number = 0;
  private _resizeStartWidth: number = 0;

  get datqDisplayColumns(): string[] {
    const pins = this.pinnedColumns.filter(c => this.datqColumns.includes(c));
    const rest = this.datqColumns.filter(c => !pins.includes(c));
    return [...pins, ...rest];
  }

  // ===== Unique-values dropdown filter helpers =====
  openFilterMenu(col: string): void {
    try {
      this.datqFilterMenuFor = col;
      this.datqFilterMenuSearch = '';
      this.ensureFilterKeys();
      // Debug: log context and attempt building unique values
      try {
        console.log('[UI] openFilterMenu', col, 'rows=', this.datqSummary ? this.datqSummary.length : 0);
      } catch {}
      this.buildUniqueValues(col);
    } catch {}
  }

  closeFilterMenu(): void {
    this.datqFilterMenuFor = null;
    this.datqFilterMenuSearch = '';
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(ev: MouseEvent): void {
    // Close the menu if clicking outside any filter menu element
    let hasMenu = false;
    const path = (ev as any).composedPath ? (ev as any).composedPath() as HTMLElement[] : null;
    if (path && Array.isArray(path)) {
      hasMenu = path.some((el: any) => el && el.classList && (el.classList.contains('filter-menu') || el.classList.contains('filter-trigger') || el.classList.contains('filter-input-wrap')));
    } else {
      // Fallback for browsers without composedPath (e.g., Safari)
      let node = ev.target as HTMLElement | null;
      const isInside = (el: HTMLElement | null): boolean => !!el && !!(el.classList && (el.classList.contains('filter-menu') || el.classList.contains('filter-trigger') || el.classList.contains('filter-input-wrap')));
      while (node) {
        if (isInside(node)) { hasMenu = true; break; }
        node = node.parentElement;
      }
    }
    if (!hasMenu) this.closeFilterMenu();
  }

  buildUniqueValues(col: string): void {
    try {
      if (!this.datqSummary || !this.datqSummary.length) {
        this.datqUniqueValuesCache[col] = [];
        try { console.warn('[UI] buildUniqueValues skipped; no datqSummary yet for', col); } catch {}
        return;
      }
      const counts = new Map<string, number>();
      for (const r of this.datqSummary) {
        const disp = String(this.displayCell(r, col));
        counts.set(disp, (counts.get(disp) || 0) + 1);
      }
      const arr = Array.from(counts.entries()).map(([value, count]) => ({ value, count }));
      arr.sort((a, b) => b.count - a.count || String(a.value).localeCompare(String(b.value)));
      this.datqUniqueValuesCache[col] = arr;
      try {
        console.log('[UI] buildUniqueValues ok', col, 'uniqueCount=', arr.length, 'sample=', arr.slice(0, 5));
      } catch {}
    } catch {
      this.datqUniqueValuesCache[col] = [];
    }
  }

  visibleUniqueValues(col: string): Array<{ value: string, count: number }> {
    // Fallback: if cache empty, try to build once on demand
    if (!this.datqUniqueValuesCache[col] || this.datqUniqueValuesCache[col].length === 0) {
      try { this.buildUniqueValues(col); } catch {}
    }
    const all = this.datqUniqueValuesCache[col] || [];
    const q = (this.datqFilterMenuSearch || '').toLowerCase();
    const onlySel = !!this.datqShowOnlySelected[col];
    const filteredByQuery = q ? all.filter(x => String(x.value).toLowerCase().includes(q)) : all;
    if (!onlySel) return filteredByQuery;
    const set = this.datqSelectedValues[col] || new Set<string>();
    return filteredByQuery.filter(x => set.has(String(x.value)));
  }

  isValueChecked(col: string, value: string): boolean {
    const set = this.datqSelectedValues[col];
    return !!set && set.has(value);
  }

  toggleValue(col: string, value: string, checked: boolean): void {
    this.ensureFilterKeys();
    const set = this.datqSelectedValues[col] || new Set<string>();
    if (checked) set.add(value); else set.delete(value);
    this.datqSelectedValues[col] = set;
  }

  selectAllValues(col: string): void {
    const arr = this.datqUniqueValuesCache[col] || [];
    const set = new Set<string>(arr.map(x => String(x.value)));
    this.datqSelectedValues[col] = set;
  }

  clearSelectedValues(col: string): void {
    this.datqSelectedValues[col] = new Set<string>();
  }

  applySelectedValues(): void {
    this.datqPage = 1;
    this.closeFilterMenu();
  }

  // Effective width for a column (user override or default)
  getColWidth(col: string): number {
    return this.colWidths[col] || this.colWidth(col);
  }

  // Wrapping toggle for table cells
  datqWrapCells: boolean = true;
  // Column resizing state
  colWidths: { [col: string]: number } = {};
  private resizingCol: string | null = null;
  private resizeStartX = 0;
  private resizeStartW = 0;

  // Preferred column widths to reduce overlap
  colWidth(col: string): number {
    if (!col) return 220;
    const c = String(col);
    if (c === 'Variable' || c === 'variable' || c === 'index') return 320;
    if (c === 'Model_Usage') return 140;  // Model_Usage column
    if (c === 'Datq_Decision') return 200;
    if (c === 'Variable_Type') return 160;
    if (c === 'PSI' || c === 'CSI') return 140;
    if (/_Train$/.test(c) || /_Test$/.test(c)) return 200;
    return 220;
  }

  // Reorder columns: Variable, Drop, PSI/Decision/Type/CSI, paired Train/Test changes, then remaining
  private reorderDatqColumns(): void {
    if (!this.datqColumns || this.datqColumns.length === 0) return;
    const cols = [...this.datqColumns];
    const has = (k: string) => cols.includes(k);
    const pickVar = has('Variable') ? 'Variable' : (has('variable') ? 'variable' : (has('index') ? 'index' : null));

    // Pair Train/Test columns by base name
    const trainTestBases = new Set<string>();
    for (const c of cols) {
      const m = c.match(/^(.*)_(Train|Test)$/);
      if (m) trainTestBases.add(m[1]);
    }
    const paired: string[] = [];
    const basesSorted = Array.from(trainTestBases).sort((a,b) => a.localeCompare(b));
    for (const b of basesSorted) {
      const t1 = `${b}_Train`;
      const t2 = `${b}_Test`;
      if (cols.includes(t1)) paired.push(t1);
      if (cols.includes(t2)) paired.push(t2);
    }

    // Add Model_Usage column after Variable (it won't come from backend)
    const fixed = [pickVar, 'Model_Usage', 'PSI', 'Datq_Decision', 'Variable_Type', 'CSI'].filter(x => !!x && (x === 'Model_Usage' || has(x as string))) as string[];
    const excluded = new Set<string>([...fixed, ...paired]);
    const rest = cols.filter(c => !excluded.has(c));
    this.datqColumns = [...fixed, ...paired, ...rest];
  }

  togglePinVariable(): void {
    const variableCol = this.datqColumns.includes('Variable') ? 'Variable' : (this.datqColumns.includes('variable') ? 'variable' : null);
    if (!variableCol) return;
    this.togglePin(variableCol);
  }

  // Get model usage for a variable
  getModelUsage(row: any): string {
    const key = this.variableKeyFromRow(row);
    const variable = row?.[key];
    if (!variable) return 'Yes';
    const varName = String(variable);
    return this.variableModelUsage[varName] ?? 'Yes';
  }

  // Set model usage for a variable
  setModelUsage(row: any, value: string): void {
    const key = this.variableKeyFromRow(row);
    const variable = row?.[key];
    if (!variable) return;
    const varName = String(variable);
    this.variableModelUsage[varName] = value;
    this.saveModelUsage();
    this.onPipelineConfigChanged();
  }

  /** Debounced auto-save when user modifies any pipeline config
   *  (purifier options, split settings, Model_Usage, encoding LOM, etc.) */
  onPipelineConfigChanged(): void {
    if (!this.activePipelineRunId) return; // no pipeline to save to yet
    if (!this.autosaveEnabled) {
      this._unsavedChanges = true;
      return;
    }
    if (this._pipelineConfigSaveTimer) clearTimeout(this._pipelineConfigSaveTimer);
    this._pipelineConfigSaveTimer = setTimeout(() => {
      const step = this.currentStep === 'data quality' ? 'data_quality' : this.currentStep;
      console.log('[Pipeline] Config changed, auto-saving at step:', step);
      this.saveCheckpoint(step);
    }, 800);
  }

  // ── Pipeline Commentary Notes (Jupyter-notebook style) ──

  onNoteChanged(position: string, content: string): void {
    this.pipelineNotes[position] = content;
    this.sharedService.updatePipelineNote(position, content);
    // Debounced auto-save
    if (this._noteSaveTimer) clearTimeout(this._noteSaveTimer);
    this._noteSaveTimer = setTimeout(() => {
      this.onPipelineConfigChanged();
    }, 1000);
  }

  toggleNoteEdit(position: string): void {
    if (this.editingNotePosition === position) {
      this.editingNotePosition = null;
    } else {
      this.editingNotePosition = position;
    }
  }

  deleteNote(position: string): void {
    delete this.pipelineNotes[position];
    this.sharedService.updatePipelineNote(position, '');
    this.editingNotePosition = null;
    this.onPipelineConfigChanged();
  }

  hasNote(position: string): boolean {
    return !!this.pipelineNotes[position]?.trim();
  }

  /** Toggle autosave on/off (persisted to localStorage) */
  toggleAutosave(): void {
    this.autosaveEnabled = !this.autosaveEnabled;
    this.sharedService.setAutosaveEnabled(this.autosaveEnabled);
    try { localStorage.setItem(this._autosaveKey, String(this.autosaveEnabled)); } catch {}
    console.log('[Pipeline] Autosave:', this.autosaveEnabled ? 'ON' : 'OFF');
    // If just turned on and there are unsaved changes, save immediately
    if (this.autosaveEnabled && this._unsavedChanges) {
      this.manualSave();
    }
  }

  /** Manual save — called by user clicking the save icon */
  manualSave(): void {
    if (!this.activePipelineRunId) return;
    const step = this.currentStep === 'data quality' ? 'data_quality' : this.currentStep;
    console.log('[Pipeline] Manual save at step:', step);
    this.saveCheckpoint(step, true);
    this._unsavedChanges = false;
  }

  /** Check if there are unsaved changes that need confirmation */
  hasUnsavedChanges(): boolean {
    return !this.autosaveEnabled && this._unsavedChanges;
  }

  // ===== Report Download =====

  downloadReportHtml(): void {
    if (!this.activePipelineRunId) return;
    this.dataService.downloadPipelineReport(this.activePipelineRunId).subscribe({
      next: (blob: Blob) => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${this.pipelineRunName || 'pipeline'}_report.html`;
        a.click();
        window.URL.revokeObjectURL(url);
      },
      error: (err: any) => {
        console.error('[Pipeline] Report download failed:', err);
        alert('Failed to download report.');
      }
    });
  }

  downloadReportPdf(): void {
    if (!this.activePipelineRunId) return;
    const url = this.dataService.getPipelineReportUrl(this.activePipelineRunId, 'print');
    window.open(url, '_blank');
  }

  // ===== Exit Confirmation =====

  @HostListener('window:beforeunload', ['$event'])
  onBeforeUnload(event: BeforeUnloadEvent): void {
    if (this.hasUnsavedChanges()) {
      event.preventDefault();
      event.returnValue = '';
    }
  }

  /** Called when user tries to navigate away (e.g. clicking Home, Login, etc.) */
  confirmExit(url: string): boolean {
    if (this.hasUnsavedChanges()) {
      this._pendingNavUrl = url;
      this.showExitDialog = true;
      return false; // block navigation
    }
    return true; // allow navigation
  }

  /** User chose 'Save & Exit' in the exit dialog */
  exitWithSave(): void {
    this.manualSave();
    this._unsavedChanges = false; // ensure dirty flag cleared before navigation
    this.showExitDialog = false;
    const url = this._pendingNavUrl;
    this._pendingNavUrl = null;
    if (url) {
      this.router.navigateByUrl(url);
    }
  }

  /** User chose 'Exit Without Saving' in the exit dialog */
  exitWithoutSave(): void {
    this._unsavedChanges = false; // clear dirty flag to allow navigation
    this.showExitDialog = false;
    const url = this._pendingNavUrl;
    this._pendingNavUrl = null;
    if (url) {
      this.router.navigateByUrl(url);
    }
  }

  /** User cancelled the exit dialog */
  cancelExit(): void {
    this.showExitDialog = false;
    this._pendingNavUrl = null;
  }

  // Save model usage to localStorage
  private saveModelUsage(): void {
    try {
      if (typeof localStorage === 'undefined') return;
      localStorage.setItem(this.modelUsageKey, JSON.stringify(this.variableModelUsage));
    } catch {}
  }

  // Load model usage from localStorage
  private loadModelUsage(): void {
    try {
      if (typeof localStorage === 'undefined') return;
      const saved = localStorage.getItem(this.modelUsageKey);
      if (saved) {
        this.variableModelUsage = JSON.parse(saved);
      }
    } catch {}
  }

  // Clear all model usage settings
  clearAllModelUsage(): void {
    this.variableModelUsage = {};
    this.saveModelUsage();
  }

  // Get list of variables marked as 'No' (excluded from model)
  getExcludedVariables(): string[] {
    return Object.keys(this.variableModelUsage).filter(v => this.variableModelUsage[v] === 'No');
  }

  // Initialize Model_Usage from Data Dictionary settings (passed via SharedService)
  private initializeFromDataDictionary(settings: { [variable: string]: string }): void {
    // ALWAYS sync from Data Dictionary (it's the source of truth)
    // This ensures that any changes made in Data Dictionary are reflected in Data Quality
    // Users can still override values in Data Quality after this initialization
    console.log('[Data Quality] Syncing Model_Usage from Data Dictionary:', settings);
    
    // Overwrite ALL values from Data Dictionary
    Object.keys(settings).forEach(variable => {
      this.variableModelUsage[variable] = settings[variable];
    });
    
    // Save the synced state
    this.saveModelUsage();
  }

  getPinnedStyle(col: string, type: 'header' | 'filter' | 'cell' = 'cell'): {[k: string]: any} {
    const idx = this.pinnedColumns.indexOf(col);
    const isVar = this.isVariableColumn(col);
    if (idx === -1 && !isVar) return {};
    // Left offset:
    // - for pinned columns: sum widths of preceding pinned columns
    // - for Variable column (if not pinned): sits right after all pinned columns
    let left = 0;
    if (idx >= 0) {
      for (let i = 0; i < idx; i++) {
        const c = this.pinnedColumns[i];
        left += this.getColWidth(c);
      }
    } else if (isVar) {
      for (let i = 0; i < this.pinnedColumns.length; i++) {
        const c = this.pinnedColumns[i];
        left += this.getColWidth(c);
      }
    }
    const z = type === 'header' ? 6 : (type === 'filter' ? 5 : 4);
    const w = this.getColWidth(col);
    return {
      position: 'sticky',
      left: left + 'px',
      zIndex: z,
      background: '#fff',
      minWidth: w + 'px',
      maxWidth: w + 'px'
    };
  }

  isVariableColumn(col: string): boolean {
    const varCol = this.datqColumns?.includes('Variable') ? 'Variable'
      : (this.datqColumns?.includes('variable') ? 'variable'
        : (this.datqColumns?.includes('index') ? 'index' : null));
    return !!varCol && col === varCol;
  }

  openFeatureCardFromDatq(variableName: string): void {
    try {
      if (!variableName) return;
      const fileId = this.currentFileId != null ? String(this.currentFileId) : null;
      if (!fileId) {
        console.warn('openFeatureCardFromDatq: missing currentFileId');
      }
      const openWithFeatures = (features: Array<{ Feature_Name: string; Feature_Description: string }>) => {
        const row = (this.datqSummary || []).find(r => String(r['Variable'] || r['variable'] || r['index']) === String(variableName));
        const qualitySummary = row ? { ...row } : null;
        const processedFile = this.processedFilePath || null;
        const dateColumn = this.splitDateColumn || (this.dateColumns && this.dateColumns.length ? this.dateColumns[0] : null);
        this.dialog.open(FeatureCardComponent, {
          width: '900px',
          data: {
            fileId: fileId || '',
            columnName: String(variableName),
            features: features,
            processedFile: processedFile || undefined,
            encodedFile: this.encodedFilePath || undefined,
            dateColumn: dateColumn || undefined,
            qualitySummary: qualitySummary || undefined,
          }
        });
      };

      const buildFromCache = (): Array<{ Feature_Name: string; Feature_Description: string }> => {
        if (this.dataDictionaryCache && this.dataDictionaryCache.length) {
          return this.dataDictionaryCache
            .map(item => ({
              Feature_Name: String(item?.Feature_Name || ''),
              Feature_Description: String(item?.Feature_Description || 'No description available')
            }))
            .filter(x => !!x.Feature_Name);
        }
        // Fallback to names only from datqSummary
        return (this.datqSummary || [])
          .map(r => {
            const name = r['Variable'] ?? r['variable'] ?? r['index'];
            return { Feature_Name: String(name), Feature_Description: 'No description available' };
          })
          .filter(x => !!x.Feature_Name);
      };

      const cacheHasDescriptions = Array.isArray(this.dataDictionaryCache) && this.dataDictionaryCache.some(x => !!x?.Feature_Description);
      if (!cacheHasDescriptions && fileId) {
        // Refresh dictionary to get latest descriptions before opening
        this.dataService.getDataDictionary(fileId).subscribe({
          next: (list: any[]) => {
            this.dataDictionaryCache = Array.isArray(list) ? list : [];
            this.sharedService.setDataDictionaryCache(this.dataDictionaryCache);
            openWithFeatures(buildFromCache());
          },
          error: () => {
            openWithFeatures(buildFromCache());
          }
        });
      } else {
        openWithFeatures(buildFromCache());
      }
    } catch (e) {
      console.error('Failed to open Feature Card from Data Quality:', e);
    }
  }

  selectedCount(col: string): number {
    const set = this.datqSelectedValues?.[col];
    return set ? set.size : 0;
  }

  uniqueCount(col: string): number {
    const arr = this.datqUniqueValuesCache?.[col];
    return Array.isArray(arr) ? arr.length : 0;
  }

  get datqTotal(): number { return this.datqFilteredRows ? this.datqFilteredRows.length : 0; }
  get datqTotalPages(): number { return this.datqPageSize > 0 ? Math.max(1, Math.ceil(this.datqTotal / this.datqPageSize)) : 1; }
  get datqFilteredRows(): any[] {
    if (!this.datqSummary) return [];
    const gf = (this.datqGlobalFilter || '').toLowerCase();
    const colFilters = this.datqColumnFilters || {};
    const selectedSets = this.datqSelectedValues || {};
    return this.datqSummary.filter(row => {
      // Global filter: any cell contains string
      const passGlobal = !gf || this.datqColumns.some(c => (row[c] !== null && row[c] !== undefined && String(row[c]).toLowerCase().includes(gf)));
      if (!passGlobal) return false;
      // Column filters: each specified column must match
      for (const c of this.datqColumns) {
        const cf = (colFilters[c] || '').toLowerCase();
        if (!cf) continue;
        const cell = row[c];
        const text = (cell === null || cell === undefined) ? '' : String(cell).toLowerCase();
        if (!text.includes(cf)) return false;
      }
      // Unique-values selections: if any selected for a column, the display value must be in the set
      for (const c of this.datqColumns) {
        const set = selectedSets[c];
        if (set && set.size > 0) {
          const disp = String(this.displayCell(row, c));
          if (!set.has(disp)) return false;
        }
      }
      return true;
    });
  }

  get datqSortedRows(): any[] {
    const rows = [...this.datqFilteredRows];
    if (!this.datqSortColumn) return rows;
    const col = this.datqSortColumn;
    const dir = this.datqSortDir === 'asc' ? 1 : -1;
    const isNumeric = rows.every(r => r[col] === null || r[col] === undefined || (!isNaN(parseFloat(r[col])) && isFinite(Number(r[col]))));
    rows.sort((a, b) => {
      const va = a[col];
      const vb = b[col];
      if (va == null && vb == null) return 0;
      if (va == null) return 1; // nulls last
      if (vb == null) return -1;
      if (isNumeric) {
        const na = Number(va);
        const nb = Number(vb);
        return (na - nb) * dir;
      }
      const sa = String(va).toLowerCase();
      const sb = String(vb).toLowerCase();
      if (sa < sb) return -1 * dir;
      if (sa > sb) return 1 * dir;
      return 0;
    });
    return rows;
  }

  get datqPagedRows(): any[] {
    const rows = this.datqSortedRows;
    const start = (this.datqPage - 1) * this.datqPageSize;
    return rows.slice(start, start + this.datqPageSize);
  }

  // Detail report state
  datqSelectedVariable: string | null = null;
  datqDetail: any | null = null;
  datqDetailColumns: string[] = [];
  datqDetailLoading: boolean = false;
  detailGlobalFilter: string = '';
  detailColumnFilters: { [key: string]: string } = {};
  detailSortColumn: string | null = null;
  detailSortDir: 'asc' | 'desc' = 'asc';

  purifierOptions: PurifierOption[] = [
    { id: 1, name: 'Column-wise duplicate drop' },
    { id: 2, name: 'Row-wise duplicate drop' },
    { id: 3, name: 'Zero-variance drop' },
    { id: 4, name: 'Perfect-correlation drop' },
    { id: 5, name: 'Corr-drop threshold = 0.95', group: 1 },
    { id: 6, name: 'Corr-drop threshold = 0.90', group: 1 },
    { id: 7, name: 'Corr-drop threshold = 0.85', group: 1 },
    { id: 8, name: 'Corr-drop threshold = 0.80', group: 1 },
    { id: 9, name: 'Corr-drop threshold = 0.75', group: 1 },
    { id: 10, name: 'Sparsity-drop threshold = 0.99', group: 2 },
    { id: 11, name: 'Sparsity-drop threshold = 0.95', group: 2 },
    { id: 12, name: 'Sparsity-drop threshold = 0.90', group: 2 },
    { id: 13, name: 'Sparsity-drop threshold = 0.85', group: 2 },
    { id: 14, name: 'Sparsity-drop threshold = 0.80', group: 2 },
    { id: 15, name: 'Sparsity-drop threshold = 0.75', group: 2 },
    { id: 16, name: 'Missing-drop threshold = 0.99', group: 3 },
    { id: 17, name: 'Missing-drop threshold = 0.95', group: 3 },
    { id: 18, name: 'Missing-drop threshold = 0.90', group: 3 },
    { id: 19, name: 'Missing-drop threshold = 0.85', group: 3 },
    { id: 20, name: 'Missing-drop threshold = 0.80', group: 3 },
    { id: 21, name: 'Missing-drop threshold = 0.75', group: 3 },
    { id: 22, name: '[Sparsity+Missing]-drop threshold = 0.99', group: 4 },
    { id: 23, name: '[Sparsity+Missing]-drop threshold = 0.95', group: 4 },
    { id: 24, name: '[Sparsity+Missing]-drop threshold = 0.90', group: 4 },
    { id: 25, name: '[Sparsity+Missing]-drop threshold = 0.85', group: 4 },
    { id: 26, name: '[Sparsity+Missing]-drop threshold = 0.80', group: 4 },
    { id: 27, name: '[Sparsity+Missing]-drop threshold = 0.75', group: 4 },
    { id: 28, name: 'Outlier-cleaning [lower-upper] quantiles = [0.01-0.99]', group: 5 },
    { id: 29, name: 'Outlier-cleaning [lower-upper] quantiles = [0.05-0.95]', group: 5 },
    { id: 30, name: 'Outlier-cleaning [lower-upper] quantiles = [0.10-0.90]', group: 5 },
    { id: 31, name: 'Outlier Cleaning (Categorical Features) threshold = 0.001', group: 6 },
    { id: 32, name: 'Outlier Cleaning (Categorical Features) threshold = 0.005', group: 6 },
    { id: 33, name: 'Outlier Cleaning (Categorical Features) threshold = 0.01', group: 6 },
    { id: 34, name: 'Outlier Cleaning (Categorical Features) threshold = 0.05', group: 6 },
  ];

  private defaultOptionIds: number[] = [1, 2, 3, 4, 7, 11, 17, 23, 28, 32];
  selectedOptions: PurifierOption[] = this.purifierOptions.filter(o => this.defaultOptionIds.includes(o.id));

  constructor(private router: Router, private sharedService: SharedService, private dataService: DataService, private dialog: MatDialog, public aiAssistant: AiAssistantService) {}

  // ===== 3-Layer Panel Toggle & Resize =====
  toggleLeftPanel(): void {
    this.showLeftPanel = !this.showLeftPanel;
  }

  toggleRightPanel(): void {
    this.showRightPanel = !this.showRightPanel;
    if (this.showRightPanel) {
      this.aiAssistant.openPanel();
    } else {
      this.aiAssistant.closePanel();
    }
  }

  onLeftResizeStart(event: MouseEvent): void {
    event.preventDefault();
    this._resizing = 'left';
    this._resizeStartX = event.clientX;
    this._resizeStartWidth = this.leftPanelWidth;
    document.addEventListener('mousemove', this._onResizeMove);
    document.addEventListener('mouseup', this._onResizeEnd);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }

  onRightResizeStart(event: MouseEvent): void {
    event.preventDefault();
    this._resizing = 'right';
    this._resizeStartX = event.clientX;
    this._resizeStartWidth = this.rightPanelWidth;
    document.addEventListener('mousemove', this._onResizeMove);
    document.addEventListener('mouseup', this._onResizeEnd);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }

  private _onResizeMove = (event: MouseEvent): void => {
    if (!this._resizing) return;
    const dx = event.clientX - this._resizeStartX;
    if (this._resizing === 'left') {
      this.leftPanelWidth = Math.max(160, Math.min(400, this._resizeStartWidth + dx));
    } else if (this._resizing === 'right') {
      this.rightPanelWidth = Math.max(280, Math.min(600, this._resizeStartWidth - dx));
    }
  };

  private _onResizeEnd = (): void => {
    this._resizing = null;
    document.removeEventListener('mousemove', this._onResizeMove);
    document.removeEventListener('mouseup', this._onResizeEnd);
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  };

  getPipelineConfig(): any {
    return {
      pipeline_type: this.selectedPipeline || 'boosting',
      target_definition: this.targetDefinition || '',
      current_step: this.currentStep,
      detailed_step: this.detailedStep,
      preprocessing_initiated: this.preprocessingInitiated,
      modeling_available: this.modelingAvailable,
      selected_purifier_steps: this.selectedOptions.map(o => o.name),
      split_strategy: this.splitStrategy,
      split_details: this.splitStrategy === 'oot'
        ? { mode: this.ootMode, oot_percent: this.ootPercent, date_column: this.splitDateColumn, cutoff: this.splitCutoff }
        : { oos_percent: this.oosPercent },
      rows_before: this.rowCountBefore,
      rows_after: this.rowCountAfter,
      rows_removed: this.rowsRemovedTotal,
      total_columns_dropped: this.droppedTotalCount(),
      dropped_by_step: this.droppedColumnsByStep,
      model_usage_exclusions: Object.entries(this.variableModelUsage || {})
        .filter(([_, v]) => String(v).toLowerCase() === 'no')
        .map(([k]) => k),
      data_dictionary: (this.dataDictionaryCache || []).map((d: any) => ({
        Feature_Name: d?.Feature_Name,
        Data_Type: d?.Data_Type,
        Level_of_Measurement: d?.Level_of_Measurement,
        Unique_Values: d?.['#_of_Unique_Value'],
        Missing_Ratio: d?.Missing_Ratio,
        Mode_Ratio: d?.Mode_Ratio,
        Model_Usage_YN: d?.Model_Usage_YN,
        Feature_Description: d?.Feature_Description || null,
      })),
      encoding_plan: (this.encodingPlan || []).map((e: any) => ({
        feature: e?.feature,
        lom: e?.user_lom || e?.lom,
        nunique: e?.nunique,
        strategy: e?.fallback_strategy,
        needs_ranking: e?.needs_ranking,
      })),
      feature_stats_before: this.featureStatsBefore,
      feature_stats_after: this.featureStatsAfter,
      preprocessing_step_stats: this.preprocessingStepStats,
      pipeline_notes: this.pipelineNotes || {},
    };
  }

  /** Build a full cumulative AI context snapshot from ALL pipeline data available so far. */
  buildFullAiContext(): any {
    const ctx: any = {
      pipeline_config: this.getPipelineConfig(),
    };
    // Data Quality summary (available after preprocessing)
    if (this.datqSummary && this.datqSummary.length > 0) {
      ctx.summary = this.datqSummary;
      ctx.purifier_summary = {
        rows_before: this.rowCountBefore,
        rows_after: this.rowCountAfter,
        rows_removed: this.rowsRemovedTotal,
        total_columns_dropped: this.droppedTotalCount(),
        dropped_by_step: this.droppedColumnsByStep,
      };
      ctx.model_usage = this.variableModelUsage;
      ctx.split_validation = this.splitValidation;
    }
    return ctx;
  }

  /** Push current cumulative AI context to SharedService so the chat panel always has it. */
  pushAiContext(): void {
    // Merge model-development context with any modeling-level context already in SharedService
    const existingCtx = this.sharedService.getAiCumulativeContext() || {};
    const myCtx = this.buildFullAiContext();
    // model-development owns pipeline_config and data quality; modeling owns cv, shap, sfs, etc.
    const merged = { ...existingCtx, ...myCtx, pipeline_config: { ...(existingCtx.pipeline_config || {}), ...myCtx.pipeline_config } };
    this.sharedService.setAiCumulativeContext(merged);
    // Also push to Redis cache for on-demand tool calling
    this.pushToAiCache();
  }

  /** Push pipeline artifacts to the backend Redis cache for LLM tool calls. */
  private pushToAiCache(): void {
    if (this.currentFileId == null) return;
    const artifacts: { [key: string]: any } = {};
    // Pipeline config
    artifacts['pipeline_config'] = this.getPipelineConfig();
    // Split validation
    if (this.splitValidation) {
      artifacts['split_validation'] = this.splitValidation;
    }
    // Data quality summary
    if (this.datqSummary && this.datqSummary.length > 0) {
      artifacts['dq_summary'] = this.datqSummary;
    }
    // Feature stats (before/after preprocessing)
    if (this.featureStatsBefore || this.featureStatsAfter) {
      artifacts['feature_stats'] = {
        before: this.featureStatsBefore || {},
        after: this.featureStatsAfter || {},
      };
    }
    // Data dictionary
    if (this.dataDictionaryCache && this.dataDictionaryCache.length > 0) {
      artifacts['data_dictionary'] = this.dataDictionaryCache;
    }
    // Pipeline notes
    const notes = this.sharedService.getPipelineNotes();
    if (notes && Object.keys(notes).length > 0) {
      artifacts['pipeline_notes'] = notes;
    }
    // Fire and forget — cache push is best-effort
    this.dataService.pushAiCache(this.currentFileId, artifacts).subscribe({
      error: (err: any) => console.warn('[AI Cache] push failed:', err),
    });
  }

  requestAiSupport(context: any, section: string, prompt: string): void {
    this.showRightPanel = true;
    const sendRequest = () => {
      const enriched = { ...context, pipeline_config: this.getPipelineConfig() };
      this.aiAssistant.requestSupport(enriched, section, prompt);
    };
    // Ensure data dictionary cache has descriptions before sending to AI
    const hasDescriptions = Array.isArray(this.dataDictionaryCache) &&
      this.dataDictionaryCache.some(x => !!x?.Feature_Description);
    if (!hasDescriptions && this.currentFileId != null) {
      this.dataService.getDataDictionary(String(this.currentFileId)).subscribe({
        next: (list: any[]) => {
          this.dataDictionaryCache = Array.isArray(list) ? list : [];
          this.sharedService.setDataDictionaryCache(this.dataDictionaryCache);
          sendRequest();
        },
        error: () => sendRequest(),
      });
    } else {
      sendRequest();
    }
  }

  requestDatqAiSupport(): void {
    const context = {
      summary: this.datqSummary,
      purifier_summary: {
        rows_before: this.rowCountBefore,
        rows_after: this.rowCountAfter,
        rows_removed: this.rowsRemovedTotal,
        total_columns_dropped: this.droppedTotalCount(),
        dropped_by_step: this.droppedColumnsByStep
      },
      model_usage: this.variableModelUsage,
      split_validation: this.splitValidation
    };
    const prompt = 'Analyze this Data Quality Summary. Compare before vs after preprocessing treatment effects (rows removed, columns dropped per step). Highlight concerns about PSI stability, missing values, distribution shifts, and features to watch for the next encoding/modeling steps.';
    this.requestAiSupport(context, 'data_quality', prompt);
  }

  /** v2.41.0 — Dedicated AI Support trigger for the Data Purifier Summary card.
   *
   * Mirrors requestDatqAiSupport() but scopes the context to purifier
   * outputs only: rows-removed totals + per-step dropped columns.
   * Keeping scope narrow avoids drowning the LLM in DQ-summary noise
   * when the user is specifically asking about purifier behavior. */
  requestPurifierAiSupport(): void {
    const context = {
      purifier_summary: {
        rows_before: this.rowCountBefore,
        rows_after: this.rowCountAfter,
        rows_removed: this.rowsRemovedTotal,
        total_columns_dropped: this.droppedTotalCount(),
        dropped_by_step: this.droppedColumnsByStep
      }
    };
    const prompt = 'Analyze the Data Purifier Summary. Review which preprocessing steps ran, how many rows were removed in each step, and which columns were dropped (sparsity, missingness, collinearity, outliers, dedup). Flag any step that removed an unexpectedly large fraction of rows or columns. Suggest whether specific purifier_options should be tightened, relaxed, added, or removed before encoding — and call out features that may have been dropped that the user might want to keep.';
    this.requestAiSupport(context, 'data_purifier', prompt);
  }

  ngAfterViewChecked(): void {
    if (this.splitValidation && !this._splitChartDrawn && this.splitValidationCanvas) {
      this._splitChartDrawn = true;
      setTimeout(() => this.drawSplitValidationChart(), 0);
    }
  }

  ngOnInit() {
    // Restore autosave preference from localStorage
    try {
      const stored = localStorage.getItem(this._autosaveKey);
      if (stored !== null) {
        this.autosaveEnabled = stored === 'true';
        this.sharedService.setAutosaveEnabled(this.autosaveEnabled);
      }
    } catch {}

    // Sync AI assistant panel open state from service (e.g. when child components open panel)
    this.subscription.add(
      this.aiAssistant.panelOpen$.subscribe(open => {
        this.showRightPanel = open;
      })
    );

    // v2.26.0+: subscribe to AI assistant Data-Purifier-start requests.
    // When the AI emits a start_data_purifier action, the chat panel
    // broadcasts the validated config here.  We mirror onto the
    // selectedOptions and split form fields, then call the existing
    // proceedFromPreprocessing() method — the exact code path a user's
    // manual "Run Preprocessing" button click takes, including
    // activeProcess registration and the data-quality-summary auto-nav.
    this.subscription.add(
      this.sharedService.dataPurifierStartRequests$.subscribe((req) => {
        if (!req || typeof req !== 'object') return;
        // Patch purifier checkbox selection if the AI provided IDs;
        // otherwise leave whatever is currently selected.  The AI
        // payload uses integer IDs that match purifierOptions[].id.
        if (Array.isArray(req.purifier_options) && req.purifier_options.length > 0) {
          const idSet = new Set<number>(req.purifier_options.map((id: number) => Number(id)));
          this.selectedOptions = this.purifierOptions.filter(o => idSet.has(o.id));
        }
        // Patch split form fields if the AI provided them.
        if (req.split && typeof req.split === 'object') {
          if (req.split.strategy === 'random' || req.split.strategy === 'oot') {
            this.splitStrategy = req.split.strategy;
          }
          if (typeof req.split.percent === 'number' && req.split.percent > 0 && req.split.percent < 100) {
            // Random uses oosPercent; OOT-percent mode uses ootPercent.
            // We patch both to the same value so the active mode picks it up.
            this.oosPercent = req.split.percent;
            this.ootPercent = req.split.percent;
          }
          if (req.split.strategy === 'oot') {
            if (typeof req.split.date_column === 'string' && req.split.date_column.trim()) {
              this.splitDateColumn = req.split.date_column.trim();
            }
            if (typeof req.split.cutoff === 'string' && req.split.cutoff.trim()) {
              this.splitCutoff = req.split.cutoff.trim();
              this.ootMode = 'cutoff';
            } else {
              this.ootMode = 'percent';
            }
          }
        }
        // Defer the actual preprocessing kickoff to the next tick so
        // pending form-binding change detection settles before
        // proceedFromPreprocessing() reads the field values (matches
        // the same setTimeout(0) pattern used elsewhere for AI-driven
        // pipeline-step kickoffs).
        setTimeout(() => this.proceedFromPreprocessing(), 0);
      })
    );

    // v2.28.0+: subscribe to AI assistant Purifier-selection updates.
    // Distinct from dataPurifierStartRequests$ above — this stream
    // patches the checkbox selection WITHOUT firing the run.  The
    // user reviews the new selection in the form, then clicks Run
    // Preprocessing themselves (or asks the AI to run it in the next
    // turn).
    //
    // CRITICAL: this handler MUST NOT call proceedFromPreprocessing().
    // The whole point of update_purifier_selection vs
    // start_data_purifier is the user-review intermediate step.  A
    // regression here re-introduces the v2.27.x UX gap (no preview
    // before commit).  Karma spec guards this.
    //
    // Supported forms (matches the backend handler + emit signature):
    //   • WHOLESALE: replace selectedOptions with the new ID set.
    //   • DIFF:      mutate selectedOptions by adding/removing IDs
    //                relative to the current state.
    // After the patch we re-push to the AI Redis cache so the AI's
    // NEXT turn sees the updated state without having to re-call
    // get_pipeline_config.
    this.subscription.add(
      this.sharedService.purifierSelectionUpdates$.subscribe((req) => {
        if (!req || typeof req !== 'object') return;

        if (req.form === 'wholesale') {
          // Wholesale-replace: empty array means "clear everything".
          // Non-empty: filter the catalog down to the requested IDs.
          if (!Array.isArray(req.purifier_options)) return;
          const idSet = new Set<number>(
            req.purifier_options.map((id: number) => Number(id)),
          );
          this.selectedOptions = this.purifierOptions.filter(o => idSet.has(o.id));
        } else if (req.form === 'diff') {
          // Diff: apply add then remove against the current selection.
          // Sequence (add → remove) matters when an ID appears in both,
          // but the backend already rejects that case so by the time
          // we get here add and remove are disjoint.
          const current = new Set<number>(this.selectedOptions.map(o => o.id));
          (req.add || []).forEach((id: number) => current.add(Number(id)));
          (req.remove || []).forEach((id: number) => current.delete(Number(id)));
          this.selectedOptions = this.purifierOptions.filter(o => current.has(o.id));
        } else {
          // 'noop' (or anything else) — nothing to patch.
          return;
        }

        // Mirror the new selection into the SharedService cache so
        // any other component reading current state (e.g. autosave
        // serializer, save-progress dialog) sees the AI's change.
        const newIds = this.selectedOptions.map(o => o.id);
        this.sharedService.setSelectedPurifierOptions(newIds);

        // Re-push to AI Redis so the AI's next turn sees the updated
        // checkbox state on-screen.  Matches the same convention used
        // by update_metadata + set_ordinal_ranking handlers — the AI
        // should always be able to read the current UI state via tool
        // calls without us having to re-fetch the dictionary.
        //
        // `getPipelineConfig()` already serializes `selectedOptions`
        // via its `selected_purifier_steps` field, which is exactly
        // what the backend `_handle_get_pipeline_config` reads — so
        // by re-calling it AFTER mutating `selectedOptions` we get a
        // fresh snapshot for free.
        if (this.currentFileId != null) {
          const artifacts: any = {
            pipeline_config: this.getPipelineConfig(),
          };
          this.dataService.pushAiCache(this.currentFileId, artifacts).subscribe({
            next: () => { /* silent success */ },
            error: (err: any) => console.warn('AI cache re-push failed (non-fatal):', err),
          });
        }
        // NO proceedFromPreprocessing() call — that is the whole
        // distinction between this stream and dataPurifierStartRequests$.
      })
    );

    // v2.26.0+: subscribe to AI assistant Apply-Encoding requests.
    // When the AI emits an apply_encoding action, the chat panel
    // broadcasts the validated config here.  We patch encodingUseNative
    // if specified, then call the existing applyEncoding() method —
    // the same code path a user's manual "Apply Encoding" button
    // click takes.  The component's current encodingPlan array
    // (already populated/edited by earlier update_metadata +
    // set_ordinal_ranking actions) is what gets applied.
    this.subscription.add(
      this.sharedService.encodingApplyRequests$.subscribe((req) => {
        if (!req || typeof req !== 'object') return;
        if (typeof req.use_native === 'boolean') {
          this.encodingUseNative = req.use_native;
        }
        setTimeout(() => this.applyEncoding(), 0);
      })
    );

    // Baseline reset to prevent stale state causing steps to appear out of order
    this.sharedService.setStarted(false);
    this.sharedService.setPreprocessingInitiated(false);
    this.sharedService.setPreprocessingRunResult(null);
    this.sharedService.setProcessedFilePath(null);
    this.sharedService.setCurrentFileId(null);
    this.currentStep = 'declaration';
    this.modelingAvailable = false;
    this.preprocessingAvailable = false;

    this.subscription.add(
      this.sharedService.currentFileId$.subscribe((id: number | null) => {
        // Mark dirty when file changes while autosave is off
        if (id !== null && id !== this.currentFileId && !this.autosaveEnabled) {
          this._unsavedChanges = true;
        }
        this.currentFileId = id;
        this.computePreprocessingAvailable();
        // Load datetime columns from data dictionary (preferred)
        if (id !== null) {
          try {
            this.dataService.getDataDictionary(String(id)).subscribe({
              next: (list: any[]) => {
                const rows = Array.isArray(list) ? list : [];
                // Cache full dictionary for FeatureCard (Feature_Description, Level_of_Measurement, etc.)
                this.dataDictionaryCache = rows;
                this.sharedService.setDataDictionaryCache(rows);
                // Push data dictionary to Redis cache for AI tool calls
                if (rows.length > 0 && this.currentFileId != null) {
                  this.dataService.pushAiCache(this.currentFileId, { data_dictionary: rows }).subscribe({
                    error: (err: any) => console.warn('[AI Cache] data dictionary push failed:', err),
                  });
                }
                const dtCols = rows
                  .filter(item => {
                    const lom = String(item?.Level_of_Measurement || '').toLowerCase();
                    const dtype = String(item?.Data_Type || '').toLowerCase();
                    const name = String(item?.Feature_Name || '');
                    return lom === 'datetime' || dtype.includes('date') || /date|time|dt/i.test(name);
                  })
                  .map(item => String(item.Feature_Name));
                this.dateColumns = Array.from(new Set(dtCols));
              },
              error: () => {
                // Fallback to preview-based heuristic if dictionary fails
                this.dataService.getDataPreview(String(id)).subscribe({
                  next: (resp: any) => {
                    try {
                      const types = resp?.data_types || {};
                      const cols = Object.keys(types).filter(k => String(types[k]).toLowerCase().includes('date') || /date|time|dt/i.test(k));
                      this.dateColumns = cols;
                    } catch { this.dateColumns = []; }
                  },
                  error: () => { this.dateColumns = []; }
                });
              }
            });
          } catch { this.dateColumns = []; }
        }
      })
    );

    // Track pipeline start
    this.subscription.add(
      this.sharedService.isStarted$.subscribe((started: boolean) => {
        // Mark dirty when pipeline starts while autosave is off
        if (started && !this.isStarted && !this.autosaveEnabled) {
          this._unsavedChanges = true;
        }
        this.isStarted = started;
        this.computePreprocessingAvailable();
      })
    );

    // Do not auto-enable modeling on preprocessing result; user will click "Proceed to Modeling"
    // Guard: only reset modelingAvailable if we haven't already entered modeling
    this.subscription.add(
      this.sharedService.preprocessingRunResult$.subscribe((_result: any) => {
        if (this.currentStep !== 'modeling' && this.currentStep !== 'sfs') {
          this.modelingAvailable = false;
        }
      })
    );

    // Track when user explicitly moves from Declaration to Preprocessing
    this.subscription.add(
      this.sharedService.preprocessingInitiated$.subscribe((initiated: boolean) => {
        // Mark dirty when preprocessing initiated while autosave is off
        if (initiated && !this.preprocessingInitiated && !this.autosaveEnabled) {
          this._unsavedChanges = true;
        }
        this.preprocessingInitiated = initiated;
        this.computePreprocessingAvailable();
        // Only transition to preprocessing if we're still at declaration (prevent regression)
        if (initiated && this.currentStep === 'declaration') {
          this.currentStep = 'preprocessing';
          this.detailedStep = '2a_purifier_declaration';
          // Auto-save checkpoint: preprocessing
          this.saveCheckpoint('preprocessing');
        }
      })
    );

    // Track processed file path for detail API
    this.subscription.add(
      this.sharedService.processedFilePath$.subscribe((p: string | null) => {
        this.processedFilePath = p;
      })
    );

    // Track Model_Usage settings from Data Dictionary to initialize Data Quality table
    this.subscription.add(
      this.sharedService.modelUsageSettings$.subscribe((settings: { [variable: string]: string } | null) => {
        if (settings) {
          // Initialize Data Quality Model_Usage with values from Data Dictionary
          this.initializeFromDataDictionary(settings);
        }
      })
    );

    // Subscribe to checkpoint triggers from child components (declaration + modeling)
    this.subscription.add(
      this.sharedService.triggerCheckpoint$.subscribe((substep: string) => {
        console.log('[Pipeline] Checkpoint trigger (Subject):', substep);
        let step: string;
        if (substep.startsWith('decl_')) {
          step = 'declaration';
          // Map declaration substeps to detailed taxonomy
          if (substep === 'decl_data_imported') this.detailedStep = '1b_data_declaration';
          else if (substep === 'decl_dictionary_generated') this.detailedStep = '1c_dictionary_declaration';
        } else if (substep.startsWith('sfs_')) {
          step = 'sfs';
          this.detailedStep = this.mapModelingSubstepToDetailed(substep);
        } else {
          step = 'modeling';
          this.detailedStep = this.mapModelingSubstepToDetailed(substep);
        }
        this.saveCheckpoint(step);
      })
    );

    // Sync pipeline notes from SharedService (modeling child may update notes)
    this.subscription.add(
      this.sharedService.pipelineNotes$.subscribe((notes: { [position: string]: string }) => {
        this.pipelineNotes = notes;
      })
    );

    // Belt-and-suspenders: also subscribe to modelingCheckpoint$ BehaviorSubject
    // and auto-save whenever the modeling substep advances.
    // This catches cases where the Subject trigger might be missed.
    this.subscription.add(
      this.sharedService.modelingCheckpoint$.subscribe((state: any) => {
        if (!state || !state.substep || !this.activePipelineRunId) return;
        const substep = state.substep;
        // Only save if substep actually changed (avoid duplicate saves)
        if (substep !== this._lastModelingSubstep) {
          console.log(`[Pipeline] modelingCheckpoint$ auto-save: ${this._lastModelingSubstep} -> ${substep}`);
          this._lastModelingSubstep = substep;
          const step = substep.startsWith('sfs_') ? 'sfs' : 'modeling';
          this.detailedStep = this.mapModelingSubstepToDetailed(substep);
          this.saveCheckpoint(step);
        }
      })
    );

    // Load persisted preferences (page size, pinned columns, sort) and widths
    this.loadDatqPrefs();
    this.loadDatqWidths();
    this.loadModelUsage();
  }

  // After user reviews the Data Quality summary, proceed to Modeling section
  goToModeling(): void {
    // Push final Model_Usage settings to SharedService for modeling phase
    this.sharedService.setModelUsageSettings(this.variableModelUsage);
    this.modelingAvailable = true;
    this.currentStep = 'modeling';
    this.detailedStep = '3a_encoding';
    // Auto-save checkpoint: modeling
    this.saveCheckpoint('modeling');
    // Smooth scroll to modeling section
    setTimeout(() => {
      try {
        const el = document.getElementById('modeling-anchor');
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      } catch (e) {
        console.warn('Scroll failed:', e);
      }
    }, 0);
  }

  changeDatqPageSize(event: any): void {
    const value = Number(event?.target?.value ?? this.datqPageSize);
    this.datqPageSize = value > 0 ? value : 25;
    this.datqPage = 1;
    this.saveDatqPrefs();
  }

  prevDatqPage(): void {
    if (this.datqPage > 1) this.datqPage--;
  }

  nextDatqPage(): void {
    if (this.datqPage < this.datqTotalPages) this.datqPage++;
  }

  onSort(col: string): void {
    if (this.datqSortColumn === col) {
      this.datqSortDir = this.datqSortDir === 'asc' ? 'desc' : 'asc';
    } else {
      this.datqSortColumn = col;
      this.datqSortDir = 'asc';
    }
    this.datqPage = 1;
    this.saveDatqPrefs();
  }

  onFilterChange(): void {
    this.ensureFilterKeys();
    this.datqPage = 1;
  }

  clearFilters(): void {
    this.datqGlobalFilter = '';
    this.datqColumnFilters = {};
    this.ensureFilterKeys();
    this.datqPage = 1;
  }

  private ensureFilterKeys(): void {
    if (!this.datqColumns) return;
    for (const c of this.datqColumns) {
      if (!(c in this.datqColumnFilters)) this.datqColumnFilters[c] = '';
      if (!(c in this.datqSelectedValues)) this.datqSelectedValues[c] = new Set<string>();
      if (!(c in this.datqShowOnlySelected)) this.datqShowOnlySelected[c] = false;
    }
  }

  private ensureDetailFilterKeys(): void {
    if (!this.datqDetailColumns) return;
    for (const c of this.datqDetailColumns) {
      if (!(c in this.detailColumnFilters)) this.detailColumnFilters[c] = '';
    }
  }

  get datqDetailFilteredRows(): any[] {
    const rows: any[] = Array.isArray(this.datqDetail?.psi_table) ? this.datqDetail!.psi_table : [];
    if (!rows.length) return [];
    const gf = (this.detailGlobalFilter || '').toLowerCase();
    const colFilters = this.detailColumnFilters || {};
    const cols = this.datqDetailColumns || [];
    return rows.filter(row => {
      const passGlobal = !gf || cols.some(c => (row[c] !== null && row[c] !== undefined && String(row[c]).toLowerCase().includes(gf)));
      if (!passGlobal) return false;
      for (const c of cols) {
        const cf = (colFilters[c] || '').toLowerCase();
        if (!cf) continue;
        const cell = row[c];
        const text = (cell === null || cell === undefined) ? '' : String(cell).toLowerCase();
        if (!text.includes(cf)) return false;
      }
      return true;
    });
  }

  get datqDetailSortedRows(): any[] {
    const rows = [...this.datqDetailFilteredRows];
    if (!this.detailSortColumn) return rows;
    const col = this.detailSortColumn;
    const dir = this.detailSortDir === 'asc' ? 1 : -1;
    const isNumeric = rows.every(r => r[col] === null || r[col] === undefined || (!isNaN(parseFloat(r[col])) && isFinite(Number(r[col]))));
    rows.sort((a, b) => {
      const va = a[col];
      const vb = b[col];
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      if (isNumeric) {
        const na = Number(va);
        const nb = Number(vb);
        return (na - nb) * dir;
      }
      const sa = String(va).toLowerCase();
      const sb = String(vb).toLowerCase();
      if (sa < sb) return -1 * dir;
      if (sa > sb) return 1 * dir;
      return 0;
    });
    return rows;
  }

  onDetailSort(col: string): void {
    if (this.detailSortColumn === col) {
      this.detailSortDir = this.detailSortDir === 'asc' ? 'desc' : 'asc';
    } else {
      this.detailSortColumn = col;
      this.detailSortDir = 'asc';
    }
  }

  onDetailFilterChange(): void {
    this.ensureDetailFilterKeys();
  }

  clearDetailFilters(): void {
    this.detailGlobalFilter = '';
    this.detailColumnFilters = {};
    this.ensureDetailFilterKeys();
  }

  get maxAbsContribution(): number {
    const rows: any[] = Array.isArray(this.datqDetail?.psi_table) ? this.datqDetail!.psi_table : [];
    if (!rows.length) return 0;
    let max = 0;
    for (const r of rows) {
      const v = Math.abs(Number(r['PSI_contribution']) || 0);
      if (v > max) max = v;
    }
    return max;
  }

  contribWidth(v: any): number {
    const max = this.maxAbsContribution;
    const val = Math.abs(Number(v) || 0);
    return max > 0 ? Math.min(100, Math.max(0, (val / max) * 100)) : 0;
  }

  onPinnedColumnsChange(cols: string[]): void {
    this.pinnedColumns = (cols || []).filter(c => this.datqColumns.includes(c));
    this.saveDatqPrefs();
  }

  togglePin(col: string): void {
    if (this.pinnedColumns.includes(col)) {
      this.pinnedColumns = this.pinnedColumns.filter(c => c !== col);
    } else {
      this.pinnedColumns = [...this.pinnedColumns, col];
    }
    this.saveDatqPrefs();
  }

  resetSorting(): void {
    this.datqSortColumn = null;
    this.datqSortDir = 'asc';
    this.saveDatqPrefs();
  }

  resetLayout(): void {
    this.resetSorting();
    this.pinnedColumns = [];
    this.saveDatqPrefs();
  }

  private variableKeyFromRow(row: any): string {
    // Try common keys, fallback to first key
    if (!row) return '';
    if ('Variable' in row) return 'Variable';
    if ('variable' in row) return 'variable';
    if ('index' in row) return 'index';
    const keys = Object.keys(row);
    return keys.length ? keys[0] : '';
  }

  onDatqRowClick(row: any): void {
    try {
      const key = this.variableKeyFromRow(row);
      const variable = row?.[key];
      if (!variable) return;
      if (this.currentFileId == null || !this.processedFilePath) {
        console.warn('Missing file id or processed file path for datq detail.');
        return;
      }
      this.datqSelectedVariable = String(variable);
      this.datqDetailLoading = true;
      this.datqDetail = null;
      this.datqDetailColumns = [];
      this.dataService.getDatqDetail(
        this.currentFileId,
        this.processedFilePath,
        this.datqSelectedVariable,
        this.currentSplit || { strategy: this.splitStrategy, date_column: this.splitDateColumn || undefined, cutoff: this.splitCutoff || undefined, percent: this.ootMode === 'percent' ? this.ootPercent : undefined }
      ).subscribe({
        next: (resp: any) => {
          this.datqDetail = resp || null;
          const rows = Array.isArray(resp?.psi_table) ? resp.psi_table : [];
          this.datqDetailColumns = rows.length ? Object.keys(rows[0]) : [];
          this.ensureDetailFilterKeys();
        },
        error: (err: any) => {
          console.error('Failed to get datq detail:', err);
        },
        complete: () => {
          this.datqDetailLoading = false;
        }
      });
    } catch (e) {
      console.warn('onDatqRowClick failed:', e);
    }
  }

  exportDatqDetailAsCSV(): void {
    if (!this.datqDetail) return;
    const rows = this.datqDetailSortedRows as any[];
    if (rows.length === 0) return;
    const cols = this.datqDetailColumns.length ? this.datqDetailColumns : Object.keys(rows[0]);
    const escape = (v: any) => {
      if (v === null || v === undefined) return '';
      const s = String(v);
      return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    };
    const header = cols.join(',');
    const body = rows.map(r => cols.map(c => escape(r[c])).join(','));
    const csv = [header, ...body].join('\n');
    const name = this.datqSelectedVariable ? `datq_detail_${this.datqSelectedVariable}.csv` : 'datq_detail.csv';
    this.downloadBlob(csv, name, 'text/csv;charset=utf-8');
  }

  exportDatqDetailAsJSON(): void {
    if (!this.datqDetail) return;
    const json = JSON.stringify(this.datqDetailSortedRows, null, 2);
    const name = this.datqSelectedVariable ? `datq_detail_${this.datqSelectedVariable}.json` : 'datq_detail.json';
    this.downloadBlob(json, name, 'application/json;charset=utf-8');
  }

  closeDatqDetail(): void {
    this.datqSelectedVariable = null;
    this.datqDetail = null;
    this.datqDetailColumns = [];
    this.datqDetailLoading = false;
  }

  exportDatqAsCSV(): void {
    if (!this.datqSummary || this.datqSummary.length === 0) return;
    const cols = this.datqDisplayColumns.length ? this.datqDisplayColumns : (this.datqColumns.length ? this.datqColumns : Object.keys(this.datqSummary[0]));
    const rowsSource = this.datqSortedRows; // export filtered + sorted, unpaged
    const escape = (v: any) => {
      if (v === null || v === undefined) return '';
      const s = String(v);
      return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    };
    const header = cols.join(',');
    const rows = rowsSource.map(r => cols.map(c => escape(r[c])).join(','));
    const csv = [header, ...rows].join('\n');
    this.downloadBlob(csv, 'data_quality_summary.csv', 'text/csv;charset=utf-8');
  }

  exportDatqAsJSON(): void {
    if (!this.datqSummary) return;
    const rowsSource = this.datqSortedRows; // export filtered + sorted, unpaged
    const json = JSON.stringify(rowsSource, null, 2);
    this.downloadBlob(json, 'data_quality_summary.json', 'application/json;charset=utf-8');
  }

  private downloadBlob(content: string, filename: string, type: string): void {
    try {
      const blob = new Blob([content], { type });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      console.warn('Download failed:', e);
    }
  }

  percent(v: any): number {
    const n = Number(v);
    if (!isFinite(n) || isNaN(n)) return 0;
    const p = n * 100;
    return p < 0 ? 0 : (p > 100 ? 100 : p);
  }

  private loadDatqPrefs(): void {
    try {
      const raw = localStorage.getItem(this.datqPrefsKey);
      if (!raw) return;
      const prefs = JSON.parse(raw);
      if (typeof prefs?.pageSize === 'number') this.datqPageSize = prefs.pageSize;
      if (Array.isArray(prefs?.pinned)) this.pinnedColumns = prefs.pinned;
      if (typeof prefs?.sortColumn === 'string' || prefs?.sortColumn === null) this.datqSortColumn = prefs.sortColumn;
      if (prefs?.sortDir === 'asc' || prefs?.sortDir === 'desc') this.datqSortDir = prefs.sortDir;
    } catch {}
  }

  private saveDatqPrefs(): void {
    try {
      const prefs = {
        pageSize: this.datqPageSize,
        pinned: this.pinnedColumns,
        sortColumn: this.datqSortColumn,
        sortDir: this.datqSortDir,
      };
      localStorage.setItem(this.datqPrefsKey, JSON.stringify(prefs));
    } catch {}
  }

  private saveDatqWidths(): void {
    try {
      localStorage.setItem(this.datqWidthsKey, JSON.stringify(this.colWidths));
    } catch {}
  }

  private loadDatqWidths(): void {
    try {
      const raw = localStorage.getItem(this.datqWidthsKey);
      if (!raw) return;
      const obj = JSON.parse(raw);
      if (obj && typeof obj === 'object') this.colWidths = obj;
    } catch {}
  }

  onResizeStart(col: string, ev: MouseEvent): void {
    ev.preventDefault();
    ev.stopPropagation();
    this.resizingCol = col;
    this.resizeStartX = ev.clientX;
    this.resizeStartW = this.getColWidth(col);
    const move = (e: MouseEvent) => this.onResizing(e);
    const up = () => this.onResizeEnd(move, up);
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up, { once: true });
  }

  private onResizing(ev: MouseEvent): void {
    if (!this.resizingCol) return;
    const dx = ev.clientX - this.resizeStartX;
    const newW = Math.max(120, Math.min(800, this.resizeStartW + dx));
    this.colWidths[this.resizingCol] = newW;
  }

  private onResizeEnd(move: any, up: any): void {
    window.removeEventListener('mousemove', move as any);
    // 'up' listener is once:true
    this.resizingCol = null;
    this.saveDatqWidths();
  }

  // Display formatter: clamp PSI/CSI to 6 decimals
  displayCell(row: any, col: string): any {
    const v = row?.[col];
    const varType = String(row?.['Variable_Type'] || '').toLowerCase();
    const colName = String(col);
    const isTrainTest = (suffix: string) => colName.endsWith(`_${suffix}`);
    const base = colName.replace(/_(Train|Test)$/i, '');
    const numericOnlyBases = new Set([
      'Mean_Change','Median_Change','STD_Change','Min_Change',
      'Quantile_1_Change','Quantile_5_Change','Q1_Change','Q3_Change',
      'Quantile_95_Change','Quantile_99_Change','Max_Change',
      'Skewness_Change','Kurtosis_Change'
    ]);
    const categoricalOnlyBases = new Set(['Mode_Change']);

    // Not Applicable rules
    if (colName === 'PSI' && varType === 'categorical') return 'NA';
    if (colName === 'CSI' && varType === 'numerical') return 'NA';
    if (numericOnlyBases.has(base) && varType === 'categorical') return 'NA';
    if (categoricalOnlyBases.has(base) && varType === 'numerical') return 'NA';

    if (v == null) return '';

    // Numeric formatting for PSI/CSI
    if (colName === 'PSI' || colName === 'CSI') {
      const n = Number(v);
      if (!isFinite(n) || isNaN(n)) return v;
      return n.toFixed(6);
    }

    return v;
  }

  /** canDeactivate hook — called by the route guard with the target URL */
  canDeactivate(nextUrl?: string): boolean {
    if (this.hasUnsavedChanges()) {
      this._pendingNavUrl = nextUrl || '/home';
      this.showExitDialog = true;
      return false;
    }
    return true;
  }

  ngOnDestroy() {
    this.subscription.unsubscribe();
  }

  // ===== Pipeline Persistence Methods =====

  loadSavedPipelines(): void {
    this.dataService.listPipelineRuns().subscribe({
      next: (runs: any[]) => { this.savedPipelines = runs || []; },
      error: () => { this.savedPipelines = []; }
    });
  }

  toggleSavedPipelines(): void {
    this.showSavedPipelines = !this.showSavedPipelines;
    if (this.showSavedPipelines) this.loadSavedPipelines();
  }

  // ── Granular step taxonomy ──
  private static readonly DETAILED_STEPS: string[] = [
    '1a_pipeline_declaration', '1b_data_declaration', '1c_dictionary_declaration',
    '2a_purifier_declaration', '2b_data_quality_summary',
    '3a_encoding', '3b_modeling', '3c_sfs', '3ci_sfs_backward'
  ];

  private static readonly DETAILED_LABELS: {[k: string]: string} = {
    '1a_pipeline_declaration': 'Pipeline Declaration',
    '1b_data_declaration': 'Data Declaration',
    '1c_dictionary_declaration': 'Dictionary Declaration',
    '2a_purifier_declaration': 'Data Purifier Declaration',
    '2b_data_quality_summary': 'Data Quality Summary',
    '3a_encoding': 'Categorical Feature Encoding',
    '3b_modeling': 'Modeling',
    '3c_sfs': 'SFS',
    '3ci_sfs_backward': 'SFS Backward'
  };

  /** Map a modeling child-component substep to the detailed taxonomy */
  private mapModelingSubstepToDetailed(substep: string): string {
    if (substep === 'algorithm_selected' || substep === 'encoding_completed') return '3a_encoding';
    if (substep === 'modeling_started' || substep === 'modeling_completed') return '3b_modeling';
    if (substep === 'sfs_backward_completed') return '3ci_sfs_backward';
    if (substep.startsWith('sfs_')) return '3c_sfs';
    return this.detailedStep; // keep current if unknown
  }

  /** Infer detailed step from coarse step + state (for old checkpoints without detailed_step) */
  private inferDetailedStep(coarseStep: string, state: any): string {
    const modelingSub = (state.modeling || {}).substep || '';
    switch (coarseStep) {
      case 'declaration':
        if (state.file_id) return '1b_data_declaration';
        return '1a_pipeline_declaration';
      case 'preprocessing':
        return '2a_purifier_declaration';
      case 'data_quality':
        return '2b_data_quality_summary';
      case 'modeling':
        if (modelingSub) return this.mapModelingSubstepToDetailed(modelingSub);
        return '3a_encoding';
      case 'sfs':
        if (modelingSub) return this.mapModelingSubstepToDetailed(modelingSub);
        return '3c_sfs';
      default:
        return '1a_pipeline_declaration';
    }
  }

  getStepIndex(step: string): number {
    const steps = ['declaration', 'preprocessing', 'data_quality', 'modeling', 'sfs', 'evaluation', 'deployment'];
    const idx = steps.indexOf(step);
    return idx >= 0 ? idx : 0;
  }

  getDetailedStepProgress(run: any): number {
    const ds = run.detailed_step || run.state?.detailed_step;
    if (ds) {
      const idx = ModelDevelopmentComponent.DETAILED_STEPS.indexOf(ds);
      if (idx >= 0) return Math.round(((idx + 1) / ModelDevelopmentComponent.DETAILED_STEPS.length) * 100);
    }
    // Fallback to coarse step
    return Math.round(((this.getStepIndex(run.current_step) + 1) / 7) * 100);
  }

  getStepProgress(step: string): number {
    return Math.round(((this.getStepIndex(step) + 1) / 7) * 100);
  }

  getDetailedStepLabel(run: any): string {
    const ds = run.detailed_step || run.state?.detailed_step;
    if (ds && ModelDevelopmentComponent.DETAILED_LABELS[ds]) {
      return ModelDevelopmentComponent.DETAILED_LABELS[ds];
    }
    // Fallback
    return this.getStepLabel(run.current_step);
  }

  getStepLabel(step: string): string {
    const labels: {[k: string]: string} = {
      'declaration': 'Declaration',
      'preprocessing': 'Preprocessing',
      'data_quality': 'Data Quality',
      'modeling': 'Modeling',
      'sfs': 'SFS',
      'evaluation': 'Evaluation',
      'deployment': 'Deployment'
    };
    return labels[step] || step;
  }

  buildCheckpointState(): any {
    return {
      file_id: this.currentFileId,
      pipeline_type: this.selectedPipeline,
      target_definition: this.targetDefinition || '',
      current_step: this.currentStep === 'data quality' ? 'data_quality' : this.currentStep,
      detailed_step: this.detailedStep,
      preprocessing: {
        purifier_option_ids: this.selectedOptions.map(o => o.id),
        split_strategy: this.splitStrategy,
        split_date_column: this.splitDateColumn,
        split_cutoff: this.splitCutoff,
        oot_mode: this.ootMode,
        oot_percent: this.ootPercent,
        oos_percent: this.oosPercent,
        processed_file_path: this.processedFilePath,
        dropped_columns_by_step: this.droppedColumnsByStep,
        rows_removed_total: this.rowsRemovedTotal,
        row_count_before: this.rowCountBefore,
        row_count_after: this.rowCountAfter,
        split_validation: this.splitValidation,
      },
      data_quality: {
        datq_summary: this.datqSummary,
        model_usage: this.variableModelUsage,
      },
      flags: {
        is_started: this.isStarted,
        preprocessing_initiated: this.preprocessingInitiated,
        preprocessing_available: this.preprocessingAvailable,
        modeling_available: this.modelingAvailable,
      },
      modeling: this.sharedService.getModelingCheckpoint() || null,
      active_process: this.sharedService.getActiveProcess() || null,
      pipeline_notes: this.sharedService.getPipelineNotes() || {},
    };
  }

  private static readonly STEP_ORDER: {[k: string]: number} = {
    'declaration': 0, 'preprocessing': 1, 'data_quality': 2,
    'modeling': 3, 'sfs': 4, 'evaluation': 5, 'deployment': 6
  };

  saveCheckpoint(step?: string, force: boolean = false): void {
    // Always refresh cumulative AI context regardless of autosave setting
    this.pushAiContext();

    // When autosave is OFF and this is NOT a forced save (manual/initial), just mark dirty
    if (!this.autosaveEnabled && !force) {
      this._unsavedChanges = true;
      console.log(`[Pipeline] saveCheckpoint SKIPPED (autosave OFF): step=${step}, componentStep=${this.currentStep}`);
      return;
    }

    const state = this.buildCheckpointState();
    const currentStep = step || state.current_step;
    console.log(`[Pipeline] saveCheckpoint called: step=${step}, currentStep=${currentStep}, componentStep=${this.currentStep}, highWater=${this._highWaterStep}, id=${this.activePipelineRunId}, creating=${this._checkpointCreating}`);

    // Frontend step regression guard: never send a PUT that would regress the step
    const newOrder = ModelDevelopmentComponent.STEP_ORDER[currentStep] ?? 0;
    const hwOrder = ModelDevelopmentComponent.STEP_ORDER[this._highWaterStep] ?? 0;
    if (newOrder < hwOrder) {
      console.warn(`[Pipeline] BLOCKED frontend regression: ${this._highWaterStep}(${hwOrder}) -> ${currentStep}(${newOrder})`, new Error().stack);
      return;
    }
    this._highWaterStep = currentStep;

    if (this.activePipelineRunId) {
      // Already have an ID — safe to update directly
      this.dataService.updatePipelineRun(this.activePipelineRunId, {
        current_step: currentStep,
        state: state,
        file_id: this.currentFileId,
      }).subscribe({
        next: () => { this._unsavedChanges = false; console.log('[Pipeline] Checkpoint saved:', currentStep); },
        error: (e: any) => console.error('[Pipeline] Checkpoint save failed:', e)
      });
    } else if (this._checkpointCreating) {
      // A create is already in flight — just flag that we need a flush
      this._pendingCheckpoint = true;
      console.log('[Pipeline] Queued checkpoint (create in flight), componentStep:', this.currentStep);
    } else {
      // No ID yet, no create in flight — fire the create
      this._checkpointCreating = true;
      const name = this.pipelineRunName || `${this.selectedPipeline || 'pipeline'}-${new Date().toISOString().replace(/[:.]/g, '-').substring(0, 19)}`;
      this.dataService.createPipelineRun({
        name: name,
        pipeline_type: this.selectedPipeline || 'boosting',
        file_id: this.currentFileId,
        current_step: currentStep,
        state: state,
      }).subscribe({
        next: (resp: any) => {
          this.activePipelineRunId = resp.id;
          this.pipelineRunName = resp.name;
          this._checkpointCreating = false;
          this._unsavedChanges = false;
          console.log('[Pipeline] Created & saved checkpoint:', resp.name, currentStep);
          // Flush: re-save with CURRENT state (not stale queued step)
          if (this._pendingCheckpoint) {
            this._pendingCheckpoint = false;
            console.log('[Pipeline] Flushing with current state, componentStep:', this.currentStep);
            this.saveCheckpoint(undefined, true);
          }
        },
        error: (e: any) => {
          this._checkpointCreating = false;
          this._pendingCheckpoint = false;
          console.error('[Pipeline] Create failed:', e);
        }
      });
    }
  }

  loadPipelineRun(id: number): void {
    this.dataService.getPipelineRun(id).subscribe({
      next: (run: any) => {
        const s = run.state || {};

        // ── 1. Set step & high-water FIRST (before any SharedService calls) ──
        //    This prevents subscription guards from mis-firing during restore.
        const step = run.current_step === 'data_quality' ? 'data quality' : (run.current_step === 'sfs' ? 'modeling' : run.current_step);
        this.currentStep = step;
        const restoredStepKey = step === 'data quality' ? 'data_quality' : step;
        this._highWaterStep = restoredStepKey;

        // ── 1b. Restore detailed step ──
        this.detailedStep = s.detailed_step || this.inferDetailedStep(restoredStepKey, s);

        // ── 2. Restore identity & clear dirty state ──
        this.activePipelineRunId = run.id;
        this.pipelineRunName = run.name;
        this._unsavedChanges = false;
        this.selectedPipeline = s.pipeline_type || run.pipeline_type || 'boosting';
        this.targetDefinition = s.target_definition || '';
        this.sharedService.setTargetDefinition(this.targetDefinition);

        // ── 3. Restore flags (local first, then SharedService) ──
        const flags = s.flags || {};
        this.isStarted = flags.is_started !== false;
        this.preprocessingInitiated = !!flags.preprocessing_initiated;
        this.preprocessingAvailable = !!flags.preprocessing_available;
        this.modelingAvailable = !!flags.modeling_available;

        // ── 4. Restore preprocessing state ──
        const pp = s.preprocessing || {};
        if (pp.purifier_option_ids && pp.purifier_option_ids.length) {
          this.selectedOptions = this.purifierOptions.filter(o => pp.purifier_option_ids.includes(o.id));
        }
        this.splitStrategy = pp.split_strategy || 'random';
        this.splitDateColumn = pp.split_date_column || null;
        this.splitCutoff = pp.split_cutoff || '';
        this.ootMode = pp.oot_mode || 'percent';
        this.ootPercent = pp.oot_percent ?? 25;
        this.oosPercent = pp.oos_percent ?? 25;
        this.processedFilePath = pp.processed_file_path || null;
        this.droppedColumnsByStep = pp.dropped_columns_by_step || [];
        this.rowsRemovedTotal = pp.rows_removed_total || 0;
        this.rowCountBefore = pp.row_count_before || 0;
        this.rowCountAfter = pp.row_count_after || 0;
        this.splitValidation = pp.split_validation || null;
        this._splitChartDrawn = false;

        // ── 5. Restore data quality state ──
        const dq = s.data_quality || {};
        if (dq.datq_summary && dq.datq_summary.length) {
          this.datqSummary = dq.datq_summary;
          this.datqAllColumns = Object.keys(this.datqSummary![0]);
          this.datqColumns = [...this.datqAllColumns];
          this.reorderDatqColumns();
          this.ensureFilterKeys();
          this.datqPage = 1;
        }
        if (dq.model_usage) {
          this.variableModelUsage = dq.model_usage;
          this.saveModelUsage();
        }

        // ── 5b. Restore pipeline notes ──
        this.pipelineNotes = s.pipeline_notes || {};
        this.sharedService.setPipelineNotes(this.pipelineNotes);

        // ── 6. Restore modeling inner state via SharedService (before component initializes) ──
        if (s.modeling) {
          this._lastModelingSubstep = s.modeling.substep || null;
          this.sharedService.setModelingCheckpoint(s.modeling);
        }

        // ── 6b. Restore active process tracking (for resume on return) ──
        if (s.active_process) {
          this.sharedService.setActiveProcess(s.active_process);
        } else {
          this.sharedService.setActiveProcess(null);
        }

        // ── 7. NOW fire SharedService setters (subscriptions will see correct currentStep) ──
        this.sharedService.setSelectedPipeline(this.selectedPipeline);
        this.sharedService.setStarted(this.isStarted);
        this.sharedService.setPreprocessingInitiated(this.preprocessingInitiated);
        this.sharedService.setProcessedFilePath(this.processedFilePath);
        if (dq.model_usage) {
          this.sharedService.setModelUsageSettings(dq.model_usage);
        }
        // Set file ID last — triggers declaration hydration (preview + dictionary fetch)
        if (s.file_id != null) {
          this.currentFileId = s.file_id;
          this.sharedService.setCurrentFileId(s.file_id);
        }

        // ── 7b. Push cumulative AI context after full restore ──
        this.pushAiContext();

        // ── 8. Close panel & scroll ──
        this.showSavedPipelines = false;
        console.log('[Pipeline] Loaded run:', run.name, 'at step:', step);

        // ── 9. Check for active process that needs resume ──
        if (s.active_process && s.active_process.type === 'preprocessing' && s.active_process.file_id) {
          this.resumePreprocessing(s.active_process.file_id);
        }

        setTimeout(() => {
          try {
            if (step === 'data quality') {
              const el = document.getElementById('data-quality-anchor');
              if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
            } else if (step === 'modeling' || step === 'sfs') {
              const el = document.getElementById('modeling-anchor');
              if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
          } catch {}
        }, 200);
      },
      error: (e: any) => console.error('[Pipeline] Load failed:', e)
    });
  }

  /** Resume preprocessing: check if it completed while the user was away */
  private resumePreprocessing(fileId: number): void {
    console.log('[Pipeline] Checking preprocessing status for resume, file_id:', fileId);
    this.isProcessing = true;
    this.dataService.getPreprocessingStatus(fileId).subscribe({
      next: (resp: any) => {
        this.isProcessing = false;
        if (resp.status === 'completed' && resp.result) {
          console.log('[Pipeline] Resume: preprocessing completed while away');
          const result = resp.result;
          // Restore all preprocessing results
          this.sharedService.setPreprocessingRunResult(result);
          this.sharedService.setProcessedFilePath(result?.processed_file ?? null);
          this.processedFilePath = result?.processed_file ?? null;
          this.droppedColumnsByStep = Array.isArray(result?.dropped_columns_by_step) ? result.dropped_columns_by_step : [];
          this.rowsRemovedTotal = Number(result?.rows_removed_total ?? 0);
          this.rowCountBefore = Number(result?.row_count_before ?? 0);
          this.rowCountAfter = Number(result?.row_count_after ?? 0);
          this.featureStatsBefore = result?.feature_stats_before ?? null;
          this.featureStatsAfter = result?.feature_stats_after ?? null;
          this.preprocessingStepStats = result?.preprocessing_step_stats ?? null;
          // Restore Split Validation
          this.splitValidation = result?.split_validation ?? null;
          this._splitChartDrawn = false;
          // Restore Data Quality summary
          this.datqSummary = Array.isArray(result?.datq_summary) ? result.datq_summary : null;
          this.datqAllColumns = this.datqSummary && this.datqSummary.length > 0 ? Object.keys(this.datqSummary[0]) : [];
          this.datqColumns = [...this.datqAllColumns];
          this.reorderDatqColumns();
          this.ensureFilterKeys();
          if (this.pinnedColumns.length === 0) {
            if (this.datqColumns.includes('Variable')) this.pinnedColumns = ['Variable'];
            else if (this.datqColumns.includes('variable')) this.pinnedColumns = ['variable'];
          }
          if (this.datqColumns.includes('PSI')) {
            this.datqSortColumn = 'PSI';
            this.datqSortDir = 'desc';
          }
          this.datqPage = 1;
          // Advance to data quality step
          if (this.datqSummary && this.datqSummary.length > 0) {
            this.currentStep = 'data quality';
            this._highWaterStep = 'data_quality';
            this.preprocessingAvailable = true;
            this.detailedStep = '2b_data_quality_summary';
          }
          // Clear active process and save
          this.sharedService.setActiveProcess(null);
          this.saveCheckpoint('data_quality', true);
          setTimeout(() => {
            try {
              const el = document.getElementById('data-quality-anchor');
              if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
            } catch {}
          }, 200);
        } else {
          console.log('[Pipeline] Resume: preprocessing not yet completed or no results');
          this.sharedService.setActiveProcess(null);
          this.saveCheckpoint(undefined, true);
        }
      },
      error: (err: any) => {
        this.isProcessing = false;
        console.warn('[Pipeline] Resume: could not check preprocessing status:', err);
        this.sharedService.setActiveProcess(null);
      }
    });
  }

  deletePipelineRun(id: number): void {
    if (!confirm('Delete this pipeline run?')) return;
    this.dataService.deletePipelineRun(id).subscribe({
      next: () => {
        this.savedPipelines = this.savedPipelines.filter(r => r.id !== id);
        if (this.activePipelineRunId === id) this.activePipelineRunId = null;
      },
      error: (e: any) => console.error('[Pipeline] Delete failed:', e)
    });
  }

  startRenamePipeline(run: any): void {
    this.renamingPipelineId = run.id;
    this.renamingPipelineName = run.name;
  }

  confirmRenamePipeline(run: any): void {
    if (!this.renamingPipelineName.trim()) return;
    this.dataService.updatePipelineRun(run.id, { name: this.renamingPipelineName.trim() }).subscribe({
      next: () => {
        run.name = this.renamingPipelineName.trim();
        if (this.activePipelineRunId === run.id) this.pipelineRunName = run.name;
        this.renamingPipelineId = null;
      },
      error: (e: any) => console.error('[Pipeline] Rename failed:', e)
    });
  }

  cancelRenamePipeline(): void {
    this.renamingPipelineId = null;
  }
  
  onPipelineChange(event: Event) {
    const select = event.target as HTMLSelectElement;
    this.selectedPipeline = select.value;
    console.log('Selected pipeline:', this.selectedPipeline);
    this.sharedService.setSelectedPipeline(this.selectedPipeline);
  }

  onPipelineChange2(value: string) {
    this.selectedPipeline = value;
    console.log('Selected pipeline:', this.selectedPipeline);
    this.sharedService.setSelectedPipeline(this.selectedPipeline);
  }

  onTargetDefinitionChange(value: string): void {
    this.targetDefinition = value;
    this.sharedService.setTargetDefinition(value);
    this.onPipelineConfigChanged();
  }

  onStartClick() {
    if (this.selectedPipeline) {
      // Reset state for a clean run
      this.activePipelineRunId = null;
      this.pipelineRunName = '';
      this._checkpointCreating = false;
      this._pendingCheckpoint = false;
      this._highWaterStep = 'declaration';
      this._lastModelingSubstep = null;
      this.sharedService.setCurrentFileId(null);
      this.sharedService.setPreprocessingInitiated(false);
      this.sharedService.setPreprocessingRunResult(null);
      this.sharedService.setProcessedFilePath(null);
      this.sharedService.setActiveProcess(null); // clear any stale active process
      this.selectedOptions = this.purifierOptions.filter(o => this.defaultOptionIds.includes(o.id));
      this.modelingAvailable = false;
      this.preprocessingAvailable = false;
      this.currentStep = 'declaration';
      this.detailedStep = '1a_pipeline_declaration';
      this.editingTargetDefinition = false;
      // Start pipeline
      this.sharedService.setStarted(true);
      // Initial creation checkpoint: always force through
      this.saveCheckpoint('declaration', true);
    }
  }

  onEditTargetDefinition(): void {
    this.editingTargetDefinition = true;
  }

  onSaveTargetDefinition(): void {
    this.editingTargetDefinition = false;
    this.sharedService.setTargetDefinition(this.targetDefinition);
    this.onPipelineConfigChanged();
  }

  onSelectionChange(event: MatSelectChange): void {
    const selectedGroups = new Set(this.selectedOptions.map(option => option.group).filter(group => group !== undefined));
    
    this.selectedOptions = this.selectedOptions.filter(option => 
      !option.group || selectedGroups.has(option.group)
    );
  }

  isOptionDisabled(option: PurifierOption): boolean {
    if (!option.group) return false;

    const selectedGroups = new Set(this.selectedOptions.map(opt => opt.group).filter(group => group !== undefined));
    return selectedGroups.has(option.group) && !this.selectedOptions.includes(option);
  }

  // Save selected purifier options and move to Modeling step
  proceedFromPreprocessing(): void {
    const optionIds = this.selectedOptions.map(o => o.id);
    this.sharedService.setSelectedPurifierOptions(optionIds);
    if (this.currentFileId == null) {
      console.error('No file ID found. Please upload/select a data file first.');
      return;
    }
    // Build split config
    const oosPct = Number(this.oosPercent);
    const oosValid = isFinite(oosPct) && oosPct > 0 && oosPct < 100;
    let split: any = { strategy: 'random', percent: oosValid ? oosPct : 25 };
    if (this.splitStrategy === 'oot') {
      if (!this.splitDateColumn) {
        console.error('Please select a date column for OOT split.');
        return;
      }
      if (this.ootMode === 'cutoff') {
        if (!this.splitCutoff) {
          console.error('Please provide a cutoff datetime for OOT split.');
          return;
        }
        split = { strategy: 'oot', date_column: this.splitDateColumn, cutoff: this.splitCutoff };
      } else {
        const pct = Number(this.ootPercent);
        const valid = isFinite(pct) && pct > 0 && pct < 100;
        split = { strategy: 'oot', date_column: this.splitDateColumn, percent: valid ? pct : 25 };
      }
    }

    // Get list of variables to exclude (Model_Usage='No')
    const excludedVariables = this.getExcludedVariables();
    if (excludedVariables.length > 0) {
      console.log(`[Preprocessing] Excluding ${excludedVariables.length} variables with Model_Usage='No':`, excludedVariables);
    }

    this.isProcessing = true;
    // Track active process for pipeline resume
    this.sharedService.setActiveProcess({ type: 'preprocessing', file_id: this.currentFileId });
    this.detailedStep = '2a_purifier_declaration';
    this.saveCheckpoint('preprocessing', true); // force-save so active_process is persisted
    this.dataService.runPreprocessing(this.currentFileId, optionIds, split, excludedVariables, this.dataDictionaryCache)
      .pipe(finalize(() => { this.isProcessing = false; }))
      .subscribe(
        (result: any) => {
          console.log('[Preprocessing] run result:', result);
          this.sharedService.setPreprocessingRunResult(result);
          this.sharedService.setProcessedFilePath(result?.processed_file ?? null);
          // Capture breakdown of dropped columns per purifier step (if provided)
          this.droppedColumnsByStep = Array.isArray(result?.dropped_columns_by_step) ? result.dropped_columns_by_step : [];
          // Capture total rows removed if provided
          this.rowsRemovedTotal = Number(result?.rows_removed_total ?? 0);
          // Capture row counts before/after
          this.rowCountBefore = Number(result?.row_count_before ?? 0);
          this.rowCountAfter = Number(result?.row_count_after ?? 0);
          // Capture before/after per-feature descriptive stats
          this.featureStatsBefore = result?.feature_stats_before ?? null;
          this.featureStatsAfter = result?.feature_stats_after ?? null;
          this.preprocessingStepStats = result?.preprocessing_step_stats ?? null;
          // Capture Split Validation data
          this.splitValidation = result?.split_validation ?? null;
          this._splitChartDrawn = false;
          // Capture Data Quality summary
          this.datqSummary = Array.isArray(result?.datq_summary) ? result.datq_summary : null;
          this.datqAllColumns = this.datqSummary && this.datqSummary.length > 0 ? Object.keys(this.datqSummary[0]) : [];
          this.datqColumns = [...this.datqAllColumns];
          this.reorderDatqColumns();
          this.ensureFilterKeys();
          // Apply persisted pins if any; else default pin Variable once
          if (this.pinnedColumns.length > 0) {
            this.pinnedColumns = this.pinnedColumns.filter(c => this.datqColumns.includes(c));
          } else {
            if (this.datqColumns.includes('Variable')) this.pinnedColumns = ['Variable'];
            else if (this.datqColumns.includes('variable')) this.pinnedColumns = ['variable'];
          }
          // Default sort by PSI desc if present
          if (this.datqColumns.includes('PSI')) {
            this.datqSortColumn = 'PSI';
            this.datqSortDir = 'desc';
          }
          this.datqPage = 1;
          this.saveDatqPrefs();
          // Clear active process — preprocessing completed
          this.sharedService.setActiveProcess(null);
          // Navigate to Data Quality section
          if (this.datqSummary && this.datqSummary.length > 0) {
            this.currentStep = 'data quality';
            this.detailedStep = '2b_data_quality_summary';
            // Auto-save checkpoint: data_quality
            this.saveCheckpoint('data_quality');
            setTimeout(() => {
              try {
                const el = document.getElementById('data-quality-anchor');
                if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
              } catch {}
            }, 0);
          }
        },
        (err: any) => {
          console.error('Failed to run preprocessing:', err);
          this.sharedService.setActiveProcess(null); // clear on error too
        }
      );
  }

  // ── Split Validation Chart (Canvas-based stacked bar + target mean line) ──
  drawSplitValidationChart(): void {
    if (!this.splitValidation || !this.splitValidationCanvas) return;
    const canvas = this.splitValidationCanvas.nativeElement;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const cssW = canvas.clientWidth || 700;
    const cssH = canvas.clientHeight || 320;
    canvas.width = cssW * dpr;
    canvas.height = cssH * dpr;
    ctx.scale(dpr, dpr);

    const splits: any[] = this.splitValidation.splits || [];
    const labels: string[] = this.splitValidation.labels || [];
    if (!splits.length || !labels.length) return;

    // Layout constants
    const marginTop = 40, marginBottom = 70, marginLeft = 70, marginRight = 120;
    const chartW = cssW - marginLeft - marginRight;
    const chartH = cssH - marginTop - marginBottom;

    // Color palette for target labels
    const labelColors: string[] = ['#90a4ae', '#e57373', '#81c784', '#ffb74d', '#ba68c8', '#4dd0e1', '#f06292', '#a1887f'];
    const labelColorMap: { [label: string]: string } = {};
    labels.forEach((l, i) => { labelColorMap[l] = labelColors[i % labelColors.length]; });

    // Max count for Y axis
    const maxCount = Math.max(...splits.map((s: any) => s.count || 0), 1);

    // Bar geometry
    const barGroupWidth = chartW / splits.length;
    const barWidth = Math.min(barGroupWidth * 0.55, 100);
    const barGap = (barGroupWidth - barWidth) / 2;

    // Clear
    ctx.clearRect(0, 0, cssW, cssH);
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, cssW, cssH);

    // Y axis: gridlines and labels (count scale)
    const nTicks = 5;
    ctx.strokeStyle = '#e8e8e8';
    ctx.lineWidth = 1;
    ctx.fillStyle = '#888';
    ctx.font = '11px -apple-system, BlinkMacSystemFont, sans-serif';
    ctx.textAlign = 'right';
    for (let i = 0; i <= nTicks; i++) {
      const v = Math.round(maxCount * i / nTicks);
      const y = marginTop + chartH - (chartH * i / nTicks);
      ctx.beginPath();
      ctx.moveTo(marginLeft, y);
      ctx.lineTo(marginLeft + chartW, y);
      ctx.stroke();
      ctx.fillText(v.toLocaleString(), marginLeft - 8, y + 4);
    }

    // Y axis title
    ctx.save();
    ctx.translate(16, marginTop + chartH / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.textAlign = 'center';
    ctx.fillStyle = '#555';
    ctx.font = 'bold 12px -apple-system, BlinkMacSystemFont, sans-serif';
    ctx.fillText('Count', 0, 0);
    ctx.restore();

    // Draw stacked bars
    splits.forEach((split: any, idx: number) => {
      const x = marginLeft + idx * barGroupWidth + barGap;
      const lc: { [k: string]: number } = split.label_counts || {};
      let yBottom = marginTop + chartH; // start from bottom

      labels.forEach((label: string) => {
        const count = lc[label] || 0;
        const barH = (count / maxCount) * chartH;
        const y = yBottom - barH;
        ctx.fillStyle = labelColorMap[label];
        ctx.fillRect(x, y, barWidth, barH);

        // Count label inside bar if tall enough
        if (barH > 18) {
          ctx.fillStyle = '#fff';
          ctx.font = 'bold 11px -apple-system, BlinkMacSystemFont, sans-serif';
          ctx.textAlign = 'center';
          ctx.fillText(count.toLocaleString(), x + barWidth / 2, y + barH / 2 + 4);
        }
        yBottom = y;
      });

      // X-axis label: split name
      ctx.fillStyle = '#333';
      ctx.font = 'bold 12px -apple-system, BlinkMacSystemFont, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(split.name, x + barWidth / 2, marginTop + chartH + 18);

      // Count subtitle
      ctx.fillStyle = '#888';
      ctx.font = '11px -apple-system, BlinkMacSystemFont, sans-serif';
      ctx.fillText(`n=${(split.count || 0).toLocaleString()}`, x + barWidth / 2, marginTop + chartH + 33);
    });

    // ── Target Mean line (secondary Y axis) ──
    const means = splits.map((s: any) => s.target_mean ?? 0);
    const meanMin = Math.min(...means);
    const meanMax = Math.max(...means);
    // Expand range slightly for visual clarity
    const meanRange = (meanMax - meanMin) || 0.01;
    const meanLow = Math.max(0, meanMin - meanRange * 0.5);
    const meanHigh = Math.min(1, meanMax + meanRange * 0.5);
    const meanScale = (v: number) => marginTop + chartH - ((v - meanLow) / (meanHigh - meanLow)) * chartH;

    // Draw line
    ctx.strokeStyle = '#2e7d32';
    ctx.lineWidth = 2.5;
    ctx.setLineDash([6, 3]);
    ctx.beginPath();
    splits.forEach((split: any, idx: number) => {
      const x = marginLeft + idx * barGroupWidth + barGap + barWidth / 2;
      const y = meanScale(split.target_mean ?? 0);
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.setLineDash([]);

    // Draw mean dots and labels
    splits.forEach((split: any, idx: number) => {
      const x = marginLeft + idx * barGroupWidth + barGap + barWidth / 2;
      const y = meanScale(split.target_mean ?? 0);
      // Dot
      ctx.beginPath();
      ctx.arc(x, y, 5, 0, Math.PI * 2);
      ctx.fillStyle = '#2e7d32';
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 2;
      ctx.stroke();
      // Label
      ctx.fillStyle = '#2e7d32';
      ctx.font = 'bold 11px -apple-system, BlinkMacSystemFont, sans-serif';
      ctx.textAlign = 'center';
      const meanPct = ((split.target_mean ?? 0) * 100).toFixed(2);
      ctx.fillText(`${meanPct}%`, x, y - 10);
    });

    // Right Y axis: target mean scale
    ctx.textAlign = 'left';
    ctx.fillStyle = '#2e7d32';
    ctx.font = '11px -apple-system, BlinkMacSystemFont, sans-serif';
    for (let i = 0; i <= 4; i++) {
      const v = meanLow + (meanHigh - meanLow) * i / 4;
      const y = meanScale(v);
      ctx.fillText((v * 100).toFixed(1) + '%', marginLeft + chartW + 8, y + 4);
    }
    // Right axis title
    ctx.save();
    ctx.translate(cssW - 10, marginTop + chartH / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.textAlign = 'center';
    ctx.fillStyle = '#2e7d32';
    ctx.font = 'bold 12px -apple-system, BlinkMacSystemFont, sans-serif';
    ctx.fillText('Target Mean', 0, 0);
    ctx.restore();

    // Title
    ctx.fillStyle = '#333';
    ctx.font = 'bold 14px -apple-system, BlinkMacSystemFont, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Train-Test Split Validation: Target Distribution', cssW / 2, 20);

    // Legend (bottom)
    const legendY = cssH - 15;
    let legendX = marginLeft;
    ctx.font = '11px -apple-system, BlinkMacSystemFont, sans-serif';
    ctx.textAlign = 'left';
    labels.forEach((label: string) => {
      ctx.fillStyle = labelColorMap[label];
      ctx.fillRect(legendX, legendY - 9, 12, 12);
      ctx.fillStyle = '#555';
      ctx.fillText(`Target=${label}`, legendX + 16, legendY + 1);
      legendX += ctx.measureText(`Target=${label}`).width + 32;
    });
    // Mean legend
    ctx.strokeStyle = '#2e7d32';
    ctx.lineWidth = 2.5;
    ctx.setLineDash([6, 3]);
    ctx.beginPath();
    ctx.moveTo(legendX, legendY - 3);
    ctx.lineTo(legendX + 20, legendY - 3);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.beginPath();
    ctx.arc(legendX + 10, legendY - 3, 3, 0, Math.PI * 2);
    ctx.fillStyle = '#2e7d32';
    ctx.fill();
    ctx.fillStyle = '#555';
    ctx.textAlign = 'left';
    ctx.fillText('Target Mean', legendX + 26, legendY + 1);
  }

  // Helpers for UI
  droppedTotalCount(): number {
    try {
      return (this.droppedColumnsByStep || []).reduce((acc, s) => acc + (Array.isArray(s.columns) ? s.columns.length : 0), 0);
    } catch { return 0; }
  }

  objectKeys(obj: any): string[] {
    return obj ? Object.keys(obj) : [];
  }

  trackByStepIndex(_idx: number, item: any): string {
    const s = item?.step || 'step';
    const ids = Array.isArray(item?.option_ids) ? item.option_ids.join(',') : '';
    const thr = (item?.threshold != null) ? String(item.threshold) : '';
    return `${s}|${ids}|${thr}`;
  }

  applyDatqPreset(preset: 'core' | 'all'): void {
    this.datqPreset = preset;
    if (!this.datqAllColumns || this.datqAllColumns.length === 0) return;
    if (preset === 'all') {
      this.datqColumns = [...this.datqAllColumns];
      this.reorderDatqColumns();
      this.ensureFilterKeys();
      return;
    }
    // Build a curated core set
    const cols = new Set(this.datqAllColumns);
    const pick = (k: string) => cols.has(k) ? k : null;
    const varCol = pick('Variable') || pick('variable') || pick('index');
    const basePrefs = [
      '%_Missing_Change',
      'Mean_Change', 'Median_Change', 'STD_Change',
      'Min_Change', 'Max_Change'
    ];
    const pairFor = (b: string) => {
      const t1 = `${b}_Train`;
      const t2 = `${b}_Test`;
      if (cols.has(t1) || cols.has(t2)) {
        const arr: string[] = [];
        if (cols.has(t1)) arr.push(t1);
        if (cols.has(t2)) arr.push(t2);
        return arr;
      }
      // fallback to single column if backend didn't flatten
      return cols.has(b) ? [b] : [];
    };
    const fixed = [varCol, pick('PSI'), pick('Datq_Decision'), pick('Variable_Type'), pick('CSI')].filter(Boolean) as string[];
    const pairs = basePrefs.flatMap(b => pairFor(b));
    // Keep order from all-columns after we compute our intended order
    const desiredOrder = [...fixed, ...pairs];
    const seen = new Set<string>();
    const ordered = [] as string[];
    for (const c of this.datqAllColumns) {
      if (desiredOrder.includes(c) && !seen.has(c)) {
        ordered.push(c);
        seen.add(c);
      }
    }
    this.datqColumns = ordered.length ? ordered : [...this.datqAllColumns];
    this.ensureFilterKeys();
  }

  stepEnabled(item: string): boolean {
    if (item === 'declaration') return true;
    if (item === 'preprocessing') return this.preprocessingAvailable;
    if (item === 'data quality') return !!(this.datqSummary && this.datqSummary.length);
    if (item === 'modeling') return this.modelingAvailable;
    if (item === 'evaluation') return this.modelingAvailable; // can refine later
    if (item === 'deployment') return this.modelingAvailable; // can refine later
    return false;
  }

  onMenuClick(event: Event, item: string): void {
    if (!this.stepEnabled(item)) {
      event.preventDefault();
      return;
    }
    event.preventDefault();
    this.currentStep = item;
    // Scroll to anchors for known sections
    setTimeout(() => {
      try {
        if (item === 'data quality') {
          const el = document.getElementById('data-quality-anchor');
          if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        } else if (item === 'modeling') {
          const el = document.getElementById('modeling-anchor');
          if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      } catch {}
    }, 0);
  }

  private computePreprocessingAvailable(): void {
    this.preprocessingAvailable = this.isStarted && this.preprocessingInitiated && (this.currentFileId !== null);
  }

  // ===== Enhanced Navigation Methods =====

  toggleNavStep(mainStepId: string): void {
    this.navExpandedSteps[mainStepId] = !this.navExpandedSteps[mainStepId];
  }

  /** Navigate to a main step (same as onMenuClick but for new nav) */
  navGoToStep(event: Event, mainStepId: string): void {
    event.stopPropagation();
    // Map nav step id to the existing menu item names
    const menuMap: { [k: string]: string } = {
      declaration: 'declaration',
      modeling: 'modeling',
      evaluation: 'evaluation',
      deployment: 'deployment',
    };
    const menuItem = menuMap[mainStepId] || mainStepId;
    if (!this.stepEnabled(menuItem)) return;
    this.currentStep = menuItem;
    // Auto-expand the clicked step
    this.navExpandedSteps[mainStepId] = true;
    this.scrollToSection(menuItem);
  }

  /** Navigate to a sub-step and scroll to its section */
  navGoToSubStep(event: Event, mainStepId: string, subStepId: string): void {
    event.stopPropagation();
    const menuMap: { [k: string]: string } = {
      declaration: 'declaration',
      modeling: 'modeling',
      evaluation: 'evaluation',
      deployment: 'deployment',
    };
    const menuItem = menuMap[mainStepId] || mainStepId;
    if (!this.stepEnabled(menuItem)) return;
    this.currentStep = menuItem;
    // Scroll to specific sub-step anchor if available
    setTimeout(() => {
      const anchorMap: { [k: string]: string } = {
        '1e': 'data-quality-anchor',
        '2a': 'encoding-anchor',
        '2b': 'modeling-anchor',
        '2c': 'sfs-anchor',
      };
      const anchorId = anchorMap[subStepId];
      if (anchorId) {
        const el = document.getElementById(anchorId);
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }, 50);
  }

  private scrollToSection(item: string): void {
    setTimeout(() => {
      try {
        if (item === 'data quality' || item === 'preprocessing') {
          const el = document.getElementById('data-quality-anchor');
          if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        } else if (item === 'modeling') {
          const el = document.getElementById('modeling-anchor');
          if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      } catch {}
    }, 50);
  }

  /** Get sub-step status: 'completed', 'in_progress', or 'pending' */
  getSubStepStatus(subStepId: string): 'completed' | 'in_progress' | 'pending' {
    const mc = this.sharedService.getModelingCheckpoint();
    switch (subStepId) {
      // Declaration sub-steps
      case '1a': // Pipeline Type
        if (this.isStarted && this.selectedPipeline) return 'completed';
        if (!this.selectedPipeline) return this.currentStep === 'declaration' ? 'in_progress' : 'pending';
        return 'pending';
      case '1b': // Data Upload
        if (this.currentFileId != null) return 'completed';
        if (this.isStarted && this.selectedPipeline && this.currentFileId == null) return 'in_progress';
        return 'pending';
      case '1c': // Data Dictionary Review
        if (this.dataDictionaryCache && this.dataDictionaryCache.length > 0) return 'completed';
        if (this.currentFileId != null && !(this.dataDictionaryCache && this.dataDictionaryCache.length > 0)) return 'in_progress';
        return 'pending';
      case '1d': // Preprocessing
        if (this.preprocessingInitiated && this.rowCountAfter > 0) return 'completed';
        if (this.dataDictionaryCache && this.dataDictionaryCache.length > 0 && !(this.preprocessingInitiated && this.rowCountAfter > 0)) {
          return this.isProcessing ? 'in_progress' : (this.preprocessingAvailable ? 'in_progress' : 'pending');
        }
        return 'pending';
      case '1e': // Data Quality Summary
        if (this.modelingAvailable) return 'completed';
        if (this.datqSummary && this.datqSummary.length > 0) return 'in_progress';
        if (this.preprocessingInitiated && this.rowCountAfter > 0) return 'in_progress';
        return 'pending';

      // Modeling sub-steps
      case '2a': // Categorical Encoding
        if (mc && mc.substep && ['encoding_completed', 'modeling_started', 'modeling_completed',
            'sfs_running', 'sfs_stopped', 'sfs_backward_completed', 'sfs_forward_completed',
            'sfs_completed', 'sfs_forward_from_backward_completed'].includes(mc.substep)) return 'completed';
        if (mc && mc.substep === 'algorithm_selected') return 'in_progress';
        if (this.modelingAvailable && !mc?.substep) return 'in_progress';
        return 'pending';
      case '2b': // Model Training & CV
        if (mc && mc.modelingStatus?.model) return 'completed';
        if (mc && (mc.substep === 'modeling_started' || mc.substep === 'encoding_completed')) return 'in_progress';
        return 'pending';
      case '2c': // SFS
        if (mc && (mc.sfsBackwardResults?.length > 0 || mc.sfsForwardResults?.length > 0)) return 'completed';
        if (mc && mc.modelingStatus?.model && !(mc.sfsBackwardResults?.length > 0 || mc.sfsForwardResults?.length > 0)) return 'in_progress';
        return 'pending';

      // Future steps
      case '3a': return 'pending';
      case '4a': return 'pending';
      default: return 'pending';
    }
  }

  /** Get main step status based on sub-steps */
  getMainStepStatus(mainStepId: string): 'completed' | 'in_progress' | 'pending' {
    const step = this.navMainSteps.find(s => s.id === mainStepId);
    if (!step) return 'pending';
    const statuses = step.subSteps.map(s => this.getSubStepStatus(s.id));
    if (statuses.every(s => s === 'completed')) return 'completed';
    if (statuses.some(s => s === 'in_progress' || s === 'completed')) return 'in_progress';
    return 'pending';
  }

  /** Get main step progress percentage (0–100) */
  getMainStepProgressPct(mainStepId: string): number {
    const step = this.navMainSteps.find(s => s.id === mainStepId);
    if (!step) return 0;
    const completed = step.subSteps.filter(s => this.getSubStepStatus(s.id) === 'completed').length;
    return Math.round((completed / step.subSteps.length) * 100);
  }

  /** Overall pipeline progress percentage */
  getOverallProgress(): number {
    const allSubs = this.navMainSteps.flatMap(m => m.subSteps);
    const completed = allSubs.filter(s => this.getSubStepStatus(s.id) === 'completed').length;
    return Math.round((completed / allSubs.length) * 100);
  }

  // ===== Encoding Step Methods =====

  goToEncoding(): void {
    // For boosting pipeline, skip encoding and go directly to modeling
    this.goToModelingFromDQ();
  }

  goToModelingFromDQ(): void {
    this.sharedService.setModelUsageSettings(this.variableModelUsage);
    this.modelingAvailable = true;
    this.currentStep = 'modeling';
    this.detailedStep = '3a_encoding';
    // Auto-save checkpoint: modeling
    this.saveCheckpoint('modeling');
    setTimeout(() => {
      try {
        const el = document.getElementById('modeling-anchor');
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      } catch {}
    }, 100);
  }

  analyzeEncoding(): void {
    if (!this.currentFileId || !this.processedFilePath) return;
    this.encodingAnalyzing = true;
    this.encodingError = null;
    const excluded = this.getExcludedVariables();
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

  applyEncoding(): void {
    if (!this.currentFileId || !this.processedFilePath) return;
    this.encodingApplying = true;
    this.encodingError = null;
    // Init rankings for ordinal features that need them
    for (const e of this.encodingPlan) {
      if (e.needs_ranking && (!e.ranking || !e.ranking.length)) {
        e.ranking = [...(e.unique_values || [])];
      }
    }
    this.dataService.applyEncoding(
      this.currentFileId, this.processedFilePath, this.encodingPlan, this.encodingUseNative
    ).subscribe({
      next: (resp: any) => {
        this.encodingReport = Array.isArray(resp.report) ? resp.report : [];
        this.encodingSummary = resp.summary || null;
        this.encodedFilePath = resp.encoded_file || null;
        this.encodingApplied = true;
        this.encodingApplying = false;
        // Share encoded file path and encoding report for modeling
        this.sharedService.setEncodedFilePath(this.encodedFilePath);
        this.sharedService.setEncodingReport(this.encodingReport);
      },
      error: (err: any) => {
        this.encodingError = 'Failed to apply encoding: ' + (err?.message || err);
        this.encodingApplying = false;
      }
    });
  }

  goToModelingFromEncoding(): void {
    this.sharedService.setModelUsageSettings(this.variableModelUsage);
    this.modelingAvailable = true;
    this.currentStep = 'modeling';
    setTimeout(() => {
      try {
        const el = document.getElementById('modeling-anchor');
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      } catch {}
    }, 100);
  }

  getFeatureDescription(featureName: string): string {
    if (!this.dataDictionaryCache || !this.dataDictionaryCache.length) return '';
    const entry = this.dataDictionaryCache.find((d: any) => d?.Feature_Name === featureName);
    return entry?.Feature_Description || '';
  }

  isNativeCategorical(mapping: any): boolean {
    return mapping?.type === 'native_categorical';
  }

  getNativeCategories(mapping: any): string[] {
    if (!mapping || mapping.type !== 'native_categorical') return [];
    return mapping.categories || [];
  }

  formatMappingPairs(mapping: any): { original: string; encoded: string }[] {
    if (!mapping) return [];
    const type = mapping.type || '';
    if (type === 'native_categorical') {
      return [];
    }
    if (type === 'label_encoding' || type === 'ordinal_encoding') {
      const m = mapping.mapping || {};
      return Object.entries(m).map(([k, v]) => ({ original: k, encoded: String(v) }));
    }
    if (type === 'target_encoding') {
      const m = mapping.mapping || {};
      return Object.entries(m).map(([k, v]) => ({ original: k, encoded: String(v) }));
    }
    if (type === 'one_hot_encoding') {
      const cols: string[] = mapping.columns || [];
      return cols.map((c: string) => ({ original: c, encoded: '0/1' }));
    }
    return [];
  }

  getStrategyLabel(strategy: string): string {
    const labels: { [k: string]: string } = {
      'native_categorical': 'XGBoost Native Categorical',
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
      'one_hot_encoding': '#388e3c',
      'ordinal_encoding': '#f57c00',
      'target_encoding': '#c62828',
    };
    return colors[strategy] || '#555';
  }
}