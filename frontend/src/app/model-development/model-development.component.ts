import { Component, OnInit, HostListener } from '@angular/core';
import { Router } from '@angular/router';
import { switchMap, finalize } from 'rxjs/operators';
import { SharedService } from '../services/shared.service';
import { MatSelectChange } from '@angular/material/select';
import { Subscription } from 'rxjs';
import { DataService } from '../services/data.service';
import { MatDialog } from '@angular/material/dialog';
import { FeatureCardComponent } from '../feature-card/feature-card.component';

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

export class ModelDevelopmentComponent implements OnInit {
  currentRoute: string = '';
  menuItems = ['declaration', 'preprocessing', 'data quality', 'modeling', 'evaluation', 'deployment'];
  selectedPipeline: string = '';
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
  processedFilePath: string | null = null;
  isProcessing: boolean = false;
  // New state flags for progressive reveal
  isStarted: boolean = false;
  modelingAvailable: boolean = false;
  preprocessingAvailable: boolean = false;
  // Purifier breakdown: which columns were dropped at which step, and how many rows were removed
  droppedColumnsByStep: Array<{ step: string; option_ids?: number[]; threshold?: number; columns: string[]; rows_removed?: number }>= [];
  // Total rows removed across all preprocessing steps
  rowsRemovedTotal: number = 0;
  // Row counts before/after preprocessing run (for summary display)
  rowCountBefore: number = 0;
  rowCountAfter: number = 0;
  preprocessingInitiated: boolean = false;

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
  ];

  private defaultOptionIds: number[] = [1, 2, 3, 4, 7, 11, 17, 23, 28];
  selectedOptions: PurifierOption[] = this.purifierOptions.filter(o => this.defaultOptionIds.includes(o.id));

  constructor(private router: Router, private sharedService: SharedService, private dataService: DataService, private dialog: MatDialog) {}

  ngOnInit() {
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
        this.isStarted = started;
        this.computePreprocessingAvailable();
      })
    );

    // Do not auto-enable modeling on preprocessing result; user will click "Proceed to Modeling"
    this.subscription.add(
      this.sharedService.preprocessingRunResult$.subscribe((_result: any) => {
        this.modelingAvailable = false;
      })
    );

    // Track when user explicitly moves from Declaration to Preprocessing
    this.subscription.add(
      this.sharedService.preprocessingInitiated$.subscribe((initiated: boolean) => {
        this.preprocessingInitiated = initiated;
        this.computePreprocessingAvailable();
        // Update flow indicator to preprocessing step when user clicks preprocessing button
        if (initiated) {
          this.currentStep = 'preprocessing';
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

  ngOnDestroy() {
    this.subscription.unsubscribe();
  }
  
  onPipelineChange(event: Event) {
    const select = event.target as HTMLSelectElement;
    this.selectedPipeline = select.value;
    // Here you can add logic to handle the pipeline change
    console.log('Selected pipeline:', this.selectedPipeline);
    this.sharedService.setSelectedPipeline(this.selectedPipeline);
  }

  onStartClick() {
    if (this.selectedPipeline) {
      // Reset state for a clean run
      this.sharedService.setCurrentFileId(null);
      this.sharedService.setPreprocessingInitiated(false);
      this.sharedService.setPreprocessingRunResult(null);
      this.sharedService.setProcessedFilePath(null);
      this.selectedOptions = this.purifierOptions.filter(o => this.defaultOptionIds.includes(o.id));
      this.modelingAvailable = false;
      this.preprocessingAvailable = false;
      this.currentStep = 'declaration';
      // Start pipeline
      this.sharedService.setStarted(true);
    }
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
    this.dataService.runPreprocessing(this.currentFileId, optionIds, split, excludedVariables)
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
          // Navigate to Data Quality section
          if (this.datqSummary && this.datqSummary.length > 0) {
            this.currentStep = 'data quality';
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
        }
      );
  }

  // Helpers for UI
  droppedTotalCount(): number {
    try {
      return (this.droppedColumnsByStep || []).reduce((acc, s) => acc + (Array.isArray(s.columns) ? s.columns.length : 0), 0);
    } catch { return 0; }
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

  // ===== Encoding Step Methods =====

  goToEncoding(): void {
    // For boosting pipeline, skip encoding and go directly to modeling
    this.goToModelingFromDQ();
  }

  goToModelingFromDQ(): void {
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