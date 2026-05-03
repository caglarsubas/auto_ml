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
});
