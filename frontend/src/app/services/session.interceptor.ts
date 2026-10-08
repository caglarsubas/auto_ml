import { Injectable } from '@angular/core';
import { HttpEvent, HttpHandler, HttpInterceptor, HttpRequest } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { AuthService } from './auth.service';

@Injectable()
export class SessionInterceptor implements HttpInterceptor {
  constructor(private auth: AuthService) {}

  intercept(request: HttpRequest<unknown>, next: HttpHandler): Observable<HttpEvent<unknown>> {
    const managed = request.url.startsWith(this.auth.apiRoot)
      || request.url.startsWith(this.auth.apiRoot.replace(/api\/$/, 'media/'));
    if (!managed) return next.handle(request);
    const unsafe = !['GET', 'HEAD', 'OPTIONS'].includes(request.method);
    const headers: Record<string, string> = unsafe && this.auth.csrfToken ? { 'X-CSRFToken': this.auth.csrfToken } : {};
    return next.handle(request.clone({ withCredentials: true, setHeaders: headers })).pipe(
      catchError(error => {
        if (error.status === 401 || (error.status === 403 && error.error?.detail?.includes('Authentication credentials'))) {
          this.auth.invalidate();
        }
        return throwError(() => error);
      }),
    );
  }
}
