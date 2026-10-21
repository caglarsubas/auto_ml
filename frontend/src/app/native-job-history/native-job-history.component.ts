import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectorRef,
  Component,
  EventEmitter,
  Input,
  OnChanges,
  OnDestroy,
  Output,
  inject,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';
import { AuthService } from '../services/auth.service';

interface HistoryPage {
  observed_at: string;
  history_cutoff: string;
  jobs_enabled: boolean;
  page_size: number;
  previous_cursor: string | null;
  next_cursor: string | null;
  restart_required: boolean;
  jobs: {
    id: string;
    kind: string;
    state: string;
    created_at: string;
    attempts: number;
    reason_code: string;
  }[];
  queue: {
    states: Record<string, number>;
    signals: Record<string, number | null>;
    installation_limits: {
      max_active: number;
      max_pending: number;
      attempts: number;
      lease_seconds: number;
    };
  };
  limitation: string;
}

@Component({
  selector: 'app-native-job-history',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './native-job-history.component.html',
  styleUrl: './native-job-history.component.css',
})
export class NativeJobHistoryComponent implements OnChanges, OnDestroy {
  @Input({ required: true }) fileId!: number;
  @Input({ required: true }) projectId!: string;
  @Output() jobSelected = new EventEmitter<string>();
  page: HistoryPage | null = null;
  busy = false;
  error = '';
  state = '';
  kind = '';
  readonly states = [
    'queued',
    'running',
    'cancel_requested',
    'succeeded',
    'blocked',
    'failed',
    'cancelled',
  ];
  readonly kinds = [
    ['package_integrity_v1', 'Package integrity'],
    ['native_csv_scoring_v1', 'Package CSV scoring'],
    ['native_numeric_training_search_v1', 'Development training search'],
    ['native_training_scoring_v1', 'Native candidate scoring'],
    ['native_protected_assessment_v1', 'Protected assessment'],
  ];
  private request?: Subscription;
  private generation = 0;
  private changeDetector = inject(ChangeDetectorRef);
  constructor(
    private http: HttpClient,
    private auth: AuthService,
  ) {}
  ngOnChanges(): void {
    this.state = this.kind = '';
    this.load();
  }
  load(cursor?: string | null): void {
    const generation = ++this.generation;
    this.request?.unsubscribe();
    this.page = null;
    this.busy = true;
    this.error = '';
    this.request = this.http
      .get<HistoryPage>(`${this.auth.apiRoot}jobs/datasets/${this.fileId}/history/`, {
        params: {
          project_id: this.projectId,
          state: this.state,
          kind: this.kind,
          ...(cursor ? { cursor } : {}),
        },
        transferCache: false,
      })
      .subscribe({
        next: (page) => {
          if (generation !== this.generation) return;
          this.page = page;
          this.busy = false;
          this.changeDetector.markForCheck();
        },
        error: (error) => {
          if (generation !== this.generation) return;
          this.busy = false;
          const code = error.error?.error_code || 'observation_unavailable';
          this.error =
            error.status === 403
              ? 'Queue history access is no longer available. Check your project access before refreshing.'
              : error.status === 409
                ? `History navigation is stale or expired (${code}). Refresh queue and history to start again.`
                : `Queue history could not be observed (${code}). Refresh after service recovery. This does not establish any job outcome.`;
          this.changeDetector.markForCheck();
        },
      });
  }
  ngOnDestroy(): void {
    this.generation++;
    this.request?.unsubscribe();
    this.page = null;
  }
}
