import { ComponentFixture, TestBed } from '@angular/core/testing';

import { DeclarationComponent } from './declaration.component';

describe('DataCollectionComponent', () => {
  let component: DeclarationComponent;
  let fixture: ComponentFixture<DeclarationComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [DeclarationComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(DeclarationComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
