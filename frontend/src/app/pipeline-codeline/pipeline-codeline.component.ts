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

/** What produced a turn: the first ask, user feedback, or an auto error fix. */
export type PipelineCodelineTurnKind = 'intent' | 'refine' | 'auto_fix';

/**
 * One message in a Codeline's own conversation thread.
 *
 * The thread is what makes a Codeline accumulative rather than single-shot:
 * every ask, every piece of user feedback, and every assistant answer stays
 * with the cell, is replayed as chat history on the next turn, and is
 * checkpointed with the rest of the cell state.
 */
export interface PipelineCodelineTurn {
  role: 'user' | 'assistant';
  kind: PipelineCodelineTurnKind;
  /** Raw, user-readable text — the ask/feedback, or the assistant's prose. */
  content: string;
  /** Assistant turns: the code this turn pinned into the cell. */
  code?: string;
  at: string;
  /** Prometa ids of the chat turn, used to attach refine feedback to it. */
  chatSpanId?: string;
  chatTraceId?: string;
  chatSessionId?: string;
}

export interface PipelineCodeline {
  id: string;
  position: string;
  mode: 'code' | 'intent';
  code: string;
  intent: string;
  model?: string;
  lastRun?: PipelineCodelineLastRun;
  turns?: PipelineCodelineTurn[];
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
  /** Turns kept on the cell (checkpointed); older ones are dropped. */
  private static readonly MAX_THREAD_TURNS = 40;
  /** Turns replayed to the model — engine models run on ~8K windows. */
  private static readonly MAX_HISTORY_TURNS = 8;
  private static readonly MAX_HISTORY_TURN_CHARS = 1200;
  private static readonly MAX_HISTORY_CODE_CHARS = 4000;
  private static readonly MAX_RUN_EXCERPT_CHARS = 800;

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

  /** Draft feedback for the next refinement turn. */
  refineText = '';
  showThread = true;

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

  get turns(): PipelineCodelineTurn[] {
    return this.cell?.turns || [];
  }

  /**
   * How many rounds the user has driven on this cell — the iteration badge.
   * Automatic error-correction rounds are excluded: they are the machine
   * retrying itself, and ``auto_correction_attempt`` already tracks them.
   */
  get iterationCount(): number {
    return this.turns.filter((t) => t.role === 'user' && t.kind !== 'auto_fix').length;
  }

  /**
   * Refinement is offered once the assistant has answered in this cell.
   * Cells restored from a checkpoint written before threads existed have no
   * turns but do carry ``lastRun.assistantText`` — they qualify too and get
   * their thread seeded on the first refinement (see ``ensureThreadSeeded``).
   */
  get canRefine(): boolean {
    if (!this.cell) return false;
    if (this.turns.some((t) => t.role === 'assistant')) return true;
    return !!(this.cell.lastRun?.assistantText || this.cell.lastRun?.generatedCode);
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
    this.refineText = '';
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

  /**
   * First ask (or a re-ask with a rewritten intent) for this Codeline.
   *
   * The cell's own thread is replayed as chat history so consecutive asks
   * accumulate instead of each one starting from a blank slate.
   */
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

    this.ensureThreadSeeded();
    const history = this.buildHistory();
    this.appendTurn({ role: 'user', kind: 'intent', content: intent });

    this.patchLastRun({
      status: 'running',
      runKind: 'assistant',
      error: undefined,
      assistantText: undefined,
      generatedCode: undefined,
    });
    this.persist();

    this.postAssistantChat(intent, 'intent', history, undefined, {
      next: (resp: any) => this.absorbAssistantReply(resp, 'intent'),
      error: (err: any) => this.absorbAssistantError(err),
    });
  }

