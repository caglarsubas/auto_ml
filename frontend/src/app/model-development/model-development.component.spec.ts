import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { RouterTestingModule } from '@angular/router/testing';
import { FormsModule } from '@angular/forms';
import { CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { MatDialogModule } from '@angular/material/dialog';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBarModule } from '@angular/material/snack-bar';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { of } from 'rxjs';
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

  it('should preselect combined sparsity/missing purifier option without separate duplicates', () => {
    const ids = component.selectedOptions.map((o: any) => o.id).sort((a: number, b: number) => a - b);
    expect(ids).toEqual([1, 2, 3, 4, 7, 23, 28, 32]);
    expect(ids).not.toContain(11);
    expect(ids).not.toContain(17);
  });

  it('should have showSteps flags all false initially', () => {
    expect(component.showSteps['declaration']).toBeFalse();
    expect(component.showSteps['modeling']).toBeFalse();
  });

  it('should include hyperparameter tuning as the post-SFS pipeline flow sub-step', () => {
    const modelingStep = component.navMainSteps.find((step) => step.id === 'modeling');
    expect(modelingStep?.subSteps.map((sub) => sub.label)).toContain('Hyperparameter Tuning');
  });

  it('should mark hyperparameter tuning in progress after SFS and completed after results', () => {
    const sharedService = TestBed.inject(SharedService);

    sharedService.setModelingCheckpoint({
      substep: 'sfs_completed',
      modelingStatus: { model: {} },
      sfsBackwardResults: [{ step: 1 }],
    });
    expect(component.getSubStepStatus('2c')).toBe('completed');
    expect(component.getSubStepStatus('2d')).toBe('in_progress');

    sharedService.setModelingCheckpoint({
      substep: 'hyperparam_completed',
      modelingStatus: { model: {} },
      sfsBackwardResults: [{ step: 1 }],
      hpResults: { best_params: {} },
    });
    expect(component.getSubStepStatus('2d')).toBe('completed');
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

  // ── purifierSelectionUpdates$ subscription (v2.28.0+) ───────────────
  // AI's `update_purifier_selection` action broadcasts here; this
  // component patches selectedOptions WITHOUT calling
  // proceedFromPreprocessing() — that's the whole UX distinction from
  // dataPurifierStartRequests$ above.  The patch is also pushed to AI
  // Redis so the next AI turn sees the new checkbox state on-screen.
  describe('purifierSelectionUpdates$ -> selectedOptions patch (no run)', () => {
    let sharedService: SharedService;
    let dataService: DataService;

    beforeEach(() => {
      sharedService = TestBed.inject(SharedService);
      dataService = TestBed.inject(DataService);
      fixture.detectChanges();
    });

    it('should REPLACE selectedOptions on wholesale-form broadcast', (done) => {
      spyOn(dataService, 'pushAiCache').and.returnValue(of({ status: 'success' }));
      // Seed with the redundant screenshot selection so we can verify it gets
      // wholesale-replaced.
      component.selectedOptions = component.purifierOptions
        .filter((o: any) => [1, 2, 3, 4, 7, 11, 17, 23, 28, 32].includes(o.id));
      sharedService.emitPurifierSelectionUpdate({
        form: 'wholesale',
        purifier_options: [1, 2, 3, 4, 7, 23, 28, 32],  // 11+17 removed
        add: [],
        remove: [],
      });
      setTimeout(() => {
        const ids = component.selectedOptions.map((o: any) => o.id).sort((a: number, b: number) => a - b);
        expect(ids).toEqual([1, 2, 3, 4, 7, 23, 28, 32]);
        // 11 and 17 must be gone from the form.
        expect(ids).not.toContain(11);
        expect(ids).not.toContain(17);
        done();
      }, 5);
    });

    it('should CLEAR selectedOptions when wholesale purifier_options is []', (done) => {
      spyOn(dataService, 'pushAiCache').and.returnValue(of({ status: 'success' }));
      component.selectedOptions = component.purifierOptions
        .filter((o: any) => [1, 2, 7].includes(o.id));
      sharedService.emitPurifierSelectionUpdate({
        form: 'wholesale',
        purifier_options: [],
        add: [],
        remove: [],
      });
      setTimeout(() => {
        expect(component.selectedOptions).toEqual([]);
        done();
      }, 5);
    });

    it('should ADD + REMOVE on diff-form broadcast', (done) => {
      spyOn(dataService, 'pushAiCache').and.returnValue(of({ status: 'success' }));
      // Mirror the screenshot's "current selection".
      component.selectedOptions = component.purifierOptions
        .filter((o: any) => [1, 2, 3, 4, 7, 11, 17, 23, 28, 32].includes(o.id));
      sharedService.emitPurifierSelectionUpdate({
        form: 'diff',
        purifier_options: null,
        add: [29],   // add the 0.05-0.95 outlier option…
        remove: [11, 17, 28],  // …and remove sparsity+missing+0.01-0.99 outlier
      });
      setTimeout(() => {
        const ids = component.selectedOptions.map((o: any) => o.id).sort((a: number, b: number) => a - b);
        expect(ids).toEqual([1, 2, 3, 4, 7, 23, 29, 32]);
        done();
      }, 5);
    });

    it('should handle diff-form with empty add (remove-only)', (done) => {
      spyOn(dataService, 'pushAiCache').and.returnValue(of({ status: 'success' }));
      component.selectedOptions = component.purifierOptions
        .filter((o: any) => [1, 2, 7].includes(o.id));
      sharedService.emitPurifierSelectionUpdate({
        form: 'diff',
        purifier_options: null,
        add: [],
        remove: [7],
      });
      setTimeout(() => {
        const ids = component.selectedOptions.map((o: any) => o.id).sort();
        expect(ids).toEqual([1, 2]);
        done();
      }, 5);
    });

    it('should handle diff-form with empty remove (add-only)', (done) => {
      spyOn(dataService, 'pushAiCache').and.returnValue(of({ status: 'success' }));
      component.selectedOptions = component.purifierOptions
        .filter((o: any) => o.id === 1);
      sharedService.emitPurifierSelectionUpdate({
        form: 'diff',
        purifier_options: null,
        add: [23, 29],
        remove: [],
      });
      setTimeout(() => {
        const ids = component.selectedOptions.map((o: any) => o.id).sort((a: number, b: number) => a - b);
        expect(ids).toEqual([1, 23, 29]);
        done();
      }, 5);
    });

    it('should NOT call proceedFromPreprocessing() (critical UX regression guard)', (done) => {
      // This is THE distinction from dataPurifierStartRequests$.  If
      // this subscriber ever fires proceedFromPreprocessing() the
      // "preview-then-run" UX collapses back into one-shot
      // apply-and-run, which is exactly what start_data_purifier is
      // for.  Two distinct actions must remain distinct.
      spyOn(dataService, 'pushAiCache').and.returnValue(of({ status: 'success' }));
      const runSpy = spyOn(component, 'proceedFromPreprocessing').and.callFake(() => { /* no-op */ });
      sharedService.emitPurifierSelectionUpdate({
        form: 'wholesale',
        purifier_options: [1, 23],
        add: [],
        remove: [],
      });
      setTimeout(() => {
        expect(runSpy).not.toHaveBeenCalled();
        done();
      }, 10);
    });

    it('should push the updated pipeline_config to AI Redis after patching', (done) => {
      const pushSpy = spyOn(dataService, 'pushAiCache').and.returnValue(of({ status: 'success' }));
      // currentFileId must be set or the push is skipped (non-fatal).
      component.currentFileId = 481;
      component.selectedOptions = component.purifierOptions
        .filter((o: any) => o.id === 1);
      sharedService.emitPurifierSelectionUpdate({
        form: 'wholesale',
        purifier_options: [1, 23],
        add: [],
        remove: [],
      });
      setTimeout(() => {
        expect(pushSpy).toHaveBeenCalledTimes(1);
        const [fileId, artifacts] = pushSpy.calls.mostRecent().args;
        expect(fileId).toBe(481);
        expect(artifacts['pipeline_config']).toBeDefined();
        // The pipeline_config snapshot is taken AFTER the
        // selectedOptions mutation, so the AI's next turn sees the
        // post-patch state.  `selected_purifier_steps` is a list of
        // option NAMES; pick the one corresponding to ID 23 to verify
        // it ended up in the snapshot.
        const stepNames: string[] = artifacts['pipeline_config']['selected_purifier_steps'] || [];
        const has23 = stepNames.some(n => n.includes('[Sparsity+Missing]-drop threshold = 0.95'));
        expect(has23).toBeTrue();
        done();
      }, 10);
    });

    it('should NOT push to AI Redis when currentFileId is null', (done) => {
      const pushSpy = spyOn(dataService, 'pushAiCache').and.returnValue(of({ status: 'success' }));
      component.currentFileId = null;
      sharedService.emitPurifierSelectionUpdate({
        form: 'wholesale',
        purifier_options: [1],
        add: [],
        remove: [],
      });
      setTimeout(() => {
        expect(pushSpy).not.toHaveBeenCalled();
        done();
      }, 5);
    });

    it('should write the new option IDs through to SharedService.setSelectedPurifierOptions', (done) => {
      spyOn(dataService, 'pushAiCache').and.returnValue(of({ status: 'success' }));
      const setSpy = spyOn(sharedService, 'setSelectedPurifierOptions').and.callThrough();
      sharedService.emitPurifierSelectionUpdate({
        form: 'wholesale',
        purifier_options: [1, 2, 23],
        add: [],
        remove: [],
      });
      setTimeout(() => {
        expect(setSpy).toHaveBeenCalledTimes(1);
        const ids = setSpy.calls.mostRecent().args[0];
        expect(ids.sort((a: number, b: number) => a - b)).toEqual([1, 2, 23]);
        done();
      }, 5);
    });
  });

  // ── 'Get AI Support' button for Data Purifier Summary (v2.41.0) ──────
  // The Data Purifier Summary card now has its own dedicated AI Support
  // button.  Unlike requestDatqAiSupport (which bundles DQ summary +
  // model_usage + split_validation), this one scopes the context to
  // purifier outputs only — so the LLM does not get drowned in noise
  // when the user is specifically asking about purifier behavior.
  describe("Data Purifier Summary 'Get AI Support' (v2.41.0)", () => {
    beforeEach(() => {
      // Spy on the shared requestAiSupport helper so we don't go through
      // the data-dict refetch / aiAssistant.requestSupport stack.
      spyOn(component, 'requestAiSupport').and.callFake(() => { /* no-op */ });
      // ngOnInit subscribes to currentFileId$/isStarted$/etc and each
      // calls computePreprocessingAvailable() which can reset our
      // hand-seeded flag.  Stub it so our flag survives detectChanges().
      spyOn(component as any, 'computePreprocessingAvailable').and.callFake(() => { /* no-op */ });
      // Seed the 5 fields the new method pulls into the context payload.
      component.rowCountBefore = 1000;
      component.rowCountAfter = 870;
      component.rowsRemovedTotal = 130;
      component.droppedColumnsByStep = [
        { step: 'sparsity', columns_dropped: ['var_x', 'var_y'] },
        { step: 'missing',  columns_dropped: ['var_z'] },
      ] as any;
      spyOn(component, 'droppedTotalCount').and.returnValue(3);
    });

    it('requestPurifierAiSupport() builds context with all 5 purifier fields and the correct section name', () => {
      component.requestPurifierAiSupport();

      expect(component.requestAiSupport).toHaveBeenCalledTimes(1);
      const args = (component.requestAiSupport as jasmine.Spy).calls.mostRecent().args;
      const ctx = args[0];
      const section = args[1];
      const prompt = args[2];
      expect(section).toBe('data_purifier');
      expect(typeof prompt).toBe('string');
      expect(prompt.length).withContext('prompt should be a meaningful directive').toBeGreaterThan(50);
      // Context shape: exactly one top-level key, no leakage of
      // DQ summary / model_usage / split_validation.
      expect(Object.keys(ctx)).toEqual(['purifier_summary']);
      expect(ctx.purifier_summary.rows_before).toBe(1000);
      expect(ctx.purifier_summary.rows_after).toBe(870);
      expect(ctx.purifier_summary.rows_removed).toBe(130);
      expect(ctx.purifier_summary.total_columns_dropped).toBe(3);
      expect(ctx.purifier_summary.dropped_by_step.length).toBe(2);
    });

    it('button renders inside .purifier-summary when droppedColumnsByStep is populated and routes click to requestPurifierAiSupport()', () => {
      // The card is gated on `droppedColumnsByStep && length` (already
      // seeded with 2 entries in beforeEach) AND sits inside an outer
      // <div *ngIf="preprocessingAvailable"> wrapper.  We flip that flag
      // AFTER an initial detectChanges() so ngOnInit subscriptions don't
      // get to reset it between our set and the second detectChanges().
      fixture.detectChanges();
      (component as any).preprocessingAvailable = true;
      fixture.detectChanges();

      const btn = fixture.nativeElement.querySelector('.purifier-summary .ai-support-btn') as HTMLButtonElement;
      expect(btn).withContext('Data Purifier AI Support button should render').toBeTruthy();
      expect((btn.textContent || '').trim()).toContain('Get AI Support');

      const spy = spyOn(component, 'requestPurifierAiSupport').and.callFake(() => { /* no-op */ });
      btn.click();
      expect(spy).toHaveBeenCalledTimes(1);
    });

    it('button is HIDDEN when droppedColumnsByStep is empty', () => {
      // Even with preprocessingAvailable=true, no dropped steps means
      // the .purifier-summary card itself is not rendered.
      component.droppedColumnsByStep = [];
      fixture.detectChanges();
      (component as any).preprocessingAvailable = true;
      fixture.detectChanges();

      const btn = fixture.nativeElement.querySelector('.purifier-summary .ai-support-btn');
      expect(btn).withContext('Purifier AI Support button must NOT render with no dropped steps').toBeNull();
    });
  });
});
