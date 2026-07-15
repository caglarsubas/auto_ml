import { ComponentFixture, TestBed } from '@angular/core/testing';
import { CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { PreprocessingComponent } from './preprocessing.component';

// NOTE: PreprocessingComponent is an intentional empty shell — its behaviour was
// moved into ModelDevelopmentComponent (see model-development.component.spec.ts
// for the real coverage). A creation smoke test is the appropriate scope here.
describe('PreprocessingComponent', () => {
  let component: PreprocessingComponent;
  let fixture: ComponentFixture<PreprocessingComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [PreprocessingComponent],
      schemas: [CUSTOM_ELEMENTS_SCHEMA],
    }).compileComponents();

    fixture = TestBed.createComponent(PreprocessingComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
