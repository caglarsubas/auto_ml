import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { NativeAdoptionComponent } from './native-adoption.component';
import { AuthService } from '../services/auth.service';

describe('Reviewed native adoption and protected assessment', () => {
  let c: NativeAdoptionComponent;
  let http: HttpTestingController;
  const proposal = {
    id: 'adopt-1',
    revision: 0,
    state: 'proposed',
    usable: false,
    proposal_sha256: 'p'.repeat(64),
    events: [],
    protected_inputs: [],
  };
  const accepted = {
    ...proposal,
    revision: 1,
    state: 'accepted',
    usable: true,
    events: [{ payload: { actor: { id: 2 } } }],
  };
  const input = { id: 'sealed-1', specification: { rows: 60, input_sha256: 's'.repeat(64) } };
  const plan = {
    adoption_id: 'adopt-1',
    proposal_sha256: proposal.proposal_sha256,
    protected_input_id: input.id,
    assessment_sha256: 'a'.repeat(64),
  };
  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [NativeAdoptionComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AuthService, useValue: { apiRoot: '/api/', user: { id: 2 } } },
      ],
    });
    c = TestBed.createComponent(NativeAdoptionComponent).componentInstance;
    http = TestBed.inject(HttpTestingController);
    c.job = { id: 'train-1', file_id: 12, result_sha256: 'r'.repeat(64) };
    c.role = 'developer';
    c.projectId = 'project';
    c.jobsEnabled = true;
    c.ngOnChanges();
    http.expectOne('/api/jobs/train-1/adoptions/?project_id=project').flush({ adoptions: [] });
  });
  afterEach(() => {
    c.ngOnDestroy();
    http.verify();
  });
  it('requires explicit proposal confirmation and pins the training result', () => {
    c.proposalRationale = 'freeze this candidate';
    c.propose();
    expect(c.pending).toBeNull();
    c.proposalConfirmed = true;
    c.propose();
    const req = http.expectOne('/api/jobs/train-1/adoptions/?project_id=project');
    expect(req.request.body.training_result_sha256).toBe(c.job.result_sha256);
    req.flush(proposal);
    expect(c.adoption.id).toBe('adopt-1');
  });
  it('binds independent review to exact revision and proposal', () => {
    c.role = 'reviewer';
    c.choose(proposal);
    c.reviewRationale = 'independent review';
    c.reviewConfirmed = true;
    c.decide('approve');
    const req = http.expectOne('/api/native-adoptions/adopt-1/?project_id=project');
    expect(req.request.body.expected_revision).toBe(0);
    expect(req.request.body.proposal_sha256).toBe(proposal.proposal_sha256);
    req.flush(accepted);
    expect(c.canAssess).toBeTrue();
  });
  it('does not offer assessment to another reviewer or a developer', () => {
    c.choose(accepted);
    expect(c.canAssess).toBeFalse();
    c.role = 'reviewer';
    c.adoption = { ...accepted, events: [{ payload: { actor: { id: 99 } } }] };
    expect(c.canAssess).toBeFalse();
  });
  it('seals exact file and custody fields without launching evaluation', () => {
    c.role = 'reviewer';
    c.choose(accepted);
    c.file = new File(['x,z,outcome\n1,2,bad\n'], 'private.csv');
    c.custodyRationale = 'mature separate population';
    c.asOf = '2026-10-21T00:00:00Z';
    c.custodyConfirmed = true;
    c.seal();
    const req = http.expectOne(
      '/api/native-adoptions/adopt-1/protected-inputs/?project_id=project',
    );
    expect(req.request.body instanceof FormData).toBeTrue();
    expect(req.request.body.get('file')).toBe(c.file);
    const id = req.request.body.get('request_id');
    req.flush({ ...accepted, protected_inputs: [{ ...input, id }] });
    expect(c.preview).toBeNull();
    expect(c.file).toBeNull();
  });
  it('separately previews and authorizes the frozen assessment budget', () => {
    c.role = 'reviewer';
    c.choose(accepted);
    c.selected = input;
    c.prepare();
    http.expectOne('/api/native-protected-inputs/sealed-1/preview/?project_id=project').flush(plan);
    c.submit();
    expect(c.pending).toBeNull();
    c.executionConfirmed = true;
    c.submit();
    const req = http.expectOne('/api/jobs/datasets/12/?project_id=project');
    expect(req.request.body).toEqual({
      request_id: jasmine.any(String),
      kind: 'native_protected_assessment_v1',
      protected_input_id: input.id,
      assessment_sha256: plan.assessment_sha256,
    });
    const emitted = spyOn(c.queued, 'emit');
    req.flush({ id: 'assessment-1' });
    expect(emitted).toHaveBeenCalledWith({ id: 'assessment-1' });
  });
  for (const status of [0, 403, 503])
    it(`retains an uncertain action for exact retry after ${status}`, () => {
      c.proposalRationale = 'frozen';
      c.proposalConfirmed = true;
      c.propose();
      const req = http.expectOne('/api/jobs/train-1/adoptions/?project_id=project');
      const body = req.request.body;
      if (status === 0) req.error(new ProgressEvent('error'));
      else req.flush({}, { status, statusText: 'Unavailable' });
      expect(c.pending?.body).toEqual(body);
      c.retry();
      const retry = http.expectOne('/api/jobs/train-1/adoptions/?project_id=project');
      expect(retry.request.body).toBe(body);
      retry.flush(proposal);
    });
  it('retains the identical multipart file on uncertain custody response', () => {
    c.role = 'reviewer';
    c.choose(accepted);
    c.file = new File(['private'], 'private.csv');
    c.asOf = '2026-10-21T00:00:00Z';
    c.custodyRationale = 'mature';
    c.custodyConfirmed = true;
    c.seal();
    const req = http.expectOne(
        '/api/native-adoptions/adopt-1/protected-inputs/?project_id=project',
      ),
      body = req.request.body;
    req.flush({}, { status: 503, statusText: 'Unavailable' });
    c.retry();
    const retry = http.expectOne(
      '/api/native-adoptions/adopt-1/protected-inputs/?project_id=project',
    );
    expect(retry.request.body).toBe(body);
    retry.flush(accepted);
  });
  it('rejects a replaced sealed input after execution approval', () => {
    c.role = 'reviewer';
    c.choose(accepted);
    c.selected = input;
    c.preview = plan;
    c.executionConfirmed = true;
    c.selected = { ...input, id: 'different' };
    c.submit();
    expect(c.preview).toBeNull();
    expect(c.pending).toBeNull();
  });
  it('context changes cancel old requests and clear review/custody state', () => {
    c.refresh();
    const old = http.expectOne('/api/jobs/train-1/adoptions/?project_id=project');
    c.projectId = 'other';
    c.ngOnChanges();
    expect(old.cancelled).toBeTrue();
    http.expectOne('/api/jobs/train-1/adoptions/?project_id=other').flush({ adoptions: [] });
    expect(c.adoption).toBeNull();
    expect(c.file).toBeNull();
    expect(c.preview).toBeNull();
  });
  it('definite stale-review rejection requires refreshed evidence', () => {
    c.role = 'reviewer';
    c.choose(proposal);
    c.reviewConfirmed = true;
    c.reviewRationale = 'accept';
    c.decide('approve');
    http
      .expectOne('/api/native-adoptions/adopt-1/?project_id=project')
      .flush(
        { error_code: 'native_adoption_review_changed' },
        { status: 409, statusText: 'Stale' },
      );
    expect(c.pending).toBeNull();
    expect(c.adoption).toBeNull();
    expect(c.error).toContain('native_adoption_review_changed');
  });
});
