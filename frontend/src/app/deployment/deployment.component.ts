import { Component, OnDestroy, OnInit } from '@angular/core';
import { Subscription } from 'rxjs';
import { DataService } from '../services/data.service';
import { SharedService } from '../services/shared.service';

@Component({
  selector: 'app-deployment',
  templateUrl: './deployment.component.html',
  styleUrl: './deployment.component.css'
})
export class DeploymentComponent implements OnInit, OnDestroy {
  currentFileId: number | null = null;
  isBundling = false;
  isScoring = false;
  error: string | null = null;
  bundle: any = null;
  scoreResult: any = null;

  private subs: Subscription[] = [];

  constructor(
    private dataService: DataService,
    private sharedService: SharedService,
  ) {}

  ngOnInit(): void {
    this.subs.push(
      this.sharedService.currentFileId$.subscribe((id) => {
        this.currentFileId = id;
        if (id != null) {
          this.dataService.getDeploymentStatus(id).subscribe({
            next: (resp) => {
              if (resp?.status === 'ok' || resp?.bundle_path) {
                this.bundle = resp;
              }
            },
            error: () => {},
          });
        }
      }),
    );
  }

  ngOnDestroy(): void {
    this.subs.forEach((s) => s.unsubscribe());
  }

  createBundle(): void {
    if (this.currentFileId == null) {
      this.error = 'Select a declaration / modeled file before deployment.';
      return;
    }
    this.isBundling = true;
    this.error = null;
    this.dataService.createDeploymentBundle(this.currentFileId).subscribe({
      next: (resp) => {
        this.bundle = resp;
        this.isBundling = false;
      },
      error: (err) => {
        this.error = err?.message || 'Bundle creation failed';
        this.isBundling = false;
      },
    });
  }

  onScoreFile(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files && input.files[0];
    if (!file || this.currentFileId == null) {
      return;
    }
    this.isScoring = true;
    this.error = null;
    this.dataService.scoreDeployment(this.currentFileId, file).subscribe({
      next: (resp) => {
        this.scoreResult = resp;
        this.isScoring = false;
      },
      error: (err) => {
        this.error = err?.message || 'Scoring failed';
        this.isScoring = false;
      },
    });
    input.value = '';
  }
}
