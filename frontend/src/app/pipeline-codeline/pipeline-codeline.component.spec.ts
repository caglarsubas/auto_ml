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
});
