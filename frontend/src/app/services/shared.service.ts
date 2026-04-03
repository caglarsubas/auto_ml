import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable, Subject } from 'rxjs';

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

  // Store Model_Usage settings from Data Dictionary to carry forward to Data Quality
  private modelUsageSettingsSubject = new BehaviorSubject<{ [variable: string]: string } | null>(null);
  modelUsageSettings$: Observable<{ [variable: string]: string } | null> = this.modelUsageSettingsSubject.asObservable();

  setStarted(value: boolean): void {
    this.isStartedSubject.next(value);
  }

  setSelectedPipeline(pipeline: string): void {
    this.selectedPipelineSubject.next(pipeline);
  }

  getSelectedPipeline(): string {
    return this.selectedPipelineSubject.getValue();
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

  setModelUsageSettings(settings: { [variable: string]: string } | null): void {
    this.modelUsageSettingsSubject.next(settings);
  }

  // Store encoded file path (produced by encoding step)
  private encodedFilePathSubject = new BehaviorSubject<string | null>(null);
  encodedFilePath$: Observable<string | null> = this.encodedFilePathSubject.asObservable();

  setEncodedFilePath(path: string | null): void {
    this.encodedFilePathSubject.next(path);
  }

  // Store encoding report (mapping info for categorical features)
  private encodingReportSubject = new BehaviorSubject<any[]>([]);
  encodingReport$: Observable<any[]> = this.encodingReportSubject.asObservable();

  setEncodingReport(report: any[]): void {
    this.encodingReportSubject.next(report);
  }

  // Store data dictionary cache for encoding analysis in modeling step
  private dataDictionaryCacheSubject = new BehaviorSubject<any[]>([]);
  dataDictionaryCache$: Observable<any[]> = this.dataDictionaryCacheSubject.asObservable();

  setDataDictionaryCache(cache: any[]): void {
    this.dataDictionaryCacheSubject.next(cache);
  }

  // Modeling inner checkpoint state (algorithm, encoding, modeling results, SFS)
  private modelingCheckpointSubject = new BehaviorSubject<any | null>(null);
  modelingCheckpoint$: Observable<any | null> = this.modelingCheckpointSubject.asObservable();

  setModelingCheckpoint(state: any | null): void {
    this.modelingCheckpointSubject.next(state);
  }

  getModelingCheckpoint(): any | null {
    return this.modelingCheckpointSubject.getValue();
  }

  // Trigger checkpoint save event (modeling child → model-development parent)
  private triggerCheckpointSubject = new Subject<string>();
  triggerCheckpoint$: Observable<string> = this.triggerCheckpointSubject.asObservable();

  triggerCheckpoint(substep: string): void {
    this.triggerCheckpointSubject.next(substep);
  }

  // Autosave flag shared between parent (model-development) and child (modeling) components
  private autosaveEnabledSubject = new BehaviorSubject<boolean>(true);
  autosaveEnabled$: Observable<boolean> = this.autosaveEnabledSubject.asObservable();

  setAutosaveEnabled(enabled: boolean): void {
    this.autosaveEnabledSubject.next(enabled);
  }

  getAutosaveEnabled(): boolean {
    return this.autosaveEnabledSubject.getValue();
  }

  // Pipeline commentary notes (Jupyter-notebook style, keyed by position)
  private pipelineNotesSubject = new BehaviorSubject<{ [position: string]: string }>({});
  pipelineNotes$: Observable<{ [position: string]: string }> = this.pipelineNotesSubject.asObservable();

  setPipelineNotes(notes: { [position: string]: string }): void {
    this.pipelineNotesSubject.next(notes);
  }

  getPipelineNotes(): { [position: string]: string } {
    return this.pipelineNotesSubject.getValue();
  }

  updatePipelineNote(position: string, content: string): void {
    const notes = { ...this.pipelineNotesSubject.getValue() };
    if (content.trim()) {
      notes[position] = content;
    } else {
      delete notes[position];
    }
    this.pipelineNotesSubject.next(notes);
  }

  // Cumulative AI context: always-fresh snapshot of ALL pipeline data accumulated so far
  private aiCumulativeContextSubject = new BehaviorSubject<any>({});
  aiCumulativeContext$: Observable<any> = this.aiCumulativeContextSubject.asObservable();

  setAiCumulativeContext(ctx: any): void {
    this.aiCumulativeContextSubject.next(ctx);
  }

  getAiCumulativeContext(): any {
    return this.aiCumulativeContextSubject.getValue();
  }

  // Target definition: user-provided description of the target variable's business meaning
  private targetDefinitionSubject = new BehaviorSubject<string>('');
  targetDefinition$: Observable<string> = this.targetDefinitionSubject.asObservable();

  setTargetDefinition(definition: string): void {
    this.targetDefinitionSubject.next(definition);
  }

  getTargetDefinition(): string {
    return this.targetDefinitionSubject.getValue();
  }

  // Active process tracking for pipeline resume (preprocessing/modeling/sfs)
  private activeProcessSubject = new BehaviorSubject<{ type: string; file_id: number } | null>(null);
  activeProcess$: Observable<{ type: string; file_id: number } | null> = this.activeProcessSubject.asObservable();

  setActiveProcess(process: { type: string; file_id: number } | null): void {
    this.activeProcessSubject.next(process);
  }

  getActiveProcess(): { type: string; file_id: number } | null {
    return this.activeProcessSubject.getValue();
  }
}