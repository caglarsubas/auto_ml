import { Component, OnInit, OnDestroy } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { MatDialog } from '@angular/material/dialog';
import { FeatureCardComponent } from '../feature-card/feature-card.component';
import * as XLSX from 'xlsx';
import { SharedService } from '../services/shared.service';
import { combineLatest, Observable, Subscription } from 'rxjs';
import { map } from 'rxjs/operators';
import { Router } from '@angular/router';
import { environment } from '../../environments/environment';

@Component({
  selector: 'app-declaration',
  templateUrl: './declaration.component.html',
  styleUrls: ['./declaration.component.css'],
})

export class DeclarationComponent implements OnInit, OnDestroy {
  selectedFiles: File[] = [];
  selectedDictionaryFile: File | null = null;
  previewData: any = null;
  dataDictionary: any[] = [];
  currentFileId: number | null = null;
  errorMessage: string | null = null;
  showUseExistingButton: boolean = false;
  existingFileName: string | null = null;
  showDataDictionaryCollection: boolean = false;
  firstLineIsNotHeader: boolean = false;
  columnSeparator: string = 'semicolon';
  isExcelFile: boolean = false;
  hasMultipleSheets: boolean = false;
  firstSheetHasNotDataset: boolean = false;
  showContent: boolean = false;
  private subscription: Subscription = new Subscription();
  mergeColumnWise: boolean = false;
  preprocessingInitiated: boolean = false;
  private apiBase = environment.apiBaseUrl;

  // Pipeline commentary notes (synced via SharedService)
  pipelineNotes: { [position: string]: string } = {};
  editingNotePosition: string | null = null;
  private _noteSaveTimer: any = null;

  // Split controls for PSI/CSI computation in Data Dictionary
  splitStrategy: 'random' | 'oot' = 'random';
  splitDateColumn: string | null = null;
  splitCutoff: string = '';

  // Model_Usage tracking for Data Dictionary
  variableModelUsage: { [featureName: string]: string } = {};
  private readonly modelUsageKey = 'dict_model_usage_v1';

  constructor(
    private http: HttpClient,
    private dialog: MatDialog,
    private sharedService: SharedService,
    private router: Router
  ) {}

  ngOnInit() {
    this.subscription.add(
      combineLatest([
        this.sharedService.isStarted$,
        this.sharedService.selectedPipeline$,
        this.sharedService.preprocessingInitiated$
      ]).subscribe(([isStarted, selectedPipeline, preprocessingInitiated]) => {
        this.showContent = isStarted && !!selectedPipeline;
        this.preprocessingInitiated = preprocessingInitiated;
      })
    );

    // Sync pipeline notes from SharedService
    this.subscription.add(
      this.sharedService.pipelineNotes$.subscribe((notes) => {
        this.pipelineNotes = notes;
      })
    );

    // Auto-hydrate when file ID is set externally (e.g., from loadPipelineRun restore)
    this.subscription.add(
      this.sharedService.currentFileId$.subscribe((id: number | null) => {
        if (id !== null && id !== this.currentFileId) {
          this.currentFileId = id;
          this.getPreview(id);
          this.showDataDictionaryCollection = true;
          // Fetch existing data dictionary
          this.http.get(`${this.apiBase}declaration/${id}/data_dictionary/`)
            .subscribe(
              (data: any) => {
                if (Array.isArray(data) && data.length > 0) {
                  this.dataDictionary = data;
                  this.initializeModelUsageFromBackend(data);
                  this.pushDeclarationAiContext();
                }
              },
              () => { /* dictionary may not exist yet — that's fine */ }
            );
        }
      })
    );

    // Listen for data refresh events (e.g., after AI creates features)
    this.subscription.add(
      this.sharedService.dataRefresh$.subscribe(() => {
        if (this.currentFileId !== null) {
          console.log('[Declaration] Data refresh triggered — re-fetching preview and dictionary');
          this.getPreview(this.currentFileId);
          this.http.get(`${this.apiBase}declaration/${this.currentFileId}/data_dictionary/`)
            .subscribe(
              (data: any) => {
                if (Array.isArray(data) && data.length > 0) {
                  this.dataDictionary = data;
                  this.initializeModelUsageFromBackend(data);
                  this.pushDeclarationAiContext();
                }
              },
              () => { /* dictionary may not exist yet */ }
            );
        }
      })
    );

    // Load saved model usage settings
    this.loadModelUsage();
  }

