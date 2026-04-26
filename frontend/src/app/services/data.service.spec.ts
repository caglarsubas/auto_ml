import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { DataService } from './data.service';
import { environment } from '../../environments/environment';

describe('DataService', () => {
  let service: DataService;
  let httpMock: HttpTestingController;
  const apiUrl = environment.apiBaseUrl;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
    });
    service = TestBed.inject(DataService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  // ── uploadFile ──────────────────────────────────────────────────────
  describe('uploadFile', () => {
    it('should POST FormData to declaration/', () => {
      const file = new File(['a,b\n1,2'], 'test.csv', { type: 'text/csv' });
      service.uploadFile(file).subscribe(res => {
        expect(res.id).toBe(1);
      });
      const req = httpMock.expectOne(`${apiUrl}declaration/`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body instanceof FormData).toBeTrue();
      req.flush({ id: 1 });
    });
  });

  // ── getDataPreview ──────────────────────────────────────────────────
  describe('getDataPreview', () => {
    it('should GET preview', () => {
      service.getDataPreview('5').subscribe(res => {
        expect(res.columns).toEqual(['A', 'B']);
      });
      const req = httpMock.expectOne(`${apiUrl}declaration/5/preview/`);
      expect(req.request.method).toBe('GET');
      req.flush({ columns: ['A', 'B'], rows: [] });
    });
  });

  // ── getDataDictionary ───────────────────────────────────────────────
  describe('getDataDictionary', () => {
    it('should GET data dictionary', () => {
      service.getDataDictionary('3').subscribe(res => {
        expect(res.length).toBe(2);
      });
      const req = httpMock.expectOne(`${apiUrl}declaration/3/data_dictionary/`);
      expect(req.request.method).toBe('GET');
      req.flush([{ Feature_Name: 'A' }, { Feature_Name: 'B' }]);
    });
  });

  // ── getFeatureCard ──────────────────────────────────────────────────
  describe('getFeatureCard', () => {
    it('should GET feature info with column param', () => {
      service.getFeatureCard('1', 'Age').subscribe(res => {
        expect(res.Feature_Name).toBe('Age');
      });
      const req = httpMock.expectOne(`${apiUrl}feature-card/1/get_feature_info/?column=Age`);
      expect(req.request.method).toBe('GET');
      req.flush({ Feature_Name: 'Age', Level_of_Measurement: 'continuous' });
    });

    it('should include file_override when provided', () => {
      service.getFeatureCard('1', 'Age', 'processed/v2.csv').subscribe();
      const req = httpMock.expectOne(
        `${apiUrl}feature-card/1/get_feature_info/?column=Age&file_override=processed%2Fv2.csv`
      );
      expect(req.request.method).toBe('GET');
      req.flush({});
    });
  });

  // ── getStackedFeatureData ───────────────────────────────────────────
  describe('getStackedFeatureData', () => {
    it('should GET stacked data and preprocess it', () => {
      service.getStackedFeatureData('2', 'Region').subscribe(res => {
        expect(res.stacked_data).toBeTruthy();
        expect(res.target_averages).toEqual([]);
      });
      const req = httpMock.expectOne(`${apiUrl}feature-card/2/get_stacked_feature_data/?column=Region`);
      req.flush({ stacked_data: { '0': { A: 10 }, '1': { A: 20 } }, target_averages: [] });
    });

    it('should handle null target_averages', () => {
      service.getStackedFeatureData('2', 'Score').subscribe(res => {
        expect(res.target_averages).toBeNull();
      });
      const req = httpMock.expectOne(`${apiUrl}feature-card/2/get_stacked_feature_data/?column=Score`);
      req.flush({ stacked_data: { '0': [1, 2] }, target_averages: null });
    });
  });

  // ── applyPreprocessing ──────────────────────────────────────────────
  describe('applyPreprocessing', () => {
    it('should POST with file_id and options', () => {
      service.applyPreprocessing(1, [2, 4]).subscribe();
      const req = httpMock.expectOne(`${apiUrl}preprocessing/apply/`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body.file_id).toBe(1);
      expect(req.request.body.options).toEqual([2, 4]);
      req.flush({ status: 'ok' });
    });
  });

  // ── runPreprocessing ────────────────────────────────────────────────
  describe('runPreprocessing', () => {
    it('should POST with file_id only', () => {
      service.runPreprocessing(5).subscribe();
      const req = httpMock.expectOne(`${apiUrl}preprocessing/run/`);
      expect(req.request.body.file_id).toBe(5);
      expect(req.request.body.options).toBeUndefined();
      req.flush({});
    });

    it('should include optional parameters', () => {
      service.runPreprocessing(5, [1, 2], { strategy: 'oot', date_column: 'D' }, ['X'], [{ Feature_Name: 'A' }]).subscribe();
      const req = httpMock.expectOne(`${apiUrl}preprocessing/run/`);
      expect(req.request.body.options).toEqual([1, 2]);
      expect(req.request.body.split.strategy).toBe('oot');
      expect(req.request.body.excluded_variables).toEqual(['X']);
      expect(req.request.body.data_dictionary).toBeTruthy();
      req.flush({});
    });
  });

  // ── getPreprocessingStatus ──────────────────────────────────────────
  describe('getPreprocessingStatus', () => {
    it('should GET status', () => {
      service.getPreprocessingStatus(10).subscribe(res => {
        expect(res.status).toBe('completed');
      });
      const req = httpMock.expectOne(`${apiUrl}preprocessing/status/10/`);
      expect(req.request.method).toBe('GET');
      req.flush({ status: 'completed', result: {} });
    });
  });

  // ── getDatqSummaryRow ───────────────────────────────────────────────
  describe('getDatqSummaryRow', () => {
    it('should GET with column param', () => {
      service.getDatqSummaryRow(7, 'Age').subscribe(res => {
        expect(res.row).toBeTruthy();
      });
      const req = httpMock.expectOne(`${apiUrl}preprocessing/datq_summary_row/7/?column=Age`);
      expect(req.request.method).toBe('GET');
      req.flush({ row: { Variable: 'Age', PSI: 0.05 } });
    });
  });

  // ── getDatqDetail ───────────────────────────────────────────────────
  describe('getDatqDetail', () => {
    it('should POST with required fields', () => {
      service.getDatqDetail(1, 'processed.csv', 'Score').subscribe();
      const req = httpMock.expectOne(`${apiUrl}preprocessing/datq_detail/`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body.file_id).toBe(1);
      expect(req.request.body.processed_file).toBe('processed.csv');
      expect(req.request.body.column).toBe('Score');
      req.flush({});
    });
  });

  // ── getDatqTimeseries ───────────────────────────────────────────────
  describe('getDatqTimeseries', () => {
    it('should POST with all required fields', () => {
      service.getDatqTimeseries(2, 'proc.csv', 'Age', 'Date', 'psi').subscribe();
      const req = httpMock.expectOne(`${apiUrl}preprocessing/datq_timeseries/`);
      expect(req.request.body.file_id).toBe(2);
      expect(req.request.body.column).toBe('Age');
      expect(req.request.body.date_column).toBe('Date');
      expect(req.request.body.metric).toBe('psi');
      req.flush({});
    });

    it('should include optional windows and min_bin_share_allowed', () => {
      service.getDatqTimeseries(2, 'proc.csv', 'Age', 'Date', 'csi', [3, 6], 0.05).subscribe();
      const req = httpMock.expectOne(`${apiUrl}preprocessing/datq_timeseries/`);
      expect(req.request.body.windows).toEqual([3, 6]);
      expect(req.request.body.min_bin_share_allowed).toBe(0.05);
      req.flush({});
    });
  });

  // ── startModeling ───────────────────────────────────────────────────
  describe('startModeling', () => {
    it('should POST with file_id and processed_file', () => {
      service.startModeling(1, 'proc.csv').subscribe();
      const req = httpMock.expectOne(`${apiUrl}modeling/start/`);
      expect(req.request.body.file_id).toBe(1);
      expect(req.request.body.processed_file).toBe('proc.csv');
      req.flush({});
    });

    it('should include optional algorithm and excluded_variables', () => {
      service.startModeling(1, 'p.csv', 'xgboost', ['Bad_Col']).subscribe();
      const req = httpMock.expectOne(`${apiUrl}modeling/start/`);
      expect(req.request.body.algorithm).toBe('xgboost');
      expect(req.request.body.excluded_variables).toEqual(['Bad_Col']);
      req.flush({});
    });
  });

  // ── getModelingStatus ───────────────────────────────────────────────
  describe('getModelingStatus', () => {
    it('should GET status for file', () => {
      service.getModelingStatus(3).subscribe(res => {
        expect(res.status).toBe('completed');
      });
      const req = httpMock.expectOne(`${apiUrl}modeling/status/3/`);
      req.flush({ status: 'completed', roc_auc: 0.85 });
    });
  });

  // ── SFS operations ──────────────────────────────────────────────────
  describe('SFS', () => {
    it('startSfs should POST with parameters', () => {
      service.startSfs(1, ['forward'], { metric: 'roc_auc' }).subscribe();
      const req = httpMock.expectOne(`${apiUrl}modeling/sfs/start/`);
      expect(req.request.body.file_id).toBe(1);
      expect(req.request.body.methods).toEqual(['forward']);
      req.flush({});
    });

    it('getSfsStatus should GET', () => {
      service.getSfsStatus(5).subscribe();
      const req = httpMock.expectOne(`${apiUrl}modeling/sfs/status/5/`);
      expect(req.request.method).toBe('GET');
      req.flush({});
    });

    it('stopSfs should POST to stop endpoint', () => {
      service.stopSfs(5).subscribe();
      const req = httpMock.expectOne(`${apiUrl}modeling/sfs/stop/5/`);
      expect(req.request.method).toBe('POST');
      req.flush({});
    });

    it('getSfsResults should GET results', () => {
      service.getSfsResults(5).subscribe(res => {
        expect(res.forward).toBeTruthy();
      });
      const req = httpMock.expectOne(`${apiUrl}modeling/sfs/5/`);
      req.flush({ forward: [], backward: [] });
    });

    it('resumeSfs should POST with resume flag', () => {
      service.resumeSfs(1, ['backward'], { metric: 'roc_auc' }).subscribe();
      const req = httpMock.expectOne(`${apiUrl}modeling/sfs/start/`);
      expect(req.request.body.resume).toBeTrue();
      req.flush({});
    });

    it('startSfsWithInitialFeatures should include initial_features', () => {
      service.startSfsWithInitialFeatures(1, ['forward'], {}, ['A', 'B']).subscribe();
      const req = httpMock.expectOne(`${apiUrl}modeling/sfs/start/`);
      expect(req.request.body.initial_features).toEqual(['A', 'B']);
      req.flush({});
    });
  });

  // ── Encoding ────────────────────────────────────────────────────────
  describe('Encoding', () => {
    it('analyzeEncoding should POST', () => {
      service.analyzeEncoding(1, 'p.csv', []).subscribe();
      const req = httpMock.expectOne(`${apiUrl}encoding/analyze/`);
      expect(req.request.body.file_id).toBe(1);
      req.flush({ plan: [] });
    });

    it('applyEncoding should POST with plan', () => {
      const plan = [{ feature: 'Region', strategy: 'ohe' }];
      service.applyEncoding(1, 'p.csv', plan, false).subscribe();
      const req = httpMock.expectOne(`${apiUrl}encoding/apply/`);
      expect(req.request.body.plan).toEqual(plan);
      expect(req.request.body.use_native).toBeFalse();
      req.flush({});
    });
  });

  // ── Pipeline CRUD ───────────────────────────────────────────────────
  describe('Pipeline CRUD', () => {
    it('listPipelineRuns should GET list', () => {
      service.listPipelineRuns().subscribe(res => {
        expect(res.length).toBe(2);
      });
      const req = httpMock.expectOne(`${apiUrl}pipeline/`);
      req.flush([{ id: 1 }, { id: 2 }]);
    });

    it('createPipelineRun should POST', () => {
      service.createPipelineRun({ name: 'Test', pipeline_type: 'boosting' }).subscribe(res => {
        expect(res.id).toBe(1);
      });
      const req = httpMock.expectOne(`${apiUrl}pipeline/create/`);
      expect(req.request.method).toBe('POST');
      req.flush({ id: 1 });
    });

    it('getPipelineRun should GET by id', () => {
      service.getPipelineRun(3).subscribe(res => {
        expect(res.name).toBe('MyPipeline');
      });
      const req = httpMock.expectOne(`${apiUrl}pipeline/3/`);
      req.flush({ id: 3, name: 'MyPipeline' });
    });

    it('updatePipelineRun should PUT', () => {
      service.updatePipelineRun(3, { name: 'Updated' }).subscribe();
      const req = httpMock.expectOne(`${apiUrl}pipeline/3/`);
      expect(req.request.method).toBe('PUT');
      req.flush({});
    });

    it('deletePipelineRun should DELETE', () => {
      service.deletePipelineRun(3).subscribe();
      const req = httpMock.expectOne(`${apiUrl}pipeline/3/`);
      expect(req.request.method).toBe('DELETE');
      req.flush({});
    });

    it('getPipelineReportUrl should build correct URL', () => {
      expect(service.getPipelineReportUrl(5)).toBe(`${apiUrl}pipeline/5/report/?output=html`);
      expect(service.getPipelineReportUrl(5, 'print')).toBe(`${apiUrl}pipeline/5/report/?output=print`);
    });

    it('downloadPipelineReport should GET blob', () => {
      service.downloadPipelineReport(5).subscribe(res => {
        expect(res instanceof Blob).toBeTrue();
      });
      const req = httpMock.expectOne(`${apiUrl}pipeline/5/report/?output=html`);
      req.flush(new Blob(['<html></html>']));
    });
  });

  // ── AI endpoints ────────────────────────────────────────────────────
  describe('AI endpoints', () => {
    it('executeAiAction should POST', () => {
      service.executeAiAction(1, 'update_notes', { content: 'test' }).subscribe(res => {
        expect(res.status).toBe('success');
      });
      const req = httpMock.expectOne(`${apiUrl}ai-assistant/execute-action/`);
      expect(req.request.body.file_id).toBe(1);
      expect(req.request.body.action_type).toBe('update_notes');
      req.flush({ status: 'success' });
    });

    it('sendAiChat should POST message with context', () => {
      service.sendAiChat('Hello', { summary: [] }, 'data_quality', []).subscribe(res => {
        expect(res.message).toBeTruthy();
      });
      const req = httpMock.expectOne(`${apiUrl}ai-assistant/chat/`);
      expect(req.request.body.message).toBe('Hello');
      expect(req.request.body.section).toBe('data_quality');
      req.flush({ message: 'Response' });
    });

    it('sendAiChat should include file_id when provided', () => {
      service.sendAiChat('Hello', {}, 'general', [], 42).subscribe();
      const req = httpMock.expectOne(`${apiUrl}ai-assistant/chat/`);
      expect(req.request.body.file_id).toBe(42);
      req.flush({ message: 'Response' });
    });

    it('pushAiCache should POST artifacts with file_id', () => {
      service.pushAiCache(1, { split_validation: { splits: [] } }).subscribe(res => {
        expect(res.status).toBe('success');
      });
      const req = httpMock.expectOne(`${apiUrl}ai-assistant/cache/`);
      expect(req.request.body.file_id).toBe(1);
      expect(req.request.body.artifacts.split_validation).toBeDefined();
      req.flush({ status: 'success', cached: ['split_validation'] });
    });
  });

  // ── VIF detail ──────────────────────────────────────────────────────
  describe('getVifDetail', () => {
    it('should POST with file_id and feature', () => {
      service.getVifDetail(1, 'Income').subscribe();
      const req = httpMock.expectOne(`${apiUrl}modeling/vif-detail/`);
      expect(req.request.body.file_id).toBe(1);
      expect(req.request.body.feature).toBe('Income');
      req.flush({ vif: 2.5, correlations: [] });
    });
  });

  // ── Error handling ──────────────────────────────────────────────────
  describe('error handling', () => {
    it('getDataPreview should propagate HTTP errors', (done) => {
      service.getDataPreview('999').subscribe({
        error: (err) => {
          expect(err).toBeTruthy();
          done();
        }
      });
      const req = httpMock.expectOne(`${apiUrl}declaration/999/preview/`);
      req.flush('Not Found', { status: 404, statusText: 'Not Found' });
    });

    it('applyPreprocessing should propagate errors', (done) => {
      service.applyPreprocessing(1, []).subscribe({
        error: (err) => {
          expect(err).toBeTruthy();
          done();
        }
      });
      const req = httpMock.expectOne(`${apiUrl}preprocessing/apply/`);
      req.flush('Error', { status: 500, statusText: 'Server Error' });
    });
  });

  // ── getFeatureExplainability ────────────────────────────────────────
  describe('getFeatureExplainability', () => {
    it('should POST with required and optional params', () => {
      service.getFeatureExplainability(1, 'Income', 'proc.csv', 100, 'model.pkl', ['A', 'B']).subscribe();
      const req = httpMock.expectOne(`${apiUrl}modeling/feature-explainability/`);
      expect(req.request.body.file_id).toBe(1);
      expect(req.request.body.feature_name).toBe('Income');
      expect(req.request.body.processed_file).toBe('proc.csv');
      expect(req.request.body.n_samples).toBe(100);
      expect(req.request.body.model_path).toBe('model.pkl');
      expect(req.request.body.selected_features).toEqual(['A', 'B']);
      req.flush({});
    });
  });
});
