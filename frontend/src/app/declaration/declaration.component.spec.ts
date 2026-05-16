import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { RouterTestingModule } from '@angular/router/testing';
import { FormsModule } from '@angular/forms';
import { CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { MatDialogModule } from '@angular/material/dialog';
import { MatSnackBarModule } from '@angular/material/snack-bar';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { DeclarationComponent } from './declaration.component';
import { SharedService } from '../services/shared.service';

describe('DeclarationComponent', () => {
  let component: DeclarationComponent;
  let fixture: ComponentFixture<DeclarationComponent>;
  let sharedService: SharedService;

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
      declarations: [DeclarationComponent],
      providers: [SharedService],
      schemas: [CUSTOM_ELEMENTS_SCHEMA],
    }).compileComponents();

    fixture = TestBed.createComponent(DeclarationComponent);
    component = fixture.componentInstance;
    sharedService = TestBed.inject(SharedService);
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should initialize with no selected files', () => {
    expect(component.selectedFiles).toEqual([]);
  });

  it('should initialize with no preview data', () => {
    expect(component.previewData).toBeNull();
  });

  it('should initialize with empty data dictionary', () => {
    expect(component.dataDictionary).toEqual([]);
  });

  it('should default column separator to semicolon', () => {
    expect(component.columnSeparator).toBe('semicolon');
  });

  it('should default split strategy to random', () => {
    expect(component.splitStrategy).toBe('random');
  });

  it('should initialize with showContent false', () => {
    expect(component.showContent).toBeFalse();
  });

  it('should initialize pipeline notes as empty object', () => {
    expect(component.pipelineNotes).toEqual({});
  });

  // ── metadataUpdates$ subscription (v2.23.0+) ──────────────────────────
  // The declaration table renders Level_of_Measurement as a read-only
  // text cell sourced from `dataDictionary[i].Level_of_Measurement`.
  // When the AI assistant changes a feature's LoM, the chat panel
  // broadcasts on metadataUpdates$ and this component must patch the
  // matching dataDictionary entry without calling the backend
  // refetch (which would recompute LoM from the raw file and wipe the
  // change).
  describe('metadataUpdates$ -> dataDictionary patch', () => {
    beforeEach(() => {
      // Drive ngOnInit so the subscription wires up.
      fixture.detectChanges();
      // Seed the dictionary the same way getPreview/data_dictionary
      // GET would after a successful upload.
      component.dataDictionary = [
        { Feature_Name: 'Var_2', Level_of_Measurement: 'nominal',
          Feature_Description: 'Worst Account Status', Data_Type: 'integer' },
        { Feature_Name: 'Var_36', Level_of_Measurement: 'nominal',
          Feature_Description: 'CC Worst Payment', Data_Type: 'integer' },
        { Feature_Name: 'Var_3', Level_of_Measurement: 'nominal',
          Feature_Description: 'Any Legal Action YN', Data_Type: 'object' },
      ];
    });

    it('should patch Level_of_Measurement on the matching row', () => {
      sharedService.emitMetadataUpdates([
        { column: 'Var_2', field: 'Level_of_Measurement', value: 'ordinal' },
      ]);
      const var2 = component.dataDictionary.find(
        (d: any) => d.Feature_Name === 'Var_2');
      expect(var2.Level_of_Measurement).toBe('ordinal');
    });

    it('should patch multiple rows in a single emission', () => {
      sharedService.emitMetadataUpdates([
        { column: 'Var_2', field: 'Level_of_Measurement', value: 'ordinal' },
        { column: 'Var_36', field: 'Level_of_Measurement', value: 'ordinal' },
      ]);
      expect(component.dataDictionary.find(
        (d: any) => d.Feature_Name === 'Var_2').Level_of_Measurement).toBe('ordinal');
      expect(component.dataDictionary.find(
        (d: any) => d.Feature_Name === 'Var_36').Level_of_Measurement).toBe('ordinal');
      // Untouched row stays the same.
      expect(component.dataDictionary.find(
        (d: any) => d.Feature_Name === 'Var_3').Level_of_Measurement).toBe('nominal');
    });

    it('should patch Feature_Description independently of LoM', () => {
      sharedService.emitMetadataUpdates([
        { column: 'Var_3', field: 'Feature_Description', value: 'New legal-action description' },
      ]);
      const var3 = component.dataDictionary.find(
        (d: any) => d.Feature_Name === 'Var_3');
      expect(var3.Feature_Description).toBe('New legal-action description');
      // LoM untouched.
      expect(var3.Level_of_Measurement).toBe('nominal');
    });

    it('should replace the array reference so Angular change detection fires', () => {
      const original = component.dataDictionary;
      sharedService.emitMetadataUpdates([
        { column: 'Var_2', field: 'Level_of_Measurement', value: 'ordinal' },
      ]);
      expect(component.dataDictionary).not.toBe(original);
    });

    it('should ignore updates whose column is not in the dictionary', () => {
      const before = JSON.stringify(component.dataDictionary);
      sharedService.emitMetadataUpdates([
        { column: 'Nonexistent_Var', field: 'Level_of_Measurement', value: 'ordinal' },
      ]);
      // Subject still emits but no row matches → no mutation, no
      // array-ref replacement.
      expect(JSON.stringify(component.dataDictionary)).toBe(before);
    });

    it('should be a no-op when the dictionary is empty', () => {
      component.dataDictionary = [];
      // Should not throw and should leave dataDictionary as empty.
      expect(() => sharedService.emitMetadataUpdates([
        { column: 'Var_2', field: 'Level_of_Measurement', value: 'ordinal' },
      ])).not.toThrow();
      expect(component.dataDictionary).toEqual([]);
    });
  });
});
