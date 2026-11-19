import { downloadBlob } from '../utils/download-blob';
import { Component, OnDestroy, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, ParamMap, Router } from '@angular/router';
import { forkJoin, of, Subscription } from 'rxjs';
import { catchError, distinctUntilChanged, map, switchMap } from 'rxjs/operators';
import { DataService } from '../services/data.service';
import { ProjectWorkspaceService } from '../services/project-workspace.service';
import { ProjectMembershipComponent } from '../project-membership/project-membership.component';
import { PackageReviewComponent } from '../package-review/package-review.component';
import { TrainingLaunchComponent } from '../training-launch/training-launch.component';

@Component({
  selector: 'app-project-workspace',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ProjectMembershipComponent,
    PackageReviewComponent,
    TrainingLaunchComponent,
  ],
  templateUrl: './project-workspace.component.html',
  styleUrl: './project-workspace.component.css',
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class ProjectWorkspaceComponent implements OnInit, OnDestroy {
  datasets: any[] = [];
  pipelines: any[] = [];
  loading = false;
  recordsError = '';
  reportError = '';
  panelError = '';
  reviewDataset: number | null = null;
  trainingDataset: any = null;
  private preferredProject: string | null = null;
  private navigation: ParamMap | null = null;
  private readonly subscriptions = new Subscription();
  constructor(
    public workspace: ProjectWorkspaceService,
    private data: DataService,
    private route: ActivatedRoute,
    private router: Router,
  ) {}

  ngOnInit(): void {
    this.subscriptions.add(
      this.workspace.state$
        .pipe(
          map((state) => (state.ready && state.governed ? state.selected : null)),
          distinctUntilChanged(
            (before, after) =>
              before?.id === after?.id &&
              before?.role === after?.role &&
              before?.membership_revision === after?.membership_revision,
          ),
          switchMap((selected) => {
            const project = selected?.id;
            this.datasets = [];
            this.pipelines = [];
            this.recordsError = '';
            this.reportError = '';
            this.panelError = '';
            this.reviewDataset = null;
            this.trainingDataset = null;
            this.loading = !!project;
            if (!project) return of(null);
            return forkJoin({
              datasets: this.data.listDatasets(project),
              pipelines: this.data.listPipelineRuns(project),
            }).pipe(
              catchError(() => {
                this.recordsError =
                  'Project records could not be loaded. Refresh access and retry.';
                return of(null);
              }),
            );
          }),
        )
        .subscribe((records) => {
          this.loading = false;
          this.datasets = records?.datasets ?? [];
          this.pipelines = records?.pipelines ?? [];
          this.resolvePanel();
        }),
    );
    this.subscriptions.add(
      this.route.queryParamMap.subscribe((params) => {
        this.navigation = params;
        this.preferredProject = params.get('project_id');
        if (
          this.workspace.state.ready &&
          this.workspace.state.governed &&
          this.preferredProject !== (this.workspace.projectId ?? null)
        ) {
          this.workspace.select(this.preferredProject ?? '');
        }
        this.resolvePanel();
      }),
    );
    this.refresh();
  }
  refresh(): void {
    this.subscriptions.add(this.workspace.refresh(this.preferredProject).subscribe());
  }
  select(projectId: string): void {
    this.preferredProject = projectId;
    this.reviewDataset = null;
    this.trainingDataset = null;
    this.workspace.select(projectId);
    this.navigate({ project_id: projectId || null, dataset_id: null, view: null });
  }
  showPanel(dataset: any, view: 'training' | 'review'): void {
    if (
      !this.workspace.projectId ||
      this.loading ||
      this.recordsError ||
      !this.datasets.some((row) => row.id === dataset.id)
    )
      return;
    this.navigate({
      project_id: this.workspace.projectId,
      dataset_id: dataset.id,
      view,
    });
  }
  closePanel(): void {
    this.reviewDataset = null;
    this.trainingDataset = null;
    this.navigate({ dataset_id: null, view: null });
  }
  private navigate(queryParams: Record<string, string | number | null>): void {
    this.router
      .navigate([], {
        relativeTo: this.route,
        queryParams,
        queryParamsHandling: 'merge',
      })
      .catch(() => {
        this.panelError =
          'Workspace navigation could not be updated. Refresh access and try again.';
      });
  }
  private resolvePanel(): void {
    this.reviewDataset = null;
    this.trainingDataset = null;
    this.panelError = '';
    const state = this.workspace.state;
    if (!state.ready || !state.selected || this.loading || this.recordsError || !this.navigation)
      return;
    const dataset = this.navigation.get('dataset_id');
    const view = this.navigation.get('view');
    if (!dataset && !view) return;
    if (
      this.navigation.getAll('dataset_id').length !== 1 ||
      this.navigation.getAll('view').length !== 1 ||
      !dataset ||
      !/^[1-9][0-9]*$/.test(dataset) ||
      !['training', 'review'].includes(view ?? '')
    ) {
      this.panelError = 'Choose a dataset below to open its training jobs or review evidence.';
      return;
    }
    const selected = this.datasets.find((row) => String(row.id) === dataset);
    if (!selected) {
      this.panelError =
        'This dataset is unavailable in the current project. Choose an accessible dataset below.';
      return;
    }
    if (view === 'training') this.trainingDataset = selected;
    else this.reviewDataset = selected.id;
  }
  report(run: any): void {
    const project = this.workspace.projectId;
    this.reportError = '';
    this.subscriptions.add(
      this.data.downloadPipelineReport(run.id, project).subscribe({
        next: (blob) => {
          if (project !== this.workspace.projectId) return;
          downloadBlob(blob, `pipeline-${run.id}-report.html`);
        },
        error: () => {
          if (project === this.workspace.projectId)
            this.reportError = 'Report access could not be verified. Refresh access and retry.';
        },
      }),
    );
  }
  ngOnDestroy(): void {
    this.subscriptions.unsubscribe();
  }
}
