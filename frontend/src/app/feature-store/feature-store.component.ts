import { Component, OnInit } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { MatSnackBar } from '@angular/material/snack-bar';
import { DataService } from '../services/data.service';

@Component({
  selector: 'app-feature-store',
  templateUrl: './feature-store.component.html',
  styleUrls: ['./feature-store.component.css'],
})
export class FeatureStoreComponent implements OnInit {
  selectedTabIndex = 0;

  projects: any[] = [];
  connections: any[] = [];
  collections: any[] = [];

  projectForm: any = this.emptyProject();
  editingProjectId: number | null = null;

  connectionForm: any = this.emptyConnection();
  editingConnectionId: number | null = null;
  connectionTestMsg: string | null = null;

  collectionForm: any = this.emptyCollection();
  editingCollectionId: number | null = null;
  selectedCollection: any = null;
  preview: any = null;
  definitions: any[] = [];
  busy = false;
  errorMessage: string | null = null;
  filterProjectId: number | null = null;

  normalizationLevels = [
    { value: 'normalized', label: 'Normalized' },
    { value: 'partially_denormalized', label: 'Partially denormalized' },
    { value: 'denormalized', label: 'Denormalized' },
  ];

  constructor(
    private dataService: DataService,
    private snackBar: MatSnackBar,
    private router: Router,
    private route: ActivatedRoute,
  ) {}

  ngOnInit(): void {
    this.reloadAll();
    const dataTab = this.route.snapshot.data?.['tab'] || this.route.snapshot.url?.[0]?.path;
    if (dataTab === 'projects') this.selectedTabIndex = 0;
    else if (dataTab === 'connections') this.selectedTabIndex = 1;
    else if (dataTab === 'collections') this.selectedTabIndex = 2;

    this.route.queryParamMap.subscribe((params) => {
      const tab = params.get('tab');
      if (tab === 'projects') this.selectedTabIndex = 0;
      else if (tab === 'connections') this.selectedTabIndex = 1;
      else if (tab === 'collections') this.selectedTabIndex = 2;
      const collectionId = params.get('collection');
      if (collectionId) {
        this.selectedTabIndex = 2;
        this.openCollection(Number(collectionId));
      }
    });
  }

  emptyProject() {
    return {
      name: '',
      objective: '',
      decision_use_case: '',
      prediction_horizon: '',
      population: '',
      exclusions: '',
      target_contract: {
        event_definition: '',
        good_bad_window: '',
        target_column: '',
      },
    };
  }

  emptyConnection() {
    return {
      name: '',
      engine: 'duckdb',
      secret_ref: '',
      is_active: true,
      config: {
        base_path: '',
        host: 'localhost',
        port: 5432,
        database: 'postgres',
        user: 'postgres',
      },
    };
  }

  emptyCollection() {
    return {
      project: null as number | null,
      connection: null as number | null,
      name: '',
      description: '',
      sql_text: '',
      normalization_level: 'denormalized',
      grain: '',
      entity_keys_text: '',
    };
  }

  reloadAll(): void {
    this.dataService.listFsProjects().subscribe({
      next: (rows) => (this.projects = Array.isArray(rows) ? rows : (rows as any)?.results || []),
      error: (err) => this.toastError('Failed to load projects', err),
    });
    this.dataService.listFsConnections().subscribe({
      next: (rows) => (this.connections = Array.isArray(rows) ? rows : (rows as any)?.results || []),
      error: (err) => this.toastError('Failed to load connections', err),
    });
    this.loadCollections();
  }

  loadCollections(): void {
    this.dataService.listFsCollections(this.filterProjectId || undefined).subscribe({
      next: (rows) => (this.collections = Array.isArray(rows) ? rows : (rows as any)?.results || []),
      error: (err) => this.toastError('Failed to load collections', err),
    });
  }

  // ----- Projects -----
  editProject(p: any): void {
    this.editingProjectId = p.id;
    this.projectForm = {
      name: p.name,
      objective: p.objective || '',
      decision_use_case: p.decision_use_case || '',
      prediction_horizon: p.prediction_horizon || '',
      population: p.population || '',
      exclusions: p.exclusions || '',
      target_contract: {
        event_definition: p.target_contract?.event_definition || '',
        good_bad_window: p.target_contract?.good_bad_window || '',
        target_column: p.target_contract?.target_column || '',
      },
    };
  }

  resetProjectForm(): void {
    this.editingProjectId = null;
    this.projectForm = this.emptyProject();
  }

