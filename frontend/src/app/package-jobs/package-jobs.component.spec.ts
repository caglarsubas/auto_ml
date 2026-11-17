import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { PackageJobsComponent } from './package-jobs.component';
import { AuthService } from '../services/auth.service';

describe('Durable package job receipts', () => {
  let fixture: ComponentFixture<PackageJobsComponent>;
  let component: PackageJobsComponent;
  let http: HttpTestingController;
  const directory = { jobs_enabled: true, jobs: [], total: 0, next_offset: null };
  const job = {
    id: 'job-1',
    state: 'queued',
    submitted_by: { id: 4, username: 'reviewer' },
    specification: { bundle_id: 'bundle-1' },
    events: [],
  };
  const assessment = {
    ...job,
    state: 'succeeded',
    result_sha256: 'a'.repeat(64),
    specification: {
      kind: 'native_protected_assessment_v1',
      runtime: { reproduction_platform: { system: 'Linux' } },
    },
    result: { n_assessed: 60, primary_value: 0.7, metric: { primary_metric: 'roc_auc' } },
    assessment_applicability: { status: 'exploratory' },
  };
  const reproductionUrl =
    '/api/jobs/job-1/reproduction/?project_id=project-a&sha256=' + 'a'.repeat(64);
  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [PackageJobsComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AuthService, useValue: { apiRoot: '/api/', user: { id: 4 } } },
      ],
    });
    fixture = TestBed.createComponent(PackageJobsComponent);
    component = fixture.componentInstance;
    http = TestBed.inject(HttpTestingController);
    component.fileId = 1;
    component.projectId = 'project-a';
    component.role = 'reviewer';
    component.packageInfo = { bundle_id: 'bundle-1', manifest_sha256: 'a'.repeat(64) };
    component.ngOnChanges();
    http.expectOne('/api/jobs/datasets/1/?project_id=project-a').flush({ ...directory, jobs: [] });
  });
  afterEach(() => {
    component.ngOnDestroy();
    http.verify();
  });
  it('pins a request and retries uncertain publication with the same UUID', () => {
    component.submit();
    const first = http.expectOne('/api/jobs/datasets/1/?project_id=project-a');
    const body = first.request.body;
    expect(body.kind).toBe('package_integrity_v1');
    expect(body.bundle_id).toBe('bundle-1');
    expect(body.manifest_sha256).toBe('a'.repeat(64));
    first.flush({}, { status: 503, statusText: 'Unavailable' });
    expect(component.pending?.body).toEqual(body);
    component.retry();
    const retry = http.expectOne('/api/jobs/datasets/1/?project_id=project-a');
    expect(retry.request.body).toEqual(body);
    retry.flush({ ...job, replayed: true });
    expect(component.pending).toBeNull();
    expect(component.directory.total).toBe(1);
    expect(component.canCancel).toBeTrue();
  });
  it('clears retained evidence after access is revoked while preserving the request', () => {
    component.submit();
    http
      .expectOne('/api/jobs/datasets/1/?project_id=project-a')
      .flush({}, { status: 403, statusText: 'Forbidden' });
    expect(component.directory).toBeNull();
    expect(component.job).toBeNull();
    expect(component.pending).not.toBeNull();
  });
  it('records cancellation explicitly and waits for worker acknowledgement', () => {
    component.job = { ...job, state: 'running' };
    component.cancel();
    const request = http.expectOne('/api/jobs/job-1/?project_id=project-a');
    expect(request.request.body).toEqual({ action: 'cancel' });
    request.flush({ ...job, state: 'cancel_requested' });
    expect(component.canCancel).toBeFalse();
    expect(component.job.state).toBe('cancel_requested');
  });
  it('cannot submit as admin or when the dedicated broker is disabled', () => {
    component.role = 'admin';
    component.submit();
    component.role = 'reviewer';
    component.directory.jobs_enabled = false;
    component.submit();
    expect(component.pending).toBeNull();
    http.expectNone('/api/jobs/datasets/1/?project_id=project-a');
  });
  it('drops pending evidence on project change and ignores superseded reads', () => {
    component.open('job-1');
    const old = http.expectOne('/api/jobs/job-1/?project_id=project-a');
    component.projectId = 'project-b';
    component.ngOnChanges();
    expect(old.cancelled).toBeTrue();
    http.expectOne('/api/jobs/datasets/1/?project_id=project-b').flush(directory);
    expect(component.job).toBeNull();
    expect(component.pending).toBeNull();
  });
  it('refreshes server authority before receipt download and withholds denied content', () => {
    const create = spyOn(URL, 'createObjectURL');
    component.job = job;
    component.download();
    http
      .expectOne('/api/jobs/job-1/?project_id=project-a')
      .flush({}, { status: 403, statusText: 'Forbidden' });
    expect(create).not.toHaveBeenCalled();
    expect(component.job).toBeNull();
  });
  it('refreshes confirmation applicability without rewriting the recorded assessment decision', () => {
    const save = spyOn(URL, 'createObjectURL').and.returnValue('blob:assessment-test');
    spyOn(HTMLAnchorElement.prototype, 'click');
    const receipt = {
      ...job,
      state: 'succeeded',
      specification: { kind: 'native_protected_assessment_v1' },
      result: {
        n_assessed: 30,
        metric: { primary_metric: 'roc_auc' },
        primary_value: 0.7,
        confirmatory: true,
        evidence_status: 'confirmatory',
        confirmation_reason: 'first_prospective_assessment_completed',
        outcome_access_id: 'outcome-1',
        training_result_sha256: 'a'.repeat(64),
        input_sha256: 'b'.repeat(64),
        reuse_adjudication: {
          policy: 'protected_assessment_reuse_v1',
          total: 0,
          counts: { exact_input: 0, overlapping_project: 0, unclassified_project: 0 },
          records: [],
        },
      },
      assessment_applicability: {
        status: 'current',
        reason_code: 'first_prospective_assessment_completed',
        assessment_sha256: 'c'.repeat(64),
        confirmation_usable: true,
      },
    };
    component.open('job-1');
    http.expectOne('/api/jobs/job-1/?project_id=project-a').flush(receipt);
    fixture.detectChanges();
    const text = () => fixture.nativeElement.textContent;
    expect(text()).toContain('Confirmatory evidence applies');

    component.download();
    const outdated = http.expectOne('/api/jobs/job-1/?project_id=project-a');
    component.download();
    http.expectOne('/api/jobs/job-1/?project_id=project-a').flush({
      ...receipt,
      assessment_applicability: {
        ...receipt.assessment_applicability,
        status: 'invalidated',
        reason_code: 'native_adoption_not_approved',
        confirmation_usable: false,
      },
    });
    outdated.flush(receipt);
    fixture.detectChanges();
    expect(save).toHaveBeenCalledTimes(1);
    expect(text()).not.toContain('Confirmatory evidence applies');
    expect(text()).toContain('Confirmation no longer applies');
    expect(text()).toContain('The independent approval is no longer active');
    expect(text()).toContain('native_adoption_not_approved');
    expect(text()).toContain('first_prospective_assessment_completed');
    expect(component.job.result).toEqual(receipt.result);
  });
  it('refreshes receipt authority before emitting an explicit review selection', () => {
    component.evidenceEnabled = true;
    component.job = { ...job, state: 'succeeded' };
    const emit = spyOn(component.receiptSelected, 'emit');
    component.selectReceipt();
    const request = http.expectOne('/api/jobs/job-1/?project_id=project-a');
    expect(request.request.transferCache).toBeFalse();
    expect(emit).not.toHaveBeenCalled();
    request.flush({ ...job, state: 'succeeded' });
    expect(emit).toHaveBeenCalledOnceWith({ ...job, state: 'succeeded' });
  });
  it('does not refresh or discard job context when a review action temporarily disables selection', () => {
    component.job = { ...job, state: 'succeeded' };
    component.ngOnChanges({
      evidenceEnabled: {
        previousValue: true,
        currentValue: false,
        firstChange: false,
        isFirstChange: () => false,
      },
    });
    expect(component.job.id).toBe('job-1');
    http.expectNone('/api/jobs/datasets/1/?project_id=project-a');
  });
  it('withholds a denied selection and ignores a receipt from a superseded context', () => {
    component.evidenceEnabled = true;
    component.job = { ...job, state: 'succeeded' };
    const emit = spyOn(component.receiptSelected, 'emit');
    component.selectReceipt();
    http
      .expectOne('/api/jobs/job-1/?project_id=project-a')
      .flush({}, { status: 403, statusText: 'Forbidden' });
    expect(emit).not.toHaveBeenCalled();
    component.job = { ...job, state: 'succeeded' };
    component.selectReceipt();
    const old = http.expectOne('/api/jobs/job-1/?project_id=project-a');
    component.projectId = 'project-b';
    component.ngOnChanges();
    expect(old.cancelled).toBeTrue();
    http.expectOne('/api/jobs/datasets/1/?project_id=project-b').flush(directory);
    expect(emit).not.toHaveBeenCalled();
  });
  it('pins prepared CSV bytes and preserves the exact scoring request after an uncertain response', () => {
    component.role = 'developer';
    component.selectInput(27);
    component.prepareInput();
    http.expectOne('/api/jobs/datasets/27/input/?project_id=project-a').flush({
      file_id: 27,
      sha256: 'b'.repeat(64),
      bytes: 52,
    });
    component.submitScore();
    const request = http.expectOne('/api/jobs/datasets/1/?project_id=project-a');
    const body = request.request.body;
    expect(body).toEqual({
      request_id: jasmine.any(String),
      kind: 'native_csv_scoring_v1',
      bundle_id: 'bundle-1',
      manifest_sha256: 'a'.repeat(64),
      input_file_id: 27,
      input_sha256: 'b'.repeat(64),
    });
    request.flush({}, { status: 503, statusText: 'Unavailable' });
    component.retry();
    const retry = http.expectOne('/api/jobs/datasets/1/?project_id=project-a');
    expect(retry.request.body).toEqual(body);
    retry.flush({ ...job, specification: body, replayed: true });
    expect(component.pending).toBeNull();
  });
  it('does not prepare or score as reviewer and requires a fresh preparation after input changes', () => {
    component.prepareInput();
    component.source = { file_id: 1, sha256: 'b'.repeat(64) };
    component.submitScore();
    expect(component.pending).toBeNull();
    component.role = 'developer';
    component.selectInput(2);
    component.submitScore();
    expect(component.source).toBeNull();
    expect(component.pending).toBeNull();
  });
  it('discards prepared source versions on project changes', () => {
    component.source = { file_id: 1, sha256: 'b'.repeat(64) };
    component.projectId = 'project-b';
    component.ngOnChanges();
    http.expectOne('/api/jobs/datasets/1/?project_id=project-b').flush(directory);
    expect(component.source).toBeNull();
  });
  it('withholds scoring downloads when current source authority is denied', () => {
    const create = spyOn(URL, 'createObjectURL');
    component.job = {
      ...job,
      state: 'succeeded',
      result_sha256: 'c'.repeat(64),
      specification: { kind: 'native_csv_scoring_v1' },
    };
    component.downloadScores();
    const request = http.expectOne(
      '/api/jobs/job-1/scores/?project_id=project-a&sha256=' + 'c'.repeat(64),
    );
    expect(request.request.responseType).toBe('blob');
    request.flush(null, { status: 403, statusText: 'Forbidden' });
    expect(create).not.toHaveBeenCalled();
    expect(component.job).toBeNull();
  });
  it('downloads exact fold evidence and displays the separately retained digest', () => {
    const save = spyOn(URL, 'createObjectURL').and.returnValue('blob:fold-test');
    spyOn(HTMLAnchorElement.prototype, 'click');
    component.job = {
      ...job,
      state: 'succeeded',
      result_sha256: 'a'.repeat(64),
      specification: { kind: 'legacy_native_execution_v1' },
    };
    component.downloadFolds();
    const request = http.expectOne(
      '/api/jobs/job-1/fold-provenance/?project_id=project-a&sha256=' + 'a'.repeat(64),
    );
    const body = new Blob(['{}']);
    request.flush(body, { headers: { 'X-DeclarAI-Export-SHA256': 'b'.repeat(64) } });
    expect(save).toHaveBeenCalledWith(body);
    expect(component.foldExportDigest).toBe('b'.repeat(64));
  });
  it('downloads a reviewer manifest pinned to the assessment and retains its separate digest', () => {
    const save = spyOn(URL, 'createObjectURL').and.returnValue('blob:reproduction-test');
    const selected = spyOn(component.reproductionSelected, 'emit');
    spyOn(HTMLAnchorElement.prototype, 'click');
    component.job = assessment;
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Download reproduction manifest');
    component.downloadReproduction();
    const request = http.expectOne(reproductionUrl);
    expect(request.request.responseType).toBe('blob');
    expect(request.request.transferCache).toBeFalse();
    const body = new Blob(['{}']);
    request.flush(body, { headers: { 'X-DeclarAI-Export-SHA256': 'b'.repeat(64) } });
    fixture.detectChanges();
    expect(save).toHaveBeenCalledOnceWith(body);
    expect(component.reproductionExportDigest).toBe('b'.repeat(64));
    expect(selected).toHaveBeenCalledOnceWith({
      assessment_job_id: 'job-1',
      assessment_result_sha256: 'a'.repeat(64),
      manifest_sha256: 'b'.repeat(64),
    });
    expect(component.foldExportDigest).toBe('');
    expect(fixture.nativeElement.textContent).toContain(
      'Retain this reproduction manifest SHA-256',
    );
  });
  it('withholds manifests for other roles, unsupported receipts and invalidated assessments', () => {
    component.job = assessment;
    component.role = 'developer';
    component.downloadReproduction();
    expect(component.canDownloadReproduction).toBeFalse();
    component.role = 'reviewer';
    for (const job of [
      { ...assessment, state: 'queued' },
      { ...assessment, result_sha256: '' },
      { ...assessment, specification: { kind: 'native_protected_assessment_v1' } },
      { ...assessment, assessment_applicability: { status: 'invalidated' } },
    ]) {
      component.job = job;
      component.downloadReproduction();
      expect(component.canDownloadReproduction).toBeFalse();
    }
    http.expectNone(reproductionUrl);
  });
  it('discards a late reproduction export after opening another job', () => {
    const save = spyOn(URL, 'createObjectURL');
    const selected = spyOn(component.reproductionSelected, 'emit');
    component.job = assessment;
    component.reproductionExportDigest = 'b'.repeat(64);
    component.downloadReproduction();
    const stale = http.expectOne(reproductionUrl);
    component.open('job-2');
    http.expectOne('/api/jobs/job-2/?project_id=project-a').flush({ ...job, id: 'job-2' });
    stale.flush(new Blob(['{}']), { headers: { 'X-DeclarAI-Export-SHA256': 'b'.repeat(64) } });
    expect(save).not.toHaveBeenCalled();
    expect(selected).toHaveBeenCalledOnceWith(null);
    expect(component.reproductionExportDigest).toBe('');
    expect(component.job.id).toBe('job-2');
  });
});
