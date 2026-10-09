import { Injectable } from '@angular/core';
import { ActivatedRouteSnapshot, CanActivate, Router } from '@angular/router';
import { map } from 'rxjs/operators';
import { ProjectWorkspaceService } from '../services/project-workspace.service';

@Injectable({ providedIn: 'root' })
export class ProjectWorkspaceGuard implements CanActivate {
  constructor(
    private workspace: ProjectWorkspaceService,
    private router: Router,
  ) {}
  canActivate(route: ActivatedRouteSnapshot) {
    const project = route.queryParamMap.get('project_id');
    // A live component must never be relabeled as another project. Change at home.
    if (
      this.router.url.startsWith('/model-development') &&
      project &&
      this.workspace.projectId &&
      project !== this.workspace.projectId
    ) {
      return this.router.createUrlTree(['/home'], { queryParams: { project_id: project } });
    }
    return this.workspace.refresh(project).pipe(
      map((state) => {
        if (state.ready && (state.governed === false || state.selected?.role === 'developer'))
          return true;
        return this.router.createUrlTree(['/home'], {
          queryParams: project ? { project_id: project } : {},
        });
      }),
    );
  }
}