  /**
   * Send feedback on the answer the assistant already gave in this cell.
   *
   * Unlike ``askAssistant``, this states outright that the previous draft is
   * the thing being revised: the pinned code, the outcome of its last run,
   * and the whole thread go along with the feedback, so successive rounds
   * refine one artifact instead of re-answering from scratch.
   */
  sendRefinement(): void {
    if (!this.cell || this.isBusy) return;
    const feedback = (this.refineText || '').trim();
    if (!feedback) {
      this.patchLastRun({
        status: 'error',
        runKind: 'assistant',
        error: 'Describe what should change before sending feedback.',
      });
      return;
    }

    this.ensureThreadSeeded();
    const history = this.buildHistory();
    const prompt = this.buildRefinePrompt(feedback);
    this.appendTurn({ role: 'user', kind: 'refine', content: feedback });
    this.refineText = '';

    // The previous run's output belongs to the code being replaced — drop it
    // so the pane never shows stale stdout/preview/charts next to new code.
    this.patchLastRun({
      status: 'running',
      runKind: 'assistant',
      error: undefined,
      assistantText: undefined,
      generatedCode: undefined,
      stdout: undefined,
      preview: undefined,
      images: undefined,
      changes: undefined,
    });
    this.persist();
    this.recordRefineFeedback(feedback);

    this.postAssistantChat(prompt, 'refine', history, undefined, {
      next: (resp: any) => this.absorbAssistantReply(resp, 'refine'),
      error: (err: any) => this.absorbAssistantError(err),
    });
  }

  onRefineChanged(value: string): void {
    this.refineText = value;
  }

  /** Drop the thread but keep the code/intent — a fresh start on this cell. */
  clearThread(): void {
    if (!this.cell) return;
    this.cell.turns = [];
    this.refineText = '';
    this.persist(true);
  }

  turnRoleLabel(turn: PipelineCodelineTurn): string {
    if (turn.role === 'assistant') return 'Assistant';
    if (turn.kind === 'refine') return 'Your feedback';
    if (turn.kind === 'auto_fix') return 'Auto-fix';
    return 'You';
  }

  /** Apply a thread turn's code back into the cell (revert to an earlier draft). */
  restoreTurnCode(turn: PipelineCodelineTurn): void {
    if (!this.cell || !turn.code || this.isBusy) return;
    this.cell.code = turn.code;
    this.cell.mode = 'code';
    this.persist(true);
  }

  private postAssistantChat(
    message: string,
    kind: PipelineCodelineTurnKind,
    history: Array<{ role: string; content: string }>,
    extraContext: any,
    handlers: { next: (resp: any) => void; error: (err: any) => void },
  ): void {
    const context = {
      ...(this.sharedService.getAiCumulativeContext() || {}),
      codeline_position: this.position,
      codeline_code: this.cell?.code || '',
      codeline_turn_kind: kind,
      codeline_iteration: this.iterationCount,
      ...(extraContext || {}),
    };
    const model = this.cell?.model || this.defaultModelKey;

    this.dataService
      .sendAiChat(
        message,
        context,
        `codeline_${this.position}`,
        history,
        this.fileId ?? undefined,
        model,
        undefined,
        undefined,
        'codeline',
      )
      .subscribe(handlers);
  }

  /** Pin the reply's code, record the assistant turn, refresh the output pane. */
  private absorbAssistantReply(resp: any, kind: PipelineCodelineTurnKind): void {
    if (!this.cell) return;
    const parsed = this.parseAssistantReply(resp);
    this.patchLastRun({
      status: 'success',
      runKind: 'assistant',
      assistantText:
        parsed.text || (parsed.code ? 'Assistant suggested code for this Codeline.' : 'No response.'),
      generatedCode: parsed.code || undefined,
      error: undefined,
    });
    // Always pin generated code into the Code tab above the assistant reply.
    if (parsed.code) {
      this.cell.code = parsed.code;
      this.cell.mode = 'code';
    }
    this.appendTurn({
      role: 'assistant',
      kind,
      content: parsed.text || (parsed.code ? 'Suggested code for this Codeline.' : 'No response.'),
      code: parsed.code || undefined,
      chatSpanId: parsed.chatSpanId,
      chatTraceId: parsed.chatTraceId,
      chatSessionId: parsed.chatSessionId,
    });
    this.persist(true);
  }

