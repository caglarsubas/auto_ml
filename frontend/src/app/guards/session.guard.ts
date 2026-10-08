import { Injectable } from '@angular/core';
import { CanActivate, Router } from '@angular/router';
import { map } from 'rxjs/operators';
import { AuthService } from '../services/auth.service';

@Injectable({ providedIn: 'root' })
export class SessionGuard implements CanActivate {
  constructor(private auth: AuthService, private router: Router) {}
  canActivate() {
    return this.auth.refresh().pipe(map(valid => valid || this.router.createUrlTree(['/login'])));
  }
}
