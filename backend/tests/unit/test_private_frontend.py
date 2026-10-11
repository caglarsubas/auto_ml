"""Source/data separation and tamper boundaries for compiled private assets."""

import importlib
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def package(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / 'scripts'))
    return importlib.import_module('private_frontend_package')


@pytest.fixture
def sealed(package, tmp_path):
    root = tmp_path / 'package'
    browser = root / 'browser'
    browser.mkdir(parents=True)
    files = {'index.html': b'<app-root></app-root>', 'main-ABC.js': b'compiled', 'assets/font.woff2': b'font'}
    for name, data in files.items():
        path = browser / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(data)
    record = {'schema': 'private_frontend_v1', 'api_root': '/api/', 'assets': package.inventory(files)}
    (root / 'manifest.json').write_text(json.dumps(record))
    return root


def test_snapshot_omits_private_untracked_download_metadata_and_tests(package, tmp_path, monkeypatch):
    root = tmp_path / 'repo'
    frontend = root / 'frontend'
    selected = package.CONFIG | {'src/main.ts', 'src/index.html', 'src/environments/environment.private.ts', 'src/assets/font.woff2'}
    omitted = {'src/assets/private.png:Zone.Identifier', 'src/assets/sources.json', 'src/assets/helper.py',
               'src/app/test.spec.ts', '.env', 'e2e/credentials.ts'}
    for name in selected | omitted | {'src/assets/untracked.png'}:
        path = frontend / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'cli': {'analytics': 'old'}}) if name == 'angular.json' else name)
    monkeypatch.setattr(package.subprocess, 'run', lambda *a, **kw: type('Result', (), {
        'stdout': b'\0'.join(('frontend/' + name).encode() for name in selected | omitted)})())
    destination = tmp_path / 'snapshot'
    hashes = package.snapshot(destination, root)
    assert set(hashes) == selected
    assert json.loads((destination / 'angular.json').read_text())['cli']['analytics'] is False
    assert all(not (destination / name).exists() for name in omitted | {'src/assets/untracked.png'})
    # A tracked source link also fails before a destination is published.
    path = frontend / 'src/main.ts'
    path.unlink();path.symlink_to(frontend / '.env')
    with pytest.raises(package.FrontendError, match='source_invalid'):
        package.snapshot(tmp_path / 'rejected', root)
    assert not (tmp_path / 'rejected').exists()


@pytest.mark.parametrize('fault', ['changed', 'extra', 'missing', 'symlink', 'hidden', 'map', 'metadata', 'reserved', 'manifest', 'nonobject'])
def test_integrity_or_unpublishable_assets_block_before_context(package, sealed, fault):
    browser = sealed / 'browser'
    if fault == 'changed':
        (browser / 'main-ABC.js').write_bytes(b'changed')
    elif fault == 'extra':
        (browser / 'extra.js').write_bytes(b'extra')
    elif fault == 'missing':
        (browser / 'main-ABC.js').unlink()
    elif fault == 'symlink':
        (browser / 'private.js').symlink_to(sealed / 'manifest.json')
    elif fault in {'hidden', 'map', 'metadata'}:
        (browser / {'hidden': '.env', 'map': 'main.js.map', 'metadata': 'sources.json'}[fault]).write_text('private')
    elif fault == 'reserved':
        (browser / 'api').mkdir();(browser / 'api/private.js').write_text('private')
    elif fault == 'manifest':
        (sealed / 'manifest.json').write_text('{}')
    else:
        (sealed / 'manifest.json').write_text('[]')
    with pytest.raises(package.FrontendError):
        package.verified_assets(sealed)


def test_asset_size_budget_blocks_before_reading_large_file(package, sealed, monkeypatch):
    monkeypatch.setattr(package, 'LIMIT', 2)
    with pytest.raises(package.FrontendError, match='budget_exceeded'):
        package.verified_assets(sealed)


def test_ingress_serves_only_manifest_assets_and_known_routes(package, sealed, tmp_path):
    ingress = importlib.import_module('private_ingress_package')
    root = Path(__file__).resolve().parents[3]
    record = ingress.context(tmp_path / 'context', 'api.private.test:8443', root=root, frontend=sealed)
    assert record['frontend']['assets'] == package.verified_assets(sealed)[0]['assets']
    config = (tmp_path / 'context/nginx.conf').read_text()
    assert 'location = /assets/font.woff2' in config and 'location = /model-development/declaration' in config
    assert 'location / { return 404; }' in config
    assert 'location = /manifest.json' not in config and 'location = /admin/' not in config
    assert "connect-src 'self'" in config
    assert 'script-src https://api.private.test:8443/main-ABC.js;' in config
    assert "script-src 'self'" not in config
    assert 'add_header Content-Disposition attachment always;' in config
    assert 'Content-Security-Policy "sandbox;' in config
    assert (tmp_path / 'context/frontend/main-ABC.js').read_bytes() == b'compiled'


@pytest.mark.parametrize('name', ['../secret.js', '.env', 'asset;return.js', 'asset{evil}.js', 'a\nb.js', '/root.js', 'api/$value.js'])
def test_manifest_names_cannot_inject_nginx_configuration(package, name):
    ingress = importlib.import_module('private_ingress_package')
    with pytest.raises(ingress.IngressError, match='frontend_name_invalid'):
        ingress.configuration('api.private.test', frontend_files=[name])
