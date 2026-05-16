import { Component, OnInit, OnDestroy, ViewChild, ElementRef, AfterViewChecked } from '@angular/core';
import { Subscription } from 'rxjs';
import { AiAssistantService, AiAction, ChatMessage } from '../services/ai-assistant.service';
import { DataService } from '../services/data.service';
import { SharedService } from '../services/shared.service';

@Component({
  selector: 'app-ai-chat-panel',
  templateUrl: './ai-chat-panel.component.html',
  styleUrls: ['./ai-chat-panel.component.css']
})
export class AiChatPanelComponent implements OnInit, OnDestroy, AfterViewChecked {
  @ViewChild('chatContainer') chatContainer!: ElementRef;

  messages: ChatMessage[] = [];
  userInput: string = '';
  isLoading: boolean = false;
  private currentContext: any = null;
  private currentSection: string = '';
  private subscriptions = new Subscription();
  private shouldScrollToBottom = false;

  // Model selector
  availableModels: Array<{key: string; display_name: string; provider: string; ram_gb?: number; tool_calling_mode?: string}> = [];
  selectedModel: string = 'gpt-5.5';
  showModelSelector: boolean = false;

  constructor(
    public aiService: AiAssistantService,
    private dataService: DataService,
    private sharedService: SharedService
  ) {}

  ngOnInit(): void {
    // Fetch available models
    this.dataService.getAiModels().subscribe({
      next: (resp: any) => {
        this.availableModels = resp.models || [];
        this.selectedModel = resp.default || 'gpt-5.5';
      },
      error: () => {
        // Fallback — just show OpenAI
        this.availableModels = [{key: 'gpt-5.5', display_name: 'GPT-5.5 (OpenAI)', provider: 'openai'}];
      }
    });

    this.subscriptions.add(
      this.aiService.messages$.subscribe(msgs => {
        this.messages = msgs;
        this.shouldScrollToBottom = true;
      })
    );

    this.subscriptions.add(
      this.aiService.pendingContext$.subscribe(pending => {
        if (pending) {
          const ctx = this.aiService.consumePendingContext();
          if (ctx) {
            this.currentContext = ctx.context;
            this.currentSection = ctx.section;
            this.sendMessage(ctx.prompt);
          }
        }
      })
    );
  }

  ngAfterViewChecked(): void {
    if (this.shouldScrollToBottom) {
      this.scrollToBottom();
      this.shouldScrollToBottom = false;
    }
  }

  ngOnDestroy(): void {
    this.subscriptions.unsubscribe();
  }

  sendMessage(message?: string): void {
    const text = (message || this.userInput || '').trim();
    if (!text || this.isLoading) return;

    this.userInput = '';

    this.aiService.addMessage({
      role: 'user',
      content: text,
      timestamp: new Date(),
      section: this.currentSection,
    });

    this.isLoading = true;
    this.aiService.addMessage({
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      loading: true,
    });

    const history = this.aiService.getHistory().slice(0, -1);

    // Always start from the cumulative context (all pipeline data accumulated so far),
    // then overlay any section-specific context from "Get AI Support" buttons.
    const cumulative = this.sharedService.getAiCumulativeContext() || {};
    const sectionCtx = this.currentContext || {};
    // Merge: cumulative is the base, section-specific overrides on top
    const ctx = { ...cumulative, ...sectionCtx };
    // Ensure pipeline_config is merged (not overwritten)
    ctx.pipeline_config = {
      ...(cumulative.pipeline_config || {}),
      ...(sectionCtx.pipeline_config || {}),
    };
    // Fallback: inject target definition and pipeline type if still missing
    if (!ctx.pipeline_config.target_definition) {
      ctx.pipeline_config.target_definition = this.sharedService.getTargetDefinition() || '';
    }
    if (!ctx.pipeline_config.pipeline_type) {
      ctx.pipeline_config.pipeline_type = this.sharedService.getSelectedPipeline() || '';
    }

    const fileId = this.sharedService.getCurrentFileId();
    this.dataService.sendAiChat(
      text,
      ctx,
      this.currentSection || 'general',
      history,
      fileId ?? undefined,
      this.selectedModel
    ).subscribe({
      next: (resp: any) => {
        const actions: AiAction[] = (resp.actions || []).map((a: any) => ({
          type: a.type,
          payload: a.payload,
          applied: false,
        }));
        const fallbackMsg = actions.length > 0
          ? 'I\'ve prepared the following operation for you. Review the details below and click **Apply** to execute.'
          : 'No response received.';
        this.aiService.updateLastMessage(resp.message || fallbackMsg, actions);
        this.isLoading = false;
      },
      error: (err: any) => {
        const errorMsg = err?.error?.error || err?.message || 'Failed to get AI response. Please check your API key.';
        this.aiService.updateLastMessage(`Error: ${errorMsg}`);
        this.isLoading = false;
      }
    });
  }

