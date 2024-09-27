// model-development.guard.ts
import { Injectable } from '@angular/core';
import { CanActivate, ActivatedRouteSnapshot, RouterStateSnapshot, UrlTree, Router } from '@angular/router';
import { Observable } from 'rxjs';
import { ModelDevelopmentService } from '../services/model-development.service';
import { map, tap } from 'rxjs/operators';

@Injectable({
  providedIn: 'root'
})
export class ModelDevelopmentGuard implements CanActivate {
  constructor(
    private modelDevelopmentService: ModelDevelopmentService,
    private router: Router
  ) {}

  canActivate(
    route: ActivatedRouteSnapshot,
    state: RouterStateSnapshot): Observable<boolean | UrlTree> | Promise<boolean | UrlTree> | boolean | UrlTree {
    console.log('ModelDevelopmentGuard: Checking if started');
    return this.modelDevelopmentService.isStarted$.pipe(
      tap(isStarted => console.log('ModelDevelopmentGuard: Is started:', isStarted)),
      map(isStarted => {
        if (isStarted) {
          console.log('ModelDevelopmentGuard: Allowing navigation');
          return true;
        } else {
          console.log('ModelDevelopmentGuard: Redirecting to model-development/select');
          return this.router.createUrlTree(['/model-development/select']);
        }
      })
    );
  }
}