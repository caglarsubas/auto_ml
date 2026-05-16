import { TestBed } from '@angular/core/testing';
import { SharedService } from './shared.service';

describe('SharedService', () => {
  let service: SharedService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(SharedService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  // ── isStarted ──────────────────────────────────────────────────────────
  describe('isStarted', () => {
    it('should default to false', (done) => {
      service.isStarted$.subscribe(val => {
        expect(val).toBeFalse();
        done();
      });
    });

    it('should emit true after setStarted(true)', (done) => {
      service.setStarted(true);
      service.isStarted$.subscribe(val => {
        expect(val).toBeTrue();
        done();
      });
    });
  });

  // ── selectedPipeline ───────────────────────────────────────────────────
  describe('selectedPipeline', () => {
    it('should default to empty string', () => {
      expect(service.getSelectedPipeline()).toBe('');
    });

    it('should store and return pipeline name', () => {
      service.setSelectedPipeline('boosting');
      expect(service.getSelectedPipeline()).toBe('boosting');
    });

    it('should emit via observable', (done) => {
      service.setSelectedPipeline('logistic');
      service.selectedPipeline$.subscribe(val => {
        expect(val).toBe('logistic');
        done();
      });
    });
  });

  // ── currentFileId ──────────────────────────────────────────────────────
  describe('currentFileId', () => {
    it('should default to null', () => {
      expect(service.getCurrentFileId()).toBeNull();
    });

    it('should store and return file id', () => {
      service.setCurrentFileId(42);
      expect(service.getCurrentFileId()).toBe(42);
    });

    it('should emit via observable', (done) => {
      service.setCurrentFileId(7);
      service.currentFileId$.subscribe(val => {
        expect(val).toBe(7);
        done();
      });
    });

    it('should allow resetting to null', () => {
      service.setCurrentFileId(10);
      service.setCurrentFileId(null);
      expect(service.getCurrentFileId()).toBeNull();
    });
  });

  // ── preprocessingInitiated ─────────────────────────────────────────────
  describe('preprocessingInitiated', () => {
    it('should default to false', (done) => {
      service.preprocessingInitiated$.subscribe(val => {
        expect(val).toBeFalse();
        done();
      });
    });

    it('should emit true after set', (done) => {
      service.setPreprocessingInitiated(true);
      service.preprocessingInitiated$.subscribe(val => {
        expect(val).toBeTrue();
        done();
      });
    });
  });

  // ── selectedPurifierOptions ────────────────────────────────────────────
  describe('selectedPurifierOptions', () => {
    it('should default to empty array', (done) => {
      service.selectedPurifierOptions$.subscribe(val => {
        expect(val).toEqual([]);
        done();
      });
    });

    it('should store option ids', (done) => {
      service.setSelectedPurifierOptions([1, 3, 5]);
      service.selectedPurifierOptions$.subscribe(val => {
        expect(val).toEqual([1, 3, 5]);
        done();
      });
    });
  });

  // ── processedFilePath ──────────────────────────────────────────────────
  describe('processedFilePath', () => {
    it('should default to null', (done) => {
      service.processedFilePath$.subscribe(val => {
        expect(val).toBeNull();
        done();
      });
    });

    it('should store path string', (done) => {
      service.setProcessedFilePath('processed/test.csv');
      service.processedFilePath$.subscribe(val => {
        expect(val).toBe('processed/test.csv');
        done();
      });
    });
  });

  // ── modelUsageSettings ─────────────────────────────────────────────────
  describe('modelUsageSettings', () => {
    it('should default to null', () => {
      expect(service.getModelUsageSettings()).toBeNull();
    });

    it('should store and retrieve settings', () => {
      const settings = { Age: 'Yes', Income: 'No' };
      service.setModelUsageSettings(settings);
      expect(service.getModelUsageSettings()).toEqual(settings);
    });
  });

  // ── encodedFilePath ────────────────────────────────────────────────────
  describe('encodedFilePath', () => {
    it('should default to null', (done) => {
      service.encodedFilePath$.subscribe(val => {
        expect(val).toBeNull();
        done();
      });
    });

    it('should store encoded path', (done) => {
      service.setEncodedFilePath('encoded/file.csv');
      service.encodedFilePath$.subscribe(val => {
        expect(val).toBe('encoded/file.csv');
        done();
      });
    });
  });

  // ── encodingReport ─────────────────────────────────────────────────────
  describe('encodingReport', () => {
    it('should default to empty array', (done) => {
      service.encodingReport$.subscribe(val => {
        expect(val).toEqual([]);
        done();
      });
    });

    it('should store report', (done) => {
      const report = [{ feature: 'Region', strategy: 'ohe' }];
      service.setEncodingReport(report);
      service.encodingReport$.subscribe(val => {
        expect(val).toEqual(report);
        done();
      });
    });
  });

  // ── dataDictionaryCache ────────────────────────────────────────────────
  describe('dataDictionaryCache', () => {
    it('should default to empty array', (done) => {
      service.dataDictionaryCache$.subscribe(val => {
        expect(val).toEqual([]);
        done();
      });
    });

    it('should store cache', (done) => {
      const cache = [{ Feature_Name: 'Age', Level_of_Measurement: 'continuous' }];
      service.setDataDictionaryCache(cache);
      service.dataDictionaryCache$.subscribe(val => {
        expect(val).toEqual(cache);
        done();
      });
    });
  });

  // ── modelingCheckpoint ─────────────────────────────────────────────────
  describe('modelingCheckpoint', () => {
    it('should default to null', () => {
      expect(service.getModelingCheckpoint()).toBeNull();
    });

    it('should store and return checkpoint state', () => {
      const state = { substep: 'modeling_completed', algorithm: 'xgboost' };
      service.setModelingCheckpoint(state);
      expect(service.getModelingCheckpoint()).toEqual(state);
    });

    it('should reset to null', () => {
      service.setModelingCheckpoint({ x: 1 });
      service.setModelingCheckpoint(null);
      expect(service.getModelingCheckpoint()).toBeNull();
    });
  });

  // ── triggerCheckpoint ──────────────────────────────────────────────────
  describe('triggerCheckpoint', () => {
    it('should emit substep string', (done) => {
      service.triggerCheckpoint$.subscribe(val => {
        expect(val).toBe('modeling_completed');
        done();
      });
      service.triggerCheckpoint('modeling_completed');
    });
  });

  // ── dataRefresh ────────────────────────────────────────────────────────
  describe('dataRefresh', () => {
    it('should emit when triggered', (done) => {
      service.dataRefresh$.subscribe(() => {
        expect(true).toBeTrue();
        done();
      });
      service.triggerDataRefresh();
    });
  });

  // ── autosaveEnabled ────────────────────────────────────────────────────
  describe('autosaveEnabled', () => {
    it('should default to true', () => {
      expect(service.getAutosaveEnabled()).toBeTrue();
    });

    it('should toggle off', () => {
      service.setAutosaveEnabled(false);
      expect(service.getAutosaveEnabled()).toBeFalse();
    });
  });

  // ── pipelineNotes ──────────────────────────────────────────────────────
  describe('pipelineNotes', () => {
    it('should default to empty object', () => {
      expect(service.getPipelineNotes()).toEqual({});
    });

    it('should set and get notes', () => {
      const notes = { after_data_preview: 'Looks clean' };
      service.setPipelineNotes(notes);
      expect(service.getPipelineNotes()).toEqual(notes);
    });

    it('should update a single note', () => {
      service.updatePipelineNote('after_data_preview', 'Note A');
      expect(service.getPipelineNotes()['after_data_preview']).toBe('Note A');
    });

    it('should remove note when content is empty', () => {
      service.updatePipelineNote('after_data_preview', 'Note A');
      service.updatePipelineNote('after_data_preview', '');
      expect(service.getPipelineNotes()['after_data_preview']).toBeUndefined();
    });

    it('should handle multiple notes', () => {
      service.updatePipelineNote('after_data_preview', 'A');
      service.updatePipelineNote('after_encoding', 'B');
      const notes = service.getPipelineNotes();
      expect(notes['after_data_preview']).toBe('A');
      expect(notes['after_encoding']).toBe('B');
    });
  });

  // ── aiCumulativeContext ────────────────────────────────────────────────
  describe('aiCumulativeContext', () => {
    it('should default to empty object', () => {
      expect(service.getAiCumulativeContext()).toEqual({});
    });

    it('should store and retrieve context', () => {
      const ctx = { declaration: { file_id: 1 }, modeling: { algorithm: 'xgboost' } };
      service.setAiCumulativeContext(ctx);
      expect(service.getAiCumulativeContext()).toEqual(ctx);
    });
  });

  // ── targetDefinition ──────────────────────────────────────────────────
  describe('targetDefinition', () => {
    it('should default to empty string', () => {
      expect(service.getTargetDefinition()).toBe('');
    });

    it('should store and retrieve definition', () => {
      service.setTargetDefinition('Binary default indicator');
      expect(service.getTargetDefinition()).toBe('Binary default indicator');
    });
  });

  // ── activeProcess ──────────────────────────────────────────────────────
  describe('activeProcess', () => {
    it('should default to null', () => {
      expect(service.getActiveProcess()).toBeNull();
    });

    it('should store and retrieve process', () => {
      service.setActiveProcess({ type: 'modeling', file_id: 5 });
      expect(service.getActiveProcess()).toEqual({ type: 'modeling', file_id: 5 });
    });

    it('should clear process', () => {
      service.setActiveProcess({ type: 'sfs', file_id: 3 });
      service.setActiveProcess(null);
      expect(service.getActiveProcess()).toBeNull();
    });
  });

  // ── metadataUpdates ────────────────────────────────────────────────────
  // v2.23.0+ feature.  Exercised end-to-end by the AI chat panel after
  // an `update_metadata` action returns: the chat panel calls
  // `emitMetadataUpdates(applied)` and every interested component
  // (declaration table, encoding plan dropdown, feature card) patches
  // its local state instead of triggering a backend refetch.
  describe('metadataUpdates', () => {
    it('should not emit anything before any call', (done) => {
      // Subject (not BehaviorSubject) — should produce zero emissions.
      let emitted = false;
      const sub = service.metadataUpdates$.subscribe(() => { emitted = true; });
      setTimeout(() => {
        expect(emitted).toBeFalse();
        sub.unsubscribe();
        done();
      }, 0);
    });

    it('should emit the applied array verbatim', (done) => {
      const updates = [
        { column: 'Var_2', field: 'Level_of_Measurement', value: 'ordinal' },
        { column: 'Var_36', field: 'Level_of_Measurement', value: 'ordinal' },
      ];
      service.metadataUpdates$.subscribe(received => {
        expect(received).toEqual(updates);
        done();
      });
      service.emitMetadataUpdates(updates);
    });

    it('should ignore an empty array (no emission)', (done) => {
      let emitted = false;
      const sub = service.metadataUpdates$.subscribe(() => { emitted = true; });
      service.emitMetadataUpdates([]);
      setTimeout(() => {
        expect(emitted).toBeFalse();
        sub.unsubscribe();
        done();
      }, 0);
    });

    it('should ignore a non-array argument (no emission)', (done) => {
      let emitted = false;
      const sub = service.metadataUpdates$.subscribe(() => { emitted = true; });
      // Defensive: the chat panel is supposed to pass arrays only, but
      // the helper guards against accidental misuse.
      service.emitMetadataUpdates(null as any);
      service.emitMetadataUpdates(undefined as any);
      service.emitMetadataUpdates({} as any);
      setTimeout(() => {
        expect(emitted).toBeFalse();
        sub.unsubscribe();
        done();
      }, 0);
    });

    it('should fan out a second emission to late subscribers (Subject semantics)', (done) => {
      // We deliberately use Subject (not BehaviorSubject) so that
      // late-mounting components don't replay stale updates that have
      // already been applied to the dictionary cache.
      const first = [{ column: 'Var_1', field: 'Feature_Description', value: 'first' }];
      const second = [{ column: 'Var_2', field: 'Feature_Description', value: 'second' }];
      service.emitMetadataUpdates(first);
      const seen: any[] = [];
      service.metadataUpdates$.subscribe(received => seen.push(received));
      service.emitMetadataUpdates(second);
      setTimeout(() => {
        expect(seen.length).toBe(1);
        expect(seen[0]).toEqual(second);
        done();
      }, 0);
    });
  });

  // ── getDataDictionaryCache snapshot accessor ──────────────────────────
  // Used by the AI chat panel to patch the dictionary cache in place
  // after an `update_metadata` action.  Must return [] (not undefined)
  // when nothing has been pushed yet so callers can safely .map() it.
  describe('getDataDictionaryCache', () => {
    it('should return [] before anything is set', () => {
      expect(service.getDataDictionaryCache()).toEqual([]);
    });

    it('should return the most recent cache snapshot', () => {
      const cache = [
        { Feature_Name: 'Age', Level_of_Measurement: 'continuous' },
        { Feature_Name: 'Var_2', Level_of_Measurement: 'nominal' },
      ];
      service.setDataDictionaryCache(cache);
      expect(service.getDataDictionaryCache()).toEqual(cache);
    });
  });

  // ── encodingRankingUpdates ────────────────────────────────────────────
  // v2.24.0+ feature.  The AI's procedural follow-through path after
  // setting a feature's LoM to ordinal: emit a `set_ordinal_ranking`
  // action; the chat panel forwards the applied rankings here, the
  // modeling component patches encodingPlan[i].ranking in place.
  describe('encodingRankingUpdates', () => {
    it('should not emit anything before any call', (done) => {
      let emitted = false;
      const sub = service.encodingRankingUpdates$.subscribe(() => { emitted = true; });
      setTimeout(() => {
        expect(emitted).toBeFalse();
        sub.unsubscribe();
        done();
      }, 0);
    });

    it('should emit the applied array verbatim', (done) => {
      const updates = [
        { column: 'Var_36', ranking: ['0', '1', '2', '3', '8', 'L', 'Others'] },
        { column: 'Var_2', ranking: ['A', 'P', 'R'] },
      ];
      service.encodingRankingUpdates$.subscribe(received => {
        expect(received).toEqual(updates);
        done();
      });
      service.emitEncodingRankingUpdates(updates);
    });

    it('should ignore an empty array (no emission)', (done) => {
      let emitted = false;
      const sub = service.encodingRankingUpdates$.subscribe(() => { emitted = true; });
      service.emitEncodingRankingUpdates([]);
      setTimeout(() => {
        expect(emitted).toBeFalse();
        sub.unsubscribe();
        done();
      }, 0);
    });

    it('should ignore null / undefined / non-array gracefully', (done) => {
      let emitted = false;
      const sub = service.encodingRankingUpdates$.subscribe(() => { emitted = true; });
      service.emitEncodingRankingUpdates(null as any);
      service.emitEncodingRankingUpdates(undefined as any);
      service.emitEncodingRankingUpdates({} as any);
      setTimeout(() => {
        expect(emitted).toBeFalse();
        sub.unsubscribe();
        done();
      }, 0);
    });

    it('should not replay past emissions to late subscribers (Subject semantics)', (done) => {
      // Critical: the ranking is applied to entry.ranking imperatively
      // when the event fires.  A late subscriber replaying a stale
      // emission would re-clobber a user's manual ▲▼ adjustments made
      // after the AI's initial proposal.
      const first = [{ column: 'Var_A', ranking: ['x', 'y', 'z'] }];
      const second = [{ column: 'Var_B', ranking: ['p', 'q'] }];
      service.emitEncodingRankingUpdates(first);
      const seen: any[] = [];
      service.encodingRankingUpdates$.subscribe(r => seen.push(r));
      service.emitEncodingRankingUpdates(second);
      setTimeout(() => {
        expect(seen.length).toBe(1);
        expect(seen[0]).toEqual(second);
        done();
      }, 0);
    });
  });

  // ── featureUsageUpdates (v2.25.0+) ───────────────────────────────────
  // AI's `update_config feature_usage` action broadcasts here; the
  // modeling component subscribes to patch the Selected Features
  // table's Keep/Drop dropdown.  The correct path for "exclude Var_3
  // from SFS due to VIF" — NOT execute_code drop.
  describe('featureUsageUpdates', () => {
    it('should not emit anything before any call', (done) => {
      let emitted = false;
      const sub = service.featureUsageUpdates$.subscribe(() => { emitted = true; });
      setTimeout(() => {
        expect(emitted).toBeFalse();
        sub.unsubscribe();
        done();
      }, 0);
    });

    it('should emit the updates array verbatim', (done) => {
      const updates: Array<{ column: string; value: 'keep' | 'drop'; reason?: string }> = [
        { column: 'Var_3', value: 'drop', reason: 'VIF=9.39' },
        { column: 'Var_25', value: 'drop', reason: 'Low SHAP' },
      ];
      service.featureUsageUpdates$.subscribe(received => {
        expect(received).toEqual(updates);
        done();
      });
      service.emitFeatureUsageUpdates(updates);
    });

    it('should ignore an empty array (no emission)', (done) => {
      let emitted = false;
      const sub = service.featureUsageUpdates$.subscribe(() => { emitted = true; });
      service.emitFeatureUsageUpdates([]);
      setTimeout(() => {
        expect(emitted).toBeFalse();
        sub.unsubscribe();
        done();
      }, 0);
    });

    it('should ignore null / undefined / non-array gracefully', (done) => {
      let emitted = false;
      const sub = service.featureUsageUpdates$.subscribe(() => { emitted = true; });
      service.emitFeatureUsageUpdates(null as any);
      service.emitFeatureUsageUpdates(undefined as any);
      service.emitFeatureUsageUpdates('drop' as any);
      setTimeout(() => {
        expect(emitted).toBeFalse();
        sub.unsubscribe();
        done();
      }, 0);
    });

    it('should not replay past emissions (Subject semantics)', (done) => {
      service.emitFeatureUsageUpdates([{ column: 'Var_A', value: 'drop' }]);
      const seen: any[] = [];
      service.featureUsageUpdates$.subscribe(r => seen.push(r));
      service.emitFeatureUsageUpdates([{ column: 'Var_B', value: 'keep' }]);
      setTimeout(() => {
        expect(seen.length).toBe(1);
        expect(seen[0]).toEqual([{ column: 'Var_B', value: 'keep' }]);
        done();
      }, 0);
    });
  });

  // ── sfsStartRequests (v2.25.0+) ──────────────────────────────────────
  // AI's `start_sfs` action broadcasts the validated SFS config here;
  // the modeling component populates form fields and calls startSfs().
  describe('sfsStartRequests', () => {
    const mkReq = (overrides: any = {}) => ({
      methods: ['backward'],
      stopping_criteria: { metrics: [{ metric: 'roc_auc', pct_change: 1.0 }], min_features: 5, max_features: 15 },
      excluded_features: [],
      n_jobs: 3,
      top_k: 5,
      ...overrides,
    });

    it('should not emit anything before any call', (done) => {
      let emitted = false;
      const sub = service.sfsStartRequests$.subscribe(() => { emitted = true; });
      setTimeout(() => {
        expect(emitted).toBeFalse();
        sub.unsubscribe();
        done();
      }, 0);
    });

    it('should emit the request object verbatim', (done) => {
      const req = mkReq({ excluded_features: ['Var_3'] });
      service.sfsStartRequests$.subscribe(received => {
        expect(received).toEqual(req);
        done();
      });
      service.emitSfsStartRequest(req);
    });

    it('should reject a request with empty methods (no emission)', (done) => {
      let emitted = false;
      const sub = service.sfsStartRequests$.subscribe(() => { emitted = true; });
      service.emitSfsStartRequest(mkReq({ methods: [] }));
      setTimeout(() => {
        expect(emitted).toBeFalse();
        sub.unsubscribe();
        done();
      }, 0);
    });

    it('should reject a non-object request gracefully', (done) => {
      let emitted = false;
      const sub = service.sfsStartRequests$.subscribe(() => { emitted = true; });
      service.emitSfsStartRequest(null as any);
      service.emitSfsStartRequest(undefined as any);
      service.emitSfsStartRequest('start' as any);
      setTimeout(() => {
        expect(emitted).toBeFalse();
        sub.unsubscribe();
        done();
      }, 0);
    });

    it('should not replay past requests to late subscribers', (done) => {
      // Critical: if a late subscriber replayed, SFS could auto-start
      // twice on component remount.
      service.emitSfsStartRequest(mkReq());
      const seen: any[] = [];
      service.sfsStartRequests$.subscribe(r => seen.push(r));
      service.emitSfsStartRequest(mkReq({ methods: ['forward'] }));
      setTimeout(() => {
        expect(seen.length).toBe(1);
        expect(seen[0].methods).toEqual(['forward']);
        done();
      }, 0);
    });
  });
});