  saveProject(): void {
    if (!this.projectForm.name?.trim()) {
      this.snackBar.open('Project name is required', 'Close', { duration: 3000 });
      return;
    }
    const req = this.editingProjectId
      ? this.dataService.updateFsProject(this.editingProjectId, this.projectForm)
      : this.dataService.createFsProject(this.projectForm);
    req.subscribe({
      next: () => {
        this.snackBar.open('Project saved', 'Close', { duration: 2500 });
        this.resetProjectForm();
        this.reloadAll();
      },
      error: (err) => this.toastError('Failed to save project', err),
    });
  }

  // ----- Connections -----
  editConnection(c: any): void {
    this.editingConnectionId = c.id;
    this.connectionForm = {
      name: c.name,
      engine: c.engine,
      secret_ref: c.secret_ref || '',
      is_active: c.is_active !== false,
      config: {
        base_path: c.config?.base_path || '',
        host: c.config?.host || 'localhost',
        port: c.config?.port || 5432,
        database: c.config?.database || 'postgres',
        user: c.config?.user || 'postgres',
      },
    };
    this.connectionTestMsg = null;
  }

  resetConnectionForm(): void {
    this.editingConnectionId = null;
    this.connectionForm = this.emptyConnection();
    this.connectionTestMsg = null;
  }

  connectionPayload(): any {
    const f = this.connectionForm;
    const config =
      f.engine === 'duckdb'
        ? { base_path: f.config.base_path }
        : {
            host: f.config.host,
            port: Number(f.config.port) || 5432,
            database: f.config.database,
            user: f.config.user,
          };
    return {
      name: f.name,
      engine: f.engine,
      secret_ref: f.secret_ref || '',
      is_active: !!f.is_active,
      config,
    };
  }

  saveConnection(): void {
    if (!this.connectionForm.name?.trim()) {
      this.snackBar.open('Connection name is required', 'Close', { duration: 3000 });
      return;
    }
    const payload = this.connectionPayload();
    const req = this.editingConnectionId
      ? this.dataService.updateFsConnection(this.editingConnectionId, payload)
      : this.dataService.createFsConnection(payload);
    req.subscribe({
      next: () => {
        this.snackBar.open('Connection saved', 'Close', { duration: 2500 });
        this.resetConnectionForm();
        this.reloadAll();
      },
      error: (err) => this.toastError('Failed to save connection', err),
    });
  }

  testConnection(): void {
    this.connectionTestMsg = null;
    if (this.editingConnectionId) {
      this.dataService.testFsConnection(this.editingConnectionId).subscribe({
        next: (r) => (this.connectionTestMsg = r.message || (r.ok ? 'OK' : 'Failed')),
        error: (err) => (this.connectionTestMsg = err?.error?.message || 'Connection test failed'),
      });
    } else {
      this.dataService.testFsConnectionPayload(this.connectionPayload()).subscribe({
        next: (r) => (this.connectionTestMsg = r.message || (r.ok ? 'OK' : 'Failed')),
        error: (err) => (this.connectionTestMsg = err?.error?.message || 'Connection test failed'),
      });
    }
  }

  // ----- Collections -----
  startNewCollection(): void {
    this.editingCollectionId = null;
    this.selectedCollection = null;
    this.preview = null;
    this.definitions = [];
    this.collectionForm = this.emptyCollection();
    if (this.projects.length === 1) this.collectionForm.project = this.projects[0].id;
    if (this.connections.length === 1) this.collectionForm.connection = this.connections[0].id;
    this.errorMessage = null;
  }

  openCollection(id: number): void {
    this.busy = true;
    this.dataService.getFsCollection(id).subscribe({
      next: (c) => {
        this.busy = false;
        this.selectedCollection = c;
        this.editingCollectionId = c.id;
        this.definitions = Array.isArray(c.definitions) ? [...c.definitions] : [];
        this.collectionForm = {
          project: c.project,
          connection: c.connection,
          name: c.name,
          description: c.description || '',
          sql_text: c.sql_text || '',
          normalization_level: c.normalization_level || 'denormalized',
          grain: c.grain || '',
          entity_keys_text: Array.isArray(c.entity_keys) ? c.entity_keys.join(', ') : '',
        };
        this.preview = null;
        this.errorMessage = null;
      },
      error: (err) => {
        this.busy = false;
        this.toastError('Failed to load collection', err);
      },
    });
  }

