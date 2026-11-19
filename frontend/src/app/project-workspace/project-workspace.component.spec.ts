import { convertToParamMap, ActivatedRoute, Router } from '@angular/router';
import { BehaviorSubject, of, Subject } from 'rxjs';
import { DataService } from '../services/data.service';
import { ProjectWorkspaceService, WorkspaceState } from '../services/project-workspace.service';
import { ProjectWorkspaceComponent } from './project-workspace.component';

describe('Project workspace navigation', () => {
  const a = { id: 'a', name: 'Project A', role: 'developer' as const, membership_revision: 'a-1' };
  const b = { id: 'b', name: 'Project B', role: 'reviewer' as const, membership_revision: 'b-1' };

  function setup(datasets: (project: string) => any) {
    const state = new BehaviorSubject<WorkspaceState>({
      ready: true,
      loading: false,
      governed: true,
      projects: [a, b],
      selected: a,
      error: '',
    });
    const navigation = new BehaviorSubject(
      convertToParamMap({
        project_id: 'a',
        dataset_id: '11',
        view: 'training',
      }),
    );
    const workspace = {
      state$: state.asObservable(),
      get state() {
        return state.value;
      },
      get projectId() {
        return state.value.selected?.id;
      },
      refresh: () => of(state.value),
      select: (id: string) =>
        state.next({
          ...state.value,
          selected: state.value.projects.find((project) => project.id === id) ?? null,
        }),
    };
    const data = {
      listDatasets: jasmine.createSpy('listDatasets').and.callFake(datasets),
      listPipelineRuns: () => of([]),
    };
    const router = {
      navigate: jasmine.createSpy('navigate').and.callFake((_commands, options) => {
        const params = Object.fromEntries(
          navigation.value.keys.map((key) => [key, navigation.value.get(key)]),
        );
        for (const [key, value] of Object.entries(options.queryParams)) {
          if (value === null) delete params[key];
          else params[key] = String(value);
        }
        navigation.next(convertToParamMap(params));
        return Promise.resolve(true);
      }),
    };
    const component = new ProjectWorkspaceComponent(
      workspace as ProjectWorkspaceService,
      data as unknown as DataService,
      { queryParamMap: navigation.asObservable() } as ActivatedRoute,
      router as unknown as Router,
    );
    component.ngOnInit();
    return { component, state, navigation, data, router };
  }

  it('waits for authorized records and refuses a foreign or malformed dataset link', () => {
    const records = new Subject<any[]>();
    const { component, navigation } = setup(() => records);
    expect(component.trainingDataset).toBeNull();
    expect(component.loading).toBeTrue();
    records.next([{ id: 11, name: 'Development data' }]);
    records.complete();
    expect(component.trainingDataset?.id).toBe(11);
    navigation.next(convertToParamMap({ project_id: 'a', dataset_id: '99', view: 'training' }));
    expect(component.trainingDataset).toBeNull();
    expect(component.panelError).toContain('unavailable in the current project');
    navigation.next(
      convertToParamMap({ project_id: 'a', dataset_id: ['11', '99'], view: 'review' }),
    );
    expect(component.reviewDataset).toBeNull();
    expect(component.panelError).toContain('Choose a dataset');
    component.ngOnDestroy();
  });

  it('restores exact panels through history and clears their links on project changes', () => {
    const { component, state, navigation, router } = setup((project) =>
      of([{ id: project === 'a' ? 11 : 22, name: project }]),
    );
    expect(component.trainingDataset?.id).toBe(11);
    navigation.next(convertToParamMap({ project_id: 'b', dataset_id: '22', view: 'review' }));
    expect(state.value.selected?.id).toBe('b');
    expect(component.reviewDataset).toBe(22);
    expect(component.trainingDataset).toBeNull();
    navigation.next(convertToParamMap({ project_id: 'a', dataset_id: '11', view: 'training' }));
    expect(component.trainingDataset?.id).toBe(11);
    component.select('b');
    expect(router.navigate).toHaveBeenCalled();
    expect(navigation.value.get('dataset_id')).toBeNull();
    expect(navigation.value.get('view')).toBeNull();
    expect(component.trainingDataset).toBeNull();
    expect(component.reviewDataset).toBeNull();
    component.ngOnDestroy();
  });
});
