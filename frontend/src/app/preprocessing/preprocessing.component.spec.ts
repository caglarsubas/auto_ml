import { ComponentFixture, TestBed } from '@angular/core/testing';

import { PreprocessingComponent } from './preprocessing.component';

describe('PreprocessingComponent', () => {
  let component: PreprocessingComponent;
  let fixture: ComponentFixture<PreprocessingComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [PreprocessingComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(PreprocessingComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