  /** Toggle edit mode for an action block */
  toggleEdit(action: AiAction): void {
    if (action.applied) return;
    if (!action.editing) {
      // Enter edit mode — seed editedPayload from current payload
      action.editing = true;
      action.editedPayload = JSON.parse(JSON.stringify(action.payload));
      this.actionError = null;
    } else {
      // Cancel edit mode — discard changes
      action.editing = false;
      action.editedPayload = undefined;
    }
  }

  /** Get the editable text representation of an action payload for the textarea */
  getEditableText(action: AiAction): string {
    const p = action.editedPayload ?? action.payload;
    if (action.type === 'execute_code') {
      return p.code || '';
    }
    // For structured types, serialize the whole payload as JSON
    return JSON.stringify(p, null, 2);
  }

  /** Update the edited payload when the user types in the textarea */
  onEditChange(action: AiAction, value: string): void {
    if (action.type === 'execute_code') {
      if (!action.editedPayload) action.editedPayload = { ...action.payload };
      action.editedPayload.code = value;
    } else {
      try {
        action.editedPayload = JSON.parse(value);
        this.actionError = null;
      } catch {
        this.actionError = 'Invalid JSON — please fix the syntax before applying.';
      }
    }
  }

  /** Execute any AI action via the general-purpose backend endpoint */
  applyAction(messageIndex: number, actionIndex: number, action: AiAction): void {
    if (action.applied || this.actionApplying) return;

    const fileId = this.sharedService.getCurrentFileId();
    if (!fileId) {
      this.actionError = 'No dataset loaded. Please upload data first.';
      return;
    }

    // Use editedPayload if user modified the action, otherwise use original
    const payload = action.editedPayload ?? action.payload;

    this.actionApplying = true;
    this.actionError = null;
    this.actionSuccess = null;

    this.dataService.executeAiAction(fileId, action.type, payload).subscribe({
      next: (resp: any) => {
        this.actionApplying = false;
        action.editing = false;
        this.aiService.markActionApplied(messageIndex, actionIndex);
        this._handleActionResult(action.type, resp);
      },
      error: (err: any) => {
        this.actionApplying = false;
        const errMsg = err?.error?.error || err?.error?.message || 'Action failed.';
        const traceback = err?.error?.traceback || '';
        const fullError = traceback ? errMsg + '\n' + traceback : errMsg;
        this.actionError = fullError;

        // Auto-send the error back to the AI for self-correction
        this._requestErrorCorrection(action.type, payload, fullError);
      }
    });
  }

