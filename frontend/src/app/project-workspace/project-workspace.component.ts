import { Component, OnDestroy, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { ActivatedRoute } from '@angular/router';
import { forkJoin, of, Subscription } from 'rxjs';
import { catchError, distinctUntilChanged, map, switchMap } from 'rxjs/operators';
import { DataService } from '../services/data.service';
import { ProjectWorkspaceService } from '../services/project-workspace.service';
import { PackageReviewComponent } from '../package-review/package-review.component';

@Component({
  selector: 'app-project-workspace',
  standalone: true,
  imports: [CommonModule, FormsModule, PackageReviewComponent],
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
  reviewDataset: number | null = null;
  private preferredProject: string | null = null;
  private readonly subscriptions = new Subscription();
  constructor(
    public workspace: ProjectWorkspaceService,
    private data: DataService,
    private route: ActivatedRoute,
  ) {}

  ngOnInit(): void {
    this.subscriptions.add(
      this.workspace.state$
        .pipe(
          map((state) => (state.ready && state.governed ? state.selected?.id : undefined)),
          distinctUntilChanged(),
          switchMap((project) => {
            this.datasets = [];
            this.pipelines = [];
            this.recordsError = '';
            this.reportError = '';
            this.reviewDataset = null;
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
        }),
    );
    this.preferredProject = this.route.snapshot.queryParamMap.get('project_id');
    this.refresh();
  }
  refresh(): void {
    this.subscriptions.add(this.workspace.refresh(this.preferredProject).subscribe());
  }
  select(projectId: string): void {
    this.preferredProject = projectId;
    this.workspace.select(this.preferredProject);
  }
  report(run: any): void {
    const project = this.workspace.projectId;
    this.reportError = '';
    this.subscriptions.add(
      this.data.downloadPipelineReport(run.id, project).subscribe({
        next: (blob) => {
          if (project !== this.workspace.projectId) return;
          const url = URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.href = url;
          link.download = `pipeline-${run.id}-report.html`;
          link.click();
          URL.revokeObjectURL(url);
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
