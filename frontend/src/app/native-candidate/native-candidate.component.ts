import {
  Component,
  Input,
  Output,
  EventEmitter,
  OnChanges,
  OnDestroy,
  ChangeDetectionStrategy,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { JsonPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Subscription } from 'rxjs';
import { NativeAdoptionComponent } from '../native-adoption/native-adoption.component';
import { AuthService } from '../services/auth.service';

@Component({
  selector: 'app-native-candidate',
  standalone: true,
  imports: [FormsModule, JsonPipe, NativeAdoptionComponent],
  templateUrl: './native-candidate.component.html',
  styleUrl: './native-candidate.component.css',
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class NativeCandidateComponent implements OnChanges, OnDestroy {
  @Input({ required: true }) job: any;
  @Input({ required: true }) projectId!: string;
  @Input({ required: true }) role!: string;
  @Input() jobsEnabled = false;
  @Output() queued = new EventEmitter<any>();
  inputFileId = 0;
  preview: any = null;
  approved = false;
  busy = false;
  error = '';
  exportSha = '';
  pending: any = null;
  private generation = 0;
  private requests = new Subscription();
  constructor(
    private http: HttpClient,
    private auth: AuthService,
  ) {}
  ngOnChanges(): void {
    this.generation++;
    this.requests.unsubscribe();
    this.requests = new Subscription();
    this.inputFileId = 0;
    this.preview = this.pending = null;
    this.busy = this.approved = false;
    this.error = this.exportSha = '';
  }
  private get params() {
    return { project_id: this.projectId };
  }
  private url(value: string) {
    return `${this.auth.apiRoot}jobs/${value}/`;
  }
  get candidateAvailable(): boolean {
    return (
      this.job?.state === 'succeeded' &&
      this.job?.specification?.kind === 'native_numeric_training_search_v1'
    );
  }
  changed(): void {
    if (!this.pending) {
      this.preview = null;
      this.approved = false;
    }
  }
  download(): void {
    if (!this.candidateAvailable || this.busy || this.pending) return;
    const generation = this.generation,
      id = this.job.id;
    this.busy = true;
    this.error = '';
    this.requests.add(
      this.http
        .get(this.url(`${id}/candidate`), {
          params: { ...this.params, sha256: this.job.result_sha256 },
          responseType: 'blob',
          observe: 'response',
          transferCache: false,
        })
        .subscribe({
          next: (response) => {
            if (generation !== this.generation) return;
            this.busy = false;
            const sha = response.headers.get('X-DeclarAI-Export-SHA256');
            if (!response.body || !sha || !/^[a-f0-9]{64}$/.test(sha)) {
              this.error = 'Export digest is unavailable. Refresh before retrying.';
              return;
            }
            this.exportSha = sha;
            const url = URL.createObjectURL(response.body),
              link = document.createElement('a');
            link.href = url;
            link.download = `candidate-${id}.json`;
            link.click();
            URL.revokeObjectURL(url);
          },
          error: (error) => this.fail(generation, error, false),
        }),
    );
  }
  prepare(): void {
    if (
      !this.candidateAvailable ||
      this.role !== 'developer' ||
      !this.jobsEnabled ||
      this.busy ||
      this.pending ||
      !Number.isSafeInteger(this.inputFileId) ||
      this.inputFileId < 1
    )
      return;
    this.preview = null;
    this.approved = false;
    this.busy = true;
    this.error = '';
    const generation = ++this.generation;
    this.requests.add(
      this.http
        .post<any>(
          this.url(`${this.job.id}/scoring-input`),
          {
            input_file_id: this.inputFileId,
            training_result_sha256: this.job.result_sha256,
          },
          { params: this.params },
        )
        .subscribe({
          next: (value) => {
            if (generation !== this.generation) return;
            this.preview = value;
            this.busy = false;
          },
          error: (error) => this.fail(generation, error, false),
        }),
    );
  }
  submit(): void {
    if (
      !this.preview ||
      !this.approved ||
      !this.candidateAvailable ||
      this.role !== 'developer' ||
      !this.jobsEnabled ||
      this.busy ||
      this.pending
    )
      return;
    if (
      this.preview.input_file_id !== this.inputFileId ||
      this.preview.training_job_id !== this.job.id ||
      this.preview.training_result_sha256 !== this.job.result_sha256
    ) {
      this.changed();
      return;
    }
    const p = this.preview;
    this.pending = {
      request_id: crypto.randomUUID(),
      kind: 'native_training_scoring_v1',
      training_job_id: p.training_job_id,
      training_result_sha256: p.training_result_sha256,
      input_file_id: p.input_file_id,
      input_sha256: p.input_sha256,
      scoring_sha256: p.scoring_sha256,
    };
    this.retry();
  }
  retry(): void {
    if (!this.pending || this.busy || this.role !== 'developer' || !this.candidateAvailable) return;
    const generation = ++this.generation;
    this.busy = true;
    this.error = '';
    this.requests.add(
      this.http
        .post<any>(this.url(`datasets/${this.job.file_id}`), this.pending, { params: this.params })
        .subscribe({
          next: (job) => {
            if (generation !== this.generation) return;
            this.busy = false;
            this.pending = null;
            this.preview = null;
            this.approved = false;
            this.queued.emit(job);
          },
          error: (error) => this.fail(generation, error, true),
        }),
    );
  }
  private fail(generation: number, error: any, mutation: boolean): void {
    if (generation !== this.generation) return;
    this.busy = false;
    this.preview = null;
    this.approved = false;
    this.exportSha = '';
    if (mutation && ![400, 404, 409].includes(error.status)) {
      this.error =
        'Admission could not be confirmed. Retry the identical pending request after access or service recovery.';
    } else {
      this.pending = null;
      this.error = `Candidate action blocked (${error.error?.error_code || 'unavailable'}). Prepare and review again.`;
    }
  }
  ngOnDestroy(): void {
    this.generation++;
    this.requests.unsubscribe();
  }
}