  /** Build a human-readable confirmation message and trigger appropriate refreshes */
  private _handleActionResult(actionType: string, resp: any): void {
    const desc = resp.description || '';

    if (actionType === 'execute_code') {
      const changes = resp.changes || {};
      const added = changes.columns_added || [];
      const removed = changes.columns_removed || [];
      const preview = resp.preview || {};
      let msg = `✅ **Code executed successfully.**`;
      if (desc) msg += ` ${desc}`;
      if (added.length) msg += `\n\n**Columns added:** ${added.join(', ')}`;
      if (removed.length) msg += `\n\n**Columns removed:** ${removed.join(', ')}`;
      if (changes.rows_before !== changes.rows_after) {
        msg += `\n\n**Rows:** ${changes.rows_before} → ${changes.rows_after}`;
      }
      msg += `\n\nDataset now has **${preview.total_columns}** columns and **${preview.total_rows}** rows.`;
      this.actionSuccess = 'Code executed successfully.';
      this.aiService.addMessage({ role: 'assistant', content: msg, timestamp: new Date() });
      // Refresh declaration data
      this.sharedService.triggerDataRefresh();
      this.sharedService.triggerCheckpoint('ai_action_execute_code');

    } else if (actionType === 'update_metadata') {
      const applied = resp.applied || [];
      const errors = resp.errors || [];
      let msg = `✅ **Metadata updated.** ${applied.length} field(s) changed.`;
      if (desc) msg += ` ${desc}`;
      if (applied.length) {
        msg += '\n\n' + applied.map((a: any) => `- **${a.column}**.${a.field} = \`${a.value}\``).join('\n');
      }
      if (errors.length) {
        msg += '\n\n⚠️ ' + errors.map((e: any) => `${e.column}: ${e.error}`).join(', ');
      }
      this.actionSuccess = `${applied.length} metadata field(s) updated.`;
      this.aiService.addMessage({ role: 'assistant', content: msg, timestamp: new Date() });
      // v2.23.0+: keep the chat assertion ("changed Var_2 to ordinal")
      // and the pipeline UI dropdowns ("Var_2 still shows Nominal") in
      // sync.  We deliberately do NOT call triggerDataRefresh() here:
      // the data_dictionary GET endpoint recomputes the dictionary from
      // the raw file every call and only persists descriptions, so a
      // refetch would wipe the LoM change the AI just made.  Instead
      // we patch the in-memory dictionary cache + broadcast the change
      // so every subscriber (declaration table, encoding plan dropdown,
      // feature card) updates in place, and re-push the patched
      // dictionary to the AI Redis cache so subsequent tool calls see
      // the same state the user sees.
      if (applied.length) {
        this._applyMetadataPatchesToDictionaryCache(applied);
        this.sharedService.emitMetadataUpdates(applied);
      }
      this.sharedService.triggerCheckpoint('ai_action_update_metadata');

    } else if (actionType === 'set_ordinal_ranking') {
      const applied = resp.applied || [];
      const errors = resp.errors || [];
      let msg = `✅ **Ordinal ranking set.** ${applied.length} feature(s) ranked.`;
      if (desc) msg += ` ${desc}`;
      if (applied.length) {
        msg += '\n\n' + applied.map((a: any) => {
          const rank = Array.isArray(a.ranking) ? a.ranking.join(' → ') : '';
          return `- **${a.column}**: \`${rank}\``;
        }).join('\n');
      }
      if (errors.length) {
        msg += '\n\n⚠️ ' + errors.map((e: any) => `${e.column || ''}: ${e.error}`).join(', ');
      }
      this.actionSuccess = `${applied.length} ordinal ranking(s) applied.`;
      this.aiService.addMessage({ role: 'assistant', content: msg, timestamp: new Date() });
      // v2.24.0+: this is the procedural-chain follow-through for an
      // earlier `update_metadata` LoM = ordinal change.  Broadcast the
      // applied rankings so the modeling component patches each
      // matching encoding plan entry's `entry.ranking` array in place
      // — equivalent to the user clicking "Set Ranking" and arranging
      // the values manually.  We do NOT re-push anything to AI Redis
      // here: the backend action_executor already wrote the ranking
      // through to the cached encoding_plan artifact so the
      // assistant's NEXT get_encoding_plan call sees its own work.
      if (applied.length) {
        this.sharedService.emitEncodingRankingUpdates(applied);
      }
      this.sharedService.triggerCheckpoint('ai_action_set_ordinal_ranking');

    } else if (actionType === 'update_config') {
      const applied = resp.applied || [];
      const errors = resp.errors || [];
      let msg = `✅ **Configuration updated.** ${applied.length} setting(s) changed.`;
      if (desc) msg += ` ${desc}`;
      if (applied.length) {
        msg += '\n\n' + applied.map((a: any) => {
          if (a.column) return `- **${a.key}**: ${a.column} = \`${a.value}\``;
          return `- **${a.key}** = \`${JSON.stringify(a.value)}\``;
        }).join('\n');
      }
      if (errors.length) {
        msg += '\n\n⚠️ ' + errors.map((e: any) => `${e.column || e.key}: ${e.error}`).join(', ');
      }
      this.actionSuccess = `${applied.length} config setting(s) updated.`;
      this.aiService.addMessage({ role: 'assistant', content: msg, timestamp: new Date() });
      // Apply config changes to frontend state
      this._applyConfigChanges(applied);
      this.sharedService.triggerCheckpoint('ai_action_update_config');

    } else if (actionType === 'start_sfs') {
      // v2.25.0+: dedicated path for the AI to actually kick off SFS.
      // The backend action handler returns the validated config object;
      // we broadcast it on sfsStartRequests$ so the modeling component
      // populates its SFS form fields and calls startSfs() — the exact
      // code path a manual "Start SFS" button click would take.
      const applied = resp.applied || null;
      let msg = `✅ **SFS started.**`;
      if (desc) msg += ` ${desc}`;
      if (applied && typeof applied === 'object') {
        const methods = Array.isArray(applied.methods) ? applied.methods.join(', ') : '?';
        const sc = applied.stopping_criteria || {};
        const metrics = Array.isArray(sc.metrics)
          ? sc.metrics.map((m: any) => `${m.metric}≤${m.pct_change}%`).join(', ')
          : '?';
        const excl = Array.isArray(applied.excluded_features) ? applied.excluded_features : [];
        msg += '\n\n' + [
          `- **Methods**: \`${methods}\``,
          `- **Stopping criteria**: ${metrics}, min=${sc.min_features ?? '?'}, max=${sc.max_features ?? '?'}`,
          `- **Excluded features**: ${excl.length ? excl.map((c: string) => `\`${c}\``).join(', ') : '_none_'}`,
          `- **Parallelism**: n_jobs=${applied.n_jobs ?? '?'}, top_k=${applied.top_k ?? '?'}`,
        ].join('\n');
      }
      this.actionSuccess = 'SFS started.';
      this.aiService.addMessage({ role: 'assistant', content: msg, timestamp: new Date() });
      if (applied && typeof applied === 'object') {
        this.sharedService.emitSfsStartRequest(applied);
      }
      this.sharedService.triggerCheckpoint('ai_action_start_sfs');

    } else if (actionType === 'update_notes') {
      const noteAction = resp.note_action || 'add';
      const position = resp.position || '';
      const content = resp.content || '';
      let msg = `✅ **Note ${noteAction === 'delete' ? 'deleted' : noteAction === 'edit' ? 'edited' : 'added'}** at position \`${position}\`.`;
      if (content) msg += `\n\n> ${content}`;
      this.actionSuccess = `Note ${noteAction}d successfully.`;
      this.aiService.addMessage({ role: 'assistant', content: msg, timestamp: new Date() });
      // Apply note change to SharedService
      if (noteAction === 'delete') {
        this.sharedService.updatePipelineNote(position, '');
      } else {
        this.sharedService.updatePipelineNote(position, content);
      }
      this.sharedService.triggerCheckpoint('ai_action_update_notes');

    } else {
      this.actionSuccess = resp.description || 'Action completed.';
      this.aiService.addMessage({
        role: 'assistant',
        content: `✅ **Action completed.** ${desc}`,
        timestamp: new Date(),
      });
    }
  }

