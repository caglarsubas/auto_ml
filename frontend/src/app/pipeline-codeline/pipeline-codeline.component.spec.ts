import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { FormsModule } from '@angular/forms';
import { CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { of, throwError } from 'rxjs';
import { PipelineCodelineComponent } from './pipeline-codeline.component';
import { DataService } from '../services/data.service';
import { SharedService } from '../services/shared.service';

describe('PipelineCodelineComponent', () => {
  let component: PipelineCodelineComponent;
  let fixture: ComponentFixture<PipelineCodelineComponent>;
  let dataService: DataService;
  let sharedService: SharedService;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HttpClientTestingModule, FormsModule],
      declarations: [PipelineCodelineComponent],
      providers: [DataService, SharedService],
      schemas: [CUSTOM_ELEMENTS_SCHEMA],
    }).compileComponents();

    fixture = TestBed.createComponent(PipelineCodelineComponent);
    component = fixture.componentInstance;
    component.position = 'after_data_preview';
    dataService = TestBed.inject(DataService);
    sharedService = TestBed.inject(SharedService);
    spyOn(dataService, 'getAiModels').and.returnValue(of({
      models: [
        { key: 'engine-gemma4-26b', display_name: 'gemma4:26b', provider: 'engine' },
      ],
      default: 'engine-gemma4-26b',
    }));
    spyOn(sharedService, 'getCurrentFileId').and.returnValue(42);
    spyOn(sharedService, 'getAiCumulativeContext').and.returnValue({});
    spyOn(sharedService, 'updatePipelineCodeline');
    spyOn(sharedService, 'triggerCheckpoint');
    spyOn(sharedService, 'triggerDataRefresh');
    fixture.detectChanges();
  });

  function seedCell(code: string): void {
    component.addCodeline();
    component.cell!.code = code;
    component.cell!.mode = 'code';
    (component as any).fileId = 42;
  }

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should pass source=codeline on executeAiAction', () => {
    seedCell("df['x'] = 1");
    const execSpy = spyOn(dataService, 'executeAiAction').and.returnValue(of({
      status: 'success',
      stdout: '',
      preview: null,
      images: [],
      changes: null,
    }));

    component.runExploratory();

    expect(execSpy).toHaveBeenCalled();
    const args = execSpy.calls.mostRecent().args;
    expect(args[0]).toBe(42);
    expect(args[1]).toBe('execute_code');
    expect(args[2].mode).toBe('exploratory');
    expect(args[2].codeline_position).toBe('after_data_preview');
    expect(args[4]).toBe('codeline');
  });

  it('iteratively auto-fixes consecutive exploratory failures up to success', () => {
    seedCell("df['x'] = missing_one");

    const execSpy = spyOn(dataService, 'executeAiAction').and.returnValues(
      throwError(() => ({ error: { error: 'NameError: missing_one' } })),
      throwError(() => ({ error: { error: 'KeyError: Var_404' } })),
      of({
        status: 'success',
        stdout: 'ok',
        preview: { columns: ['x'], top_rows: [{ x: 1 }], total_columns: 1, total_rows: 1 },
        images: [],
        changes: null,
      }),
    );
    const chatSpy = spyOn(dataService, 'sendAiChat').and.returnValues(
      of({
        message: 'First correction.',
        actions: [{ type: 'execute_code', payload: { code: "df['x'] = df['Var_404']" } }],
      }),
      of({
        message: 'Second correction.',
        actions: [{ type: 'execute_code', payload: { code: "df['x'] = 1" } }],
      }),
    );

    component.runExploratory();

    expect(chatSpy.calls.count()).toBe(2);
    expect(execSpy.calls.count()).toBe(3);
    expect(execSpy.calls.argsFor(0)[2].mode).toBe('exploratory');
    expect(execSpy.calls.argsFor(1)[2].mode).toBe('exploratory');
    expect(execSpy.calls.argsFor(2)[2].mode).toBe('exploratory');
    expect(execSpy.calls.argsFor(1)[2].auto_correction_attempt).toBe(1);
    expect(execSpy.calls.argsFor(2)[2].auto_correction_attempt).toBe(2);
    expect(chatSpy.calls.argsFor(0)[8]).toBe('codeline');
    expect(component.cell!.code).toBe("df['x'] = 1");
    expect(component.cell!.lastRun?.status).toBe('success');
    expect(component.isBusy).toBeFalse();
  });

  it('stops automatic correction after the retry cap', () => {
    seedCell("df['x'] = still_bad");

    const execSpy = spyOn(dataService, 'executeAiAction').and.returnValues(
      throwError(() => ({ error: { error: 'NameError: still_bad' } })),
      throwError(() => ({ error: { error: 'NameError: still_bad_1' } })),
      throwError(() => ({ error: { error: 'NameError: still_bad_2' } })),
      throwError(() => ({ error: { error: 'NameError: still_bad_3' } })),
    );
    const chatSpy = spyOn(dataService, 'sendAiChat').and.returnValues(
      of({
        message: 'Correction 1.',
        actions: [{ type: 'execute_code', payload: { code: "df['x'] = still_bad_1" } }],
      }),
      of({
        message: 'Correction 2.',
        actions: [{ type: 'execute_code', payload: { code: "df['x'] = still_bad_2" } }],
      }),
      of({
        message: 'Correction 3.',
        actions: [{ type: 'execute_code', payload: { code: "df['x'] = still_bad_3" } }],
      }),
    );

    component.runExploratory();

    expect(chatSpy.calls.count()).toBe(3);
    expect(execSpy.calls.count()).toBe(4); // initial + 3 corrections
    expect(component.cell!.lastRun?.status).toBe('error');
    expect(component.cell!.lastRun?.assistantText || '').toContain('3 automatic correction');
    expect(component.isBusy).toBeFalse();
  });

  it('preserves apply mode across auto-fix retries', () => {
    seedCell("df['x'] = bad");

    const execSpy = spyOn(dataService, 'executeAiAction').and.returnValues(
      throwError(() => ({ error: { error: 'NameError: bad' } })),
      of({
        status: 'success',
        stdout: '',
        preview: { columns: ['x'], top_rows: [], total_columns: 1, total_rows: 1 },
        images: [],
        changes: { columns_added: ['x'], columns_removed: [], rows_before: 1, rows_after: 1 },
      }),
    );
    spyOn(dataService, 'sendAiChat').and.returnValue(of({
      message: 'Fixed.',
      actions: [{ type: 'execute_code', payload: { code: "df['x'] = 1" } }],
    }));

    component.applyToDataset();

    expect(execSpy.calls.argsFor(0)[2].mode).toBe('apply');
    expect(execSpy.calls.argsFor(1)[2].mode).toBe('apply');
    expect(sharedService.triggerDataRefresh).toHaveBeenCalled();
    expect(component.cell!.lastRun?.status).toBe('success');
  });

  it('triggers auto-fix on status:error response shape (HTTP 200-style body)', () => {
    seedCell("globals()");

    const execSpy = spyOn(dataService, 'executeAiAction').and.returnValues(
      of({
        status: 'error',
        error: "name 'globals' is not defined",
        mode: 'exploratory',
      }),
      of({
        status: 'success',
        stdout: 'ok',
        preview: null,
        images: [],
        changes: null,
      }),
    );
    spyOn(dataService, 'sendAiChat').and.returnValue(of({
      message: 'Avoid globals.',
      actions: [{ type: 'execute_code', payload: { code: "print(df.shape)" } }],
    }));

    component.runExploratory();

    expect(execSpy.calls.count()).toBe(2);
    expect(component.cell!.code).toBe('print(df.shape)');
    expect(component.cell!.lastRun?.status).toBe('success');
  });

  // ── v3.5.0: accumulative feedback loop ────────────────────────────────
  function seedIntent(intent: string): void {
    component.addCodeline();
    component.cell!.intent = intent;
    component.cell!.mode = 'intent';
    (component as any).fileId = 42;
  }

  function assistantReply(message: string, code?: string): any {
    return {
      message,
      chat_span_id: 'span-1',
      chat_trace_id: 'trace-1',
      chat_session_id: 'declarai-file-42',
      actions: code ? [{ type: 'execute_code', payload: { code } }] : [],
    };
  }

  it('records the ask and the answer as thread turns', () => {
    seedIntent('draw the target ratio over time');
    spyOn(dataService, 'sendAiChat').and.returnValue(
      of(assistantReply('Here is the weekly bad rate.', 'print(df.head())')),
    );

    component.askAssistant();

    expect(component.turns.length).toBe(2);
    expect(component.turns[0]).toEqual(jasmine.objectContaining({
      role: 'user', kind: 'intent', content: 'draw the target ratio over time',
    }));
    expect(component.turns[1]).toEqual(jasmine.objectContaining({
      role: 'assistant', kind: 'intent', content: 'Here is the weekly bad rate.',
      code: 'print(df.head())', chatSpanId: 'span-1',
    }));
    expect(component.canRefine).toBeTrue();
    expect(component.iterationCount).toBe(1);
  });

  it('replays the thread and flags the turn kind when feedback is sent', () => {
    seedIntent('draw the target ratio over time');
    const chatSpy = spyOn(dataService, 'sendAiChat').and.returnValues(
      of(assistantReply('Weekly bad rate.', 'print(1)')),
      of(assistantReply('Switched to monthly buckets.', 'print(2)')),
    );
    spyOn(dataService, 'submitAiFeedback').and.returnValue(of({ status: 'success' }));

    component.askAssistant();
    // First ask carries no history — there is nothing to build on yet.
    expect(chatSpy.calls.argsFor(0)[3]).toEqual([]);
    expect(chatSpy.calls.argsFor(0)[1].codeline_turn_kind).toBe('intent');

    component.refineText = 'use monthly buckets instead';
    component.sendRefinement();

    const [message, context, section, history] = chatSpy.calls.argsFor(1);
    expect(context.codeline_turn_kind).toBe('refine');
    expect(context.codeline_iteration).toBe(2);
    expect(section).toBe('codeline_after_data_preview');
    // The whole prior exchange is replayed, with the pinned code attached to
    // the newest assistant turn — that is what makes it accumulative.
    expect(history.length).toBe(2);
    expect(history[0]).toEqual({ role: 'user', content: 'draw the target ratio over time' });
    expect(history[1].role).toBe('assistant');
    expect(history[1].content).toContain('Weekly bad rate.');
    expect(history[1].content).toContain('print(1)');
    // The prompt states the feedback and hands over the draft to revise.
    expect(message).toContain('use monthly buckets instead');
    expect(message).toContain('print(1)');

    expect(component.cell!.code).toBe('print(2)');
    expect(component.turns.length).toBe(4);
    expect(component.turns[2]).toEqual(jasmine.objectContaining({
      role: 'user', kind: 'refine', content: 'use monthly buckets instead',
    }));
    expect(component.refineText).toBe('');
    expect(component.iterationCount).toBe(2);
  });

  it('feeds the last run outcome into the refinement prompt', () => {
    seedIntent('summarise the target');
    spyOn(dataService, 'sendAiChat').and.returnValues(
      of(assistantReply('Done.', 'print(df.shape)')),
      of(assistantReply('Fixed the column name.', 'print(df.columns)')),
    );
    spyOn(dataService, 'submitAiFeedback').and.returnValue(of({ status: 'success' }));
    component.askAssistant();

    (component as any).patchLastRun({
      status: 'error',
      runKind: 'exploratory',
      error: "KeyError: 'Target'",
      stdout: 'partial output',
    });

    component.refineText = 'it crashes';
    component.sendRefinement();

    const message = (dataService.sendAiChat as jasmine.Spy).calls.argsFor(1)[0];
    expect(message).toContain("KeyError: 'Target'");
    expect(message).toContain('partial output');
    expect(message).toContain('exploratory');
  });

  it('clears stale run output when a refinement starts', () => {
    seedIntent('summarise the target');
    spyOn(dataService, 'sendAiChat').and.returnValues(
      of(assistantReply('Done.', 'print(df.shape)')),
      of(assistantReply('Revised.', 'print(df.dtypes)')),
    );
    spyOn(dataService, 'submitAiFeedback').and.returnValue(of({ status: 'success' }));
    component.askAssistant();
    (component as any).patchLastRun({
      status: 'success',
      runKind: 'exploratory',
      stdout: 'old stdout',
      images: ['data:image/png;base64,AAA'],
    });

    component.refineText = 'different chart please';
    component.sendRefinement();

    expect(component.cell!.lastRun?.stdout).toBeUndefined();
    expect(component.cell!.lastRun?.images).toBeUndefined();
    expect(component.cell!.lastRun?.assistantText).toBe('Revised.');
  });

  it('mirrors the feedback to Prometa against the turn it corrects', () => {
    seedIntent('summarise the target');
    spyOn(dataService, 'sendAiChat').and.returnValues(
      of(assistantReply('Done.', 'print(df.shape)')),
      of(assistantReply('Revised.', 'print(df.dtypes)')),
    );
    const feedbackSpy = spyOn(dataService, 'submitAiFeedback')
      .and.returnValue(of({ status: 'success' }));
    component.askAssistant();

    component.refineText = 'too many columns';
    component.sendRefinement();

    expect(feedbackSpy).toHaveBeenCalled();
    const payload = feedbackSpy.calls.mostRecent().args[0];
    expect(payload.comment).toBe('too many columns');
    expect(payload.source).toBe('declarai-codeline-refine');
    expect(payload.target_span_id).toBe('span-1');
    expect(payload.target_trace_id).toBe('trace-1');
    expect(payload.file_id).toBe(42);
  });

  it('rejects empty feedback without calling the assistant', () => {
    seedIntent('summarise the target');
    const chatSpy = spyOn(dataService, 'sendAiChat').and.returnValue(
      of(assistantReply('Done.', 'print(df.shape)')),
    );
    component.askAssistant();
    chatSpy.calls.reset();

    component.refineText = '   ';
    component.sendRefinement();

    expect(chatSpy).not.toHaveBeenCalled();
    expect(component.cell!.lastRun?.status).toBe('error');
    expect(component.cell!.lastRun?.error).toContain('what should change');
  });

  it('seeds a thread for cells restored from a pre-thread checkpoint', () => {
    component.addCodeline();
    (component as any).fileId = 42;
    component.cell!.intent = 'plot the distribution';
    component.cell!.code = 'print(df.head())';
    component.cell!.turns = [];
    (component as any).patchLastRun({
      status: 'success',
      runKind: 'assistant',
      assistantText: 'Older answer from a previous build.',
      generatedCode: 'print(df.head())',
    });
    expect(component.canRefine).toBeTrue();

    const chatSpy = spyOn(dataService, 'sendAiChat').and.returnValue(
      of(assistantReply('Now with bins.', 'print(df.describe())')),
    );
    spyOn(dataService, 'submitAiFeedback').and.returnValue(of({ status: 'success' }));

    component.refineText = 'add bins';
    component.sendRefinement();

    const history = chatSpy.calls.mostRecent().args[3];
    expect(history.length).toBe(2);
    expect(history[0].content).toBe('plot the distribution');
    expect(history[1].content).toContain('Older answer from a previous build.');
  });

  it('carries the thread into automatic error correction', () => {
    seedIntent('add a ratio feature');
    const chatSpy = spyOn(dataService, 'sendAiChat').and.returnValues(
      of(assistantReply('Ratio feature added.', "df['r'] = df['a'] / df['b']")),
      of(assistantReply('Guarded the divisor.', "df['r'] = df['a'] / df['b'].replace(0, 1)")),
    );
    component.askAssistant();

    spyOn(dataService, 'executeAiAction').and.returnValues(
      throwError(() => ({ error: { error: 'ZeroDivisionError' } })),
      of({ status: 'success', stdout: 'ok', preview: null, images: [], changes: null }),
    );

    component.runExploratory();

    const [, context, , history] = chatSpy.calls.argsFor(1);
    expect(context.codeline_turn_kind).toBe('auto_fix');
    expect(history.length).toBe(2);
    expect(component.turns.map((t) => t.kind)).toEqual([
      'intent', 'intent', 'auto_fix', 'auto_fix',
    ]);
    // Machine retries are not user iterations.
    expect(component.iterationCount).toBe(1);
  });

  it('clearThread drops the conversation but keeps the code', () => {
    seedIntent('add a ratio feature');
    spyOn(dataService, 'sendAiChat').and.returnValue(
      of(assistantReply('Added.', "df['r'] = 1")),
    );
    component.askAssistant();
    expect(component.turns.length).toBe(2);

    component.clearThread();

    expect(component.turns.length).toBe(0);
    expect(component.cell!.code).toBe("df['r'] = 1");
  });

  it('renders the thread and the feedback composer once the assistant answers', () => {
    seedIntent('draw the target ratio over time');
    spyOn(dataService, 'sendAiChat').and.returnValue(
      of(assistantReply('Here is the weekly bad rate.', 'print(1)')),
    );
    component.expanded = true;
    fixture.detectChanges();
    // Nothing to give feedback on yet.
    expect(fixture.nativeElement.querySelector('.codeline-refine')).toBeNull();

    component.askAssistant();
    fixture.detectChanges();

    const composer = fixture.nativeElement.querySelector('.codeline-refine textarea');
    expect(composer).withContext('feedback composer should render').toBeTruthy();
    expect(composer.getAttribute('id')).toBe('codeline-refine-after_data_preview');
    const rendered = fixture.nativeElement.querySelectorAll('.codeline-turn');
    expect(rendered.length).toBe(2);
    expect(rendered[0].textContent).toContain('You');
    expect(rendered[1].textContent).toContain('Assistant');

    // Send is disabled until the user actually writes feedback.
    const send = fixture.nativeElement.querySelector('.run-btn.refine') as HTMLButtonElement;
    expect(send.disabled).toBeTrue();
    component.refineText = 'use monthly buckets';
    fixture.detectChanges();
    expect(send.disabled).toBeFalse();
  });

  it('restoreTurnCode puts an earlier draft back in the Code tab', () => {
    seedIntent('add a ratio feature');
    spyOn(dataService, 'sendAiChat').and.returnValues(
      of(assistantReply('v1', "df['r'] = 1")),
      of(assistantReply('v2', "df['r'] = 2")),
    );
    spyOn(dataService, 'submitAiFeedback').and.returnValue(of({ status: 'success' }));
    component.askAssistant();
    component.refineText = 'try something else';
    component.sendRefinement();
    expect(component.cell!.code).toBe("df['r'] = 2");

    component.restoreTurnCode(component.turns[1]);

    expect(component.cell!.code).toBe("df['r'] = 1");
    expect(component.cell!.mode).toBe('code');
  });
});
