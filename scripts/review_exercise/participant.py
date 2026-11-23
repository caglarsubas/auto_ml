"""Local participant launcher. Account passwords stay in memory. No review action has a default."""

import getpass
import json
import math
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone

import requests
import hashlib


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class ExercisePaused(RuntimeError):
    """Participant-facing message safe to display after stopping the exercise."""


def load(path):
    return json.loads(path.read_bytes())


def save(path, value):
    raw = (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()
    tmp = path.with_name("." + uuid.uuid4().hex)
    with tmp.open("xb") as stream:
        stream.write(raw)
    os.replace(tmp, path)


def verify(flag, reason):
    if not flag:
        raise ExercisePaused(reason)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def choose(prompt, options):
    while True:
        print(prompt)
        for k, v in options.items():
            print(f"  {k}  {v}")
        key = input("Choice: ").strip().lower()
        if key in options:
            return key


def note(prompt, limit=2000):
    while True:
        value = input(prompt + "\n> ").strip()
        if 0 < len(value) <= limit:
            return value
        print(f"Enter between 1 and {limit} characters.")


def pause(prompt):
    if (
        choose(
            prompt,
            {"y": "Proceed with this exact step", "p": "Pause and keep my place"},
        )
        == "p"
    ):
        raise SystemExit(0)


def login(site, cfg, scope):
    user = scope["reviewer_username"]
    print("D09 independent review • two synthetic cases • no production use")
    print("Sign in with a fresh exercise-only passphrase. Setup and computing are handled for you.")
    record = site.root / "human-account.json"
    identifier = site.root / "human-enrollment-id"
    if not identifier.exists():
        identifier.write_text(str(uuid.uuid4()))
    if not record.exists():
        print("Choose a fresh passphrase with at least 16 characters and eight distinct characters.")
        while True:
            pw = getpass.getpass("New exercise passphrase (hidden): ")
            if not 16 <= len(pw) <= 4096 or len(set(pw)) < 8 or any(ord(char) < 32 or ord(char) == 127 for char in pw):
                print("Use at least 16 characters with eight distinct characters and no control characters.")
                continue
            if pw != getpass.getpass("Confirm (hidden): "):
                print("The two entries differed. Try again.")
                continue
            data = {
                "password": pw,
                "username": user,
                "project": cfg["project_id"],
                "request": identifier.read_text().strip(),
            }
            try:
                result = subprocess.run(
                    site.enrollment_command, input=json.dumps(data), capture_output=True, text=True, timeout=60
                )
            except subprocess.TimeoutExpired:
                raise ExercisePaused(
                    "Exercise account setup timed out. Reopen the launcher and use the same exercise passphrase."
                ) from None
            finally:
                del data
            if result.returncode:
                if result.stderr.rstrip().splitlines()[-1:] == ["enrollment_password_policy_failed"]:
                    print("The account rejected that passphrase. Choose a different exercise passphrase.")
                    continue
                raise ExercisePaused("Exercise account setup returned an error. Contact the exercise operator.")
            save(record, json.loads(result.stdout))
            break
    else:
        pw = getpass.getpass("Exercise passphrase (hidden): ")
    session = requests.Session()
    session.trust_env = False
    session.verify = str(site.root / "tls.crt")
    session.api_url = site.api_url
    r = session.get(session.api_url + "auth/session/", timeout=15)
    r.raise_for_status()
    session.headers["X-CSRFToken"] = r.json()["csrf_token"]
    r = session.post(
        session.api_url + "auth/login/",
        json={"username": user, "password": pw},
        timeout=20,
    )
    del pw
    verify(r.ok, "Sign-in failed. No review decision was submitted.")
    response = r.json()
    session.headers["X-CSRFToken"] = response["csrf_token"]
    verify(
        response["user"]["username"] == user,
        "The signed-in account differs from the assigned reviewer.",
    )
    return session


def call(s, project, method, path, **kwargs):
    query = {"project_id": project, **kwargs.pop("params", {})}
    resp = s.request(method, s.api_url + path, params=query, timeout=30, **kwargs)
    if not resp.ok:
        raise ExercisePaused(f"Governed request returned {resp.status_code} at {path}. Contact the exercise operator.")
    return resp


def study_log(directory, event, **data):
    with (directory / "participant-events.jsonl").open("a") as f:
        f.write(json.dumps({"time_utc": stamp(), "event": event, **data}, ensure_ascii=False) + "\n")


def fresh_body(directory, name, body):
    """Reuse identical bytes after an uncertain write; never resubmit another choice silently."""
    loc = directory / (name + "-request.json")
    if loc.exists():
        old = load(loc)
        verify(
            old == body,
            "The saved request differs. Pause for the operator to reconcile its receipt.",
        )
    else:
        save(loc, body)
    return body


def accept_and_seal(site, s, project, directory, task, ids):
    proposal = load(directory / "proposal.json")
    path = "native-adoptions/" + proposal["id"] + "/"
    ad = call(s, project, "GET", path).json()
    verify(
        ad["proposal_sha256"] == proposal["proposal_sha256"] and ad["project_id"] == project,
        "Proposal binding changed.",
    )
    opts = ad["proposal"]
    contract = opts["prediction_contract"]
    print("\n" + task.upper() + " • protected assessment only")
    print(
        "Candidate proposal:",
        ad["proposal_sha256"],
        "\nTraining receipt:",
        opts["training_result_sha256"],
    )
    print(
        "Predictors:",
        ", ".join(opts["features"]),
        "• 80 development rows • two random folds",
    )
    print(
        "Target:",
        contract["target_column"],
        "• task:",
        contract["task"],
        "• positive class:",
        contract.get("positive_class") or "not applicable",
    )
    print(
        "Population:",
        contract["population"],
        "• prediction horizon:",
        contract["prediction_horizon"],
    )
    print(
        "Outcome meaning:",
        contract["target_contract"].get("event_definition"),
        "• maturity:",
        contract["target_contract"].get("label_maturity"),
    )
    print(
        "Selection metric:",
        opts["metric"]["primary_metric"],
        "• feature timing:",
        contract["feature_availability"].get("default", "see full declaration"),
    )
    print(
        "Your private candidate file contains the full declaration:",
        directory / "proposal.json",
    )
    print("Developer rationale:", opts["rationale"])
    if ad["state"] == "proposed":
        req = directory / "adoption-request.json"
        if req.exists():
            body = load(req)
            print("Your saved rationale:", body["rationale"])
            pause("Resume your previous exact assessment-only authorization?")
        else:
            action = choose(
                "Your candidate decision",
                {
                    "a": "Accept this candidate for the protected synthetic assessment",
                    "h": "Withhold and record my reason",
                    "p": "Pause",
                },
            )
            if action == "p":
                raise SystemExit(0)
            if action == "h":
                reason = note("What needs attention before this candidate can be assessed?")
                study_log(directory, "candidate_withheld", reason=reason)
                raise SystemExit(0)
            body = fresh_body(
                directory,
                "adoption",
                {
                    "request_id": ids["adoption"],
                    "expected_revision": ad["revision"],
                    "proposal_sha256": ad["proposal_sha256"],
                    "action": "approve",
                    "rationale": note("Why do you accept this exact candidate for assessment?"),
                },
            )
        ad = call(s, project, "POST", path, json=body).json()
    verify(
        ad["state"] == "accepted" and ad["usable"] is True,
        "The candidate lacks a current usable assessment-only approval.",
    )
    save(directory / "accepted-snapshot.json", ad)
    if not ad["protected_inputs"]:
        print(
            "Reserved outcomes: 60 synthetic rows with complete fixture follow-up, separate from the 80 development rows. The date represents the synthetic observation clock, 2026-10-21 UTC. Random development folds support exploratory assessment."
        )
        print("Reserved input SHA-256:", site.expected[task][1])
        req = directory / "seal-request.json"
        if req.exists():
            body = load(req)
            print("Your saved population/maturity rationale:", body["rationale"])
            pause("Resubmit your identical sealing request?")
        else:
            pause("Can you attest this synthetic population and maturity and authorize sealing the displayed input?")
            body = fresh_body(
                directory,
                "seal",
                {
                    "request_id": ids["seal"],
                    "proposal_sha256": ad["proposal_sha256"],
                    "rationale": note("Record your population and maturity rationale."),
                    "assessment_as_of": "2026-10-21T00:00:00Z",
                    "population_and_maturity_attested": "true",
                },
            )
        ad = call(
            s,
            project,
            "POST",
            path + "protected-inputs/",
            data=body,
            files={
                "file": (
                    "synthetic-assessment.csv",
                    site.payload(task, "outcomes"),
                    "text/csv",
                )
            },
        ).json()
    verify(len(ad["protected_inputs"]) == 1, "Expected exactly one sealed input.")
    sealed = ad["protected_inputs"][0]
    verify(
        sealed["specification"]["input_sha256"] == site.expected[task][1],
        "Sealed input binding changed.",
    )
    return ad, sealed["id"]


def assess(site, s, project, directory, ad, protected_id, task, ids):
    plan = call(
        s,
        project,
        "POST",
        "native-protected-inputs/" + protected_id + "/preview/",
        json={},
    ).json()
    body = {
        "request_id": ids["assessment"],
        "kind": plan["kind"],
        "protected_input_id": protected_id,
        "assessment_sha256": plan["assessment_sha256"],
    }
    if not (directory / "assessment-request.json").exists():
        print("Frozen assessment SHA-256:", plan["assessment_sha256"])
        pause("Authorize computing this exact exploratory assessment?")
    else:
        verify(
            load(directory / "assessment-request.json") == body,
            "The saved assessment scope changed.",
        )
    fresh_body(directory, "assessment", body)
    job = call(s, project, "POST", f"jobs/datasets/{ad['file_id']}/", json=body).json()
    started = time.monotonic()
    while job["state"] in {"queued", "running", "cancel_requested"} and time.monotonic() - started < 180:
        time.sleep(1)
        job = call(s, project, "GET", f"jobs/{job['id']}/").json()
    study_log(directory, "assessment_wait", wait_seconds=round(time.monotonic() - started, 3))
    verify(
        job["state"] == "succeeded",
        "The job did not succeed. Preserve its receipt for the operator.",
    )
    save(directory / "assessment-receipt.json", job)
    response = call(
        s,
        project,
        "GET",
        f"jobs/{job['id']}/reproduction/",
        params={"sha256": job["result_sha256"]},
    )
    raw = response.content
    manifest_hash = sha(raw)
    verify(
        manifest_hash == response.headers.get("X-Declarai-Export-Sha256"),
        "Export digest mismatch.",
    )
    approved = directory / "approved"
    approved.mkdir(mode=0o700, exist_ok=True)
    triplet = {
        "reproduction-manifest.json": raw,
        "reproduction-development.csv": site.payload(task, "development"),
        "reproduction-outcomes.csv": site.payload(task, "outcomes"),
    }
    for fname, content in triplet.items():
        dest = approved / fname
        if dest.exists():
            verify(dest.read_bytes() == content, "The previously staged handoff changed.")
        else:
            dest.write_bytes(content)
    m = json.loads(raw)
    res = m["assessment"]["result"]
    train = m["training"]
    wanted = site.expected[task]
    verify(
        (
            train["specification"]["training"]["source"]["sha256"],
            m["protected_input"]["specification"]["input_sha256"],
            train["fit"]["model_sha256"],
            res["scores_sha256"],
        )
        == wanted,
        "An input, fitted model or score digest differs from the original qualification. Contact the operator.",
    )
    verify(
        m["project_id"] == project
        and m["adoption"]["id"] == ad["id"]
        and m["assessment"]["job_id"] == job["id"]
        and m["assessment"]["result_sha256"] == job["result_sha256"],
        "Mismatch in the signed handoff identities.",
    )
    verify(
        res["n_assessed"] == 60 and not res["confirmatory"] and not res["production_use_approved"],
        "The assessed population or evidence scope changed.",
    )
    print(
        "Assessment outcome:",
        res["metric"]["primary_metric"],
        res["primary_value"],
        "•",
        res["evidence_status"],
        "•",
        res["n_assessed"],
        "rows",
    )
    print(
        "Development split and preprocessing: inspect training/specification and training/fit in",
        approved / "reproduction-manifest.json",
    )
    checks = res["population_checks"]
    print(
        "Assessment design:",
        checks["strategy"],
        "• temporal ordering checked:",
        checks["chronology_checked"],
        "• entity separation checked:",
        checks["entity_separation_checked"],
    )
    return {
        "manifest_sha256": manifest_hash,
        "assessment_job_id": job["id"],
        "assessment_result_sha256": job["result_sha256"],
    }, m


def run_replay(site, directory, task, context, m, image, username):
    """Bind three files only. Keep original report bytes and isolate each execution."""
    expected = site.expected[task]
    binding = {
        **context,
        "development_sha256": expected[0],
        "outcomes_sha256": expected[1],
        "image_id": image,
        "model_sha256": expected[2],
        "scores_sha256": expected[3],
    }
    binding["reviewer_host"] = site.replay_binding(image)
    print("\nIndependent replay for", task)
    print(site.replay_description)
    for k, v in binding.items():
        print(k.replace("_", " "), v)
    attempts = directory / "replays"
    attempts.mkdir(exist_ok=True)
    latest = directory / "successful-replay.json"
    if latest.exists():
        previous = load(latest)
        report = attempts / previous["attempt"] / "reproduction-report.json"
        verify(
            previous["binding"] == binding and sha(report.read_bytes()) == previous["report_file_sha256"],
            "Saved replay binding changed.",
        )
        print("Using your existing successful replay.")
        return load(report)
    pause("Countersign these exact inputs, model, assessment and runtime, and start your clean independent replay?")
    attempt = attempts / uuid.uuid4().hex
    attempt.mkdir()
    save(
        attempt / "authorized.json",
        {"reviewer": username, "at": stamp(), "binding": binding},
    )
    start = time.monotonic()
    digests = {
        "manifest": context["manifest_sha256"],
        "development": expected[0],
        "outcomes": expected[1],
    }
    try:
        status, raw = site.replay(image, directory / "approved", digests)
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
        save(
            attempt / "transport-failure.json",
            {"finished_at": stamp(), "binding": binding, "error": type(exc).__name__},
        )
        raise ExercisePaused(
            "The dedicated clean reviewer host did not return a verified receipt. Your attempt is retained. Please contact the operator."
        ) from None
    elapsed = time.monotonic() - start
    receipt = {
        "exit_code": status,
        "completed_at": stamp(),
        "wait_seconds": round(elapsed, 3),
        "report_file_sha256": sha(raw) if raw else None,
        "binding": binding,
        "attempt": attempt.name,
    }
    save(attempt / "execution.json", receipt)
    study_log(
        directory,
        "clean_replay",
        exit_code=status,
        wait_seconds=receipt["wait_seconds"],
    )
    if raw is not None:
        (attempt / "reproduction-report.json").write_bytes(raw)
    verify(
        status == 0 and raw is not None,
        "Clean replay failed. The attempt was preserved. Ask the operator to review it.",
    )
    rep = json.loads(raw)
    result = m["assessment"]["result"]
    must = {
        "schema_version": 1,
        "scope": "native_refit_assessment_reproduction_v1",
        "status": "passed",
        "task": task,
        "manifest_sha256": context["manifest_sha256"],
        "training_result_sha256": m["training"]["result_sha256"],
        "assessment_result_sha256": context["assessment_result_sha256"],
        "development_sha256": expected[0],
        "outcomes_sha256": expected[1],
        "model_sha256": expected[2],
        "scores_sha256": expected[3],
        "candidate_export_sha256": result["candidate_export_sha256"],
        "outcome_access_id": result["outcome_access_id"],
        "n_assessed": 60,
        "comparison": "exact_canonical_result_and_scores_sha256",
        "model_refit_reproduced": True,
        "assessment_reproduced": True,
        "confirmation_granted": False,
        "review_approved": False,
        "production_use_approved": False,
    }
    verify(
        all(rep.get(k) == v and type(rep.get(k)) is type(v) for k, v in must.items()),
        "Reproduction report differs from the countersigned case.",
    )
    save(latest, receipt)
    print("Exact model, assessment and ordered scores reproduced on 60 rows. Your technical decision is still open.")
    return rep


def retain_decision(directory, state, raw):
    decision = state["decision"]
    event = next((row for row in state["events"] if row["id"] == decision.get("event_id")), None)
    verify(
        event is not None and len(decision["decision_sha256"]) == 64 and len(event["details"]["report_sha256"]) == 64,
        "Approval or canonical-report digest missing.",
    )
    (directory / ("review-response-" + event["id"] + ".json")).write_bytes(raw)
    save(
        directory / ("receipt-" + event["id"] + ".json"),
        {
            "decision": decision,
            "report_sha256": event["details"]["report_sha256"],
            "event": event,
            "snapshot_file_sha256": sha(raw),
        },
    )


def disposition(s, project, directory, ad, context, report, ids):
    case = call(
        s,
        project,
        "POST",
        f"reviews/datasets/{ad['file_id']}/",
        json={"request_id": ids["review"], **context},
    ).json()
    path = f"reviews/{case['id']}/"
    response = call(s, project, "GET", path)
    state = response.json()
    save(directory / "review-snapshot.json", state)
    pending = directory / "pending-disposition.json"
    if pending.exists():
        original = load(pending)
        recorded = next(
            (row for row in state["events"] if row["id"] == original["request_id"]),
            None,
        )
        if recorded is not None:
            verify(
                recorded["event_type"] == original["event_type"] and recorded["text"] == original["text"],
                "A recorded decision conflicts with the local request.",
            )
            os.replace(pending, directory / ("disposition-" + original["request_id"] + ".json"))
    print("Current technical decision:", state["decision"]["status"])
    if state["decision"]["status"] == "approved":
        retain_decision(directory, state, response.content)
        return
    action = choose(
        "What does the evidence justify?",
        {
            "a": "Approve this exact technical review",
            "f": "Record a finding and leave the review open",
            "p": "Pause without a decision",
        },
    )
    if action == "p":
        raise SystemExit(0)
    event_path = directory / "pending-disposition.json"
    if event_path.exists():
        event = load(event_path)
        verify(
            event["expected_revision"] == state["revision"],
            "The previous review write needs reconciliation against its receipt.",
        )
        print(
            "A previous decision is awaiting confirmation:",
            event["event_type"],
            event["text"],
        )
        pause("Resume the identical recorded request?")
    else:
        event = {
            "request_id": str(uuid.uuid4()),
            "expected_revision": state["revision"],
        }
        if action == "a":
            event.update(event_type="approve", report=report)
        else:
            severity = choose(
                "Finding severity",
                {k: k for k in ["observation", "minor", "major", "critical"]},
            )
            event.update(event_type="finding", severity=severity)
        event["text"] = note(
            "Record your own finding or disposition, including any limitation you consider material.",
            10000,
        )
        print("Your " + event["event_type"] + ":", event["text"])
        pause("Submit this decision under your named review account?")
        save(event_path, event)
    updated = call(s, project, "POST", path, json=event).json()
    response = call(s, project, "GET", path)
    state = response.json()
    verify(
        updated["id"] == state["id"] and any(e["id"] == event["request_id"] for e in state["events"]),
        "Review event receipt unavailable.",
    )
    save(directory / "review-snapshot.json", state)
    os.replace(event_path, directory / ("disposition-" + event["request_id"] + ".json"))
    if event["event_type"] == "approve":
        verify(state["review_approved"] is True, "The approval is no longer current.")
        retain_decision(directory, state, response.content)
    study_log(
        directory,
        "technical_disposition",
        status=state["decision"]["status"],
        revision=state["revision"],
    )
    print(
        "Saved technical review:",
        state["decision"]["status"],
        "revision",
        state["revision"],
    )


def main(site):
    os.umask(0o077)
    verify(
        sys.stdin.isatty(),
        "Open Start Review.command personally in Terminal to enter your own decisions.",
    )
    scope = load(site.root / "scope.json")
    cfg = load(site.root / "project.json")
    image = (site.root / "runtime-id").read_text().strip()
    site.verify_runtime(image)
    s = login(site, cfg, scope)
    project = cfg["project_id"]
    study_log(site.root, "participant_session_started")
    try:
        for task in ("classification", "regression"):
            d = site.root / task
            ids = load(d / "request-ids.json")
            ad, sealed = accept_and_seal(site, s, project, d, task, ids)
            ctx, m = assess(site, s, project, d, ad, sealed, task, ids)
            print(
                "Model choice:",
                m["training"]["fit"]["selection_rule"],
                "• selected depth",
                m["training"]["fit"]["selected_max_depth"],
            )
            print("Evidence limitation:", m["assessment"]["result"]["limitation"])
            rep = run_replay(site, d, task, ctx, m, image, scope["reviewer_username"])
            disposition(s, project, d, ad, ctx, rep, ids)
        print("\nBoth case records are available for your exercise-level decision.")
        state = choose(
            "As scope owner, does the evidence satisfy the synthetic exercise?",
            {
                "a": "Accept the exercise",
                "h": "Withhold acceptance",
                "p": "Leave the decision pending",
            },
        )
        if state != "p":
            why = note("Record the evidence and limitations behind your exercise decision.")
            receipt = {
                "owner": scope["reviewer_username"],
                "time_utc": stamp(),
                "decision": {"a": "accepted", "h": "withheld"}[state],
                "reason": why,
                "cases": {},
            }
            for task in ("classification", "regression"):
                p = site.root / task
                receipt["cases"][task] = {
                    "binding": load(p / "successful-replay.json"),
                    "review_state": load(p / "review-snapshot.json")["decision"],
                    "review_snapshot_sha256": sha((p / "review-snapshot.json").read_bytes()),
                }
            save(site.root / ("owner-decision-" + uuid.uuid4().hex + ".json"), receipt)
        if (
            choose(
                "Add an observation on the reviewer experience?",
                {"m": "Record measures and friction", "s": "Leave unmeasured for now"},
            )
            == "m"
        ):
            measures = {
                k: None
                for k in (
                    "developer_minutes",
                    "reviewer_minutes",
                    "wait_minutes",
                    "review_iterations",
                    "help_requests",
                    "validation_defects",
                )
            }
            for key, label, kind in [
                (
                    "reviewer_minutes",
                    "Your active review minutes, excluding compute or breaks",
                    float,
                ),
                ("wait_minutes", "Your total waiting minutes", float),
                ("review_iterations", "Formal returns for revision", int),
                ("help_requests", "Explicit requests for help", int),
                (
                    "validation_defects",
                    "Distinct independently verified validation defects",
                    int,
                ),
            ]:
                while True:
                    v = input(label + " (Enter if unknown): ").strip()
                    if not v:
                        break
                    try:
                        val = kind(v)
                        if val < 0 or not math.isfinite(val):
                            raise ValueError
                    except ValueError:
                        continue
                    measures[key] = val
                    break
            save(
                site.root / ("reviewer-observation-" + uuid.uuid4().hex + ".json"),
                {
                    "observed_at": stamp(),
                    "scope": "Independent exercise",
                    "method": "Guided",
                    "measures": measures,
                    "participant": scope["reviewer_username"],
                    "finding": note("Which step helped or slowed the review, and why?"),
                },
            )
        print("Your records are saved privately. You can close this window.")
    finally:
        study_log(site.root, "participant_session_ended")
        try:
            s.post(s.api_url + "auth/logout/", timeout=8)
        except requests.RequestException:
            pass
        s.close()


if __name__ == "__main__":
    try:
        from review_installation import site

        main(site)
    except ExercisePaused as error:
        print("Exercise paused.", error)
        sys.exit(1)
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        RuntimeError,
        subprocess.SubprocessError,
        requests.RequestException,
    ):
        print("Exercise paused. Contact the exercise operator.")
        sys.exit(1)
