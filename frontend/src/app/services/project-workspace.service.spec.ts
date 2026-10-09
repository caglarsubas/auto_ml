import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { AuthService } from './auth.service';
import { ProjectWorkspaceService, WorkspaceDirectory } from './project-workspace.service';
import { DataService } from './data.service';
import { ProjectWorkspaceGuard } from '../guards/project-workspace.guard';
import { RouterTestingModule } from '@angular/router/testing';
import { ActivatedRouteSnapshot, Router, UrlTree } from '@angular/router';
import { isObservable } from 'rxjs';

const project = (id: string, role: 'developer' | 'reviewer' | 'admin' = 'developer') => ({
  id,
  name: id,
  role,
  membership_revision: 'revision',
});
describe('Project workspace authority and transport', () => {
  let service: ProjectWorkspaceService;
  let http: HttpTestingController;
  let auth: AuthService;
  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [HttpClientTestingModule, RouterTestingModule] });
    service = TestBed.inject(ProjectWorkspaceService);
    http = TestBed.inject(HttpTestingController);
    auth = TestBed.inject(AuthService);
  });
  afterEach(() => http.verify());
  const load = (directory: WorkspaceDirectory, preferred?: string) => {
    service.refresh(preferred).subscribe();
    const req = http.expectOne(auth.apiRoot + 'projects/');
    expect(req.request.transferCache).toBeFalse();
    req.flush(directory);
  };
  it('requires an explicit choice for multiple memberships and refuses an unknown project', () => {
    load({ governed: true, projects: [project('a'), project('b')] });
    expect(service.projectId).toBeUndefined();
    expect(() => service.creationPayload({})).toThrowError(/Select a project/);
    service.select('a');
    expect(service.creationPayload({ name: 'work' }).project_id).toBe('a');
    service.select('unknown');
    expect(() => service.appendProject(new FormData())).toThrowError(/Select a project/);
  });
  it('checks a deep link against current membership instead of choosing another project', () => {
    load({ governed: true, projects: [project('a')] }, 'revoked');
    expect(service.projectId).toBeUndefined();
    expect(service.state.error).toContain('unavailable');
  });
  it('does not fall back to cached authority when the directory fails', () => {
    load({ governed: true, projects: [project('a')] });
    service.refresh().subscribe();
    expect(service.projectId).toBeUndefined();
    http
      .expectOne(auth.apiRoot + 'projects/')
      .flush({}, { status: 503, statusText: 'Unavailable' });
    expect(service.state.ready).toBeFalse();
    expect(service.state.error).toContain('Retry');
    expect(() => service.creationPayload({})).toThrowError(/Select a project/);
  });
  it('ignores an in-flight directory result after sign-out', () => {
    service.refresh().subscribe();
    const pending = http.expectOne(auth.apiRoot + 'projects/');
    auth.invalidate();
    pending.flush({ governed: true, projects: [project('a')] });
    expect(service.state.ready).toBeFalse();
    expect(service.projectId).toBeUndefined();
  });
  it('ignores superseded directory results', () => {
    service.refresh('a').subscribe();
    const first = http.expectOne(auth.apiRoot + 'projects/');
    service.refresh('b').subscribe();
    http.expectOne(auth.apiRoot + 'projects/').flush({ governed: true, projects: [project('b')] });
    first.flush({ governed: true, projects: [project('a')] });
    expect(service.projectId).toBe('b');
  });
  for (const role of ['reviewer', 'admin'] as const) {
    it(`keeps ${role} read access separate from new model work`, () => {
      load({ governed: true, projects: [project('a', role)] });
      expect(service.projectId).toBe('a');
      expect(() => service.creationPayload({})).toThrowError(/developer role/);
    });
  }
  it('pins upload, pipeline creation and reads to the current project', () => {
    load({ governed: true, projects: [project('a'), project('b')] }, 'b');
    const data = TestBed.inject(DataService);
    data.uploadFile(new File(['x,y\n1,0'], 'fixture.csv')).subscribe();
    const upload = http.expectOne(auth.apiRoot + 'declaration/');
    expect(upload.request.body.get('project_id')).toBe('b');
    upload.flush({});
    data.createPipelineRun({ name: 'work' }).subscribe();
    const create = http.expectOne(auth.apiRoot + 'pipeline/create/');
    expect(create.request.body.project_id).toBe('b');
    create.flush({});
    data.listPipelineRuns().subscribe();
    const list = http.expectOne(auth.apiRoot + 'pipeline/?project_id=b');
    list.flush([]);
    data.getPipelineRun(9).subscribe();
    http.expectOne(auth.apiRoot + 'pipeline/9/?project_id=b').flush({});
    data.createPipelineRun({ project_id: 'a' }).subscribe({
      next: () => fail('Conflicting creation must fail'),
      error: (error) => expect(error.message).toContain('current project'),
    });
  });
  it('preserves the explicit ungoverned compatibility mode', () => {
    load({ governed: false, projects: [] });
    expect(service.creationPayload({ name: 'legacy' })).toEqual({ name: 'legacy' });
  });
  for (const role of ['developer', 'reviewer', 'admin'] as const) {
    it(`guards the model route for ${role} using fresh membership`, () => {
      const guard = TestBed.inject(ProjectWorkspaceGuard);
      const route = { queryParamMap: { get: () => 'a' } } as unknown as ActivatedRouteSnapshot;
      const result = guard.canActivate(route);
      expect(isObservable(result)).toBeTrue();
      if (isObservable(result))
        result.subscribe((allowed) => {
          if (role === 'developer') expect(allowed).toBeTrue();
          else expect(allowed instanceof UrlTree).toBeTrue();
        });
      http
        .expectOne(auth.apiRoot + 'projects/')
        .flush({ governed: true, projects: [project('a', role)] });
    });
  }
  it('returns home without relabeling an already mounted workspace', () => {
    load({ governed: true, projects: [project('a'), project('b')] }, 'a');
    const router = TestBed.inject(Router);
    spyOnProperty(router, 'url', 'get').and.returnValue('/model-development?project_id=a');
    const result = TestBed.inject(ProjectWorkspaceGuard).canActivate({
      queryParamMap: { get: () => 'b' },
    } as unknown as ActivatedRouteSnapshot);
    expect(result instanceof UrlTree).toBeTrue();
    expect(service.projectId).toBe('a');
  });
});
