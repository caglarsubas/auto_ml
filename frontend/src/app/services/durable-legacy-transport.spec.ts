import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { DataService } from './data.service';
import { AuthService } from './auth.service';
import { LegacyExecutionReviewService } from './legacy-execution-review.service';
import { environment } from '../../environments/environment';

describe('Durable legacy launch transport', () => {
  let data: DataService;
  let http: HttpTestingController;
  let review: LegacyExecutionReviewService;
  let auth: AuthService;
  const base = environment.apiBaseUrl;
  const jobId = '11111111-1111-4111-8111-111111111111';
  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [HttpClientTestingModule] });
    data = TestBed.inject(DataService);
    auth = TestBed.inject(AuthService);
    auth.user = { id: 1, username: 'developer' };
    http = TestBed.inject(HttpTestingController);
    review = TestBed.inject(LegacyExecutionReviewService);
  });
  afterEach(() => http.verify());

  function proposal(): void {
    http
      .expectOne(base + 'modeling/start/')
      .flush(
        { error_code: 'job_legacy_preview_required' },
        { status: 409, statusText: 'Conflict' },
      );
    const preview = http.expectOne(base + 'jobs/datasets/1/legacy-input/');
    expect(preview.request.body.operation).toBe('training');
    preview.flush({
      plan_sha256: 'a'.repeat(64),
      inputs_sha256: 'b'.repeat(64),
      budget: { seconds: 120 },
    });
  }
  it('submits only after exact review, then polls the accepted job', () => {
    let result: any;
    data.startModeling(1, 'data_files/v1.csv', 'xgboost').subscribe((reply) => (result = reply));
    proposal();
    expect(review.pending$.value?.fileId).toBe(1);
    http.expectNone(base + 'modeling/start/');
    review.resolve(true);
    const submitted = http.expectOne(base + 'modeling/start/');
    expect(submitted.request.body.execution_request.plan_sha256).toBe('a'.repeat(64));
    expect(submitted.request.body.execution_request.request_id).toMatch(/^[0-9a-f-]{36}$/);
    submitted.flush({ native_job_id: jobId, job_status: 'queued' });
    expect(result.native_job_id).toBe(jobId);
    data.getModelingStatus(1).subscribe();
    http
      .expectOne(
        (request) =>
          request.url === base + 'modeling/status/1/' && request.params.get('job_id') === jobId,
      )
      .flush({ job_status: 'running' });
  });
  it('canceling review performs no submission or fallback', () => {
    let failure: any;
    data.startModeling(1, 'data_files/v1.csv').subscribe({ error: (error) => (failure = error) });
    proposal();
    review.resolve(false);
    expect(failure.executionCancelled).toBeTrue();
    http.expectNone(base + 'modeling/start/');
  });
  it('session changes invalidate an outstanding proposal', () => {
    let failure: any;
    data.startModeling(1, 'data_files/v1.csv').subscribe({ error: (error) => (failure = error) });
    proposal();
    auth.user = { id: 2, username: 'another-developer' };
    review.resolve(true);
    expect(failure.message).toContain('session changed');
    http.expectNone(base + 'modeling/start/');
  });
  it('selection sends previous projection and immutable result references', () => {
    data
      .selectLegacyCandidate(
        jobId,
        { file_id: 1, result_sha256: 'c'.repeat(64), expected_projection_sha256: 'd'.repeat(64) },
        jobId,
      )
      .subscribe();
    const request = http.expectOne(base + `jobs/${jobId}/legacy-selection/`);
    expect(request.request.body.execution_id).toBe(jobId);
    expect(request.request.body.result_sha256).toBe('c'.repeat(64));
    expect(request.request.body.expected_projection_sha256).toBe('d'.repeat(64));
    request.flush({ currently_selected: true });
  });
});