  private absorbAssistantError(err: any): void {
    this.patchLastRun({
      status: 'error',
      runKind: 'assistant',
      error: err?.error?.error || err?.message || 'Assistant request failed.',
    });
    this.persist(true);
  }

  private parseAssistantReply(resp: any): {
    text: string;
    code: string;
    chatSpanId?: string;
    chatTraceId?: string;
    chatSessionId?: string;
  } {
    const actions = Array.isArray(resp?.actions) ? resp.actions : [];
    const executeAction = actions.find((a: any) => a?.type === 'execute_code');
    const rawText = (resp?.message || resp?.response || '').trim();
    return {
      text: this.stripActionBlocks(rawText),
      code: (executeAction?.payload?.code || this.extractCodeFence(rawText) || '').trim(),
      chatSpanId: resp?.chat_span_id,
      chatTraceId: resp?.chat_trace_id,
      chatSessionId: resp?.chat_session_id,
    };
  }

  /**
   * Replay the thread as chat history.
   *
   * Only the newest assistant turn carries its code: earlier drafts are
   * superseded, and repeating each one would blow a small-context engine
   * model's window well before the interesting turns are read.
   */
  private buildHistory(): Array<{ role: string; content: string }> {
    const recent = this.turns.slice(-PipelineCodelineComponent.MAX_HISTORY_TURNS);
    let lastAssistant = -1;
    recent.forEach((t, i) => {
      if (t.role === 'assistant') lastAssistant = i;
    });
    return recent
      .map((turn, i) => {
        let content = this.truncate(
          turn.content || '',
          PipelineCodelineComponent.MAX_HISTORY_TURN_CHARS,
        );
        if (turn.role === 'assistant' && i === lastAssistant && turn.code) {
          const code = this.truncate(
            turn.code,
            PipelineCodelineComponent.MAX_HISTORY_CODE_CHARS,
          );
          content = `${content}\n\n\`\`\`python\n${code}\n\`\`\``.trim();
        }
        return { role: turn.role as string, content: content.trim() };
      })
      .filter((m) => !!m.content);
  }

  private buildRefinePrompt(feedback: string): string {
    const parts: string[] = [
      'Feedback on the Codeline answer you just gave:\n\n' + feedback,
    ];
    const code = (this.cell?.code || '').trim();
    if (code) {
      parts.push(
        'This is the code currently pinned in the cell — the exact draft to ' +
          'revise (the user may have edited it by hand):\n' +
          '```python\n' +
          this.truncate(code, PipelineCodelineComponent.MAX_HISTORY_CODE_CHARS) +
          '\n```',
      );
    }
    const outcome = this.describeLastRun();
    if (outcome) {
      parts.push('What happened when that code last ran:\n' + outcome);
    }
    parts.push(
      'Apply the feedback and return the COMPLETE revised code as exactly one ' +
        'execute_code action — keep every part the feedback did not object to. ' +
        'Sandbox builtins: pandas (pd), numpy (np), DataFrame (df), ' +
        'matplotlib.pyplot (plt). No imports, no open(), no eval()/exec().',
    );
    return parts.join('\n\n');
  }

  /**
   * Compact account of the pinned code's last execution.
   *
   * This is what turns feedback into an actual improvement loop: without it
   * the model revises code it has never seen the output of.
   */
  private describeLastRun(): string {
    const run = this.cell?.lastRun;
    if (!run || run.status === 'idle' || !run.runKind) return '';
    if (run.runKind === 'assistant' && !run.error && !run.stdout) return '';
    const max = PipelineCodelineComponent.MAX_RUN_EXCERPT_CHARS;
    const lines: string[] = [`- Run mode: ${run.runKind} · status: ${run.status}`];
    if (run.error) {
      lines.push('- Error:\n```\n' + this.truncate(run.error, max) + '\n```');
    }
    if (run.stdout) {
      lines.push('- Stdout:\n```\n' + this.truncate(run.stdout, max) + '\n```');
    }
    if (run.images?.length) {
      lines.push(`- Charts rendered: ${run.images.length}`);
    }
    if (run.changes) {
      const added = (run.changes.columns_added || []).join(', ');
      const removed = (run.changes.columns_removed || []).join(', ');
      lines.push(
        `- Dataset: rows ${run.changes.rows_before} → ${run.changes.rows_after}` +
          (added ? `, added [${added}]` : '') +
          (removed ? `, removed [${removed}]` : ''),
      );
    }
    if (run.status === 'success' && !run.stdout && !run.images?.length && !run.changes) {
      lines.push('- The run produced no printed output, no chart, and no dataset change.');
    }
    return lines.join('\n');
  }

