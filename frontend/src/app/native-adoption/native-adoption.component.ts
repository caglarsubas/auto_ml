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
import { AuthService } from '../services/auth.service';

@Component({
  selector: 'app-native-adoption',
  standalone: true,
  imports: [FormsModule, JsonPipe],
  templateUrl: './native-adoption.component.html',
  styleUrl: './native-adoption.component.css',
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class NativeAdoptionComponent implements OnChanges, OnDestroy {
  @Input({ required: true }) job: any;
  @Input({ required: true }) projectId!: string;
  @Input({ required: true }) role!: string;
  @Input() jobsEnabled = false;
  @Output() queued = new EventEmitter<any>();
  directory: any[] = [];
  adoption: any = null;
  selected: any = null;
  preview: any = null;
  proposalRationale = '';
  reviewRationale = '';
  custodyRationale = '';
  asOf = '';
  proposalConfirmed = false;
  reviewConfirmed = false;
  custodyConfirmed = false;
  executionConfirmed = false;
  file: File | null = null;
  busy = false;
  error = '';
  pending: { url: string; body: any; kind: string } | null = null;
  private requests = new Subscription();
  private generation = 0;
  constructor(
    private http: HttpClient,
    private auth: AuthService,
  ) {}
  private url(value: string) {
    return `${this.auth.apiRoot}${value}/`;
  }
  private get params() {
    return { project_id: this.projectId };
  }
  get canAssess(): boolean {
    return (
      this.role === 'reviewer' &&
      this.adoption?.usable &&
      this.adoption.events.at(-1)?.payload.actor.id === this.auth.user?.id
    );
  }
  ngOnChanges(): void {
    this.generation++;
    this.requests.unsubscribe();
    this.requests = new Subscription();
    this.directory = [];
    this.adoption = this.selected = this.preview = this.pending = null;
    this.file = null;
    this.proposalRationale =
      this.reviewRationale =
      this.custodyRationale =
      this.asOf =
      this.error =
        '';
    this.proposalConfirmed =
      this.reviewConfirmed =
      this.custodyConfirmed =
      this.executionConfirmed =
      this.busy =
        false;
    this.refresh();
  }
  refresh(): void {
    if (this.busy || this.pending || !this.job?.id) return;
    this.busy = true;
    const generation = ++this.generation;
    this.requests.add(
      this.http
        .get<any>(this.url(`jobs/${this.job.id}/adoptions`), {
          params: this.params,
          transferCache: false,
        })
        .subscribe({
          next: (value) => {
            if (generation !== this.generation) return;
            this.directory = value.adoptions;
            this.busy = false;
            this.error = '';
            this.choose(
              this.directory.find((a: any) => a.id === this.adoption?.id) ||
                this.directory[0] ||
                null,
            );
          },
          error: (error) => this.fail(generation, error, false),
        }),
    );
  }
  choose(value: any): void {
    if (this.pending) return;
    this.adoption = value;
    this.selected = null;
    this.preview = null;
    this.executionConfirmed = this.reviewConfirmed = this.custodyConfirmed = false;
    this.file = null;
  }
  changed(): void {
    this.proposalConfirmed =
      this.reviewConfirmed =
      this.custodyConfirmed =
      this.executionConfirmed =
        false;
    this.preview = null;
  }
  selectFile(event: Event): void {
    this.file = (event.target as HTMLInputElement).files?.[0] || null;
    this.custodyConfirmed = false;
    this.preview = null;
    this.executionConfirmed = false;
  }
  propose(): void {
    if (
      this.role !== 'developer' ||
      !this.proposalConfirmed ||
      !this.proposalRationale.trim() ||
      this.busy ||
      this.pending
    )
      return;
    this.action(
      `jobs/${this.job.id}/adoptions`,
      {
        request_id: crypto.randomUUID(),
        training_result_sha256: this.job.result_sha256,
        rationale: this.proposalRationale,
      },
      'adoption',
    );
  }
  decide(action: 'approve' | 'revoke'): void {
    if (
      this.role !== 'reviewer' ||
      !this.adoption ||
      !this.reviewRationale.trim() ||
      !this.reviewConfirmed ||
      this.busy ||
      this.pending
    )
      return;
    if (
      (action === 'approve' && this.adoption.state !== 'proposed') ||
      (action === 'revoke' && this.adoption.state !== 'accepted')
    )
      return;
    this.action(
      `native-adoptions/${this.adoption.id}`,
      {
        request_id: crypto.randomUUID(),
        expected_revision: this.adoption.revision,
        proposal_sha256: this.adoption.proposal_sha256,
        action,
        rationale: this.reviewRationale,
      },
      'adoption',
    );
  }
  seal(): void {
    if (
      !this.canAssess ||
      !this.file ||
      !this.custodyConfirmed ||
      !this.custodyRationale.trim() ||
      !this.asOf ||
      this.busy ||
      this.pending
    )
      return;
    const body = new FormData();
    body.set('request_id', crypto.randomUUID());
    body.set('proposal_sha256', this.adoption.proposal_sha256);
    body.set('rationale', this.custodyRationale);
    body.set('assessment_as_of', this.asOf);
    body.set('population_and_maturity_attested', 'true');
    body.set('file', this.file);
    this.action(`native-adoptions/${this.adoption.id}/protected-inputs`, body, 'seal');
  }
  selectInput(value: any): void {
    if (this.pending || this.busy) return;
    this.selected = value;
    this.preview = null;
    this.executionConfirmed = false;
  }
  prepare(): void {
    if (!this.canAssess || !this.selected || !this.jobsEnabled || this.busy || this.pending) return;
    this.busy = true;
    this.preview = null;
    this.executionConfirmed = false;
    const generation = ++this.generation;
    this.requests.add(
      this.http
        .post<any>(
          this.url(`native-protected-inputs/${this.selected.id}/preview`),
          {},
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
      !this.canAssess ||
      !this.preview ||
      !this.executionConfirmed ||
      !this.jobsEnabled ||
      this.busy ||
      this.pending
    )
      return;
    if (
      this.preview.protected_input_id !== this.selected?.id ||
      this.preview.adoption_id !== this.adoption.id ||
      this.preview.proposal_sha256 !== this.adoption.proposal_sha256
    ) {
      this.changed();
      return;
    }
    this.action(
      `jobs/datasets/${this.job.file_id}`,
      {
        request_id: crypto.randomUUID(),
        kind: 'native_protected_assessment_v1',
        protected_input_id: this.selected.id,
        assessment_sha256: this.preview.assessment_sha256,
      },
      'assessment',
    );
  }
  private action(path: string, body: any, kind: string): void {
    this.pending = { url: this.url(path), body, kind };
    this.retry();
  }
  retry(): void {
    if (!this.pending || this.busy) return;
    const action = this.pending,
      generation = ++this.generation;
    this.busy = true;
    this.error = '';
    this.requests.add(
      this.http.post<any>(action.url, action.body, { params: this.params }).subscribe({
        next: (value) => {
          if (generation !== this.generation) return;
          this.busy = false;
          this.pending = null;
          this.preview = null;
          this.executionConfirmed = false;
          if (action.kind === 'assessment') {
            this.queued.emit(value);
            return;
          }
          this.adoption = value;
          const index = this.directory.findIndex((a: any) => a.id === value.id);
          if (index < 0) this.directory.unshift(value);
          else this.directory[index] = value;
          if (action.kind === 'seal') {
            this.file = null;
            this.custodyConfirmed = false;
            this.selected = value.protected_inputs.find(
              (p: any) => p.id === action.body.get('request_id'),
            );
          }
          this.reviewConfirmed = false;
        },
        error: (error) => this.fail(generation, error, true),
      }),
    );
  }
  private fail(generation: number, error: any, mutation: boolean): void {
    if (generation !== this.generation) return;
    this.busy = false;
    this.preview = null;
    this.executionConfirmed = this.reviewConfirmed = this.custodyConfirmed = false;
    if (mutation && ![400, 404, 409].includes(error.status)) {
      this.error =
        'The action outcome is unconfirmed. Retry the identical pending request after access or service recovery.';
    } else {
      this.pending = null;
      this.adoption = this.selected = null;
      this.directory = [];
      this.file = null;
      this.error = `Adoption or assessment blocked (${error.error?.error_code || 'unavailable'}). Refresh the evidence and review again.`;
    }
  }
  ngOnDestroy(): void {
    this.generation++;
    this.requests.unsubscribe();
  }
}
