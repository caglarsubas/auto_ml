import { Component, Input, OnChanges, OnDestroy, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { Subscription } from 'rxjs';
import { AuthService } from '../services/auth.service';

@Component({
  selector: 'app-package-review',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './package-review.component.html',
  styleUrl: './package-review.component.css',
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class PackageReviewComponent implements OnChanges, OnDestroy {
  @Input({ required: true }) fileId!: number;
  @Input({ required: true }) projectId!: string;
  @Input({ required: true }) role!: string;
  directory: any = null;
  review: any = null;
  busy = false;
  error = '';
  text = '';
  severity = 'major';
  eventType = 'finding';
  findingId = '';
  private generation = 0;
  private requests = new Subscription();
  pending: { url: string; body: any } | null = null;

  constructor(
    private http: HttpClient,
    private auth: AuthService,
  ) {}
  ngOnChanges(): void {
    this.generation++;
    this.requests.unsubscribe();
    this.requests = new Subscription();
    this.directory = this.review = this.pending = null;
    this.text = this.findingId = '';
    this.eventType = this.role === 'developer' ? 'response' : 'finding';
    this.refresh();
  }
  get params() {
    return { project_id: this.projectId };
  }
  get hasCurrentReview(): boolean {
    return !!this.directory?.reviews.some(
      (review: any) => review.bundle_id === this.directory.current_package?.bundle_id,
    );
  }
  older(): void {
    if (this.busy || this.directory?.next_offset == null) return;
    this.busy = true;
    const generation = this.generation;
    this.requests.add(
      this.http
        .get<any>(this.url(`datasets/${this.fileId}`), {
          params: { ...this.params, offset: this.directory.next_offset },
          transferCache: false,
        })
        .subscribe({
          next: (page) => {
            if (generation !== this.generation) return;
            this.directory = { ...page, reviews: [...this.directory.reviews, ...page.reviews] };
            this.busy = false;
          },
          error: () => {
            if (generation === this.generation) {
              this.busy = false;
              this.error = 'Older reviews could not be loaded. Refresh access and retry.';
            }
          },
        }),
    );
  }
  private url(suffix: string) {
    return `${this.auth.apiRoot}reviews/${suffix}/`;
  }
  refresh(): void {
    const selected = this.review?.id;
    this.review = this.directory = null;
    this.busy = true;
    this.error = '';
    const generation = ++this.generation;
    this.requests.add(
      this.http
        .get<any>(this.url(`datasets/${this.fileId}`), {
          params: this.params,
          transferCache: false,
        })
        .subscribe({
          next: (directory) => {
            if (generation !== this.generation) return;
            this.directory = directory;
            this.busy = false;
            if (selected) this.open(selected);
          },
          error: () => {
            if (generation !== this.generation) return;
            this.busy = false;
            this.error =
              'Review access or evidence could not be checked. Refresh access and retry.';
          },
        }),
    );
  }
  open(id: string): void {
    this.review = null;
    this.busy = true;
    this.error = '';
    const generation = ++this.generation;
    this.requests.add(
      this.http.get<any>(this.url(id), { params: this.params, transferCache: false }).subscribe({
        next: (review) => {
          if (generation !== this.generation) return;
          this.review = review;
          this.findingId = '';
          this.busy = false;
        },
        error: () => {
          if (generation !== this.generation) return;
          this.busy = false;
          this.error = 'Review access or evidence could not be checked. Refresh access and retry.';
        },
      }),
    );
  }
  start(): void {
    if (!this.directory?.current_package || this.pending || this.busy) return;
    const packageInfo = this.directory.current_package;
    this.pending = {
      url: this.url(`datasets/${this.fileId}`),
      body: {
        request_id: crypto.randomUUID(),
        bundle_id: packageInfo.bundle_id,
        manifest_sha256: packageInfo.manifest_sha256,
      },
    };
    this.retry();
  }
  submit(): void {
    if (
      !this.review ||
      this.review.freshness !== 'current' ||
      !this.text.trim() ||
      this.pending ||
      this.busy
    )
      return;
    const body: any = {
      request_id: crypto.randomUUID(),
      expected_revision: this.review.revision,
      event_type: this.eventType,
      text: this.text,
    };
    if (this.eventType === 'finding') body.severity = this.severity;
    else body.finding_id = this.findingId;
    this.pending = { url: this.url(this.review.id), body };
    this.retry();
  }
  retry(): void {
    if (!this.pending || this.busy) return;
    this.busy = true;
    this.error = '';
    const action = this.pending;
    const generation = ++this.generation;
    this.requests.add(
      this.http.post<any>(action.url, action.body, { params: this.params }).subscribe({
        next: (review) => {
          if (generation !== this.generation) return;
          this.review = review;
          this.pending = null;
          if (
            this.directory &&
            !this.directory.reviews.some((item: any) => item.id === review.id)
          ) {
            this.directory.reviews.unshift({
              id: review.id,
              bundle_id: review.bundle_id,
              freshness: review.freshness,
            });
            this.directory.total++;
          }
          this.text = this.findingId = '';
          this.busy = false;
        },
        error: (error) => {
          if (generation !== this.generation) return;
          this.busy = false;
          if ([400, 403, 404, 409].includes(error.status)) {
            this.pending = null;
            this.review = null;
            this.error = `Action was blocked (${error.error?.error_code || 'invalid request'}). Refresh the review before making another change.`;
          } else {
            this.error =
              'The outcome could not be confirmed. Retry the pending action with the same receipt.';
          }
        },
      }),
    );
  }
  download(kind: 'discussion' | 'package'): void {
    if (!this.review || this.busy) return;
    const selected = this.review;
    const generation = this.generation;
    const save = (blob: Blob, filename: string) => {
      if (generation !== this.generation) return;
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    };
    const fail = () => {
      if (generation === this.generation)
        this.error = 'Evidence download could not be verified. Refresh access and retry.';
    };
    if (kind === 'discussion') {
      this.requests.add(
        this.http
          .get<any>(this.url(selected.id), { params: this.params, transferCache: false })
          .subscribe({
            next: (value) =>
              save(
                new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }),
                `review-${selected.id}.json`,
              ),
            error: fail,
          }),
      );
    } else {
      this.requests.add(
        this.http
          .post(
            `${this.auth.apiRoot}deployment/pack/`,
            { file_id: this.fileId, bundle_id: selected.bundle_id },
            { params: this.params, responseType: 'blob' },
          )
          .subscribe({
            next: (blob) => save(blob, `package-${selected.bundle_id}.zip`),
            error: fail,
          }),
      );
    }
  }
  ngOnDestroy(): void {
    this.generation++;
    this.requests.unsubscribe();
  }
}