  private appendTurn(turn: Omit<PipelineCodelineTurn, 'at'>): void {
    if (!this.cell) return;
    const turns = [...(this.cell.turns || []), { ...turn, at: new Date().toISOString() }];
    this.cell.turns = turns.slice(-PipelineCodelineComponent.MAX_THREAD_TURNS);
  }

  /**
   * Backfill a thread for cells answered before threads existed (checkpoints
   * written by an earlier build), so their first refinement still has the
   * original ask and answer to build on.
   */
  private ensureThreadSeeded(): void {
    if (!this.cell || this.turns.length) return;
    const run = this.cell.lastRun;
    if (!run?.assistantText && !run?.generatedCode) return;
    const intent = (this.cell.intent || '').trim();
    if (intent) {
      this.appendTurn({ role: 'user', kind: 'intent', content: intent });
    }
    this.appendTurn({
      role: 'assistant',
      kind: 'intent',
      content: run?.assistantText || 'Suggested code for this Codeline.',
      code: run?.generatedCode || (this.cell.code || '').trim() || undefined,
    });
  }

  /**
   * Mirror the refinement into Prometa as feedback on the turn it corrects.
   *
   * Best-effort: a failure here must never block the refinement itself, and
   * the ids are only present when the Prometa SDK is active server-side.
   */
  private recordRefineFeedback(feedback: string): void {
    const target = [...this.turns].reverse().find((t) => t.role === 'assistant');
    if (!target?.chatSpanId && !target?.chatTraceId && !target?.chatSessionId) return;
    const payload: any = { comment: feedback, source: 'declarai-codeline-refine' };
    if (target.chatTraceId) payload.target_trace_id = target.chatTraceId;
    if (target.chatSpanId) payload.target_span_id = target.chatSpanId;
    if (target.chatSessionId) {
      payload.target_session_id = target.chatSessionId;
      payload.conversation_id = target.chatSessionId;
    }
    if (this.fileId != null) payload.file_id = this.fileId;
    this.dataService.submitAiFeedback(payload).subscribe({
      next: () => {},
      error: () => {},
    });
  }

  private truncate(text: string, max: number): string {
    const value = text || '';
    return value.length <= max ? value : `${value.slice(0, max)}\n… (truncated)`;
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
    this.ensureThreadSeeded();
    const history = this.buildHistory();
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

    this.appendTurn({
      role: 'user',
      kind: 'auto_fix',
      content: `Run failed (${mode}) — auto-fix attempt ${attempt}/${max}: ${firstErrorLine}`,
    });

    this.patchLastRun({
      status: 'running',
      runKind: 'assistant',
      error: errorText,
      assistantText:
        `Code run failed: ${firstErrorLine} — auto-fix attempt ${attempt}/${max}...`,
    });
    this.persist(true);

    this.postAssistantChat(
      correctionPrompt,
      'auto_fix',
      history,
      {
        codeline_code: failedCode,
        auto_correction_attempt: attempt,
        execute_mode: mode,
      },
      {
        next: (resp: any) => {
          const parsed = this.parseAssistantReply(resp);
          const correctedCode = parsed.code;
          const assistantText = parsed.text;

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
          this.appendTurn({
            role: 'assistant',
            kind: 'auto_fix',
            content: assistantText || 'Applied corrected code.',
            code: correctedCode,
            chatSpanId: parsed.chatSpanId,
            chatTraceId: parsed.chatTraceId,
            chatSessionId: parsed.chatSessionId,
          });
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
      },
    );
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
      turns: [],
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
