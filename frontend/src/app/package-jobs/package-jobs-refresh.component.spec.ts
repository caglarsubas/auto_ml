import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { PackageJobsComponent } from './package-jobs.component';
import { AuthService } from '../services/auth.service';

describe('Job evidence during an in-flight history refresh', () => {
  const directory = { jobs_enabled: true, jobs: [], total: 0, next_offset: null };
  const job = {
    id: 'finished-job',
    state: 'succeeded',
    submitted_by: { id: 4 },
    specification: { kind: 'package_integrity_v1' },
    events: [],
  };
  let component: PackageJobsComponent;
  let http: HttpTestingController;
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
    component.ngOnChanges();
    http.expectOne('/api/jobs/datasets/1/?project_id=project-a').flush(directory);
    component.job = job;
    component.handoff = { sha256: 'a'.repeat(64) };
  });
  afterEach(() => {
    component.ngOnDestroy();
    http.verify();
  });
  it('withdraws the old receipt immediately, before either refresh response arrives', () => {
    component.refresh();
    const listing = http.expectOne('/api/jobs/datasets/1/?project_id=project-a');
    expect(component.job).toBeNull();
    expect(component.handoff).toBeNull();
    expect(component.busy).toBeTrue();
    listing.flush(directory);
    const receipt = http.expectOne('/api/jobs/finished-job/?project_id=project-a');
    expect(component.job).toBeNull();
    expect(component.busy).toBeTrue();
    receipt.flush({ ...job, revision: 2 });
    expect(component.job.revision).toBe(2);
    expect(component.busy).toBeFalse();
  });
  it('withholds a previously requested download once refresh supersedes its generation', () => {
    const create = spyOn(URL, 'createObjectURL');
    component.download();
    const old = http.expectOne('/api/jobs/finished-job/?project_id=project-a');
    component.refresh();
    old.flush(job);
    expect(create).not.toHaveBeenCalled();
    http
      .expectOne('/api/jobs/datasets/1/?project_id=project-a')
      .flush({}, { status: 403, statusText: 'Forbidden' });
    expect(component.job).toBeNull();
    expect(component.handoff).toBeNull();
  });
});