  collectionPayload(): any {
    const keys = String(this.collectionForm.entity_keys_text || '')
      .split(/[,;\n]+/)
      .map((s: string) => s.trim())
      .filter(Boolean);
    return {
      project: this.collectionForm.project,
      connection: this.collectionForm.connection,
      name: this.collectionForm.name,
      description: this.collectionForm.description,
      sql_text: this.collectionForm.sql_text,
      normalization_level: this.collectionForm.normalization_level,
      grain: this.collectionForm.grain,
      entity_keys: keys,
    };
  }

  saveCollection(then?: () => void): void {
    const payload = this.collectionPayload();
    if (!payload.name?.trim() || !payload.project || !payload.connection) {
      this.snackBar.open('Name, project, and connection are required', 'Close', { duration: 3000 });
      return;
    }
    this.busy = true;
    const req = this.editingCollectionId
      ? this.dataService.updateFsCollection(this.editingCollectionId, payload)
      : this.dataService.createFsCollection(payload);
    req.subscribe({
      next: (c) => {
        this.busy = false;
        this.editingCollectionId = c.id;
        this.selectedCollection = c;
        this.snackBar.open('Collection saved', 'Close', { duration: 2500 });
        this.loadCollections();
        if (then) then();
      },
      error: (err) => {
        this.busy = false;
        this.toastError('Failed to save collection', err);
      },
    });
  }

  runPreview(): void {
    const run = () => {
      if (!this.editingCollectionId) return;
      this.busy = true;
      this.errorMessage = null;
      this.dataService
        .previewFsCollection(this.editingCollectionId, {
          sql_text: this.collectionForm.sql_text,
          save_sql: true,
          limit: 50,
        })
        .subscribe({
          next: (r) => {
            this.busy = false;
            this.preview = r;
            this.definitions = Array.isArray(r.definitions) ? [...r.definitions] : this.definitions;
            if (this.selectedCollection) this.selectedCollection.status = r.status;
            this.snackBar.open(`Preview: ${r.row_count} rows`, 'Close', { duration: 2500 });
          },
          error: (err) => {
            this.busy = false;
            this.errorMessage = err?.error?.error || err?.message || 'Preview failed';
          },
        });
    };
    if (!this.editingCollectionId) this.saveCollection(run);
    else {
      this.dataService
        .updateFsCollection(this.editingCollectionId, this.collectionPayload())
        .subscribe({
          next: () => run(),
          error: (err) => this.toastError('Failed to save before preview', err),
        });
    }
  }

  materialize(): void {
    const run = () => {
      if (!this.editingCollectionId) return;
      this.busy = true;
      this.errorMessage = null;
      this.dataService
        .materializeFsCollection(this.editingCollectionId, {
          sql_text: this.collectionForm.sql_text,
        })
        .subscribe({
          next: (r) => {
            this.busy = false;
            this.selectedCollection = r;
            this.definitions = Array.isArray(r.definitions) ? [...r.definitions] : this.definitions;
            this.snackBar.open(
              `Materialized ${r.materialize?.row_count ?? r.row_count} rows → Declaration #${r.materialized_declaration}`,
              'Close',
              { duration: 4000 },
            );
            this.loadCollections();
          },
          error: (err) => {
            this.busy = false;
            this.errorMessage = err?.error?.error || err?.message || 'Materialize failed';
          },
        });
    };
    if (!this.editingCollectionId) this.saveCollection(run);
    else {
      this.dataService
        .updateFsCollection(this.editingCollectionId, this.collectionPayload())
        .subscribe({
          next: () => run(),
          error: (err) => this.toastError('Failed to save before materialize', err),
        });
    }
  }

  saveDefinitions(): void {
    if (!this.editingCollectionId) return;
    this.dataService.updateFsDefinitions(this.editingCollectionId, this.definitions).subscribe({
      next: (defs) => {
        this.definitions = Array.isArray(defs) ? defs : this.definitions;
        this.snackBar.open('Feature definitions saved', 'Close', { duration: 2500 });
      },
      error: (err) => this.toastError('Failed to save definitions', err),
    });
  }

  openInModelDevelopment(): void {
    if (!this.editingCollectionId) return;
    this.router.navigate(['/model-development/declaration'], {
      queryParams: { featureCollectionId: this.editingCollectionId },
    });
  }

  private toastError(prefix: string, err: any): void {
    const detail = err?.error?.error || err?.error?.detail || err?.message || '';
    this.snackBar.open(`${prefix}${detail ? ': ' + detail : ''}`, 'Close', { duration: 5000 });
  }
}
