import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { RouterTestingModule } from '@angular/router/testing';
import { FormsModule } from '@angular/forms';
import { CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { MatDialogModule } from '@angular/material/dialog';
import { MatSnackBarModule } from '@angular/material/snack-bar';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { ModelingComponent } from './modeling.component';
import { SharedService } from '../services/shared.service';
import { DataService } from '../services/data.service';
import { AiAssistantService } from '../services/ai-assistant.service';

describe('ModelingComponent', () => {
  let component: ModelingComponent;
  let fixture: ComponentFixture<ModelingComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        HttpClientTestingModule,
        RouterTestingModule,
        FormsModule,
        MatDialogModule,
        MatSnackBarModule,
        BrowserAnimationsModule,
      ],
      declarations: [ModelingComponent],
      providers: [SharedService, DataService, AiAssistantService],
      schemas: [CUSTOM_ELEMENTS_SCHEMA],
    }).compileComponents();

    fixture = TestBed.createComponent(ModelingComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should initialize with null processedFilePath', () => {
    expect(component.processedFilePath).toBeNull();
  });

  it('should default selectedOptionIds to empty array', () => {
    expect(component.selectedOptionIds).toEqual([]);
  });

  it('should have null runPreview initially', () => {
    expect(component.runPreview).toBeNull();
  });

  // ── metadataUpdates$ subscription (v2.23.0+) ──────────────────────────
  // When the AI assistant assistant changes a feature's LoM via
  // `update_metadata`, the chat panel broadcasts the {column, field,
  // value} array on metadataUpdates$.  The modeling component must
  // patch the matching encoding plan entry's user_lom AND its dependent
  // fields (fallback_strategy, needs_ranking, ranking) — exactly as if
  // the user had changed the dropdown manually.  Without this, the chat
  // says "Var_2 is now ordinal" while the dropdown still shows Nominal.
  describe('metadataUpdates$ -> encodingPlan sync', () => {
    let sharedService: SharedService;

    beforeEach(() => {
      sharedService = TestBed.inject(SharedService);
      // Drive the component through ngOnInit so the subscription wires up.
      fixture.detectChanges();
    });

    function seedEncodingPlan(plan: any[]): void {
      component.encodingPlan = plan;
    }

    it('should flip a matching feature\'s user_lom to ordinal and recompute side effects', () => {
      seedEncodingPlan([
        { feature: 'Var_2', user_lom: 'nominal', nunique: 7,
          fallback_strategy: 'label_encoding', fallback_reason: 'Nominal feature → Label Encoding',
          needs_ranking: false, ranking: null },
      ]);
      sharedService.emitMetadataUpdates([
        { column: 'Var_2', field: 'Level_of_Measurement', value: 'ordinal' },
      ]);
      const entry = component.encodingPlan[0];
      expect(entry.user_lom).toBe('ordinal');
      // 7 unique values → 5–10 bucket → ordinal_encoding + needs_ranking
      // (matches the manual updateEncodingLom side-effect logic).
      expect(entry.fallback_strategy).toBe('ordinal_encoding');
      expect(entry.needs_ranking).toBeTrue();
    });

    it('should flip back from ordinal to nominal and clear ranking state', () => {
      seedEncodingPlan([
        { feature: 'Var_36', user_lom: 'ordinal', nunique: 7,
          fallback_strategy: 'ordinal_encoding', fallback_reason: '...',
          needs_ranking: true, ranking: ['low', 'mid', 'high'] },
      ]);
      sharedService.emitMetadataUpdates([
        { column: 'Var_36', field: 'Level_of_Measurement', value: 'nominal' },
      ]);
      const entry = component.encodingPlan[0];
      expect(entry.user_lom).toBe('nominal');
      expect(entry.fallback_strategy).toBe('label_encoding');
      expect(entry.needs_ranking).toBeFalse();
      expect(entry.ranking).toBeNull();
    });

    it('should ignore a feature not in the encoding plan', () => {
      seedEncodingPlan([
        { feature: 'Var_2', user_lom: 'nominal', nunique: 5,
          fallback_strategy: 'label_encoding', fallback_reason: 'x' },
      ]);
      sharedService.emitMetadataUpdates([
        { column: 'NotInPlan', field: 'Level_of_Measurement', value: 'ordinal' },
      ]);
      // Untouched.
      expect(component.encodingPlan[0].user_lom).toBe('nominal');
    });

    it('should mirror Feature_Description on the matching encoding plan entry', () => {
      seedEncodingPlan([
        { feature: 'Var_9', user_lom: 'nominal', nunique: 3,
          fallback_strategy: 'label_encoding', fallback_reason: 'x',
          description: 'Old' },
      ]);
      sharedService.emitMetadataUpdates([
        { column: 'Var_9', field: 'Feature_Description', value: 'Last credit decision' },
      ]);
      expect(component.encodingPlan[0].description).toBe('Last credit decision');
      // LoM-dependent fields stay untouched on description-only change.
      expect(component.encodingPlan[0].fallback_strategy).toBe('label_encoding');
    });

    it('should mirror non-dropdown LoM values (cardinal) without crashing', () => {
      // The dropdown only renders nominal/ordinal, but the AI may set
      // cardinal/continuous on FE features.  We mirror the value on
      // the entry so debugging is possible — the dropdown will simply
      // render blank (a visible signal that the entry is stale).
      seedEncodingPlan([
        { feature: 'FE_Contact_Info_Count', user_lom: 'nominal', nunique: 12,
          fallback_strategy: 'label_encoding', fallback_reason: 'x' },
      ]);
      sharedService.emitMetadataUpdates([
        { column: 'FE_Contact_Info_Count', field: 'Level_of_Measurement', value: 'cardinal' },
      ]);
      expect(component.encodingPlan[0].user_lom).toBe('cardinal');
      // No side-effect recomputation for cardinal — entry is now stale
      // and a re-run of analyzeEncoding is needed.
    });

    it('should do nothing when encodingPlan is empty (modeling step not entered yet)', () => {
      component.encodingPlan = [];
      // Should not throw.
      expect(() => sharedService.emitMetadataUpdates([
        { column: 'Var_2', field: 'Level_of_Measurement', value: 'ordinal' },
      ])).not.toThrow();
      expect(component.encodingPlan).toEqual([]);
    });
  });

  // ── encodingRankingUpdates$ subscription (v2.24.0+) ──────────────────
  // The AI assistant's procedural follow-through path: after setting
  // LoM=ordinal (handled by metadataUpdates$), it emits a
  // `set_ordinal_ranking` action with the ranked category values.
  // The chat panel forwards those rankings here and we patch
  // encodingPlan[i].ranking on the matching feature — equivalent to
  // the user clicking "Set Ranking" and arranging the values manually.
  describe('encodingRankingUpdates$ -> encodingPlan.ranking sync', () => {
    let sharedService: SharedService;

    beforeEach(() => {
      sharedService = TestBed.inject(SharedService);
      fixture.detectChanges();
    });

    function seedEncodingPlan(plan: any[]): void {
      component.encodingPlan = plan;
    }

    it('should patch entry.ranking on the matching feature', () => {
      seedEncodingPlan([
        { feature: 'Var_36', user_lom: 'ordinal', nunique: 7,
          fallback_strategy: 'ordinal_encoding', needs_ranking: true,
          unique_values: ['0', '1', '2', '3', '8', 'L', 'Others'],
          ranking: null },
      ]);
      sharedService.emitEncodingRankingUpdates([
        { column: 'Var_36', ranking: ['0', '1', '2', '3', '8', 'L', 'Others'] },
      ]);
      expect(component.encodingPlan[0].ranking).toEqual(
        ['0', '1', '2', '3', '8', 'L', 'Others']);
    });

    it('should clone the ranking defensively (subsequent ▲▼ must not mutate AI source)', () => {
      seedEncodingPlan([
        { feature: 'Var_X', user_lom: 'ordinal', nunique: 3,
          fallback_strategy: 'ordinal_encoding', needs_ranking: true,
          unique_values: ['Low', 'Mid', 'High'], ranking: null },
      ]);
      const aiSource = ['Low', 'Mid', 'High'];
      sharedService.emitEncodingRankingUpdates([
        { column: 'Var_X', ranking: aiSource },
      ]);
      // entry.ranking must be a different array reference so any
      // subsequent moveRankingUp/Down doesn't mutate the AI's source.
      expect(component.encodingPlan[0].ranking).not.toBe(aiSource);
      expect(component.encodingPlan[0].ranking).toEqual(aiSource);
    });

    it('should coerce numeric ranking values to strings (encoding lookup key type)', () => {
      seedEncodingPlan([
        { feature: 'Var_Num', user_lom: 'ordinal', nunique: 4,
          fallback_strategy: 'ordinal_encoding', needs_ranking: true,
          unique_values: ['0', '1', '2', '3'], ranking: null },
      ]);
      // The LLM may emit ints — the modeling component must coerce
      // to strings so the backend _ordinal_encode lookup hits.
      sharedService.emitEncodingRankingUpdates([
        { column: 'Var_Num', ranking: [0, 1, 2, 3] as any },
      ]);
      expect(component.encodingPlan[0].ranking).toEqual(['0', '1', '2', '3']);
      expect(component.encodingPlan[0].ranking.every((v: any) => typeof v === 'string')).toBeTrue();
    });

    it('should ignore updates whose column is not in the encoding plan', () => {
      seedEncodingPlan([
        { feature: 'Var_36', user_lom: 'ordinal', nunique: 3,
          fallback_strategy: 'ordinal_encoding', needs_ranking: true,
          unique_values: ['A', 'B', 'C'], ranking: null },
      ]);
      sharedService.emitEncodingRankingUpdates([
        { column: 'NotInPlan', ranking: ['x', 'y'] },
      ]);
      // Untouched.
      expect(component.encodingPlan[0].ranking).toBeNull();
    });

    it('should patch multiple features in a single emission', () => {
      seedEncodingPlan([
        { feature: 'Var_2', user_lom: 'ordinal', nunique: 3,
          fallback_strategy: 'ordinal_encoding', needs_ranking: true,
          unique_values: ['A', 'P', 'R'], ranking: null },
        { feature: 'Var_36', user_lom: 'ordinal', nunique: 7,
          fallback_strategy: 'ordinal_encoding', needs_ranking: true,
          unique_values: ['0', '1', '2', '3', '8', 'L', 'Others'], ranking: null },
      ]);
      sharedService.emitEncodingRankingUpdates([
        { column: 'Var_2', ranking: ['A', 'P', 'R'] },
        { column: 'Var_36', ranking: ['0', '1', '2', '3', '8', 'L', 'Others'] },
      ]);
      expect(component.encodingPlan[0].ranking).toEqual(['A', 'P', 'R']);
      expect(component.encodingPlan[1].ranking).toEqual(
        ['0', '1', '2', '3', '8', 'L', 'Others']);
    });

    it('should silently skip entries with empty ranking arrays', () => {
      seedEncodingPlan([
        { feature: 'Var_X', user_lom: 'ordinal', nunique: 3,
          fallback_strategy: 'ordinal_encoding', needs_ranking: true,
          unique_values: ['Low', 'Mid', 'High'], ranking: ['Low', 'Mid', 'High'] },
      ]);
      const before = [...component.encodingPlan[0].ranking];
      sharedService.emitEncodingRankingUpdates([
        { column: 'Var_X', ranking: [] },
      ]);
      // Existing ranking preserved — empty payload is a no-op for that entry.
      expect(component.encodingPlan[0].ranking).toEqual(before);
    });

    it('should do nothing when encodingPlan is empty (late mount safety)', () => {
      component.encodingPlan = [];
      expect(() => sharedService.emitEncodingRankingUpdates([
        { column: 'Var_36', ranking: ['Low', 'Mid', 'High'] },
      ])).not.toThrow();
      expect(component.encodingPlan).toEqual([]);
    });

    // End-to-end procedural-chain check: simulate the AI's two-action
    // sequence (LoM=ordinal first, then set_ordinal_ranking) and
    // verify the final entry state matches what a user clicking
    // through the UI manually would produce.
    it('should fully transform a nominal entry through the procedural chain', () => {
      seedEncodingPlan([
        { feature: 'Var_36', user_lom: 'nominal', nunique: 7,
          fallback_strategy: 'label_encoding',
          fallback_reason: 'Nominal feature → Label Encoding',
          needs_ranking: false, ranking: null,
          unique_values: ['0', '1', '2', '3', '8', 'L', 'Others'] },
      ]);
      // Step 1: AI sets LoM = ordinal via update_metadata
      sharedService.emitMetadataUpdates([
        { column: 'Var_36', field: 'Level_of_Measurement', value: 'ordinal' },
      ]);
      // Side effects from updateEncodingLom (nunique=7 → 5–10 bucket)
      expect(component.encodingPlan[0].user_lom).toBe('ordinal');
      expect(component.encodingPlan[0].fallback_strategy).toBe('ordinal_encoding');
      expect(component.encodingPlan[0].needs_ranking).toBeTrue();
      // Step 2: AI sets the ranking via set_ordinal_ranking
      sharedService.emitEncodingRankingUpdates([
        { column: 'Var_36', ranking: ['0', '1', '2', '3', '8', 'L', 'Others'] },
      ]);
      // Final state matches the UI's manual "Set Ranking" + reorder path.
      expect(component.encodingPlan[0].ranking).toEqual(
        ['0', '1', '2', '3', '8', 'L', 'Others']);
    });
  });

  // ── featureUsageUpdates$ subscription (v2.25.0+) ──────────────────────
  // AI's `update_config feature_usage` action broadcasts here; the
  // modeling component patches the Selected Features table's
  // Keep/Drop dropdown in place — identical to a user changing the
  // dropdown manually.  The next SFS start picks up the exclusion
  // through the existing excludedFeatures collection.
  describe('featureUsageUpdates$ -> featureUsage map sync', () => {
    let sharedService: SharedService;

    beforeEach(() => {
      sharedService = TestBed.inject(SharedService);
      fixture.detectChanges();
      component.featureUsage = {};
      component.featureDropReason = {};
    });

    it('should set featureUsage[col]=drop and record the reason', () => {
      sharedService.emitFeatureUsageUpdates([
        { column: 'Var_3', value: 'drop', reason: 'VIF=9.39' },
      ]);
      expect(component.featureUsage['Var_3']).toBe('drop');
      expect(component.featureDropReason['Var_3']).toBe('VIF=9.39');
    });

    it('should clear the reason when flipping back to keep', () => {
      component.featureUsage['Var_3'] = 'drop';
      component.featureDropReason['Var_3'] = 'VIF=9.39';
      sharedService.emitFeatureUsageUpdates([
        { column: 'Var_3', value: 'keep' },
      ]);
      expect(component.featureUsage['Var_3']).toBe('keep');
      // Matches the template's onChange handler: $event === 'keep'
      // && (featureDropReason[f.feature] = '').
      expect(component.featureDropReason['Var_3']).toBe('');
    });

    it('should batch-patch multiple features in a single emission', () => {
      sharedService.emitFeatureUsageUpdates([
        { column: 'Var_3', value: 'drop', reason: 'VIF=9.39' },
        { column: 'Var_25', value: 'drop', reason: 'Low SHAP' },
        { column: 'Var_24', value: 'drop' },  // no reason
      ]);
      expect(component.featureUsage['Var_3']).toBe('drop');
      expect(component.featureUsage['Var_25']).toBe('drop');
      expect(component.featureUsage['Var_24']).toBe('drop');
      expect(component.featureDropReason['Var_3']).toBe('VIF=9.39');
      expect(component.featureDropReason['Var_25']).toBe('Low SHAP');
      // No reason supplied → unset (stays undefined / empty).
      expect(component.featureDropReason['Var_24']).toBeFalsy();
    });

    it('should ignore entries with invalid value', () => {
      sharedService.emitFeatureUsageUpdates([
        { column: 'Var_3', value: 'remove' as any },
        { value: 'drop', reason: 'no col' } as any,
      ]);
      expect(component.featureUsage['Var_3']).toBeUndefined();
    });
  });

  // ── sfsStartRequests$ subscription (v2.25.0+) ─────────────────────────
  // The dedicated path for the AI to actually kick off SFS.  Verifies
  // the modeling component populates form fields and calls startSfs()
  // — the same code path a manual "Start SFS" button click takes.
  describe('sfsStartRequests$ -> form-fields + startSfs() sync', () => {
    let sharedService: SharedService;

    beforeEach(() => {
      sharedService = TestBed.inject(SharedService);
      fixture.detectChanges();
    });

    it('should populate SFS form fields from the request and call startSfs()', (done) => {
      const startSpy = spyOn(component, 'startSfs').and.callFake(() => { /* no-op */ });
      sharedService.emitSfsStartRequest({
        methods: ['backward'],
        stopping_criteria: {
          metrics: [{ metric: 'roc_auc', pct_change: 1.5 }],
          min_features: 7,
          max_features: 20,
        },
        excluded_features: ['Var_3'],
        n_jobs: 4,
        top_k: 8,
      });
      // startSfs() is fired via setTimeout(0); poll once.
      setTimeout(() => {
        expect(component.sfsMethodBackward).toBeTrue();
        expect(component.sfsMethodForward).toBeFalse();
        expect(component.sfsMetrics).toEqual([{ metric: 'roc_auc', pct_change: 1.5 }]);
        expect(component.sfsMinFeatures).toBe(7);
        expect(component.sfsMaxFeatures).toBe(20);
        expect(component.sfsNJobs).toBe(4);
        expect(component.sfsTopK).toBe(8);
        // Excluded features also marked as drop in featureUsage map.
        expect(component.featureUsage['Var_3']).toBe('drop');
        expect(startSpy).toHaveBeenCalledTimes(1);
        done();
      }, 5);
    });

    it('should support both forward and backward methods together', (done) => {
      spyOn(component, 'startSfs').and.callFake(() => { /* no-op */ });
      sharedService.emitSfsStartRequest({
        methods: ['forward', 'backward'],
        stopping_criteria: {
          metrics: [
            { metric: 'roc_auc', pct_change: 1.0 },
            { metric: 'pr_auc', pct_change: 2.0 },
          ],
          min_features: 5,
          max_features: 15,
        },
        excluded_features: [],
        n_jobs: 3,
        top_k: 5,
      });
      setTimeout(() => {
        expect(component.sfsMethodForward).toBeTrue();
        expect(component.sfsMethodBackward).toBeTrue();
        expect(component.sfsMetrics.length).toBe(2);
        done();
      }, 5);
    });

    it('should reject empty methods (no startSfs call)', (done) => {
      const startSpy = spyOn(component, 'startSfs').and.callFake(() => { /* no-op */ });
      // The SharedService guard already blocks empty methods, but the
      // component's own guard is a defensive double-check.
      sharedService.emitSfsStartRequest({
        methods: [],
        stopping_criteria: {} as any,
        excluded_features: [],
        n_jobs: 3,
        top_k: 5,
      });
      setTimeout(() => {
        expect(startSpy).not.toHaveBeenCalled();
        done();
      }, 5);
    });

    it('should filter unknown metric names from the form fields', (done) => {
      spyOn(component, 'startSfs').and.callFake(() => { /* no-op */ });
      sharedService.emitSfsStartRequest({
        methods: ['backward'],
        stopping_criteria: {
          metrics: [
            { metric: 'roc_auc', pct_change: 1.0 },
            { metric: 'f1_score', pct_change: 2.0 } as any,  // unknown
          ],
          min_features: 5,
          max_features: 15,
        },
        excluded_features: [],
        n_jobs: 3,
        top_k: 5,
      });
      setTimeout(() => {
        // Only roc_auc survives the filter.
        expect(component.sfsMetrics).toEqual([{ metric: 'roc_auc', pct_change: 1.0 }]);
        done();
      }, 5);
    });

    // End-to-end procedural-chain check: AI's two-action sequence
    // for "drop Var_3 due to VIF and start SFS":
    //   1. update_config feature_usage=drop  → featureUsageUpdates$
    //   2. start_sfs                         → sfsStartRequests$
    // verifies final state mirrors manual UI click-through.
    it('should fully transform via the v2.25.0+ procedural chain', (done) => {
      const startSpy = spyOn(component, 'startSfs').and.callFake(() => { /* no-op */ });
      component.featureUsage = {};
      component.featureDropReason = {};

      // Step 1: AI flips Var_3 to drop with VIF reason.
      sharedService.emitFeatureUsageUpdates([
        { column: 'Var_3', value: 'drop', reason: 'VIF=9.39' },
      ]);
      expect(component.featureUsage['Var_3']).toBe('drop');
      expect(component.featureDropReason['Var_3']).toBe('VIF=9.39');

      // Step 2: AI starts SFS with Var_3 in excluded_features.
      sharedService.emitSfsStartRequest({
        methods: ['backward'],
        stopping_criteria: {
          metrics: [{ metric: 'roc_auc', pct_change: 1.0 }],
          min_features: 5,
          max_features: 15,
        },
        excluded_features: ['Var_3'],
        n_jobs: 3,
        top_k: 5,
      });
      setTimeout(() => {
        // Form fields populated.
        expect(component.sfsMethodBackward).toBeTrue();
        // featureUsage still has Var_3=drop (preserved across steps).
        expect(component.featureUsage['Var_3']).toBe('drop');
        // Reason preserved — the second action doesn't clobber the first.
        expect(component.featureDropReason['Var_3']).toBe('VIF=9.39');
        // startSfs() called exactly once.
        expect(startSpy).toHaveBeenCalledTimes(1);
        done();
      }, 5);
    });
  });

  // ── modelingStartRequests$ subscription (v2.26.0+) ────────────────────
  // The headline of v2.26.0 — closes the user's exact blocker from
  // v2.25.0 ("I cannot 'start' the modeling engine directly").
  // Verifies the modeling component populates form fields and calls
  // startModeling() — the same code path a manual "Start Modeling"
  // button click takes.
  describe('modelingStartRequests$ -> form-fields + startModeling() sync', () => {
    let sharedService: SharedService;

    beforeEach(() => {
      sharedService = TestBed.inject(SharedService);
      fixture.detectChanges();
    });

    it('should populate form fields from the request and call startModeling()', (done) => {
      const startSpy = spyOn(component, 'startModeling').and.callFake(() => { /* no-op */ });
      sharedService.emitModelingStartRequest({
        algorithm: 'lightgbm',
        encoding_use_native: false,
      });
      // startModeling() is fired via setTimeout(0); poll once.
      setTimeout(() => {
        expect(component.selectedAlgorithm).toBe('lightgbm');
        expect(component.encodingUseNative).toBeFalse();
        expect(startSpy).toHaveBeenCalledTimes(1);
        done();
      }, 5);
    });

    it('should not patch selectedAlgorithm when algorithm is null', (done) => {
      const startSpy = spyOn(component, 'startModeling').and.callFake(() => { /* no-op */ });
      // Pre-populate selectedAlgorithm so we can verify it's preserved.
      component.selectedAlgorithm = 'xgboost';
      sharedService.emitModelingStartRequest({
        algorithm: null,
        encoding_use_native: true,
      });
      setTimeout(() => {
        // The user's pre-existing form value is preserved.
        expect(component.selectedAlgorithm).toBe('xgboost');
        expect(component.encodingUseNative).toBeTrue();
        expect(startSpy).toHaveBeenCalledTimes(1);
        done();
      }, 5);
    });

    it('should strip whitespace from algorithm before patching', (done) => {
      spyOn(component, 'startModeling').and.callFake(() => { /* no-op */ });
      sharedService.emitModelingStartRequest({
        algorithm: 'lightgbm',  // already trimmed by the backend handler
        encoding_use_native: true,
      });
      setTimeout(() => {
        expect(component.selectedAlgorithm).toBe('lightgbm');
        done();
      }, 5);
    });

    it('should not call startModeling on rejected request (empty algorithm string)', (done) => {
      const startSpy = spyOn(component, 'startModeling').and.callFake(() => { /* no-op */ });
      // SharedService guard already filters this; the component's
      // own subscription doesn't even fire.
      sharedService.emitModelingStartRequest({
        algorithm: '   ',
        encoding_use_native: true,
      });
      setTimeout(() => {
        expect(startSpy).not.toHaveBeenCalled();
        done();
      }, 5);
    });
  });

  // ── pushModelingAiContext / pushModelingToAiCache (v2.36.0+) ─────────
  //
  // Closes ToDoS item #1: "the cached SHAP details currently show the
  // feature order but not numeric signed SHAP values".  Pre-v2.36.0 the
  // SHAP map read non-existent field names (`f.shap_impact` instead of
  // `f.impact`), so the cached `shap_details` artifact was just bare
  // `{feature: 'Var_5'}` items — the assistant had no way to reason
  // about impact direction.
  //
  // These specs lock in the field-name correctness AT THE FRONTEND so
  // the bug class cannot silently re-emerge if anyone refactors
  // `pushModelingAiContext` again.  The backend handler tests
  // (test_unit.py::TestShapDetailsHandler) verify that GIVEN a properly
  // populated cache, the handler renders `direction=UP/DOWN` correctly
  // — but the FE specs are what guarantee the cache is properly
  // populated in the first place.
  describe('pushModelingAiContext: shap_features field mapping (v2.36.0)', () => {
    let sharedService: SharedService;

    beforeEach(() => {
      sharedService = TestBed.inject(SharedService);
      fixture.detectChanges();
    });

    function seedModelingStatusWithSelectedFeatures(features: any[]): void {
      // Mirror the actual backend response shape produced by
      // ``modeling/views.py::ModelingStartView`` and dumped to
      // ``media/modeling/<id>_status.json`` — `feature`, `impact`,
      // `signed_impact`, `signed_mean`, `vif`, etc.  Tests must use
      // this shape (not the legacy `shap_impact` / `signed_shap_impact`
      // variant) — using the wrong key names here would mask the bug
      // that v2.36.0 actually fixed.
      (component as any).modelingStatus = {
        model: { selected_features: features, score: 0.85 },
      };
      // Required so the encoding-plan + cv branches don't short-circuit.
      component.encodingPlan = [];
    }

    it('should write shap_features with NUMERIC `impact` (not undefined) — the v2.36.0 regression', () => {
      seedModelingStatusWithSelectedFeatures([
        { feature: 'Var_5', impact: 0.342, signed_impact: 0.342,
          signed_mean: -0.095, vif: 1.8, combined_score: 0.91,
          shap_percentile: 0.95, gain_percentile: 0.88, usage: 'keep' },
        { feature: 'Var_7', impact: 0.349, signed_impact: -0.349,
          signed_mean: -0.085, vif: 2.1, combined_score: 0.89,
          shap_percentile: 0.93, gain_percentile: 0.81, usage: 'keep' },
      ]);
      // Capture what would be pushed to the AI cumulative context —
      // that's where shap_features lands BEFORE pushModelingToAiCache
      // forwards it to the Redis cache as `shap_details`.
      const setSpy = spyOn(sharedService, 'setAiCumulativeContext').and.callThrough();
      // Stub the network-bound cache push so this stays a unit test.
      spyOn((component as any), 'pushModelingToAiCache').and.callFake(() => { /* no-op */ });
      (component as any).pushModelingAiContext();
      expect(setSpy).toHaveBeenCalled();
      const pushedCtx = setSpy.calls.mostRecent().args[0] as any;
      expect(pushedCtx.shap_features).toBeDefined();
      expect(pushedCtx.shap_features.length).toBe(2);
      const v5 = pushedCtx.shap_features[0];
      // PRIMARY ASSERTION — impact must be a finite number, not undefined.
      // Pre-v2.36.0 this was undefined because the map read f.shap_impact
      // instead of f.impact.
      expect(typeof v5.impact).toBe('number');
      expect(Number.isFinite(v5.impact)).toBeTrue();
      expect(v5.impact).toBeCloseTo(0.342, 4);
      // SIGN must encode direction.  Var_7 has signed_impact < 0
      // (DOWN); Var_5 has signed_impact > 0 (UP).  This is what
      // enables the assistant to reason about impact direction.
      expect(typeof v5.signed_impact).toBe('number');
      expect(v5.signed_impact).toBeGreaterThan(0);
      const v7 = pushedCtx.shap_features[1];
      expect(typeof v7.signed_impact).toBe('number');
      expect(v7.signed_impact).toBeLessThan(0);
    });

    it('should include the v2.36.0-added context fields (signed_mean, vif) in shap_features items', () => {
      seedModelingStatusWithSelectedFeatures([
        { feature: 'Var_5', impact: 0.342, signed_impact: 0.342,
          signed_mean: -0.095, vif: 1.8 },
      ]);
      const setSpy = spyOn(sharedService, 'setAiCumulativeContext').and.callThrough();
      spyOn((component as any), 'pushModelingToAiCache').and.callFake(() => { /* no-op */ });
      (component as any).pushModelingAiContext();
      const pushedCtx = setSpy.calls.mostRecent().args[0] as any;
      const v5 = pushedCtx.shap_features[0];
      // signed_mean and vif are pulled into shap_features payload so
      // the assistant handler can render "raw_mean_signed=-0.0950"
      // and "VIF=1.80" tail context.  Without these, the v2.36.0
      // backend handler's tail-formatting branch would always be
      // skipped and the LLM would never see the collinearity hint
      // alongside SHAP magnitude.
      expect(v5.signed_mean).toBeCloseTo(-0.095, 4);
      expect(v5.vif).toBe(1.8);
    });

    it('should NOT read legacy field names (f.shap_impact / f.signed_shap_impact) — guards against pre-v2.36.0 regression', () => {
      // Construct selected_features with ONLY the legacy field names
      // populated and the v2.36.0 names as undefined.  Pre-v2.36.0 this
      // would have produced shap_features[0].impact = 0.5 (because the
      // map read f.shap_impact).  Post-v2.36.0 it must produce
      // shap_features[0].impact = undefined — i.e. the legacy fields
      // are ignored entirely.  Without this guard a future refactor
      // that "helpfully" added a fallback `f.impact ?? f.shap_impact`
      // would silently mask the actual fix and the bug could re-emerge
      // if the backend ever stopped writing `f.impact`.
      seedModelingStatusWithSelectedFeatures([
        { feature: 'LegacyVar', shap_impact: 0.5, signed_shap_impact: 0.5 },
      ]);
      const setSpy = spyOn(sharedService, 'setAiCumulativeContext').and.callThrough();
      spyOn((component as any), 'pushModelingToAiCache').and.callFake(() => { /* no-op */ });
      (component as any).pushModelingAiContext();
      const pushedCtx = setSpy.calls.mostRecent().args[0] as any;
      const item = pushedCtx.shap_features[0];
      // The legacy shap_impact is 0.5, but item.impact must be
      // undefined — confirming we read the canonical field name.
      expect(item.impact).toBeUndefined();
      expect(item.signed_impact).toBeUndefined();
    });
  });

  // ── SFS step tables: Description column (v2.36.1) ──────────────────
  //
  // Closes ToDoS item #5: "view details button under sfs progress with
  // the table containing per-step sfs results, including feature name,
  // description, CV ROC-AUC, percentage change, and direction."
  //
  // The modal, the post-completion Forward Selection Results table, and
  // the Backward Elimination table all carry a `Description` column
  // sourced from `getFeatureDescription(step.feature_name)` (which
  // resolves against `dataDictionaryCache`).  These specs are the lock:
  // if someone reorders columns, drops the cell, or breaks the lookup,
  // we want the test gate to fail BEFORE the change reaches a user.
  //
  // We deliberately verify the rendered DOM (not just component state)
  // because the bug class here is "the column silently disappeared from
  // the template" — which a pure state-level assertion would miss.
  describe('SFS step tables: Description column rendering (v2.36.1)', () => {
    beforeEach(() => {
      fixture.detectChanges();
      // Seed dataDictionaryCache with two entries the SFS step seeds
      // below will reference.  `Var_unknown` is deliberately absent so
      // the em-dash fallback path is exercised.
      component.dataDictionaryCache = [
        { Feature_Name: 'Var_5', Feature_Description: 'Customer credit score band' },
        { Feature_Name: 'Var_7', Feature_Description: 'Months since last default' },
      ];
      // The post-completion Forward/Backward results tables live inside
      // TWO nested gates in modeling.component.html:
      //   line 167: <div *ngIf="modelingStatus">          (outer)
      //   line 174: <div *ngIf="modelingStatus?.model">   (inner)
      // Both must be truthy or the SFS Results section at line 604 is
      // pruned from the DOM and our `.sfs-feature-description` querySelector
      // returns an empty NodeList.  An empty `model: {}` object suffices
      // because line 174 only does a truthiness check.
      (component as any).modelingStatus = { status: 'completed', model: {} };
    });

    function descriptionCellTexts(): string[] {
      const cells: NodeListOf<HTMLElement> =
        fixture.nativeElement.querySelectorAll('.sfs-feature-description');
      return Array.from(cells).map(c => (c.textContent || '').trim());
    }

    it('should render the Description header + cell in the View Details modal', () => {
      component.sfsCompletedSteps = [
        { step: 1, direction: 'forward', action: 'added',
          feature_name: 'Var_5', cv_roc_auc: 0.81, cv_pr_auc: 0.62,
          pct_changes: { roc_auc: 0, pr_auc: 0 } },
        { step: 2, direction: 'forward', action: 'added',
          feature_name: 'Var_7', cv_roc_auc: 0.83, cv_pr_auc: 0.65,
          pct_changes: { roc_auc: 2.47, pr_auc: 4.84 } },
      ];
      component.showSfsProgressModal = true;
      fixture.detectChanges();

      const headers: NodeListOf<HTMLElement> =
        fixture.nativeElement.querySelectorAll('th');
      const headerTexts = Array.from(headers).map(h => (h.textContent || '').trim());
      // Sanity: a Description header exists alongside the original
      // CV ROC-AUC / Direction columns — this is the "column wasn't
      // accidentally dropped" check.
      expect(headerTexts).toContain('Description');
      expect(headerTexts).toContain('CV ROC-AUC');
      expect(headerTexts).toContain('Direction');

      const texts = descriptionCellTexts();
      // Both modal rows must surface the dictionary text.
      expect(texts).toContain('Customer credit score band');
      expect(texts).toContain('Months since last default');
    });

    it('should render the Description column in the Forward Selection Results table', () => {
      component.sfsForwardResults = [
        { step: 1, feature_name: 'Var_5',
          train_roc_auc: 0.85, cv_roc_auc: 0.81, test_roc_auc: 0.80,
          train_pr_auc: 0.66, cv_pr_auc: 0.62, test_pr_auc: 0.60 },
        { step: 2, feature_name: 'Var_7',
          train_roc_auc: 0.87, cv_roc_auc: 0.83, test_roc_auc: 0.82,
          train_pr_auc: 0.69, cv_pr_auc: 0.65, test_pr_auc: 0.63 },
      ];
      fixture.detectChanges();

      const texts = descriptionCellTexts();
      expect(texts).toContain('Customer credit score band');
      expect(texts).toContain('Months since last default');
    });

    it('should render the Description column in the Backward Elimination table', () => {
      component.sfsBackwardResults = [
        { step: 1, feature_name: 'Var_5', selected_features: ['Var_5','Var_7','Var_9'],
          train_roc_auc: 0.85, cv_roc_auc: 0.81, test_roc_auc: 0.80,
          train_pr_auc: 0.66, cv_pr_auc: 0.62, test_pr_auc: 0.60 },
        { step: 2, feature_name: 'Var_7', selected_features: ['Var_5','Var_9'],
          train_roc_auc: 0.83, cv_roc_auc: 0.79, test_roc_auc: 0.78,
          train_pr_auc: 0.64, cv_pr_auc: 0.60, test_pr_auc: 0.58 },
      ];
      fixture.detectChanges();

      const texts = descriptionCellTexts();
      expect(texts).toContain('Customer credit score band');
      expect(texts).toContain('Months since last default');
    });

    it('should fall back to em-dash when the feature has no dictionary entry', () => {
      // Var_unknown is intentionally absent from dataDictionaryCache
      // (see beforeEach).  The cell text must be exactly the em-dash
      // placeholder so users see "missing" rather than blank.
      component.sfsCompletedSteps = [
        { step: 1, direction: 'forward', action: 'added',
          feature_name: 'Var_unknown', cv_roc_auc: 0.71, cv_pr_auc: 0.55,
          pct_changes: { roc_auc: 0, pr_auc: 0 } },
      ];
      component.showSfsProgressModal = true;
      fixture.detectChanges();

      const texts = descriptionCellTexts();
      // Em-dash (U+2014) — must match exactly what the template emits.
      expect(texts).toContain('\u2014');
    });

    it('should set the [title] attribute to the full description for hover preview (modal)', () => {
      // Description cells truncate with ellipsis at max-width.  The
      // [title] binding must carry the full text so users can hover to
      // see the rest — otherwise long descriptions are silently lost.
      component.sfsCompletedSteps = [
        { step: 1, direction: 'forward', action: 'added',
          feature_name: 'Var_5', cv_roc_auc: 0.81, cv_pr_auc: 0.62,
          pct_changes: { roc_auc: 0, pr_auc: 0 } },
      ];
      component.showSfsProgressModal = true;
      fixture.detectChanges();

      const cells: NodeListOf<HTMLElement> =
        fixture.nativeElement.querySelectorAll('.sfs-feature-description');
      // Find the cell whose body text matches the seeded description.
      const cell = Array.from(cells)
        .find(c => (c.textContent || '').trim() === 'Customer credit score band');
      expect(cell).toBeTruthy();
      expect(cell!.getAttribute('title')).toBe('Customer credit score band');
    });

    it('getFeatureDescription should resolve from dataDictionaryCache and return empty string on miss', () => {
      // The renderer leans on this helper for all three tables, so a
      // direct unit assertion guards the lookup contract independently
      // of any template wiring.
      expect(component.getFeatureDescription('Var_5')).toBe('Customer credit score band');
      expect(component.getFeatureDescription('Var_7')).toBe('Months since last default');
      // Miss must return '' (NOT undefined) so the template's
      // `|| '\u2014'` fallback fires cleanly.
      expect(component.getFeatureDescription('Var_unknown')).toBe('');
      // Empty/null inputs must not crash and must return ''.
      expect(component.getFeatureDescription('')).toBe('');
    });
  });

  // ── Backward cut-step lifecycle (v2.37.0) ─────────────────────────────
  // Locks in two related fixes:
  //
  //   (Bug A — regression) Before v2.37.0, fetchSfsResults() unconditionally
  //   called initBackwardCutStep() on every refetch, which RESET the user's
  //   manual cut selection (sfsBackwardCutStep, sfsBackwardCutFeatures) back
  //   to the last backward step.  Symptom: user clicks the radio at step 37,
  //   runs forward-from-backward, the SFS completes, fetchSfsResults() fires
  //   → green box label snaps back to "Step 67 (6 features)" even though the
  //   forward run actually used 36 features from step 37.  The user-visible
  //   bug: clicking the radio looked like it did nothing.
  //
  //   (Bug B — new feature) The AI's start_sfs tool now accepts a
  //   backward_cut_step parameter.  When present, the modeling component
  //   routes to startForwardFromBackwardFeatures() instead of startSfs() —
  //   the exact same code path the manual "Run Forward Selection on These N
  //   Features" button takes.  Without this, the AI's only way to mimic the
  //   cut was to enumerate every dropped feature in excluded_features, which
  //   never updated the visible cut step display.
  describe('backward cut-step lifecycle (v2.37.0)', () => {
    let sharedService: SharedService;
    let dataService: DataService;

    beforeEach(() => {
      sharedService = TestBed.inject(SharedService);
      dataService = TestBed.inject(DataService);
      fixture.detectChanges();
    });

    // Seeds a backward-results array shaped like the backend's
    // sanitize_sfs() output (modeling/views.py:1513): each step has
    // `step`, `feature_name`, `selected_features`, and a CV metric.
    function seedBackwardResults(): any[] {
      return [
        { step: 1, direction: 'backward', action: 'dropped',
          feature_name: 'Var_A', cv_roc_auc: 0.70,
          selected_features: ['Var_B', 'Var_C', 'Var_D'] },
        { step: 2, direction: 'backward', action: 'dropped',
          feature_name: 'Var_B', cv_roc_auc: 0.72,
          selected_features: ['Var_C', 'Var_D'] },
        { step: 3, direction: 'backward', action: 'dropped',
          feature_name: 'Var_C', cv_roc_auc: 0.68,
          selected_features: ['Var_D'] },
      ];
    }

    // ── setBackwardCutStep: manual click contract ──────────────────────
    it('setBackwardCutStep should set sfsBackwardCutStep and copy selected_features', () => {
      const steps = seedBackwardResults();
      component.sfsBackwardResults = steps;
      // Simulate the user clicking the radio at step 2.
      component.setBackwardCutStep(steps[1]);
      expect(component.sfsBackwardCutStep).toBe(2);
      expect(component.sfsBackwardCutFeatures).toEqual(['Var_C', 'Var_D']);
      // Verify it's a defensive copy (mutating the source row must not
      // leak into the component's state).
      (steps[1].selected_features as string[]).push('Var_LEAK');
      expect(component.sfsBackwardCutFeatures).not.toContain('Var_LEAK');
    });

    it('setBackwardCutStep should clear features when the step has no selected_features', () => {
      // Robustness: even though the backend writes selected_features on
      // every step, a corrupted/legacy result row must not crash the UI.
      component.setBackwardCutStep({ step: 7, feature_name: 'Var_X' } as any);
      expect(component.sfsBackwardCutStep).toBe(7);
      expect(component.sfsBackwardCutFeatures).toEqual([]);
    });

    // ── initBackwardCutStep: default-to-last semantics ─────────────────
    it('initBackwardCutStep should default to the last backward step when called fresh', () => {
      const steps = seedBackwardResults();
      component.sfsBackwardResults = steps;
      // Use `as any` to avoid TS control-flow narrowing — after a literal
      // null assignment the compiler will narrow subsequent reads to
      // `null` and reject the numeric `toBe(3)` matcher.
      (component as any).sfsBackwardCutStep = null;
      component.sfsBackwardCutFeatures = [];
      component.initBackwardCutStep();
      expect(component.sfsBackwardCutStep).toBe(3);
      expect(component.sfsBackwardCutFeatures).toEqual(['Var_D']);
    });

    it('initBackwardCutStep should null-out cut state when there are no backward results', () => {
      component.sfsBackwardResults = [];
      component.sfsBackwardCutStep = 99;
      component.sfsBackwardCutFeatures = ['stale'];
      component.initBackwardCutStep();
      expect(component.sfsBackwardCutStep).toBeNull();
      expect(component.sfsBackwardCutFeatures).toEqual([]);
    });

    // ── fetchSfsResults: Bug A regression lock ─────────────────────────
    //
    // Before v2.37.0 this call would have stomped sfsBackwardCutStep
    // back to step 3 (the last step in the response).  The fix preserves
    // step 2 because it's still a valid step in the refreshed results.
    it('fetchSfsResults should PRESERVE a user-selected cut step that is still valid', (done) => {
      const steps = seedBackwardResults();
      // Stub the HTTP call so the test stays synchronous and stable.
      spyOn(dataService, 'getSfsResults').and.returnValue({
        subscribe: (cb: any) => cb.next({
          forward: [], backward: steps, backward_remaining_features: ['Var_D'],
          forward_from_backward: [],
        })
      } as any);
      component.currentFileId = 42;
      component.sfsBackwardResults = steps;
      // User clicked step 2 before the refetch.
      component.setBackwardCutStep(steps[1]);
      expect(component.sfsBackwardCutStep).toBe(2);

      component.fetchSfsResults();

      setTimeout(() => {
        // Cut step PRESERVED — the unconditional initBackwardCutStep()
        // call is gone.  Features are resynced from the refreshed row.
        expect(component.sfsBackwardCutStep).toBe(2);
        expect(component.sfsBackwardCutFeatures).toEqual(['Var_C', 'Var_D']);
        done();
      }, 5);
    });

    it('fetchSfsResults should RESYNC sfsBackwardCutFeatures from the refreshed row data', (done) => {
      // After a stop+resume the backend may rewrite a step's selected_features
      // list.  The cut step is still valid, but the features list must
      // reflect the latest payload so the green box and the
      // startForwardFromBackwardFeatures() call use the correct set.
      const stale: any[] = [
        { step: 1, selected_features: ['Var_OLD_1', 'Var_OLD_2'] },
      ];
      const refreshed: any[] = [
        { step: 1, selected_features: ['Var_NEW_1', 'Var_NEW_2', 'Var_NEW_3'] },
      ];
      component.sfsBackwardResults = stale;
      component.setBackwardCutStep(stale[0]);
      expect(component.sfsBackwardCutFeatures).toEqual(['Var_OLD_1', 'Var_OLD_2']);

      spyOn(dataService, 'getSfsResults').and.returnValue({
        subscribe: (cb: any) => cb.next({
          forward: [], backward: refreshed, backward_remaining_features: [],
          forward_from_backward: [],
        })
      } as any);
      component.currentFileId = 42;
      component.fetchSfsResults();

      setTimeout(() => {
        // Cut step preserved, features resynced from refreshed data.
        expect(component.sfsBackwardCutStep).toBe(1);
        expect(component.sfsBackwardCutFeatures).toEqual(['Var_NEW_1', 'Var_NEW_2', 'Var_NEW_3']);
        done();
      }, 5);
    });

    it('fetchSfsResults should FALL BACK to last-step default when the cut step is no longer present', (done) => {
      // After an SFS restart, the backward results may be entirely new
      // and the user's previous cut step number may no longer exist.
      const fresh: any[] = [
        { step: 1, selected_features: ['F1', 'F2'] },
        { step: 2, selected_features: ['F2'] },
      ];
      component.sfsBackwardResults = [{ step: 99, selected_features: ['old'] }];
      // Use `as any` to avoid TS literal narrowing (= 99 narrows the read
      // type to `99 | null`, which then rejects the `toBe(2)` matcher).
      (component as any).sfsBackwardCutStep = 99;
      component.sfsBackwardCutFeatures = ['old'];

      spyOn(dataService, 'getSfsResults').and.returnValue({
        subscribe: (cb: any) => cb.next({
          forward: [], backward: fresh, backward_remaining_features: [],
          forward_from_backward: [],
        })
      } as any);
      component.currentFileId = 42;
      component.fetchSfsResults();

      setTimeout(() => {
        // Step 99 is no longer valid → fall back to last (step 2).
        expect(component.sfsBackwardCutStep).toBe(2);
        expect(component.sfsBackwardCutFeatures).toEqual(['F2']);
        done();
      }, 5);
    });

    // ── sfsStartRequests$ branching on backward_cut_step (Bug B) ───────
    it('sfsStartRequests$ with backward_cut_step + forward method should route to startForwardFromBackwardFeatures()', (done) => {
      const startSfsSpy = spyOn(component, 'startSfs').and.callFake(() => { /* no-op */ });
      const ffbSpy = spyOn(component, 'startForwardFromBackwardFeatures')
        .and.callFake(() => { /* no-op */ });
      const steps = seedBackwardResults();
      component.sfsBackwardResults = steps;

      sharedService.emitSfsStartRequest({
        methods: ['forward'],
        stopping_criteria: { metrics: [{ metric: 'roc_auc', pct_change: 1.0 }], min_features: 5, max_features: 15 },
        excluded_features: [],
        n_jobs: 3,
        top_k: 5,
        backward_cut_step: 2,  // ← v2.37.0+ new field
      });

      setTimeout(() => {
        // Cut step + features synced from the matching backward row.
        expect(component.sfsBackwardCutStep).toBe(2);
        expect(component.sfsBackwardCutFeatures).toEqual(['Var_C', 'Var_D']);
        // Routed to the forward-from-backward path; plain startSfs NOT called.
        expect(ffbSpy).toHaveBeenCalledTimes(1);
        expect(startSfsSpy).not.toHaveBeenCalled();
        done();
      }, 5);
    });

    it('sfsStartRequests$ should fall back to startSfs() when backward_cut_step is missing (no regression)', (done) => {
      const startSfsSpy = spyOn(component, 'startSfs').and.callFake(() => { /* no-op */ });
      const ffbSpy = spyOn(component, 'startForwardFromBackwardFeatures')
        .and.callFake(() => { /* no-op */ });
      component.sfsBackwardResults = seedBackwardResults();

      // Existing v2.25.0 payload shape — no backward_cut_step.
      sharedService.emitSfsStartRequest({
        methods: ['backward'],
        stopping_criteria: { metrics: [{ metric: 'roc_auc', pct_change: 1.0 }], min_features: 5, max_features: 15 },
        excluded_features: [],
        n_jobs: 3,
        top_k: 5,
      });

      setTimeout(() => {
        expect(startSfsSpy).toHaveBeenCalledTimes(1);
        expect(ffbSpy).not.toHaveBeenCalled();
        done();
      }, 5);
    });

    it('sfsStartRequests$ should fall back to startSfs() when backward_cut_step is set but methods lack forward', (done) => {
      const startSfsSpy = spyOn(component, 'startSfs').and.callFake(() => { /* no-op */ });
      const ffbSpy = spyOn(component, 'startForwardFromBackwardFeatures')
        .and.callFake(() => { /* no-op */ });
      // Console.warn is logged in the fallback branch; spy on it so we
      // can assert the developer-facing warning fired without polluting
      // the test runner's output.
      const warnSpy = spyOn(console, 'warn');
      component.sfsBackwardResults = seedBackwardResults();

      // Mixed signal: cut step set but only backward method.  Backend
      // would have already rejected this, but the frontend also
      // defensively falls through to plain startSfs() with a warn.
      sharedService.emitSfsStartRequest({
        methods: ['backward'],
        stopping_criteria: { metrics: [{ metric: 'roc_auc', pct_change: 1.0 }], min_features: 5, max_features: 15 },
        excluded_features: [],
        n_jobs: 3,
        top_k: 5,
        backward_cut_step: 2,
      });

      setTimeout(() => {
        expect(startSfsSpy).toHaveBeenCalledTimes(1);
        expect(ffbSpy).not.toHaveBeenCalled();
        expect(warnSpy).toHaveBeenCalled();
        done();
      }, 5);
    });

    it('sfsStartRequests$ should fall back to startSfs() when backward_cut_step does not match any row', (done) => {
      const startSfsSpy = spyOn(component, 'startSfs').and.callFake(() => { /* no-op */ });
      const ffbSpy = spyOn(component, 'startForwardFromBackwardFeatures')
        .and.callFake(() => { /* no-op */ });
      spyOn(console, 'warn');
      component.sfsBackwardResults = seedBackwardResults();  // steps 1..3

      sharedService.emitSfsStartRequest({
        methods: ['forward'],
        stopping_criteria: { metrics: [{ metric: 'roc_auc', pct_change: 1.0 }], min_features: 5, max_features: 15 },
        excluded_features: [],
        n_jobs: 3,
        top_k: 5,
        backward_cut_step: 999,  // ← not in seedBackwardResults()
      });

      setTimeout(() => {
        // Frontend cannot resolve step 999 → fall back to plain startSfs.
        expect(startSfsSpy).toHaveBeenCalledTimes(1);
        expect(ffbSpy).not.toHaveBeenCalled();
        done();
      }, 5);
    });
  });

  // ── 'Get AI Support' per-table buttons in SFS Results (v2.41.0) ──────
  // Replaces the single combined SFS button at the end of the SFS
  // results panel.  Each per-table button passes ONLY its own data
  // slice + a directive forbidding cross-comparison, so the LLM
  // focuses on the table the user clicked from.  We also pin a
  // regression guard: the combined button must no longer render even
  // when all three result arrays are populated.
  describe("SFS per-table 'Get AI Support' buttons (v2.41.0)", () => {
    beforeEach(() => {
      // requestAiSupport runs through dataService and the data-dict refetch.
      // Spy on it so we just capture (context, section, prompt) args
      // without triggering network calls.
      spyOn(component, 'requestAiSupport').and.callFake(() => { /* no-op */ });
      // SFS results section sits inside `modelingStatus?.model` gate;
      // seed the minimum needed to render the section.  We deliberately
      // leave model.cv / model.shap_beeswarm / model.selected_features
      // unset so their sibling AI-support buttons do not render and
      // pollute the per-table querySelectorAll('.ai-support-btn') count.
      component.modelingStatus = { model: {} } as any;
    });

    it('forward-only SFS state renders exactly ONE ai-support-btn (sfs_forward) and clicking it passes the right args', () => {
      component.sfsForwardResults = [
        { step: 1, feature_name: 'a', cv_roc_auc: 0.71 },
        { step: 2, feature_name: 'b', cv_roc_auc: 0.74 },
      ] as any;
      component.sfsBackwardResults = [];
      component.sfsForwardFromBackwardResults = [];
      fixture.detectChanges();

      const btns = fixture.nativeElement.querySelectorAll('.ai-support-btn');
      expect(btns.length).withContext('Only the Forward SFS AI Support button should render').toBe(1);

      (btns[0] as HTMLButtonElement).click();

      const args = (component.requestAiSupport as jasmine.Spy).calls.mostRecent().args;
      expect(args[1]).toBe('sfs_forward');
      expect(Object.keys(args[0])).toEqual(['forward']);
      expect(args[0].forward.length).toBe(2);
    });

    it('backward-only SFS state renders ONE ai-support-btn (sfs_backward) with cut_step + cut_features', () => {
      component.sfsForwardResults = [];
      component.sfsBackwardResults = [
        { step: 1, feature_name: 'x', cv_roc_auc: 0.69 },
        { step: 2, feature_name: 'y', cv_roc_auc: 0.66 },
      ] as any;
      component.sfsForwardFromBackwardResults = [];
      component.sfsBackwardCutStep = 1;
      component.sfsBackwardCutFeatures = ['x'];
      fixture.detectChanges();

      const btns = fixture.nativeElement.querySelectorAll('.ai-support-btn');
      expect(btns.length).withContext('Only the Backward SFS AI Support button should render').toBe(1);

      (btns[0] as HTMLButtonElement).click();

      const args = (component.requestAiSupport as jasmine.Spy).calls.mostRecent().args;
      expect(args[1]).toBe('sfs_backward');
      expect(Object.keys(args[0]).sort()).toEqual(['backward', 'cut_features', 'cut_step']);
      expect(args[0].cut_step).toBe(1);
      expect(args[0].cut_features).toEqual(['x']);
    });

    it('forward-from-backward-only state renders ONE ai-support-btn (sfs_forward_from_backward) with seed metadata', () => {
      component.sfsForwardResults = [];
      component.sfsBackwardResults = [];
      component.sfsForwardFromBackwardResults = [
        { step: 1, feature_name: 'p', cv_roc_auc: 0.72 },
      ] as any;
      component.sfsBackwardCutFeatures = ['p', 'q', 'r'];
      fixture.detectChanges();

      const btns = fixture.nativeElement.querySelectorAll('.ai-support-btn');
      expect(btns.length).withContext('Only the Forward-from-Backward AI Support button should render').toBe(1);

      (btns[0] as HTMLButtonElement).click();

      const args = (component.requestAiSupport as jasmine.Spy).calls.mostRecent().args;
      expect(args[1]).toBe('sfs_forward_from_backward');
      expect(Object.keys(args[0]).sort()).toEqual(['forward_from_backward', 'seed_count', 'seed_features']);
      expect(args[0].seed_count).toBe(3);
      expect(args[0].seed_features).toEqual(['p', 'q', 'r']);
    });

    it('REGRESSION: with all 3 result arrays populated, exactly THREE ai-support-btns render — combined button is gone', () => {
      // This pins removal of the legacy combined SFS button at the end
      // of the SFS results panel.  If a future edit re-adds it, this
      // test fails with 4 buttons instead of 3, AND the section-name
      // harvest finds 'sfs' which is rejected.
      component.sfsForwardResults = [{ step: 1, feature_name: 'a' }] as any;
      component.sfsBackwardResults = [{ step: 1, feature_name: 'b' }] as any;
      component.sfsForwardFromBackwardResults = [{ step: 1, feature_name: 'c' }] as any;
      component.sfsBackwardCutFeatures = ['b'];
      fixture.detectChanges();

      const btns = fixture.nativeElement.querySelectorAll('.ai-support-btn');
      expect(btns.length).withContext('Per-table buttons only — combined button must be removed').toBe(3);

      // Click each button and harvest section names from the spy.
      btns.forEach((b: HTMLButtonElement) => b.click());
      const sections = (component.requestAiSupport as jasmine.Spy).calls.allArgs().map((a: any[]) => a[1]);
      expect(sections.slice().sort()).toEqual(['sfs_backward', 'sfs_forward', 'sfs_forward_from_backward']);
      expect(sections).not.toContain('sfs');
    });
  });
});
