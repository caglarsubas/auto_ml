import { fakeAsync, tick } from '@angular/core/testing';
import { of, Subject } from 'rxjs';
import { ModelingComponent } from './modeling.component';

describe('Displayed-operation search cancellation', () => {
  const first = '11111111-1111-4111-8111-111111111111';
  const second = '22222222-2222-4222-8222-222222222222';
  let component: ModelingComponent;
  let data: any;
  let shared: any;
  let sfsPolling: jasmine.Spy;
  let hpPolling: jasmine.Spy;
  const reply = (operation = first, file = 1, status = 'started') => ({
    file_id: file,
    operation_id: operation,
    status,
  });

  beforeEach(() => {
    data = jasmine.createSpyObj('DataService', [
      'startSfs',
      'resumeSfs',
      'startSfsWithInitialFeatures',
      'startHyperparam',
      'getSfsStatus',
      'getHyperparamStatus',
      'stopSfs',
      'stopHyperparam',
    ]);
    shared = jasmine.createSpyObj('SharedService', ['setActiveProcess', 'getActiveProcess']);
    shared.getActiveProcess.and.returnValue(null);
    component = new ModelingComponent(
      shared,
      data,
      {} as any,
      'browser' as any,
      {} as any,
      {} as any,
      {} as any,
    );
    component.currentFileId = 1;
    spyOn(component as any, 'pushModelingCheckpoint');
    spyOn(component as any, 'pushModelingAiContext');
    sfsPolling = spyOn(component as any, 'startSfsStatusPolling');
    hpPolling = spyOn(component as any, 'startHyperparamStatusPolling');
    data.stopSfs.and.returnValue(of(reply(first, 1, 'stop_requested')));
    data.stopHyperparam.and.returnValue(of(reply(first, 1, 'stop_requested')));
  });
  afterEach(() => component.ngOnDestroy());

  for (const kind of ['sfs', 'hyperparam'] as const) {
    const start = (response: any = reply()) => {
      if (kind === 'sfs') {
        data.startSfs.and.returnValue(of(response));
        component.startSfs();
      } else {
        data.startHyperparam.and.returnValue(of(response));
        component.startHyperparam();
      }
    };
    const stop = () => (kind === 'sfs' ? component.stopSfs() : component.stopHyperparam());
    const stopSpy = () => (kind === 'sfs' ? data.stopSfs : data.stopHyperparam);
    const stopping = () => (kind === 'sfs' ? component.sfsStopping : component.hpStopping);
    const message = () => (kind === 'sfs' ? component.sfsMessage : component.hpMessage);
    const running = () => {
      if (kind === 'sfs') component.sfsRunning = true;
      else component.hpRunning = true;
    };

    it(`${kind}: uses the acknowledged operation and suppresses duplicate clicks`, () => {
      start();
      stop();
      stop();
      expect(stopSpy()).toHaveBeenCalledOnceWith(1, first);
      expect(stopping()).toBeTrue();
    });

    for (const response of [{ status: 'started' }, reply('not-a-uuid'), reply(first, 2)]) {
      it(`${kind}: missing/malformed/foreign start identity cannot fall back to current-run stop ${JSON.stringify(response)}`, () => {
        start(response);
        stop();
        expect(stopSpy()).not.toHaveBeenCalled();
        expect(stopping()).toBeFalse();
        expect(message()).toContain('Refresh status');
      });
    }

    it(`${kind}: checkpoint history is not live stop authority`, () => {
      start();
      component.restoreFromCheckpoint({
        hpRunning: true,
        operation_id: first,
        substep: 'hyperparam_running',
      });
      running();
      stop();
      expect(stopSpy()).not.toHaveBeenCalled();
      expect(message()).toContain('Refresh status');
    });

    it(`${kind}: switching away and back invalidates earlier identity`, () => {
      start();
      component.currentFileId = 2;
      component.currentFileId = 1;
      running();
      stop();
      expect(stopSpy()).not.toHaveBeenCalled();
    });

    for (const response of [reply(second, 1, 'stop_requested'), { status: 'stop_requested' }]) {
      it(`${kind}: an unverified acknowledgement clears waiting without resubmitting ${JSON.stringify(response)}`, () => {
        stopSpy().and.returnValue(of(response));
        start();
        stop();
        stop();
        expect(stopSpy()).toHaveBeenCalledTimes(1);
        expect(stopping()).toBeFalse();
        expect(message()).toContain('Refresh status');
      });
    }

    it(`${kind}: matching terminal acknowledgement does not keep waiting`, () => {
      stopSpy().and.returnValue(of(reply(first, 1, 'not_running')));
      start();
      stop();
      expect(stopping()).toBeFalse();
      expect(message()).toContain('no longer running');
      stop();
      expect(stopSpy()).toHaveBeenCalledTimes(1);
    });

    it(`${kind}: a conflict is explained and never retried against the newer run`, () => {
      const pending = new Subject<any>();
      stopSpy().and.returnValue(pending);
      start();
      stop();
      pending.error({
        status: 409,
        error: { error: 'The displayed operation changed. Refresh status.' },
      });
      expect(stopping()).toBeFalse();
      expect(message()).toContain('operation changed');
      stop();
      expect(stopSpy()).toHaveBeenCalledTimes(1);
    });

    for (const error of [false, true]) {
      it(`${kind}: a delayed stop ${error ? 'error' : 'acknowledgement'} cannot change a newer displayed operation`, () => {
        const pending = new Subject<any>();
        stopSpy().and.returnValue(pending);
        start();
        stop();
        start(reply(second));
        const currentMessage = message();
        if (error) pending.error({ status: 409, error: { error: 'Old conflict' } });
        else pending.next(reply(first, 1, 'stop_requested'));
        expect(message()).toBe(currentMessage);
        expect(stopping()).toBeFalse();
        stopSpy().and.returnValue(of(reply(second, 1, 'stop_requested')));
        stop();
        expect(stopSpy()).toHaveBeenCalledWith(1, second);
      });
    }

    it(`${kind}: a delayed start callback cannot bind another dataset`, () => {
      const pending = new Subject<any>();
      if (kind === 'sfs') {
        data.startSfs.and.returnValue(pending);
        component.startSfs();
      } else {
        data.startHyperparam.and.returnValue(pending);
        component.startHyperparam();
      }
      component.currentFileId = 2;
      pending.next(reply());
      running();
      stop();
      expect(stopSpy()).not.toHaveBeenCalled();
    });

    it(`${kind}: reattachment gets authority from fresh running status`, () => {
      const request = kind === 'sfs' ? data.getSfsStatus : data.getHyperparamStatus;
      request.and.returnValue(of(reply(first, 1, 'running')));
      (component as any).resumeActiveProcess({ type: kind, file_id: 1 });
      stop();
      expect(stopSpy()).toHaveBeenCalledOnceWith(1, first);
    });

    it(`${kind}: polling updates identity and clears the old stop wait`, fakeAsync(() => {
      const responses = new Subject<any>();
      const poll = kind === 'sfs' ? sfsPolling : hpPolling;
      const request = kind === 'sfs' ? data.getSfsStatus : data.getHyperparamStatus;
      request.and.returnValue(responses);
      poll.and.callThrough();
      start();
      tick(1000);
      responses.next(reply(first, 1, 'running'));
      stop();
      expect(stopping()).toBeTrue();
      responses.next(reply(second, 1, 'running'));
      expect(stopping()).toBeFalse();
      stopSpy().and.returnValue(of(reply(second, 1, 'stop_requested')));
      stop();
      expect(stopSpy()).toHaveBeenCalledWith(1, second);
      component.ngOnDestroy();
    }));

    it(`${kind}: delayed polling from an earlier dataset cannot bind the current one`, fakeAsync(() => {
      const responses = new Subject<any>();
      const poll = kind === 'sfs' ? sfsPolling : hpPolling;
      const request = kind === 'sfs' ? data.getSfsStatus : data.getHyperparamStatus;
      request.and.returnValue(responses);
      poll.and.callThrough();
      start();
      tick(1000);
      component.currentFileId = 2;
      responses.next(reply(first, 1, 'running'));
      running();
      stop();
      expect(stopSpy()).not.toHaveBeenCalled();
      component.ngOnDestroy();
    }));
  }

  for (const mode of ['resume', 'forward']) {
    it(`SFS ${mode} binds its newly accepted operation`, () => {
      if (mode === 'resume') {
        data.resumeSfs.and.returnValue(of(reply()));
        component.resumeSfs();
      } else {
        component.sfsBackwardRemainingFeatures = ['x'];
        data.startSfsWithInitialFeatures.and.returnValue(of(reply()));
        component.startForwardFromBackwardFeatures();
      }
      component.stopSfs();
      expect(data.stopSfs).toHaveBeenCalledOnceWith(1, first);
    });
  }
});
