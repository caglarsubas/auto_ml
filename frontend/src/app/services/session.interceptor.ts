import { Injectable } from '@angular/core';
import { HttpEvent, HttpHandler, HttpInterceptor, HttpRequest } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { AuthService } from './auth.service';

@Injectable()
export class SessionInterceptor implements HttpInterceptor {
  constructor(private auth: AuthService) {}

  intercept(request: HttpRequest<unknown>, next: HttpHandler): Observable<HttpEvent<unknown>> {
    // Resolve relative private-installation URLs and absolute artifact URLs
    // against the same origin before applying the credential boundary.
    const base = new URL(this.auth.apiRoot, window.location.origin);
    const url = new URL(request.url, window.location.origin);
    const managed = url.origin === base.origin && (
      url.pathname.startsWith(base.pathname)
      || url.pathname.startsWith(base.pathname.replace(/api\/$/, 'media/'))
    );
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
