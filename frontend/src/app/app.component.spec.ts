import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { RouterTestingModule } from '@angular/router/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatButtonModule } from '@angular/material/button';
import { MatMenuModule } from '@angular/material/menu';
import { AppComponent } from './app.component';
import { AuthService } from './services/auth.service';

describe('AppComponent', () => {
  let component: AppComponent;
  let fixture: ComponentFixture<AppComponent>;
  let authService: AuthService;
  let router: Router;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        RouterTestingModule,
        NoopAnimationsModule,
        MatToolbarModule,
        MatButtonModule,
        MatMenuModule,
      ],
      declarations: [AppComponent],
      providers: [AuthService],
    }).compileComponents();

    fixture = TestBed.createComponent(AppComponent);
    component = fixture.componentInstance;
    authService = TestBed.inject(AuthService);
    router = TestBed.inject(Router);
  });

  it('should create the app', () => {
    expect(component).toBeTruthy();
  });

  it('should have title "declar.ai"', () => {
    expect(component.title).toEqual('declar.ai');
  });

  it('should default to not login page', () => {
    expect(component.isLoginPage).toBeFalse();
  });

  it('should default to not home page', () => {
    expect(component.isHomePage).toBeFalse();
  });

  it('onSignOut should logout and navigate to login', () => {
    spyOn(authService, 'logout');
    spyOn(router, 'navigate');
    component.onSignOut();
    expect(authService.logout).toHaveBeenCalled();
    expect(router.navigate).toHaveBeenCalledWith(['/login']);
  });

  it('should disable unavailable Feature Store menu items', async () => {
    component.isBrowser = true;
    component.isLoginPage = false;
    fixture.detectChanges();

    const triggers = fixture.nativeElement.querySelectorAll('a[mat-button]');
    const featureStoreTrigger = Array.from(triggers as NodeListOf<HTMLElement>)
      .find(el => el.textContent?.trim() === 'Feature Store');
    expect(featureStoreTrigger).toBeTruthy();
    featureStoreTrigger!.click();
    fixture.detectChanges();
    await fixture.whenStable();

    const items = Array.from(
      document.querySelectorAll('.mat-mdc-menu-panel .mat-mdc-menu-item') as NodeListOf<HTMLButtonElement>
    );
    expect(items.length).toBe(3);

    const byLabel = Object.fromEntries(
      items.map(el => [el.textContent?.trim() || '', el.disabled])
    );
    expect(byLabel['Feature Collection']).toBeFalse();
    expect(byLabel['Feature Engineering']).toBeTrue();
    expect(byLabel['Feature Monitoring']).toBeTrue();
  });
});

