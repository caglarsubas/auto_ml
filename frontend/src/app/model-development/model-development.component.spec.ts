import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { RouterTestingModule } from '@angular/router/testing';
import { FormsModule } from '@angular/forms';
import { CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { MatDialogModule } from '@angular/material/dialog';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBarModule } from '@angular/material/snack-bar';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { ModelDevelopmentComponent } from './model-development.component';
import { SharedService } from '../services/shared.service';
import { DataService } from '../services/data.service';
import { AiAssistantService } from '../services/ai-assistant.service';

describe('ModelDevelopmentComponent', () => {
  let component: ModelDevelopmentComponent;
  let fixture: ComponentFixture<ModelDevelopmentComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        HttpClientTestingModule,
        RouterTestingModule,
        FormsModule,
        MatDialogModule,
        MatSelectModule,
        MatSnackBarModule,
        BrowserAnimationsModule,
      ],
      declarations: [ModelDevelopmentComponent],
      providers: [SharedService, DataService, AiAssistantService],
      schemas: [CUSTOM_ELEMENTS_SCHEMA],
    }).compileComponents();

    fixture = TestBed.createComponent(ModelDevelopmentComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should have menu items for pipeline steps', () => {
    expect(component.menuItems).toContain('declaration');
    expect(component.menuItems).toContain('modeling');
    expect(component.menuItems).toContain('deployment');
  });

  it('should default currentStep to declaration', () => {
    expect(component.currentStep).toBe('declaration');
  });

  it('should default selectedPipeline to empty string', () => {
    expect(component.selectedPipeline).toBe('');
  });

  it('should have showSteps flags all false initially', () => {
    expect(component.showSteps['declaration']).toBeFalse();
    expect(component.showSteps['modeling']).toBeFalse();
  });
});
