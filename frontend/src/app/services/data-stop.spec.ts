import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { DataService } from './data.service';
import { environment } from '../../environments/environment';

describe('Operation-bound search stop transport', () => {
  const operation = '11111111-1111-4111-8111-111111111111';
  let service: DataService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [HttpClientTestingModule] });
    service = TestBed.inject(DataService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());

  for (const kind of ['sfs', 'hyperparam'] as const) {
    const url = `${environment.apiBaseUrl}modeling/${kind}/stop/1/`;
    const stop = (value: any) =>
      kind === 'sfs' ? service.stopSfs(1, value) : service.stopHyperparam(1, value);

    it(`${kind}: sends exactly the accepted operation`, () => {
      stop(operation).subscribe();
      const request = http.expectOne(url);
      expect(request.request.method).toBe('POST');
      expect(request.request.body).toEqual({ operation_id: operation });
      request.flush({ status: 'stop_requested', file_id: 1, operation_id: operation });
    });

    for (const value of [
      undefined,
      null,
      '',
      'old-run',
      1,
      false,
      'ABCDEFAB-1234-1234-1234-ABCDEFABCDEF',
    ]) {
      it(`${kind}: refuses invalid runtime identity ${String(value)} without HTTP`, () => {
        let failure: any;
        stop(value).subscribe({ error: (error) => (failure = error) });
        expect(failure instanceof Error).toBeTrue();
        expect(failure.message).toContain('Refresh status');
        http.expectNone(url);
      });
    }

    it(`${kind}: preserves a conflict response and sends no fallback or retry`, () => {
      let failure: any;
      const payload = {
        error_code: 'search_operation_changed',
        error: 'Refresh status before stopping.',
      };
      stop(operation).subscribe({ error: (error) => (failure = error) });
      http.expectOne(url).flush(payload, { status: 409, statusText: 'Conflict' });
      expect(failure instanceof HttpErrorResponse).toBeTrue();
      expect(failure.status).toBe(409);
      expect(failure.error).toBe(payload);
      http.expectNone(url);
    });
  }
});
