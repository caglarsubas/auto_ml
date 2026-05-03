import { TestBed } from '@angular/core/testing';
import { AuthService } from './auth.service';

describe('AuthService', () => {
  let service: AuthService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(AuthService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  describe('login', () => {
    it('should return true for valid credentials', () => {
      expect(service.login('caglarsubas@gmail.com', 'con3e7ne')).toBeTrue();
    });

    it('should emit isLoggedIn true after valid login', (done) => {
      service.login('caglarsubas@gmail.com', 'con3e7ne');
      service.isLoggedIn$.subscribe(val => {
        expect(val).toBeTrue();
        done();
      });
    });

    it('should return false for invalid username', () => {
      expect(service.login('wrong@email.com', 'con3e7ne')).toBeFalse();
    });

    it('should return false for invalid password', () => {
      expect(service.login('caglarsubas@gmail.com', 'wrongpass')).toBeFalse();
    });

    it('should not set isLoggedIn on failed login', (done) => {
      service.login('wrong@email.com', 'wrong');
      service.isLoggedIn$.subscribe(val => {
        expect(val).toBeFalse();
        done();
      });
    });
  });

  describe('logout', () => {
    it('should set isLoggedIn to false', (done) => {
      service.login('caglarsubas@gmail.com', 'con3e7ne');
      service.logout();
      service.isLoggedIn$.subscribe(val => {
        expect(val).toBeFalse();
        done();
      });
    });
  });
});
