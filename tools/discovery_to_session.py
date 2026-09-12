#!/usr/bin/env python3
"""
Turn an accepted discovery run record into a session file for tools/apply_session.py.

    python3 tools/discovery_to_session.py runs/DISC-021-2026-09-03-01.yaml --accepted-by "Name"
    python3 tools/discovery_to_session.py runs/DISC-021-2026-09-03-01.yaml --accepted-by "Name" --steps 2,4
    python3 tools/discovery_to_session.py runs/DISC-021-2026-09-03-01.yaml --accepted-by "Name" --out session.json

This is the bridge, and it is the only thing it is. It reads the proposals an agent
made, keeps the ones a person accepts, and writes them in the session_format the
viewer already produces, so the one tool that edits scenario YAML (apply_session.py,
ruamel round-tripping, comments intact) does the writing. It never touches a record
itself, and it never calls apply_session for you: the last line of its output is the
command to run next, and running it is a deliberate act.

WHAT LANDS, AND HOW IT IS MARKED. Every score this bridge emits carries
score_provenance: agent-proposed. That marker rides into the record and stays there
until a person edits it to human-session, and while it is there the row is listed
in the coverage rollup but counted in no average. The last commit before discovery
mode existed stripped invented scores because they made the library read as measured
when nothing had been measured. A machine proposal that lands looking like a human
measurement is the same failure, and the marker is what prevents it.

WHAT IS NOT CARRIED. The agent does not know who owns a system, so owner is never
set. No backlog ticket is invented. The proposal rationale goes into the row's notes
with the run id in front, so the reasoning survives next to the number it justifies.

SOURCE AND EVIDENCE DEPEND ON THE PIPELINE. In a mirrored pipeline the artifact
landed in the estate's real collector, so observed_source is the estate's source and
the artifact pointers are evidence for the row; both are carried. In a scratch or
no-collection pipeline the artifact landed in a lab stand-in, and writing the
stand-in's name over the record's claim about the estate would replace a human
statement about our systems with a machine statement about a lab. There the source
and the pointers go into notes, labeled as the lab's, and the record's own source
and evidence fields are left alone.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys

try:
    import yaml
    from jsonschema import Draft202012Validator
except ImportError:
    sys.exit("pip install pyyaml jsonschema")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
# The validator is the one definition of a legal discovery record. Refusing to bridge
# an invalid one here means the bridge cannot be the path by which a bad record
# reaches the library.
from validate import DISC_SCHEMA, derive_coverage, load_scenario_steps, \
    validate_discovery_run_file

ROOT = pathlib.Path(__file__).resolve().parent.parent


def proposals_in(run: dict) -> list[dict]:
    """The observations that carry a proposal. An unscoreable or unexecuted step never
    does, and the validator has already refused a record where one tries to."""
    out = []
    for o in run.get("observations", []):
        if o.get("proposed_visibility") is None or o.get("proposed_detection") is None:
            continue
        out.append(o)
    return out


def row_for(o: dict, run_id: str, pipeline: str) -> dict:
    row = {
        "dettect": {"visibility": int(o["proposed_visibility"]),
                    "detection": int(o["proposed_detection"])},
        "score_provenance": "agent-proposed",
    }
    notes = [f"[{run_id}] {o['proposal_rationale'].strip()}"]
    seen = o.get("observed") in ("detected", "logged-only")
    if pipeline == "mirrored":
        if o.get("observed_source"):
            row["source"] = o["observed_source"]
        if seen and o.get("artifacts"):
            row["evidence"] = f"{run_id}: " + "; ".join(o["artifacts"])
    else:
        if o.get("observed_source"):
            notes.append(f"Observed in the {pipeline} lab at: {o['observed_source']}. "
                         "That is the lab's stand-in, not the estate's source, which is "
                         "why the source field above is unchanged.")
        if seen and o.get("artifacts"):
            notes.append("Lab artifacts: " + "; ".join(o["artifacts"]))
    row["notes"] = " ".join(notes)
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=pathlib.Path)
    ap.add_argument("--accepted-by", required=True,
                    help="who is accepting these proposals into the record, by name")
    ap.add_argument("--steps", help="comma separated steps to accept; default is every "
                                    "step that carries a proposal")
    ap.add_argument("--out", type=pathlib.Path,
                    help="where to write the session file (default: next to the run)")
    args = ap.parse_args()

    if not args.run.exists():
        sys.exit(f"not found: {args.run}")

    # Validate first. The same function validate.py runs, so a record this bridge
    # accepts is a record ./liszt validate accepts, and nothing else.
    validator = Draft202012Validator(json.loads(DISC_SCHEMA.read_text()))
    findings = validate_discovery_run_file(args.run, validator, load_scenario_steps())
    if findings.errors:
        print(f"REFUSING TO BRIDGE {args.run.name}: the record does not validate.\n")
        for where, msg in findings.errors:
            print(f"  ERROR  {where}: {msg}")
        return 1

    run = yaml.safe_load(args.run.read_text(encoding="utf-8"))
    run_id, sid = run["run_id"], run["scenario"]
    pipeline = run["environment"]["telemetry_pipeline"]

    wanted = None
    if args.steps:
        wanted = {int(s) for s in args.steps.split(",") if s.strip()}

    # A row a person has already scored is a measurement. Discovery proposes first
    # numbers; it does not argue with existing ones. That is the scoring path's job,
    # and it does it with a sealed prediction. Refuse those steps here, so the bridge
    # cannot be the way a human number gets replaced by a machine one.
    scen = next(iter(sorted((ROOT / "scenarios").glob(f"{sid}-*.yaml"))), None)
    human_scored: set[int] = set()
    if scen:
        srec = yaml.safe_load(scen.read_text(encoding="utf-8")) or {}
        for r in srec.get("telemetry", []):
            if r.get("kind", "attack-step") != "attack-step":
                continue
            if derive_coverage(r.get("dettect")) is not None and \
                    r.get("score_provenance") != "agent-proposed":
                human_scored.add(int(r["step"]))

    accepted, skipped = [], []
    for o in proposals_in(run):
        if wanted is not None and o["step"] not in wanted:
            skipped.append(o["step"])
            continue
        if o["step"] in human_scored:
            print(f"  step {o['step']}: the record already carries a person's scores. "
                  "Discovery does not overwrite a measurement; use the scoring path "
                  "(emit_testspec.py, score_run.py) to dispute it. Not accepted.")
            continue
        accepted.append(o)
    if wanted is not None:
        proposed = {o["step"] for o in proposals_in(run)}
        for s in sorted(wanted - proposed):
            print(f"  step {s}: no proposal on this run, nothing to accept")
    if not accepted:
        sys.exit("no proposals accepted, nothing to write")

    today = dt.date.today().isoformat()
    steps_txt = ", ".join(str(o["step"]) for o in accepted)
    session = {
        "session_format": 1,
        "recorded": today,
        "facilitator": f"{args.accepted_by} (accepting discovery run {run_id})",
        "changes": {
            sid: {
                "telemetry": {str(o["step"]): row_for(o, run_id, pipeline) for o in accepted},
                "notes": (f"Discovery run {run_id} proposed scores on steps {steps_txt}, "
                          f"accepted into the record by {args.accepted_by}. They carry "
                          "score_provenance: agent-proposed and count toward nothing until "
                          "a person changes that field to human-session."),
            }
        },
    }

    out = args.out or args.run.with_suffix(".session.json")
    out.write_text(json.dumps(session, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"discovery run {run_id} for scenario {sid}, {pipeline} pipeline")
    if pipeline != "mirrored":
        print("  sources and artifacts go to notes as the lab's; the record's source and "
              "evidence fields are not touched")
    print(f"  {'step':<5}{'observed':<13}{'proposes':<10}{'source'}")
    for o in accepted:
        src = (o.get("observed_source") or "")[:60]
        print(f"  {o['step']:<5}{o['observed']:<13}"
              f"v{o['proposed_visibility']} d{o['proposed_detection']:<5} {src}")
    if skipped:
        print(f"  not accepted: steps {skipped}")
    print(f"\nsession file written: {out}")
    print("\nNothing has been applied. Review the session file, then:")
    print(f"  python3 tools/apply_session.py {out} --dry-run")
    print(f"  python3 tools/apply_session.py {out}")
    print("\nEvery score that lands is marked agent-proposed. It stays out of the coverage "
          "numbers until\nsomeone who has looked at the evidence changes score_provenance "
          "to human-session on that row.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
