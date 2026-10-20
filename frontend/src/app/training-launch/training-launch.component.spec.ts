import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { TrainingLaunchComponent } from './training-launch.component';
import { AuthService } from '../services/auth.service';

describe('Reviewed durable training launch', () => {
  let component: TrainingLaunchComponent;
  let fixture: ComponentFixture<TrainingLaunchComponent>;
  let http: HttpTestingController;
  const url = '/api/jobs/datasets/1/?project_id=project-a';
  const previewUrl = '/api/jobs/datasets/1/training-input/?project_id=project-a';
  const preview = {
    kind: 'native_numeric_training_search_v1',
    input_sha256: 'a'.repeat(64),
    training_sha256: 'b'.repeat(64),
    prediction_contract: {
      task: 'classification',
      target_column: 'outcome',
      positive_class: 'bad',
    },
    folds: [{ train_rows: [0, 1], valid_rows: [2, 3] }],
    budget: { candidates: 2, seconds: 120 },
    runtime: { python: '3.12' },
  };
  function fill() {
    Object.assign(component.draft, {
      task: 'classification',
      target: 'outcome',
      positive: 'bad',
      predictors: 'x\nz',
      objective: 'Estimate event risk',
      population: 'Development applicants',
      horizon: '12 months',
      event: 'Observed event',
      maturity: 'Complete follow-up',
      metric: 'roc_auc',
      strategy: 'random',
      folds: 2,
      developmentOnly: true,
      available: true,
    });
  }
  function prepare() {
    component.prepare();
    const request = http.expectOne(previewUrl);
    request.flush(structuredClone(preview));
    component.approved = true;
    return request.request.body;
  }
  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [TrainingLaunchComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AuthService, useValue: { apiRoot: '/api/', user: { id: 4 } } },
      ],
    });
    fixture = TestBed.createComponent(TrainingLaunchComponent);
    component = fixture.componentInstance;
    fixture.componentRef.setInput('fileId', 1);
    fixture.componentRef.setInput('projectId', 'project-a');
    fixture.componentRef.setInput('role', 'developer');
    http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    http.expectOne(url).flush({ jobs_enabled: true, jobs: [], total: 0, next_offset: null });
    fill();
  });
  afterEach(() => {
    fixture.destroy();
    http.verify();
  });
  it('previews the explicit declaration and ordered predictors without submitting a job', () => {
    const body = prepare();
    expect(body.data_role).toBe('development_only');
    expect(body.features).toEqual(['x', 'z']);
    expect(body.business_understanding.target_contract.positive_class).toBe('bad');
    expect(body.validation).toEqual({ strategy: 'random', n_splits: 2 });
    expect(body.request_id).toBeUndefined();
    http.expectNone(url);
  });
  it('renders a labelled keyboard form and inspectable preview without expert or adoption actions', () => {
    prepare();
    fixture.detectChanges();
    expect(
      fixture.nativeElement.querySelector('textarea[name=predictors]').labels[0].textContent,
    ).toContain('Numeric predictor columns');
    expect(fixture.nativeElement.querySelector('label[for=training-task]').textContent.trim()).toBe(
      'Task',
    );
    expect(fixture.nativeElement.textContent).toContain('Review the exact plan');
    expect(fixture.nativeElement.querySelector('details pre').textContent).toContain(
      'training_sha256',
    );
    expect(fixture.nativeElement.textContent).toContain('No model adoption');
    expect(fixture.nativeElement.textContent).not.toContain('Queue integrity check');
  });
  for (const key of ['developmentOnly', 'available'] as const) {
    it(`requires the explicit ${key} declaration`, () => {
      component.draft[key] = false;
      component.prepare();
      expect(component.error).toContain('Complete the declaration');
      http.expectNone(previewUrl);
    });
  }
  for (const predictors of ['x\nx', 'outcome', '']) {
    it(`rejects invalid predictor selection ${JSON.stringify(predictors)}`, () => {
      component.draft.predictors = predictors;
      component.prepare();
      http.expectNone(previewUrl);
      expect(component.error).toContain('unique numeric predictors');
    });
  }
  it('preserves low-cardinality regression as an explicit task with no positive class', () => {
    component.draft.task = 'regression';
    component.draft.metric = 'rmse';
    const body = prepare();
    expect(body.business_understanding.problem_type).toBe('regression');
    expect(body.business_understanding.target_contract.positive_class).toBeNull();
  });
  it('pins group validation and excludes the entity control from predictors', () => {
    component.draft.strategy = 'group';
    component.draft.group = 'entity';
    expect(prepare().validation).toEqual({
      strategy: 'group',
      n_splits: 2,
      group_column: 'entity',
    });
    component.changed();
    component.draft.predictors = 'entity';
    component.prepare();
    http.expectNone(previewUrl);
  });
  it('pins temporal and outcome-window controls without shuffled fallback', () => {
    Object.assign(component.draft, {
      strategy: 'oot',
      date: 'observed',
      labelEnd: 'matures',
      group: 'entity',
      folds: 3,
    });
    expect(prepare().validation).toEqual({
      strategy: 'oot',
      n_splits: 3,
      date_column: 'observed',
      label_end_column: 'matures',
      group_column: 'entity',
    });
  });
  it('resets task-dependent labels, metrics and approval after changing task', () => {
    prepare();
    component.draft.task = 'regression';
    component.taskChanged();
    expect(component.preview).toBeNull();
    expect(component.approved).toBeFalse();
    expect(component.draft.positive).toBe('');
    expect(component.draft.metric).toBe('');
  });
  it('pins finite business costs while preserving the trusted metric', () => {
    Object.assign(component.draft, { metric: 'expected_cost', fnCost: 4, fpCost: 1 });
    expect(prepare().business_understanding.success_criteria).toEqual({
      primary_metric: 'expected_cost',
      cost_matrix: { fn_cost: 4, fp_cost: 1 },
    });
    component.changed();
    component.draft.fnCost = Infinity;
    component.prepare();
    http.expectNone(previewUrl);
  });
  it('requires explicit review and available job service before admission', () => {
    prepare();
    component.approved = false;
    component.submit();
    http.expectNone(url);
    component.approved = true;
    component.jobs!.directory.jobs_enabled = false;
    component.submit();
    http.expectNone(url);
  });
  it('invalidates a changed declaration even if a programmatic edit bypasses the form event', () => {
    prepare();
    component.draft.predictors = 'z\nx';
    component.submit();
    http.expectNone(url);
    expect(component.preview).toBeNull();
    expect(component.approved).toBeFalse();
  });
  it('queues exactly the approved plan and opens the durable job receipt', () => {
    const options = prepare();
    component.submit();
    component.submit();
    const request = http.expectOne(url),
      body = request.request.body;
    expect(body).toEqual({
      ...options,
      kind: preview.kind,
      request_id: jasmine.any(String),
      input_sha256: preview.input_sha256,
      training_sha256: preview.training_sha256,
    });
    request.flush({ id: 'job-1' });
    http.expectOne('/api/jobs/job-1/?project_id=project-a').flush({ id: 'job-1', state: 'queued' });
    expect(component.preview).toBeNull();
    expect(component.submittedId).toBe('job-1');
    expect(component.jobs!.directory.total).toBe(1);
    expect(component.jobs!.directory.jobs[0].id).toBe('job-1');
  });
  for (const status of [0, 403, 503]) {
    it(`retains the identical UUID and body after uncertain submission ${status}`, () => {
      prepare();
      component.submit();
      const first = http.expectOne(url),
        body = first.request.body;
      first.flush({ error_code: 'fixture_unavailable' }, { status, statusText: 'Unavailable' });
      expect(component.preview).toBeNull();
      expect(component.error).toContain('unconfirmed');
      expect(component.pending!.body).toEqual(body);
      component.retry();
      const retry = http.expectOne(url);
      expect(retry.request.body).toEqual(body);
      retry.flush({ id: 'job-replayed', replayed: true });
      http
        .expectOne('/api/jobs/job-replayed/?project_id=project-a')
        .flush({ id: 'job-replayed', state: 'queued' });
      expect(component.pending).toBeNull();
    });
  }
  it('clears a rejected stale preview and demands fresh review instead of resubmitting', () => {
    prepare();
    component.submit();
    http
      .expectOne(url)
      .flush({ error_code: 'job_training_spec_changed' }, { status: 409, statusText: 'Conflict' });
    expect(component.pending).toBeNull();
    expect(component.preview).toBeNull();
    expect(component.error).toContain('new preview');
    component.retry();
    http.expectNone(url);
  });
  it('explains known assessment history without proposing a reupload bypass', () => {
    component.prepare();
    http
      .expectOne(previewUrl)
      .flush(
        { error_code: 'job_training_requires_fresh_development_input' },
        { status: 409, statusText: 'Conflict' },
      );
    expect(component.error).toContain('reuploading assessed rows does not make them fresh');
    expect(component.preview).toBeNull();
  });
  it('rejects an incomplete preview receipt', () => {
    component.prepare();
    http.expectOne(previewUrl).flush({ ...preview, training_sha256: '' });
    expect(component.preview).toBeNull();
    expect(component.error).toContain('incomplete');
  });
  it('clears the declaration and cancels late preview delivery on project changes', () => {
    component.prepare();
    const late = http.expectOne(previewUrl);
    fixture.componentRef.setInput('projectId', 'project-b');
    fixture.detectChanges();
    expect(late.cancelled).toBeTrue();
    http
      .expectOne('/api/jobs/datasets/1/?project_id=project-b')
      .flush({ jobs_enabled: true, jobs: [] });
    expect(component.preview).toBeNull();
    expect(component.draft.developmentOnly).toBeFalse();
  });
  it('clears uncertain request state and closes write authority on role change', () => {
    prepare();
    component.submit();
    http.expectOne(url).flush({}, { status: 503, statusText: 'Unavailable' });
    fixture.componentRef.setInput('role', 'reviewer');
    fixture.detectChanges();
    http.expectOne(url).flush({ jobs_enabled: true, jobs: [] });
    component.retry();
    component.prepare();
    component.submit();
    http.expectNone(previewUrl);
    http.expectNone(url);
    expect(component.pending).toBeNull();
    expect(fixture.nativeElement.querySelector('form')).toBeNull();
  });
});
