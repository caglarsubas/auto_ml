import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { FormsModule } from '@angular/forms';
import { CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { of } from 'rxjs';
import { AiChatPanelComponent } from './ai-chat-panel.component';
import { AiAssistantService } from '../services/ai-assistant.service';
import { DataService } from '../services/data.service';
import { SharedService } from '../services/shared.service';

describe('AiChatPanelComponent', () => {
  let component: AiChatPanelComponent;
  let fixture: ComponentFixture<AiChatPanelComponent>;
  let aiService: AiAssistantService;
  let sharedService: SharedService;
  let dataService: DataService;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HttpClientTestingModule, FormsModule],
      declarations: [AiChatPanelComponent],
      providers: [AiAssistantService, DataService, SharedService],
      schemas: [CUSTOM_ELEMENTS_SCHEMA],
    }).compileComponents();

    fixture = TestBed.createComponent(AiChatPanelComponent);
    component = fixture.componentInstance;
    aiService = TestBed.inject(AiAssistantService);
    sharedService = TestBed.inject(SharedService);
    dataService = TestBed.inject(DataService);
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should start with empty messages', () => {
    expect(component.messages).toEqual([]);
  });

  it('should start with empty userInput', () => {
    expect(component.userInput).toBe('');
  });

  it('should start with isLoading false', () => {
    expect(component.isLoading).toBeFalse();
  });

  it('should sync messages from AiAssistantService on init', () => {
    aiService.addMessage({ role: 'user', content: 'Test', timestamp: new Date() });
    fixture.detectChanges();
    expect(component.messages.length).toBe(1);
    expect(component.messages[0].content).toBe('Test');
  });

  it('should reflect panel open state from service', () => {
    expect(aiService.isPanelOpen()).toBeFalse();
    aiService.openPanel();
    expect(aiService.isPanelOpen()).toBeTrue();
  });

  // ── update_metadata response handling (v2.23.0+) ──────────────────────
  // The AI assistant's update_metadata action returns an `applied` array
  // describing the LoM/description changes it made.  The chat panel must
  // (a) NOT trigger a backend dictionary refetch — that endpoint
  //     recomputes from the raw file and would silently overwrite the
  //     change the AI just made,
  // (b) broadcast the array on metadataUpdates$ so every interested
  //     component (declaration table, encoding plan dropdown) patches
  //     in place,
  // (c) patch the SharedService dataDictionaryCache snapshot so any
  //     downstream consumer reading via getDataDictionaryCache() sees
  //     the new state immediately,
  // (d) re-push the patched dictionary to the AI Redis cache so the
  //     assistant's NEXT tool call sees the same state on screen.
  describe('_handleActionResult update_metadata flow', () => {
    beforeEach(() => {
      // Seed the shared dictionary cache with the same shape the
      // declaration step pushes after fetching the dictionary.
      sharedService.setDataDictionaryCache([
        { Feature_Name: 'Var_2', Level_of_Measurement: 'nominal', Feature_Description: 'A' },
        { Feature_Name: 'Var_36', Level_of_Measurement: 'nominal', Feature_Description: 'B' },
      ]);
      sharedService.setCurrentFileId(481);
    });

    it('should NOT call triggerDataRefresh() (would wipe the AI change)', () => {
      const refreshSpy = spyOn(sharedService, 'triggerDataRefresh');
      // Reach into the private handler with bracket notation.
      (component as any)._handleActionResult('update_metadata', {
        applied: [{ column: 'Var_2', field: 'Level_of_Measurement', value: 'ordinal' }],
        errors: [],
      });
      expect(refreshSpy).not.toHaveBeenCalled();
    });

    it('should emit applied updates on metadataUpdates$', (done) => {
      const applied = [
        { column: 'Var_2', field: 'Level_of_Measurement', value: 'ordinal' },
        { column: 'Var_36', field: 'Level_of_Measurement', value: 'ordinal' },
      ];
      sharedService.metadataUpdates$.subscribe(received => {
        expect(received).toEqual(applied);
        done();
      });
      // Stub the AI cache push so the http call doesn't escape the test.
      spyOn(dataService, 'pushAiCache').and.returnValue(of({ status: 'success' }));
      (component as any)._handleActionResult('update_metadata', { applied, errors: [] });
    });

    it('should patch dataDictionaryCache snapshot in place', () => {
      spyOn(dataService, 'pushAiCache').and.returnValue(of({ status: 'success' }));
      (component as any)._handleActionResult('update_metadata', {
        applied: [{ column: 'Var_2', field: 'Level_of_Measurement', value: 'ordinal' }],
        errors: [],
      });
      const cache = sharedService.getDataDictionaryCache();
      const var2 = cache.find((d: any) => d.Feature_Name === 'Var_2');
      expect(var2.Level_of_Measurement).toBe('ordinal');
      // Untouched feature should keep its original value.
      const var36 = cache.find((d: any) => d.Feature_Name === 'Var_36');
      expect(var36.Level_of_Measurement).toBe('nominal');
    });

    it('should re-push the patched dictionary to the AI Redis cache', () => {
      const pushSpy = spyOn(dataService, 'pushAiCache').and.returnValue(of({ status: 'success' }));
      (component as any)._handleActionResult('update_metadata', {
        applied: [{ column: 'Var_2', field: 'Level_of_Measurement', value: 'ordinal' }],
        errors: [],
      });
      expect(pushSpy).toHaveBeenCalledTimes(1);
      const [pushedFileId, pushedArtifacts] = pushSpy.calls.mostRecent().args;
      expect(pushedFileId).toBe(481);
      expect(pushedArtifacts['data_dictionary']).toBeDefined();
      const var2 = pushedArtifacts['data_dictionary'].find((d: any) => d.Feature_Name === 'Var_2');
      expect(var2.Level_of_Measurement).toBe('ordinal');
    });

    it('should still broadcast updates when the dictionary cache is empty (late-mount safety)', (done) => {
      // No cache yet — chat panel can run before the declaration step
      // has populated the cache, in which case in-place patching is a
      // no-op but the broadcast must still fan out.
      sharedService.setDataDictionaryCache([]);
      const pushSpy = spyOn(dataService, 'pushAiCache').and.returnValue(of({ status: 'success' }));
      const applied = [{ column: 'Var_2', field: 'Level_of_Measurement', value: 'ordinal' }];
      sharedService.metadataUpdates$.subscribe(received => {
        expect(received).toEqual(applied);
        // No cache present means no Redis re-push (we don't want to
        // invent an empty dictionary for the assistant to see).
        expect(pushSpy).not.toHaveBeenCalled();
        done();
      });
      (component as any)._handleActionResult('update_metadata', { applied, errors: [] });
    });

    it('should not broadcast or push when applied is empty (e.g. all errors)', () => {
      const emitSpy = spyOn(sharedService, 'emitMetadataUpdates');
      const pushSpy = spyOn(dataService, 'pushAiCache').and.returnValue(of({ status: 'success' }));
      (component as any)._handleActionResult('update_metadata', {
        applied: [],
        errors: [{ column: 'Var_2', error: 'unknown column' }],
      });
      expect(emitSpy).not.toHaveBeenCalled();
      expect(pushSpy).not.toHaveBeenCalled();
    });

    it('should ignore updates whose column is not in the cache', () => {
      spyOn(dataService, 'pushAiCache').and.returnValue(of({ status: 'success' }));
      (component as any)._handleActionResult('update_metadata', {
        applied: [{ column: 'Nonexistent_Column', field: 'Level_of_Measurement', value: 'ordinal' }],
        errors: [],
      });
      const cache = sharedService.getDataDictionaryCache();
      // Original entries preserved unchanged.
      expect(cache.length).toBe(2);
      expect(cache[0].Level_of_Measurement).toBe('nominal');
      expect(cache[1].Level_of_Measurement).toBe('nominal');
    });
  });

  // ── set_ordinal_ranking response handling (v2.24.0+) ──────────────────
  // The procedural follow-through path after `update_metadata` sets a
  // feature's LoM to ordinal.  The action handler must:
  //   (a) broadcast the applied rankings on encodingRankingUpdates$ so
  //       the modeling component patches encodingPlan[i].ranking,
  //   (b) NOT re-push to AI Redis (the backend action_executor already
  //       wrote through to the cached encoding_plan artifact),
  //   (c) NOT call triggerDataRefresh (would wipe state).
  describe('_handleActionResult set_ordinal_ranking flow', () => {
    it('should broadcast applied rankings on encodingRankingUpdates$', (done) => {
      const applied = [
        { column: 'Var_36', ranking: ['0', '1', '2', '3', '8', 'L', 'Others'] },
        { column: 'Var_2', ranking: ['A', 'P', 'R'] },
      ];
      sharedService.encodingRankingUpdates$.subscribe(received => {
        expect(received).toEqual(applied);
        done();
      });
      (component as any)._handleActionResult('set_ordinal_ranking', {
        applied,
        errors: [],
      });
    });

    it('should NOT re-push to AI Redis (backend already wrote through)', () => {
      const pushSpy = spyOn(dataService, 'pushAiCache').and.returnValue(of({ status: 'success' }));
      (component as any)._handleActionResult('set_ordinal_ranking', {
        applied: [{ column: 'Var_36', ranking: ['Low', 'Mid', 'High'] }],
        errors: [],
      });
      expect(pushSpy).not.toHaveBeenCalled();
    });

    it('should NOT call triggerDataRefresh', () => {
      const refreshSpy = spyOn(sharedService, 'triggerDataRefresh');
      (component as any)._handleActionResult('set_ordinal_ranking', {
        applied: [{ column: 'Var_36', ranking: ['Low', 'Mid', 'High'] }],
        errors: [],
      });
      expect(refreshSpy).not.toHaveBeenCalled();
    });

    it('should trigger a checkpoint with ai_action_set_ordinal_ranking substep', () => {
      const cpSpy = spyOn(sharedService, 'triggerCheckpoint');
      (component as any)._handleActionResult('set_ordinal_ranking', {
        applied: [{ column: 'Var_36', ranking: ['Low', 'Mid', 'High'] }],
        errors: [],
      });
      expect(cpSpy).toHaveBeenCalledWith('ai_action_set_ordinal_ranking');
    });

    it('should not broadcast when applied is empty', () => {
      const emitSpy = spyOn(sharedService, 'emitEncodingRankingUpdates');
      (component as any)._handleActionResult('set_ordinal_ranking', {
        applied: [],
        errors: [{ column: 'Var_X', error: 'duplicates' }],
      });
      expect(emitSpy).not.toHaveBeenCalled();
    });

    it('should add a chat message summarising the ranking with arrow notation', () => {
      // Defensive check that the user-visible message renders the
      // ranking with ' → ' separators — easier for the user to read
      // than a comma list and matches how the backend renders it back
      // to the AI on get_encoding_plan.
      (component as any)._handleActionResult('set_ordinal_ranking', {
        applied: [{ column: 'Var_36', ranking: ['Low', 'Mid', 'High'] }],
        errors: [],
      });
      const lastMsg = aiService.getMessages().slice(-1)[0];
      expect(lastMsg.content).toContain('Var_36');
      expect(lastMsg.content).toContain('Low → Mid → High');
    });
  });

  // ── update_config feature_usage (v2.25.0+) ────────────────────────────
  // The AI's correct path to "exclude Var_3 from SFS due to VIF" — the
  // chat panel must route feature_usage entries through featureUsageUpdates$
  // (NOT setModelUsageSettings — that's for the data-quality model_usage flag).
  describe('_applyConfigChanges feature_usage flow', () => {
    it('should broadcast feature_usage entries on featureUsageUpdates$', (done) => {
      const applied = [
        { key: 'feature_usage', column: 'Var_3', value: 'drop', reason: 'VIF=9.39' },
      ];
      sharedService.featureUsageUpdates$.subscribe(received => {
        expect(received).toEqual([
          { column: 'Var_3', value: 'drop', reason: 'VIF=9.39' },
        ]);
        done();
      });
      (component as any)._handleActionResult('update_config', { applied, errors: [] });
    });

    it('should batch multiple feature_usage entries into a single broadcast', (done) => {
      const applied = [
        { key: 'feature_usage', column: 'Var_3', value: 'drop', reason: 'VIF=9.39' },
        { key: 'feature_usage', column: 'Var_25', value: 'drop', reason: 'Low SHAP' },
        { key: 'feature_usage', column: 'Var_24', value: 'keep' },
      ];
      sharedService.featureUsageUpdates$.subscribe(received => {
        expect(received.length).toBe(3);
        expect(received[0]).toEqual({ column: 'Var_3', value: 'drop', reason: 'VIF=9.39' });
        expect(received[1]).toEqual({ column: 'Var_25', value: 'drop', reason: 'Low SHAP' });
        // No reason field on "keep" entries — matches the manual UI's
        // clear-on-flip-back behaviour.
        expect(received[2]).toEqual({ column: 'Var_24', value: 'keep' });
        done();
      });
      (component as any)._handleActionResult('update_config', { applied, errors: [] });
    });

    it('should ignore feature_usage entries with invalid value (no broadcast)', () => {
      const emitSpy = spyOn(sharedService, 'emitFeatureUsageUpdates');
      (component as any)._handleActionResult('update_config', {
        applied: [
          { key: 'feature_usage', column: 'Var_3', value: 'remove' },  // not keep/drop
          { key: 'feature_usage', value: 'drop' },                      // no column
        ],
        errors: [],
      });
      expect(emitSpy).not.toHaveBeenCalled();
    });

    it('should keep model_usage flow working alongside feature_usage', () => {
      // Mixed batch — model_usage goes through setModelUsageSettings,
      // feature_usage through emitFeatureUsageUpdates.  Neither breaks
      // the other.
      const modelSpy = spyOn(sharedService, 'setModelUsageSettings').and.callThrough();
      const featSpy = spyOn(sharedService, 'emitFeatureUsageUpdates');
      (component as any)._handleActionResult('update_config', {
        applied: [
          { key: 'feature_usage', column: 'Var_3', value: 'drop' },
          { key: 'model_usage', column: 'AppID', value: 'No' },
        ],
        errors: [],
      });
      expect(modelSpy).toHaveBeenCalled();
      expect(featSpy).toHaveBeenCalledTimes(1);
      expect(featSpy.calls.mostRecent().args[0]).toEqual([
        { column: 'Var_3', value: 'drop' },
      ]);
    });
  });

  // ── start_sfs response handling (v2.25.0+) ────────────────────────────
  // The dedicated path for the AI to actually kick off SFS.  The chat
  // panel forwards the validated config object on sfsStartRequests$
  // so the modeling component populates form fields and calls startSfs().
  describe('_handleActionResult start_sfs flow', () => {
    const validApplied = {
      methods: ['backward'],
      stopping_criteria: {
        metrics: [{ metric: 'roc_auc', pct_change: 1.0 }],
        min_features: 5,
        max_features: 15,
      },
      excluded_features: ['Var_3'],
      n_jobs: 3,
      top_k: 5,
    };

    it('should broadcast the validated config on sfsStartRequests$', (done) => {
      sharedService.sfsStartRequests$.subscribe(received => {
        expect(received).toEqual(validApplied);
        done();
      });
      (component as any)._handleActionResult('start_sfs', {
        applied: validApplied,
        description: 'Start backward SFS, excluding Var_3 (VIF=9.39)',
      });
    });

    it('should NOT broadcast when applied is missing', () => {
      const emitSpy = spyOn(sharedService, 'emitSfsStartRequest');
      (component as any)._handleActionResult('start_sfs', { description: 'malformed' });
      expect(emitSpy).not.toHaveBeenCalled();
    });

    it('should add a chat message summarising the SFS config', () => {
      (component as any)._handleActionResult('start_sfs', {
        applied: validApplied,
        description: 'Start backward SFS, excluding Var_3 (VIF=9.39)',
      });
      const lastMsg = aiService.getMessages().slice(-1)[0];
      // Methods rendered.
      expect(lastMsg.content).toContain('backward');
      // Stopping criteria rendered with metric/threshold.
      expect(lastMsg.content).toContain('roc_auc');
      expect(lastMsg.content).toContain('1');
      // Excluded features rendered with backtick code formatting.
      expect(lastMsg.content).toContain('Var_3');
      // Parallelism rendered.
      expect(lastMsg.content).toContain('n_jobs=3');
      expect(lastMsg.content).toContain('top_k=5');
    });

    it('should trigger ai_action_start_sfs checkpoint substep', () => {
      const cpSpy = spyOn(sharedService, 'triggerCheckpoint');
      (component as any)._handleActionResult('start_sfs', { applied: validApplied });
      expect(cpSpy).toHaveBeenCalledWith('ai_action_start_sfs');
    });

    it('should render "none" when excluded_features is empty', () => {
      (component as any)._handleActionResult('start_sfs', {
        applied: { ...validApplied, excluded_features: [] },
      });
      const lastMsg = aiService.getMessages().slice(-1)[0];
      // Italic-_none_ marker so the user knows nothing was excluded.
      expect(lastMsg.content).toContain('_none_');
    });
  });

  // ── start_data_purifier (v2.26.0+) ────────────────────────────────────
  // AI's `start_data_purifier` action result handler — must broadcast
  // on dataPurifierStartRequests$, render a chat summary, trigger a
  // checkpoint substep.
  describe('_handleActionResult start_data_purifier flow', () => {
    it('should broadcast the validated config on dataPurifierStartRequests$', (done) => {
      const applied = {
        purifier_options: [1, 2, 5, 7],
        split: { strategy: 'random', percent: 25 },
      };
      sharedService.dataPurifierStartRequests$.subscribe(received => {
        expect(received).toEqual({
          purifier_options: [1, 2, 5, 7],
          split: { strategy: 'random', percent: 25 },
        });
        done();
      });
      (component as any)._handleActionResult('start_data_purifier', { applied });
    });

    it('should pass empty options + null split through unchanged', (done) => {
      sharedService.dataPurifierStartRequests$.subscribe(received => {
        expect(received).toEqual({ purifier_options: [], split: null });
        done();
      });
      (component as any)._handleActionResult('start_data_purifier', {
        applied: { purifier_options: [], split: null },
      });
    });

    it('should render a chat summary with purifier options and split', () => {
      (component as any)._handleActionResult('start_data_purifier', {
        applied: {
          purifier_options: [1, 2, 5],
          split: { strategy: 'random', percent: 25 },
        },
        description: 'Run preprocessing with low-variance pruning',
      });
      const lastMsg = aiService.getMessages().slice(-1)[0];
      expect(lastMsg.content).toContain('Data purifier started');
      expect(lastMsg.content).toContain('Run preprocessing with low-variance pruning');
      expect(lastMsg.content).toContain('1');
      expect(lastMsg.content).toContain('random');
      expect(lastMsg.content).toContain('25');
    });

    it('should render OOT split details when strategy=oot', () => {
      (component as any)._handleActionResult('start_data_purifier', {
        applied: {
          purifier_options: [],
          split: { strategy: 'oot', date_column: 'Application_Datetime', percent: 30 },
        },
      });
      const lastMsg = aiService.getMessages().slice(-1)[0];
      expect(lastMsg.content).toContain('OOT');
      expect(lastMsg.content).toContain('Application_Datetime');
      expect(lastMsg.content).toContain('30');
    });

    it('should render "_form defaults_" when split is null', () => {
      (component as any)._handleActionResult('start_data_purifier', {
        applied: { purifier_options: [], split: null },
      });
      const lastMsg = aiService.getMessages().slice(-1)[0];
      expect(lastMsg.content).toContain('_form defaults_');
    });

    it('should trigger ai_action_start_data_purifier checkpoint substep', () => {
      const cpSpy = spyOn(sharedService, 'triggerCheckpoint');
      (component as any)._handleActionResult('start_data_purifier', {
        applied: { purifier_options: [], split: null },
      });
      expect(cpSpy).toHaveBeenCalledWith('ai_action_start_data_purifier');
    });
  });

  // ── apply_encoding (v2.26.0+) ─────────────────────────────────────────
  describe('_handleActionResult apply_encoding flow', () => {
    it('should broadcast the use_native flag on encodingApplyRequests$', (done) => {
      sharedService.encodingApplyRequests$.subscribe(received => {
        expect(received).toEqual({ use_native: true });
        done();
      });
      (component as any)._handleActionResult('apply_encoding', {
        applied: { use_native: true },
      });
    });

    it('should default use_native=true when applied is missing', (done) => {
      sharedService.encodingApplyRequests$.subscribe(received => {
        expect(received).toEqual({ use_native: true });
        done();
      });
      (component as any)._handleActionResult('apply_encoding', {});
    });

    it('should pass explicit false through unchanged', (done) => {
      sharedService.encodingApplyRequests$.subscribe(received => {
        expect(received.use_native).toBeFalse();
        done();
      });
      (component as any)._handleActionResult('apply_encoding', {
        applied: { use_native: false },
      });
    });

    it('should add a chat message summarising the call', () => {
      (component as any)._handleActionResult('apply_encoding', {
        applied: { use_native: true },
        description: 'Apply encoding plan with native library',
      });
      const lastMsg = aiService.getMessages().slice(-1)[0];
      expect(lastMsg.content).toContain('Apply encoding started');
      expect(lastMsg.content).toContain('Apply encoding plan with native library');
      expect(lastMsg.content).toContain('use_native');
    });

    it('should trigger ai_action_apply_encoding checkpoint substep', () => {
      const cpSpy = spyOn(sharedService, 'triggerCheckpoint');
      (component as any)._handleActionResult('apply_encoding', {
        applied: { use_native: true },
      });
      expect(cpSpy).toHaveBeenCalledWith('ai_action_apply_encoding');
    });
  });

  // ── start_modeling (v2.26.0+) ─────────────────────────────────────────
  // The headline action — closes the user's blocker from v2.25.0.
  describe('_handleActionResult start_modeling flow', () => {
    it('should broadcast the validated config on modelingStartRequests$', (done) => {
      const applied = { algorithm: 'lightgbm', encoding_use_native: true };
      sharedService.modelingStartRequests$.subscribe(received => {
        expect(received).toEqual({ algorithm: 'lightgbm', encoding_use_native: true });
        done();
      });
      (component as any)._handleActionResult('start_modeling', { applied });
    });

    it('should normalise null algorithm (form-value fallback)', (done) => {
      sharedService.modelingStartRequests$.subscribe(received => {
        expect(received.algorithm).toBeNull();
        expect(received.encoding_use_native).toBeTrue();
        done();
      });
      (component as any)._handleActionResult('start_modeling', {
        applied: { algorithm: null, encoding_use_native: true },
      });
    });

    it('should default to algorithm=null + use_native=true on missing applied', (done) => {
      sharedService.modelingStartRequests$.subscribe(received => {
        expect(received.algorithm).toBeNull();
        expect(received.encoding_use_native).toBeTrue();
        done();
      });
      (component as any)._handleActionResult('start_modeling', {});
    });

    it('should add a chat summary mentioning algorithm and use_native', () => {
      (component as any)._handleActionResult('start_modeling', {
        applied: { algorithm: 'xgboost', encoding_use_native: false },
        description: 'Start modeling with XGBoost',
      });
      const lastMsg = aiService.getMessages().slice(-1)[0];
      expect(lastMsg.content).toContain('Modeling started');
      expect(lastMsg.content).toContain('Start modeling with XGBoost');
      expect(lastMsg.content).toContain('xgboost');
      expect(lastMsg.content).toContain('use_native');
    });

    it('should render "_form value_" when algorithm is null', () => {
      (component as any)._handleActionResult('start_modeling', {
        applied: { algorithm: null, encoding_use_native: true },
      });
      const lastMsg = aiService.getMessages().slice(-1)[0];
      expect(lastMsg.content).toContain('_form value_');
    });

    it('should trigger ai_action_start_modeling checkpoint substep', () => {
      const cpSpy = spyOn(sharedService, 'triggerCheckpoint');
      (component as any)._handleActionResult('start_modeling', {
        applied: { algorithm: 'lightgbm', encoding_use_native: true },
      });
      expect(cpSpy).toHaveBeenCalledWith('ai_action_start_modeling');
    });
  });

  // ── v2.27.2 — empty-response defensive fallback ───────────────────────
  // The backend now always returns a meaningful `message` even when the
  // LLM produces no content (synthesis pass + actionable fallback in
  // backend/ai_assistant/views.py).  Pre-v2.27.2 the chat panel showed
  // the literal "No response received." which gave the user no next
  // step.  This block pins the new defensive fallback wording so any
  // future revert to the old string trips immediately.
  describe('v2.27.2 empty-response fallback copy', () => {
    it('should expose a public EMPTY_RESPONSE_FALLBACK constant', () => {
      expect(typeof AiChatPanelComponent.EMPTY_RESPONSE_FALLBACK).toBe('string');
      expect(AiChatPanelComponent.EMPTY_RESPONSE_FALLBACK.trim().length).toBeGreaterThan(0);
    });

    it('should NOT use the bare pre-v2.27.2 "No response received." literal', () => {
      // The pre-v2.27.2 string left users with no actionable next step.
      // Pin it gone.
      expect(AiChatPanelComponent.EMPTY_RESPONSE_FALLBACK).not.toBe('No response received.');
      expect(AiChatPanelComponent.EMPTY_RESPONSE_FALLBACK.toLowerCase())
        .not.toContain('no response received');
    });

    it('should mention an actionable next step (rephrasing or backend logs)', () => {
      const copy = AiChatPanelComponent.EMPTY_RESPONSE_FALLBACK.toLowerCase();
      const hasActionableHint =
        copy.includes('rephras') || copy.includes('backend') || copy.includes('try ');
      expect(hasActionableHint).toBeTrue();
    });

    it('should render EMPTY_RESPONSE_FALLBACK when backend returns empty message AND no actions', () => {
      // Stub network calls + service plumbing.
      spyOn(dataService, 'sendAiChat').and.returnValue(of({ message: '', actions: [] }));
      spyOn(dataService, 'getAiModels').and.returnValue(of({ models: [], default: 'gpt-5.5' }));
      sharedService.setCurrentFileId(1);

      // Seed an in-flight assistant message so updateLastMessage has
      // something to update — mirrors the real send-flow which adds an
      // empty assistant placeholder before awaiting the response.
      aiService.addMessage({ role: 'user', content: 'hi', timestamp: new Date() });
      aiService.addMessage({ role: 'assistant', content: '', timestamp: new Date() });

      component.sendMessage('hi');

      const last = aiService.getMessages().slice(-1)[0];
      expect(last.content).toBe(AiChatPanelComponent.EMPTY_RESPONSE_FALLBACK);
    });

    it('should render the action-prepared message (NOT the empty fallback) when actions are present', () => {
      // When the backend returns no message but DOES return actions,
      // the user should see the "I've prepared the following operation"
      // string, not the empty-response fallback.  This is the same
      // branch the existing fallbackMsg ternary covers.
      spyOn(dataService, 'sendAiChat').and.returnValue(of({
        message: '',
        actions: [{ type: 'update_notes', payload: { description: 'note' } }],
      }));
      spyOn(dataService, 'getAiModels').and.returnValue(of({ models: [], default: 'gpt-5.5' }));
      sharedService.setCurrentFileId(1);
      aiService.addMessage({ role: 'user', content: 'add note', timestamp: new Date() });
      aiService.addMessage({ role: 'assistant', content: '', timestamp: new Date() });

      component.sendMessage('add note');

      const last = aiService.getMessages().slice(-1)[0];
      expect(last.content.toLowerCase()).toContain('prepared');
      expect(last.content).not.toBe(AiChatPanelComponent.EMPTY_RESPONSE_FALLBACK);
    });

    it('should pass through the backend message verbatim when present', () => {
      // The fallback only kicks in when `resp.message` is falsy — pin
      // that the happy path is unaffected.
      const realMessage = 'Here is a real assistant reply with content.';
      spyOn(dataService, 'sendAiChat').and.returnValue(of({ message: realMessage, actions: [] }));
      spyOn(dataService, 'getAiModels').and.returnValue(of({ models: [], default: 'gpt-5.5' }));
      sharedService.setCurrentFileId(1);
      aiService.addMessage({ role: 'user', content: 'hi', timestamp: new Date() });
      aiService.addMessage({ role: 'assistant', content: '', timestamp: new Date() });

      component.sendMessage('hi');

      const last = aiService.getMessages().slice(-1)[0];
      expect(last.content).toBe(realMessage);
    });
  });
});
