#!/usr/bin/env python3
"""Verify fresh installed versions against the shipped private runtime profile."""
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import platform
import sys

from packaging.markers import default_environment
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ('docker/private-api.requirements.lock', 'docker/private-qualification.constraints.txt')


class DependencyProfileError(ValueError):
    def __init__(self, code, package=None):
        self.code, self.package = code, package
        super().__init__(code + (': ' + package if package else ''))


def verify(paths, lookup=None, environment=None):
    """Compare every pin; never retain an installed-state or successful lookup."""
    pins, sources, skipped = {}, {}, {}
    selected_environment = {**default_environment(), **(environment or {})}
    if not paths:
        raise DependencyProfileError('private_dependency_profile_empty')
    for path in paths:
        raw = Path(path).read_bytes()
        sources[Path(path).name] = hashlib.sha256(raw).hexdigest()
        for line in raw.decode('utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            try:
                requirement = Requirement(line)
            except InvalidRequirement:
                raise DependencyProfileError('private_dependency_pin_invalid') from None
            specs = list(requirement.specifier)
            if (requirement.url or requirement.extras or len(specs) != 1
                    or specs[0].operator != '==' or '*' in specs[0].version):
                raise DependencyProfileError('private_dependency_pin_invalid')
            name = canonicalize_name(requirement.name)
            if name in pins:
                raise DependencyProfileError('private_dependency_pin_duplicate', name)
            pins[name] = specs[0].version
            if requirement.marker and not requirement.marker.evaluate(environment=selected_environment):
                skipped[name] = str(requirement.marker)
    if not pins:
        raise DependencyProfileError('private_dependency_profile_empty')
    observed = {}
    for name, expected in sorted(pins.items()):
        if name in skipped:
            continue
        try:
            actual = (lookup or metadata.version)(name)
        except metadata.PackageNotFoundError:
            raise DependencyProfileError('private_dependency_missing', name) from None
        except Exception:
            raise DependencyProfileError('private_dependency_lookup_unavailable', name) from None
        if actual != expected:
            raise DependencyProfileError('private_dependency_version_mismatch', name)
        observed[name] = actual
    return {'schema': 'private_dependency_profile_v1', 'verified': True,
            'python': platform.python_version(), 'lock_sha256': sources,
            'environment': selected_environment, 'packages': observed, 'inactive_markers': skipped, 'lookup_mode': 'fresh_each_call',
            'package_bytes_or_customer_installation_qualified': False}


def main():
    try:
        result = verify([ROOT / name for name in PROFILE])
    except (DependencyProfileError, OSError, UnicodeError) as error:
        print(json.dumps({'verified': False, 'code': getattr(error, 'code', 'private_dependency_profile_unavailable'),
                          'package': getattr(error, 'package', None)}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
