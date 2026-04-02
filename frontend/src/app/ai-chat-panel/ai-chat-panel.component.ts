import { Component, OnInit, OnDestroy, ViewChild, ElementRef, AfterViewChecked } from '@angular/core';
import { Subscription } from 'rxjs';
import { AiAssistantService, ChatMessage } from '../services/ai-assistant.service';
import { DataService } from '../services/data.service';

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

  constructor(
    public aiService: AiAssistantService,
    private dataService: DataService
  ) {}

  ngOnInit(): void {
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

    this.dataService.sendAiChat(
      text,
      this.currentContext || {},
      this.currentSection || 'general',
      history
    ).subscribe({
      next: (resp: any) => {
        this.aiService.updateLastMessage(resp.message || 'No response received.');
        this.isLoading = false;
      },
      error: (err: any) => {
        const errorMsg = err?.error?.error || err?.message || 'Failed to get AI response. Please check your API key.';
        this.aiService.updateLastMessage(`Error: ${errorMsg}`);
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
