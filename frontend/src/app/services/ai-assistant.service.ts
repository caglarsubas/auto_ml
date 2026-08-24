import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';

export interface AiAction {
  type: string;
  payload: any;
  applied?: boolean;
  editing?: boolean;
  editedPayload?: any;
}

export type AiIntentLabel = 'A' | 'B' | 'C' | 'D' | 'E' | 'R';

export interface AiFeedbackState {
  liked?: boolean;
  rating?: number;
  comment?: string;
  commentOpen?: boolean;
  submitting?: boolean;
  submitted?: boolean;
  error?: string;
  feedbackId?: string;
}

export interface PendingAiContext {
  context: any;
  section: string;
  prompt: string;
  intentLabels?: AiIntentLabel[];
  intentSource?: string;
}

export const AI_SUPPORT_INTENTS_BY_SECTION: { [section: string]: AiIntentLabel[] } = {
  data_quality: ['C'],
  data_purifier: ['C'],
  encoding: ['C'],
  cv: ['C'],
  shap: ['C'],
  selected_features: ['C'],
  sfs_forward: ['C'],
  sfs_backward: ['C'],
  sfs_forward_from_backward: ['C'],
  hyperparameter_results: ['C'],
};

/**
 * One phase of an in-flight assistant turn, as narrated by the backend's
 * NDJSON progress channel (``ai_assistant/progress.py``).
 *
 * A turn is a single HTTP request that internally runs intent classification,
 * context assembly, knowledge-bank retrieval, one or more LLM rounds, tool
 * calls, and a synthesis pass.  The panel used to show one typing indicator
 * for the whole thing; these rows show what it is actually doing.
 *
 * ``id`` is the identity we de-duplicate on — a ``running`` event creates the
 * row and a later ``done``/``error`` with the same id updates it in place.
 */
export interface AssistantStep {
  id: string;
  label: string;
  state: 'running' | 'done' | 'error';
  detail?: string;
  /** ms since the turn started, stamped server-side when the event was emitted. */
  elapsedMs: number;
  /** ms this step itself took — set when the closing event arrives. */
  durationMs?: number;
}

/** Knowledge-bank snippet metadata returned with RAG-backed assistant turns. */
export interface RagSource {
  source: string;
  title: string;
  heading: string;
  chunk_id: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  section?: string;
  loading?: boolean;
  actions?: AiAction[];
  autoCorrection?: boolean;
  autoCorrectionSummary?: string;
  /**
   * v2.38.0+: Prometa span id of the @workflow('declarai-chat') turn
   * that produced this message.  Populated only when the backend
   * response includes `chat_span_id` (i.e. when the turn produced ≥1
   * action AND the Prometa SDK is active).  Forwarded to
   * `dataService.executeAiAction()` on Apply so the action-dispatch
   * trace can call `set_input_ref(chatSpanId)` and Prometa renders
   * the two traces as a single navigable flow in the Causal-context
   * block.  Optional everywhere — a missing id means "no cross-trace
   * link" and the apply call simply omits the `parent_span_id` field.
   */
  chatSpanId?: string;
  chatTraceId?: string;
  chatSessionId?: string;
  /** v3.4.0+: knowledge-bank sources when intent included retrieval (R). */
  ragSources?: RagSource[];
  feedback?: AiFeedbackState;
  /**
   * Live progress rows for this turn.  Populated while `loading` is true and
   * kept afterwards so the finished message can show a collapsed
   * "N steps · 12.4s" trail the user can expand.  Absent on messages from
   * before this feature and on turns that used the non-streaming transport.
   */
  steps?: AssistantStep[];
  /** True once the turn finished, so the template can collapse the trail. */
  stepsComplete?: boolean;
}

@Injectable({
  providedIn: 'root'
})
export class AiAssistantService {
  private messagesSubject = new BehaviorSubject<ChatMessage[]>([]);
  messages$: Observable<ChatMessage[]> = this.messagesSubject.asObservable();

  private panelOpenSubject = new BehaviorSubject<boolean>(false);
  panelOpen$: Observable<boolean> = this.panelOpenSubject.asObservable();

  private pendingContextSubject = new BehaviorSubject<PendingAiContext | null>(null);
  pendingContext$: Observable<PendingAiContext | null> = this.pendingContextSubject.asObservable();

  togglePanel(): void {
    this.panelOpenSubject.next(!this.panelOpenSubject.getValue());
  }

  openPanel(): void {
    this.panelOpenSubject.next(true);
  }

  closePanel(): void {
    this.panelOpenSubject.next(false);
  }

  isPanelOpen(): boolean {
    return this.panelOpenSubject.getValue();
  }

  getMessages(): ChatMessage[] {
    return this.messagesSubject.getValue();
  }

  addMessage(msg: ChatMessage): void {
    const messages = [...this.messagesSubject.getValue(), msg];
    this.messagesSubject.next(messages);
  }

