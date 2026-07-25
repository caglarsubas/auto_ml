import { Component, ElementRef, HostListener, Input, OnDestroy, OnInit, ViewChild } from '@angular/core';
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
  model?: string;
  lastRun?: PipelineCodelineLastRun;
  updatedAt: string;
}

type AiModelOption = {
  key: string;
  display_name: string;
  provider: string;
  ram_gb?: number;
  tool_calling_mode?: string;
};

@Component({
  selector: 'app-pipeline-codeline',
  templateUrl: './pipeline-codeline.component.html',
  styleUrls: ['./pipeline-codeline.component.css'],
})
export class PipelineCodelineComponent implements OnInit, OnDestroy {
  private static readonly MAX_AUTO_CORRECTION_ATTEMPTS = 3;

  @Input() position!: string;
  @ViewChild('modelSelectorWrapper') modelSelectorWrapper?: ElementRef<HTMLElement>;

  cell: PipelineCodeline | null = null;
  expanded = false;
  private saveTimer: any = null;
  private subs: Subscription[] = [];
  private fileId: number | null = null;
  /** True while an auto-fix chat/re-run cycle is in progress (keeps isBusy). */
  private autoFixing = false;

  previewColumns: string[] = [];
  previewRows: any[] = [];

  availableModels: AiModelOption[] = [];
  defaultModelKey = 'engine-gemma4-26b';
  showModelSelector = false;
  engineStatus: { available: boolean; model_count?: number; last_error?: string | null } | null = null;

  constructor(
    private sharedService: SharedService,
    private dataService: DataService,
  ) {}

  ngOnInit(): void {
    this.fileId = this.sharedService.getCurrentFileId();
    this.loadModels(true);
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
          const nextCell: PipelineCodeline = {
            ...existing,
            model: existing.model || this.defaultModelKey,
          };
          this.cell = nextCell;
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
    return this.autoFixing || this.cell?.lastRun?.status === 'running';
  }

  get hasContent(): boolean {
    return !!(this.cell && (this.cell.code?.trim() || this.cell.intent?.trim() || this.cell.lastRun));
  }

  addCodeline(): void {
    this.cell = this.createEmptyCell();
    this.expanded = true;
    this.loadModels(true);
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
    this.showModelSelector = false;
  }