  /** Apply config changes returned by update_config to frontend SharedService state */
  private _applyConfigChanges(applied: any[]): void {
    // v2.25.0+: feature_usage entries are collected and broadcast in a
    // single emission on featureUsageUpdates$ so the modeling component
    // can patch its featureUsage map and the Selected Features
    // dropdown re-renders.  model_usage continues to use the existing
    // BehaviorSubject pattern because it has a different downstream
    // consumer (Data Quality / preprocessing).
    const featureUsageBatch: Array<{ column: string; value: 'keep' | 'drop'; reason?: string }> = [];
    for (const upd of applied) {
      if (upd.key === 'model_usage' && upd.column) {
        const current = this.sharedService.getModelUsageSettings() || {};
        current[upd.column] = upd.value;
        this.sharedService.setModelUsageSettings(current);
      } else if (upd.key === 'feature_usage' && upd.column) {
        if (upd.value === 'keep' || upd.value === 'drop') {
          const entry: { column: string; value: 'keep' | 'drop'; reason?: string } = {
            column: String(upd.column),
            value: upd.value,
          };
          if (upd.reason) entry.reason = String(upd.reason);
          featureUsageBatch.push(entry);
        }
      }
      // Other config keys (preprocessing_options, split_strategy, etc.) are handled
      // by triggering a checkpoint which the parent components pick up
    }
    if (featureUsageBatch.length) {
      this.sharedService.emitFeatureUsageUpdates(featureUsageBatch);
    }
  }

