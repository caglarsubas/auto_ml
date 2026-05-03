import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { FormsModule } from '@angular/forms';
import { CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { MatDialogModule, MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { FeatureCardComponent } from './feature-card.component';
import { SharedService } from '../services/shared.service';
import { DataService } from '../services/data.service';

describe('FeatureCardComponent', () => {
  let component: FeatureCardComponent;
  let fixture: ComponentFixture<FeatureCardComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        HttpClientTestingModule,
        FormsModule,
        MatDialogModule,
        BrowserAnimationsModule,
      ],
      declarations: [FeatureCardComponent],
      providers: [
        SharedService,
        DataService,
        { provide: MAT_DIALOG_DATA, useValue: { fileId: '1', columnName: 'Age', features: [] } },
        { provide: MatDialogRef, useValue: { close: jasmine.createSpy('close') } },
      ],
      schemas: [CUSTOM_ELEMENTS_SCHEMA],
    }).compileComponents();

    fixture = TestBed.createComponent(FeatureCardComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should receive dialog data with fileId and columnName', () => {
    expect(component.data.fileId).toBe('1');
    expect(component.data.columnName).toBe('Age');
  });

  it('should default currentTabIndex to 0 (Descriptives)', () => {
    expect(component.currentTabIndex).toBe(0);
  });

  it('should have null featureData initially', () => {
    expect(component.featureData).toBeNull();
  });

  it('should have null errorMessage initially', () => {
    expect(component.errorMessage).toBeNull();
  });

  it('should default dataVersion to "raw" (no processed/encoded files)', () => {
    expect(component.dataVersion).toBe('raw');
  });

  it('should initialize isCategorical as false', () => {
    expect(component.isCategorical).toBeFalse();
  });

  it('should have numericalStats array defined', () => {
    expect(component.numericalStats.length).toBeGreaterThan(0);
    expect(component.numericalStats).toContain('Mean');
    expect(component.numericalStats).toContain('Std');
  });

  it('should have categoricalStats array defined', () => {
    expect(component.categoricalStats).toContain('#_of_Categories');
    expect(component.categoricalStats).toContain('Mode_Value');
  });

  it('should default selectedImportanceType to shap', () => {
    expect(component.selectedImportanceType).toBe('shap');
  });
});
