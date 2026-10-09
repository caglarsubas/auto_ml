import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, of } from 'rxjs';
import { catchError, map } from 'rxjs/operators';
import { AuthService } from './auth.service';

export interface WorkspaceProject {
  id: string;
  name: string;
  role: 'developer' | 'reviewer' | 'admin';
  membership_revision: string;
}
export interface WorkspaceDirectory {
  governed: boolean;
  projects: WorkspaceProject[];
}
export interface WorkspaceState {
  ready: boolean;
  loading: boolean;
  governed: boolean | null;
  projects: WorkspaceProject[];
  selected: WorkspaceProject | null;
  error: string;
}
const emptyState = (): WorkspaceState => ({
  ready: false,
  loading: false,
  governed: null,
  projects: [],
  selected: null,
  error: '',
});

@Injectable({ providedIn: 'root' })
export class ProjectWorkspaceService {
  private readonly stateSubject = new BehaviorSubject<WorkspaceState>(emptyState());
  readonly state$ = this.stateSubject.asObservable();
  private generation = 0;
  get state(): WorkspaceState {
    return this.stateSubject.value;
  }
  get projectId(): string | undefined {
    return this.state.selected?.id;
  }

  constructor(
    private http: HttpClient,
    private auth: AuthService,
  ) {
    auth.isLoggedIn$.subscribe((valid) => {
      if (!valid) {
        this.generation++;
        this.stateSubject.next(emptyState());
      }
    });
  }

  refresh(preferred?: string | null): Observable<WorkspaceState> {
    const requested = preferred ?? this.projectId;
    const governed = this.state.governed;
    const generation = ++this.generation;
    this.stateSubject.next({ ...emptyState(), loading: true, governed });
    return this.http
      .get<WorkspaceDirectory>(`${this.auth.apiRoot}projects/`, {
        transferCache: false,
      })
      .pipe(
        map((directory) => {
          if (generation !== this.generation) return this.state;
          const selected = requested
            ? (directory.projects.find((p) => p.id === requested) ?? null)
            : directory.projects.length === 1
              ? directory.projects[0]
              : null;
          const state: WorkspaceState = {
            ready: true,
            loading: false,
            governed: directory.governed,
            projects: directory.projects,
            selected,
            error:
              requested && !selected
                ? 'That project is unavailable. Select a current project or ask its administrator for access.'
                : '',
          };
          this.stateSubject.next(state);
          return state;
        }),
        catchError(() => {
          if (generation === this.generation)
            this.stateSubject.next({
              ...emptyState(),
              governed,
              error: 'Project access could not be checked. Retry to load the workspace.',
            });
          return of(this.state);
        }),
      );
  }

  select(id: string): void {
    if (!this.state.ready) return;
    this.stateSubject.next({
      ...this.state,
      selected: this.state.projects.find((p) => p.id === id) ?? null,
      error: '',
    });
  }

  creationPayload<T extends Record<string, unknown>>(payload: T): T & { project_id?: string } {
    if (this.state.governed !== true) return payload;
    if (!this.state.ready || this.state.selected?.role !== 'developer') {
      throw new Error('Select a project where you have the developer role before creating work.');
    }
    if (payload['project_id'] && payload['project_id'] !== this.projectId) {
      throw new Error(
        'New work must belong to the current project. Return home to change projects.',
      );
    }
    return { ...payload, project_id: this.projectId };
  }

  appendProject(form: FormData): void {
    const project = this.creationPayload({}).project_id;
    if (project) form.set('project_id', project);
  }
}