  ngOnDestroy() {
    if (this.subscription) {
      this.subscription.unsubscribe();
    }
  }

  // ── Pipeline Commentary Notes ──

  onNoteChanged(position: string, content: string): void {
    this.pipelineNotes[position] = content;
    this.sharedService.updatePipelineNote(position, content);
    if (this._noteSaveTimer) clearTimeout(this._noteSaveTimer);
    this._noteSaveTimer = setTimeout(() => {
      this.sharedService.triggerCheckpoint('decl_note_updated');
    }, 1000);
  }

  toggleNoteEdit(position: string): void {
    this.editingNotePosition = this.editingNotePosition === position ? null : position;
  }

  deleteNote(position: string): void {
    delete this.pipelineNotes[position];
    this.sharedService.updatePipelineNote(position, '');
    this.editingNotePosition = null;
    this.sharedService.triggerCheckpoint('decl_note_updated');
  }

  hasNote(position: string): boolean {
    return !!this.pipelineNotes[position]?.trim();
  }

  onFilesSelected(event: any): void {
    this.selectedFiles = Array.from(event.target.files);
    this.errorMessage = null;
    this.showUseExistingButton = false;
    this.columnSeparator = 'semicolon';
    
    // Reset Excel-related properties
    this.isExcelFile = false;
    this.hasMultipleSheets = false;
    this.firstSheetHasNotDataset = false;

    if (this.selectedFiles.length > 0) {
      const fileName = this.selectedFiles[0].name.toLowerCase();
      if (fileName.endsWith('.xlsx') || fileName.endsWith('.xls')) {
        this.isExcelFile = true;
        this.checkExcelSheets();
      } else if (fileName.endsWith('.csv') || fileName.endsWith('.txt') || fileName.endsWith('.tsv')) {
        this.detectCsvSeparator(this.selectedFiles[0]);
      }
    }
    // Reset mergeColumnWise when only one file is selected
    if (this.selectedFiles.length <= 1) {
      this.mergeColumnWise = false;
    }
  }

  private detectCsvSeparator(file: File): void {
    const reader = new FileReader();
    reader.onload = (e: any) => {
      const text: string = e.target.result;
      // Take first 5 lines for analysis
      const lines = text.split(/\r?\n/).filter(l => l.trim().length > 0).slice(0, 5);
      if (lines.length === 0) return;

      const candidates: { char: string; key: string }[] = [
        { char: ',', key: 'comma' },
        { char: ';', key: 'semicolon' },
        { char: '\t', key: 'tab' },
        { char: ' ', key: 'space' }
      ];

      // For each candidate, count occurrences per line and check consistency
      let bestKey = 'semicolon';
      let bestScore = -1;

      for (const sep of candidates) {
        const counts = lines.map(line => {
          // Count separators outside quoted strings
          let count = 0;
          let inQuote = false;
          for (const ch of line) {
            if (ch === '"') { inQuote = !inQuote; }
            else if (!inQuote && ch === sep.char) { count++; }
          }
          return count;
        });
        // All lines should have > 0 and roughly the same count
        const minCount = Math.min(...counts);
        const maxCount = Math.max(...counts);
        if (minCount <= 0) continue;
        // Score: higher min count is better; penalize inconsistency
        const consistency = minCount / (maxCount || 1);
        const score = minCount * consistency;
        if (score > bestScore) {
          bestScore = score;
          bestKey = sep.key;
        }
      }

      this.columnSeparator = bestKey;
      console.log(`[CSV Auto-detect] Detected separator: ${bestKey}`);
    };
    // Read only first 8KB — enough for header detection
    const slice = file.slice(0, 8192);
    reader.readAsText(slice);
  }

  checkExcelSheets(): void {
    const reader = new FileReader();
    reader.onload = (e: any) => {
      const data = new Uint8Array(e.target.result);
      const workbook = XLSX.read(data, {type: 'array'});
      this.hasMultipleSheets = workbook.SheetNames.length > 1;
    };
    reader.readAsArrayBuffer(this.selectedFiles[0] as Blob);
  }

  onDictionaryFileSelected(event: any): void {
    this.selectedDictionaryFile = event.target.files[0];
  }

