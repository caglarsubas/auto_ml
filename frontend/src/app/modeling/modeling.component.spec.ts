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
});
