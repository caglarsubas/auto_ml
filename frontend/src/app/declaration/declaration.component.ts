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

  // Split controls for PSI/CSI computation in Data Dictionary
  splitStrategy: 'random' | 'oot' = 'random';
  splitDateColumn: string | null = null;
  splitCutoff: string = '';

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
  }

  ngOnDestroy() {
    if (this.subscription) {
      this.subscription.unsubscribe();
    }
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
      }
    }
    // Reset mergeColumnWise when only one file is selected
    if (this.selectedFiles.length <= 1) {
      this.mergeColumnWise = false;
    }
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
    this.sharedService.setPreprocessingInitiated(true);
  }
  
}