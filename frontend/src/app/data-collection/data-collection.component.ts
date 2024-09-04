// src/app/data-collection/data-collection.component.ts
import { Component } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';

@Component({
  selector: 'app-data-collection',
  templateUrl: './data-collection.component.html',
  styleUrls: ['./data-collection.component.css']
})
export class DataCollectionComponent {
  selectedFile: File | null = null;
  selectedDictionaryFile: File | null = null;
  previewData: any = null;
  dataDictionary: any[] = [];
  currentFileId: number | null = null;
  errorMessage: string | null = null;
  showUseExistingButton: boolean = false;
  existingFileName: string | null = null;

  constructor(private http: HttpClient) {}

  onFileSelected(event: any): void {
    this.selectedFile = event.target.files[0];
    this.errorMessage = null;
    this.showUseExistingButton = false;
  }

  onDictionaryFileSelected(event: any): void {
    this.selectedDictionaryFile = event.target.files[0];
  }

  onUpload(): void {
    if (this.selectedFile) {
      const formData = new FormData();
      formData.append('file', this.selectedFile);
      formData.append('name', this.selectedFile.name);

      this.http.post('http://localhost:8000/api/data-files/', formData)
        .subscribe(
          (response: any) => {
            console.log('File uploaded successfully');
            this.currentFileId = response.id;
            if (this.currentFileId !== null) {
              this.getPreview(this.currentFileId);
            }
            this.getPreview(response.id);
            this.errorMessage = null;
            this.showUseExistingButton = false;
          },
          (error: HttpErrorResponse) => {
            if (error.status === 409) {
              this.errorMessage = error.error.error;
              this.showUseExistingButton = true;
              this.existingFileName = this.selectedFile?.name || null;
            } else {
              this.errorMessage = 'An error occurred while uploading the file.';
              this.showUseExistingButton = false;
            }
            console.error('Error uploading file:', error);
          }
        );
    }
  }

  useExistingFile(): void {
    if (this.existingFileName) {
      this.http.get(`http://localhost:8000/api/data-files/by-name/${this.existingFileName}/`)
        .subscribe(
          (response: any) => {
            this.currentFileId = response.id;
            if (this.currentFileId !== null) {
              this.getPreview(this.currentFileId);
            }
            this.errorMessage = null;
            this.showUseExistingButton = false;
          },
          error => {
            console.error('Error fetching existing file:', error);
            this.errorMessage = 'An error occurred while fetching the existing file.';
          }
        );
    }
  }

  getPreview(fileId: number): void {
    this.http.get(`http://localhost:8000/api/data-files/${fileId}/preview/`)
      .subscribe(
        (data: any) => {
          this.previewData = data;
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

    this.http.post(`http://localhost:8000/api/data-files/${this.currentFileId}/data_dictionary/`, formData)
      .subscribe(
        (data: any) => {
          this.dataDictionary = data;
        },
        error => console.error('Error generating data dictionary:', error)
      );
  }
}