import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { MatButtonModule } from '@angular/material/button';

import { DeploymentComponent } from './deployment.component';
import { SharedService } from '../services/shared.service';
import { DataService } from '../services/data.service';

describe('DeploymentComponent', () => {
  let component: DeploymentComponent;
  let fixture: ComponentFixture<DeploymentComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [DeploymentComponent],
      imports: [HttpClientTestingModule, NoopAnimationsModule, MatButtonModule],
      providers: [SharedService, DataService],
    }).compileComponents();

    fixture = TestBed.createComponent(DeploymentComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('explains raw bundle input and exposes required columns in expandable detail', () => {
    component.bundle = {
      manifest: { input_stage: 'raw_unencoded', input_features: ['amount', 'region'] },
    };
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;
    expect(root.textContent).toContain('raw data before preprocessing and encoding');
    expect(root.querySelector('details summary')?.textContent).toContain('Required input columns');
    expect(root.querySelector('details')?.textContent).toContain('amount');
    expect(root.textContent).not.toContain('Historical preprocessing provenance is unverified');
  });

  it('identifies the processed input and unverified historical provenance of older bundles', () => {
    component.bundle = { manifest: { input_stage: 'processed_unencoded' } };
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('processed data before encoding');
    expect(fixture.nativeElement.textContent).toContain(
      'Historical preprocessing provenance is unverified',
    );
  });

  it('shows an actionable missing-raw-feature response from scoring', () => {
    component.currentFileId = 1;
    component.bundle = { bundle_id: 'selected-bundle' };
    component.onScoreFile({
      target: { files: [new File(['x\n1\n'], 'synthetic.csv')] },
    } as unknown as Event);
    const request = TestBed.inject(HttpTestingController).expectOne((req) =>
      req.url.endsWith('/deployment/score/'),
    );
    expect(request.request.body.get('bundle_id')).toBe('selected-bundle');
    request.flush(
      { error: 'Missing required raw features: amount' },
      { status: 400, statusText: 'Bad Request' },
    );
    fixture.detectChanges();
    expect(component.isScoring).toBeFalse();
    expect(fixture.nativeElement.textContent).toContain('Missing required raw features: amount');
    TestBed.inject(HttpTestingController).verify();
  });
  it('pins packaging to readiness evidence and downloads/scoring to the selected bundle', () => {
    component.currentFileId = 1;
    component.readiness = {
      ready: true,
      execution_id: 'model-version',
      assessment_id: 'assessment-version',
    };
    component.createBundle();
    const http = TestBed.inject(HttpTestingController);
    const create = http.expectOne((req) => req.url.endsWith('/deployment/bundle/'));
    expect(create.request.body).toEqual({
      file_id: 1,
      execution_id: 'model-version',
      assessment_id: 'assessment-version',
    });
    create.flush({
      status: 'ok',
      bundle_id: 'frozen-bundle',
      manifest: { readiness: component.readiness },
    });
    component.downloadBundle();
    const download = http.expectOne((req) => req.url.endsWith('/deployment/pack/'));
    expect(download.request.body).toEqual({ file_id: 1, bundle_id: 'frozen-bundle' });
    expect(download.request.responseType).toBe('blob');
    download.flush(new Blob(), { status: 409, statusText: 'Conflict' });
    expect(component.isDownloading).toBeFalse();
    http.verify();
  });

  it('clears selected evidence and ignores late results when the file changes', () => {
    const shared = TestBed.inject(SharedService);
    const http = TestBed.inject(HttpTestingController);
    shared.setCurrentFileId(1);
    const old = http.match((req) => req.url.includes('/deployment/'));
    component.bundle = { bundle_id: 'previous-bundle' };
    component.scoreResult = { scores: [1] };
    shared.setCurrentFileId(2);
    expect(component.bundle).toBeNull();
    expect(component.scoreResult).toBeNull();
    old.forEach((req) =>
      req.flush({ status: 'ok', bundle_id: 'late-bundle', readiness: { ready: true } }),
    );
    expect(component.bundle).toBeNull();
    expect(component.readiness).toBeNull();
    http
      .match((req) => req.url.includes('/deployment/'))
      .forEach((req) => req.flush({ status: 'unknown', readiness: { ready: false } }));
    http.verify();
  });

  it('blocks creation until exact package checks pass', () => {
    component.currentFileId = 1;
    component.createBundle();
    expect(component.isBundling).toBeFalse();
    expect(component.error).toContain('this exact model and assessment');
    TestBed.inject(HttpTestingController).expectNone((req) =>
      req.url.endsWith('/deployment/bundle/'),
    );
  });
});
