#!/usr/bin/env python3
"""
Import an agent run produced by the agentic platform into an immutable run record.

    python3 tools/import_agent_run.py path/to/run.json
    python3 tools/import_agent_run.py path/to/run.json --dry-run     # validate and show, write nothing
    python3 tools/import_agent_run.py path/to/run.json --out runs/   # default

The input is one JSON document per scenario per run, in the shape of
schema/agent-run-import.schema.json: what a single purpose sub-agent observed at each
step, built from the traces it collected, plus who produced it and where the traces live.
The output is one file under runs/, RUN-<id>-<date>-<NN>.yaml in test mode or
DISC-<id>-<date>-<NN>.yaml in discovery mode, validated against its schema before it is
written. Nothing else is written. The scenario record is only ever changed by a person,
through tools/apply_session.py, after the run has been scored (tools/score_run.py) or its
proposals reviewed (tools/discovery_to_session.py).

WHAT THE IMPORTER REFUSES.
  - A document that does not match the import schema.
  - A scenario that does not exist, or a step the scenario does not have.
  - In test mode, a prediction_digest or spec_digest that does not match the files on
    disk. A run bound to a prediction that has since moved cannot be scored honestly, and
    importing it would let that pass unnoticed until the scorer refused.
  - In discovery mode, a spec_digest that does not match specs/DISC-<id>-*/discovery.yaml,
    when one is given.
  - An environment definition that does not exist, or a pipeline mode that disagrees
    with it.

WHAT THE IMPORTER DOES NOT DO. It does not score, it does not propose, it does not touch
a scenario record, and it does not read the traces. Trace and observation ids are carried
as pointers so a person can open them; the evidence stays in the tracing platform.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import pathlib
import sys

try:
    import yaml
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:
    sys.exit("pip install pyyaml jsonschema")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import validate as V  # noqa: E402  the same checks the CI gate runs

ROOT = pathlib.Path(__file__).resolve().parent.parent
IMPORT_SCHEMA = ROOT / "schema" / "agent-run-import.schema.json"


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def fail(msg: str) -> None:
    sys.exit(f"REFUSING TO IMPORT.\n\n  {msg}\n")


def next_run_id(prefix: str, sid: str, date: str, out_dir: pathlib.Path) -> str:
    n = 1
    while (out_dir / f"{prefix}-{sid}-{date}-{n:02d}.yaml").exists():
        n += 1
    return f"{prefix}-{sid}-{date}-{n:02d}"


def find_spec_dir(prefix: str, sid: str) -> pathlib.Path | None:
    hits = sorted((ROOT / "specs").glob(f"{prefix}-{sid}-*/"))
    return hits[0] if hits else None


def artifact_line(a: dict) -> str:
    s = f"{a['kind']}: {a['ref']}"
    if a.get("trace_id"):
        s += f" [trace {a['trace_id']}" + (f" / {a['observation_id']}" if a.get("observation_id") else "") + "]"
    if a.get("sha256"):
        s += f" sha256={a['sha256'][:16]}"
    if a.get("note"):
        s += f" ({a['note']})"
    return s


def build_record(doc: dict, run_id: str, source_sha: str) -> dict:
    mode = doc["mode"]
    started = doc["executed"]["started_at"]
    agent = doc["produced_by"]["agent"]
    env_in = doc["environment"]
    env = {}
    if env_in.get("definition"):
        env["definition"] = dict(env_in["definition"])
    env["telemetry_pipeline"] = env_in["telemetry_pipeline"]
    if env_in.get("targets_used"):
        env["targets_used"] = list(env_in["targets_used"])
    env["teardown_confirmed"] = env_in["teardown_confirmed"]
    deviations = list(env_in.get("deviations") or [])
    if env_in.get("teardown_evidence"):
        deviations.append(f"teardown evidence: {env_in['teardown_evidence']}")
    if deviations:
        env["deviations"] = deviations

    observations = []
    for st in sorted(doc["steps"], key=lambda s: s["step"]):
        o = {"step": st["step"], "executed": st["executed"]}
        if st.get("not_executed_reason"):
            o["not_executed_reason"] = st["not_executed_reason"]
        o["observed"] = st["observed"]
        if st.get("observed_source"):
            o["observed_source"] = st["observed_source"]
        if mode == "discovery":
            if st.get("observed_layer"):
                o["observed_layer"] = list(st["observed_layer"])
            if "out_of_estate" in st:
                o["out_of_estate"] = st["out_of_estate"]
        if "detection_fired" in st:
            o["detection_fired"] = st["detection_fired"]
        if st.get("detection_artifact_observed"):
            o["detection_artifact_observed"] = st["detection_artifact_observed"]
        if "latency_seconds" in st:
            o["latency_seconds"] = st["latency_seconds"]
        arts = st.get("artifacts") or []
        if arts:
            o["artifacts"] = [artifact_line(a) for a in arts]
        if st.get("surprises"):
            o["surprises"] = list(st["surprises"])
        if mode == "discovery":
            for k in ("proposed_visibility", "proposed_detection", "proposal_rationale"):
                if k in st:
                    o[k] = st[k]
        notes = []
        if st.get("started_at") and st.get("ended_at"):
            notes.append(f"executed {st['started_at']} to {st['ended_at']}")
        if st.get("notes"):
            notes.append(st["notes"])
        if notes:
            o["notes"] = ". ".join(notes)
        refs = [{"provider": doc["traces"]["provider"], "trace_id": a["trace_id"],
                 **({"observation_id": a["observation_id"]} if a.get("observation_id") else {})}
                for a in arts if a.get("trace_id")]
        if refs:
            o["trace_refs"] = refs
        observations.append(o)

    rec = {
        "run_version": 1,
        "run_id": run_id,
        "spec_id": doc["spec_id"],
        "scenario": doc["scenario"],
    }
    if mode == "test":
        rec["prediction_digest"] = doc["prediction_digest"]
    if doc.get("spec_digest"):
        rec["spec_digest"] = doc["spec_digest"]
    rec.update({
        "executed": started[:10],
        "executed_by": doc["executed"].get("by")
                       or f"{agent['name']} {agent['version']}, dispatched by orchestrator run "
                          f"{doc['produced_by']['orchestrator_run_id']}",
        "agent": {"adapter": agent.get("adapter", "none recorded"),
                  "build": f"{agent['name']} {agent['version']}",
                  "model": agent.get("model", "none recorded")},
        "environment": env,
        "autonomy_used": doc["autonomy_used"],
        "stop_conditions_triggered": list(doc.get("stop_conditions_triggered") or []),
        "observations": observations,
        "imported_from": {
            "import_version": doc["import_version"],
            "produced_at": doc["produced_at"],
            "orchestrator_run_id": doc["produced_by"]["orchestrator_run_id"],
            "agent": dict(agent),
            "traces": dict(doc["traces"]),
            "source_sha256": source_sha,
        },
    })
    if doc.get("notes"):
        rec["notes"] = doc["notes"]
    return rec


def header(doc: dict, run_id: str, source: pathlib.Path) -> str:
    agent = doc["produced_by"]["agent"]
    return (f"# {run_id}. Imported by tools/import_agent_run.py from {source.name} on "
            f"{datetime.date.today().isoformat()}.\n"
            f"# Produced by {agent['name']} {agent['version']} under orchestrator run "
            f"{doc['produced_by']['orchestrator_run_id']}; traces in "
            f"{doc['traces']['provider']}.\n"
            "# Immutable once committed. A correction is a new run, never an edit. Nothing in\n"
            "# this file has been written to a scenario record; scoring and acceptance are\n"
            "# separate, deliberate steps.\n"
            + (f"# The import document said: {doc['_comment']}\n" if doc.get("_comment") else "")
            + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "runs")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    raw = args.source.read_bytes()
    try:
        doc = json.loads(raw)
    except ValueError as e:
        fail(f"not JSON: {e}")
    schema = json.loads(IMPORT_SCHEMA.read_text())
    errs = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(doc),
                  key=lambda e: list(e.path))
    if errs:
        for e in errs:
            print(f"  {'/'.join(str(p) for p in e.path) or '(root)'}: {e.message}")
        fail("the document does not match schema/agent-run-import.schema.json")

    # The jsonschema format checker only enforces date-time when an extra package is
    # installed, so check the timestamps here rather than trust the environment.
    stamps = [("produced_at", doc["produced_at"]),
              ("executed.started_at", doc["executed"]["started_at"]),
              ("executed.ended_at", doc["executed"]["ended_at"])]
    stamps += [(f"steps[{i}].{k}", st[k]) for i, st in enumerate(doc["steps"])
               for k in ("started_at", "ended_at") if st.get(k)]
    for where, val in stamps:
        try:
            datetime.datetime.fromisoformat(val.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            fail(f"{where} is not an ISO 8601 timestamp: {val!r}")
    if doc["executed"]["ended_at"] < doc["executed"]["started_at"]:
        fail("executed.ended_at is before executed.started_at")

    mode, sid = doc["mode"], doc["scenario"]
    prefix = "RUN" if mode == "test" else "DISC"
    steps = V.load_scenario_steps().get(sid)
    if steps is None:
        fail(f"scenario {sid} does not exist in scenarios/")
    bad = sorted({s["step"] for s in doc["steps"]} - set(steps))
    if bad:
        fail(f"steps {bad} are not in scenario {sid}'s attack path, which has steps {steps}")
    missing = sorted(set(steps) - {s["step"] for s in doc["steps"]})

    spec_dir = find_spec_dir("ST" if mode == "test" else "DISC", sid)
    if mode == "test":
        if spec_dir is None:
            fail(f"no spec under specs/ST-{sid}-*/; a test run needs a sealed prediction to bind to")
        actual_pred = sha256_bytes((spec_dir / "prediction.yaml").read_bytes())
        if actual_pred != doc["prediction_digest"]:
            fail(f"prediction_digest {doc['prediction_digest'][:16]} does not match the prediction "
                 f"on disk ({actual_pred[:16]}). The prediction moved after the run was bound "
                 "to it, or the run cites the wrong one. Resolve it in git before importing.")
        actual_spec = sha256_bytes((spec_dir / "spec.yaml").read_bytes())
        if actual_spec != doc["spec_digest"]:
            fail(f"spec_digest {doc['spec_digest'][:16]} does not match specs/{spec_dir.name}/"
                 f"spec.yaml ({actual_spec[:16]}); the agent ran a different spec")
    elif doc.get("spec_digest"):
        if spec_dir is None:
            fail(f"spec_digest given but no spec under specs/DISC-{sid}-*/")
        actual = sha256_bytes((spec_dir / "discovery.yaml").read_bytes())
        if actual != doc["spec_digest"]:
            fail(f"spec_digest does not match specs/{spec_dir.name}/discovery.yaml")

    ref = doc["environment"].get("definition")
    if ref:
        envs = V.load_environments()
        defn = envs.get((ref["id"], ref["version"]))
        if defn is None:
            fail(f"environment {ref['id']} v{ref['version']} has no record in environments/")
        if defn["telemetry_pipeline"] != doc["environment"]["telemetry_pipeline"]:
            fail(f"pipeline {doc['environment']['telemetry_pipeline']!r} disagrees with "
                 f"{ref['id']} v{ref['version']} ({defn['telemetry_pipeline']!r})")

    date = doc["executed"]["started_at"][:10]
    run_id = next_run_id(prefix, sid, date, args.out)
    rec = build_record(doc, run_id, sha256_bytes(raw))

    schema_path = ROOT / "schema" / ("run-record.schema.json" if mode == "test"
                                     else "discovery-run.schema.json")
    rerrs = sorted(Draft202012Validator(json.loads(schema_path.read_text())).iter_errors(rec),
                   key=lambda e: list(e.path))
    if rerrs:
        for e in rerrs:
            print(f"  {'/'.join(str(p) for p in e.path) or '(root)'}: {e.message}")
        fail(f"the built record does not match {schema_path.name}; this is an importer defect")

    text = header(doc, run_id, args.source) + yaml.safe_dump(
        rec, sort_keys=False, default_flow_style=False, width=100, allow_unicode=True)
    out_path = args.out / f"{run_id}.yaml"

    print(f"  {run_id}  scenario {sid}  {mode} mode  {len(rec['observations'])} step(s)"
          + (f", steps {missing} not addressed" if missing else ""))
    if args.dry_run:
        print("\n--dry-run, nothing written. The record would be:\n")
        print(text)
        return 0
    out_path.write_text(text, encoding="utf-8")
    print(f"  written to {out_path.relative_to(ROOT)}")
    if missing:
        print(f"  NOTE steps {missing} have no observation. Say why in notes before committing.")
    if mode == "test":
        print(f"\nnext: python3 tools/score_run.py {out_path.relative_to(ROOT)}")
    else:
        print(f"\nnext: python3 tools/validate.py {out_path.relative_to(ROOT)}\n"
              f"      python3 tools/discovery_to_session.py {out_path.relative_to(ROOT)} "
              "--accepted-by \"Name\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
