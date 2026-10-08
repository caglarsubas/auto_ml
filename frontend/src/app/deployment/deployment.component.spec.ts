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
    component.onScoreFile({
      target: { files: [new File(['x\n1\n'], 'synthetic.csv')] },
    } as unknown as Event);
    const request = TestBed.inject(HttpTestingController).expectOne((req) =>
      req.url.endsWith('/deployment/score/'),
    );
    request.flush(
      { error: 'Missing required raw features: amount' },
      { status: 400, statusText: 'Bad Request' },
    );
    fixture.detectChanges();
    expect(component.isScoring).toBeFalse();
    expect(fixture.nativeElement.textContent).toContain('Missing required raw features: amount');
    TestBed.inject(HttpTestingController).verify();
  });
});
