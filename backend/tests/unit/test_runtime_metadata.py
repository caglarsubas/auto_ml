"""Parsing reuse must never turn installed metadata into a stale runtime snapshot."""

import os
from importlib import metadata
from pathlib import Path

import pytest

from deployment import runtime_metadata

pytestmark = pytest.mark.unit


class TextDistribution(metadata.Distribution):
    def __init__(self, entries):
        self.entries = entries
        self.reads = []

    def read_text(self, filename):
        self.reads.append(filename)
        return self.entries.get(filename)

    def locate_file(self, path):
        raise AssertionError("Version parsing must not locate installed code")


@pytest.fixture(autouse=True)
def isolated_parse_cache():
    runtime_metadata._parsed_version.cache_clear()
    yield
    runtime_metadata._parsed_version.cache_clear()


@pytest.mark.parametrize("package", ["Django", "celery", "kombu", "redis", "numpy", "pandas", "scipy", "scikit-learn", "xgboost"])
def test_installed_versions_equal_the_public_metadata_api(package):
    expected = metadata.version(package)
    assert runtime_metadata.package_version(package) == expected
    assert runtime_metadata.package_version(package) == expected
    assert runtime_metadata._parsed_version.cache_info().hits == 1


@pytest.mark.parametrize("location", ["METADATA", "PKG-INFO", ""])
def test_standard_metadata_fallback_order_is_preserved(monkeypatch, location):
    current = TextDistribution({location: "Metadata-Version: 2.1\nName: probe\nVersion: 1.2.3\n\nBody\n"})
    expected = current.version
    current.reads.clear()
    monkeypatch.setattr(runtime_metadata, "distribution", lambda package: current)
    assert runtime_metadata.package_version("probe") == expected
    assert current.reads == ["METADATA", "PKG-INFO", ""][:["METADATA", "PKG-INFO", ""].index(location) + 1]


@pytest.mark.parametrize("headers", [
    "Version: 1.2.3\n",
    "vErSiOn: 1.2.3\n",
    "Version: 1.2.3\nVersion: 9.0\n",
    "Version: first\n second\n",
    "Name: missing-version\n",
])
def test_header_semantics_match_distribution_version(monkeypatch, headers):
    current = TextDistribution({"METADATA": headers + "\nDescription\nVersion: body-is-not-a-header\n"})
    expected = current.version
    monkeypatch.setattr(runtime_metadata, "distribution", lambda package: current)
    assert runtime_metadata.package_version("probe") == expected
    assert runtime_metadata.package_version("probe") == expected


def test_changed_metadata_is_observed_with_identical_path_inode_size_and_mtime(monkeypatch, tmp_path):
    directory = tmp_path / "fresh_metadata_probe-1.0.dist-info"
    directory.mkdir()
    path = directory / "METADATA"
    text = "Metadata-Version: 2.1\nName: fresh-metadata-probe\nVersion: 1.0\n\n"
    path.write_text(text)
    monkeypatch.syspath_prepend(str(tmp_path))
    assert runtime_metadata.package_version("fresh-metadata-probe") == metadata.version("fresh-metadata-probe") == "1.0"
    original = path.stat()
    path.write_text(text.replace("Version: 1.0", "Version: 2.0"))
    os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
    changed = path.stat()
    assert (changed.st_ino, changed.st_size, changed.st_mtime_ns) == (original.st_ino, original.st_size, original.st_mtime_ns)
    assert runtime_metadata.package_version("fresh-metadata-probe") == metadata.version("fresh-metadata-probe") == "2.0"


