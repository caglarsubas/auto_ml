import { ComponentFixture, TestBed } from '@angular/core/testing';
import { RouterTestingModule } from '@angular/router/testing';
import { FormsModule } from '@angular/forms';
import { CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { Router } from '@angular/router';
import { LoginComponent } from './login.component';
import { AuthService } from '../services/auth.service';

describe('LoginComponent', () => {
  let component: LoginComponent;
  let fixture: ComponentFixture<LoginComponent>;
  let authService: AuthService;
  let router: Router;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [RouterTestingModule, FormsModule],
      declarations: [LoginComponent],
      providers: [AuthService],
      schemas: [CUSTOM_ELEMENTS_SCHEMA],
    }).compileComponents();

    fixture = TestBed.createComponent(LoginComponent);
    component = fixture.componentInstance;
    authService = TestBed.inject(AuthService);
    router = TestBed.inject(Router);
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should have empty credentials initially', () => {
    expect(component.username).toBe('');
    expect(component.password).toBe('');
    expect(component.errorMessage).toBe('');
  });

  it('onSubmit should navigate to /home on valid login', () => {
    spyOn(router, 'navigate');
    component.username = 'caglarsubas@gmail.com';
    component.password = 'con3e7ne';
    component.onSubmit();
    expect(router.navigate).toHaveBeenCalledWith(['/home']);
    expect(component.errorMessage).toBe('');
  });

  it('onSubmit should set errorMessage on invalid login', () => {
    spyOn(router, 'navigate');
    component.username = 'wrong@test.com';
    component.password = 'bad';
    component.onSubmit();
    expect(router.navigate).not.toHaveBeenCalled();
    expect(component.errorMessage).toBe('Invalid username or password');
  });
});
