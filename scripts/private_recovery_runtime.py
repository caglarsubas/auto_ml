"""Fixed, isolated same-image binary COPY protocol; no saved SQL or Python."""

CODE = r'''
import base64,hashlib,json,logging,os,sys
from pathlib import Path
logging.disable(logging.CRITICAL)
phase='runtime'
try:
    assert os.geteuid()==os.getegid()==10001
    sys.path.insert(0,'/app/scripts')
    from private_runtime_manifest import verify
    verify(Path('/app'))
    sys.path.insert(0,'/app/backend')
    os.environ['DJANGO_SETTINGS_MODULE']='backend.settings'
    Path('/tmp/recovery-media').mkdir(mode=0o700)
    import django
    django.setup()
    from django.apps import apps
    from django.db import connection,transaction
    from psycopg import sql
    encode=lambda x:(json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()
    sha=lambda x:hashlib.sha256(x).hexdigest()
    limit=64*1024**2
    request=json.load(sys.stdin)
    assert set(request)=={'action','payload'} and request['action'] in {'snapshot','inspect','restore'}
    phase='authority'
    with connection.cursor() as c:
        c.execute("SET search_path=pg_catalog,public; SET lock_timeout='5s'; SET statement_timeout='45s'")
        c.execute("SELECT current_user,rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,EXISTS(SELECT 1 FROM pg_auth_members m WHERE m.member=r.oid),(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()) FROM pg_roles r WHERE rolname=current_user")
        row=c.fetchone()
        assert row[0]==os.environ['DECLARAI_DB_USER'] and row[1] is True and all(v is False for v in row[2:8]) and row[8] is True
    phase='catalog'
    wanted={'django_migrations'}|{m._meta.db_table for m in apps.get_models(include_auto_created=True) if m._meta.managed and not m._meta.proxy}
    assert len(wanted)<256
    catalog={'tables':{},'sequences':{}}
    with connection.cursor() as c:
        c.execute("SELECT relname,relkind,pg_get_userbyid(relowner) FROM pg_class JOIN pg_namespace n ON n.oid=relnamespace WHERE n.nspname='public' AND relkind IN ('r','p','v','m','f','S') ORDER BY relname")
        relations=c.fetchall()
        assert {n for n,k,o in relations if k!='S'}==wanted and all(k in {'r','S'} and o==os.environ['DECLARAI_DB_USER'] for n,k,o in relations)
        for table in sorted(wanted):
            c.execute("SELECT a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,a.attidentity,a.attgenerated,pg_get_expr(d.adbin,d.adrelid),co.collname FROM pg_attribute a JOIN pg_class t ON t.oid=a.attrelid JOIN pg_namespace n ON n.oid=t.relnamespace LEFT JOIN pg_attrdef d ON d.adrelid=t.oid AND d.adnum=a.attnum LEFT JOIN pg_collation co ON co.oid=a.attcollation WHERE n.nspname='public' AND t.relname=%s AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum",[table])
            columns=[list(r) for r in c.fetchall()]
            assert columns and all(r[4]=='' for r in columns)
            c.execute("SELECT conname,contype,condeferrable,condeferred,convalidated,pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid=%s::regclass ORDER BY conname",['public.'+table])
            constraints=[list(r) for r in c.fetchall()]
            assert all(r[2] and r[3] for r in constraints if r[1]=='f')
            c.execute("SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=ANY(i.indkey) WHERE i.indrelid=%s::regclass AND i.indisprimary ORDER BY array_position(i.indkey,a.attnum)",['public.'+table])
            primary=[r[0] for r in c.fetchall()]
            assert primary
            c.execute("SELECT ci.relname,i.indisunique,i.indisvalid,i.indisready,i.indisexclusion,i.indimmediate,pg_get_indexdef(i.indexrelid) FROM pg_index i JOIN pg_class ci ON ci.oid=i.indexrelid WHERE i.indrelid=%s::regclass ORDER BY ci.relname",['public.'+table])
            indexes=[list(r) for r in c.fetchall()]
            c.execute("SELECT t.tgname,t.tgenabled,t.tgtype,p.proname,n.nspname FROM pg_trigger t JOIN pg_proc p ON p.oid=t.tgfoid JOIN pg_namespace n ON n.oid=p.pronamespace WHERE t.tgrelid=%s::regclass ORDER BY t.tgname",['public.'+table])
            # PostgreSQL assigns different numeric suffixes to internal RI names.
            triggers=sorted([list(r[1:]) for r in c.fetchall()])
            catalog['tables'][table]={'columns':columns,'primary':primary,'constraints':constraints,'indexes':indexes,'triggers':triggers}
        c.execute("SELECT s.relname,format_type(q.seqtypid,NULL),q.seqstart,q.seqincrement,q.seqmax,q.seqmin,q.seqcache,q.seqcycle,t.relname FROM pg_sequence q JOIN pg_class s ON s.oid=q.seqrelid JOIN pg_namespace n ON n.oid=s.relnamespace LEFT JOIN pg_depend d ON d.classid='pg_class'::regclass AND d.objid=s.oid AND d.deptype IN ('a','i') LEFT JOIN pg_class t ON t.oid=d.refobjid WHERE n.nspname='public' ORDER BY s.relname")
        for name,*definition in c.fetchall():
            assert definition[-1] in wanted
            catalog['sequences'][name]=definition
    def sequences():
        out={}
        with connection.cursor() as c:
            for name in catalog['sequences']:
                c.execute(sql.SQL('SELECT last_value,is_called FROM {}').format(sql.Identifier('public',name)))
                value,called=c.fetchone();out[name]=[value,called]
        return out
    def inspect(include_data=False):
        tables={};total=0
        with connection.cursor() as c:
            for table,meta in catalog['tables'].items():
                columns=[r[0] for r in meta['columns']]
                query=sql.SQL('COPY (SELECT {} FROM {} ORDER BY {}) TO STDOUT (FORMAT BINARY)').format(sql.SQL(',').join(map(sql.Identifier,columns)),sql.Identifier('public',table),sql.SQL(',').join(map(sql.Identifier,meta['primary'])))
                chunks=[];digest=hashlib.sha256();size=0
                with c.copy(query) as stream:
                    for chunk in stream:
                        raw=bytes(chunk);total+=len(raw);size+=len(raw)
                        assert total<=limit
                        digest.update(raw)
                        if include_data:chunks.append(raw)
                c.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier('public',table)))
                count=c.fetchone()[0]
                row={'sha256':digest.hexdigest(),'bytes':size,'rows':count}
                if include_data:row['data']=base64.b64encode(b''.join(chunks)).decode()
                tables[table]=row
        identities={k:{f:v[f] for f in ('sha256','bytes','rows')} for k,v in tables.items()}
        fresh=all(v['rows']==0 for k,v in tables.items() if k not in {'django_migrations','django_content_type','auth_permission'})
        return {'catalog':catalog,'tables':tables,'data_sha256':sha(encode(identities)),'sequences':sequences(),'empty_application':fresh,'bytes':total}
    phase='snapshot'
    if request['action'] in {'snapshot','inspect'}:
        with transaction.atomic():
            with connection.cursor() as c:c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            result=inspect(request['action']=='snapshot')
    else:
        phase='binding'
        v=request['payload'];source=v['source'];before=v['baseline']
        assert source['catalog']==before['catalog']==catalog
        current=inspect()
        assert current['data_sha256'] in {before['data_sha256'],source['data_sha256']}
        assert set(current['sequences'])==set(source['sequences'])==set(before['sequences'])
        assert all(current['sequences'][n] in [source['sequences'][n],before['sequences'][n]] for n in current['sequences'])
        phase='copy'
        with transaction.atomic():
            if current['data_sha256']!=source['data_sha256']:
                with connection.cursor() as c:
                    c.execute('SET CONSTRAINTS ALL DEFERRED')
                    c.execute(sql.SQL('TRUNCATE {} RESTART IDENTITY CASCADE').format(sql.SQL(',').join(sql.Identifier('public',n) for n in catalog['tables'])))
                    for table,meta in catalog['tables'].items():
                        raw=base64.b64decode(source['tables'][table]['data'],validate=True)
                        assert len(raw)==source['tables'][table]['bytes'] and sha(raw)==source['tables'][table]['sha256']
                        query=sql.SQL('COPY {} ({}) FROM STDIN (FORMAT BINARY)').format(sql.Identifier('public',table),sql.SQL(',').join(sql.Identifier(r[0]) for r in meta['columns']))
                        with c.copy(query) as stream:stream.write(raw)
                assert inspect()['data_sha256']==source['data_sha256']
            phase='sequences'
            with connection.cursor() as c:
                for name,(value,called) in source['sequences'].items():
                    c.execute('SELECT pg_catalog.setval(%s::pg_catalog.regclass,%s,%s)',['public.'+name,value,called])
            assert sequences()==source['sequences']
        phase='verified'
        result=inspect()
        assert result['data_sha256']==source['data_sha256'] and result['sequences']==source['sequences']
    print(json.dumps({'schema':'private_recovery_data_v1','action':request['action'],'application_role_elevated':False,'result':result},sort_keys=True))
except Exception:
    print('private_recovery_'+phase+'_failed');raise SystemExit(1)
finally:
    if 'connection' in globals():connection.close()
'''
