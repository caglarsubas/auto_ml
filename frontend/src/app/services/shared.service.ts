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

  getCurrentFileId(): number | null {
    return this.currentFileIdSubject.getValue();
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

  getModelUsageSettings(): { [variable: string]: string } | null {
    return this.modelUsageSettingsSubject.getValue();
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

  // Trigger data refresh in declaration component (e.g., after AI creates features)
  private dataRefreshSubject = new Subject<void>();
  dataRefresh$: Observable<void> = this.dataRefreshSubject.asObservable();

  triggerDataRefresh(): void {
    this.dataRefreshSubject.next();
  }

  // Broadcast metadata updates applied by AI assistant actions (v2.23.0+).
  //
  // When the AI runs `update_metadata` to change Level_of_Measurement,
  // Feature_Description, or any other dictionary field, the response's
  // `applied` array is fanned out via this subject so every component
  // showing dictionary-derived state — declaration table, encoding plan
  // dropdown in the modeling tab, feature card panel — can patch its
  // local state in place and stay synchronized with the chat assertion.
  //
  // Each update has shape: { column: string, field: string, value: any }
  // where `field` matches the data dictionary key
  // (Feature_Description / Level_of_Measurement / Model_Usage_YN / ...).
  //
  // We deliberately do NOT trigger a backend refetch here: the
  // `GET /declaration/<id>/data_dictionary/` endpoint recomputes the
  // dictionary from the raw file every call and only persists
  // descriptions, so a refetch would silently overwrite the AI's LoM
  // change. In-place patching is the only way to keep the UI in sync
  // until the dictionary persistence layer is broadened.
  private metadataUpdatesSubject = new Subject<Array<{ column: string; field: string; value: any }>>();
  metadataUpdates$: Observable<Array<{ column: string; field: string; value: any }>> =
    this.metadataUpdatesSubject.asObservable();

  emitMetadataUpdates(updates: Array<{ column: string; field: string; value: any }>): void {
    if (!Array.isArray(updates) || updates.length === 0) return;
    this.metadataUpdatesSubject.next(updates);
  }

  // Read-only snapshot accessor for the data dictionary cache; used by
  // ai-chat-panel to patch the cache in-memory after an AI action and
  // re-push it to the AI Redis cache without an extra GET round-trip.
  getDataDictionaryCache(): any[] {
    return this.dataDictionaryCacheSubject.getValue() || [];
  }

  // Broadcast ordinal-ranking updates applied by AI assistant actions
  // (v2.24.0+).
  //
  // When the AI runs `set_ordinal_ranking` to commit the rank order of
  // an ordinal feature's distinct category values, the response's
  // `applied` array — shape Array<{column, ranking: string[]}> — is
  // fanned out via this subject.  The modeling component subscribes
  // and patches `encodingPlan[i].ranking` for matching features so the
  // UI's drag-to-reorder rows render immediately, exactly as if the
  // user had clicked "Set Ranking" and arranged the values manually.
  //
  // Subject (not BehaviorSubject) — late subscribers must NOT replay a
  // stale ranking that's already been applied to the encoding plan.
  // Companion to metadataUpdates$ which handles LoM/description
  // changes from the same `update_metadata` action family.
  private encodingRankingUpdatesSubject =
    new Subject<Array<{ column: string; ranking: string[] }>>();
  encodingRankingUpdates$: Observable<Array<{ column: string; ranking: string[] }>> =
    this.encodingRankingUpdatesSubject.asObservable();

  emitEncodingRankingUpdates(
    updates: Array<{ column: string; ranking: string[] }>,
  ): void {
    if (!Array.isArray(updates) || updates.length === 0) return;
    this.encodingRankingUpdatesSubject.next(updates);
  }

  // Broadcast Selected-Features Keep/Drop changes coming from the AI
  // assistant's `update_config: feature_usage` action (v2.25.0+).
  //
  // The AI's correct path to "exclude Var_3 from SFS due to VIF" is
  // NOT to physically drop the column with execute_code — that
  // invalidates the modeling artifacts.  Instead it emits
  // update_config with key=feature_usage, mirroring the existing
  // manual UI dropdown on each row of the Selected Features table.
  // This subject fans those updates out to the modeling component,
  // which sets `featureUsage[col] = value` and `featureDropReason[col]`
  // in place — the dropdown re-renders to "Drop" with the supplied
  // reason, and the next SFS start picks up the exclusion via the
  // existing `excludedFeatures` collection in startSfs().
  //
  // Subject (not BehaviorSubject) — late subscribers must not replay
  // stale drop flags that have already been applied.
  private featureUsageUpdatesSubject =
    new Subject<Array<{ column: string; value: 'keep' | 'drop'; reason?: string }>>();
  featureUsageUpdates$:
    Observable<Array<{ column: string; value: 'keep' | 'drop'; reason?: string }>> =
    this.featureUsageUpdatesSubject.asObservable();

  emitFeatureUsageUpdates(
    updates: Array<{ column: string; value: 'keep' | 'drop'; reason?: string }>,
  ): void {
    if (!Array.isArray(updates) || updates.length === 0) return;
    this.featureUsageUpdatesSubject.next(updates);
  }

  // Broadcast SFS-start requests coming from the AI assistant's
  // `start_sfs` action (v2.25.0+).
  //
  // The chat panel emits this with the validated SFS config object
  // returned by the backend action handler.  The modeling component
  // subscribes, populates its SFS form fields (sfsMethodForward /
  // sfsMethodBackward / sfsMetrics / sfsMinFeatures / sfsMaxFeatures /
  // sfsNJobs / sfsTopK), and calls its existing `startSfs()` method
  // — exactly the same code path the user's manual "Start SFS"
  // button click takes.  This means the AI gets the same form
  // validation, the same SharedService.activeProcess registration,
  // and the same status-polling lifecycle as a human click.
  //
  // Subject (not BehaviorSubject) — late subscribers must not auto-
  // re-start SFS on a stale request.  The single shape is the same
  // object the backend action handler returns in `applied`.
  private sfsStartRequestsSubject = new Subject<{
    methods: string[];
    stopping_criteria: any;
    excluded_features: string[];
    n_jobs: number;
    top_k: number;
  }>();
  sfsStartRequests$: Observable<{
    methods: string[];
    stopping_criteria: any;
    excluded_features: string[];
    n_jobs: number;
    top_k: number;
  }> = this.sfsStartRequestsSubject.asObservable();

  emitSfsStartRequest(request: {
    methods: string[];
    stopping_criteria: any;
    excluded_features: string[];
    n_jobs: number;
    top_k: number;
  }): void {
    if (!request || typeof request !== 'object') return;
    if (!Array.isArray(request.methods) || request.methods.length === 0) return;
    this.sfsStartRequestsSubject.next(request);
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