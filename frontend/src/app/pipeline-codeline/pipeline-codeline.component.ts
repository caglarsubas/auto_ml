import { Component, Input, OnDestroy, OnInit } from '@angular/core';
import { Subscription } from 'rxjs';
import { SharedService } from '../services/shared.service';
import { DataService } from '../services/data.service';

export interface PipelineCodelineLastRun {
  status: 'idle' | 'running' | 'success' | 'error';
  runKind?: 'exploratory' | 'apply' | 'assistant';
  stdout?: string;
  error?: string;
  preview?: any;
  images?: string[];
  changes?: any;
  assistantText?: string;
  generatedCode?: string;
}

export interface PipelineCodeline {
  id: string;
  position: string;
  mode: 'code' | 'intent';
  code: string;
  intent: string;
  lastRun?: PipelineCodelineLastRun;
  updatedAt: string;
}

@Component({
  selector: 'app-pipeline-codeline',
  templateUrl: './pipeline-codeline.component.html',
  styleUrls: ['./pipeline-codeline.component.css'],
})
export class PipelineCodelineComponent implements OnInit, OnDestroy {
  @Input() position!: string;

  cell: PipelineCodeline | null = null;
  expanded = false;
  private saveTimer: any = null;
  private subs: Subscription[] = [];
  private fileId: number | null = null;

  previewColumns: string[] = [];
  previewRows: any[] = [];

  constructor(
    private sharedService: SharedService,
    private dataService: DataService,
  ) {}

  ngOnInit(): void {
    this.fileId = this.sharedService.getCurrentFileId();
    this.subs.push(
      this.sharedService.currentFileId$.subscribe((id) => {
        this.fileId = id;
      }),
    );
    this.subs.push(
      this.sharedService.pipelineCodelines$.subscribe((map) => {
        const existing = map?.[this.position] || null;
        if (existing) {
          // Sync from shared state (checkpoint restore / cross-component).
          // Do not force-expand — respect the user's Done/collapse choice.
          const wasEmpty = !this.cell;
          this.cell = { ...existing };
          if (wasEmpty) {
            this.expanded = false;
          }
          this.refreshPreviewTables();
        } else if (!this.expanded) {
          this.cell = null;
        }
      }),
    );
  }

  ngOnDestroy(): void {
    this.subs.forEach((s) => s.unsubscribe());
    if (this.saveTimer) clearTimeout(this.saveTimer);
  }

  get isBusy(): boolean {
    return this.cell?.lastRun?.status === 'running';
  }

  get hasContent(): boolean {
    return !!(this.cell && (this.cell.code?.trim() || this.cell.intent?.trim() || this.cell.lastRun));
  }

  addCodeline(): void {
    this.cell = this.createEmptyCell();
    this.expanded = true;
    this.persist(true);
  }

  collapse(): void {
    if (!this.hasContent) {
      this.expanded = false;
      this.cell = null;
      this.sharedService.deletePipelineCodeline(this.position);
      this.scheduleCheckpoint();
      return;
    }
    this.expanded = false;
  }

  deleteCodeline(): void {
    this.cell = null;
    this.expanded = false;
    this.previewColumns = [];
    this.previewRows = [];
    this.sharedService.deletePipelineCodeline(this.position);
    this.scheduleCheckpoint(0);
  }

  setMode(mode: 'code' | 'intent'): void {
    if (!this.cell) return;
    this.cell.mode = mode;
    this.persist();
  }

  onCodeChanged(value: string): void {
    if (!this.cell) return;
    this.cell.code = value;
    this.persist();
  }

  onIntentChanged(value: string): void {
    if (!this.cell) return;
    this.cell.intent = value;
    this.persist();
  }

  runExploratory(): void {
    this.execute('exploratory');
  }

  applyToDataset(): void {
    this.execute('apply');
  }

  askAssistant(): void {
    if (!this.cell || this.isBusy) return;
    const intent = (this.cell.intent || '').trim();
    if (!intent) {
      this.patchLastRun({
        status: 'error',
        runKind: 'assistant',
        error: 'Write a natural-language intent before asking the assistant.',
      });
      return;
    }

    this.patchLastRun({
      status: 'running',
      runKind: 'assistant',
      error: undefined,
      assistantText: undefined,
      generatedCode: undefined,
    });

    const context = {
      ...(this.sharedService.getAiCumulativeContext() || {}),
      codeline_position: this.position,
      codeline_code: this.cell.code || '',
    };

    this.dataService
      .sendAiChat(
        intent,
        context,
        `codeline_${this.position}`,
        [],
        this.fileId ?? undefined,
        undefined,
        undefined,
        undefined,
        'codeline',
      )
      .subscribe({
        next: (resp: any) => {
          const actions = Array.isArray(resp?.actions) ? resp.actions : [];
          const executeAction = actions.find((a: any) => a?.type === 'execute_code');
          const generatedCode =
            executeAction?.payload?.code ||
            this.extractCodeFence(resp?.message || resp?.response || '') ||
            '';
          const rawText = (resp?.message || resp?.response || '').trim();
          const assistantText = this.stripActionBlocks(rawText);
          this.patchLastRun({
            status: 'success',
            runKind: 'assistant',
            assistantText: assistantText || (generatedCode ? 'Assistant suggested code for this Codeline.' : 'No response.'),
            generatedCode: generatedCode || undefined,
            error: undefined,
          });
          if (generatedCode && !(this.cell!.code || '').trim()) {
            this.cell!.code = generatedCode;
          }
          this.persist(true);
        },
        error: (err: any) => {
          this.patchLastRun({
            status: 'error',
            runKind: 'assistant',
            error: err?.error?.error || err?.message || 'Assistant request failed.',
          });
          this.persist(true);
        },
      });
  }

