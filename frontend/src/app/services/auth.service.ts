import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, of } from 'rxjs';
import { catchError, map, switchMap, tap } from 'rxjs/operators';
import { environment } from '../../environments/environment';

interface SessionResponse {
  authenticated: boolean;
  csrf_token: string;
  user: { id: number; username: string } | null;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly status = new BehaviorSubject<boolean>(false);
  readonly isLoggedIn$ = this.status.asObservable();
  csrfToken = '';
  user: SessionResponse['user'] = null;
  readonly apiRoot = environment.apiBaseUrl.replace(/\/?$/, '/');

  constructor(private http: HttpClient) {}

  private accept(session: SessionResponse): boolean {
    this.csrfToken = session.csrf_token;
    this.user = session.user;
    this.status.next(session.authenticated);
    return session.authenticated;
  }

  invalidate(): void {
    this.user = null;
    this.status.next(false);
  }

  refresh(): Observable<boolean> {
    // Identity responses are private and must always reflect the current session.
    return this.http.get<SessionResponse>(`${this.apiRoot}auth/session/`, {
      withCredentials: true, transferCache: false,
    }).pipe(
      map(session => this.accept(session)),
      catchError(() => { this.invalidate(); return of(false); }),
    );
  }

  login(username: string, password: string): Observable<boolean> {
    return this.refresh().pipe(
      switchMap(() => this.http.post<SessionResponse>(`${this.apiRoot}auth/login/`, { username, password }, {
        withCredentials: true, headers: { 'X-CSRFToken': this.csrfToken },
      })),
      map(session => this.accept(session)),
      catchError(() => { this.invalidate(); return of(false); }),
    );
  }

  logout(): Observable<boolean> {
    return this.http.post<SessionResponse>(`${this.apiRoot}auth/logout/`, {}, {
      withCredentials: true, headers: { 'X-CSRFToken': this.csrfToken },
    }).pipe(
      tap(session => this.accept(session)),
      map(() => true),
      catchError(() => of(false)),
    );
  }
}
