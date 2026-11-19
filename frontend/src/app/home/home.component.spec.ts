import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { RouterTestingModule } from '@angular/router/testing';
import { CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { HomeComponent } from './home.component';
import { ProjectWorkspaceService } from '../services/project-workspace.service';

describe('HomeComponent', () => {
  let component: HomeComponent;
  let fixture: ComponentFixture<HomeComponent>;
  let workspace: { state: { governed: boolean; selected: any }; projectId?: string };

  beforeEach(async () => {
    workspace = { state: { governed: false, selected: null } };
    await TestBed.configureTestingModule({
      imports: [RouterTestingModule],
      declarations: [HomeComponent],
      schemas: [CUSTOM_ELEMENTS_SCHEMA],
      providers: [{ provide: ProjectWorkspaceService, useValue: workspace }],
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
    const names = component.sections.map((s) => s.name);
    expect(names).toContain('Feature Store');
    expect(names).toContain('Model Store');
    expect(names).toContain('Deployments');
    expect(names).toContain('Reporting');
    expect(names).toContain('About');
  });

  it('Model Development should be live with a route', () => {
    const modelDev = component.sections
      .flatMap((s) => s.items)
      .find((i) => i.label === 'Model Development');

    expect(modelDev).toEqual({
      label: 'Model Development',
      route: '/model-development',
      status: 'live',
    });
  });

  it('non-live items should be unavailable without routes', () => {
    const unavailable = component.sections
      .flatMap((s) => s.items)
      .filter((i) => i.label !== 'Model Development');

    expect(unavailable.length).toBeGreaterThan(0);
    unavailable.forEach((item) => {
      expect(item.status).toBe('unavailable');
      expect(item.route).toBeUndefined();
    });
  });

  it('primary CTA should link to model development', () => {
    const cta = fixture.debugElement.query(By.css('[data-testid="home-primary-cta"]'));
    expect(cta).toBeTruthy();
    expect(cta.nativeElement.getAttribute('href')).toBe('/model-development');
  });

  it('secondary CTA should link to declaration', () => {
    const cta = fixture.debugElement.query(By.css('[data-testid="home-secondary-cta"]'));
    expect(cta).toBeTruthy();
    expect(cta.nativeElement.getAttribute('href')).toBe('/model-development/declaration');
  });

  it('guides reviewers to project records and keeps developer links in their selected project', () => {
    workspace.state = { governed: true, selected: { role: 'reviewer' } };
    workspace.projectId = 'review-project';
    fixture.detectChanges();
    const primary = fixture.nativeElement.querySelector('[data-testid="home-primary-cta"]');
    expect(primary.textContent).toContain('Open project records');
    expect(primary.getAttribute('href')).toBe('#workspace-title');
    expect(fixture.nativeElement.querySelector('[data-testid="home-secondary-cta"]')).toBeNull();
    workspace.state = { governed: true, selected: { role: 'developer' } };
    workspace.projectId = 'development-project';
    fixture.detectChanges();
    expect(
      fixture.nativeElement.querySelector('[data-testid="home-primary-cta"]').getAttribute('href'),
    ).toBe('/model-development?project_id=development-project');
    expect(
      fixture.nativeElement
        .querySelector('[data-testid="home-secondary-cta"]')
        .getAttribute('href'),
    ).toBe('/model-development/declaration?project_id=development-project');
  });

  it('should render evidence margin notes', () => {
    expect(component.evidenceNotes.length).toBe(3);
    const evidence = fixture.debugElement.query(By.css('.home-evidence'));
    expect(evidence).toBeTruthy();
  });

  it('should use authored brand mark without happy talk', () => {
    const brand = fixture.debugElement.query(By.css('.home-brand'));
    expect(brand.nativeElement.textContent.trim()).toBe('declar.ai');
    expect(fixture.nativeElement.textContent).not.toContain('Welcome to');
    expect(fixture.nativeElement.textContent).not.toContain('Democratizing');
  });

  it('should render monoline section icons for each directory block', () => {
    const icons = fixture.debugElement.queryAll(By.css('[data-testid="home-section-icon"]'));
    expect(icons.length).toBe(5);
    component.sections.forEach((section) => {
      expect(section.icon).toBeTruthy();
    });
  });
});
