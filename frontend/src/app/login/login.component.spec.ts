import { ComponentFixture, TestBed } from '@angular/core/testing';
import { RouterTestingModule } from '@angular/router/testing';
import { FormsModule } from '@angular/forms';
import { CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { Router } from '@angular/router';
import { of, Subject } from 'rxjs';
import { LoginComponent } from './login.component';
import { AuthService } from '../services/auth.service';

describe('LoginComponent', () => {
  let component: LoginComponent;
  let fixture: ComponentFixture<LoginComponent>;
  let auth: jasmine.SpyObj<AuthService>;
  let router: Router;
  beforeEach(async () => {
    auth = jasmine.createSpyObj<AuthService>('AuthService', ['login']);
    await TestBed.configureTestingModule({
      imports: [RouterTestingModule, FormsModule], declarations: [LoginComponent],
      providers: [{ provide: AuthService, useValue: auth }], schemas: [CUSTOM_ELEMENTS_SCHEMA],
    }).compileComponents();
    fixture = TestBed.createComponent(LoginComponent);
    component = fixture.componentInstance;
    router = TestBed.inject(Router);
  });
  it('starts with empty credentials', () => {
    expect(component.username).toBe('');
    expect(component.password).toBe('');
  });
  it('waits for server acceptance before navigation and clears the password', () => {
    const response = new Subject<boolean>();
    auth.login.and.returnValue(response);
    spyOn(router, 'navigate');
    component.username = 'developer-test';
    component.password = 'synthetic-test-password';
    component.onSubmit();
    component.onSubmit();
    expect(auth.login).toHaveBeenCalledTimes(1);
    expect(router.navigate).not.toHaveBeenCalled();
    response.next(true);
    expect(router.navigate).toHaveBeenCalledWith(['/home']);
    expect(component.password).toBe('');
    expect(component.signingIn).toBeFalse();
  });
  it('explains a failed sign-in', () => {
    auth.login.and.returnValue(of(false));
    spyOn(router, 'navigate');
    component.onSubmit();
    expect(router.navigate).not.toHaveBeenCalled();
    expect(component.errorMessage).toContain('Sign-in failed');
  });
});
