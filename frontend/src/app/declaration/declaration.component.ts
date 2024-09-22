import { Component } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { MatDialog } from '@angular/material/dialog';
import { FeatureCardComponent } from '../feature-card/feature-card.component';
import * as XLSX from 'xlsx';

@Component({
  selector: 'app-declaration',
  templateUrl: './declaration.component.html',
  styleUrls: ['./declaration.component.css']
})
export class DeclarationComponent {
  selectedFile: File | null = null;
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

  constructor(private http: HttpClient, private dialog: MatDialog) {}

  onFileSelected(event: any): void {
    this.selectedFile = event.target.files[0];
    this.errorMessage = null;
    this.showUseExistingButton = false;
    this.columnSeparator = 'semicolon';
    
    // Reset Excel-related properties
    this.isExcelFile = false;
    this.hasMultipleSheets = false;
    this.firstSheetHasNotDataset = false;

    if (this.selectedFile) {
      const fileName = this.selectedFile.name.toLowerCase();
      if (fileName.endsWith('.xlsx') || fileName.endsWith('.xls')) {
        this.isExcelFile = true;
        this.checkExcelSheets();
      }
    }
  }

  checkExcelSheets(): void {
    const reader = new FileReader();
    reader.onload = (e: any) => {
      const data = new Uint8Array(e.target.result);
      const workbook = XLSX.read(data, {type: 'array'});
      this.hasMultipleSheets = workbook.SheetNames.length > 1;
    };
    reader.readAsArrayBuffer(this.selectedFile as Blob);
  }

  onDictionaryFileSelected(event: any): void {
    this.selectedDictionaryFile = event.target.files[0];
  }

  onUpload(): void {
    if (this.selectedFile) {
      const formData = new FormData();
      formData.append('file', this.selectedFile, this.selectedFile.name);
      formData.append('name', this.selectedFile.name);
      formData.append('first_line_is_not_header', this.firstLineIsNotHeader.toString());
      formData.append('column_separator', this.columnSeparator);
      formData.append('first_sheet_has_not_dataset', this.firstSheetHasNotDataset.toString());

      this.http.post('http://localhost:8000/api/declaration/', formData)
        .subscribe(
          (response: any) => {
            console.log('File uploaded successfully', response);
            this.currentFileId = response.id;
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
              this.existingFileName = this.selectedFile?.name || null;
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
      this.http.get(`http://localhost:8000/api/declaration/by-name/${this.existingFileName}/`)
        .subscribe(
          (response: any) => {
            this.currentFileId = response.id;
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
    this.http.get(`http://localhost:8000/api/declaration/${fileId}/preview/`)
      .subscribe(
        (data: any) => {
          this.previewData = data;
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

    this.http.post(`http://localhost:8000/api/declaration/${this.currentFileId}/data_dictionary/`, formData)
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
        width: '400px',
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
}