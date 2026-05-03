import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { FormsModule } from '@angular/forms';
import { CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { AiChatPanelComponent } from './ai-chat-panel.component';
import { AiAssistantService } from '../services/ai-assistant.service';
import { DataService } from '../services/data.service';
import { SharedService } from '../services/shared.service';

describe('AiChatPanelComponent', () => {
  let component: AiChatPanelComponent;
  let fixture: ComponentFixture<AiChatPanelComponent>;
  let aiService: AiAssistantService;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HttpClientTestingModule, FormsModule],
      declarations: [AiChatPanelComponent],
      providers: [AiAssistantService, DataService, SharedService],
      schemas: [CUSTOM_ELEMENTS_SCHEMA],
    }).compileComponents();

    fixture = TestBed.createComponent(AiChatPanelComponent);
    component = fixture.componentInstance;
    aiService = TestBed.inject(AiAssistantService);
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should start with empty messages', () => {
    expect(component.messages).toEqual([]);
  });

  it('should start with empty userInput', () => {
    expect(component.userInput).toBe('');
  });

  it('should start with isLoading false', () => {
    expect(component.isLoading).toBeFalse();
  });

  it('should sync messages from AiAssistantService on init', () => {
    aiService.addMessage({ role: 'user', content: 'Test', timestamp: new Date() });
    fixture.detectChanges();
    expect(component.messages.length).toBe(1);
    expect(component.messages[0].content).toBe('Test');
  });

  it('should reflect panel open state from service', () => {
    expect(aiService.isPanelOpen()).toBeFalse();
    aiService.openPanel();
    expect(aiService.isPanelOpen()).toBeTrue();
  });
});
