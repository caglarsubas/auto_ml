import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { NativeCandidateComponent } from './native-candidate.component';
import { AuthService } from '../services/auth.service';

describe('Native development candidate export and scoring', () => {
  let c: NativeCandidateComponent;
  let http: HttpTestingController;
  const job = {
    id: 'trained-1',
    file_id: 12,
    state: 'succeeded',
    specification: { kind: 'native_numeric_training_search_v1' },
    result_sha256: 'a'.repeat(64),
  };
  const preview = {
    training_job_id: job.id,
    training_result_sha256: job.result_sha256,
    input_file_id: 13,
    input_sha256: 'b'.repeat(64),
    scoring_sha256: 'c'.repeat(64),
  };
  const prepare = () => {
    c.inputFileId = 13;
    c.prepare();
    const req = http.expectOne('/api/jobs/trained-1/scoring-input/?project_id=project');
    expect(req.request.body).toEqual({
      input_file_id: 13,
      training_result_sha256: job.result_sha256,
    });
    req.flush(preview);
  };
  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [NativeCandidateComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AuthService, useValue: { apiRoot: '/api/' } },
      ],
    });
    c = TestBed.createComponent(NativeCandidateComponent).componentInstance;
    http = TestBed.inject(HttpTestingController);
    c.job = { ...job };
    c.projectId = 'project';
    c.role = 'developer';
    c.jobsEnabled = true;
    c.ngOnChanges();
  });
  afterEach(() => {
    c.ngOnDestroy();
    http.verify();
  });
  it('requires separate explicit confirmation after the pinned preview', () => {
    prepare();
    c.submit();
    http.expectNone('/api/jobs/datasets/12/?project_id=project');
    c.approved = true;
    c.submit();
    const req = http.expectOne('/api/jobs/datasets/12/?project_id=project');
    expect(req.request.body).toEqual({
      ...preview,
      kind: 'native_training_scoring_v1',
      request_id: expectUUID(),
    });
    const queued = spyOn(c.queued, 'emit');
    req.flush({ id: 'scores-1' });
    expect(queued).toHaveBeenCalledWith({ id: 'scores-1' });
  });
  for (const status of [0, 403, 503]) {
    it(`retains exact uncertain request for explicit retry after ${status}`, () => {
      prepare();
      c.approved = true;
      c.submit();
      const first = http.expectOne('/api/jobs/datasets/12/?project_id=project');
      const body = first.request.body;
      if (status === 0) first.error(new ProgressEvent('error'));
      else first.flush({}, { status, statusText: 'Unavailable' });
      expect(c.pending).toEqual(body);
      expect(c.preview).toBeNull();
      c.retry();
      const retry = http.expectOne('/api/jobs/datasets/12/?project_id=project');
      expect(retry.request.body).toEqual(body);
      retry.flush({ id: 'scores-1', replayed: true });
      expect(c.pending).toBeNull();
    });
  }
  for (const status of [400, 404, 409]) {
    it(`invalidates review after definite rejection ${status}`, () => {
      prepare();
      c.approved = true;
      c.submit();
      http
        .expectOne('/api/jobs/datasets/12/?project_id=project')
        .flush({}, { status, statusText: 'Rejected' });
      expect(c.pending).toBeNull();
      expect(c.preview).toBeNull();
      expect(c.approved).toBeFalse();
    });
  }
  it('edits invalidate the displayed review', () => {
    prepare();
    c.approved = true;
    c.changed();
    expect(c.preview).toBeNull();
    expect(c.approved).toBeFalse();
  });
  it('a programmatic input change cannot reuse approval', () => {
    prepare();
    c.approved = true;
    c.inputFileId = 14;
    c.submit();
    expect(c.preview).toBeNull();
  });
  it('context change cancels outstanding preview and clears pending evidence', () => {
    c.inputFileId = 13;
    c.prepare();
    const req = http.expectOne('/api/jobs/trained-1/scoring-input/?project_id=project');
    c.projectId = 'other';
    c.ngOnChanges();
    expect(req.cancelled).toBeTrue();
    expect(c.preview).toBeNull();
    expect(c.pending).toBeNull();
  });
  for (const role of ['reviewer', 'admin']) {
    it(`does not prepare or submit scoring as ${role}`, () => {
      c.role = role;
      c.inputFileId = 13;
      c.prepare();
      c.preview = preview;
      c.approved = true;
      c.submit();
      http.expectNone('/api/jobs/trained-1/scoring-input/?project_id=project');
      expect(c.pending).toBeNull();
    });
  }
  it('exports only after a fresh server authority check and retains external digest', () => {
    const create = spyOn(URL, 'createObjectURL').and.returnValue('blob:export');
    spyOn(URL, 'revokeObjectURL');
    spyOn(HTMLAnchorElement.prototype, 'click');
    c.download();
    const req = http.expectOne(
      '/api/jobs/trained-1/candidate/?project_id=project&sha256=' + job.result_sha256,
    );
    expect(req.request.responseType).toBe('blob');
    req.flush(new Blob(['{}']), { headers: { 'X-DeclarAI-Export-SHA256': 'd'.repeat(64) } });
    expect(c.exportSha).toBe('d'.repeat(64));
    expect(create).toHaveBeenCalled();
  });
  it('does not download denied or unpinned exports', () => {
    const create = spyOn(URL, 'createObjectURL');
    c.download();
    http
      .expectOne('/api/jobs/trained-1/candidate/?project_id=project&sha256=' + job.result_sha256)
      .flush(new Blob(['{}']));
    expect(create).not.toHaveBeenCalled();
    expect(c.exportSha).toBe('');
    c.download();
    http
      .expectOne('/api/jobs/trained-1/candidate/?project_id=project&sha256=' + job.result_sha256)
      .flush(new Blob(['{}']), { status: 403, statusText: 'Denied' });
    expect(create).not.toHaveBeenCalled();
  });
  it('disabled service blocks new admission while retaining export access', () => {
    c.jobsEnabled = false;
    c.inputFileId = 13;
    c.prepare();
    expect(c.preview).toBeNull();
  });
  function expectUUID() {
    return jasmine.stringMatching(/^[a-f0-9-]{36}$/);
  }
});
