#!/usr/bin/env python3
"""
Emit a discovery specification from a scenario record that has not been scored.

    python3 tools/emit_discovery.py 021
    python3 tools/emit_discovery.py 021 --pipeline mirrored
    python3 tools/emit_discovery.py 021 --org platform-eng
    python3 tools/emit_discovery.py 021 --check          # readiness only, write nothing

Two files land in specs/DISC-<id>-<slug>/ :

    discovery.yaml    the machine readable specification
    discovery.md      the same spec in the spec-driven agent convention, generated

THERE IS NO PREDICTION FILE, AND THAT IS THE POINT. tools/emit_testspec.py asks an
agent to check a claim that already exists, and seals that claim in prediction.yaml
before the run so hindsight cannot rewrite it. Discovery asks an agent to establish
a claim that does not exist yet: go run the scenario, observe what came out, say
which layer it came from, and propose first DeTT&CT numbers for a person to accept
or reject. With nothing predicted there is nothing to seal, and an empty prediction
file would manufacture the appearance of a claim nobody made.

WHAT THE EMITTER REFUSES TO DO. It will not emit from a published record, because a
published record is scored and belongs to the scoring path; from a retired one,
because there is nothing left to learn; from a failure-mode scenario, which has no
adversary to emulate; or from a doomsday record, whose emulation is a separate
decision. It also refuses a record with no framework baseline and a step with no
evidence row, since a proposal needs a row to land in.

WHAT IT SHARES WITH THE SCORING EMITTER. The action sets, the prohibited list, the
stop conditions and the environment builder are imported from emit_testspec.py, not
copied, so the two specs cannot drift on what an agent may do. What is NOT shared is
the observation block: that one encodes claims, and discovery has none.

THE RETURN PATH. The agent's answer is a discovery run record, runs/DISC-<id>-<date>-<NN>.yaml,
validated by schema/discovery-run.schema.json. tools/discovery_to_session.py turns
the proposals a person accepts into a session file, and tools/apply_session.py
writes them into the record with score_provenance: agent-proposed. Nothing on this
path writes itself.
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sys

try:
    import yaml
except ImportError:
    sys.exit("pip install pyyaml")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from emit_testspec import (PROHIBITED, ROOT, SPECS, build_environment, build_procedure,
                           derive_coverage, load_overlay, load_scenario, resolve_rows,
                           sha256_bytes)

SCHEMA_DIR = ROOT / "schema"

# The stop conditions are the scoring emitter's, word for word. They are not exported
# as a constant there, so they are restated here and a test below asserts equality
# against the emitted spec of record, which is the closest thing to sharing them.
STOP_CONDITIONS = [
    "Any interaction with an address or account outside authorization.targets.",
    "Any credential that resolves outside the lab boundary.",
    "Any action not present in this spec's procedure.",
    "Time box expiry, whether or not the procedure has finished.",
    "Loss of the observer's ability to read the telemetry pipeline, since the "
    "run stops producing evidence at that moment.",
]


def layer_vocabulary() -> list[str]:
    """The five layer values, read from the scenario schema so there is one copy."""
    s = json.loads((SCHEMA_DIR / "scenario.schema.json").read_text(encoding="utf-8"))
    return list(s["$defs"]["aiLayer"]["enum"])


def discovery_readiness(rec: dict, rows: dict[int, dict], path: pathlib.Path) -> list[str]:
    """Mechanical gate for discovery. A second door beside emit_testspec.readiness(),
    not a wider one: it drops the two conditions that ask for scores, because
    producing the first scores is what this mode is for, and keeps every condition
    that is about whether an agent should run the scenario at all."""
    blockers = []
    status = rec.get("status")
    if status == "published":
        blockers.append(
            "status is 'published'. A published record is scored, so it has claims to "
            "test; that is the scoring path (tools/emit_testspec.py), not discovery.")
    elif status == "retired":
        blockers.append("status is 'retired'. There is nothing left to learn about a record "
                        "the library has set aside.")
    elif status not in ("draft", "in-review"):
        blockers.append(f"status is '{status}', which discovery does not know how to treat.")

    steps = {s["step"] for s in rec.get("attack_path", [])}
    if not steps:
        blockers.append("no attack path: there is nothing for the agent to reproduce.")
    missing = sorted(steps - set(rows))
    if missing:
        blockers.append(f"attack path steps {missing} have no attack-step evidence row. A "
                        "proposal needs a row to land in; add the row, even empty.")

    fm = rec.get("framework_mapping", {})
    if not fm.get("baseline"):
        blockers.append("no framework_mapping.baseline: the spec would not know which "
                        "pinned vocabulary its technique ids speak.")
    if rec.get("classification", {}).get("mode") == "failure":
        blockers.append(
            "classification.mode is 'failure'. Failure scenarios have no adversary to "
            "emulate; they are tested by fault injection, which this spec does not cover.")
    if rec.get("classification", {}).get("evidence") == "doomsday":
        blockers.append(
            "classification.evidence is 'doomsday'. These records exist to reason about "
            "an attack nobody has run; emulating one is a different decision and needs "
            "its own approval.")
    return blockers


def build_discovery_procedure(rec: dict, rows: dict[int, dict], pipeline: str,
                              vocabulary: list[str]) -> tuple[list, list]:
    """The scoring emitter's procedure with its observation block removed and a report
    block put in its place. The action set, techniques, layer guess, safety seed and
    out-of-scope notes are taken from build_procedure() as they are, so an agent is
    told to do exactly what the scoring path would tell it to do. The observation
    block is dropped rather than adapted: on an unscored row it invents claims (it
    tests coverage against Blind, and None is not Blind), and discovery has no claims
    to make."""
    base, excluded = build_procedure(rec, rows, pipeline)
    procedure = []
    for entry in base:
        n = entry["step"]
        row = rows[n]
        if derive_coverage(row.get("dettect")) is not None and \
                row.get("score_provenance") != "agent-proposed":
            excluded.append({"step": n, "class": "already-scored",
                             "reason": "a person has scored this row. Discovery proposes "
                                       "first numbers and does not argue with existing "
                                       "ones; dispute a score through the scoring path."})
            continue
        report = {
            "artifact_appeared": "detected | logged-only | absent | unscoreable",
            "observed_source": "the system and the index, log, table or topic by name, "
                               "and nothing else",
            "observed_layer": {"one_or_two_of": vocabulary},
            "out_of_estate": "true when the step reaches a third party and the lab used "
                             "a stand-in",
            "alerted": "did anything fire, and what",
            "proposed_visibility": "0..4, with proposal_rationale",
            "proposed_detection": ("-1..5, with proposal_rationale. In a scratch pipeline "
                                   "our detection content is not in the path, so propose "
                                   "-1 and say why." if pipeline != "mirrored" else
                                   "-1..5, with proposal_rationale"),
            "surprises": "anything seen that the record does not mention, including "
                         "sources it does not name",
        }
        procedure.append({
            "step": n,
            "intent": entry["intent"],
            "layer": entry["layer"],
            "techniques": entry["techniques"],
            "actions": entry["actions"],
            "record_claims": {
                # What the record says today, labeled as the hypothesis it is. The
                # agent looks here first and then everywhere else.
                "signal": row.get("signal"),
                "emitted_at": row.get("emitted_at"),
                "source": row.get("source") or None,
                "detection_opportunity": row.get("detection_opportunity"),
                "scored": False,
            },
            "report": report,
            "safety": entry["safety"],
            **({"out_of_scope": entry["out_of_scope"]} if entry.get("out_of_scope") else {}),
        })
    return procedure, excluded


def render_markdown(spec: dict) -> str:
    """GENERATED from discovery.yaml; the yaml is the source of truth."""
    a = spec["authorization"]
    L = []
    L.append(f"# {spec['spec_id']}: {spec.get('scenario_title', '')}".rstrip())
    L.append("")
    L.append(f"> Generated by `{spec['generated_by']}` from scenario `{spec['scenario']}` "
             f"(status `{spec['scenario_status']}`) at baseline `{spec['baseline']}` on "
             f"{spec['generated']}. Do not edit; regenerate.")
    L.append("")
    L.append("## Purpose")
    L.append("")
    L.append("Establish the evidence map for this scenario. Nothing on the record has been "
             "scored, so there is no claim to test and no prediction to seal. The agent "
             "reproduces each step, records what appeared and where, tags which layer it "
             "came from, and proposes DeTT&CT numbers with a written rationale. A person "
             "accepts or rejects each proposal. Until then the numbers count toward nothing.")
    L.append("")
    L.append("## Authorization")
    L.append("")
    L.append(f"- **Autonomy rung**: `{a['autonomy']}`")
    L.append(f"- **Rungs enabled in this deployment**: "
             f"{', '.join(f'`{r}`' for r in a.get('enabled_rungs', []))}")
    L.append(f"- **Time box**: `{a['time_box']}`")
    L.append(f"- **Egress**: `{a['egress']}`")
    L.append(f"- **Teardown required**: `{str(a['teardown_required']).lower()}`")
    L.append("")
    L.append("**Targets.** The agent MUST NOT act on anything not in this list.")
    L.append("")
    if a["targets"]:
        for t in a["targets"]:
            L.append(f"- `{t['id']}` ({t['kind']}): {t['scope_note']}")
    else:
        L.append("- _None assigned yet. With an empty allowlist the run MUST refuse to start._")
    L.append("")
    L.append("**Stop conditions.** Any of these aborts the run immediately and leaves the "
             "environment intact for inspection.")
    L.append("")
    for s in a["stop_conditions"]:
        L.append(f"- {s}")
    L.append("")
    L.append("**Prohibited.**")
    L.append("")
    for s in a.get("prohibited", []):
        L.append(f"- {s}")
    L.append("")
    L.append("## Environment")
    L.append("")
    e = spec["environment"]
    L.append(f"Telemetry pipeline mode: **`{e['telemetry_pipeline']['mode']}`**. In "
             "discovery this bounds what may be proposed: a scratch pipeline supports a "
             "visibility proposal (did an artifact appear, and in which system class) and "
             "not a detection proposal, because our detection content was not in the path.")
    L.append("")
    L.append("| Layer | Steps |")
    L.append("|---|---|")
    for row in e["layers"]:
        L.append(f"| {row['layer']} | {', '.join(str(s) for s in row['steps'])} |")
    L.append("")
    L.append("| Component | For steps | Fidelity |")
    L.append("|---|---|---|")
    for c in e["components"]:
        L.append(f"| {c['name']} | {', '.join(str(s) for s in c['for_steps'])} | "
                 f"`{c['fidelity']}` |")
    L.append("")
    L.append("## Layer vocabulary")
    L.append("")
    L.append("`observed_layer` in the run record takes one or two of these, exactly as "
             "written. Agent behavior and MCP servers are L3. Model output is L2. Retrieval "
             "and data stores are L1. App surface is L4. Hosts, cloud and network are L0. "
             "A third party is not a layer: set `out_of_estate: true` instead.")
    L.append("")
    for v in spec["layer_vocabulary"]:
        L.append(f"- `{v}`")
    L.append("")
    L.append("## Requirements")
    L.append("")
    for entry in spec["procedure"]:
        n = entry["step"]
        tech = entry.get("techniques", {})
        tech_s = ", ".join(f"`{t}`" for t in tech.get("attack", []) + tech.get("atlas", [])) \
            or "_none mapped_"
        L.append(f"### Requirement: Step {n} — {entry['intent']}")
        L.append("")
        L.append(f"Techniques: {tech_s}. Lab layer: {entry.get('layer','')}.")
        L.append("")
        L.append("The agent SHALL reproduce this behavior against an allowlisted target, and "
                 "SHALL NOT take any action outside the action set below.")
        L.append("")
        for act in entry["actions"]:
            L.append(f"- {act}")
        L.append("")
        rc = entry["record_claims"]
        L.append("**What the record says today, unscored.** Treat it as the first place to "
                 "look, not the only one.")
        L.append("")
        L.append(f"- Signal: _{rc.get('signal') or 'not stated'}_")
        L.append(f"- Emitted at: _{rc.get('emitted_at') or 'not stated'}_")
        L.append(f"- Source: _{rc.get('source') or 'none named'}_")
        L.append(f"- Detection opportunity: _{rc.get('detection_opportunity') or 'not stated'}_")
        L.append("")
        L.append("#### Scenario: The step is observed")
        L.append("")
        L.append(f"- **WHEN** the step {n} action set completes")
        L.append("- **THEN** the agent SHALL search every collector it can reach, not only "
                 "the source the record names, and record `detected`, `logged-only`, "
                 "`absent` or `unscoreable`")
        L.append("- **AND** SHALL record `observed_source` as the system plus index or log "
                 "name, and only where the artifact was found")
        L.append("- **AND** SHALL tag `observed_layer` from the vocabulary above, one or two "
                 "values, and `out_of_estate` where the step reached a stand-in")
        L.append("- **AND** SHALL record whether anything alerted, and what")
        L.append("- **AND** SHALL record the artifact latency in seconds, or null")
        L.append("")
        L.append("#### Scenario: A proposal is made")
        L.append("")
        L.append(f"- **WHEN** step {n} was executed and its observation is not `unscoreable`")
        L.append("- **THEN** the agent SHALL propose `proposed_visibility` (0..4) and "
                 "`proposed_detection` (-1..5)")
        L.append("- **AND** SHALL write `proposal_rationale` naming what was seen, where, "
                 "how completely, and what would have moved each number")
        if spec["environment"]["telemetry_pipeline"]["mode"] != "mirrored":
            L.append("- **AND** SHALL propose `-1` for detection, because this pipeline does "
                     "not carry our detection content and nothing about it was observed")
        L.append("- **AND** SHALL NOT propose anything for a step that did not execute or "
                 "whose observation is `unscoreable`")
        L.append("")
        if entry.get("out_of_scope"):
            L.append("**Out of scope for this run.**")
            L.append("")
            for o in entry["out_of_scope"]:
                L.append(f"- {o}")
            L.append("")
    if spec.get("excluded_steps"):
        L.append("## Excluded steps")
        L.append("")
        L.append("Kept visible so an exclusion is a stated decision rather than a step "
                 "that quietly went missing.")
        L.append("")
        for x in spec["excluded_steps"]:
            L.append(f"- Step {x['step']} ({x.get('class','other')}): {x['reason']}")
        L.append("")
    rp = spec["return_path"]
    L.append("## Return path")
    L.append("")
    L.append("There is no scoring step and no scorecard. `confirmed` and `overestimate` are "
             "defined against a prediction, and this run had none.")
    L.append("")
    L.append(f"1. Write the run record to `{rp['record']}`, in the shape of "
             f"`{rp['schema']}`.")
    L.append("2. Validate it: `python3 tools/validate.py runs/DISC-*.yaml`.")
    L.append(f"3. A person reads the proposals and accepts some or all: "
             f"`python3 tools/{rp['bridge']} runs/DISC-... --accepted-by \"Name\"`.")
    L.append("4. Apply, review the diff, commit: `python3 tools/apply_session.py ... --dry-run`, "
             "then without `--dry-run`.")
    L.append("")
    L.append("Every score that lands carries `score_provenance: agent-proposed`. It is listed "
             "in the coverage rollup and counted in no average until a person who has looked "
             "at the evidence sets it to `human-session`.")
    L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenario", help="scenario id, for example 021")
    ap.add_argument("--pipeline", choices=["mirrored", "scratch", "none"], default="scratch",
                    help="telemetry pipeline fidelity of the lab. Default scratch.")
    ap.add_argument("--org", help="apply this org's coverage overlay before emitting")
    ap.add_argument("--requested-by", default=None,
                    help="who asked for this run; stamped on the spec, nothing is sealed")
    ap.add_argument("--date", default=None, help="ISO date to stamp; defaults to today")
    ap.add_argument("--check", action="store_true", help="run the readiness gate and stop")
    ap.add_argument("--out", default=None, help="output directory (default specs/)")
    args = ap.parse_args()

    rec, path = load_scenario(args.scenario)
    overlay = load_overlay(args.scenario, args.org) if args.org else None
    rows = resolve_rows(rec, overlay)

    blockers = discovery_readiness(rec, rows, path)
    if blockers:
        print(f"NOT READY: scenario {args.scenario} cannot be emitted for discovery.\n")
        for b in blockers:
            print(f"  - {b}")
        return 1
    unscored = sum(1 for r in rows.values() if derive_coverage(r.get("dettect")) is None)
    print(f"discovery readiness: {args.scenario} passes the mechanical gate "
          f"({unscored} of {len(rows)} rows unscored, status {rec.get('status')})")
    if args.check:
        print("--check given, nothing written.")
        return 0

    date = args.date or datetime.date.today().isoformat()
    sid = rec["id"]
    spec_id = f"DISC-{sid}"
    outdir = pathlib.Path(args.out) if args.out else SPECS / f"{spec_id}-{rec['slug']}"
    outdir.mkdir(parents=True, exist_ok=True)

    vocabulary = layer_vocabulary()
    procedure, excluded = build_discovery_procedure(rec, rows, args.pipeline, vocabulary)
    spec = {
        "spec_version": 1,
        "spec_id": spec_id,
        "mode": "discovery",
        "scenario": sid,
        "scenario_title": rec.get("title", ""),
        "scenario_status": rec.get("status"),
        "baseline": rec["framework_mapping"]["baseline"],
        "generated": date,
        "generated_by": "tools/emit_discovery.py",
        "requested_by": args.requested_by,
        "source_digest": sha256_bytes(path.read_bytes()),
        "prediction": None,   # deliberately, and permanently. See the module docstring.
        "authorization": {
            "autonomy": "lab-only",
            "enabled_rungs": ["lab-only"],
            "targets": [],
            "time_box": "PT2H",
            "egress": "deny-all",
            "stop_conditions": STOP_CONDITIONS,
            "teardown_required": True,
            "prohibited": PROHIBITED,
        },
        "environment": build_environment(rec, rows, args.pipeline),
        "layer_vocabulary": vocabulary,
        "procedure": procedure,
        "readiness": {
            "mechanical_gate": "passed",
            "checks": [
                "status is draft or in-review, not published or retired",
                "every attack path step has an evidence row to land a proposal in",
                "the record declares a framework baseline",
                "the scenario is an attack, not a failure mode, and not doomsday",
            ],
            "judgment_gate": "not recorded here. Run the readiness prompt in "
                             "docs/12-agent-testing.md before approving the run.",
        },
        "return_path": {
            "record": f"runs/{spec_id}-YYYY-MM-DD-NN.yaml",
            "schema": "schema/discovery-run.schema.json",
            "bridge": "discovery_to_session.py",
        },
    }
    if excluded:
        spec["excluded_steps"] = excluded

    dump = lambda o: yaml.safe_dump(o, sort_keys=False, default_flow_style=False,
                                    width=100, allow_unicode=True)
    (outdir / "discovery.yaml").write_text(dump(spec), encoding="utf-8")
    (outdir / "discovery.md").write_text(render_markdown(spec), encoding="utf-8")

    print(f"\nwrote {outdir.relative_to(ROOT)}/")
    print("  discovery.yaml   the specification")
    print("  discovery.md     the same, in the spec-driven agent convention")
    print(f"\n{len(procedure)} step(s) in the procedure"
          + (f", {len(excluded)} excluded" if excluded else ""))
    print("\nNo prediction.yaml was written. Nothing is sealed, because nothing is claimed.")
    print(f"The agent's answer is a run record: runs/{spec_id}-{date}-01.yaml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
