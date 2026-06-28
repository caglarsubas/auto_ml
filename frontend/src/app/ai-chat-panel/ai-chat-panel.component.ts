import { Component, OnInit, OnDestroy, ViewChild, ElementRef, AfterViewChecked, HostListener } from '@angular/core';
import { Subscription } from 'rxjs';
import { AiAssistantService, AiAction, AiFeedbackState, AiIntentLabel, ChatMessage } from '../services/ai-assistant.service';
import { DataService } from '../services/data.service';
import { SharedService } from '../services/shared.service';

@Component({
  selector: 'app-ai-chat-panel',
  templateUrl: './ai-chat-panel.component.html',
  styleUrls: ['./ai-chat-panel.component.css']
})
export class AiChatPanelComponent implements OnInit, OnDestroy, AfterViewChecked {
  @ViewChild('chatContainer') chatContainer!: ElementRef;
  @ViewChild('modelSelectorWrapper') modelSelectorWrapper?: ElementRef<HTMLElement>;
  private static readonly MAX_AUTO_CORRECTION_ATTEMPTS = 3;

  messages: ChatMessage[] = [];
  userInput: string = '';
  isLoading: boolean = false;
  private currentContext: any = null;
  private currentSection: string = '';
  private subscriptions = new Subscription();
  private shouldScrollToBottom = false;
  feedbackStars = [1, 2, 3, 4, 5];
  private feedbackSequence = 0;

  // Model selector
  availableModels: Array<{key: string; display_name: string; provider: string; ram_gb?: number; tool_calling_mode?: string}> = [];
  selectedModel: string = 'gpt-5.5';
  showModelSelector: boolean = false;

  // ── v2.27.2 — defensive empty-response copy ─────────────────────────
  // The backend now always returns a meaningful `message` even when the
  // LLM produces no content (see `_chat_workflow` synthesis pass +
  // _EMPTY_RESPONSE_FALLBACK / _TOOL_BUDGET_EXHAUSTED_FALLBACK in
  // backend/ai_assistant/views.py).  Pre-v2.27.2 the frontend showed
  // the literal "No response received." which left the user with no
  // actionable next step.  Keeping this constant as defense-in-depth:
  // if a future regression or network anomaly does return an empty
  // `message`, the user still sees actionable copy.  Public so the
  // Karma spec can pin the exact wording without reaching into a
  // component-private field.
  static readonly EMPTY_RESPONSE_FALLBACK =
    'The assistant did not return an answer this time. ' +
    'Please try rephrasing your question or check the backend logs.';

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
            this.sendMessage(ctx.prompt, ctx.intentLabels, ctx.intentSource);
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

