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
});
