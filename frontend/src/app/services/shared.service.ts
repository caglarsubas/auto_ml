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

  setStarted(value: boolean): void {
    this.isStartedSubject.next(value);
  }

  setSelectedPipeline(pipeline: string): void {
    this.selectedPipelineSubject.next(pipeline);
  }

  setPreprocessingInitiated(value: boolean): void {
    this.preprocessingInitiatedSubject.next(value);
  }
  
}