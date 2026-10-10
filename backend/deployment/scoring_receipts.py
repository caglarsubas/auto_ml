"""Input/runtime-bound native batch receipts; hashes are not signatures."""
import hashlib
import platform
import re
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

PACKAGES = ('Django', 'djangorestframework', 'pandas', 'numpy', 'scikit-learn',
            'xgboost', 'lightgbm', 'catboost', 'joblib')
RUNTIME_FILES = ('deployment/deploy_utils.py', 'deployment/evidence.py',
                 'deployment/scoring_receipts.py', 'deployment/offline_verify.py', 'encoding/fitted.py',
                 'preprocessing/replay.py', 'modeling/alt_pipelines.py',
                 'modeling/booster_adapters.py', 'modeling/calibration_utils.py',
                 'modeling/execution_artifacts.py', 'evaluation/eval_utils.py')


def byte_digest(raw):
    return hashlib.sha256(raw).hexdigest()


def require_digest(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('An exact lowercase SHA-256 digest is required.')
    return value


def scoring_runtime():
    packages = {}
    for package in PACKAGES:
        try:
            packages[package] = version(package)
        except PackageNotFoundError:
            packages[package] = None
    root = Path(__file__).resolve().parent.parent
    return {'python_version': platform.python_version(), 'packages': packages,
            'source_sha256': {name: byte_digest((root / name).read_bytes()) for name in RUNTIME_FILES}}


def csv_input(raw):
    return {'format': 'csv', 'sha256': byte_digest(raw), 'bytes': len(raw),
            'parser': 'pandas.read_csv/defaults', 'pandas_version': version('pandas')}
