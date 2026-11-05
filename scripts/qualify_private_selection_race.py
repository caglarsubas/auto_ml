"""Race two exact installed candidates over HTTPS; own synthetic fixtures only."""

import copy
import hashlib
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from qualify_private_installation_workflow import owned, require


def qualify(session, value, parent, candidates):
    owned(value, parent)
    require(len(candidates) == 2 and candidates[0]["file_id"] == candidates[1]["file_id"]
            and candidates[0]["id"] != candidates[1]["id"], "selection_race_candidates")
    previews = [session.data("GET", f"/api/jobs/{row['id']}/legacy-selection/") for row in candidates]
    previous = previews[0]["expected_projection_sha256"]
    require(previous == previews[1]["expected_projection_sha256"], "selection_race_previous")
    requests = [{"request_id": str(uuid.uuid4()), "result_sha256": row["result_sha256"],
                 "execution_id": preview["candidates"][0]["execution_id"],
                 "expected_projection_sha256": previous} for row, preview in zip(candidates, previews)]
    gate = Barrier(2)

    def select(index):
        # Independent HTTPS connections and cookie containers. The production
        # server supplies the projection/authority fence; the client has none.
        client = copy.copy(session)
        client.cookies = copy.deepcopy(session.cookies)
        authority = client.value["request"]["authority"]
        headers = {"Host": authority, "Origin": "https://" + authority,
                   "X-CSRFToken": client.csrf, "Content-Type": "application/json",
                   "Cookie": "; ".join(k + "=" + v.value for k, v in client.cookies.items())}
        from private_installation_adopt import DeclaredHTTPS

        connection = DeclaredHTTPS(client.value["request"]["bind_ip"], client.port, client.host, client.context)
        try:
            gate.wait(timeout=5)
            connection.request("POST", f"/api/jobs/{candidates[index]['id']}/legacy-selection/",
                               body=json.dumps(requests[index]).encode(), headers=headers)
            response = connection.getresponse()
            raw = response.read(1024**2 + 1)
            require(len(raw) <= 1024**2, "selection_race_response_budget")
            return response.status, json.loads(raw)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(select, range(2)))
    require(sorted(code for code, _ in outcomes) == [200, 409], "selection_race_outcomes")
    winner = next(i for i, (code, _) in enumerate(outcomes) if code == 200)
    loser = 1 - winner
    require(outcomes[loser][1]["error_code"] == "job_legacy_selection_base_changed", "selection_race_stale")
    replay = session.data("POST", f"/api/jobs/{candidates[winner]['id']}/legacy-selection/", requests[winner])
    require(replay["replayed"] and replay["currently_selected"]
            and replay["review_approved"] is replay["production_use_approved"] is False, "selection_race_replay")
    current = session.data("GET", f"/api/modeling/status/{candidates[winner]['file_id']}/?selected=true")
    require(current["execution_id"] == requests[winner]["execution_id"], "selection_race_pointer")
    events = []
    pins = []
    for candidate in candidates:
        raw, _ = session.request("GET", f"/api/jobs/{candidate['id']}/", response_limit=10 * 1024**2)
        row = json.loads(raw)
        require(row["state"] == "succeeded" and row["result_sha256"] == candidate["result_sha256"],
                "selection_race_immutable_result")
        pins.append({"job_id": row["id"], "result_sha256": row["result_sha256"]})
        events += [e for e in row["events"] if e["event_type"] == "legacy_selection_completed"
                   and e["detail"].get("request_id") in {r["request_id"] for r in requests}]
    require(len(events) == 1 and events[0]["detail"]["request_id"] == requests[winner]["request_id"],
            "selection_race_one_attributable_completion")
    return {"schema": "private_installed_selection_race_v1", "installation_id": value["request"]["installation_id"],
            "synthetic_only": True, "independent_https_clients": 2, "simultaneous_start": True,
            "responses": sorted(code for code, _ in outcomes), "attributable_completed_selections": 1,
            "winner_replay": "idempotent", "stale_base": "refused", "immutable_candidates": pins,
            "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "review_approved": False, "production_use_approved": False, "customer_accepted": False}
