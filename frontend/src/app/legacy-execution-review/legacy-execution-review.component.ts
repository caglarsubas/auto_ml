import { AfterViewInit, Component, ElementRef, OnDestroy, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Subscription } from 'rxjs';
import { LegacyExecutionReviewService } from '../services/legacy-execution-review.service';

@Component({
  selector: 'app-legacy-execution-review',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './legacy-execution-review.component.html',
  styleUrl: './legacy-execution-review.component.css',
})
export class LegacyExecutionReviewComponent implements AfterViewInit, OnDestroy {
  @ViewChild('dialog', { static: true }) dialog!: ElementRef<HTMLDialogElement>;
  private subscription?: Subscription;
  constructor(public review: LegacyExecutionReviewService) {}

  ngAfterViewInit(): void {
    this.subscription = this.review.pending$.subscribe((proposal) => {
      const dialog = this.dialog.nativeElement;
      if (typeof dialog.showModal !== 'function') return;
      if (!proposal) {
        if (dialog.open) dialog.close();
        return;
      }
      setTimeout(() => {
        if (this.review.pending$.value === proposal && !dialog.open) dialog.showModal();
      });
    });
  }
  cancel(event: Event): void {
    event.preventDefault();
    this.review.resolve(false);
  }
  ngOnDestroy(): void {
    this.subscription?.unsubscribe();
    this.review.resolve(false);
  }
}