  sendMessage(message?: string, intentLabels?: AiIntentLabel[], intentSource?: string): void {
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
      this.selectedModel,
      intentLabels,
      intentSource
    ).subscribe({
      next: (resp: any) => {
        const actions: AiAction[] = (resp.actions || []).map((a: any) => ({
          type: a.type,
          payload: a.payload,
          applied: false,
        }));
        const fallbackMsg = actions.length > 0
          ? 'I\'ve prepared the following operation for you. Review the details below and click **Apply** to execute.'
          : AiChatPanelComponent.EMPTY_RESPONSE_FALLBACK;
        // v2.38.0: capture chat_span_id (only present when actions exist
        // AND Prometa SDK is active server-side).  Stored on the message
        // so applyAction can forward it as parent_span_id when the user
        // clicks Apply, enabling cross-trace linking in Prometa.
        this.aiService.updateLastMessage(
          resp.message || fallbackMsg,
          actions,
          resp.chat_span_id,
          resp.chat_trace_id,
          resp.chat_session_id,
        );
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

  isSpecializedAction(actionType: string): boolean {
    return [
      'execute_code',
      'update_metadata',
      'update_config',
      'update_notes',
    ].includes(actionType);
  }

  getActionTitle(actionType: string): string {
    const titles: Record<string, string> = {
      start_data_purifier: 'Start Data Purifier',
      update_purifier_selection: 'Update Purifier Selection',
      start_sfs: 'Start Sequential Feature Selection',
      set_ordinal_ranking: 'Set Ordinal Ranking',
      apply_encoding: 'Apply Encoding',
    };
    if (titles[actionType]) return titles[actionType];
    return actionType
      .split('_')
      .filter(Boolean)
      .map(part => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ');
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

    // v2.38.0: pull the chat_span_id stamped on the source message when
    // the proposing turn was traced.  Falls back to undefined for
    // legacy v2.25.0..v2.37.0 messages or untraced turns — in which
    // case dataService skips the parent_span_id POST field and the
    // backend treats it as no-link (legacy semantics preserved).
    const sourceMessage = this.aiService.getMessages()[messageIndex];
    const parentSpanId = sourceMessage?.chatSpanId;

    this.actionApplying = true;
    this.actionError = null;
    this.actionSuccess = null;

    this.dataService.executeAiAction(fileId, action.type, payload, parentSpanId).subscribe({
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

        // Auto-send the error back to the AI for self-correction. The user's
        // first Apply is treated as consent for bounded execute_code repairs.
        this._requestErrorCorrection(
          action.type,
          payload,
          fullError,
          1,
          parentSpanId,
          messageIndex,
          actionIndex,
        );
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
      // v2.39.0: backend now returns parallel implied_metadata_updates[]
      // (one entry per applied column, shaped like update_metadata's
      // applied array) so we can fan the LoM=ordinal flip onto the
      // existing metadataUpdates$ stream alongside the ranking
      // broadcast.  Pre-v2.39.0 backends omit the field; default to []
      // so this branch is byte-identical to v2.38.0 against an old
      // backend.
      const impliedMetadata = resp.implied_metadata_updates || [];
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
      // v2.39.0: surface the implied LoM=ordinal flips in the chat
      // bubble so the user sees the full effect of the action.  Pre-
      // v2.39.0 the user only saw the ranking confirmation while the
      // Categorical Feature Encoding table silently kept showing the
      // pre-action LoM (typically Nominal), which read as "the action
      // did nothing" — see the gemma-4-26b screenshot in the v2.39.0
      // commit body.
      if (impliedMetadata.length) {
        const cols = impliedMetadata.map((m: any) => `**${m.column}**`).join(', ');
        msg += `\n\nAlso set Level of Measurement → Ordinal for ${cols}.`;
      }
      this.actionSuccess = `${applied.length} ordinal ranking(s) applied.`;
      this.aiService.addMessage({ role: 'assistant', content: msg, timestamp: new Date() });
      // v2.24.0+: broadcast the applied rankings so the modeling
      // component patches each matching encoding plan entry's
      // `entry.ranking` array in place — equivalent to the user
      // clicking "Set Ranking" and arranging the values manually.  We
      // do NOT re-push anything to AI Redis here: the backend
      // action_executor already wrote the ranking through to the
      // cached encoding_plan artifact so the assistant's NEXT
      // get_encoding_plan call sees its own work.
      if (applied.length) {
        this.sharedService.emitEncodingRankingUpdates(applied);
      }
      // v2.39.0: also patch the in-memory data dictionary cache and
      // broadcast LoM=ordinal so the encoding plan dropdown's LoM
      // column flips visibly in lock-step with the ranking
      // populating.  Closes the gemma-4-26b multi-action gap by
      // treating LoM=ordinal as an automatic invariant of
      // set_ordinal_ranking instead of a separate update_metadata
      // block the smaller model reliably forgot to emit.  We reuse
      // _applyMetadataPatchesToDictionaryCache (also called from the
      // update_metadata branch) so the cache-coherence + AI Redis
      // re-push paths are identical to a manually-emitted LoM flip.
      if (impliedMetadata.length) {
        this._applyMetadataPatchesToDictionaryCache(impliedMetadata);
        this.sharedService.emitMetadataUpdates(impliedMetadata);
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

    } else if (actionType === 'start_data_purifier') {
      // v2.26.0+: dedicated path for the AI to fire the
      // "Run Preprocessing" button.  Validated config from the
      // backend handler is forwarded to the model-development
      // component via dataPurifierStartRequests$, which mirrors
      // the user clicking "Run Preprocessing" with these settings.
      const applied = resp.applied || null;
      let msg = `✅ **Data purifier started.**`;
      if (desc) msg += ` ${desc}`;
      if (applied && typeof applied === 'object') {
        const opts = Array.isArray(applied.purifier_options) ? applied.purifier_options : [];
        const split = applied.split || null;
        const splitDesc = split
          ? (split.strategy === 'oot'
              ? `OOT on \`${split.date_column}\`${split.cutoff ? ` cutoff=${split.cutoff}` : ` (${split.percent ?? '?'}%)`}`
              : `random ${split.percent ?? '?'}%`)
          : '_form defaults_';
        msg += '\n\n' + [
          `- **Purifier options**: ${opts.length ? opts.map((o: number) => `\`${o}\``).join(', ') : '_form defaults_'}`,
          `- **Split**: ${splitDesc}`,
        ].join('\n');
      }
      this.actionSuccess = 'Data purifier started.';
      this.aiService.addMessage({ role: 'assistant', content: msg, timestamp: new Date() });
      if (applied && typeof applied === 'object') {
        this.sharedService.emitDataPurifierStartRequest({
          purifier_options: Array.isArray(applied.purifier_options) ? applied.purifier_options : [],
          split: applied.split ?? null,
        });
      }
      this.sharedService.triggerCheckpoint('ai_action_start_data_purifier');

    } else if (actionType === 'update_purifier_selection') {
      // v2.28.0+: the "preview" sibling of start_data_purifier.
      // Edits the Data-Purifier checkbox UI WITHOUT firing the run.
      // The user reviews the new selection in the form and clicks
      // Run Preprocessing themselves (or asks the AI to run it in
      // the next turn).
      //
      // Two payload forms supported (matches the backend handler):
      //   • WHOLESALE: { form: 'wholesale', purifier_options: [..] }
      //   • DIFF:      { form: 'diff', add: [..], remove: [..] }
      //
      // No-op form: { form: 'noop' } — the backend returns this
      // when the AI emitted a description-only payload or a diff
      // that cancels itself out.  We render a chat message but skip
      // the broadcast so the form doesn't flash.
      const applied = resp.applied || {};
      const form = applied.form || 'noop';
      const opts: number[] = Array.isArray(applied.purifier_options) ? applied.purifier_options : [];
      const adds: number[] = Array.isArray(applied.add) ? applied.add : [];
      const rems: number[] = Array.isArray(applied.remove) ? applied.remove : [];

      let msg = `✏️ **Purifier selection updated.**`;
      if (desc) msg += ` ${desc}`;
      if (form === 'wholesale') {
        msg += '\n\n- **New selection**: ' + (opts.length
          ? opts.map((o: number) => `\`${o}\``).join(', ')
          : '_(cleared)_');
      } else if (form === 'diff') {
        if (adds.length) msg += '\n- **Added**: ' + adds.map((o: number) => `\`${o}\``).join(', ');
        if (rems.length) msg += '\n- **Removed**: ' + rems.map((o: number) => `\`${o}\``).join(', ');
      } else {
        msg += '\n\n_(no change applied — empty payload or self-cancelling diff)_';
      }
      msg += '\n\n👉 _Review the Data-Purifier checkboxes, then click_ **Run Preprocessing** _when ready (or ask me to run it)._';

      this.actionSuccess = 'Purifier selection updated.';
      this.aiService.addMessage({ role: 'assistant', content: msg, timestamp: new Date() });

      // Broadcast to the model-development subscriber.  The noop
      // form is intentionally NOT broadcast — there is nothing for
      // the form to patch.
      if (form === 'wholesale' || form === 'diff') {
        this.sharedService.emitPurifierSelectionUpdate({
          form,
          purifier_options: form === 'wholesale' ? opts : null,
          add: adds,
          remove: rems,
          description: desc || undefined,
        });
      }
      this.sharedService.triggerCheckpoint('ai_action_update_purifier_selection');

    } else if (actionType === 'apply_encoding') {
      // v2.26.0+: dedicated path for the AI to fire the
      // "Apply Encoding" button.  The component's current
      // encodingPlan array (already populated/edited by earlier
      // update_metadata + set_ordinal_ranking actions) is what
      // gets applied — this action just toggles the use_native flag.
      const applied = resp.applied || null;
      const useNative = applied && typeof applied.use_native === 'boolean'
        ? applied.use_native
        : true;
      let msg = `✅ **Apply encoding started.**`;
      if (desc) msg += ` ${desc}`;
      msg += `\n\n- **use_native**: \`${useNative}\``;
      this.actionSuccess = 'Apply encoding started.';
      this.aiService.addMessage({ role: 'assistant', content: msg, timestamp: new Date() });
      this.sharedService.emitEncodingApplyRequest({ use_native: useNative });
      this.sharedService.triggerCheckpoint('ai_action_apply_encoding');

    } else if (actionType === 'start_modeling') {
      // v2.26.0+: the headline action — closes the user's exact
      // blocker from v2.25.0 ("I cannot 'start' the modeling engine
      // directly").  Validated config goes via modelingStartRequests$
      // to the modeling component, which optionally patches
      // selectedAlgorithm + encodingUseNative, then calls the
      // existing startModeling() method.
      const applied = resp.applied || null;
      const algorithm = applied && typeof applied.algorithm === 'string' && applied.algorithm.trim()
        ? applied.algorithm.trim()
        : null;
      const useNative = applied && typeof applied.encoding_use_native === 'boolean'
        ? applied.encoding_use_native
        : true;
      let msg = `✅ **Modeling started.**`;
      if (desc) msg += ` ${desc}`;
      msg += '\n\n' + [
        `- **Algorithm**: ${algorithm ? `\`${algorithm}\`` : '_form value_'}`,
        `- **encoding_use_native**: \`${useNative}\``,
      ].join('\n');
      this.actionSuccess = 'Modeling started.';
      this.aiService.addMessage({ role: 'assistant', content: msg, timestamp: new Date() });
      this.sharedService.emitModelingStartRequest({
        algorithm,
        encoding_use_native: useNative,
      });
      this.sharedService.triggerCheckpoint('ai_action_start_modeling');

    } else if (actionType === 'start_hyperparameter') {
      // Phase 3: dedicated path for the AI to fire the "Start
      // Hyperparameter Tuning" button (the pipeline step after SFS).
      // The validated config goes via hyperparamStartRequests$ to the
      // modeling component, which mirrors it onto the tuning form fields
      // and calls startHyperparam() — the same code path the manual
      // click takes (active-process registration + status polling).
      const applied = resp.applied || null;
      let msg = `✅ **Hyperparameter tuning started.**`;
      if (desc) msg += ` ${desc}`;
      if (applied && typeof applied === 'object') {
        const enabled = Array.isArray(applied.enabled_params) && applied.enabled_params.length
          ? applied.enabled_params.map((p: string) => `\`${p}\``).join(', ')
          : '_form defaults_';
        const method = applied.search_method || 'auto';
        msg += '\n\n' + [
          `- **Search method**: \`${method}\`${method === 'auto' ? ' _(picks grid/random/bayesian by fit count)_' : ''}`,
          `- **Trials (n_iter)**: ${applied.n_iter ?? '?'}`,
          `- **CV folds**: ${applied.cv_folds ?? '?'}`,
          `- **Compute power (n_jobs)**: ${applied.n_jobs ?? '?'}`,
          `- **Curve metric**: \`${applied.primary_metric ?? 'roc_auc'}\``,
          `- **Curve points**: ${applied.validation_curve_points ?? '?'}`,
          `- **Tuned params**: ${enabled}`,
        ].join('\n');
      }
      this.actionSuccess = 'Hyperparameter tuning started.';
      this.aiService.addMessage({ role: 'assistant', content: msg, timestamp: new Date() });
      if (applied && typeof applied === 'object') {
        this.sharedService.emitHyperparamStartRequest(applied);
      }
      this.sharedService.triggerCheckpoint('ai_action_start_hyperparameter');

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
      } else if (upd.key === 'preprocessing_options') {
        if (Array.isArray(upd.value)) {
          const purifierOptions = upd.value
            .map((id: any) => Number(id))
            .filter((id: number) => Number.isInteger(id));
          this.sharedService.emitPurifierSelectionUpdate({
            form: 'wholesale',
            purifier_options: purifierOptions,
            add: [],
            remove: [],
          });
        }
      }
      // Other config keys (split_strategy, etc.) are handled by triggering a
      // checkpoint which the parent components pick up.
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
  private _requestErrorCorrection(
    actionType: string,
    payload: any,
    errorText: string,
    attempt: number = 1,
    parentSpanId?: string,
    acceptedMessageIndex?: number,
    acceptedActionIndex?: number,
  ): void {
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
      `No imports, no open(), no __import__. Fix the issue and respond with the corrected action.` +
      (actionType === 'execute_code'
        ? `\n\nThis is automated correction attempt ${attempt} of ${AiChatPanelComponent.MAX_AUTO_CORRECTION_ATTEMPTS}. ` +
          `The user already approved applying this implementation, so return exactly one corrected execute_code action block. ` +
          `Do not ask the user to press Apply again.`
        : '');

    // Extract the first line of the error for the collapsed summary
    const firstErrorLine = errorText.split('\n')[0].trim();
    const summary = actionType === 'execute_code'
      ? `Code run failed: ${firstErrorLine} — auto-fix attempt ${attempt}/${AiChatPanelComponent.MAX_AUTO_CORRECTION_ATTEMPTS}...`
      : `Action failed: ${firstErrorLine} — requesting AI correction...`;

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
        const shouldAutoApply = this._shouldAutoApplyCorrection(actionType, actions, attempt);
        if (shouldAutoApply) {
          const message = resp.message || 'I prepared a corrected operation.';
          this.aiService.updateLastMessage(
            `${message}\n\nApplying the corrected operation now...`,
            [],
            resp.chat_span_id,
            resp.chat_trace_id,
            resp.chat_session_id,
          );
          this.isLoading = false;
          this.actionError = null;
          this._executeAutoCorrectedAction(
            actions[0].type,
            actions[0].payload,
            attempt,
            resp.chat_span_id || parentSpanId,
            acceptedMessageIndex,
            acceptedActionIndex,
          );
          return;
        }
        const correctionFallback = actions.length > 0
          ? 'I\'ve prepared a corrected operation. Review the details below and click **Apply** to execute.'
          : AiChatPanelComponent.EMPTY_RESPONSE_FALLBACK;
        // v2.38.0: same chat_span_id capture as the main send flow.
        // Self-correction turns produce a NEW chat span, so the corrected
        // action card (now appended to this new assistant message) gets
        // linked to that new span — not the original failing turn.
        this.aiService.updateLastMessage(
          resp.message || correctionFallback,
          actions,
          resp.chat_span_id,
          resp.chat_trace_id,
          resp.chat_session_id,
        );
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

  private _shouldAutoApplyCorrection(actionType: string, actions: AiAction[], attempt: number): boolean {
    return actionType === 'execute_code'
      && attempt <= AiChatPanelComponent.MAX_AUTO_CORRECTION_ATTEMPTS
      && actions.length === 1
      && actions[0].type === 'execute_code'
      && !!actions[0].payload;
  }

  private _executeAutoCorrectedAction(
    actionType: string,
    payload: any,
    attempt: number,
    parentSpanId?: string,
    acceptedMessageIndex?: number,
    acceptedActionIndex?: number,
  ): void {
    const fileId = this.sharedService.getCurrentFileId();
    if (!fileId) {
      this.actionError = 'No dataset loaded. Please upload data first.';
      return;
    }

    this.actionApplying = true;
    this.actionError = null;
    this.actionSuccess = null;

    this.dataService.executeAiAction(fileId, actionType, payload, parentSpanId).subscribe({
      next: (resp: any) => {
        this.actionApplying = false;
        this.actionError = null;
        if (acceptedMessageIndex !== undefined && acceptedActionIndex !== undefined) {
          this.aiService.markActionApplied(acceptedMessageIndex, acceptedActionIndex);
        }
        this._handleActionResult(actionType, resp);
      },
      error: (err: any) => {
        this.actionApplying = false;
        const errMsg = err?.error?.error || err?.error?.message || 'Action failed.';
        const traceback = err?.error?.traceback || '';
        const fullError = traceback ? errMsg + '\n' + traceback : errMsg;
        this.actionError = fullError;

        if (attempt >= AiChatPanelComponent.MAX_AUTO_CORRECTION_ATTEMPTS) {
          const max = AiChatPanelComponent.MAX_AUTO_CORRECTION_ATTEMPTS;
          this.aiService.addMessage({
            role: 'assistant',
            content: `I tried ${max} automatic correction attempts, but the code still failed. The last error was:\n\n\`\`\`\n${fullError}\n\`\`\``,
            timestamp: new Date(),
          });
          return;
        }

        this._requestErrorCorrection(
          actionType,
          payload,
          fullError,
          attempt + 1,
          parentSpanId,
          acceptedMessageIndex,
          acceptedActionIndex,
        );
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
    // v2.41.1 — strip LaTeX BEFORE markdown so `$\rightarrow$` becomes
    // `→` instead of being passed through as raw text the user sees.
    // The system prompts also instruct the LLM to use Unicode directly,
    // but this pass is defense-in-depth: a rogue model output can never
    // put raw LaTeX on screen.
    s = this._delatexify(s);
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

  /**
   * v2.41.1 — Convert the most common LaTeX commands to Unicode.
   *
   * Our chat renderer is a hand-rolled markdown subset (see
   * `_formatInline` and `_renderTable` above) — it has no MathJax /
   * KaTeX layer.  Without this pass, content like `$\rightarrow$` or
   * `\alpha` shows up as raw LaTeX in the chat bubble, which is what
   * the user reported in the v2.41.1 bug.
   *
   * We accept BOTH `\command` and `$\command$` forms by allowing an
   * optional `$` on each side of every pattern.  A strict `$...$`
   * stripper for unrecognised content is deliberately omitted: a naive
   * regex would corrupt money strings like "$50 and $60" and the win
   * for unknown LaTeX is small (the user still sees broken-but-
   * recognisable source).
   *
   * Symbol catalog covers what's plausible in a credit-risk / ML
   * conversation: arrows, comparison & arithmetic ops, set & logic
   * operators, calculus, full Greek alphabet (lowercase + the
   * uppercase letters that differ from Latin).
   */
  private _delatexify(s: string): string {
    if (!s || s.indexOf('\\') === -1) return s;
    // Pattern shape: `<optional $><LaTeX command><non-letter lookahead><optional $>`.
    // The negative lookahead `(?![a-zA-Z])` is critical: without it, `\\in`
    // would prefix-match inside `\\int` and `\\infty`, producing garbage
    // like `∈t$` and `∈fty$`.  Same hazard applies to `\\le` (prefix of
    // `\\leq`/`\\leftarrow`/`\\leftrightarrow`), `\\ge` (`\\geq`), `\\ne`
    // (`\\neq`).  We use the lookahead uniformly so rule order doesn't
    // have to encode that knowledge — but we ALSO order longer commands
    // first as defense-in-depth (`\\int` before `\\in`, etc.).
    //
    // A single rule per command handles BOTH `\command` and `$\command$`
    // forms because the leading `\$?` and trailing `\$?` each match zero
    // or one `$` independently.
    const map: Array<[RegExp, string]> = [
      // Arrows
      [/\$?\\rightarrow(?![a-zA-Z])\$?/g, '→'],
      [/\$?\\to(?![a-zA-Z])\$?/g, '→'],
      [/\$?\\Rightarrow(?![a-zA-Z])\$?/g, '⇒'],
      [/\$?\\Leftrightarrow(?![a-zA-Z])\$?/g, '⇔'],
      [/\$?\\leftrightarrow(?![a-zA-Z])\$?/g, '↔'],
      [/\$?\\Leftarrow(?![a-zA-Z])\$?/g, '⇐'],
      [/\$?\\leftarrow(?![a-zA-Z])\$?/g, '←'],
      [/\$?\\uparrow(?![a-zA-Z])\$?/g, '↑'],
      [/\$?\\downarrow(?![a-zA-Z])\$?/g, '↓'],
      [/\$?\\mapsto(?![a-zA-Z])\$?/g, '↦'],
      // Comparison + arithmetic — longer commands first (`\leq` before `\le`).
      [/\$?\\leq(?![a-zA-Z])\$?/g, '≤'],
      [/\$?\\le(?![a-zA-Z])\$?/g, '≤'],
      [/\$?\\geq(?![a-zA-Z])\$?/g, '≥'],
      [/\$?\\ge(?![a-zA-Z])\$?/g, '≥'],
      [/\$?\\neq(?![a-zA-Z])\$?/g, '≠'],
      [/\$?\\ne(?![a-zA-Z])\$?/g, '≠'],
      [/\$?\\approx(?![a-zA-Z])\$?/g, '≈'],
      [/\$?\\equiv(?![a-zA-Z])\$?/g, '≡'],
      [/\$?\\sim(?![a-zA-Z])\$?/g, '∼'],
      [/\$?\\propto(?![a-zA-Z])\$?/g, '∝'],
      [/\$?\\pm(?![a-zA-Z])\$?/g, '±'],
      [/\$?\\mp(?![a-zA-Z])\$?/g, '∓'],
      [/\$?\\times(?![a-zA-Z])\$?/g, '×'],
      [/\$?\\div(?![a-zA-Z])\$?/g, '÷'],
      [/\$?\\cdot(?![a-zA-Z])\$?/g, '·'],
      [/\$?\\ast(?![a-zA-Z])\$?/g, '∗'],
      // Set / logic — `\notin` before `\in`, longer subset before shorter.
      [/\$?\\notin(?![a-zA-Z])\$?/g, '∉'],
      [/\$?\\in(?![a-zA-Z])\$?/g, '∈'],
      [/\$?\\subseteq(?![a-zA-Z])\$?/g, '⊆'],
      [/\$?\\subset(?![a-zA-Z])\$?/g, '⊂'],
      [/\$?\\supseteq(?![a-zA-Z])\$?/g, '⊇'],
      [/\$?\\supset(?![a-zA-Z])\$?/g, '⊃'],
      [/\$?\\cup(?![a-zA-Z])\$?/g, '∪'],
      [/\$?\\cap(?![a-zA-Z])\$?/g, '∩'],
      [/\$?\\forall(?![a-zA-Z])\$?/g, '∀'],
      [/\$?\\exists(?![a-zA-Z])\$?/g, '∃'],
      [/\$?\\emptyset(?![a-zA-Z])\$?/g, '∅'],
      // Calculus / operators — `\infty` and `\int` come before `\in`
      // (defense-in-depth ordering even though the lookahead would catch it).
      [/\$?\\infty(?![a-zA-Z])\$?/g, '∞'],
      [/\$?\\int(?![a-zA-Z])\$?/g, '∫'],
      [/\$?\\sum(?![a-zA-Z])\$?/g, '∑'],
      [/\$?\\prod(?![a-zA-Z])\$?/g, '∏'],
      [/\$?\\partial(?![a-zA-Z])\$?/g, '∂'],
      [/\$?\\nabla(?![a-zA-Z])\$?/g, '∇'],
      [/\$?\\sqrt(?![a-zA-Z])\$?/g, '√'],
      // Greek lowercase
      [/\$?\\alpha(?![a-zA-Z])\$?/g, 'α'],
      [/\$?\\beta(?![a-zA-Z])\$?/g, 'β'],
      [/\$?\\gamma(?![a-zA-Z])\$?/g, 'γ'],
      [/\$?\\delta(?![a-zA-Z])\$?/g, 'δ'],
      [/\$?\\varepsilon(?![a-zA-Z])\$?/g, 'ε'],
      [/\$?\\epsilon(?![a-zA-Z])\$?/g, 'ε'],
      [/\$?\\zeta(?![a-zA-Z])\$?/g, 'ζ'],
      [/\$?\\eta(?![a-zA-Z])\$?/g, 'η'],
      [/\$?\\theta(?![a-zA-Z])\$?/g, 'θ'],
      [/\$?\\iota(?![a-zA-Z])\$?/g, 'ι'],
      [/\$?\\kappa(?![a-zA-Z])\$?/g, 'κ'],
      [/\$?\\lambda(?![a-zA-Z])\$?/g, 'λ'],
      [/\$?\\mu(?![a-zA-Z])\$?/g, 'μ'],
      [/\$?\\nu(?![a-zA-Z])\$?/g, 'ν'],
      [/\$?\\xi(?![a-zA-Z])\$?/g, 'ξ'],
      [/\$?\\pi(?![a-zA-Z])\$?/g, 'π'],
      [/\$?\\rho(?![a-zA-Z])\$?/g, 'ρ'],
      [/\$?\\sigma(?![a-zA-Z])\$?/g, 'σ'],
      [/\$?\\tau(?![a-zA-Z])\$?/g, 'τ'],
      [/\$?\\upsilon(?![a-zA-Z])\$?/g, 'υ'],
      [/\$?\\varphi(?![a-zA-Z])\$?/g, 'φ'],
      [/\$?\\phi(?![a-zA-Z])\$?/g, 'φ'],
      [/\$?\\chi(?![a-zA-Z])\$?/g, 'χ'],
      [/\$?\\psi(?![a-zA-Z])\$?/g, 'ψ'],
      [/\$?\\omega(?![a-zA-Z])\$?/g, 'ω'],
      // Greek uppercase (only the ones that differ visually from Latin).
      [/\$?\\Gamma(?![a-zA-Z])\$?/g, 'Γ'],
      [/\$?\\Delta(?![a-zA-Z])\$?/g, 'Δ'],
      [/\$?\\Theta(?![a-zA-Z])\$?/g, 'Θ'],
      [/\$?\\Lambda(?![a-zA-Z])\$?/g, 'Λ'],
      [/\$?\\Xi(?![a-zA-Z])\$?/g, 'Ξ'],
      [/\$?\\Pi(?![a-zA-Z])\$?/g, 'Π'],
      [/\$?\\Sigma(?![a-zA-Z])\$?/g, 'Σ'],
      [/\$?\\Phi(?![a-zA-Z])\$?/g, 'Φ'],
      [/\$?\\Psi(?![a-zA-Z])\$?/g, 'Ψ'],
      [/\$?\\Omega(?![a-zA-Z])\$?/g, 'Ω'],
      // Spacing commands the LLM may emit but which mean nothing here.
      [/\\,/g, ' '],
      [/\\;/g, ' '],
      [/\\:/g, ' '],
      [/\\!/g, ''],
      [/\\qquad(?![a-zA-Z])/g, '    '],
      [/\\quad(?![a-zA-Z])/g, '  '],
    ];
    for (const [re, repl] of map) {
      s = s.replace(re, repl);
    }
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

  setFeedbackLiked(messageIndex: number, liked: boolean): void {
    const msg = this.aiService.getMessages()[messageIndex];
    if (!msg || msg.feedback?.submitted || msg.feedback?.submitting) return;
    this.aiService.updateMessageFeedback(messageIndex, { liked, error: undefined });
  }

  setFeedbackRating(messageIndex: number, rating: number): void {
    const msg = this.aiService.getMessages()[messageIndex];
    if (!msg || msg.feedback?.submitted || msg.feedback?.submitting) return;
    const nextRating = msg.feedback?.rating === rating ? undefined : rating;
    this.aiService.updateMessageFeedback(messageIndex, { rating: nextRating, error: undefined });
  }

  toggleFeedbackComment(messageIndex: number): void {
    const msg = this.aiService.getMessages()[messageIndex];
    if (!msg || msg.feedback?.submitted || msg.feedback?.submitting) return;
    this.aiService.updateMessageFeedback(messageIndex, {
      commentOpen: !msg.feedback?.commentOpen,
      error: undefined,
    });
  }

  onFeedbackCommentChange(messageIndex: number, value: string): void {
    const msg = this.aiService.getMessages()[messageIndex];
    if (!msg || msg.feedback?.submitted || msg.feedback?.submitting) return;
    this.aiService.updateMessageFeedback(messageIndex, { comment: value, error: undefined });
  }

  canSubmitFeedback(msg: ChatMessage): boolean {
    const feedback = msg.feedback || {};
    return !!(
      feedback.liked !== undefined ||
      feedback.rating ||
      (feedback.comment || '').trim()
    );
  }

  submitFeedback(messageIndex: number): void {
    const msg = this.aiService.getMessages()[messageIndex];
    if (!msg || msg.role !== 'assistant' || msg.feedback?.submitted || msg.feedback?.submitting) return;

    const feedback: AiFeedbackState = msg.feedback || {};
    const comment = (feedback.comment || '').trim();
    if (!this.canSubmitFeedback(msg)) {
      this.aiService.updateMessageFeedback(messageIndex, {
        error: 'Choose a thumb, star rating, or add a comment.',
      });
      return;
    }

    const feedbackId = feedback.feedbackId || this.newFeedbackId(messageIndex);
    const payload: any = {
      source: 'declarai-ai-chat-panel',
      feedback_id: feedbackId,
      submitted_at: new Date().toISOString(),
    };
    if (feedback.liked !== undefined) payload.liked = feedback.liked;
    if (feedback.rating) payload.rating = feedback.rating;
    if (comment) payload.comment = comment;
    if (msg.chatTraceId) payload.target_trace_id = msg.chatTraceId;
    if (msg.chatSpanId) payload.target_span_id = msg.chatSpanId;
    if (msg.chatSessionId) {
      payload.target_session_id = msg.chatSessionId;
      payload.conversation_id = msg.chatSessionId;
    }
    const fileId = this.sharedService.getCurrentFileId();
    if (fileId != null) payload.file_id = fileId;

    this.aiService.updateMessageFeedback(messageIndex, {
      submitting: true,
      error: undefined,
      feedbackId,
    });
    this.dataService.submitAiFeedback(payload).subscribe({
      next: (resp: any) => {
        this.aiService.updateMessageFeedback(messageIndex, {
          submitting: false,
          submitted: true,
          commentOpen: false,
          feedbackId: resp?.feedback_id || feedbackId,
          error: undefined,
        });
      },
      error: (err: any) => {
        const msgText = err?.error?.errors
          ? Object.values(err.error.errors).join(' ')
          : (err?.error?.error || err?.message || 'Feedback could not be submitted.');
        this.aiService.updateMessageFeedback(messageIndex, {
          submitting: false,
          error: msgText,
        });
      },
    });
  }

  private newFeedbackId(messageIndex: number): string {
    const cryptoObj = globalThis.crypto;
    if (cryptoObj && typeof cryptoObj.randomUUID === 'function') {
      return cryptoObj.randomUUID();
    }
    this.feedbackSequence += 1;
    return `declarai-feedback-${Date.now()}-${messageIndex}-${this.feedbackSequence}`;
  }

  private scrollToBottom(): void {
    try {
      if (this.chatContainer) {
        this.chatContainer.nativeElement.scrollTop = this.chatContainer.nativeElement.scrollHeight;
      }
    } catch (e) {}
  }
}
