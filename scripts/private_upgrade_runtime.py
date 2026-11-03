"""Fixed image inspection and transactional, data-preserving index migrations."""

from private_recovery_runtime import CODE as RECOVERY_CODE

DESCRIBE_CODE = r"""
import hashlib,json,logging,os,sys
from pathlib import Path
logging.disable(logging.CRITICAL)
try:
    assert os.geteuid()==os.getegid()==10001
    sys.path.insert(0,'/app/scripts')
    from private_runtime_manifest import verify
    inventory=verify(Path('/app'))
    runtime=json.loads(Path('/app/runtime-manifest.json').read_bytes())
    source=json.loads(Path('/app/source-manifest.json').read_bytes())
    sys.path.insert(0,'/app/backend')
    Path('/tmp/upgrade-inspection').mkdir(mode=0o700)
    os.environ.update(DJANGO_SETTINGS_MODULE='backend.settings',DECLARAI_MEDIA_ROOT='/tmp/upgrade-inspection')
    import django;django.setup()
    from django.db.migrations.loader import MigrationLoader
    from django.db import migrations,models
    loader=MigrationLoader(None);assert not loader.replacements
    from django.db import connection
    assert connection.connection is None
    vertices=[];operations={}
    for key,migration in sorted(loader.disk_migrations.items()):
        path=Path(sys.modules[migration.__module__].__file__)
        assert (path.is_relative_to('/app/backend') or path.is_relative_to(sys.prefix)) and path.suffix=='.py'
        vertices.append({'app':key[0],'name':key[1],'parents':[list(p.key) for p in sorted(loader.graph.node_map[key].parents,key=lambda p:p.key)]})
        ops=[];safe=migration.atomic is True
        for outer in migration.operations:
            if type(outer) is not migrations.SeparateDatabaseAndState or outer.state_operations:
                safe=False;break
            for op in outer.database_operations:
                if type(op) is not migrations.AddIndex or type(op.index) is not models.Index:
                    safe=False;break
                index=op.index
                if index.expressions or index.condition or index.include or index.opclasses or not index.fields:
                    safe=False;break
                model=loader.project_state([key]).apps.get_model(key[0],op.model_name)
                fields=[]
                for name in index.fields:
                    field=model._meta.get_field(name.lstrip('-'))
                    fields.append(('-' if name.startswith('-') else '')+field.column)
                ops.append({'table':model._meta.db_table,'name':index.name,'fields':fields})
        operations['/'.join(key)]={'file_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'index_only':safe and bool(ops),'indexes':ops if safe else []}
    graph={'runtime_manifest_sha256':hashlib.sha256(Path('/app/runtime-manifest.json').read_bytes()).hexdigest(),
           'vertices':vertices,'targets':[list(k) for k in sorted(loader.graph.leaf_nodes())]}
    encoded=lambda v:(json.dumps(v,sort_keys=True,separators=(',',':'))+'\n').encode()
    print(json.dumps({'schema':'private_upgrade_image_v1','database_access':False,'graph':graph,
          'schema_sha256':hashlib.sha256(encoded(graph)).hexdigest(),'migrations':operations,
          'files':source['source_sha256'],'requirements_sha256':source['requirements_sha256'],
          'runtime':{k:runtime[k] for k in ('python','implementation','system','machine','packages')}},sort_keys=True))
except Exception:
    print('private_upgrade_inspection_failed');raise SystemExit(1)
"""

# Reuse the qualified byte-copy catalog/row fingerprint definitions unchanged.
# This is fixed source composition, never caller-supplied Python or saved SQL.
MIGRATE_CODE = (
    RECOVERY_CODE.split("    phase='snapshot'\n", 1)[0]
    + r"""
    from django.db.migrations.executor import MigrationExecutor
    v=request['payload']
    assert request['action']=='inspect' and set(v)=={'source_nodes','target_nodes','targets','data','sequences'}
    before_nodes={tuple(k) for k in v['source_nodes']};after_nodes={tuple(k) for k in v['target_nodes']}
    assert before_nodes<after_nodes or after_nodes<before_nodes
    executor=MigrationExecutor(connection);loader=executor.loader
    loader.check_consistent_history(connection)
    assert not loader.replacements and set(loader.disk_migrations)==before_nodes|after_nodes
    expected_data=v['data'];expected_sequences=v['sequences']
    def invariant():
        state=inspect()
        rows={k:{f:r[f] for f in ('sha256','bytes','rows')} for k,r in state['tables'].items() if k!='django_migrations'}
        seq={k:r for k,r in state['sequences'].items() if k!='django_migrations_id_seq'}
        assert rows==expected_data and seq==expected_sequences
    phase='transition_binding'
    applied=set(loader.applied_migrations)
    assert applied in (before_nodes,after_nodes)
    invariant()
    reused=applied==after_nodes
    if not reused:
        phase='transition_transaction'
        with transaction.atomic():
            with connection.cursor() as c:
                c.execute('SELECT pg_catalog.pg_try_advisory_xact_lock(1584948041,43)')
                assert c.fetchone()==(True,)
            plan=executor.migration_plan([tuple(k) for k in v['targets']])
            assert {m.app_label+'/'+m.name for m,backward in plan}=={'/'.join(k) for k in before_nodes^after_nodes}
            assert all(backward==(after_nodes<before_nodes) and m.atomic is True for m,backward in plan)
            from django.db import migrations,models
            for migration,backward in plan:
                assert migration.operations
                for outer in migration.operations:
                    assert type(outer) is migrations.SeparateDatabaseAndState and not outer.state_operations and outer.database_operations
                    for op in outer.database_operations:
                        assert type(op) is migrations.AddIndex and type(op.index) is models.Index
                        assert not op.index.expressions and not op.index.condition and not op.index.include and not op.index.opclasses
            executor.migrate([tuple(k) for k in v['targets']])
            assert set(MigrationExecutor(connection).loader.applied_migrations)==after_nodes
            invariant()
    phase='transition_verified'
    invariant()
    assert set(MigrationExecutor(connection).loader.applied_migrations)==after_nodes
    print(json.dumps({'schema':'private_upgrade_migration_v1','application_role_elevated':False,'reused':reused,
                      'data_and_sequences_preserved':True,'applied':sorted([list(k) for k in after_nodes])},sort_keys=True))
except Exception:
    print('private_upgrade_'+phase+'_failed');raise SystemExit(1)
finally:
    if 'connection' in globals():connection.close()
"""
)
