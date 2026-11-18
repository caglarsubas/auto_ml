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
const AVAILABLE = 'available_at_prediction';
const EXCLUDED = 'excluded';

interface OutcomeWindow {
  horizon_days: number;
  maturity_lag_days: number;
  development_as_of: string;
}

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
  outcomeWindow: boolean;
  horizonDays: number | null;
  maturityLagDays: number | null;
  developmentAsOf: string;
  fnCost: number;
  fpCost: number;
  developmentOnly: boolean;
  available: boolean;
  explicitlyAvailable: string;
  excluded: string;
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
  outcomeWindow: false,
  horizonDays: null,
  maturityLagDays: null,
  developmentAsOf: '',
  fnCost: 1,
  fpCost: 1,
  developmentOnly: false,
  available: false,
  explicitlyAvailable: '',
  excluded: '',
});

function columnNames(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((column) => column.trim())
    .filter(Boolean);
}

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
  private options() {
    const d = this.draft;
    const target = d.target.trim();
    const features = columnNames(d.predictors);
    const explicitlyAvailable = columnNames(d.explicitlyAvailable);
    const excluded = columnNames(d.excluded);
    const overrideColumns = [...explicitlyAvailable, ...excluded];
    if (new Set(overrideColumns).size !== overrideColumns.length) {
      throw new Error('List each column once in feature availability overrides.');
    }
    if (overrideColumns.includes(target)) {
      throw new Error('Remove the target column from feature availability overrides.');
    }
    const excludedPredictors = features.filter((feature) => excluded.includes(feature));
    if (excludedPredictors.length) {
      throw new Error(
        `Remove excluded columns from the predictor list: ${excludedPredictors.join(', ')}.`,
      );
    }
    const overrides = Object.fromEntries<typeof AVAILABLE | typeof EXCLUDED>([
      ...explicitlyAvailable.map((column) => [column, AVAILABLE] as const),
      ...excluded.map((column) => [column, EXCLUDED] as const),
    ]);
    const controls =
      d.strategy === 'group'
        ? [d.group.trim()]
        : d.strategy === 'oot'
          ? [d.date.trim(), d.group.trim(), d.labelEnd.trim()].filter(Boolean)
          : [];
    if (explicitlyAvailable.some((column) => controls.includes(column))) {
      throw new Error('Validation control columns cannot be marked as available predictors.');
    }
    if (
      !d.developmentOnly ||
      !d.available ||
      !['classification', 'regression'].includes(d.task) ||
      !target ||
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
      features.some((f) => f === target || controls.includes(f)) ||
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
    let outcomeWindow: OutcomeWindow | undefined;
    if (d.outcomeWindow) {
      if (
        d.strategy !== 'oot' ||
        !d.date.trim() ||
        !d.labelEnd.trim() ||
        d.date.trim() === d.labelEnd.trim()
      ) {
        throw new Error(
          'The outcome window requires temporal validation and distinct date and label end columns.',
        );
      }
      const { horizonDays, maturityLagDays } = d;
      if (
        horizonDays === null ||
        !Number.isInteger(horizonDays) ||
        horizonDays < 1 ||
        horizonDays > 3650 ||
        maturityLagDays === null ||
        !Number.isInteger(maturityLagDays) ||
        maturityLagDays < 0 ||
        maturityLagDays > 3650
      ) {
        throw new Error(
          'Enter a whole-number horizon of 1–3,650 days and a maturity lag of 0–3,650 days.',
        );
      }
      const developmentAsOf = d.developmentAsOf.trim();
      if (
        !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,3})?)?(?:Z|[+-]\d{2}:\d{2})$/.test(
          developmentAsOf,
        ) ||
        !Number.isFinite(Date.parse(developmentAsOf))
      ) {
        throw new Error(
          'Enter the development as-of timestamp in ISO format with a timezone, such as 2026-11-18T00:00:00Z.',
        );
      }
      outcomeWindow = {
        horizon_days: horizonDays,
        maturity_lag_days: maturityLagDays,
        development_as_of: developmentAsOf,
      };
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
        feature_availability: {
          default: AVAILABLE,
          ...(overrideColumns.length ? { overrides } : {}),
        },
        target_contract: {
          target_column: target,
          positive_class: d.task === 'classification' ? d.positive.trim() : null,
          event_definition: d.event.trim(),
          label_maturity: d.maturity.trim(),
          ...(outcomeWindow ? { outcome_window: outcomeWindow } : {}),
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
  private matchesDeclaration(
    contract: any,
    declaration: ReturnType<TrainingLaunchComponent['options']>['business_understanding'],
  ): boolean {
    const availability = contract.feature_availability;
    const overrides = availability?.overrides === undefined ? {} : availability.overrides;
    const expected = Object.entries(declaration.feature_availability.overrides ?? {});
    const acceptedWindow = contract.target_contract?.outcome_window;
    const requestedWindow = declaration.target_contract.outcome_window;
    const windowMatches = requestedWindow
      ? acceptedWindow?.horizon_days === requestedWindow.horizon_days &&
        acceptedWindow.maturity_lag_days === requestedWindow.maturity_lag_days &&
        typeof acceptedWindow.development_as_of === 'string' &&
        Date.parse(acceptedWindow.development_as_of) ===
          Date.parse(requestedWindow.development_as_of)
      : acceptedWindow === undefined || acceptedWindow === null;
    return (
      contract.population === declaration.population &&
      contract.prediction_horizon === declaration.prediction_horizon &&
      contract.target_contract?.label_maturity === declaration.target_contract.label_maturity &&
      windowMatches &&
      availability?.default === declaration.feature_availability.default &&
      overrides !== null &&
      typeof overrides === 'object' &&
      !Array.isArray(overrides) &&
      Object.keys(overrides).length === expected.length &&
      expected.every(
        ([column, status]) => Object.hasOwn(overrides, column) && overrides[column] === status,
      )
    );
  }
  prepare(): void {
    if (this.locked || this.role !== 'developer') return;
    this.changed();
    let options: ReturnType<TrainingLaunchComponent['options']>;
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
            !preview ||
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
          if (
            !this.matchesDeclaration(preview.prediction_contract, options.business_understanding)
          ) {
            this.error =
              'The preview did not preserve the declared population, horizon, label maturity, outcome window or feature availability. Prepare a fresh preview before submitting.';
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
      job_prediction_contract_invalid:
        error.error?.error ||
        'Check the declared task, target, positive label, population, horizon, label maturity, feature availability and objective.',
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
