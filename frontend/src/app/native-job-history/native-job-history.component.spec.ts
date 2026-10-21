import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { NativeJobHistoryComponent } from './native-job-history.component';
import { AuthService } from '../services/auth.service';

describe('Bounded native history observations', () => {
  let component: NativeJobHistoryComponent;
  let http: HttpTestingController;
  const page: any = {
    observed_at: '2026-10-21T00:00:00Z',
    history_cutoff: '2026-10-21T00:00:00Z',
    jobs: [{ id: 'first' }],
    next_cursor: 'signed-next',
    previous_cursor: null,
  };
  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [NativeJobHistoryComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AuthService, useValue: { apiRoot: '/api/' } },
      ],
    });
    component = TestBed.createComponent(NativeJobHistoryComponent).componentInstance;
    http = TestBed.inject(HttpTestingController);
    component.fileId = 1;
    component.projectId = 'project-a';
  });
  afterEach(() => {
    component.ngOnDestroy();
    http.verify();
  });
  function request() {
    return http.expectOne((r) => r.url.endsWith('/history/'));
  }
  it('observes through uncached GET with current project scope and no execution call', () => {
    component.ngOnChanges();
    const r = request();
    expect(r.request.method).toBe('GET');
    expect(r.request.params.get('project_id')).toBe('project-a');
    expect(r.request.transferCache).toBeFalse();
    r.flush(page);
    expect(component.page).toEqual(page);
    expect(component.busy).toBeFalse();
  });
  it('replaces each page instead of retaining unbounded history rows', () => {
    component.page = page;
    component.load(page.next_cursor);
    expect(component.page).toBeNull();
    const r = request();
    expect(r.request.params.get('cursor')).toBe('signed-next');
    r.flush({ ...page, jobs: [{ id: 'older' }], previous_cursor: 'signed-prev' });
    expect(component.page!.jobs).toEqual([{ id: 'older' }] as any);
    component.load(component.page!.previous_cursor);
    const previous = request();
    expect(previous.request.params.get('cursor')).toBe('signed-prev');
    previous.flush(page);
  });
  it('explicit refresh and filter changes discard the previous navigation fence', () => {
    component.state = 'failed';
    component.kind = 'package_integrity_v1';
    component.load();
    const r = request();
    expect(r.request.params.get('state')).toBe('failed');
    expect(r.request.params.get('kind')).toBe('package_integrity_v1');
    expect(r.request.params.has('cursor')).toBeFalse();
    r.flush(page);
  });
  for (const status of [0, 403, 409, 503]) {
    it(`clears stale signals and gives explicit read failure diagnostics on ${status}`, () => {
      component.page = page;
      component.load('old-cursor');
      const r = request();
      if (status === 0) r.error(new ProgressEvent('error'));
      else r.flush({ error_code: 'history_unavailable' }, { status, statusText: 'Unavailable' });
      expect(component.page).toBeNull();
      expect(component.busy).toBeFalse();
      expect(component.error).toContain(
        status === 403
          ? 'project access'
          : status === 409
            ? 'stale or expired'
            : 'does not establish any job outcome',
      );
      http.expectNone((r) => r.method !== 'GET');
    });
  }
  it('cancels old context reads and resets filters without adopting stale observations', () => {
    component.load();
    const old = request();
    component.state = 'failed';
    component.kind = 'package_integrity_v1';
    component.fileId = 2;
    component.projectId = 'project-b';
    component.ngOnChanges();
    expect(old.cancelled).toBeTrue();
    expect(component.page).toBeNull();
    const current = request();
    expect(current.request.url).toBe('/api/jobs/datasets/2/history/');
    expect(current.request.params.get('project_id')).toBe('project-b');
    expect(current.request.params.get('state')).toBe('');
    expect(component.kind).toBe('');
    current.flush(page);
  });
  it('cancels a read when the history panel closes', () => {
    component.load();
    const r = request();
    component.ngOnDestroy();
    expect(r.cancelled).toBeTrue();
    expect(component.page).toBeNull();
  });
  it('renders bounded keyboard controls and explicit health limitations', () => {
    const fixture = TestBed.createComponent(NativeJobHistoryComponent);
    fixture.componentRef.setInput('fileId', 1);
    fixture.componentRef.setInput('projectId', 'project-a');
    fixture.detectChanges();
    request().flush({
      ...page,
      jobs: [],
      page_size: 50,
      queue: { states: {}, signals: {}, installation_limits: {} },
    });
    fixture.detectChanges();
    const root: HTMLElement = fixture.nativeElement;
    expect(root.textContent).toContain('Live worker and broker health: not observed');
    const buttons = [...root.querySelectorAll('nav button')];
    expect((buttons[0] as HTMLButtonElement).disabled).toBeTrue();
    expect((buttons[1] as HTMLButtonElement).disabled).toBeFalse();
    expect(root.querySelectorAll('select').length).toBe(2);
    fixture.destroy();
  });
});
