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
});
