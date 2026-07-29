import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
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
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should have 5 directory sections', () => {
    expect(component.sections.length).toBe(5);
  });

  it('sections should include Feature Store and Model Store', () => {
    const names = component.sections.map(s => s.name);
    expect(names).toContain('Feature Store');
    expect(names).toContain('Model Store');
    expect(names).toContain('Deployments');
    expect(names).toContain('Reporting');
    expect(names).toContain('About');
  });

  it('Model Development and Feature Collection should be live with routes', () => {
    const modelDev = component.sections
      .flatMap(s => s.items)
      .find(i => i.label === 'Model Development');
    const featureCollection = component.sections
      .flatMap(s => s.items)
      .find(i => i.label === 'Feature Collection');

    expect(modelDev).toEqual({
      label: 'Model Development',
      route: '/model-development',
      status: 'live',
    });
    expect(featureCollection).toEqual({
      label: 'Feature Collection',
      route: '/feature-store/collections',
      status: 'live',
    });
  });

  it('non-live items should be unavailable without routes', () => {
    const unavailable = component.sections
      .flatMap(s => s.items)
      .filter(i => i.label !== 'Model Development' && i.label !== 'Feature Collection');

    expect(unavailable.length).toBeGreaterThan(0);
    unavailable.forEach(item => {
      expect(item.status).toBe('unavailable');
      expect(item.route).toBeUndefined();
    });
  });

  it('primary CTA should link to model development', () => {
    const cta = fixture.debugElement.query(By.css('[data-testid="home-primary-cta"]'));
    expect(cta).toBeTruthy();
    expect(cta.attributes['ng-reflect-router-link']).toBe('/model-development');
  });
});
