import { TestBed, ComponentFixture } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { PackageReviewComponent } from './package-review.component';
import { AuthService } from '../services/auth.service';

describe('Package review receipts and context', () => {
  let fixture: ComponentFixture<PackageReviewComponent>;
  let component: PackageReviewComponent;
  let http: HttpTestingController;
  const review = {
    id: 'case',
    revision: 3,
    bundle_id: 'bundle',
    freshness: 'current',
    findings: [],
    events: [],
  };
  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [PackageReviewComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AuthService, useValue: { apiRoot: '/api/' } },
      ],
    });
    fixture = TestBed.createComponent(PackageReviewComponent);
    component = fixture.componentInstance;
    http = TestBed.inject(HttpTestingController);
    fixture.componentRef.setInput('fileId', 1);
    fixture.componentRef.setInput('projectId', 'project-a');
    fixture.componentRef.setInput('role', 'reviewer');
    fixture.detectChanges();
    const request = http.expectOne('/api/reviews/datasets/1/?project_id=project-a');
    expect(request.request.transferCache).toBeFalse();
    request.flush({
      reviews: [],
      current_package: { bundle_id: 'bundle', manifest_sha256: 'sha' },
      next_offset: null,
    });
  });
  afterEach(() => {
    fixture.destroy();
    http.verify();
  });
  it('opens the exact package with a unique receipt and no client actor', () => {
    component.start();
    const request = http.expectOne('/api/reviews/datasets/1/?project_id=project-a');
    expect(request.request.body).toEqual({
      request_id: jasmine.any(String),
      bundle_id: 'bundle',
      manifest_sha256: 'sha',
    });
    request.flush(review);
    expect(component.review).toEqual(review);
    expect(component.pending).toBeNull();
  });
  it('retries an ambiguous write using identical code-free payload and receipt', () => {
    component.review = review;
    component.text = 'Exact finding';
    component.submit();
    const first = http.expectOne('/api/reviews/case/?project_id=project-a');
    const payload = first.request.body;
    first.error(new ProgressEvent('network'));
    expect(component.pending?.body).toBe(payload);
    component.text = 'Edited after uncertain outcome';
    component.retry();
    const retry = http.expectOne('/api/reviews/case/?project_id=project-a');
    expect(retry.request.body).toEqual(payload);
    expect(payload.expected_revision).toBe(3);
    retry.flush({ ...review, revision: 4, replayed: true });
    expect(component.text).toBe('');
    expect(component.pending).toBeNull();
  });
  it('clears stale discussion after a definite conflict', () => {
    component.review = review;
    component.text = 'Finding';
    component.submit();
    http
      .expectOne('/api/reviews/case/?project_id=project-a')
      .flush({ error_code: 'review_revision_changed' }, { status: 409, statusText: 'Conflict' });
    expect(component.review).toBeNull();
    expect(component.pending).toBeNull();
    expect(component.error).toContain('review_revision_changed');
  });
  it('retains a receipt when a final authority check withholds confirmation', () => {
    component.review = review;
    component.text = 'Finding before revocation';
    component.submit();
    const first = http.expectOne('/api/reviews/case/?project_id=project-a');
    const payload = first.request.body;
    first.flush(
      { error_code: 'project_authority_changed' },
      { status: 403, statusText: 'Forbidden' },
    );
    expect(component.pending?.body).toEqual(payload);
    expect(component.review).toBeNull();
    expect(component.directory).toBeNull();
    component.retry();
    const retry = http.expectOne('/api/reviews/case/?project_id=project-a');
    expect(retry.request.body).toEqual(payload);
    retry.flush({ ...review, revision: 4, replayed: true });
    expect(component.pending).toBeNull();
  });
  it('never submits historical evidence', () => {
    component.review = { ...review, freshness: 'historical' };
    component.text = 'Finding';
    component.submit();
    http.expectNone('/api/reviews/case/?project_id=project-a');
    expect(component.pending).toBeNull();
  });
  it('context changes cancel prior reads and clear pending authority', () => {
    component.open('old-case');
    const old = http.expectOne('/api/reviews/old-case/?project_id=project-a');
    component.pending = { url: '/old', body: { request_id: 'old' } };
    fixture.componentRef.setInput('projectId', 'project-b');
    fixture.componentRef.setInput('fileId', 2);
    fixture.detectChanges();
    expect(old.cancelled).toBeTrue();
    expect(component.review).toBeNull();
    expect(component.pending).toBeNull();
    http
      .expectOne('/api/reviews/datasets/2/?project_id=project-b')
      .flush({ reviews: [], next_offset: null });
  });
  it('refresh failure withholds records and authority', () => {
    component.review = review;
    component.refresh();
    http
      .expectOne('/api/reviews/datasets/1/?project_id=project-a')
      .flush({}, { status: 503, statusText: 'Unavailable' });
    expect(component.review).toBeNull();
    expect(component.directory).toBeNull();
    expect(component.error).toContain('could not be checked');
  });
  it('keeps findings as text instead of executing reviewer content', () => {
    component.review = {
      ...review,
      findings: [
        {
          id: 'f',
          severity: 'major',
          state: 'open',
          text: '<img src=x onerror=alert(1)>',
          responses: 0,
        },
      ],
    };
    fixture.detectChanges();
    http.expectOne('/api/jobs/datasets/1/?project_id=project-a').flush({
      jobs_enabled: false,
      jobs: [],
      total: 0,
      next_offset: null,
    });
    expect(fixture.nativeElement.textContent).toContain('<img src=x onerror=alert(1)>');
    expect(fixture.nativeElement.querySelector('img')).toBeNull();
  });
});
