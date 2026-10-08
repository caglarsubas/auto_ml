import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { AuthService } from './auth.service';

describe('AuthService server sessions', () => {
  let service: AuthService;
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [HttpClientTestingModule] });
    service = TestBed.inject(AuthService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());

  it('accepts a login only after the server returns an authenticated session', () => {
    let result: boolean | undefined;
    service.login('developer-test', 'synthetic-test-password').subscribe(value => result = value);
    const session = http.expectOne(`${service.apiRoot}auth/session/`);
    expect(session.request.withCredentials).toBeTrue();
    session.flush({ authenticated: false, csrf_token: 'initial-csrf', user: null });
    const login = http.expectOne(`${service.apiRoot}auth/login/`);
    expect(login.request.headers.get('X-CSRFToken')).toBe('initial-csrf');
    expect(result).toBeUndefined();
    login.flush({ authenticated: true, csrf_token: 'rotated-csrf', user: { id: 1, username: 'developer-test' } });
    expect(result).toBeTrue();
    expect(service.csrfToken).toBe('rotated-csrf');
    expect(service.user?.id).toBe(1);
  });

  it('does not authenticate on rejected credentials or a network failure', () => {
    let result: boolean | undefined;
    service.login('developer-test', 'wrong').subscribe(value => result = value);
    http.expectOne(`${service.apiRoot}auth/session/`).flush({ authenticated: false, csrf_token: 'csrf', user: null });
    http.expectOne(`${service.apiRoot}auth/login/`).flush({ error: 'Invalid credentials' }, { status: 401, statusText: 'Unauthorized' });
    expect(result).toBeFalse();
    expect(service.user).toBeNull();
  });

  it('restores and revokes session state through the server', () => {
    service.refresh().subscribe();
    http.expectOne(`${service.apiRoot}auth/session/`).flush({ authenticated: true, csrf_token: 'csrf', user: { id: 1, username: 'developer-test' } });
    let completed: boolean | undefined;
    service.logout().subscribe(value => completed = value);
    const request = http.expectOne(`${service.apiRoot}auth/logout/`);
    expect(request.request.headers.get('X-CSRFToken')).toBe('csrf');
    request.flush({ authenticated: false, csrf_token: 'new-csrf', user: null });
    expect(completed).toBeTrue();
    expect(service.user).toBeNull();
  });
});
