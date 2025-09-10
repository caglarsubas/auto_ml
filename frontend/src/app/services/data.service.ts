import { Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError, tap, map } from 'rxjs/operators';
import { environment } from '../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class DataService {
  private apiUrl = environment.apiBaseUrl;

  constructor(private http: HttpClient) { }

  uploadFile(file: File): Observable<any> {
    const formData = new FormData();
    formData.append('file', file, file.name);
    return this.http.post(`${this.apiUrl}declaration/`, formData);
  }

  getDataPreview(fileId: string): Observable<any> {
    return this.http.get(`${this.apiUrl}declaration/${fileId}/preview/`);
  }

  getDataDictionary(fileId: string): Observable<any> {
    return this.http.get(`${this.apiUrl}declaration/${fileId}/data_dictionary/`);
  }

  getFeatureCard(fileId: string, columnName: string): Observable<any> {
    return this.http.get(`${this.apiUrl}feature-card/${fileId}/get_feature_info/?column=${encodeURIComponent(columnName)}`);
  }

  getStackedFeatureData(fileId: string, columnName: string): Observable<any> {
    const url = `${this.apiUrl}feature-card/${fileId}/get_stacked_feature_data/?column=${encodeURIComponent(columnName)}`;
    console.log('Requesting URL:', url);
    return this.http.get(url).pipe(
      tap((data: any) => console.log('Raw response:', data)),
      map((data: any) => this.preprocessStackedData(data)),
      catchError((error: any) => {
        console.error('Error in getStackedFeatureData:', error);
        if (error instanceof SyntaxError) {
          console.error('JSON parsing error:', error.message);
        }
        return throwError(() => new Error(error.message || 'An unknown error occurred'));
      })
    );
  }

  // Submit selected preprocessing options for a given file
  applyPreprocessing(fileId: number, options: number[]): Observable<any> {
    const payload = { file_id: fileId, options };
    return this.http.post(`${this.apiUrl}preprocessing/apply/`, payload).pipe(
      catchError((error: any) => {
        console.error('Error applying preprocessing:', error);
        return throwError(() => new Error(error.message || 'Failed to apply preprocessing'));
      })
    );
  }

  // Run preprocessing. If options omitted, backend uses previously saved config.
  // Optional split: { strategy: 'random' | 'oot', date_column?: string, cutoff?: string, percent?: number }
  runPreprocessing(fileId: number, options?: number[], split?: { strategy?: string; date_column?: string; cutoff?: string; percent?: number }): Observable<any> {
    const payload: any = { file_id: fileId };
    if (options) payload.options = options;
    if (split) payload.split = split;
    return this.http.post(`${this.apiUrl}preprocessing/run/`, payload).pipe(
      catchError((error: any) => {
        console.error('Error running preprocessing:', error);
        return throwError(() => new Error(error.message || 'Failed to run preprocessing'));
      })
    );
  }

  // Get detailed PSI report for a specific variable from processed file
  getDatqDetail(fileId: number, processedFile: string, column: string, split?: { strategy?: string; date_column?: string; cutoff?: string; percent?: number }): Observable<any> {
    const payload: any = { file_id: fileId, processed_file: processedFile, column };
    if (split) payload.split = split;
    return this.http.post(`${this.apiUrl}preprocessing/datq_detail/`, payload).pipe(
      catchError((error: any) => {
        console.error('Error getting datq detail:', error);
        return throwError(() => new Error(error.message || 'Failed to get data quality detail'));
      })
    );
  }

  // Get monthly rolling PSI/CSI time series for a variable
  getDatqTimeseries(
    fileId: number,
    processedFile: string,
    column: string,
    dateColumn: string,
    metric: 'psi' | 'csi' = 'psi',
    windows?: number[],
    minBinShareAllowed?: number,
    split?: { strategy?: string; date_column?: string; cutoff?: string; percent?: number }
  ): Observable<any> {
    const payload: any = { file_id: fileId, processed_file: processedFile, column, date_column: dateColumn, metric };
    if (windows && windows.length) payload.windows = windows;
    if (minBinShareAllowed != null) payload.min_bin_share_allowed = minBinShareAllowed;
    if (split) payload.split = split;
    return this.http.post(`${this.apiUrl}preprocessing/datq_timeseries/`, payload).pipe(
      catchError((error: any) => {
        console.error('Error getting datq timeseries:', error);
        return throwError(() => new Error(error.message || 'Failed to get data quality timeseries'));
      })
    );
  }

  // Start modeling with the processed file path and optional algorithm
  startModeling(fileId: number, processedFile: string, algorithm?: string): Observable<any> {
    const payload: any = { file_id: fileId, processed_file: processedFile };
    if (algorithm) payload.algorithm = algorithm;
    return this.http.post(`${this.apiUrl}modeling/start/`, payload).pipe(
      catchError((error: any) => {
        console.error('Error starting modeling:', error);
        return throwError(() => new Error(error.message || 'Failed to start modeling'));
      })
    );
  }

  // Get modeling status/metrics
  getModelingStatus(fileId: number): Observable<any> {
    return this.http.get(`${this.apiUrl}modeling/status/${fileId}/`).pipe(
      catchError((error: any) => {
        console.error('Error getting modeling status:', error);
        return throwError(() => new Error(error.message || 'Failed to get modeling status'));
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

  private preprocessStackedData(data: any): any {
    return Object.keys(data).reduce((acc: any, key: string) => {
      if (typeof data[key] === 'object' && data[key] !== null) {
        acc[key] = Object.entries(data[key]).reduce((innerAcc: any, [innerKey, innerValue]: [string, any]) => {
          innerAcc[innerKey] = innerValue === null ? 'NaN' : innerValue;
          return innerAcc;
        }, {} as {[key: string]: any});
      } else {
        acc[key] = data[key];
      }
      return acc;
    }, {});
  }

}
