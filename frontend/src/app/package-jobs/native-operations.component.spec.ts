import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { PackageJobsComponent } from './package-jobs.component';
import { AuthService } from '../services/auth.service';

describe('Operational handoff authority', () => {
  let component: PackageJobsComponent;
  let http: HttpTestingController;
  const snapshot = { sha256: 'a'.repeat(64), read_only: true };
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
    component.projectId = 'project-a';
    component.fileId = 1;
    component.job = { id: 'job-1', revision: 3, state: 'running', submitted_by: { id: 4 } };
  });
  afterEach(() => {
    component.ngOnDestroy();
    http.verify();
  });
  function request(download = false) {
    component.inspectHandoff(download);
    return http.expectOne((r) => r.url === '/api/jobs/job-1/operational-handoff/');
  }
  it('pins revision and bypasses transfer cache without mutation', () => {
    const r = request();
    expect(r.request.method).toBe('GET');
    expect(r.request.params.get('revision')).toBe('3');
    expect(r.request.params.get('project_id')).toBe('project-a');
    expect(r.request.transferCache).toBeFalse();
    r.flush(snapshot);
    expect(component.handoff).toEqual(snapshot);
    component.pending = { url: '/api/jobs/job-2/', body: { action: 'cancel' } };
    component.retry();
    expect(component.handoff).toBeNull();
    http.expectOne('/api/jobs/job-2/?project_id=project-a').flush({ id: 'job-2' });
  });
  it('refreshes access and the exact snapshot before a download', () => {
    component.handoff = snapshot;
    const save = spyOn<any>(component, 'save');
    const r = request(true);
    expect(r.request.params.get('sha256')).toBe(snapshot.sha256);
    expect(save).not.toHaveBeenCalled();
    r.flush(snapshot);
    expect(save).toHaveBeenCalledTimes(1);
  });
  for (const status of [403, 409, 503]) {
    it(`withholds stale or denied handoff on ${status}`, () => {
      component.handoff = snapshot;
      const save = spyOn<any>(component, 'save');
      request(true).flush({ error_code: 'job_handoff_stale' }, { status, statusText: 'Blocked' });
      expect(component.handoff).toBeNull();
      expect(component.job).toBeNull();
      expect(save).not.toHaveBeenCalled();
    });
  }
  it('never starts a handoff during an uncertain pending mutation', () => {
    component.pending = { url: '/api/jobs/job-1/', body: { action: 'cancel' } };
    component.inspectHandoff();
    http.expectNone('/api/jobs/job-1/operational-handoff/');
  });
  it('clears snapshots and cancels the request when context changes', () => {
    const r = request();
    component.ngOnChanges();
    expect(r.cancelled).toBeTrue();
    expect(component.handoff).toBeNull();
    http.expectOne('/api/jobs/datasets/1/?project_id=project-a').flush({ jobs: [] });
  });
});
