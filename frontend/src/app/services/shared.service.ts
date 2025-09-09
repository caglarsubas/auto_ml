import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class SharedService {
  private isStartedSubject = new BehaviorSubject<boolean>(false);
  isStarted$: Observable<boolean> = this.isStartedSubject.asObservable();

  private selectedPipelineSubject = new BehaviorSubject<string>('');
  selectedPipeline$: Observable<string> = this.selectedPipelineSubject.asObservable();

  private preprocessingInitiatedSubject = new BehaviorSubject<boolean>(false);
  preprocessingInitiated$: Observable<boolean> = this.preprocessingInitiatedSubject.asObservable();

  // Store selected purifier option IDs (from preprocessing step)
  private selectedPurifierOptionsSubject = new BehaviorSubject<number[]>([]);
  selectedPurifierOptions$: Observable<number[]> = this.selectedPurifierOptionsSubject.asObservable();

  // Track currently uploaded/selected file id from Declaration step
  private currentFileIdSubject = new BehaviorSubject<number | null>(null);
  currentFileId$: Observable<number | null> = this.currentFileIdSubject.asObservable();

  // Store preprocessing run result (preview JSON from backend)
  private preprocessingRunResultSubject = new BehaviorSubject<any | null>(null);
  preprocessingRunResult$: Observable<any | null> = this.preprocessingRunResultSubject.asObservable();

  // Store processed file relative path to use in modeling step
  private processedFilePathSubject = new BehaviorSubject<string | null>(null);
  processedFilePath$: Observable<string | null> = this.processedFilePathSubject.asObservable();

  setStarted(value: boolean): void {
    this.isStartedSubject.next(value);
  }

  setSelectedPipeline(pipeline: string): void {
    this.selectedPipelineSubject.next(pipeline);
  }

  setPreprocessingInitiated(value: boolean): void {
    this.preprocessingInitiatedSubject.next(value);
  }
  
  setSelectedPurifierOptions(optionIds: number[]): void {
    this.selectedPurifierOptionsSubject.next(optionIds);
  }
  
  setCurrentFileId(id: number | null): void {
    this.currentFileIdSubject.next(id);
  }
  
  setPreprocessingRunResult(result: any | null): void {
    this.preprocessingRunResultSubject.next(result);
  }

  setProcessedFilePath(path: string | null): void {
    this.processedFilePathSubject.next(path);
  }
  
}