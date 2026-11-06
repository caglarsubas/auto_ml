import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectorRef, Component, inject, Input, OnChanges, OnDestroy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';
import { AuthService } from '../services/auth.service';

type MembershipRole = 'developer' | 'reviewer' | 'admin' | 'none';

interface MembershipReview {
  username: string;
  role: MembershipRole;
  active: boolean;
  expected: string;
}

interface MembershipChange {
  username: string;
  role: MembershipRole;
  expected: string;
  request_id: string;
}

@Component({
  selector: 'app-project-membership',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './project-membership.component.html',
  styleUrl: './project-membership.component.css',
})
export class ProjectMembershipComponent implements OnChanges, OnDestroy {
  @Input({ required: true }) projectId = '';
  @Input({ required: true }) membershipRevision = '';

  username = '';
  review: MembershipReview | null = null;
  role: MembershipRole = 'none';
  pending: MembershipChange | null = null;
  busy = false;
  error = '';
  receipt = '';
  private request?: Subscription;

  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);
  private readonly changeDetector = inject(ChangeDetectorRef);

  ngOnChanges(): void {
    this.request?.unsubscribe();
    this.username = '';
    this.clearReview();
    this.busy = false;
  }

  clearReview(): void {
    this.review = null;
    this.pending = null;
    this.error = '';
    this.receipt = '';
  }

  lookUp(): void {
    const username = this.username.trim();
    if (!username || this.busy) return;
    this.clearReview();
    this.busy = true;
    this.request = this.http
      .post<MembershipReview>(this.url, {
        operation: 'preview',
        username,
      })
      .subscribe({
        next: (review) => {
          this.review = review;
          this.role = review.role;
          this.busy = false;
          this.changeDetector.markForCheck();
        },
        error: (error: HttpErrorResponse) => {
          this.error =
            error.status === 400
              ? 'Enter the exact username of another enrolled account.'
              : 'Membership could not be checked. Refresh project access and try again.';
          this.busy = false;
          this.changeDetector.markForCheck();
        },
      });
  }

  save(): void {
    const review = this.review;
    if (
      !review ||
      this.busy ||
      this.role === review.role ||
      (!review.active && this.role !== 'none')
    )
      return;
    const change = this.pending ?? {
      username: review.username,
      role: this.role,
      expected: review.expected,
      request_id: crypto.randomUUID(),
    };
    this.pending = change;
    this.busy = true;
    this.error = '';
    this.request = this.http.post<{ event_id: string }>(this.url, change).subscribe({
      next: (result) => {
        this.clearReview();
        this.receipt = result.event_id;
        this.busy = false;
        this.changeDetector.markForCheck();
      },
      error: (error: HttpErrorResponse) => {
        this.busy = false;
        this.changeDetector.markForCheck();
        if (error.status === 0 || error.status >= 500) {
          this.error =
            'The result could not be confirmed. Retry this same change or review current membership.';
          return;
        }
        this.clearReview();
        this.error =
          error.status === 409
            ? 'The reviewed membership changed. Look up the account again before applying a role.'
            : 'The change was refused. Refresh project access and review the account again.';
      },
    });
  }

  ngOnDestroy(): void {
    this.request?.unsubscribe();
  }

  private get url(): string {
    return `${this.auth.apiRoot}projects/${this.projectId}/members/`;
  }
}
