import { TestBed } from '@angular/core/testing';
import { HTTP_INTERCEPTORS, HttpClient } from '@angular/common/http';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { AuthService } from './auth.service';
import { SessionInterceptor } from './session.interceptor';

describe('SessionInterceptor credential boundary', () => {
  let http: HttpClient;
  let requests: HttpTestingController;
  const auth = { apiRoot: 'http://localhost:8002/api/', csrfToken: 'synthetic-csrf', invalidate: jasmine.createSpy('invalidate') };
  beforeEach(() => {
    auth.invalidate.calls.reset();
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [
        { provide: AuthService, useValue: auth },
        { provide: HTTP_INTERCEPTORS, useClass: SessionInterceptor, multi: true },
      ],
    });
    http = TestBed.inject(HttpClient);
    requests = TestBed.inject(HttpTestingController);
  });
  afterEach(() => requests.verify());

  it('sends session cookies and CSRF only to managed unsafe requests', () => {
    http.post(`${auth.apiRoot}modeling/start/`, {}).subscribe();
    const request = requests.expectOne(`${auth.apiRoot}modeling/start/`);
    expect(request.request.withCredentials).toBeTrue();
    expect(request.request.headers.get('X-CSRFToken')).toBe('synthetic-csrf');
    request.flush({});
  });

  it('protects artifact access without adding CSRF to safe requests', () => {
    const url = 'http://localhost:8002/media/bundles/evidence.json';
    http.get(url).subscribe();
    const request = requests.expectOne(url);
    expect(request.request.withCredentials).toBeTrue();
    expect(request.request.headers.has('X-CSRFToken')).toBeFalse();
    request.flush({});
  });

  it('does not send identity headers or cookies to another origin', () => {
    const url = 'https://example.test/api/modeling/start/';
    http.post(url, {}).subscribe();
    const request = requests.expectOne(url);
    expect(request.request.withCredentials).toBeFalse();
    expect(request.request.headers.has('X-CSRFToken')).toBeFalse();
    request.flush({});
  });

  it('invalidates a revoked session while retaining authorization errors', () => {
    http.get(`${auth.apiRoot}declaration/`).subscribe({ error: () => undefined });
    requests.expectOne(`${auth.apiRoot}declaration/`).flush(
      { detail: 'Authentication credentials were not provided.' }, { status: 403, statusText: 'Forbidden' },
    );
    expect(auth.invalidate).toHaveBeenCalledTimes(1);
    http.get(`${auth.apiRoot}pipeline/`).subscribe({ error: () => undefined });
    requests.expectOne(`${auth.apiRoot}pipeline/`).flush(
      { detail: 'You do not have permission.' }, { status: 403, statusText: 'Forbidden' },
    );
    expect(auth.invalidate).toHaveBeenCalledTimes(1);
  });
});