  updateLastMessage(content: string, actions?: AiAction[], chatSpanId?: string,
                    chatTraceId?: string, chatSessionId?: string,
                    ragSources?: RagSource[]): void {
    const messages = [...this.messagesSubject.getValue()];
    if (messages.length > 0) {
      messages[messages.length - 1] = {
        ...messages[messages.length - 1],
        content,
        loading: false,
        ...(actions && actions.length > 0 ? { actions } : {}),
        // v2.38.0+: persist the chat span id so applyAction() can
        // forward it as parent_span_id on the action-execute call.
        // Only stamped when defined — legacy callers that pass 2 args
        // are unaffected and an absent id keeps the message clean
        // rather than writing `chatSpanId: undefined`.
        ...(chatSpanId ? { chatSpanId } : {}),
        ...(chatTraceId ? { chatTraceId } : {}),
        ...(chatSessionId ? { chatSessionId } : {}),
        ...(ragSources && ragSources.length > 0 ? { ragSources } : {}),
      };
      this.messagesSubject.next(messages);
    }
  }

  /**
   * Fold one progress event into the last message's step trail.
   *
   * Events arrive as a stream of `running` / `done` / `error` rows keyed by
   * `id`.  A `running` row for an unseen id is appended; any later event for
   * the same id updates that row in place (and stamps how long it took) so
   * the list stays one-row-per-phase instead of growing two rows per phase.
   */
  applyProgressStep(step: AssistantStep): void {
    const messages = [...this.messagesSubject.getValue()];
    const last = messages.length - 1;
    if (last < 0 || messages[last].role !== 'assistant') return;

    const steps = [...(messages[last].steps || [])];
    const existing = steps.findIndex(s => s.id === step.id);
    if (existing >= 0) {
      steps[existing] = {
        ...steps[existing],
        ...step,
        durationMs: Math.max(0, step.elapsedMs - steps[existing].elapsedMs),
        // Keep the original start time so the duration stays meaningful.
        elapsedMs: steps[existing].elapsedMs,
      };
    } else {
      steps.push(step);
    }

    messages[last] = { ...messages[last], steps };
    this.messagesSubject.next(messages);
  }

  /**
   * Close out the step trail when a turn ends.  Any row still `running`
   * (e.g. the turn errored mid-phase) is marked done so nothing spins
   * forever, and the trail is flagged complete so the template collapses it.
   */
  finalizeProgressSteps(): void {
    const messages = [...this.messagesSubject.getValue()];
    const last = messages.length - 1;
    if (last < 0 || messages[last].role !== 'assistant') return;
    if (!messages[last].steps?.length) return;

    messages[last] = {
      ...messages[last],
      steps: messages[last].steps!.map(s =>
        s.state === 'running' ? { ...s, state: 'done' as const } : s),
      stepsComplete: true,
    };
    this.messagesSubject.next(messages);
  }

  updateMessageFeedback(messageIndex: number, patch: Partial<AiFeedbackState>): void {
    const messages = [...this.messagesSubject.getValue()];
    const msg = messages[messageIndex];
    if (!msg || msg.role !== 'assistant') return;
    messages[messageIndex] = {
      ...msg,
      feedback: {
        ...(msg.feedback || {}),
        ...patch,
      },
    };
    this.messagesSubject.next(messages);
  }

  /** Mark an action on a specific message as applied */
  markActionApplied(messageIndex: number, actionIndex: number): void {
    const messages = [...this.messagesSubject.getValue()];
    if (messages[messageIndex]?.actions?.[actionIndex]) {
      messages[messageIndex] = { ...messages[messageIndex] };
      messages[messageIndex].actions = [...messages[messageIndex].actions!];
      messages[messageIndex].actions![actionIndex] = { ...messages[messageIndex].actions![actionIndex], applied: true };
      this.messagesSubject.next(messages);
    }
  }

  clearMessages(): void {
    this.messagesSubject.next([]);
  }

  getHistory(): Array<{ role: string; content: string }> {
    return this.messagesSubject.getValue()
      .filter(m => m.role === 'user' || m.role === 'assistant')
      .filter(m => !m.loading)
      .map(m => ({ role: m.role, content: m.content }));
  }

  /** Called by "Get AI Support" buttons to inject context and open panel */
  requestSupport(context: any, section: string, prompt: string,
                 intentLabels?: AiIntentLabel[],
                 intentSource: string = 'get_ai_support_button'): void {
    const labels = (intentLabels && intentLabels.length > 0)
      ? intentLabels
      : (AI_SUPPORT_INTENTS_BY_SECTION[section] || []);
    this.pendingContextSubject.next({
      context,
      section,
      prompt,
      ...(labels.length > 0 ? { intentLabels: labels, intentSource } : {}),
    });
    this.openPanel();
  }

  consumePendingContext(): PendingAiContext | null {
    const pending = this.pendingContextSubject.getValue();
    this.pendingContextSubject.next(null);
    return pending;
  }
}
