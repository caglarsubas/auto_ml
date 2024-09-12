import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class DataService {
  private apiUrl = 'http://localhost:8000/api/';  // Update this with your Django backend URL

  constructor(private http: HttpClient) { }

  uploadFile(file: File): Observable<any> {
    const formData = new FormData();
    formData.append('file', file, file.name);
    return this.http.post(`${this.apiUrl}data-files/`, formData);
  }

  getDataPreview(fileId: string): Observable<any> {
    return this.http.get(`${this.apiUrl}data-files/${fileId}/preview/`);
  }

  getDataDictionary(fileId: string): Observable<any> {
    return this.http.get(`${this.apiUrl}data-files/${fileId}/data_dictionary/`);
  }

  getFeatureCard(fileId: string, columnName: string): Observable<any> {
    return this.http.get(`${this.apiUrl}feature-card/${fileId}/get_feature_info/?column=${encodeURIComponent(columnName)}`);
  }

  // Add more methods as needed
}