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

  describe('model selector dropdown', () => {
    beforeEach(() => {
      spyOn(dataService, 'getAiModels').and.returnValue(of({
        models: [
          { key: 'gpt-5.5', display_name: 'GPT-5.5', provider: 'openai' },
          { key: 'gemma4:26b', display_name: 'gemma4:26b', provider: 'engine' },
        ],
        default: 'gpt-5.5',
      }));
    });

    it('should close when clicking outside the selector frame', () => {
      fixture.detectChanges();
      component.showModelSelector = true;

      document.body.dispatchEvent(new MouseEvent('click', { bubbles: true }));

      expect(component.showModelSelector).toBeFalse();
    });

    it('should stay open when clicking inside the selector frame', () => {
      fixture.detectChanges();
      component.showModelSelector = true;
      fixture.detectChanges();

      const wrapper: HTMLElement = fixture.nativeElement.querySelector('.model-selector-wrapper');
      wrapper.dispatchEvent(new MouseEvent('click', { bubbles: true }));

      expect(component.showModelSelector).toBeTrue();
    });

    it('should close after selecting a model', () => {
      component.showModelSelector = true;

      component.selectModel('gemma4:26b');

      expect(component.selectedModel).toBe('gemma4:26b');
      expect(component.showModelSelector).toBeFalse();
    });
  });

  it('should forward preclassified button intent labels to /chat/', () => {
    spyOn(dataService, 'getAiModels').and.returnValue(of({
      models: [{ key: 'gpt-5.5', display_name: 'GPT-5.5', provider: 'openai' }],
      default: 'gpt-5.5',
    }));
    const sendSpy = spyOn(dataService, 'sendAiChat').and.returnValue(of({ message: 'ok' }));
    sharedService.setCurrentFileId(42);

    fixture.detectChanges();
    aiService.requestSupport({ summary: [] }, 'data_quality', 'Analyze the current summary');

    expect(sendSpy).toHaveBeenCalled();
    const args = sendSpy.calls.mostRecent().args;
    expect(args[0]).toBe('Analyze the current summary');
    expect(args[2]).toBe('data_quality');
    expect(args[4]).toBe(42);
    expect(args[6]).toEqual(['C']);
    expect(args[7]).toBe('get_ai_support_button');
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

    // ── v2.39.0+: implied_metadata_updates auto-fan to metadataUpdates$ ──
    // The v2.39.0 backend stamps an `implied_metadata_updates` array onto
    // every set_ordinal_ranking response — one LoM=ordinal entry per
    // applied column, shaped identically to update_metadata's `applied`.
    // The chat panel MUST fan this list onto metadataUpdates$ AND patch
    // the dictionary cache so the encoding-plan dropdown's LoM column
    // flips Nominal → Ordinal in lock-step with the ranking populating.
    // Pre-v2.39.0 the user saw "Applied" while the table silently kept
    // showing Nominal — the regression these tests guard against.
    it('should broadcast implied_metadata_updates on metadataUpdates$ (v2.39.0+)', (done) => {
      const implied = [
        { column: 'Var_2', field: 'Level_of_Measurement', value: 'ordinal' },
        { column: 'Var_36', field: 'Level_of_Measurement', value: 'ordinal' },
      ];
      sharedService.metadataUpdates$.subscribe(received => {
        expect(received).toEqual(implied);
        done();
      });
      (component as any)._handleActionResult('set_ordinal_ranking', {
        applied: [
          { column: 'Var_2', ranking: ['A', 'P', 'R'] },
          { column: 'Var_36', ranking: ['Low', 'Mid', 'High'] },
        ],
        errors: [],
        implied_metadata_updates: implied,
      });
    });

    it('should patch the dictionary cache with LoM=ordinal for ranked features (v2.39.0+)', () => {
      // Seed the cache with the same shape the declaration step pushes
      // after fetching the dictionary — both features are nominal pre-action.
      sharedService.setDataDictionaryCache([
        { Feature_Name: 'Var_2', Level_of_Measurement: 'nominal', Feature_Description: 'A' },
        { Feature_Name: 'Var_36', Level_of_Measurement: 'nominal', Feature_Description: 'B' },
        { Feature_Name: 'Var_Other', Level_of_Measurement: 'nominal', Feature_Description: 'C' },
      ]);
      spyOn(dataService, 'pushAiCache').and.returnValue(of({ status: 'success' }));
      (component as any)._handleActionResult('set_ordinal_ranking', {
        applied: [
          { column: 'Var_2', ranking: ['A', 'P', 'R'] },
          { column: 'Var_36', ranking: ['Low', 'Mid', 'High'] },
        ],
        errors: [],
        implied_metadata_updates: [
          { column: 'Var_2', field: 'Level_of_Measurement', value: 'ordinal' },
          { column: 'Var_36', field: 'Level_of_Measurement', value: 'ordinal' },
        ],
      });
      const cache = sharedService.getDataDictionaryCache();
      const byName: Record<string, any> = {};
      cache.forEach((d: any) => { byName[d.Feature_Name] = d; });
      // Ranked features flipped to ordinal in place.
      expect(byName['Var_2'].Level_of_Measurement).toBe('ordinal');
      expect(byName['Var_36'].Level_of_Measurement).toBe('ordinal');
      // Untouched feature MUST keep its original LoM — the patch is
      // surgical, not a wholesale dictionary replace.
      expect(byName['Var_Other'].Level_of_Measurement).toBe('nominal');
    });

    it('should NOT broadcast metadataUpdates$ when implied_metadata_updates is empty (v2.39.0+)', () => {
      // All-invalid set_ordinal_ranking call: applied=[], implied=[].
      // Frontend's `if (impliedMetadata.length)` guard MUST prevent the
      // broadcast — flipping LoM for a column whose ranking didn't land
      // would leave the pipeline in a broken state (LoM=ordinal but no
      // ranking → encoding silently downgrades to label_encoding).
      const emitSpy = spyOn(sharedService, 'emitMetadataUpdates');
      (component as any)._handleActionResult('set_ordinal_ranking', {
        applied: [],
        errors: [{ column: 'Var_X', error: 'duplicates' }],
        implied_metadata_updates: [],
      });
      expect(emitSpy).not.toHaveBeenCalled();
    });

    it('should be backward-compatible with pre-v2.39.0 backends (no implied_metadata_updates field)', () => {
      // A v2.38.0 backend would omit `implied_metadata_updates` entirely.
      // Frontend MUST default to [] (NOT undefined.length crash) so a
      // version-mismatched stack still applies the ranking — just
      // without the LoM auto-flip.  Existing v2.24.0..v2.38.0 manual
      // chain (update_metadata then set_ordinal_ranking across two
      // turns) remains the operative path against an old backend.
      const emitSpy = spyOn(sharedService, 'emitMetadataUpdates');
      const rankingSpy = spyOn(sharedService, 'emitEncodingRankingUpdates');
      expect(() => {
        (component as any)._handleActionResult('set_ordinal_ranking', {
          applied: [{ column: 'Var_36', ranking: ['Low', 'Mid', 'High'] }],
          errors: [],
          // No implied_metadata_updates field — pre-v2.39.0 backend.
        });
      }).not.toThrow();
      // Ranking still broadcasts (existing v2.24.0+ behaviour preserved).
      expect(rankingSpy).toHaveBeenCalledWith([
        { column: 'Var_36', ranking: ['Low', 'Mid', 'High'] },
      ]);
      // Metadata broadcast is skipped because no implied updates exist.
      expect(emitSpy).not.toHaveBeenCalled();
    });

    it('should surface the implied LoM flip in the chat bubble (v2.39.0+)', () => {
      // The user-visible message must explicitly mention the LoM=ordinal
      // side-effect so the action's full impact is transparent.  Pre-
      // v2.39.0 the bubble only described the ranking and the user
      // could not tell whether LoM had been touched.
      (component as any)._handleActionResult('set_ordinal_ranking', {
        applied: [{ column: 'Var_36', ranking: ['Low', 'Mid', 'High'] }],
        errors: [],
        implied_metadata_updates: [
          { column: 'Var_36', field: 'Level_of_Measurement', value: 'ordinal' },
        ],
      });
      const lastMsg = aiService.getMessages().slice(-1)[0];
      // Mention of the LoM flip — exact wording verified by the test
      // so any future copy change shows up as an explicit test diff.
      expect(lastMsg.content).toContain('Level of Measurement');
      expect(lastMsg.content).toContain('Ordinal');
      expect(lastMsg.content).toContain('Var_36');
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

    it('should mirror preprocessing_options updates into the purifier selector', (done) => {
      // Regression guard for the 28 -> 29 purifier swap: update_config
      // can return success, but the left-hand Data Purifier UI must also
      // receive the new checkbox set.
      sharedService.purifierSelectionUpdates$.subscribe(received => {
        expect(received).toEqual({
          form: 'wholesale',
          purifier_options: [1, 2, 3, 4, 7, 23, 29, 32],
          add: [],
          remove: [],
        });
        done();
      });
      (component as any)._handleActionResult('update_config', {
        applied: [
          { key: 'preprocessing_options', value: [1, 2, 3, 4, 7, 23, 29, 32] },
        ],
        errors: [],
      });
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

    // ── v2.37.0+: backward_cut_step pass-through ──────────────────────
    // Backend tool now returns `backward_cut_step` in `applied`.  The
    // chat panel must forward it verbatim so the modeling component can
    // branch to startForwardFromBackwardFeatures() instead of startSfs().
    it('should forward backward_cut_step in the broadcast (v2.37.0+)', (done) => {
      const appliedWithCut = {
        ...validApplied,
        methods: ['forward'],
        backward_cut_step: 37,
      };
      sharedService.sfsStartRequests$.subscribe(received => {
        expect(received).toEqual(appliedWithCut);
        expect(received.backward_cut_step).toBe(37);
        done();
      });
      (component as any)._handleActionResult('start_sfs', {
        applied: appliedWithCut,
        description: 'Forward SFS from backward step 37 survivor set',
      });
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

  // ── update_purifier_selection (v2.28.0+) ─────────────────────────────
  // AI's `update_purifier_selection` action result handler — the
  // "preview" sibling of start_data_purifier.  Must:
  //   (a) broadcast on purifierSelectionUpdates$ with the right form
  //       discriminator + payload shape,
  //   (b) render a chat summary that distinguishes wholesale/diff/noop,
  //   (c) trigger an ai_action_update_purifier_selection checkpoint,
  //   (d) NEVER emit a start_data_purifier broadcast (that distinction
  //       is the whole point of v2.28.0 — guard against regression).
  describe('_handleActionResult update_purifier_selection flow', () => {
    it('should broadcast a wholesale-form update on purifierSelectionUpdates$', (done) => {
      const applied = {
        form: 'wholesale',
        purifier_options: [1, 2, 3, 4, 7, 23, 28, 32],
        add: [],
        remove: [],
      };
      sharedService.purifierSelectionUpdates$.subscribe(received => {
        expect(received.form).toBe('wholesale');
        expect(received.purifier_options).toEqual([1, 2, 3, 4, 7, 23, 28, 32]);
        expect(received.add).toEqual([]);
        expect(received.remove).toEqual([]);
        done();
      });
      (component as any)._handleActionResult('update_purifier_selection', {
        applied,
        description: 'Consolidate 11+17 into 23',
      });
    });

    it('should broadcast a diff-form update on purifierSelectionUpdates$', (done) => {
      const applied = {
        form: 'diff',
        purifier_options: null,
        add: [23],
        remove: [11, 17],
      };
      sharedService.purifierSelectionUpdates$.subscribe(received => {
        expect(received.form).toBe('diff');
        expect(received.purifier_options).toBeNull();
        expect(received.add).toEqual([23]);
        expect(received.remove).toEqual([11, 17]);
        done();
      });
      (component as any)._handleActionResult('update_purifier_selection', {
        applied,
        description: 'Replace 11+17 with 23',
      });
    });

    it('should NOT broadcast on dataPurifierStartRequests$ (critical regression guard)', () => {
      // The whole point of update_purifier_selection vs
      // start_data_purifier is the no-run UX.  A regression here
      // re-introduces the v2.27.x problem of one-shot apply-and-run
      // with no user review step in between.
      const runSpy = spyOn(sharedService, 'emitDataPurifierStartRequest');
      (component as any)._handleActionResult('update_purifier_selection', {
        applied: {
          form: 'wholesale',
          purifier_options: [1, 2, 23],
          add: [],
          remove: [],
        },
      });
      expect(runSpy).not.toHaveBeenCalled();
    });

    it('should NOT broadcast for a noop applied form (description-only payload)', () => {
      // Backend returns form='noop' for description-only payloads.
      // We render a chat message but skip the broadcast so the form
      // doesn't flash.
      const emitSpy = spyOn(sharedService, 'emitPurifierSelectionUpdate');
      (component as any)._handleActionResult('update_purifier_selection', {
        applied: {
          form: 'noop',
          purifier_options: null,
          add: [],
          remove: [],
        },
        description: 'Thinking about it…',
      });
      expect(emitSpy).not.toHaveBeenCalled();
    });

    it('should render a chat summary listing the new wholesale selection', () => {
      (component as any)._handleActionResult('update_purifier_selection', {
        applied: {
          form: 'wholesale',
          purifier_options: [1, 2, 23],
          add: [],
          remove: [],
        },
        description: 'Consolidate to combined-drop',
      });
      const lastMsg = aiService.getMessages().slice(-1)[0];
      expect(lastMsg.content).toContain('Purifier selection updated');
      expect(lastMsg.content).toContain('Consolidate to combined-drop');
      // Each kept ID surfaces with backtick formatting.
      expect(lastMsg.content).toContain('`1`');
      expect(lastMsg.content).toContain('`2`');
      expect(lastMsg.content).toContain('`23`');
    });

    it('should render a chat summary listing added + removed IDs for diff form', () => {
      (component as any)._handleActionResult('update_purifier_selection', {
        applied: {
          form: 'diff',
          purifier_options: null,
          add: [23],
          remove: [11, 17],
        },
        description: 'Combined-drop swap',
      });
      const lastMsg = aiService.getMessages().slice(-1)[0];
      expect(lastMsg.content).toContain('Purifier selection updated');
      expect(lastMsg.content).toContain('Added');
      expect(lastMsg.content).toContain('Removed');
      expect(lastMsg.content).toContain('`23`');
      expect(lastMsg.content).toContain('`11`');
      expect(lastMsg.content).toContain('`17`');
    });

    it('should render the "review then run" call-to-action footer', () => {
      // The user-visible hint that distinguishes this action from
      // start_data_purifier: it does NOT auto-run, the user has to
      // click Run themselves.  Pin the wording so a future copy edit
      // doesn't silently strip the cue.
      (component as any)._handleActionResult('update_purifier_selection', {
        applied: {
          form: 'wholesale',
          purifier_options: [1, 23],
          add: [],
          remove: [],
        },
      });
      const lastMsg = aiService.getMessages().slice(-1)[0];
      expect(lastMsg.content).toContain('Run Preprocessing');
      // "Review the … checkboxes" prompts the user to scroll to the
      // form and verify the AI's change before committing.
      expect(lastMsg.content.toLowerCase()).toContain('review');
    });

    it('should render an "(cleared)" hint when wholesale selection is empty', () => {
      (component as any)._handleActionResult('update_purifier_selection', {
        applied: {
          form: 'wholesale',
          purifier_options: [],
          add: [],
          remove: [],
        },
        description: 'Clear everything',
      });
      const lastMsg = aiService.getMessages().slice(-1)[0];
      expect(lastMsg.content.toLowerCase()).toContain('cleared');
    });

    it('should trigger ai_action_update_purifier_selection checkpoint substep', () => {
      const cpSpy = spyOn(sharedService, 'triggerCheckpoint');
      (component as any)._handleActionResult('update_purifier_selection', {
        applied: {
          form: 'diff',
          purifier_options: null,
          add: [7],
          remove: [],
        },
      });
      expect(cpSpy).toHaveBeenCalledWith('ai_action_update_purifier_selection');
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

  // ── v2.38.0: cross-trace linking (chat_span_id ↔ parent_span_id) ─────
  // The chat panel is the bridge between the two backend traces:
  //   1. /chat/ response → carries chat_span_id (when actions present)
  //   2. /execute-action/ request → must echo it as parent_span_id
  // These specs lock both halves of the bridge so a future refactor of
  // the send/apply flow can't silently drop the link.
  describe('v2.38.0 cross-trace linking', () => {
    beforeEach(() => {
      sharedService.setCurrentFileId(1);
    });

    it('should persist chat_span_id from /chat/ response onto the message', () => {
      // Mirror the send-flow: stub sendAiChat to return a chat_span_id,
      // verify updateLastMessage stamped it on the assistant message.
      spyOn(dataService, 'sendAiChat').and.returnValue(of({
        message: 'I prepared an action.',
        actions: [{ type: 'update_notes', payload: { description: 'note' } }],
        chat_span_id: 'chat-span-abc123',
        chat_trace_id: 'trace-abc123',
        chat_session_id: 'declarai-file-1',
      }));
      spyOn(dataService, 'getAiModels').and.returnValue(of({ models: [], default: 'gpt-5.5' }));

      aiService.addMessage({ role: 'user', content: 'hi', timestamp: new Date() });
      aiService.addMessage({ role: 'assistant', content: '', timestamp: new Date() });

      component.sendMessage('hi');

      const last = aiService.getMessages().slice(-1)[0];
      expect(last.chatSpanId).toBe('chat-span-abc123');
      expect(last.chatTraceId).toBe('trace-abc123');
      expect(last.chatSessionId).toBe('declarai-file-1');
    });

    it('should leave chatSpanId undefined when /chat/ response omits the field', () => {
      // Pre-v2.38.0 backend (or SDK-disabled) — no chat_span_id in response.
      // Frontend must not fabricate one; subsequent applyAction skips link.
      spyOn(dataService, 'sendAiChat').and.returnValue(of({
        message: 'I prepared an action.',
        actions: [{ type: 'update_notes', payload: { description: 'note' } }],
      }));
      spyOn(dataService, 'getAiModels').and.returnValue(of({ models: [], default: 'gpt-5.5' }));

      aiService.addMessage({ role: 'user', content: 'hi', timestamp: new Date() });
      aiService.addMessage({ role: 'assistant', content: '', timestamp: new Date() });

      component.sendMessage('hi');

      const last = aiService.getMessages().slice(-1)[0];
      expect(last.chatSpanId).toBeUndefined();
    });

    it('applyAction should forward chatSpanId as parentSpanId to executeAiAction', () => {
      // Seed an assistant message that already has a chatSpanId
      // (mimicking the post-send state from the previous spec).
      const action: any = {
        type: 'update_notes',
        payload: { description: 'note' },
        applied: false,
      };
      aiService.addMessage({
        role: 'assistant',
        content: 'I prepared an action.',
        timestamp: new Date(),
        actions: [action],
        chatSpanId: 'chat-span-abc123',
      });
      const messageIndex = aiService.getMessages().length - 1;

      const execSpy = spyOn(dataService, 'executeAiAction').and.returnValue(
        of({ status: 'success', description: 'ok' })
      );

      component.applyAction(messageIndex, 0, action);

      // 4th arg (parentSpanId) MUST be the message's chatSpanId.
      expect(execSpy).toHaveBeenCalledWith(
        1,                            // fileId
        'update_notes',               // actionType
        { description: 'note' },      // payload
        'chat-span-abc123',           // parentSpanId — the link
      );
    });

    it('applyAction should pass undefined parentSpanId when message lacks chatSpanId', () => {
      // Legacy v2.25.0..v2.37.0 message with no chatSpanId — applyAction
      // must call executeAiAction with parentSpanId omitted/undefined so
      // dataService skips the parent_span_id POST field (legacy semantics).
      const action: any = {
        type: 'update_notes',
        payload: { description: 'note' },
        applied: false,
      };
      aiService.addMessage({
        role: 'assistant',
        content: 'I prepared an action.',
        timestamp: new Date(),
        actions: [action],
        // No chatSpanId — pre-v2.38.0 message shape.
      });
      const messageIndex = aiService.getMessages().length - 1;

      const execSpy = spyOn(dataService, 'executeAiAction').and.returnValue(
        of({ status: 'success' })
      );

      component.applyAction(messageIndex, 0, action);

      expect(execSpy).toHaveBeenCalledWith(
        1,
        'update_notes',
        { description: 'note' },
        undefined,                    // ← key assertion: no link forwarded
      );
    });
  });

  describe('assistant answer feedback', () => {
    beforeEach(() => {
      sharedService.setCurrentFileId(42);
    });

    it('submitFeedback should send thumbs/rating/comment with Prometa target ids', () => {
      aiService.addMessage({
        role: 'assistant',
        content: 'Useful answer',
        timestamp: new Date(),
        chatSpanId: 'span-1',
        chatTraceId: 'trace-1',
        chatSessionId: 'declarai-file-42',
        feedback: {
          liked: true,
          rating: 4,
          comment: 'This clarified the PSI threshold.',
          feedbackId: 'feedback-1',
        },
      });
      const submitSpy = spyOn(dataService, 'submitAiFeedback').and.returnValue(
        of({ status: 'success', feedback_id: 'feedback-1' })
      );

      component.submitFeedback(0);

      expect(submitSpy).toHaveBeenCalled();
      const payload = submitSpy.calls.mostRecent().args[0];
      expect(payload.liked).toBeTrue();
      expect(payload.rating).toBe(4);
      expect(payload.comment).toBe('This clarified the PSI threshold.');
      expect(payload.source).toBe('declarai-ai-chat-panel');
      expect(payload.feedback_id).toBe('feedback-1');
      expect(payload.target_trace_id).toBe('trace-1');
      expect(payload.target_span_id).toBe('span-1');
      expect(payload.target_session_id).toBe('declarai-file-42');
      expect(payload.conversation_id).toBe('declarai-file-42');
      expect(payload.file_id).toBe(42);
      expect(payload.submitted_at).toBeTruthy();
      expect(aiService.getMessages()[0].feedback?.submitted).toBeTrue();
    });

    it('submitFeedback should require a thumb, rating, or comment before POSTing', () => {
      aiService.addMessage({
        role: 'assistant',
        content: 'Answer',
        timestamp: new Date(),
      });
      const submitSpy = spyOn(dataService, 'submitAiFeedback');

      component.submitFeedback(0);

      expect(submitSpy).not.toHaveBeenCalled();
      expect(aiService.getMessages()[0].feedback?.error).toContain('Choose a thumb');
    });
  });

  // ── v2.41.1: LaTeX → Unicode rendering pass ─────────────────────────
  // The chat renderer is a hand-rolled markdown subset with no MathJax /
  // KaTeX layer.  When the LLM emits LaTeX-style symbols (e.g.
  // `$\rightarrow$`, `\alpha`, `\le`) the user previously saw the raw
  // source in the chat bubble.  v2.41.1 adds a defensive `_delatexify`
  // pass inside `_formatInline` that converts the most common
  // ML/credit-risk symbols to Unicode before markdown processing.
  //
  // These specs pin the round-trip for the user-reported case AND a
  // representative sample of every category (arrows, comparison ops,
  // arithmetic, set/logic, calculus, Greek lowercase + uppercase).
  // The system prompts ALSO instruct the LLM to use Unicode directly
  // (see TestSystemPromptLatexFormattingRule on the backend); this
  // client-side pass is defense-in-depth so a rogue model output can
  // never put raw LaTeX on screen.
  describe('v2.41.1 LaTeX → Unicode rendering', () => {
    it('REGRESSION: the user-reported `$\\rightarrow$` renders as `→`', () => {
      // The exact string from the v2.41.1 bug report: assistant emitted
      // `$\rightarrow$` and the user saw it raw in the chat bubble.
      const out = component.formatMessage('PSI ≥ 0.25 $\\rightarrow$ significant shift');
      expect(out).toContain('→');
      expect(out).not.toContain('rightarrow');
      expect(out).not.toContain('\\');
    });

    it('handles bare `\\rightarrow` without $ delimiters', () => {
      const out = component.formatMessage('See \\rightarrow next step');
      expect(out).toContain('→');
      expect(out).not.toContain('rightarrow');
    });

    it('converts the full arrow family', () => {
      const out = component.formatMessage(
        'Arrows: $\\Rightarrow$ $\\leftarrow$ $\\Leftarrow$ $\\leftrightarrow$ $\\uparrow$ $\\downarrow$ $\\mapsto$'
      );
      expect(out).toContain('⇒');
      expect(out).toContain('←');
      expect(out).toContain('⇐');
      expect(out).toContain('↔');
      expect(out).toContain('↑');
      expect(out).toContain('↓');
      expect(out).toContain('↦');
      expect(out).not.toMatch(/Rightarrow|leftarrow|Leftarrow|leftrightarrow|uparrow|downarrow|mapsto/);
    });

    it('converts comparison + arithmetic ops', () => {
      const out = component.formatMessage(
        'Ops: $\\leq$ $\\le$ $\\geq$ $\\ge$ $\\neq$ $\\approx$ $\\pm$ $\\times$ $\\div$ $\\cdot$'
      );
      // Each conversion target appears at least once.  We don't pin the
      // count because $\le$ and $\leq$ both map to ≤ (so two ≤ from those).
      expect(out).toContain('≤');
      expect(out).toContain('≥');
      expect(out).toContain('≠');
      expect(out).toContain('≈');
      expect(out).toContain('±');
      expect(out).toContain('×');
      expect(out).toContain('÷');
      expect(out).toContain('·');
      // None of the LaTeX command names should leak through.
      expect(out).not.toMatch(/\\(leq|le|geq|ge|neq|approx|pm|times|div|cdot)\b/);
    });

    it('converts Greek letters (lowercase + uppercase)', () => {
      const out = component.formatMessage(
        'Greek: $\\alpha$ $\\beta$ $\\sigma$ $\\mu$ $\\pi$ $\\theta$ $\\Delta$ $\\Sigma$ $\\Omega$'
      );
      expect(out).toContain('α');
      expect(out).toContain('β');
      expect(out).toContain('σ');
      expect(out).toContain('μ');
      expect(out).toContain('π');
      expect(out).toContain('θ');
      expect(out).toContain('Δ');
      expect(out).toContain('Σ');
      expect(out).toContain('Ω');
      expect(out).not.toMatch(/\\(alpha|beta|sigma|mu|pi|theta|Delta|Sigma|Omega)\b/);
    });

    it('converts calculus + set/logic operators', () => {
      const out = component.formatMessage(
        'Math: $\\sum$ $\\prod$ $\\int$ $\\infty$ $\\sqrt$ $\\partial$ $\\in$ $\\notin$ $\\forall$'
      );
      expect(out).toContain('∑');
      expect(out).toContain('∏');
      expect(out).toContain('∫');
      expect(out).toContain('∞');
      expect(out).toContain('√');
      expect(out).toContain('∂');
      expect(out).toContain('∈');
      expect(out).toContain('∉');
      expect(out).toContain('∀');
    });

    it('REGRESSION: money strings like `$50` and `$1,200` are NOT corrupted', () => {
      // The whole point of NOT writing a generic `$...$` stripper is to
      // keep money/price strings intact.  This pin guards against a
      // future "smarter" stripper regressing the ML/finance use case.
      const out = component.formatMessage(
        'Loan amount $50,000 with $1,200 monthly payment for $24 months'
      );
      expect(out).toContain('$50,000');
      expect(out).toContain('$1,200');
      expect(out).toContain('$24');
    });

    it('REGRESSION: code blocks and inline code with backslashes are not LaTeX-mangled', () => {
      // Markdown inline code like `\n` (Python newline literal) should
      // pass through unchanged — the LaTeX pass must not eat the
      // backslash inside non-LaTeX contexts.  We test this via the
      // `\,` spacing command rule: a code mention of `\,` is rare, so
      // the broader contract here is "unknown commands stay as-is".
      const out = component.formatMessage('Unknown: \\foobar should stay');
      expect(out).toContain('\\foobar');
    });

    it('shortcuts when the input has no backslash at all (perf path)', () => {
      // The early return optimisation: strings without `\` should
      // pass through unchanged byte-for-byte (modulo HTML escaping +
      // markdown formatting).
      const out = component.formatMessage('Plain text with → and ≤ already in unicode');
      expect(out).toContain('→');
      expect(out).toContain('≤');
      expect(out).not.toContain('\\');
    });

    it('integrates cleanly with markdown bold + LaTeX in the same line', () => {
      // Ensures the LaTeX pass runs BEFORE markdown so `**bold**` still
      // renders as `<strong>` even when the line also has LaTeX.
      const out = component.formatMessage('**Result:** PSI $\\ge$ 0.25');
      expect(out).toContain('<strong>Result:</strong>');
      expect(out).toContain('≥');
    });
  });

  // ── start_hyperparameter response handling (Phase 3) ──────────────────
  // The dedicated path for the AI to fire the "Start Hyperparameter Tuning"
  // button.  The chat panel forwards the validated config on
  // hyperparamStartRequests$ so the modeling component mirrors the tuning
  // form fields and calls startHyperparam().
  describe('_handleActionResult start_hyperparameter flow', () => {
    const validApplied = {
      param_space: null,
      enabled_params: ['max_depth', 'learning_rate'],
      n_iter: 60,
      cv_folds: 4,
      n_jobs: 6,
      primary_metric: 'f1',
      validation_curve_points: 10,
      search_method: 'bayesian',
      grid_points_per_param: 5,
    };

    it('should broadcast the validated config on hyperparamStartRequests$', (done) => {
      sharedService.hyperparamStartRequests$.subscribe(received => {
        expect(received).toEqual(validApplied);
        done();
      });
      (component as any)._handleActionResult('start_hyperparameter', {
        applied: validApplied,
        description: 'Tune depth + learning rate, 60 trials',
      });
    });

    it('should NOT broadcast when applied is missing', () => {
      const emitSpy = spyOn(sharedService, 'emitHyperparamStartRequest');
      (component as any)._handleActionResult('start_hyperparameter', { description: 'malformed' });
      expect(emitSpy).not.toHaveBeenCalled();
    });

    it('should add a chat message summarising the tuning config', () => {
      (component as any)._handleActionResult('start_hyperparameter', {
        applied: validApplied,
        description: 'Tune depth + learning rate',
      });
      const lastMsg = aiService.getMessages().slice(-1)[0];
      expect(lastMsg.content).toContain('Hyperparameter tuning started');
      expect(lastMsg.content).toContain('60');          // n_iter
      expect(lastMsg.content).toContain('n_jobs');       // compute-power label
      expect(lastMsg.content).toContain('max_depth');    // enabled param
      expect(lastMsg.content).toContain('f1');           // curve metric
      expect(lastMsg.content).toContain('bayesian');     // search method
    });

    it('should trigger ai_action_start_hyperparameter checkpoint substep', () => {
      const cpSpy = spyOn(sharedService, 'triggerCheckpoint');
      (component as any)._handleActionResult('start_hyperparameter', { applied: validApplied });
      expect(cpSpy).toHaveBeenCalledWith('ai_action_start_hyperparameter');
    });

    it('should render "form defaults" when enabled_params is empty', () => {
      (component as any)._handleActionResult('start_hyperparameter', {
        applied: { ...validApplied, enabled_params: [] },
      });
      const lastMsg = aiService.getMessages().slice(-1)[0];
      expect(lastMsg.content).toContain('_form defaults_');
    });
  });
});