  onUpload(): void {
    if (this.selectedFiles.length > 0) {
      const formData = new FormData();
      this.selectedFiles.forEach((file, index) => {
        formData.append(`file${index}`, file, file.name);
      });
      formData.append('first_line_is_not_header', this.firstLineIsNotHeader.toString());
      formData.append('column_separator', this.columnSeparator);
      formData.append('first_sheet_has_not_dataset', this.firstSheetHasNotDataset.toString());
      formData.append('merge_column_wise', this.mergeColumnWise.toString());

      this.http.post(`${this.apiBase}declaration/`, formData)
        .subscribe(
          (response: any) => {
            console.log('File uploaded successfully', response);
            this.currentFileId = response.id;
            this.sharedService.setCurrentFileId(this.currentFileId);
            if (this.currentFileId !== null) {
              this.getPreview(this.currentFileId);
            }
            this.errorMessage = null;
            this.showUseExistingButton = false;
            this.showDataDictionaryCollection = true;
            // Checkpoint: data imported
            this.sharedService.triggerCheckpoint('decl_data_imported');
          },
          (error: HttpErrorResponse) => {
            console.error('Error uploading file:', error);
            this.errorMessage = 'An error occurred while uploading the file: ' + (error.error?.error || error.message);
            if (error.status === 409) {
              this.showUseExistingButton = true;
              this.existingFileName = this.selectedFiles[0]?.name || null;
            } else {
              this.showUseExistingButton = false;
            }
            // Log more details about the error
            if (error.error instanceof ErrorEvent) {
              console.error('Client-side error:', error.error.message);
            } else {
              console.error('Server-side error:', error.status, error.error);
            }
          }
        );
    }
  }

  useExistingFile(): void {
    if (this.existingFileName) {
      this.http.get(`${this.apiBase}declaration/by-name/${this.existingFileName}/`)
        .subscribe(
          (response: any) => {
            this.currentFileId = response.id;
            this.sharedService.setCurrentFileId(this.currentFileId);
            if (this.currentFileId !== null) {
              this.getPreview(this.currentFileId);
            }
            this.errorMessage = null;
            this.showUseExistingButton = false;
            // Show Data Dictionary Collection after using existing file
            this.showDataDictionaryCollection = true;
            // Checkpoint: data imported (via existing file)
            this.sharedService.triggerCheckpoint('decl_data_imported');
          },
          error => {
            console.error('Error fetching existing file:', error);
            this.errorMessage = 'An error occurred while fetching the existing file.';
          }
        );
    }
  }

  getPreview(fileId: number): void {
    this.http.get(`${this.apiBase}declaration/${fileId}/preview/`)
      .subscribe(
        (data: any) => {
          this.previewData = data;
          // Default OOT date column candidate if exists
          const cols: string[] = Array.isArray(data?.columns) ? data.columns : [];
          if (cols.length && !this.splitDateColumn) {
            const dateLike = cols.find(c => /date|time|dt/i.test(String(c)));
            this.splitDateColumn = dateLike || null;
          }
          if (this.firstLineIsNotHeader) {
            this.previewData.note = "Note: First line is treated as data, generic headers are used.";
          }
          this.showDataDictionaryCollection = true;
          // Push data preview to cumulative AI context
          this.pushDeclarationAiContext();
        },
        error => console.error('Error getting preview:', error)
      );
  }

  onGenerateDataDictionary(withUpload: boolean): void {
    if (this.currentFileId === null) {
      console.error('No file has been uploaded yet');
      return;
    }

    const formData = new FormData();
    if (withUpload && this.selectedDictionaryFile) {
      formData.append('dictionary', this.selectedDictionaryFile);
    }
    // Append split settings for PSI/CSI
    formData.append('split_strategy', this.splitStrategy);
    if (this.splitStrategy === 'oot') {
      if (!this.splitDateColumn || !this.splitCutoff) {
        console.error('Please select a date column and cutoff for OOT split.');
        return;
      }
      formData.append('date_column', this.splitDateColumn);
      formData.append('cutoff', this.splitCutoff);
    }

    this.http.post(`${this.apiBase}declaration/${this.currentFileId}/data_dictionary/`, formData)
      .subscribe(
        (data: any) => {
          this.dataDictionary = data;
          // Initialize Model_Usage with backend's predetermined values (unless user has overridden)
          this.initializeModelUsageFromBackend(data);
          // Push dictionary to cumulative AI context
          this.pushDeclarationAiContext();
          // Checkpoint: dictionary generated
          this.sharedService.triggerCheckpoint('decl_dictionary_generated');
        },
        error => console.error('Error generating data dictionary:', error)
      );
  }