  /**
   * v2.23.0+: Patch the SharedService data dictionary cache in place when
   * the AI assistant runs `update_metadata`, then push the patched cache
   * back to the AI Redis cache so subsequent tool calls see the same
   * state the user sees in the pipeline UI.
   *
   * Returns nothing — side effects only.  Errors on the AI cache push
   * are logged but never raised: the in-memory patch is the source of
   * truth for the UI, and the Redis re-push is a best-effort
   * synchronization for the AI's next turn.
   */
  private _applyMetadataPatchesToDictionaryCache(applied: any[]): void {
    if (!Array.isArray(applied) || applied.length === 0) return;
    const cache = this.sharedService.getDataDictionaryCache();
    if (!Array.isArray(cache) || cache.length === 0) {
      // No cache to patch yet (declaration step hasn't loaded the
      // dictionary) — the metadataUpdates$ broadcast will still reach
      // any component that lazily fetches the dictionary later.
      return;
    }
    // Build a name -> entry index for O(1) lookups.
    const idxByName = new Map<string, number>();
    cache.forEach((d: any, i: number) => {
      const n = d?.Feature_Name;
      if (typeof n === 'string') idxByName.set(n, i);
    });
    let mutated = false;
    const patched = cache.map((d: any) => ({ ...d }));
    for (const upd of applied) {
      const col = upd?.column;
      const field = upd?.field;
      const value = upd?.value;
      if (!col || !field) continue;
      const i = idxByName.get(col);
      if (i === undefined) continue;
      patched[i][field] = value;
      mutated = true;
    }
    if (!mutated) return;
    this.sharedService.setDataDictionaryCache(patched);
    // Re-push to AI Redis cache (best effort) so the assistant's next
    // tool call sees the same dictionary the user sees on screen.
    const fileId = this.sharedService.getCurrentFileId();
    if (fileId !== null && fileId !== undefined) {
      this.dataService.pushAiCache(fileId as number, { data_dictionary: patched }).subscribe({
        error: (err: any) => console.warn('[AI Cache] post-update_metadata dictionary push failed:', err),
      });
    }
  }

  actionApplying = false;
  actionError: string | null = null;
  actionSuccess: string | null = null;

  /** Track which auto-correction messages are expanded (by message index) */
  expandedCorrections = new Set<number>();

  toggleCorrectionExpand(index: number): void {
    if (this.expandedCorrections.has(index)) {
      this.expandedCorrections.delete(index);
    } else {
      this.expandedCorrections.add(index);
    }
  }