  useGeneratedCode(): void {
    if (!this.cell?.lastRun?.generatedCode) return;
    this.cell.code = this.cell.lastRun.generatedCode;
    this.cell.mode = 'code';
    this.persist(true);
  }

  private execute(mode: 'exploratory' | 'apply'): void {
    if (!this.cell || this.isBusy) return;
    const code = (this.cell.code || '').trim();
    if (!code) {
      this.patchLastRun({
        status: 'error',
        runKind: mode,
        error: 'Write some code before running.',
      });
      return;
    }
    if (this.fileId == null) {
      this.patchLastRun({
        status: 'error',
        runKind: mode,
        error: 'No dataset loaded. Upload data before running a Codeline.',
      });
      return;
    }

    this.patchLastRun({
      status: 'running',
      runKind: mode,
      error: undefined,
      stdout: undefined,
      preview: undefined,
      images: undefined,
      changes: undefined,
    });

    this.dataService
      .executeAiAction(this.fileId, 'execute_code', {
        code,
        description: `Codeline at ${this.position}`,
        mode,
      })
      .subscribe({
        next: (resp: any) => {
          if (resp?.status === 'error') {
            this.patchLastRun({
              status: 'error',
              runKind: mode,
              error: resp?.error || 'Execution failed.',
              stdout: resp?.stdout || '',
              images: resp?.images || [],
            });
          } else {
            this.patchLastRun({
              status: 'success',
              runKind: mode,
              stdout: resp?.stdout || '',
              preview: resp?.preview || null,
              images: resp?.images || [],
              changes: resp?.changes || null,
              error: undefined,
            });
            if (mode === 'apply') {
              this.sharedService.triggerDataRefresh();
            }
          }
          this.refreshPreviewTables();
          this.persist(true);
        },
        error: (err: any) => {
          this.patchLastRun({
            status: 'error',
            runKind: mode,
            error: err?.error?.error || err?.message || 'Execution failed.',
          });
          this.persist(true);
        },
      });
  }

  private createEmptyCell(): PipelineCodeline {
    return {
      id: this.newId(),
      position: this.position,
      mode: 'code',
      code: '',
      intent: '',
      lastRun: { status: 'idle' },
      updatedAt: new Date().toISOString(),
    };
  }

  private newId(): string {
    if (typeof crypto !== 'undefined' && typeof (crypto as any).randomUUID === 'function') {
      return (crypto as any).randomUUID();
    }
    return `cl_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
  }

  private patchLastRun(partial: Partial<PipelineCodelineLastRun>): void {
    if (!this.cell) return;
    this.cell.lastRun = {
      ...(this.cell.lastRun || { status: 'idle' }),
      ...partial,
    };
    this.refreshPreviewTables();
  }

  private persist(immediateCheckpoint = false): void {
    if (!this.cell) return;
    this.cell.updatedAt = new Date().toISOString();
    this.sharedService.updatePipelineCodeline(this.position, { ...this.cell });
    this.scheduleCheckpoint(immediateCheckpoint ? 0 : 1000);
  }

  private scheduleCheckpoint(delayMs = 1000): void {
    if (this.saveTimer) clearTimeout(this.saveTimer);
    this.saveTimer = setTimeout(() => {
      this.sharedService.triggerCheckpoint(`codeline_${this.position}`);
    }, delayMs);
  }

  private refreshPreviewTables(): void {
    const preview = this.cell?.lastRun?.preview;
    if (preview && Array.isArray(preview.columns) && Array.isArray(preview.top_rows)) {
      this.previewColumns = preview.columns;
      this.previewRows = preview.top_rows;
    } else {
      this.previewColumns = [];
      this.previewRows = [];
    }
  }

  private extractCodeFence(text: string): string {
    if (!text) return '';
    const m = text.match(/```(?:python|py)?\s*([\s\S]*?)```/i);
    return m ? m[1].trim() : '';
  }

  private stripActionBlocks(text: string): string {
    if (!text) return '';
    return text
      .replace(/<<<ACTION:[\s\S]*?<<<END_ACTION>>>/g, '')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  }

  cellValue(row: any, col: string): string {
    const v = row?.[col];
    if (v === null || v === undefined) return '';
    return String(v);
  }
}
