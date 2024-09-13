import { Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError, tap } from 'rxjs/operators';

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

  getStackedFeatureData(fileId: string, columnName: string): Observable<any> {
    const url = `${this.apiUrl}feature-card/${fileId}/get_stacked_feature_data/?column=${encodeURIComponent(columnName)}`;
    console.log('Requesting URL:', url);
    return this.http.get(url).pipe(
      tap(data => console.log('Raw response:', data)),
      catchError(error => {
        console.error('Error in getStackedFeatureData:', error);
        if (error instanceof SyntaxError) {
          console.error('JSON parsing error:', error.message);
        }
        return throwError(() => new Error(error.message || 'An unknown error occurred'));
      })
    );
  }
  
  private handleError(error: HttpErrorResponse) {
    console.error('An error occurred:', error);
    let errorMessage = 'An unknown error occurred';
    if (error.error instanceof ErrorEvent) {
      errorMessage = `Error: ${error.error.message}`;
    } else {
      errorMessage = `Error Code: ${error.status}\nMessage: ${error.message}`;
    }
    return throwError(() => new Error(errorMessage));
  }
}