  isCorrectionExpanded(index: number): boolean {
    return this.expandedCorrections.has(index);
  }

  /** Automatically send the failed action + error back to the AI for self-correction */
  private _requestErrorCorrection(actionType: string, payload: any, errorText: string): void {
    // Build a concise description of what failed
    let codeSnippet = '';
    if (actionType === 'execute_code') {
      codeSnippet = payload?.code || JSON.stringify(payload, null, 2);
    } else {
      codeSnippet = JSON.stringify(payload, null, 2);
    }

    const correctionPrompt =
      `The following "${actionType}" action you proposed failed with an error.\n\n` +
      `**Failed code / payload:**\n\`\`\`\n${codeSnippet}\n\`\`\`\n\n` +
      `**Error:**\n\`\`\`\n${errorText}\n\`\`\`\n\n` +
      `Please analyze the error and provide a corrected action block. ` +
      `Remember: only pandas (pd), numpy (np), and the DataFrame (df) are available in the sandbox. ` +
      `No imports, no open(), no __import__. Fix the issue and respond with the corrected action.`;

    // Extract the first line of the error for the collapsed summary
    const firstErrorLine = errorText.split('\n')[0].trim();
    const summary = `Action failed: ${firstErrorLine} — requesting AI correction...`;

    // Add the error as a user-role message, marked as auto-correction (collapsed by default)
    this.aiService.addMessage({
      role: 'user',
      content: correctionPrompt,
      timestamp: new Date(),
      autoCorrection: true,
      autoCorrectionSummary: summary,
    });

    // Add a loading placeholder for the AI response
    this.aiService.addMessage({
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      loading: true,
    });

    this.isLoading = true;

    const history = this.aiService.getHistory().slice(0, -1);
    const cumulative = this.sharedService.getAiCumulativeContext() || {};
    const sectionCtx = this.currentContext || {};
    const ctx = { ...cumulative, ...sectionCtx };
    ctx.pipeline_config = {
      ...(cumulative.pipeline_config || {}),
      ...(sectionCtx.pipeline_config || {}),
    };
    if (!ctx.pipeline_config.target_definition) {
      ctx.pipeline_config.target_definition = this.sharedService.getTargetDefinition() || '';
    }
    if (!ctx.pipeline_config.pipeline_type) {
      ctx.pipeline_config.pipeline_type = this.sharedService.getSelectedPipeline() || '';
    }

    this.dataService.sendAiChat(
      correctionPrompt,
      ctx,
      this.currentSection || 'general',
      history,
      this.sharedService.getCurrentFileId() ?? undefined,
      this.selectedModel
    ).subscribe({
      next: (resp: any) => {
        const actions: AiAction[] = (resp.actions || []).map((a: any) => ({
          type: a.type,
          payload: a.payload,
          applied: false,
        }));
        const correctionFallback = actions.length > 0
          ? 'I\'ve prepared a corrected operation. Review the details below and click **Apply** to execute.'
          : 'No response received.';
        this.aiService.updateLastMessage(resp.message || correctionFallback, actions);
        this.isLoading = false;
        // Clear the error since the AI has provided a correction
        this.actionError = null;
      },
      error: (err: any) => {
        const errorMsg = err?.error?.error || err?.message || 'Failed to get AI correction.';
        this.aiService.updateLastMessage(`Error getting correction: ${errorMsg}`);
        this.isLoading = false;
      }
    });
  }

