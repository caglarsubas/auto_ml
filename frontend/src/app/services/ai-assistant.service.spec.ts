import { TestBed } from '@angular/core/testing';
import { AiAssistantService, ChatMessage, AiAction } from './ai-assistant.service';

describe('AiAssistantService', () => {
  let service: AiAssistantService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(AiAssistantService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  // ── Panel state ─────────────────────────────────────────────────────
  describe('panel state', () => {
    it('should default to closed', () => {
      expect(service.isPanelOpen()).toBeFalse();
    });

    it('togglePanel should open if closed', () => {
      service.togglePanel();
      expect(service.isPanelOpen()).toBeTrue();
    });

    it('togglePanel should close if open', () => {
      service.openPanel();
      service.togglePanel();
      expect(service.isPanelOpen()).toBeFalse();
    });

    it('openPanel should set to true', () => {
      service.openPanel();
      expect(service.isPanelOpen()).toBeTrue();
    });

    it('closePanel should set to false', () => {
      service.openPanel();
      service.closePanel();
      expect(service.isPanelOpen()).toBeFalse();
    });

    it('panelOpen$ should emit state changes', (done) => {
      service.openPanel();
      service.panelOpen$.subscribe(val => {
        expect(val).toBeTrue();
        done();
      });
    });
  });

  // ── Messages ────────────────────────────────────────────────────────
  describe('messages', () => {
    const userMsg: ChatMessage = {
      role: 'user',
      content: 'Hello',
      timestamp: new Date(),
    };

    const assistantMsg: ChatMessage = {
      role: 'assistant',
      content: 'Hi there',
      timestamp: new Date(),
    };

    it('should start with empty messages', () => {
      expect(service.getMessages()).toEqual([]);
    });

    it('addMessage should append to list', () => {
      service.addMessage(userMsg);
      expect(service.getMessages().length).toBe(1);
      expect(service.getMessages()[0].content).toBe('Hello');
    });

    it('addMessage should preserve order', () => {
      service.addMessage(userMsg);
      service.addMessage(assistantMsg);
      expect(service.getMessages().length).toBe(2);
      expect(service.getMessages()[0].role).toBe('user');
      expect(service.getMessages()[1].role).toBe('assistant');
    });

    it('messages$ should emit updated list', (done) => {
      service.addMessage(userMsg);
      service.messages$.subscribe(msgs => {
        expect(msgs.length).toBe(1);
        done();
      });
    });

    it('clearMessages should empty the list', () => {
      service.addMessage(userMsg);
      service.addMessage(assistantMsg);
      service.clearMessages();
      expect(service.getMessages()).toEqual([]);
    });
  });

  // ── updateLastMessage ──────────────────────────────────────────────
  describe('updateLastMessage', () => {
    it('should update content and set loading to false', () => {
      service.addMessage({ role: 'assistant', content: '...', timestamp: new Date(), loading: true });
      service.updateLastMessage('Final answer');
      const msgs = service.getMessages();
      expect(msgs[msgs.length - 1].content).toBe('Final answer');
      expect(msgs[msgs.length - 1].loading).toBeFalse();
    });

    it('should attach actions when provided', () => {
      service.addMessage({ role: 'assistant', content: '...', timestamp: new Date(), loading: true });
      const actions: AiAction[] = [{ type: 'update_notes', payload: { content: 'test' } }];
      service.updateLastMessage('Done', actions);
      const msgs = service.getMessages();
      expect(msgs[msgs.length - 1].actions!.length).toBe(1);
      expect(msgs[msgs.length - 1].actions![0].type).toBe('update_notes');
    });

    it('should do nothing when messages is empty', () => {
      service.updateLastMessage('test');
      expect(service.getMessages()).toEqual([]);
    });

    // ── v2.38.0: chat-span-id persistence (cross-trace linking) ─────
    it('should persist chatSpanId when provided as 3rd arg (v2.38.0)', () => {
      service.addMessage({ role: 'assistant', content: '...', timestamp: new Date(), loading: true });
      const actions: AiAction[] = [{ type: 'update_notes', payload: { content: 'test' } }];
      service.updateLastMessage('Done', actions, 'chat-span-deadbeef');
      const msgs = service.getMessages();
      expect(msgs[msgs.length - 1].chatSpanId).toBe('chat-span-deadbeef');
    });

    it('should leave chatSpanId undefined when 3rd arg is omitted (legacy)', () => {
      service.addMessage({ role: 'assistant', content: '...', timestamp: new Date(), loading: true });
      service.updateLastMessage('Done');
      const msgs = service.getMessages();
      // Pre-v2.38.0 callers used 1- or 2-arg form — chatSpanId must stay
      // absent so applyAction's `sourceMessage?.chatSpanId` evaluates
      // to undefined and the link header is skipped.
      expect(msgs[msgs.length - 1].chatSpanId).toBeUndefined();
    });

    it('should leave chatSpanId undefined when 3rd arg is empty string', () => {
      service.addMessage({ role: 'assistant', content: '...', timestamp: new Date(), loading: true });
      service.updateLastMessage('Done', [], '');
      const msgs = service.getMessages();
      // Empty string from a Prometa-disabled chat response (resp.chat_span_id
      // missing) must be treated identically to omitted — never stamped.
      expect(msgs[msgs.length - 1].chatSpanId).toBeUndefined();
    });
  });

  // ── markActionApplied ──────────────────────────────────────────────
  describe('markActionApplied', () => {
    it('should mark specific action as applied', () => {
      const actions: AiAction[] = [
        { type: 'update_notes', payload: { content: 'a' } },
        { type: 'update_config', payload: { key: 'b' } },
      ];
      service.addMessage({ role: 'assistant', content: 'test', timestamp: new Date(), actions });

      service.markActionApplied(0, 1);
      const msgs = service.getMessages();
      expect(msgs[0].actions![0].applied).toBeFalsy();
      expect(msgs[0].actions![1].applied).toBeTrue();
    });

    it('should do nothing for invalid indices', () => {
      service.addMessage({ role: 'assistant', content: 'test', timestamp: new Date() });
      service.markActionApplied(0, 99);
      expect(service.getMessages().length).toBe(1);
    });
  });

  // ── getHistory ─────────────────────────────────────────────────────
  describe('getHistory', () => {
    it('should return only user and assistant messages', () => {
      service.addMessage({ role: 'user', content: 'Q1', timestamp: new Date() });
      service.addMessage({ role: 'assistant', content: 'A1', timestamp: new Date() });
      service.addMessage({ role: 'system', content: 'sys', timestamp: new Date() });

      const history = service.getHistory();
      expect(history.length).toBe(2);
      expect(history[0].role).toBe('user');
      expect(history[1].role).toBe('assistant');
    });

    it('should exclude loading messages', () => {
      service.addMessage({ role: 'assistant', content: '...', timestamp: new Date(), loading: true });
      const history = service.getHistory();
      expect(history.length).toBe(0);
    });
  });

  // ── Pending context ────────────────────────────────────────────────
  describe('pendingContext', () => {
    it('should start as null', (done) => {
      service.pendingContext$.subscribe(val => {
        expect(val).toBeNull();
        done();
      });
    });

    it('requestSupport should set context and open panel', () => {
      const ctx = { summary: [{ Variable: 'Age' }] };
      service.requestSupport(ctx, 'data_quality', 'Explain PSI');
      expect(service.isPanelOpen()).toBeTrue();
    });

    it('consumePendingContext should return and clear context', () => {
      service.requestSupport({ x: 1 }, 'cv', 'Why low AUC?');
      const pending = service.consumePendingContext();
      expect(pending).toBeTruthy();
      expect(pending!.section).toBe('cv');
      expect(pending!.prompt).toBe('Why low AUC?');

      const after = service.consumePendingContext();
      expect(after).toBeNull();
    });
  });
});
