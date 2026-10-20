import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  Input,
  OnChanges,
  OnDestroy,
  ViewChild,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';
import { AuthService } from '../services/auth.service';
import { PackageJobsComponent } from '../package-jobs/package-jobs.component';

const KIND = 'native_numeric_training_search_v1';
interface Draft {
  task: string;
  target: string;
  positive: string;
  predictors: string;
  objective: string;
  population: string;
  horizon: string;
  event: string;
  maturity: string;
  metric: string;
  strategy: string;
  folds: number;
  group: string;
  date: string;
  labelEnd: string;
  fnCost: number;
  fpCost: number;
  developmentOnly: boolean;
  available: boolean;
}
const emptyDraft = (): Draft => ({
  task: '',
  target: '',
  positive: '',
  predictors: '',
  objective: '',
  population: '',
  horizon: '',
  event: '',
  maturity: '',
  metric: '',
  strategy: '',
  folds: 2,
  group: '',
  date: '',
  labelEnd: '',
  fnCost: 1,
  fpCost: 1,
  developmentOnly: false,
  available: false,
});

@Component({
  selector: 'app-training-launch',
  standalone: true,
  imports: [CommonModule, FormsModule, PackageJobsComponent],
  templateUrl: './training-launch.component.html',
  styleUrl: './training-launch.component.css',
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class TrainingLaunchComponent implements OnChanges, OnDestroy {
  @Input({ required: true }) fileId!: number;
  @Input({ required: true }) projectId!: string;
  @Input({ required: true }) role!: string;
  @Input() datasetName = '';
  @ViewChild(PackageJobsComponent) jobs?: PackageJobsComponent;
  draft = emptyDraft();
  preview: any = null;
  reviewedOptions: any = null;
  approved = false;
  busy = false;
  error = '';
  submittedId = '';
  pending: { url: string; body: any } | null = null;
  private generation = 0;
  private requests = new Subscription();
  readonly declarations = [
    { key: 'objective', label: 'Business objective' },
    { key: 'population', label: 'Development population' },
    { key: 'horizon', label: 'Prediction horizon' },
    { key: 'event', label: 'Outcome definition' },
    { key: 'maturity', label: 'Label maturity and follow-up' },
  ] as const;
  get metrics(): string[] {
    return this.draft.task === 'regression'
      ? ['rmse', 'mae', 'mse', 'r2']
      : [
          'roc_auc',
          'pr_auc',
          'log_loss',
          'accuracy',
          'f1',
          'precision',
          'recall',
          'ks',
          'brier',
          'expected_cost',
        ];
  }
  get locked(): boolean {
    return this.busy || !!this.pending;
  }
  private get params() {
    return { project_id: this.projectId };
  }
  private url(suffix = '') {
    return `${this.auth.apiRoot}jobs/datasets/${this.fileId}/${suffix}`;
  }
  constructor(
    private http: HttpClient,
    private auth: AuthService,
  ) {}
  ngOnChanges(): void {
    this.generation++;
    this.requests.unsubscribe();
    this.requests = new Subscription();
    this.draft = emptyDraft();
    this.preview = this.reviewedOptions = this.pending = null;
    this.approved = this.busy = false;
    this.error = this.submittedId = '';
  }
  changed(): void {
    this.preview = this.reviewedOptions = null;
    this.approved = false;
    this.error = '';
  }
  taskChanged(): void {
    this.draft.metric = '';
    this.draft.positive = '';
    this.changed();
  }
  private options(): any {
    const d = this.draft;
    const features = d.predictors
      .split(/\r?\n/)
      .map((x) => x.trim())
      .filter(Boolean);
    const controls =
      d.strategy === 'group'
        ? [d.group]
        : d.strategy === 'oot'
          ? [d.date, d.group, d.labelEnd].filter(Boolean)
          : [];
    if (
      !d.developmentOnly ||
      !d.available ||
      !['classification', 'regression'].includes(d.task) ||
      !d.target.trim() ||
      (d.task === 'classification' && !d.positive.trim()) ||
      this.declarations.some((f) => !d[f.key].trim()) ||
      !this.metrics.includes(d.metric) ||
      !['random', 'group', 'oot'].includes(d.strategy) ||
      ![2, 3].includes(d.folds) ||
      (d.strategy === 'group' && !d.group.trim()) ||
      (d.strategy === 'oot' && !d.date.trim()) ||
      features.length < 1 ||
      features.length > 32 ||
      new Set(features).size !== features.length ||
      features.some((f) => f === d.target.trim() || controls.map((x) => x.trim()).includes(f)) ||
      (d.metric === 'expected_cost' &&
        [d.fnCost, d.fpCost].some((v) => typeof v !== 'number' || !Number.isFinite(v) || v < 0))
    ) {
      throw new Error(
        'Complete the declaration and confirmations. Choose 1–32 unique numeric predictors, one exact column name per line, excluding the target and validation controls. Select a supported metric and validation strategy; costs must be finite and nonnegative.',
      );
    }
    const validation: any = { strategy: d.strategy, n_splits: d.folds };
    if (d.strategy === 'group') validation.group_column = d.group.trim();
    if (d.strategy === 'oot') {
      validation.date_column = d.date.trim();
      if (d.group.trim()) validation.group_column = d.group.trim();
      if (d.labelEnd.trim()) validation.label_end_column = d.labelEnd.trim();
    }
    return {
      data_role: 'development_only',
      features,
      validation,
      business_understanding: {
        problem_type: d.task,
        objective: d.objective.trim(),
        population: d.population.trim(),
        prediction_horizon: d.horizon.trim(),
        feature_availability: { default: 'available_at_prediction' },
        target_contract: {
          target_column: d.target.trim(),
          positive_class: d.task === 'classification' ? d.positive.trim() : null,
          event_definition: d.event.trim(),
          label_maturity: d.maturity.trim(),
        },
        success_criteria: {
          primary_metric: d.metric,
          ...(d.metric === 'expected_cost'
            ? { cost_matrix: { fn_cost: d.fnCost, fp_cost: d.fpCost } }
            : {}),
        },
      },
    };
  }
  prepare(): void {
    if (this.locked || this.role !== 'developer') return;
    this.changed();
    let options: any;
    try {
      options = this.options();
    } catch (error) {
      this.error = (error as Error).message;
      return;
    }
    this.busy = true;
    const generation = ++this.generation;
    this.requests.add(
      this.http.post<any>(this.url('training-input/'), options, { params: this.params }).subscribe({
        next: (preview) => {
          if (generation !== this.generation) return;
          this.busy = false;
          if (
            preview.kind !== KIND ||
            !/^[a-f0-9]{64}$/.test(preview.input_sha256) ||
            !/^[a-f0-9]{64}$/.test(preview.training_sha256) ||
            !preview.prediction_contract ||
            !Array.isArray(preview.folds) ||
            !preview.budget ||
            !preview.runtime
          ) {
            this.error = 'The preview was incomplete. Prepare a fresh preview before submitting.';
            return;
          }
          this.preview = preview;
          this.reviewedOptions = structuredClone(options);
        },
        error: (error) => this.failed(generation, error, false),
      }),
    );
  }
  submit(): void {
    if (
      this.locked ||
      this.role !== 'developer' ||
      !this.preview ||
      !this.approved ||
      !this.jobs?.directory?.jobs_enabled
    )
      return;
    // Recheck even programmatic draft changes; submit only the displayed immutable preview.
    let options: any;
    try {
      options = this.options();
    } catch {
      this.changed();
      return;
    }
    if (JSON.stringify(options) !== JSON.stringify(this.reviewedOptions)) {
      this.changed();
      return;
    }
    this.pending = {
      url: this.url(),
      body: {
        ...structuredClone(this.reviewedOptions),
        kind: KIND,
        request_id: crypto.randomUUID(),
        input_sha256: this.preview.input_sha256,
        training_sha256: this.preview.training_sha256,
      },
    };
    this.retry();
  }
  retry(): void {
    if (!this.pending || this.busy || this.role !== 'developer') return;
    this.busy = true;
    this.error = '';
    const generation = ++this.generation,
      pending = this.pending;
    this.requests.add(
      this.http.post<any>(pending.url, pending.body, { params: this.params }).subscribe({
        next: (job) => {
          if (generation !== this.generation) return;
          this.busy = false;
          this.pending = null;
          this.submittedId = job.id;
          this.changed();
          const directory = this.jobs?.directory;
          if (directory && !directory.jobs.some((item: any) => item.id === job.id)) {
            directory.jobs.unshift({
              id: job.id,
              state: job.state,
              kind: job.specification?.kind || KIND,
              bundle_id: null,
            });
            directory.total++;
          }
          this.jobs?.open(job.id);
        },
        error: (error) => this.failed(generation, error, true),
      }),
    );
  }
  private failed(generation: number, error: any, mutation: boolean): void {
    if (generation !== this.generation) return;
    this.busy = false;
    const code = error.error?.error_code || 'unavailable';
    if (mutation && ![400, 404, 409].includes(error.status)) {
      this.preview = this.reviewedOptions = null;
      this.approved = false;
      this.error = `Submission outcome is unconfirmed (${code}). Retry the same request after access or service recovery. Do not start a replacement job; inspect job history if you leave this panel.`;
      return;
    }
    this.pending = null;
    this.changed();
    const advice: Record<string, string> = {
      job_training_requires_fresh_development_input:
        'This dataset has recorded split, model or assessment history. Use a genuinely fresh development input with verified population provenance; reuploading assessed rows does not make them fresh.',
      job_training_numeric_features_required:
        'Choose only numeric predictors with finite observed values. Missing predictors are imputed inside training folds.',
      job_training_csv_profile_invalid:
        'Use a headered UTF-8 CSV with 30–1,000 rows, at most 40 columns and consistent row widths.',
      job_request_invalid:
        'Check the exact target and positive label, metric, required declarations and split columns. Unsupported or invalid folds cannot fall back to shuffled validation.',
    };
    this.error = `Training preview or admission was blocked (${code}). ${advice[code] || 'Refresh project access and job history, then prepare and review a fresh preview. Input, runtime or budget changes require a new preview.'}`;
  }
  ngOnDestroy(): void {
    this.generation++;
    this.requests.unsubscribe();
  }
}
