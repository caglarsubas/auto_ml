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

  getFeatureCard(fileId: string, columnName: string, fileOverride?: string): Observable<any> {
    let url = `${this.apiUrl}feature-card/${fileId}/get_feature_info/?column=${encodeURIComponent(columnName)}`;
    if (fileOverride) url += `&file_override=${encodeURIComponent(fileOverride)}`;
    return this.http.get(url);
  }

  getStackedFeatureData(fileId: string, columnName: string, fileOverride?: string): Observable<any> {
    let url = `${this.apiUrl}feature-card/${fileId}/get_stacked_feature_data/?column=${encodeURIComponent(columnName)}`;
    if (fileOverride) url += `&file_override=${encodeURIComponent(fileOverride)}`;
    console.log('Requesting URL:', url);
    return this.http.get(url).pipe(
      tap((data: any) => console.log('Raw response:', data)),
      map((data: any) => {
        // Backend now returns { stacked_data, target_averages }
        const raw = data?.stacked_data ?? data;
        return { stacked_data: this.preprocessStackedData(raw), target_averages: data?.target_averages ?? null };
      }),
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
  // Optional excluded_variables: list of variables to exclude (Model_Usage='No')
  runPreprocessing(fileId: number, options?: number[], split?: { strategy?: string; date_column?: string; cutoff?: string; percent?: number }, excludedVariables?: string[], dataDictionary?: any[]): Observable<any> {
    const payload: any = { file_id: fileId };
    if (options) payload.options = options;
    if (split) payload.split = split;
    if (excludedVariables && excludedVariables.length > 0) payload.excluded_variables = excludedVariables;
    if (dataDictionary && dataDictionary.length > 0) payload.data_dictionary = dataDictionary;
    return this.http.post(`${this.apiUrl}preprocessing/run/`, payload).pipe(
      catchError((error: any) => {
        console.error('Error running preprocessing:', error);
        return throwError(() => new Error(error.message || 'Failed to run preprocessing'));
      })
    );
  }

  // Check preprocessing completion status for a file (used for pipeline resume)
  getPreprocessingStatus(fileId: number): Observable<any> {
    return this.http.get(`${this.apiUrl}preprocessing/status/${fileId}/`).pipe(
      catchError((error: any) => {
        console.error('Error getting preprocessing status:', error);
        return throwError(() => new Error(error.message || 'Failed to get preprocessing status'));
      })
    );
  }

  // Get quality summary row for a specific variable from saved datq_summary JSON
  getDatqSummaryRow(fileId: number, column: string): Observable<any> {
    return this.http.get(`${this.apiUrl}preprocessing/datq_summary_row/${fileId}/`, { params: { column } }).pipe(
      catchError((error: any) => {
        console.error('Error getting datq summary row:', error);
        return throwError(() => new Error(error.message || 'Failed to get quality summary'));
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
    metric: 'psi' | 'csi' | 'ks' | 'jsd' | 'wd' = 'psi',
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
  // Optional excluded_variables: list of variables to exclude (Model_Usage='No')
  startModeling(fileId: number, processedFile: string, algorithm?: string, excludedVariables?: string[], encodingPlan?: any[], encodingUseNative?: boolean): Observable<any> {
    const payload: any = { file_id: fileId, processed_file: processedFile };
    if (algorithm) payload.algorithm = algorithm;
    if (excludedVariables && excludedVariables.length > 0) payload.excluded_variables = excludedVariables;
    if (encodingPlan && encodingPlan.length > 0) payload.encoding_plan = encodingPlan;
    if (encodingUseNative !== undefined) payload.encoding_use_native = encodingUseNative;
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

  // Start Sequential Feature Selection (SFS) with user parameters
  startSfs(
    fileId: number,
    methods: string[],
    stoppingCriteria: any,
    excludedFeatures: string[] = [],
    nJobs: number = 1,
    topK: number = 3,
    algorithm?: string,
    opts?: {
      initialFeatures?: string[];
      useCombinedScoreOrder?: boolean;
      candidateTopK?: number | null;
    },
  ): Observable<any> {
    const payload: any = {
      file_id: fileId,
      methods: methods,
      stopping_criteria: stoppingCriteria,
      n_jobs: nJobs,
      top_k: topK
    };
    if (excludedFeatures.length > 0) {
      payload.excluded_features = excludedFeatures;
    }
    if (algorithm) payload.algorithm = algorithm;
    if (opts?.initialFeatures?.length) {
      payload.initial_features = opts.initialFeatures;
    }
    if (opts?.useCombinedScoreOrder) {
      payload.use_combined_score_order = true;
      if (opts.candidateTopK != null && opts.candidateTopK > 0) {
        payload.candidate_top_k = opts.candidateTopK;
      }
    }
    return this.http.post(`${this.apiUrl}modeling/sfs/start/`, payload).pipe(
      catchError((error: any) => {
        console.error('Error starting SFS:', error);
        return throwError(() => new Error(error.message || 'Failed to start SFS'));
      })
    );
  }

  // Start SFS with initial features (for chained backward→forward SFS)
  startSfsWithInitialFeatures(fileId: number, methods: string[], stoppingCriteria: any, initialFeatures: string[], nJobs: number = 1, topK: number = 3, algorithm?: string): Observable<any> {
    const payload: any = {
      file_id: fileId,
      methods: methods,
      stopping_criteria: stoppingCriteria,
      initial_features: initialFeatures,
      n_jobs: nJobs,
      top_k: topK
    };
    if (algorithm) payload.algorithm = algorithm;
    return this.http.post(`${this.apiUrl}modeling/sfs/start/`, payload).pipe(
      catchError((error: any) => {
        console.error('Error starting SFS with initial features:', error);
        return throwError(() => new Error(error.message || 'Failed to start SFS'));
      })
    );
  }

  // Get SFS progress/status
  getSfsStatus(fileId: number): Observable<any> {
    return this.http.get(`${this.apiUrl}modeling/sfs/status/${fileId}/`).pipe(
      catchError((error: any) => {
        console.error('Error getting SFS status:', error);
        return throwError(() => new Error(error.message || 'Failed to get SFS status'));
      })
    );
  }

  // Stop SFS gracefully
  stopSfs(fileId: number): Observable<any> {
    return this.http.post(`${this.apiUrl}modeling/sfs/stop/${fileId}/`, {}).pipe(
      catchError((error: any) => {
        console.error('Error stopping SFS:', error);
        return throwError(() => new Error(error.message || 'Failed to stop SFS'));
      })
    );
  }

  // Resume SFS from where it was stopped
  resumeSfs(fileId: number, methods: string[], stoppingCriteria: any, excludedFeatures: string[] = [], nJobs: number = 1, topK: number = 3, algorithm?: string): Observable<any> {
    const payload: any = {
      file_id: fileId,
      methods: methods,
      stopping_criteria: stoppingCriteria,
      n_jobs: nJobs,
      top_k: topK,
      resume: true
    };
    if (excludedFeatures.length > 0) {
      payload.excluded_features = excludedFeatures;
    }
    if (algorithm) payload.algorithm = algorithm;
    return this.http.post(`${this.apiUrl}modeling/sfs/start/`, payload).pipe(
      catchError((error: any) => {
        console.error('Error resuming SFS:', error);
        return throwError(() => new Error(error.message || 'Failed to resume SFS'));
      })
    );
  }

  // Get Sequential Feature Selection (SFS) results
  getSfsResults(fileId: number): Observable<any> {
    return this.http.get(`${this.apiUrl}modeling/sfs/${fileId}/`).pipe(
      catchError((error: any) => {
        console.error('Error getting SFS results:', error);
        return throwError(() => new Error(error.message || 'Failed to get SFS results'));
      })
    );
  }

  // ===== Hyperparameter Tuning (random joint search + validation curves) =====
  // Mirrors the SFS service methods: start a background tuning run, poll its
  // status, stop it gracefully, and fetch persisted results.

  // Start hyperparameter tuning with an editable param space + compute config.
  startHyperparam(fileId: number, options: {
    paramSpace?: any;
    fixedParams?: any;
    features?: string[];
    nIter?: number;
    cvFolds?: number;
    nJobs?: number;
    primaryMetric?: string;
    threshold?: number;
    validationCurvePoints?: number;
    searchMethod?: string;
    gridPointsPerParam?: number;
    gridPointsPerParamMap?: { [param: string]: number };
    algorithm?: string;
  } = {}): Observable<any> {
    const payload: any = { file_id: fileId };
    if (options.paramSpace) payload.param_space = options.paramSpace;
    if (options.fixedParams) payload.fixed_params = options.fixedParams;
    if (options.features && options.features.length) payload.features = options.features;
    if (typeof options.nIter === 'number') payload.n_iter = options.nIter;
    if (typeof options.cvFolds === 'number') payload.cv_folds = options.cvFolds;
    if (typeof options.nJobs === 'number') payload.n_jobs = options.nJobs;
    if (options.primaryMetric) payload.primary_metric = options.primaryMetric;
    if (typeof options.threshold === 'number') payload.threshold = options.threshold;
    if (typeof options.validationCurvePoints === 'number') payload.validation_curve_points = options.validationCurvePoints;
    if (options.searchMethod) payload.search_method = options.searchMethod;
    if (typeof options.gridPointsPerParam === 'number') payload.grid_points_per_param = options.gridPointsPerParam;
    if (options.gridPointsPerParamMap) payload.grid_points_per_param_map = options.gridPointsPerParamMap;
    if (options.algorithm) payload.algorithm = options.algorithm;
    return this.http.post(`${this.apiUrl}modeling/hyperparam/start/`, payload).pipe(
      catchError((error: any) => {
        console.error('Error starting hyperparameter tuning:', error);
        return throwError(() => error);
      })
    );
  }

  // Get hyperparameter-tuning progress/status.
  getHyperparamStatus(fileId: number): Observable<any> {
    return this.http.get(`${this.apiUrl}modeling/hyperparam/status/${fileId}/`).pipe(
      catchError((error: any) => {
        console.error('Error getting hyperparameter status:', error);
        return throwError(() => new Error(error.message || 'Failed to get hyperparameter status'));
      })
    );
  }

  // Request a graceful stop of an in-flight tuning run.
  stopHyperparam(fileId: number): Observable<any> {
    return this.http.post(`${this.apiUrl}modeling/hyperparam/stop/${fileId}/`, {}).pipe(
      catchError((error: any) => {
        console.error('Error stopping hyperparameter tuning:', error);
        return throwError(() => new Error(error.message || 'Failed to stop hyperparameter tuning'));
      })
    );
  }

  // Get persisted hyperparameter-tuning results.
  getHyperparamResults(fileId: number): Observable<any> {
    return this.http.get(`${this.apiUrl}modeling/hyperparam/${fileId}/`).pipe(
      catchError((error: any) => {
        console.error('Error getting hyperparameter results:', error);
        return throwError(() => new Error(error.message || 'Failed to get hyperparameter results'));
      })
    );
  }

  // Get feature explainability data (SHAP beeswarm + partial dependence)
  getFeatureExplainability(fileId: number, featureName: string, processedFile?: string, nSamples?: number, modelPath?: string, selectedFeatures?: string[]): Observable<any> {
    const payload: any = { file_id: fileId, feature_name: featureName };
    if (processedFile) payload.processed_file = processedFile;
    if (nSamples) payload.n_samples = nSamples;
    if (modelPath) payload.model_path = modelPath;
    if (selectedFeatures && selectedFeatures.length) payload.selected_features = selectedFeatures;
    return this.http.post(`${this.apiUrl}modeling/feature-explainability/`, payload).pipe(
      catchError((error: any) => {
        console.error('Error getting feature explainability:', error);
        // Preserve the full error structure so components can access error.error.reason, etc.
        return throwError(() => error);
      })
    );
  }
  
  // Analyze categorical features and return encoding plan
  analyzeEncoding(fileId: number, processedFile: string, dataDictionary: any[], excludedVariables?: string[]): Observable<any> {
    const payload: any = { file_id: fileId, processed_file: processedFile, data_dictionary: dataDictionary };
    if (excludedVariables && excludedVariables.length > 0) payload.excluded_variables = excludedVariables;
    return this.http.post(`${this.apiUrl}encoding/analyze/`, payload).pipe(
      catchError((error: any) => {
        console.error('Error analyzing encoding:', error);
        return throwError(() => new Error(error.message || 'Failed to analyze encoding'));
      })
    );
  }

  // Apply encoding based on user-adjusted plan
  applyEncoding(fileId: number, processedFile: string, plan: any[], useNative: boolean = true): Observable<any> {
    const payload = { file_id: fileId, processed_file: processedFile, plan, use_native: useNative };
    return this.http.post(`${this.apiUrl}encoding/apply/`, payload).pipe(
      catchError((error: any) => {
        console.error('Error applying encoding:', error);
        return throwError(() => new Error(error.message || 'Failed to apply encoding'));
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

  // Get VIF decomposition detail for a specific feature
  getVifDetail(fileId: number, feature: string): Observable<any> {
    return this.http.post(`${this.apiUrl}modeling/vif-detail/`, { file_id: fileId, feature }).pipe(
      catchError((error: any) => {
        console.error('Error getting VIF detail:', error);
        return throwError(() => error);
      })
    );
  }

  // ===== Pipeline Run CRUD =====

  listPipelineRuns(): Observable<any[]> {
    return this.http.get<any[]>(`${this.apiUrl}pipeline/`).pipe(
      catchError((err: any) => {
        console.error('Error listing pipeline runs:', err);
        return throwError(() => err);
      })
    );
  }

  createPipelineRun(payload: any): Observable<any> {
    return this.http.post(`${this.apiUrl}pipeline/create/`, payload).pipe(
      catchError((err: any) => {
        console.error('Error creating pipeline run:', err);
        return throwError(() => err);
      })
    );
  }

  getPipelineRun(id: number): Observable<any> {
    return this.http.get(`${this.apiUrl}pipeline/${id}/`).pipe(
      catchError((err: any) => {
        console.error('Error getting pipeline run:', err);
        return throwError(() => err);
      })
    );
  }

  updatePipelineRun(id: number, payload: any): Observable<any> {
    return this.http.put(`${this.apiUrl}pipeline/${id}/`, payload).pipe(
      catchError((err: any) => {
        console.error('Error updating pipeline run:', err);
        return throwError(() => err);
      })
    );
  }

  deletePipelineRun(id: number): Observable<any> {
    return this.http.delete(`${this.apiUrl}pipeline/${id}/`).pipe(
      catchError((err: any) => {
        console.error('Error deleting pipeline run:', err);
        return throwError(() => err);
      })
    );
  }

  getPipelineReportUrl(id: number, output: 'html' | 'print' = 'html'): string {
    return `${this.apiUrl}pipeline/${id}/report/?output=${output}`;
  }

  downloadPipelineReport(id: number): Observable<Blob> {
    return this.http.get(`${this.apiUrl}pipeline/${id}/report/?output=html`, { responseType: 'blob' }).pipe(
      catchError((err: any) => {
        console.error('Error downloading pipeline report:', err);
        return throwError(() => err);
      })
    );
  }

  // ===== AI Action Execution (general-purpose) =====

  executeAiAction(fileId: number, actionType: string, payload: any,
                  parentSpanId?: string,
                  source?: 'codeline' | 'panel'): Observable<any> {
    const body: any = {
      file_id: fileId,
      action_type: actionType,
      payload,
    };
    // v2.38.0+: cross-trace link.  Only set when caller has a span id;
    // backend treats missing/empty as "no link" (legacy semantics).
    if (parentSpanId) {
      body.parent_span_id = parentSpanId;
    }
    if (source) {
      body.source = source;
    }
    return this.http.post(`${this.apiUrl}ai-assistant/execute-action/`, body).pipe(
      catchError((err: any) => {
        console.error('Error executing AI action:', err);
        return throwError(() => err);
      })
    );
  }

  // ===== AI Assistant =====

  sendAiChat(message: string, context: any, section: string,
             history: Array<{role: string; content: string}>,
             fileId?: number, model?: string,
             intentLabels?: Array<'A' | 'B' | 'C' | 'D' | 'E' | 'R'>,
             intentSource?: string,
             source?: 'codeline' | 'panel'): Observable<any> {
    const body: any = { message, context, section, history };
    if (fileId != null) {
      body.file_id = fileId;
    }
    if (model) {
      body.model = model;
    }
    if (intentLabels && intentLabels.length > 0) {
      body.intent_labels = intentLabels;
    }
    if (intentSource) {
      body.intent_source = intentSource;
    }
    if (source) {
      body.source = source;
    }
    return this.http.post(`${this.apiUrl}ai-assistant/chat/`, body).pipe(
      catchError((err: any) => {
        console.error('Error in AI assistant chat:', err);
        return throwError(() => err);
      })
    );
  }

  submitAiFeedback(payload: {
    liked?: boolean;
    rating?: number;
    comment?: string;
    source?: string;
    feedback_id?: string;
    target_trace_id?: string;
    target_span_id?: string;
    target_session_id?: string;
    conversation_id?: string;
    submitted_at?: string;
    file_id?: number;
  }): Observable<any> {
    return this.http.post(`${this.apiUrl}ai-assistant/feedback/`, payload).pipe(
      catchError((err: any) => {
        console.error('Error submitting AI feedback:', err);
        return throwError(() => err);
      })
    );
  }

  getAiModels(): Observable<any> {
    return this.http.get(`${this.apiUrl}ai-assistant/models/`).pipe(
      catchError((err: any) => {
        console.error('Error fetching AI models:', err);
        return throwError(() => err);
      })
    );
  }

  pushAiCache(fileId: number, artifacts: { [key: string]: any }): Observable<any> {
    return this.http.post(`${this.apiUrl}ai-assistant/cache/`, {
      file_id: fileId,
      artifacts,
    }).pipe(
      catchError((err: any) => {
        console.error('Error pushing AI cache:', err);
        return throwError(() => err);
      })
    );
  }

  runEvaluation(fileId: number, threshold: number = 0.5, features?: string[]): Observable<any> {
    const payload: any = { file_id: fileId, threshold };
    if (features && features.length) payload.features = features;
    return this.http.post(`${this.apiUrl}evaluation/run/`, payload).pipe(
      catchError((error: any) => {
        console.error('Error running evaluation:', error);
        return throwError(() => new Error(error?.error?.error || error.message || 'Failed to run evaluation'));
      })
    );
  }

  getEvaluationStatus(fileId: number): Observable<any> {
    return this.http.get(`${this.apiUrl}evaluation/status/${fileId}/`).pipe(
      catchError((error: any) => {
        console.error('Error getting evaluation status:', error);
        return throwError(() => new Error(error.message || 'Failed to get evaluation status'));
      })
    );
  }

  getDeployReadiness(fileId: number): Observable<any> {
    return this.http.get(`${this.apiUrl}deployment/bundle/`, { params: { file_id: String(fileId) } }).pipe(
      catchError((error: any) => {
        console.error('Error getting deploy readiness:', error);
        return throwError(() => new Error(error?.error?.error || error.message || 'Failed to get deploy readiness'));
      })
    );
  }

  createDeploymentBundle(fileId: number): Observable<any> {
    return this.http.post(`${this.apiUrl}deployment/bundle/`, { file_id: fileId }).pipe(
      catchError((error: any) => {
        console.error('Error creating deployment bundle:', error);
        // Preserve structured 409 readiness payload for the deployment UI.
        return throwError(() => error);
      })
    );
  }

  getDeploymentStatus(fileId: number): Observable<any> {
    return this.http.get(`${this.apiUrl}deployment/status/${fileId}/`).pipe(
      catchError((error: any) => {
        console.error('Error getting deployment status:', error);
        return throwError(() => new Error(error.message || 'Failed to get deployment status'));
      })
    );
  }

  scoreDeployment(fileId: number, file: File): Observable<any> {
    const form = new FormData();
    form.append('file_id', String(fileId));
    form.append('file', file);
    return this.http.post(`${this.apiUrl}deployment/score/`, form).pipe(
      catchError((error: any) => {
        console.error('Error scoring deployment batch:', error);
        return throwError(() => new Error(error?.error?.error || error.message || 'Failed to score batch'));
      })
    );
  }

  // ===== CRISP-DM cycle APIs =====

  downloadCrispExportPack(fileId: number, pipelineRunId?: number, bu?: any): Observable<Blob> {
    const payload: any = { file_id: fileId };
    if (pipelineRunId != null) payload.pipeline_run_id = pipelineRunId;
    if (bu) payload.business_understanding = bu;
    return this.http.post(`${this.apiUrl}crisp/export/`, payload, { responseType: 'blob' }).pipe(
      catchError((err: any) => {
        console.error('Error downloading CRISP export pack:', err);
        return throwError(() => err);
      })
    );
  }

  runMonitoring(fileId: number, file: File, scoreCol?: string, targetCol?: string): Observable<any> {
    const form = new FormData();
    form.append('file_id', String(fileId));
    form.append('file', file, file.name);
    if (scoreCol) form.append('score_col', scoreCol);
    if (targetCol) form.append('target_col', targetCol);
    return this.http.post(`${this.apiUrl}crisp/monitoring/`, form).pipe(
      catchError((err: any) => {
        console.error('Error running monitoring:', err);
        return throwError(() => new Error(err?.error?.error || err.message || 'Failed to run monitoring'));
      })
    );
  }

  clonePipelineIteration(pipelineRunId: number): Observable<any> {
    return this.http.post(`${this.apiUrl}crisp/iteration/clone/`, { pipeline_run_id: pipelineRunId }).pipe(
      catchError((err: any) => {
        console.error('Error cloning pipeline iteration:', err);
        return throwError(() => err);
      })
    );
  }

  getSequentialPatterns(fileId: number, timeCol?: string): Observable<any> {
    const params: any = {};
    if (timeCol) params.time_col = timeCol;
    return this.http.get(`${this.apiUrl}crisp/sequential/${fileId}/`, { params }).pipe(
      catchError((err: any) => {
        console.error('Error fetching sequential patterns:', err);
        return throwError(() => err);
      })
    );
  }

  getDatqEnriched(fileId: number): Observable<any> {
    return this.http.get(`${this.apiUrl}crisp/datq/${fileId}/`).pipe(
      catchError((err: any) => {
        console.error('Error fetching enriched DATQ:', err);
        return throwError(() => err);
      })
    );
  }

  downloadEvalPack(fileId: number): Observable<Blob> {
    return this.http.post(`${this.apiUrl}evaluation/pack/`, { file_id: fileId }, { responseType: 'blob' }).pipe(
      catchError((err: any) => {
        console.error('Error downloading evaluation pack:', err);
        return throwError(() => err);
      })
    );
  }

  downloadDeploymentPack(fileId: number): Observable<any> {
    return this.http.post(`${this.apiUrl}deployment/pack/`, { file_id: fileId }).pipe(
      catchError((err: any) => {
        console.error('Error downloading deployment pack:', err);
        return throwError(() => err);
      })
    );
  }

  promoteChampion(fileId: number, payload: any): Observable<any> {
    return this.http.post(`${this.apiUrl}modeling/champion/`, { file_id: fileId, ...payload }).pipe(
      catchError((err: any) => {
        console.error('Error promoting champion:', err);
        return throwError(() => err);
      })
    );
  }

  getSfsHistory(fileId: number): Observable<any> {
    return this.http.get(`${this.apiUrl}modeling/sfs/${fileId}/history/`).pipe(
      catchError((err: any) => {
        console.error('Error fetching SFS history:', err);
        return throwError(() => err);
      })
    );
  }

  saveGovernanceChecks(fileId: number, checks: { [key: string]: boolean }): Observable<any> {
    return this.http.post(`${this.apiUrl}evaluation/governance/`, { file_id: fileId, checks }).pipe(
      catchError((err: any) => {
        console.error('Error saving governance checks:', err);
        return throwError(() => err);
      })
    );
  }

  applyRecommendationConfirm(fileId: number, payload: any): Observable<any> {
    return this.executeAiAction(fileId, 'apply_recommendation', payload);
  }

  compareModels(fileId: number): Observable<any> {
    return this.http.get(`${this.apiUrl}modeling/compare/${fileId}/`).pipe(
      catchError((err: any) => {
        console.error('Error comparing models:', err);
        return throwError(() => err);
      })
    );
  }

}
