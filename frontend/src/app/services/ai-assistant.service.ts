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
};

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

  updateLastMessage(content: string, actions?: AiAction[], chatSpanId?: string): void {
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
      };
      this.messagesSubject.next(messages);
    }
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
