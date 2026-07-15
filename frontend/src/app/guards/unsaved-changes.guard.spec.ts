import { TestBed } from '@angular/core/testing';
import { RouterStateSnapshot } from '@angular/router';
import { ModelDevelopmentComponent } from '../model-development/model-development.component';
import { UnsavedChangesGuard } from './unsaved-changes.guard';

describe('UnsavedChangesGuard', () => {
  let guard: UnsavedChangesGuard;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [UnsavedChangesGuard] });
    guard = TestBed.inject(UnsavedChangesGuard);
  });

  function makeComponent(result: boolean) {
    return {
      canDeactivate: jasmine.createSpy('canDeactivate').and.returnValue(result),
    } as unknown as ModelDevelopmentComponent;
  }

  it('should be created', () => {
    expect(guard).toBeTruthy();
  });

  it('delegates to the component canDeactivate and returns its result (allow)', () => {
    const component = makeComponent(true);
    const nextState = { url: '/home' } as RouterStateSnapshot;

    const result = guard.canDeactivate(component, null as any, null as any, nextState);

    expect(result).toBeTrue();
    expect(component.canDeactivate).toHaveBeenCalledWith('/home');
  });

  it('delegates to the component canDeactivate and returns its result (block)', () => {
    const component = makeComponent(false);
    const nextState = { url: '/login' } as RouterStateSnapshot;

    const result = guard.canDeactivate(component, null as any, null as any, nextState);

    expect(result).toBeFalse();
    expect(component.canDeactivate).toHaveBeenCalledWith('/login');
  });

  it('passes undefined url when nextState is absent', () => {
    const component = makeComponent(true);

    const result = guard.canDeactivate(component, null as any, null as any, undefined);

    expect(result).toBeTrue();
    expect(component.canDeactivate).toHaveBeenCalledWith(undefined);
  });
});