  deleteCodeline(): void {
    this.cell = null;
    this.expanded = false;
    this.showModelSelector = false;
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

  loadModels(applyDefault: boolean = false): void {
    this.dataService.getAiModels().subscribe({
      next: (resp: any) => {
        this.availableModels = resp.models || [];
        this.engineStatus = resp.engine || null;
        if (resp.default) {
          this.defaultModelKey = resp.default;
        }
        if (applyDefault && this.cell) {
          const current = this.cell.model;
          const known = this.availableModels.some((m) => m.key === current);
          if (!current || !known) {
            this.cell.model = this.defaultModelKey;
            this.persist();
          }
        }
      },
      error: () => {
        if (!this.availableModels.length) {
          this.availableModels = [
            { key: 'engine-gemma4-26b', display_name: 'gemma4:26b (Inference Engine)', provider: 'engine' },
            { key: 'gpt-5.5', display_name: 'GPT-5.5 (OpenAI)', provider: 'openai' },
          ];
          this.defaultModelKey = 'engine-gemma4-26b';
        }
      },
    });
  }

  toggleModelSelector(): void {
    this.showModelSelector = !this.showModelSelector;
    if (this.showModelSelector) {
      this.loadModels();
    }
  }

  @HostListener('document:click', ['$event'])
  closeModelSelectorOnOutsideClick(event: MouseEvent): void {
    if (!this.showModelSelector) return;
    const wrapper = this.modelSelectorWrapper?.nativeElement;
    const target = event.target;
    if (!wrapper || !(target instanceof Node) || !wrapper.contains(target)) {
      this.showModelSelector = false;
    }
  }

  selectModel(modelKey: string): void {
    if (!this.cell) return;
    this.cell.model = modelKey;
    this.showModelSelector = false;
    this.persist(true);
  }

  getSelectedModelName(): string {
    const key = this.cell?.model || this.defaultModelKey;
    const model = this.availableModels.find((m) => m.key === key);
    return model ? model.display_name : key;
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
    const model = this.cell.model || this.defaultModelKey;

    this.dataService
      .sendAiChat(
        intent,
        context,
        `codeline_${this.position}`,
        [],
        this.fileId ?? undefined,
        model,
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
          // Always pin generated code into the Code tab above the assistant reply.
          if (generatedCode) {
            this.cell!.code = generatedCode;
            this.cell!.mode = 'code';
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

  private execute(mode: 'exploratory' | 'apply', attempt: number = 0): void {
    if (!this.cell || (this.isBusy && attempt === 0)) return;
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

    const payload: any = {
      code,
      description: `Codeline at ${this.position}`,
      mode,
      codeline_position: this.position,
    };
    if (attempt > 0) {
      payload.auto_correction_attempt = attempt;
    }

    this.dataService
      .executeAiAction(
        this.fileId,
        'execute_code',
        payload,
        undefined,
        'codeline',
      )
      .subscribe({
        next: (resp: any) => {
          if (resp?.status === 'error') {
            const fullError = this.formatExecutionError(resp);
            this.handleExecutionFailure(mode, code, fullError, attempt, resp);
          } else {
            this.autoFixing = false;
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
            this.refreshPreviewTables();
            this.persist(true);
          }
        },
        error: (err: any) => {
          const errMsg = err?.error?.error || err?.error?.message || err?.message || 'Execution failed.';
          const traceback = err?.error?.traceback || '';
          const fullError = traceback ? `${errMsg}\n${traceback}` : errMsg;
          this.handleExecutionFailure(mode, code, fullError, attempt, err?.error);
        },
      });
  }

  private formatExecutionError(resp: any): string {
    const errMsg = resp?.error || 'Execution failed.';
    const traceback = resp?.traceback || '';
    return traceback ? `${errMsg}\n${traceback}` : errMsg;
  }

  private handleExecutionFailure(
    mode: 'exploratory' | 'apply',
    failedCode: string,
    fullError: string,
    attempt: number,
    resp?: any,
  ): void {
    this.patchLastRun({
      status: 'error',
      runKind: mode,
      error: fullError,
      stdout: resp?.stdout || '',
      images: resp?.images || [],
    });
    this.persist(true);

    const nextAttempt = attempt + 1;
    if (nextAttempt > PipelineCodelineComponent.MAX_AUTO_CORRECTION_ATTEMPTS) {
      this.autoFixing = false;
      const max = PipelineCodelineComponent.MAX_AUTO_CORRECTION_ATTEMPTS;
      this.patchLastRun({
        status: 'error',
        runKind: mode,
        error: fullError,
        assistantText:
          `I tried ${max} automatic correction attempts, but the code still failed. ` +
          `The last error was:\n\n${fullError}`,
      });
      this.persist(true);
      return;
    }

    this.requestErrorCorrection(mode, failedCode, fullError, nextAttempt);
  }

  private requestErrorCorrection(
    mode: 'exploratory' | 'apply',
    failedCode: string,
    errorText: string,
    attempt: number,
  ): void {
    if (!this.cell || this.fileId == null) {
      this.autoFixing = false;
      return;
    }

    this.autoFixing = true;
    const max = PipelineCodelineComponent.MAX_AUTO_CORRECTION_ATTEMPTS;
    const firstErrorLine = errorText.split('\n')[0].trim();
    const correctionPrompt =
      `The following Codeline execute_code action failed with an error.\n\n` +
      `**Failed code:**\n\`\`\`python\n${failedCode}\n\`\`\`\n\n` +
      `**Error:**\n\`\`\`\n${errorText}\n\`\`\`\n\n` +
      `Please analyze the error and provide a corrected execute_code action block. ` +
      `Sandbox builtins: pandas (pd), numpy (np), DataFrame (df), and matplotlib.pyplot (plt). ` +
      `No imports, no open(), no __import__, no globals()/locals()/eval()/exec(). ` +
      `Fix the issue and respond with exactly one corrected execute_code action.\n\n` +
      `This is automated correction attempt ${attempt} of ${max}. ` +
      `The user already approved running this Codeline (${mode}), so return the corrected code ` +
      `without asking them to click Run/Apply again.`;

    this.patchLastRun({
      status: 'running',
      runKind: 'assistant',
      error: errorText,
      assistantText:
        `Code run failed: ${firstErrorLine} — auto-fix attempt ${attempt}/${max}...`,
    });
    this.persist(true);

    const context = {
      ...(this.sharedService.getAiCumulativeContext() || {}),
      codeline_position: this.position,
      codeline_code: failedCode,
      auto_correction_attempt: attempt,
      execute_mode: mode,
    };
    const model = this.cell.model || this.defaultModelKey;

    this.dataService
      .sendAiChat(
        correctionPrompt,
        context,
        `codeline_${this.position}`,
        [],
        this.fileId ?? undefined,
        model,
        undefined,
        undefined,
        'codeline',
      )
      .subscribe({
        next: (resp: any) => {
          const actions = Array.isArray(resp?.actions) ? resp.actions : [];
          const executeAction = actions.find((a: any) => a?.type === 'execute_code');
          const correctedCode = (
            executeAction?.payload?.code ||
            this.extractCodeFence(resp?.message || resp?.response || '') ||
            ''
          ).trim();
          const rawText = (resp?.message || resp?.response || '').trim();
          const assistantText = this.stripActionBlocks(rawText);

          if (!correctedCode) {
            this.autoFixing = false;
            this.patchLastRun({
              status: 'error',
              runKind: mode,
              error: errorText,
              assistantText:
                assistantText ||
                'Auto-fix failed: assistant did not return corrected code.',
            });
            this.persist(true);
            return;
          }

          this.cell!.code = correctedCode;
          this.cell!.mode = 'code';
          this.patchLastRun({
            status: 'running',
            runKind: mode,
            generatedCode: correctedCode,
            assistantText:
              (assistantText || 'Applying corrected code...') +
              `\n\nRe-running (${mode}) — auto-fix attempt ${attempt}/${max}...`,
            error: undefined,
          });
          this.persist(true);
          this.execute(mode, attempt);
        },
        error: (err: any) => {
          this.autoFixing = false;
          this.patchLastRun({
            status: 'error',
            runKind: mode,
            error: errorText,
            assistantText:
              err?.error?.error || err?.message || 'Failed to get AI correction.',
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
      model: this.defaultModelKey,
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
