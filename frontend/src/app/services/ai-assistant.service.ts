import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';

export interface AiAction {
  type: string;
  payload: any;
  applied?: boolean;
  editing?: boolean;
  editedPayload?: any;
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
}

@Injectable({
  providedIn: 'root'
})
export class AiAssistantService {
  private messagesSubject = new BehaviorSubject<ChatMessage[]>([]);
  messages$: Observable<ChatMessage[]> = this.messagesSubject.asObservable();

  private panelOpenSubject = new BehaviorSubject<boolean>(false);
  panelOpen$: Observable<boolean> = this.panelOpenSubject.asObservable();

  private pendingContextSubject = new BehaviorSubject<{ context: any; section: string; prompt: string } | null>(null);
  pendingContext$: Observable<{ context: any; section: string; prompt: string } | null> = this.pendingContextSubject.asObservable();

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

  updateLastMessage(content: string, actions?: AiAction[]): void {
    const messages = [...this.messagesSubject.getValue()];
    if (messages.length > 0) {
      messages[messages.length - 1] = {
        ...messages[messages.length - 1],
        content,
        loading: false,
        ...(actions && actions.length > 0 ? { actions } : {}),
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
  requestSupport(context: any, section: string, prompt: string): void {
    this.pendingContextSubject.next({ context, section, prompt });
    this.openPanel();
  }

  consumePendingContext(): { context: any; section: string; prompt: string } | null {
    const pending = this.pendingContextSubject.getValue();
    this.pendingContextSubject.next(null);
    return pending;
  }
}
