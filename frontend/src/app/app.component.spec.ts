import { ComponentFixture, TestBed } from '@angular/core/testing';
import { RouterTestingModule } from '@angular/router/testing';
import { CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { AppComponent } from './app.component';
import { AuthService } from './services/auth.service';

describe('AppComponent', () => {
  let component: AppComponent;
  let fixture: ComponentFixture<AppComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [RouterTestingModule],
      declarations: [AppComponent],
      providers: [AuthService],
      schemas: [CUSTOM_ELEMENTS_SCHEMA],
    }).compileComponents();

    fixture = TestBed.createComponent(AppComponent);
    component = fixture.componentInstance;
  });

  it('should create the app', () => {
    expect(component).toBeTruthy();
  });

  it('should have title "frontend"', () => {
    expect(component.title).toEqual('frontend');
  });

  it('should default to not login page', () => {
    expect(component.isLoginPage).toBeFalse();
  });

  it('should default to not home page', () => {
    expect(component.isHomePage).toBeFalse();
  });

  it('shouldShowFullMenu returns true when not login and not home', () => {
    component.isLoginPage = false;
    component.isHomePage = false;
    expect(component.shouldShowFullMenu()).toBeTrue();
  });

  it('shouldShowFullMenu returns false on login page', () => {
    component.isLoginPage = true;
    expect(component.shouldShowFullMenu()).toBeFalse();
  });

  it('shouldShowFullMenu returns false on home page', () => {
    component.isHomePage = true;
    expect(component.shouldShowFullMenu()).toBeFalse();
  });

  it('magnifier properties should have defaults', () => {
    expect(component.magnifierSize).toBe(120);
    expect(component.zoomLevel).toBe(2.5);
    expect(component.showMagnifier).toBeFalse();
  });
});
