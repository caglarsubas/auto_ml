import { Component, OnDestroy, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { Subscription } from 'rxjs';
import { DataService } from '../services/data.service';
import { SharedService } from '../services/shared.service';

@Component({
  selector: 'app-deployment',
  templateUrl: './deployment.component.html',
  styleUrl: './deployment.component.css',
  changeDetection: ChangeDetectionStrategy.Eager,
  standalone: false,
})
export class DeploymentComponent implements OnInit, OnDestroy {
  currentFileId: number | null = null;
  isBundling = false;
  isScoring = false;
  isDownloading = false;
  isReceiptDownloading = false;
  error: string | null = null;
  bundle: any = null;
  scoreResult: any = null;
  readiness: any = null;
  blockers: string[] = [];

  private generation = 0;
  private readinessRequest = 0;
  private bundleRequest = 0;
  private subs: Subscription[] = [];

  constructor(
    private dataService: DataService,
    private sharedService: SharedService,
  ) {}

  get isDeployReady(): boolean {
    return !!this.readiness?.ready;
  }

  ngOnInit(): void {
    this.subs.push(
      this.sharedService.currentFileId$.subscribe((id) => {
        this.currentFileId = id;
        this.generation++;
        this.bundle = null;
        this.scoreResult = null;
        this.readiness = null;
        this.blockers = [];
        this.error = null;
        this.isBundling = this.isScoring = this.isDownloading = false;
        this.isReceiptDownloading = false;
        this.sharedService.setDeploymentCompleted(false);
        if (id != null) {
          this.refreshReadiness(id);
          const generation = this.generation;
          const bundleRequest = ++this.bundleRequest;
          this.subs.push(
            this.dataService.getDeploymentStatus(id).subscribe({
              next: (resp) => {
                if (
                  generation === this.generation &&
                  bundleRequest === this.bundleRequest &&
                  resp?.status === 'ok' &&
                  resp?.bundle_id
                ) {
                  this.bundle = resp;
                  this.scoreResult = null;
                  this.isScoring = false;
                  this.sharedService.setDeploymentCompleted(true);
                }
              },
              error: (err) => {
                if (generation === this.generation)
                  this.error = err?.message || 'Package verification failed.';
              },
            }),
          );
        }
      }),
    );
    this.subs.push(
      this.sharedService.evaluationCompleted$.subscribe((completed) => {
        if (completed && this.currentFileId != null) this.refreshReadiness(this.currentFileId);
      }),
    );
  }

  ngOnDestroy(): void {
    this.generation++;
    this.subs.forEach((s) => s.unsubscribe());
  }

  private refreshReadiness(fileId: number): void {
    const generation = this.generation;
    const request = ++this.readinessRequest;
    this.readiness = null;
    this.blockers = [];
    this.subs.push(
      this.dataService.getDeployReadiness(fileId).subscribe({
        next: (resp) => {
          if (generation !== this.generation) return;
          this.readiness = resp?.readiness || null;
          this.blockers = (this.readiness?.blocking || []).map((b: any) => b.message || String(b));
        },
        error: (err) => {
          if (generation !== this.generation) return;
          this.readiness = {
            ready: false,
            summary:
              err?.error?.error ||
              err?.message ||
              'Package checks unavailable. Retry after completing assessment.',
          };
        },
      }),
    );
  }

  createBundle(): void {
    if (this.currentFileId == null) {
      this.error = 'Select a declaration / modeled file before deployment.';
      return;
    }
    this.isBundling = true;
    this.error = null;
    this.blockers = [];
    if (!this.isDeployReady) {
      this.isBundling = false;
      this.error = 'Complete package checks for this exact model and assessment first.';
      return;
    }
    const generation = this.generation;
    const request = this.readinessRequest;
    this.bundleRequest++;
    this.subs.push(
      this.dataService
        .createDeploymentBundle(
          this.currentFileId,
          this.readiness.execution_id,
          this.readiness.assessment_id,
        )
        .subscribe({
          next: (resp) => {
            if (generation !== this.generation) return;
            this.bundle = resp;
            this.scoreResult = null;
            this.isScoring = false;
            if (request === this.readinessRequest)
              this.readiness = resp?.manifest?.readiness || this.readiness;
            this.isBundling = false;
            this.sharedService.setDeploymentCompleted(true);
            try {
              this.sharedService.triggerCheckpoint('deployment_completed');
            } catch {}
          },
          error: (err) => {
            if (generation !== this.generation) return;
            const body = err?.error || {};
            this.readiness = body.readiness || this.readiness;
            this.blockers = (body.blocking || body.readiness?.blocking || []).map(
              (b: any) => b.message || String(b),
            );
            this.error = body.error || err?.message || 'Bundle creation failed';
            this.isBundling = false;
          },
        }),
    );
  }

  onScoreFile(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files && input.files[0];
    if (!file || this.currentFileId == null || !this.bundle?.bundle_id) {
      return;
    }
    this.isScoring = true;
    this.scoreResult = null;
    this.error = null;
    const generation = this.generation;
    const bundleId = this.bundle.bundle_id;
    this.subs.push(
      this.dataService.scoreDeployment(this.currentFileId, file, bundleId).subscribe({
        next: (resp) => {
          if (generation !== this.generation || this.bundle?.bundle_id !== bundleId) return;
          this.scoreResult = resp;
          this.isScoring = false;
        },
        error: (err) => {
          if (generation !== this.generation) return;
          this.error = err?.error?.error || err?.message || 'Scoring failed';
          this.isScoring = false;
        },
      }),
    );
    input.value = '';
  }

  downloadBundle(): void {
    if (this.currentFileId == null || !this.bundle?.bundle_id) return;
    const generation = this.generation;
    const bundleId = this.bundle.bundle_id;
    this.isDownloading = true;
    this.subs.push(
      this.dataService.downloadDeploymentPack(this.currentFileId, bundleId).subscribe({
        next: (blob) => {
          if (generation !== this.generation || this.bundle?.bundle_id !== bundleId) return;
          const url = URL.createObjectURL(blob);
          const anchor = document.createElement('a');
          anchor.href = url;
          anchor.download = `declarai-bundle-${bundleId}.zip`;
          anchor.click();
          URL.revokeObjectURL(url);
          this.isDownloading = false;
        },
        error: () => {
          if (generation !== this.generation) return;
          this.error =
            'Package download failed verification. Refresh the selected package and retry.';
          this.isDownloading = false;
        },
      }),
    );
  }

  downloadReceipt(): void {
    if (this.currentFileId == null || !this.scoreResult?.receipt_sha256) return;
    const generation = this.generation;
    const { batch_id: batchId, receipt_sha256: digest, bundle_id: bundleId } = this.scoreResult;
    this.isReceiptDownloading = true;
    this.subs.push(
      this.dataService.downloadScoringReceipt(this.currentFileId, batchId, digest).subscribe({
        next: (blob) => {
          if (
            generation !== this.generation ||
            this.bundle?.bundle_id !== bundleId ||
            this.scoreResult?.batch_id !== batchId
          )
            return;
          const url = URL.createObjectURL(blob);
          const anchor = document.createElement('a');
          anchor.href = url;
          anchor.download = `scoring-${batchId}.json`;
          anchor.click();
          URL.revokeObjectURL(url);
          this.isReceiptDownloading = false;
        },
        error: () => {
          if (generation !== this.generation) return;
          this.error = 'Exact scoring receipt download failed. Refresh access and retry.';
          this.isReceiptDownloading = false;
        },
      }),
    );
  }
}
