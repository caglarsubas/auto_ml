import { ComponentFixture, TestBed } from '@angular/core/testing';
import { RouterTestingModule } from '@angular/router/testing';
import { CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { HomeComponent } from './home.component';

describe('HomeComponent', () => {
  let component: HomeComponent;
  let fixture: ComponentFixture<HomeComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [RouterTestingModule],
      declarations: [HomeComponent],
      schemas: [CUSTOM_ELEMENTS_SCHEMA],
    }).compileComponents();

    fixture = TestBed.createComponent(HomeComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should have 5 menu items', () => {
    expect(component.menuItems.length).toBe(5);
  });

  it('menu items should include Feature Store and Model Store', () => {
    const names = component.menuItems.map(m => m.name);
    expect(names).toContain('Feature Store');
    expect(names).toContain('Model Store');
    expect(names).toContain('Deployments');
    expect(names).toContain('Reporting');
    expect(names).toContain('About');
  });

  it('Model Store should include Model Development sub-item', () => {
    const modelStore = component.menuItems.find(m => m.name === 'Model Store');
    expect(modelStore!.subItems).toContain('Model Development');
  });
});
