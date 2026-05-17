import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { RouterTestingModule } from '@angular/router/testing';
import { FormsModule } from '@angular/forms';
import { CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { MatDialogModule } from '@angular/material/dialog';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBarModule } from '@angular/material/snack-bar';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { ModelDevelopmentComponent } from './model-development.component';
import { SharedService } from '../services/shared.service';
import { DataService } from '../services/data.service';
import { AiAssistantService } from '../services/ai-assistant.service';

describe('ModelDevelopmentComponent', () => {
  let component: ModelDevelopmentComponent;
  let fixture: ComponentFixture<ModelDevelopmentComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        HttpClientTestingModule,
        RouterTestingModule,
        FormsModule,
        MatDialogModule,
        MatSelectModule,
        MatSnackBarModule,
        BrowserAnimationsModule,
      ],
      declarations: [ModelDevelopmentComponent],
      providers: [SharedService, DataService, AiAssistantService],
      schemas: [CUSTOM_ELEMENTS_SCHEMA],
    }).compileComponents();

    fixture = TestBed.createComponent(ModelDevelopmentComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should have menu items for pipeline steps', () => {
    expect(component.menuItems).toContain('declaration');
    expect(component.menuItems).toContain('modeling');
    expect(component.menuItems).toContain('deployment');
  });

  it('should default currentStep to declaration', () => {
    expect(component.currentStep).toBe('declaration');
  });

  it('should default selectedPipeline to empty string', () => {
    expect(component.selectedPipeline).toBe('');
  });

  it('should have showSteps flags all false initially', () => {
    expect(component.showSteps['declaration']).toBeFalse();
    expect(component.showSteps['modeling']).toBeFalse();
  });

  // ── dataPurifierStartRequests$ subscription (v2.26.0+) ──────────────
  // AI's `start_data_purifier` action broadcasts here; this component
  // patches selectedOptions + split form fields and calls
  // proceedFromPreprocessing() — same code path as a manual
  // "Run Preprocessing" click.
  describe('dataPurifierStartRequests$ -> form-fields + proceedFromPreprocessing() sync', () => {
    let sharedService: SharedService;

    beforeEach(() => {
      sharedService = TestBed.inject(SharedService);
      fixture.detectChanges();
    });

    it('should patch selectedOptions and call proceedFromPreprocessing', (done) => {
      const spy = spyOn(component, 'proceedFromPreprocessing').and.callFake(() => { /* no-op */ });
      sharedService.emitDataPurifierStartRequest({
        purifier_options: [1, 2, 5],
        split: null,
      });
      setTimeout(() => {
        // selectedOptions is filtered from purifierOptions[] by ID.
        const ids = component.selectedOptions.map((o: any) => o.id).sort((a: number, b: number) => a - b);
        expect(ids).toEqual([1, 2, 5]);
        expect(spy).toHaveBeenCalledTimes(1);
        done();
      }, 5);
    });

    it('should NOT patch selectedOptions when purifier_options is empty', (done) => {
      const spy = spyOn(component, 'proceedFromPreprocessing').and.callFake(() => { /* no-op */ });
      // Pre-populate to verify it's preserved across an empty AI request.
      component.selectedOptions = component.purifierOptions.filter((o: any) => o.id === 7);
      sharedService.emitDataPurifierStartRequest({
        purifier_options: [],
        split: null,
      });
      setTimeout(() => {
        // User's pre-existing selection preserved.
        expect(component.selectedOptions.length).toBe(1);
        expect(component.selectedOptions[0].id).toBe(7);
        expect(spy).toHaveBeenCalledTimes(1);
        done();
      }, 5);
    });

    it('should patch random-split fields from request', (done) => {
      spyOn(component, 'proceedFromPreprocessing').and.callFake(() => { /* no-op */ });
      sharedService.emitDataPurifierStartRequest({
        purifier_options: [],
        split: { strategy: 'random', percent: 30 },
      });
      setTimeout(() => {
        expect(component.splitStrategy).toBe('random');
        expect(component.oosPercent).toBe(30);
        done();
      }, 5);
    });

    it('should patch OOT-cutoff split fields from request', (done) => {
      spyOn(component, 'proceedFromPreprocessing').and.callFake(() => { /* no-op */ });
      sharedService.emitDataPurifierStartRequest({
        purifier_options: [],
        split: {
          strategy: 'oot',
          date_column: 'Application_Datetime',
          cutoff: '2024-01-01T00:00:00',
        },
      });
      setTimeout(() => {
        expect(component.splitStrategy).toBe('oot');
        expect(component.splitDateColumn).toBe('Application_Datetime');
        expect(component.splitCutoff).toBe('2024-01-01T00:00:00');
        expect(component.ootMode).toBe('cutoff');
        done();
      }, 5);
    });

    it('should patch OOT-percent split fields from request', (done) => {
      spyOn(component, 'proceedFromPreprocessing').and.callFake(() => { /* no-op */ });
      sharedService.emitDataPurifierStartRequest({
        purifier_options: [],
        split: {
          strategy: 'oot',
          date_column: 'Application_Datetime',
          percent: 25,
        },
      });
      setTimeout(() => {
        expect(component.splitStrategy).toBe('oot');
        expect(component.splitDateColumn).toBe('Application_Datetime');
        expect(component.ootPercent).toBe(25);
        expect(component.ootMode).toBe('percent');
        done();
      }, 5);
    });

    it('should NOT patch form fields when split is null (form fallback)', (done) => {
      spyOn(component, 'proceedFromPreprocessing').and.callFake(() => { /* no-op */ });
      // Pre-populate to verify preservation.
      component.splitStrategy = 'oot';
      component.splitDateColumn = 'Application_Datetime';
      sharedService.emitDataPurifierStartRequest({
        purifier_options: [],
        split: null,
      });
      setTimeout(() => {
        expect(component.splitStrategy).toBe('oot');
        expect(component.splitDateColumn).toBe('Application_Datetime');
        done();
      }, 5);
    });
  });

  // ── encodingApplyRequests$ subscription (v2.26.0+) ──────────────────
  // AI's `apply_encoding` action broadcasts use_native flag here; this
  // component patches encodingUseNative and calls applyEncoding() —
  // same code path as a manual "Apply Encoding" click.
  describe('encodingApplyRequests$ -> applyEncoding() sync', () => {
    let sharedService: SharedService;

    beforeEach(() => {
      sharedService = TestBed.inject(SharedService);
      fixture.detectChanges();
    });

    it('should patch encodingUseNative and call applyEncoding', (done) => {
      const spy = spyOn(component, 'applyEncoding').and.callFake(() => { /* no-op */ });
      sharedService.emitEncodingApplyRequest({ use_native: false });
      setTimeout(() => {
        expect(component.encodingUseNative).toBeFalse();
        expect(spy).toHaveBeenCalledTimes(1);
        done();
      }, 5);
    });

    it('should pass use_native=true through unchanged', (done) => {
      const spy = spyOn(component, 'applyEncoding').and.callFake(() => { /* no-op */ });
      sharedService.emitEncodingApplyRequest({ use_native: true });
      setTimeout(() => {
        expect(component.encodingUseNative).toBeTrue();
        expect(spy).toHaveBeenCalledTimes(1);
        done();
      }, 5);
    });

    it('should NOT call applyEncoding on a rejected request', (done) => {
      const spy = spyOn(component, 'applyEncoding').and.callFake(() => { /* no-op */ });
      // SharedService guard rejects non-boolean use_native; subscription
      // doesn't fire.
      sharedService.emitEncodingApplyRequest({ use_native: 'true' as any });
      setTimeout(() => {
        expect(spy).not.toHaveBeenCalled();
        done();
      }, 5);
    });
  });
});
