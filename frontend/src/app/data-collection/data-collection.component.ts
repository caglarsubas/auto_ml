// src/app/data-collection/data-collection.component.ts
import { Component } from '@angular/core';
import { HttpClient } from '@angular/common/http';

@Component({
  selector: 'app-data-collection',
  templateUrl: './data-collection.component.html',
  styleUrls: ['./data-collection.component.css']
})
export class DataCollectionComponent {
  selectedFile: File | null = null;
  previewData: any = null;

  constructor(private http: HttpClient) {}

  onFileSelected(event: any): void {
    this.selectedFile = event.target.files[0];
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
            this.getPreview(response.id);
          },
          error => console.error('Error uploading file:', error)
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
}