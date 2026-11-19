import { Component, Input, OnChanges, OnDestroy, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { Subscription } from 'rxjs';
import {
  NativeAssessmentReviewIdentity,
  PackageJobsComponent,
} from '../package-jobs/package-jobs.component';
import { AuthService } from '../services/auth.service';
import { downloadBlob } from '../utils/download-blob';

@Component({
  selector: 'app-package-review',
  standalone: true,
  imports: [CommonModule, FormsModule, PackageJobsComponent],
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
  expiresAt = '';
  reportText = '';
  evidence: any = null;
  nativeCandidate: NativeAssessmentReviewIdentity | null = null;
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
    this.refresh();
  }
  get params() {
    return { project_id: this.projectId };
  }
  get nextStep(): string {
    if (this.pending)
      return 'An action has an unconfirmed outcome. Retry the pending action with its original receipt before making another change.';
    if (!this.review)
      return this.role === 'reviewer'
        ? 'Open a current package review or select a completed assessment to begin independent review.'
        : 'Open a review to inspect findings and the recorded evidence. Developers can respond to current findings.';
    if (this.review.freshness !== 'current')
      return 'This evidence is historical or unverified. Open a current package or assessment before recording further review actions.';
    if (this.role === 'developer')
      return 'Read the findings, select an open finding and record your response. An independent reviewer records its disposition.';
    if (this.role !== 'reviewer')
      return 'Inspect the evidence and attributable history. Review actions require the current project reviewer role.';
    if (this.review.decision?.status === 'approved')
      return 'Technical review is approved for this exact evidence. Further discussion or upstream changes require the decision to be checked again. Production use requires separate approval.';
    if ((this.review.findings ?? []).some((finding: any) => finding.state === 'open'))
      return 'Review the open findings and developer responses. Resolve each finding or record an eligible time-bound exception before technical approval.';
    return this.review.assessment_job_id
      ? 'Inspect the assessment and independently reproduce its manifest. Attach the reproduction report when recording technical approval. The server checks evidence and reviewer independence.'
      : 'Inspect the exact package and record findings or dispositions. Package discussion does not grant production-use approval.';
  }
  get decisionExplanation(): string {
    const explanations: Record<string, string> = {
      review_upstream_evidence_changed:
        'The underlying evidence changed. Open the current assessment and reproduce it before requesting a new approval.',
      review_approval_evidence_changed:
        'The approval evidence could not be verified. Refresh the review and check the exact reproduction report.',
      review_policy_changed:
        'The applicable review policy changed. Recheck the evidence against the current policy before requesting approval.',
      review_approver_authority_changed:
        'The approving reviewer’s authority changed. A currently authorized independent reviewer must reassess the evidence.',
      review_discussion_changed:
        'The discussion changed after approval. Review the latest findings and dispositions, then record a new decision.',
      review_exception_unavailable:
        'A required exception is no longer available. Resolve the finding or record an eligible current exception before requesting approval.',
      review_approval_revoked:
        'A reviewer revoked technical approval. Read the recorded reason and address it before requesting a new decision.',
    };
    return (
      explanations[this.review?.decision?.reason_code] ??
      'Refresh the review and inspect the recorded reason before requesting a new decision.'
    );
  }
  get lastEvent(): any {
    return this.review?.events?.at(-1);
  }
  private clearAccess(): void {
    this.generation++;
    this.review = this.directory = this.nativeCandidate = null;
    this.clearDraft();
  }
  get hasCurrentReview(): boolean {
    return !!this.directory?.reviews.some(
      (review: any) => review.bundle_id === this.directory.current_package?.bundle_id,
    );
  }
  get needsFinding(): boolean {
    return ['response', 'resolve', 'reopen', 'exception'].includes(this.eventType);
  }
  get availableFindings(): any[] {
    return (this.review?.findings ?? []).filter((finding: any) =>
      this.eventType === 'reopen'
        ? ['resolved', 'excepted'].includes(finding.state)
        : finding.state === 'open',
    );
  }
  get canSubmit(): boolean {
    const actions =
      this.role === 'developer'
        ? ['response']
        : [
            'finding',
            'resolve',
            'reopen',
            ...(this.review?.assessment_job_id ? ['exception', 'approve', 'revoke'] : []),
          ];
    return (
      (this.role === 'developer' || this.role === 'reviewer') &&
      this.review?.freshness === 'current' &&
      !this.pending &&
      !this.busy &&
      !!this.text.trim() &&
      actions.includes(this.eventType) &&
      (!this.needsFinding ||
        this.availableFindings.some((finding) => finding.id === this.findingId)) &&
      (this.eventType !== 'exception' || !!this.expiresAt.trim()) &&
      (this.eventType !== 'approve' || !!this.reportText.trim())
    );
  }
  clearActionFields(): void {
    this.findingId = this.expiresAt = this.reportText = '';
  }
  private clearDraft(resetAction = true): void {
    this.text = '';
    this.evidence = null;
    if (resetAction) this.eventType = this.role === 'developer' ? 'response' : 'finding';
    this.clearActionFields();
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
            this.nativeCandidate = null;
            this.directory = { ...page, reviews: [...this.directory.reviews, ...page.reviews] };
            this.busy = false;
          },
          error: (error) => {
            if (generation === this.generation) {
              if (error.status === 403) this.clearAccess();
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
    this.nativeCandidate = null;
    this.clearDraft();
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
    this.nativeCandidate = null;
    this.clearDraft();
    this.busy = true;
    this.error = '';
    const generation = ++this.generation;
    this.requests.add(
      this.http.get<any>(this.url(id), { params: this.params, transferCache: false }).subscribe({
        next: (review) => {
          if (generation !== this.generation) return;
          this.review = review;
          this.busy = false;
        },
        error: (error) => {
          if (generation !== this.generation) return;
          this.busy = false;
          if (error.status === 403) this.clearAccess();
          this.error = 'Review access or evidence could not be checked. Refresh access and retry.';
        },
      }),
    );
  }
  start(): void {
    if (this.role !== 'reviewer' || !this.directory?.current_package || this.pending || this.busy)
      return;
    const packageInfo = this.directory.current_package;
    this.startReview({
      bundle_id: packageInfo.bundle_id,
      manifest_sha256: packageInfo.manifest_sha256,
    });
  }
  selectNativeReview(identity: NativeAssessmentReviewIdentity | null): void {
    this.nativeCandidate =
      this.role === 'reviewer' && !this.busy && !this.pending ? identity : null;
  }
  startNative(): void {
    const identity = this.nativeCandidate;
    if (this.role !== 'reviewer' || !identity || !this.directory || this.pending || this.busy)
      return;
    const existing = this.directory.reviews.find(
      (review: any) =>
        review.assessment_job_id === identity.assessment_job_id &&
        review.assessment_result_sha256 === identity.assessment_result_sha256 &&
        review.manifest_sha256 === identity.manifest_sha256,
    );
    if (existing) {
      this.open(existing.id);
      return;
    }
    this.startReview(identity);
  }
  private startReview(
    identity: NativeAssessmentReviewIdentity | { bundle_id: string; manifest_sha256: string },
  ): void {
    this.nativeCandidate = null;
    this.pending = {
      url: this.url(`datasets/${this.fileId}`),
      body: { request_id: crypto.randomUUID(), ...identity },
    };
    this.retry();
  }
  submit(): void {
    if (!this.canSubmit) return;
    const body: any = {
      request_id: crypto.randomUUID(),
      expected_revision: this.review.revision,
      event_type: this.eventType,
      text: this.text,
    };
    if (this.eventType === 'finding') body.severity = this.severity;
    if (this.needsFinding) body.finding_id = this.findingId;
    if (this.eventType === 'exception') {
      const expiresAt = this.expiresAt.trim();
      if (!/T.*(?:Z|[+-]\d{2}:\d{2})$/.test(expiresAt) || !Number.isFinite(Date.parse(expiresAt))) {
        this.error = 'Enter an expiry with a timezone, such as 2026-12-31T17:00:00Z.';
        return;
      }
      body.expires_at = expiresAt;
    }
    if (this.eventType === 'approve') {
      try {
        if (new TextEncoder().encode(this.reportText).length > 262144) throw new Error();
        const report = JSON.parse(this.reportText);
        if (!report || typeof report !== 'object' || Array.isArray(report)) throw new Error();
        body.report = report;
      } catch {
        this.error = 'Paste the complete JSON reproduction report, up to 256 KiB.';
        return;
      }
    }
    if (this.evidence && !this.review.assessment_job_id)
      body.evidence = { job_id: this.evidence.id, result_sha256: this.evidence.result_sha256 };
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
              assessment_job_id: review.assessment_job_id,
              assessment_result_sha256: review.assessment_result_sha256,
              manifest_sha256: review.manifest_sha256,
            });
            this.directory.total++;
          }
          this.clearDraft(!!review.assessment_job_id);
          this.busy = false;
        },
        error: (error) => {
          if (generation !== this.generation) return;
          this.busy = false;
          // A final authority recheck may withhold a committed response with
          // 403. Preserve that receipt just like a network/storage ambiguity.
          if ([400, 404, 409].includes(error.status)) {
            this.pending = null;
            this.review = null;
            this.clearDraft();
            const code = error.error?.error_code || 'invalid request';
            const guidance: Record<string, string> = {
              review_findings_unaddressed:
                'Resolve open findings or record eligible time-bound exceptions before approval.',
              review_reproduction_report_mismatch:
                'Reproduce the exact current manifest and attach its matching report.',
            };
            this.error = `Action was blocked (${code}). ${guidance[code] ?? 'The evidence, discussion or request may have changed.'} Refresh the review before making another change.`;
          } else {
            if (error.status === 403) {
              this.clearAccess();
            }
            const authority =
              error.status === 403
                ? 'Project authority could not be verified. Ask an administrator to check your current role and reviewer independence. '
                : '';
            this.error = `${authority}The outcome could not be confirmed. Retry the pending action with the same receipt.`;
          }
        },
      }),
    );
  }
  selectEvidence(job: any): void {
    if (!this.review?.bundle_id || this.review.freshness !== 'current' || this.pending || this.busy)
      return;
    if (
      job.state !== 'succeeded' ||
      job.file_id !== this.fileId ||
      job.project_id !== this.projectId ||
      ['bundle_id', 'execution_id', 'assessment_id', 'manifest_sha256'].some(
        (key) => job.specification[key] !== this.review[key],
      )
    ) {
      this.evidence = null;
      this.error = 'This receipt belongs to a different package. Select a check for this review.';
      return;
    }
    this.evidence = job;
    this.error = '';
  }
  downloadEvidence(eventId: string): void {
    if (!this.review || this.busy) return;
    const generation = this.generation;
    const reviewId = this.review.id;
    this.requests.add(
      this.http
        .get(this.url(`${reviewId}/events/${eventId}/receipt`), {
          params: this.params,
          transferCache: false,
          responseType: 'blob',
        })
        .subscribe({
          next: (blob) => {
            if (generation !== this.generation) return;
            downloadBlob(blob, `review-${reviewId}-event-${eventId}.json`);
          },
          error: (error) => {
            if (generation !== this.generation) return;
            if (error.status === 403) {
              this.clearAccess();
            }
            this.error =
              'Linked receipt access or integrity could not be checked. Refresh and retry.';
          },
        }),
    );
  }
  download(kind: 'discussion' | 'package'): void {
    if (!this.review || this.busy || (kind === 'package' && !this.review.bundle_id)) return;
    const selected = this.review;
    const generation = this.generation;
    const save = (blob: Blob, filename: string) => {
      if (generation !== this.generation) return;
      downloadBlob(blob, filename);
    };
    const fail = (error: { status: number }) => {
      if (generation !== this.generation) return;
      if (error.status === 403) this.clearAccess();
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
