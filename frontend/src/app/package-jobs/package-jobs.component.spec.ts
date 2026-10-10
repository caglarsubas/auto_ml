import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { PackageJobsComponent } from './package-jobs.component';
import { AuthService } from '../services/auth.service';

describe('Durable package job receipts', () => {
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
  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [PackageJobsComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AuthService, useValue: { apiRoot: '/api/', user: { id: 4 } } },
      ],
    });
    component = TestBed.createComponent(PackageJobsComponent).componentInstance;
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
});