@pytest.mark.parametrize("failure", ["missing", "unreadable"])
def test_a_cached_parse_never_hides_a_new_lookup_or_read_error(monkeypatch, failure):
    current = TextDistribution({"METADATA": "Version: 1.0\n\n"})
    monkeypatch.setattr(runtime_metadata, "distribution", lambda package: current)
    assert runtime_metadata.package_version("probe") == "1.0"
    assert runtime_metadata.package_version("probe") == "1.0"

    def missing(package):
        raise metadata.PackageNotFoundError(package)

    def unreadable(filename):
        raise OSError("metadata read refused")

    if failure == "missing":
        monkeypatch.setattr(runtime_metadata, "distribution", missing)
        expected = metadata.PackageNotFoundError
    else:
        monkeypatch.setattr(current, "read_text", unreadable)
        expected = OSError
    with pytest.raises(expected):
        runtime_metadata.package_version("probe")


def test_identical_text_shares_parsing_but_each_distribution_is_resolved_and_read(monkeypatch):
    entries = {name: TextDistribution({"METADATA": "Version: 3.0\n\n"}) for name in ("first", "second")}
    lookups = []

    def resolve(package):
        lookups.append(package)
        return entries[package]

    monkeypatch.setattr(runtime_metadata, "distribution", resolve)
    assert runtime_metadata.package_version("first") == "3.0"
    assert runtime_metadata.package_version("second") == "3.0"
    assert lookups == ["first", "second"]
    assert entries["first"].reads == entries["second"].reads == ["METADATA"]
    assert runtime_metadata._parsed_version.cache_info().hits == 1


def test_oversized_metadata_keeps_standard_semantics_without_cache_retention(monkeypatch):
    current = TextDistribution({"METADATA": "Version: 7.0\n\n" + "x" * (runtime_metadata._MAX_CACHE_CHARACTERS + 1)})
    monkeypatch.setattr(runtime_metadata, "distribution", lambda package: current)
    assert runtime_metadata.package_version("probe") == current.version == "7.0"
    assert runtime_metadata.package_version("probe") == "7.0"
    assert runtime_metadata._parsed_version.cache_info().currsize == 0


def test_distinct_metadata_parses_have_a_bounded_cache(monkeypatch):
    current = TextDistribution({})
    monkeypatch.setattr(runtime_metadata, "distribution", lambda package: current)
    for number in range(67):
        current.entries["METADATA"] = f"Version: {number}.0\n\n"
        assert runtime_metadata.package_version("probe") == f"{number}.0"
    info = runtime_metadata._parsed_version.cache_info()
    assert info.currsize == info.maxsize == 64


@pytest.mark.parametrize("override", ["version", "metadata"])
def test_custom_distribution_properties_keep_their_public_api_semantics(monkeypatch, override):
    class CustomVersion(TextDistribution):
        @property
        def version(self):
            return "provider-version"

    class CustomMetadata(TextDistribution):
        @property
        def metadata(self):
            return {"Version": "provider-metadata-version"}

    current = (CustomVersion if override == "version" else CustomMetadata)({"METADATA": "Version: ignored\n\n"})
    monkeypatch.setattr(runtime_metadata, "distribution", lambda package: current)
    assert runtime_metadata.package_version("probe") == current.version
    assert current.reads == []
    assert runtime_metadata._parsed_version.cache_info().currsize == 0


@pytest.mark.parametrize("consumer", ["job", "scoring", "metric"])
def test_helper_source_remains_live_in_every_changed_runtime_fingerprint(monkeypatch, consumer):
    from deployment.scoring_receipts import scoring_runtime
    from execution_jobs.service import runtime
    from modeling.declared_metric import metric_spec

    helper = "deployment/runtime_metadata.py"
    builders = {
        "job": lambda: runtime()["sources"][helper],
        "scoring": lambda: scoring_runtime()["source_sha256"][helper],
        "metric": lambda: metric_spec({"task": "regression", "objective": {"primary_metric": "rmse"}, "sha256": "a" * 64})["implementation_sha256"],
    }
    before = builders[consumer]()
    original = Path.read_bytes

    def changed(path):
        raw = original(path)
        return raw + b"\n# changed implementation\n" if path.as_posix().endswith(helper) else raw

    monkeypatch.setattr(Path, "read_bytes", changed)
    assert builders[consumer]() != before
    assert runtime_metadata._parsed_version.cache_info().hits > 0
