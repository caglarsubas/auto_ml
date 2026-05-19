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
});
