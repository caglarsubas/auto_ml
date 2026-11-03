#!/usr/bin/env python3
"""Qualify a real index release, interrupted upgrade, and current-data rollback."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import private_installation_upgrade as upgrade
import qualify_private_installation_recovery as q
from qualify_private_account_enrollment import https_roles
from qualify_private_upgrade_reference import reference_plan

recovery, startup, adopter = q.recovery, q.startup, q.adopter
ROOT = Path(__file__).resolve().parents[1]
require = q.require


class Scenario:
    def __init__(self, custody):
        self.custody = custody
        self.key = custody / "backup.key"
        self.key.write_bytes(os.urandom(32))
        self.key.chmod(0o400)
        self.archive = custody / "before.aesgcm"

    def observe(self, value, accounts, passwords, parent, prepared, adopted, invoke):
        self.accounts, self.passwords = accounts, passwords
        self.token = parent.name.removeprefix("declarai-p37-")
        self.source_id = value["request"]["installation_id"]

        def callback(session, handles):
            self.handles = handles
            self.ids = [
                row[k]["id"] for row in handles for k in ("training", "scoring")
            ]
            self.evidence = q.boundary(
                adopted["services"]["api"]["container_id"], "evidence", ids=self.ids
            )

        return callback

    def capture(self, plan, expected):
        self.backup = recovery.backup(plan, expected, self.key, self.archive)

    def login(self, value, parent):
        https_roles(
            value, self.accounts, self.passwords, parent, username_token=self.token
        )
        session = q.Session(value, parent)
        session.csrf = session.data("GET", "/api/auth/session/")["csrf_token"]
        session.csrf = session.data(
            "POST",
            "/api/auth/login/",
            {
                "username": "fixture-developer-" + self.token,
                "password": self.passwords["developer"],
            },
        )["csrf_token"]
        return session

    def verify_history(self, session, api):
        for row in self.handles:
            trained, scored = row["training"], row["scoring"]
            export, _ = session.request(
                "GET",
                f"/api/jobs/{trained['id']}/candidate/?sha256={trained['result_sha256']}",
            )
            scores, _ = session.request(
                "GET",
                f"/api/jobs/{scored['id']}/scores/?sha256={scored['result_sha256']}",
            )
            require(
                export == row["export"] and scores == row["scores"],
                "upgrade_completed_bytes",
            )
        require(
            q.boundary(api, "evidence", ids=self.ids) == self.evidence,
            "upgrade_completed_history",
        )

    def score(self, session):
        row = self.handles[0]
        trained = row["training"]
        preview = session.data(
            "POST",
            f"/api/jobs/{trained['id']}/scoring-input/?project_id={self.accounts['project_id']}",
            {
                "input_file_id": row["input_file_id"],
                "training_result_sha256": trained["result_sha256"],
            },
        )
        request = {
            k: preview[k]
            for k in (
                "kind",
                "training_job_id",
                "training_result_sha256",
                "input_file_id",
                "input_sha256",
                "scoring_sha256",
            )
        }
        request["request_id"] = str(uuid.uuid4())
        base = f"/api/jobs/datasets/{row['dataset_id']}/?project_id={self.accounts['project_id']}"
        queued = session.data("POST", base, request, 202)
        scored = session.finished(queued["id"])
        require(
            scored["state"] == "succeeded"
            and scored["result"]["scores"] == row["scoring"]["result"]["scores"],
            "upgrade_post_use_score",
        )
        require(
            session.data("POST", base, request)["id"] == scored["id"],
            "upgrade_post_use_idempotence",
        )
        return scored


def pending(plan, expected, parent):
    try:
        adopter.adoption(plan, expected, parent / "server.crt")
    except recovery.checker.planner.PlanError as error:
        require(str(error) == "upgrade_pending", "upgrade_pending_diagnostic")
    else:
        require(False, "upgrade_pending_adopted")


def transition(
    scenario,
    source_plan,
    source_sha,
    target_plan,
    target_sha,
    parent,
    archive,
    backup,
    *,
    faults=False,
):
    request = scenario.custody / ("transition-" + parent.name + ".json")
    spec = upgrade.render(
        archive,
        backup["backup_sha256"],
        scenario.key,
        source_plan,
        source_sha,
        target_plan,
        target_sha,
        request,
    )
    value = startup.checker.verify(target_plan, target_sha)
    journal = parent / "installation/transition"

    def apply(pin=spec["plan_sha256"]):
        return upgrade.apply(
            archive, scenario.key, target_plan, target_sha, request, pin
        )

    try:
        apply("0" * 64)
    except recovery.checker.planner.PlanError as error:
        require(
            str(error) == "upgrade_plan_digest" and not journal.exists(),
            "upgrade_stale_plan",
        )
    else:
        require(False, "upgrade_stale_plan_accepted")
    if faults:
        execute = upgrade.execute
        faulty = upgrade.MIGRATE_CODE.replace(
            "            executor.migrate([tuple(k) for k in v['targets']])",
            "            executor.migrate([tuple(k) for k in v['targets']])\n            raise RuntimeError('qualification_transaction_fault')",
        )
        require(faulty != upgrade.MIGRATE_CODE, "upgrade_fault_binding")

        def transaction_fault(*args, **kwargs):
            if args[3] == upgrade.MIGRATE_CODE:
                args = (*args[:3], faulty, *args[4:])
            return execute(*args, **kwargs)

        upgrade.execute = transaction_fault
        try:
            apply()
        except recovery.checker.planner.PlanError as error:
            require(
                str(error) == "upgrade_helper_failed", "upgrade_transaction_failure"
            )
        else:
            require(False, "upgrade_transaction_fault_accepted")
        finally:
            upgrade.execute = execute
        pending(target_plan, target_sha, parent)
        _, receipt, _ = upgrade.context(target_plan, target_sha)
        source = upgrade.image_value(
            value, startup.checker.verify(source_plan, source_sha)["images"]["api"]
        )
        source_image = recovery.resources.inspect("image", source["images"]["api"])
        state = recovery.schema_init.helper(source, receipt, source_image, "describe")
        require(state["state"] == "current", "upgrade_transaction_not_rolled_back")
        before = recovery.helper(source, receipt, source_image, "inspect")
        expected_catalog = recovery.unseal(
            recovery.private_read(archive, recovery.MAX_WIRE),
            recovery.private_read(scenario.key, 32, 0o400),
            backup["backup_sha256"],
        )["database"]["catalog"]
        require(
            before["catalog"] == expected_catalog, "upgrade_transaction_catalog_changed"
        )

        def lost_ack(*args, **kwargs):
            result = execute(*args, **kwargs)
            if args[3] == upgrade.MIGRATE_CODE:
                raise RuntimeError("qualification_after_migration_commit")
            return result

        upgrade.execute = lost_ack
        try:
            apply()
        except RuntimeError as error:
            require(
                str(error) == "qualification_after_migration_commit", "upgrade_lost_ack"
            )
        else:
            require(False, "upgrade_lost_ack_missing")
        finally:
            upgrade.execute = execute
        pending(target_plan, target_sha, parent)
        publish = recovery.publish

        def missing_completion(path, raw):
            if Path(path) == journal / "complete.json":
                raise RuntimeError("qualification_before_transition_completion")
            return publish(path, raw)

        recovery.publish = missing_completion
        try:
            apply()
        except RuntimeError as error:
            require(
                str(error) == "qualification_before_transition_completion",
                "upgrade_artifact_ack",
            )
        else:
            require(False, "upgrade_artifact_fault_missing")
        finally:
            recovery.publish = publish
        pending(target_plan, target_sha, parent)
        require(
            not (journal / "complete.json").exists()
            and not (journal / "staged-artifacts").exists(),
            "upgrade_publication_boundary",
        )
    first = apply()
    complete = (journal / "complete.json").read_bytes()
    require(
        first["reused"] is False
        and apply()["reused"] is True
        and (journal / "complete.json").read_bytes() == complete,
        "upgrade_completed_replay",
    )
    return spec, apply


def stop_application(plan, expected, adopted):
    value = startup.checker.verify(plan, expected)
    initialized = recovery.resources.initialization(value)
    profile, profile_sha, binding = adopter.application_profile(
        value, expected, initialized["initialization_id"]
    )
    for role, record in adopted["services"].items():
        info = recovery.resources.inspect("container", record["container_id"])
        image = recovery.resources.inspect(
            "image", value["images"]["ingress" if role == "ingress" else "api"]
        )
        adopter.validate_application(
            info, role, profile["services"][role], profile, profile_sha, binding, image
        )
        q.command(["container", "stop", "--time", "30", info["Id"]])
        q.command(["container", "rm", "--volumes", info["Id"]])


def run_case(v):
    require(sys.platform == "linux" and os.geteuid() == 0, "upgrade_fixture_linux_root")
    parents = [Path(v[k]) for k in ("source", "target", "rollback")]
    custody = Path(v["custody"])
    require(
        all(
            p.parent == Path("/srv")
            and recovery.resources.re.fullmatch(r"declarai-p37-[0-9a-f]{32}", p.name)
            for p in parents
        )
        and custody.parent == Path("/srv")
        and recovery.resources.re.fullmatch(
            r"declarai-upgrade-[0-9a-f]{32}", custody.name
        ),
        "upgrade_fixture_scope",
    )
    plans = [p / "plan" for p in parents]
    created = []
    phase = "upgrade_source_installation"
    try:
        custody.mkdir(mode=0o700)
        created.append(custody)
        for key, parent, plan in zip(("source", "target", "rollback"), parents, plans):
            parent.mkdir(mode=0o700)
            created.append(parent)
            plan.mkdir(mode=0o700)
            for name, raw in v[key + "_files"].items():
                (plan / name).write_text(raw)
        scenario = Scenario(custody)
        source_result = q.source_fixture.host_case(
            plans[0], v["source_sha"], parents[0], recovery=scenario
        )
        source_history = {
            p.relative_to(parents[0]).as_posix(): recovery.digest(p.read_bytes())
            for p in parents[0].rglob("*")
            if p.is_file()
        }
        phase = "upgrade_target_initialization"
        target, _, _ = q.prepare_empty(
            plans[1], v["target_sha"], parents[1], initialize_schema=False
        )
        phase = "upgrade_interrupted_migration_and_adoption"
        forward, forward_replay = transition(
            scenario,
            plans[0],
            v["source_sha"],
            plans[1],
            v["target_sha"],
            parents[1],
            scenario.archive,
            scenario.backup,
            faults=True,
        )
        adopted = adopter.adoption(plans[1], v["target_sha"], parents[1] / "server.crt")
        session = scenario.login(target, parents[1])
        api = adopted["services"]["api"]["container_id"]
        scenario.verify_history(session, api)
        post_use = scenario.score(session)
        post_evidence = q.boundary(api, "evidence", ids=[post_use["id"]])
        require(forward_replay()["reused"] is True, "upgrade_post_use_replay")
        phase = "upgrade_current_data_backup"
        stop_application(plans[1], v["target_sha"], adopted)
        current_archive = custody / "current.aesgcm"
        current_backup = recovery.backup(
            plans[1], v["target_sha"], scenario.key, current_archive
        )
        phase = "upgrade_rollback_current_data"
        rollback, _, _ = q.prepare_empty(
            plans[2], v["rollback_sha"], parents[2], initialize_schema=False
        )
        backward, backward_replay = transition(
            scenario,
            plans[1],
            v["target_sha"],
            plans[2],
            v["rollback_sha"],
            parents[2],
            current_archive,
            current_backup,
        )
        restored = adopter.adoption(
            plans[2], v["rollback_sha"], parents[2] / "server.crt"
        )
        session = scenario.login(rollback, parents[2])
        api = restored["services"]["api"]["container_id"]
        scenario.verify_history(session, api)
        require(
            session.data("GET", f"/api/jobs/{post_use['id']}/")["result"]
            == post_use["result"]
            and q.boundary(api, "evidence", ids=[post_use["id"]]) == post_evidence,
            "upgrade_post_use_rollback_history",
        )
        scenario.score(session)
        require(backward_replay()["reused"] is True, "upgrade_rollback_replay")
        require(
            source_history
            == {
                p.relative_to(parents[0]).as_posix(): recovery.digest(p.read_bytes())
                for p in parents[0].rglob("*")
                if p.is_file()
            },
            "upgrade_source_history_changed",
        )
        require(
            forward["direction"] == "upgrade" and backward["direction"] == "rollback",
            "upgrade_directions",
        )
        return {
            "schema": "private_installed_upgrade_v1",
            "source_installation_id": scenario.source_id,
            "target_installation_id": target["request"]["installation_id"],
            "rollback_installation_id": rollback["request"]["installation_id"],
            "source_images": startup.checker.verify(plans[0], v["source_sha"])[
                "images"
            ],
            "target_images": target["images"],
            "source_profile": source_result["installation_profile"],
            "original_source_controller_assertions": "passed",
            "actual_schema_migration": "execution_jobs/0004_project_history_index",
            "both_directions": "passed",
            "source_history": "preserved",
            "classification_regression_export_score_bytes": "passed",
            "account_project_authority": "passed",
            "all_application_rows_and_sequences": "preserved",
            "catalog_delta_exact_reviewed_index_only": "passed",
            "post_upgrade_work_after_rollback": "preserved",
            "migration_transaction_fault": "rolled_back",
            "lost_commit_ack": "resumed",
            "lost_publication_ack": "resumed",
            "pending_transition_adoption": "refused",
            "stale_plan": "refused_before_mutation",
            "post_use_transition_replays": "read_only",
            "forward_plan_sha256": forward["plan_sha256"],
            "rollback_plan_sha256": backward["plan_sha256"],
            "source_reconstruction": "exact_previous_source_on_current_locked_dependencies",
            "customer_accepted": False,
            "release_qualified": False,
            "customer_RPO_RTO_qualified": False,
            "operator_key_custody_qualified": False,
            "general_schema_changes_qualified": False,
        }
    except BaseException as error:
        print(
            json.dumps(q.failure_diagnostic(phase, error)), file=sys.stderr, flush=True
        )
        raise
    finally:
        for key, plan in zip(("source", "target", "rollback"), plans):
            if plan.exists():
                q.cleanup(plan, v[key + "_sha"])
        for path in reversed(created):
            if path.exists():
                shutil.rmtree(path)


def qualify(directory, expected, reports):
    reports = reports.resolve()
    require(reports.is_relative_to(ROOT / "test-reports"), "upgrade_reports_scope")
    with tempfile.TemporaryDirectory(prefix="declarai-upgrade-plan-") as temp:
        plan = Path(temp)
        for name in recovery.checker.planner.FILES | {"manifest.json"}:
            (plan / name).write_bytes(
                (reports / ("installation-plan-" + name)).read_bytes()
            )
        pin = recovery.digest((plan / "manifest.json").read_bytes())
        value = startup.checker.verify(plan, pin)
        require(
            value["request"]["root"] == "/srv/declarai/qualification"
            and value["request"]["installation_id"] == "qualification",
            "upgrade_template",
        )
        with reference_plan(directory, expected, value["images"]["api"]) as (
            old_plan,
            old_pin,
            old_image,
        ):
            payload = {
                "scripts": str(ROOT / "scripts"),
                "custody": "/srv/declarai-upgrade-" + uuid.uuid4().hex,
            }
            for key, template, template_pin in (
                ("source", old_plan, old_pin),
                ("target", plan, pin),
                ("rollback", old_plan, old_pin),
            ):
                identifier = uuid.uuid4().hex
                files, digest = q.fixture_plan(template, template_pin, identifier)
                payload.update(
                    {
                        key: "/srv/declarai-p37-" + identifier,
                        key + "_files": {k: raw.decode() for k, raw in files.items()},
                        key + "_sha": digest,
                    }
                )
            code = "import json,sys;v=json.load(sys.stdin);sys.path.insert(0,v['scripts']);from qualify_private_installation_upgrade import run_case;print(json.dumps(run_case(v)))"
            result = subprocess.run(
                ["sudo", "-n", sys.executable, "-c", code],
                input=recovery.encoded(payload),
                capture_output=True,
                timeout=600,
                check=False,
            )
            if result.returncode:
                (reports / "installed-upgrade-failed.log").write_bytes(result.stderr)
                require(False, "upgrade_fixture_failed")
            record = json.loads(result.stdout)
            require(
                record["source_images"]["api"] == old_image
                and record["target_images"] == value["images"],
                "upgrade_report_images",
            )
            profile = record["source_profile"]
            require(
                profile["architecture"]
                == {"arm64": "aarch64", "amd64": "x86_64"}[
                    value["manifest"]["architecture"]
                ]
                and profile["cpu_count"] == 4
                and 14 * 1024**3 <= profile["observed_memory_bytes"] <= 17 * 1024**3
                and profile["os_release"]["ID"] == "ubuntu"
                and profile["os_release"]["VERSION_ID"] == "24.04",
                "upgrade_reference_profile",
            )
            record.update(
                owned_roots_and_resources_removed=True,
                synthetic_installed_upgrade_qualified=True,
            )
            (reports / "installed-upgrade.json").write_bytes(recovery.encoded(record))
            return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-set", type=Path, required=True)
    parser.add_argument("--expected-image-set-sha256", required=True)
    parser.add_argument(
        "--reports", type=Path, default=ROOT / "test-reports/postgresql"
    )
    args = parser.parse_args()
    print(
        json.dumps(
            qualify(args.image_set, args.expected_image_set_sha256, args.reports)
        )
    )
