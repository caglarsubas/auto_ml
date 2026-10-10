import {
  Component,
  Input,
  Output,
  EventEmitter,
  OnChanges,
  OnDestroy,
  SimpleChanges,
  ChangeDetectionStrategy,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { Subscription } from 'rxjs';
import { AuthService } from '../services/auth.service';

@Component({
  selector: 'app-package-jobs',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './package-jobs.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class PackageJobsComponent implements OnChanges, OnDestroy {
  @Input({ required: true }) fileId!: number;
  @Input({ required: true }) projectId!: string;
  @Input({ required: true }) role!: string;
  @Input() packageInfo: any = null;
  @Input() evidenceEnabled = false;
  @Output() receiptSelected = new EventEmitter<any>();
  directory: any = null;
  job: any = null;
  busy = false;
  error = '';
  inputFileId = 0;
  source: any = null;
  pending: { url: string; body: any } | null = null;
  private generation = 0;
  private requests = new Subscription();
  constructor(
    private http: HttpClient,
    private auth: AuthService,
  ) {}
  ngOnChanges(changes?: SimpleChanges): void {
    // Review availability changes during a write; it is not a new job context.
    // Avoid resetting selection and issuing an audit-writing read at that point.
    if (changes && Object.keys(changes).every((key) => key === 'evidenceEnabled')) return;
    this.generation++;
    this.requests.unsubscribe();
    this.requests = new Subscription();
    this.directory = this.job = this.pending = this.source = null;
    this.inputFileId = this.fileId;
    this.busy = false;
    this.error = '';
    this.refresh();
  }
  private url(value: string) {
    return `${this.auth.apiRoot}jobs/${value}/`;
  }
  private get params() {
    return { project_id: this.projectId };
  }
  get canCancel(): boolean {
    return (
      !!this.job &&
      this.job.submitted_by.id === this.auth.user?.id &&
      ['queued', 'running'].includes(this.job.state) &&
      ['developer', 'reviewer'].includes(this.role)
    );
  }
  refresh(older = false): void {
    if (this.busy) return;
    this.busy = true;
    this.error = '';
    const generation = ++this.generation;
    const selected = this.job?.id;
    this.requests.add(
      this.http
        .get<any>(this.url(`datasets/${this.fileId}`), {
          params: { ...this.params, ...(older ? { offset: this.directory.next_offset } : {}) },
          transferCache: false,
        })
        .subscribe({
          next: (directory) => {
            if (generation !== this.generation) return;
            this.directory = older
              ? { ...directory, jobs: [...this.directory.jobs, ...directory.jobs] }
              : directory;
            this.busy = false;
            if (selected) this.open(selected);
          },
          error: (error) => this.fail(generation, error, false),
        }),
    );
  }
  open(id: string): void {
    if (this.busy) return;
    this.busy = true;
    this.job = null;
    this.error = '';
    const generation = ++this.generation;
    this.requests.add(
      this.http.get<any>(this.url(id), { params: this.params, transferCache: false }).subscribe({
        next: (job) => {
          if (generation === this.generation) {
            this.job = job;
            this.busy = false;
          }
        },
        error: (error) => this.fail(generation, error, false),
      }),
    );
  }
  submit(): void {
    if (
      !this.packageInfo ||
      !this.directory?.jobs_enabled ||
      this.pending ||
      this.busy ||
      !['developer', 'reviewer'].includes(this.role)
    )
      return;
    this.pending = {
      url: this.url(`datasets/${this.fileId}`),
      body: {
        request_id: crypto.randomUUID(),
        kind: 'package_integrity_v1',
        bundle_id: this.packageInfo.bundle_id,
        manifest_sha256: this.packageInfo.manifest_sha256,
      },
    };
    this.retry();
  }
  selectInput(id: number): void {
    this.inputFileId = id;
    this.source = null;
  }
  prepareInput(): void {
    if (
      this.busy ||
      this.pending ||
      this.role !== 'developer' ||
      !Number.isSafeInteger(this.inputFileId) ||
      this.inputFileId < 1
    )
      return;
    this.source = null;
    this.busy = true;
    this.error = '';
    const generation = ++this.generation;
    this.requests.add(
      this.http
        .get<any>(this.url(`datasets/${this.inputFileId}/input`), {
          params: this.params,
          transferCache: false,
        })
        .subscribe({
          next: (source) => {
            if (generation === this.generation) {
              this.source = source;
              this.busy = false;
            }
          },
          error: (error) => this.fail(generation, error, false),
        }),
    );
  }
  submitScore(): void {
    if (
      this.role !== 'developer' ||
      !this.source ||
      !this.packageInfo ||
      !this.directory?.jobs_enabled ||
      this.busy ||
      this.pending
    )
      return;
    this.pending = {
      url: this.url(`datasets/${this.fileId}`),
      body: {
        request_id: crypto.randomUUID(),
        kind: 'native_csv_scoring_v1',
        bundle_id: this.packageInfo.bundle_id,
        manifest_sha256: this.packageInfo.manifest_sha256,
        input_file_id: this.source.file_id,
        input_sha256: this.source.sha256,
      },
    };
    this.retry();
  }
  downloadScores(): void {
    if (
      this.busy ||
      this.job?.state !== 'succeeded' ||
      this.job.specification.kind !== 'native_csv_scoring_v1'
    )
      return;
    const generation = this.generation,
      id = this.job.id;
    this.requests.add(
      this.http
        .get(this.url(`${id}/scores`), {
          params: { ...this.params, sha256: this.job.result_sha256 },
          responseType: 'blob',
          transferCache: false,
        })
        .subscribe({
          next: (blob) => {
            if (generation === this.generation) this.save(blob, `scoring-${id}.json`);
          },
          error: (error) => this.fail(generation, error, false),
        }),
    );
  }
  private save(blob: Blob, filename: string): void {
    const url = URL.createObjectURL(blob),
      link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  }
  cancel(): void {
    if (!this.canCancel || this.pending || this.busy) return;
    this.pending = { url: this.url(this.job.id), body: { action: 'cancel' } };
    this.retry();
  }
  retry(): void {
    if (!this.pending || this.busy) return;
    this.busy = true;
    this.error = '';
    const action = this.pending,
      generation = ++this.generation;
    this.requests.add(
      this.http.post<any>(action.url, action.body, { params: this.params }).subscribe({
        next: (job) => {
          if (generation !== this.generation) return;
          this.job = job;
          this.pending = null;
          this.busy = false;
          if (this.directory && !this.directory.jobs.some((j: any) => j.id === job.id)) {
            this.directory.jobs.unshift({
              id: job.id,
              state: job.state,
              kind: job.specification.kind,
              bundle_id: job.specification.bundle_id,
            });
            this.directory.total++;
          }
        },
        error: (error) => this.fail(generation, error, true),
      }),
    );
  }
  private fail(generation: number, error: any, mutation: boolean): void {
    if (generation !== this.generation) return;
    this.busy = false;
    this.job = null;
    if (error.status === 403 || !mutation) {
      this.directory = null;
      this.source = null;
    }
    if (mutation && ![400, 404, 409].includes(error.status)) {
      this.error =
        'The outcome could not be confirmed. Retry the same pending request after access or service recovery.';
    } else {
      if (mutation) this.pending = null;
      this.error = `Job access or execution was blocked (${error.error?.error_code || 'unavailable'}). Refresh and retry.`;
    }
  }
  download(): void {
    if (!this.job || this.busy) return;
    // Refresh authority and the retained receipt before every download.
    const generation = this.generation,
      id = this.job.id;
    this.requests.add(
      this.http.get<any>(this.url(id), { params: this.params, transferCache: false }).subscribe({
        next: (job) => {
          if (generation !== this.generation) return;
          const url = URL.createObjectURL(
            new Blob([JSON.stringify(job, null, 2)], { type: 'application/json' }),
          );
          const link = document.createElement('a');
          link.href = url;
          link.download = `job-${id}.json`;
          link.click();
          URL.revokeObjectURL(url);
        },
        error: (error) => this.fail(generation, error, false),
      }),
    );
  }
  selectReceipt(): void {
    if (!this.evidenceEnabled || this.busy || this.job?.state !== 'succeeded') return;
    const generation = this.generation;
    const id = this.job.id;
    // Selection refreshes authority; the review API validates again on adoption.
    this.busy = true;
    this.requests.add(
      this.http.get<any>(this.url(id), { params: this.params, transferCache: false }).subscribe({
        next: (job) => {
          if (generation !== this.generation) return;
          this.job = job;
          this.busy = false;
          if (job.state === 'succeeded') this.receiptSelected.emit(job);
        },
        error: (error) => this.fail(generation, error, false),
      }),
    );
  }
  ngOnDestroy(): void {
    this.generation++;
    this.requests.unsubscribe();
  }
}