  openFeatureCard(feature: any): void {
    if (this.currentFileId !== null && feature.Feature_Name) {
      const features = this.dataDictionary.map(item => ({
        Feature_Name: item.Feature_Name,
        Feature_Description: item.Feature_Description || 'No description available'
      }));
      this.dialog.open(FeatureCardComponent, {
        width: '600px',
        data: { 
          fileId: this.currentFileId.toString(), 
          columnName: feature.Feature_Name,
          features: features
        }
      });
    } else {
      console.error('Cannot open feature card: fileId or columnName is missing');
      // Optionally show an error message to the user
    }
  }

  goToPreprocessing(): void {
    // Push current Model_Usage settings to SharedService before proceeding
    this.sharedService.setModelUsageSettings(this.variableModelUsage);
    this.sharedService.setPreprocessingInitiated(true);
  }

  // Get model usage for a feature
  getModelUsage(featureName: string): string {
    // Check if user has set a value (either from localStorage or manual selection)
    if (this.variableModelUsage[featureName] !== undefined) {
      return this.variableModelUsage[featureName];
    }
    // Fall back to backend's predetermined value from data dictionary
    const feature = this.dataDictionary.find(f => f.Feature_Name === featureName);
    if (feature && feature.Model_Usage_YN) {
      return feature.Model_Usage_YN;
    }
    // Default to 'Yes' if no backend value
    return 'Yes';
  }

  // Set model usage for a feature
  setModelUsage(featureName: string, value: string): void {
    this.variableModelUsage[featureName] = value;
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

  // Initialize Model_Usage from backend's predetermined values
  private initializeModelUsageFromBackend(dataDictionary: any[]): void {
    if (!Array.isArray(dataDictionary)) return;
    
    // For each feature in the data dictionary
    dataDictionary.forEach(feature => {
      const featureName = feature.Feature_Name;
      const backendValue = feature.Model_Usage_YN;
      
      // Only initialize if:
      // 1. Feature has a backend value
      // 2. User hasn't already set a value (localStorage override)
      if (featureName && backendValue && this.variableModelUsage[featureName] === undefined) {
        this.variableModelUsage[featureName] = backendValue;
      }
    });
    
    // Save the initialized values (merging with any existing user overrides)
    this.saveModelUsage();
  }

  /** Push declaration-level data into the cumulative AI context in SharedService. */
  private pushDeclarationAiContext(): void {
    const existing = this.sharedService.getAiCumulativeContext() || {};
    const declCtx: any = {};
    // Data preview info
    if (this.previewData) {
      declCtx.data_preview = {
        total_rows: this.previewData.total_rows,
        total_columns: this.previewData.total_columns,
        columns: this.previewData.columns,
        file_name: this.selectedFiles?.[0]?.name || this.existingFileName || null,
      };
    }
    // Data dictionary
    if (this.dataDictionary && this.dataDictionary.length > 0) {
      declCtx.data_dictionary = this.dataDictionary.map((d: any) => ({
        Feature_Name: d?.Feature_Name,
        Data_Type: d?.Data_Type,
        Level_of_Measurement: d?.Level_of_Measurement,
        Unique_Values: d?.['#_of_Unique_Value'],
        Missing_Ratio: d?.Missing_Ratio,
        Mode_Ratio: d?.Mode_Ratio,
        Model_Usage_YN: this.getModelUsage(d?.Feature_Name),
        Feature_Description: d?.Feature_Description || null,
      }));
    }
    // Model usage exclusions
    const excluded = this.getExcludedFeatures();
    if (excluded.length > 0) {
      declCtx.model_usage_exclusions = excluded;
    }
    // Merge into existing cumulative context
    const merged = { ...existing, ...declCtx };
    // Preserve pipeline_config from other components
    if (existing.pipeline_config) {
      merged.pipeline_config = existing.pipeline_config;
    }
    this.sharedService.setAiCumulativeContext(merged);
  }

  // Get list of features marked as 'No' (excluded from model)
  getExcludedFeatures(): string[] {
    // Include both user-set values and backend-determined values
    const excluded: string[] = [];
    
    // Add user-set 'No' values
    Object.keys(this.variableModelUsage).forEach(f => {
      if (this.variableModelUsage[f] === 'No') {
        excluded.push(f);
      }
    });
    
    // Add backend-determined 'No' values that user hasn't overridden
    this.dataDictionary.forEach(feature => {
      const featureName = feature.Feature_Name;
      if (feature.Model_Usage_YN === 'No' && 
          this.variableModelUsage[featureName] === undefined &&
          !excluded.includes(featureName)) {
        excluded.push(featureName);
      }
    });
    
    return excluded;
  }
  
}