  onKeyDown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.sendMessage();
    }
  }

  toggleModelSelector(): void {
    this.showModelSelector = !this.showModelSelector;
  }

  selectModel(modelKey: string): void {
    this.selectedModel = modelKey;
    this.showModelSelector = false;
  }

  getSelectedModelName(): string {
    const model = this.availableModels.find(m => m.key === this.selectedModel);
    return model ? model.display_name : this.selectedModel;
  }

  clearChat(): void {
    this.aiService.clearMessages();
    this.currentContext = null;
    this.currentSection = '';
  }

  formatMessage(content: string): string {
    if (!content) return '';

    // Split into lines for block-level processing
    const lines = content.split('\n');
    const blocks: string[] = [];
    let i = 0;

    while (i < lines.length) {
      // Detect markdown table: line contains | and next line is separator (|---|)
      if (this._isTableRow(lines[i]) && i + 1 < lines.length && this._isTableSeparator(lines[i + 1])) {
        const tableLines: string[] = [lines[i]];
        i++; // skip header
        i++; // skip separator
        while (i < lines.length && this._isTableRow(lines[i])) {
          tableLines.push(lines[i]);
          i++;
        }
        blocks.push(this._renderTable(tableLines));
        continue;
      }

      // Standalone table rows (no separator line — still render as table)
      if (this._isTableRow(lines[i])) {
        const tableLines: string[] = [];
        while (i < lines.length && this._isTableRow(lines[i])) {
          if (!this._isTableSeparator(lines[i])) {
            tableLines.push(lines[i]);
          }
          i++;
        }
        if (tableLines.length > 0) {
          blocks.push(this._renderTable(tableLines));
        }
        continue;
      }

      // Regular line — apply inline formatting
      blocks.push(this._formatInline(lines[i]));
      i++;
    }

    return blocks.join('<br>');
  }

  private _isTableRow(line: string): boolean {
    if (!line) return false;
    const trimmed = line.trim();
    return trimmed.startsWith('|') && trimmed.endsWith('|') && trimmed.length > 2;
  }

  private _isTableSeparator(line: string): boolean {
    if (!line) return false;
    return /^\|[\s\-:|]+\|$/.test(line.trim());
  }

  private _renderTable(rows: string[]): string {
    if (rows.length === 0) return '';
    const parseRow = (line: string): string[] =>
      line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(c => c.trim());

    let html = '<table class="chat-table"><thead><tr>';
    const headerCells = parseRow(rows[0]);
    headerCells.forEach(c => { html += `<th>${this._formatInline(c)}</th>`; });
    html += '</tr></thead><tbody>';
    for (let r = 1; r < rows.length; r++) {
      const cells = parseRow(rows[r]);
      html += '<tr>';
      cells.forEach(c => { html += `<td>${this._formatInline(c)}</td>`; });
      html += '</tr>';
    }
    html += '</tbody></table>';
    return html;
  }

  private _formatInline(text: string): string {
    if (!text) return '';
    let s = text
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    // Headers
    s = s.replace(/^#### (.+)/, '<strong style="font-size:13px;">$1</strong>');
    s = s.replace(/^### (.+)/, '<strong style="font-size:14px;">$1</strong>');
    s = s.replace(/^## (.+)/, '<strong style="font-size:15px;">$1</strong>');
    s = s.replace(/^# (.+)/, '<strong style="font-size:16px;">$1</strong>');
    // Bold & italic
    s = s.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
    s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/\*(.+?)\*/g, '<em>$1</em>');
    // Inline code
    s = s.replace(/`(.+?)`/g, '<code>$1</code>');
    // Bullet/numbered list items
    s = s.replace(/^- (.+)/, '• $1');
    s = s.replace(/^\d+\.\s/, (m) => m);
    return s;
  }

  getSectionLabel(section: string): string {
    const labels: Record<string, string> = {
      data_quality: 'Data Quality Summary',
      encoding: 'Categorical Feature Encoding',
      cv: 'Cross-Validation',
      shap: 'SHAP Beeswarm',
      selected_features: 'Selected Features',
      sfs: 'SFS Results',
      general: 'General',
    };
    return labels[section] || section;
  }

  private scrollToBottom(): void {
    try {
      if (this.chatContainer) {
        this.chatContainer.nativeElement.scrollTop = this.chatContainer.nativeElement.scrollHeight;
      }
    } catch (e) {}
  }
}
