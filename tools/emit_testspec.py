#!/usr/bin/env python3
"""
Emit an agent test specification, and the sealed prediction that goes with it, from a
scenario record.

    python3 tools/emit_testspec.py 021 --sealed-by "A. Analyst"
    python3 tools/emit_testspec.py 021 --pipeline mirrored --sealed-by "A. Analyst"
    python3 tools/emit_testspec.py 021 --org platform-eng --sealed-by "A. Analyst"
    python3 tools/emit_testspec.py 021 --check          # readiness only, write nothing

Three files land in specs/ST-<id>-<slug>/ :

    spec.yaml         the machine readable specification, schema validated
    spec.md           the same spec in the spec-driven agent convention, generated
    prediction.yaml   what we claim the run will find, to be committed BEFORE it runs

WHY THE PREDICTION IS A SEPARATE FILE. The scenario's coverage tags are already
predictions; this exercise only means something if they are frozen before the answer is
known. Committing prediction.yaml is a discrete, timestamped act, so git is the notary.
The run record binds to it by sha256, which is what makes a prediction quietly revised
after the fact detectable rather than merely discouraged.

WHAT THE EMITTER REFUSES TO DO. It will not emit from a record that cannot be scored
against: unpublished, unscored rows, a source-less Have or Collectable, or a baseline
the record does not actually speak. Those are not warnings. A spec emitted from a record
with an unscored row produces a run that answers a question nobody asked.

The procedure is deliberately engine agnostic. It states intent, technique and expected
artifact; an adapter binds it to an emulation runner at execution time. Specs outlive
runners, and an abstract action set is also the only form that can be reviewed for safety
before anyone chooses a tool.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys

try:
    import yaml
except ImportError:
    sys.exit("pip install pyyaml")

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPECS = ROOT / "specs"

# Coverage ranks. Blind 0, Collectable 1, Have 2. Used by the scorer too; the two tools
# must agree, so the ranking lives here and score_run.py imports it.
RANK = {"Blind": 0, "Collectable": 1, "Have": 2}

# Free-text step layers are a reading aid in the record, not a controlled field, so this
# is a seeded guess the author confirms. Getting it wrong costs a wrong lab component
# list, which is why the emitted note says to check it.
LAYER_HINTS = [
    (r"agent|orchestr|eval|tool.?call", "L3 Orchestration and Agent"),
    (r"model|inference|guardrail|prompt", "L2 Model"),
    (r"data|dataset|rag|vector|ingest|corpus", "L1 Data"),
    (r"app|applic|api|ui|front", "L4 Application"),
    (r"host|cloud|net|infra|container|node|k8s|kube", "L0 Infrastructure"),
]

PROHIBITED = [
    "No exploit development and no unpublished vulnerability research: the agent "
    "emulates published techniques only.",
    "No action against any system not named in authorization.targets.",
    "No persistence that survives teardown.",
    "No movement of real data. Synthetic canary records only.",
    "No credential use that resolves outside the lab boundary.",
]


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def derive_coverage(dettect: dict | None) -> str | None:
    """The one derivation rule. Mirrors tools/validate.py::derive_coverage() exactly;
    if these two ever disagree the program has two definitions of coverage, which is the
    one thing docs/04-measurement.md says must never happen."""
    if not dettect:
        return None
    vis, det = dettect.get("visibility"), dettect.get("detection")
    if vis is None or det is None:
        return None
    if vis == 0:
        return "Blind"
    return "Have" if det >= 1 else "Collectable"


def guess_layer(step: dict) -> str:
    hay = f"{step.get('layer','')} {step.get('text','')}".lower()
    if "external" in hay and "internal" not in hay:
        return "External (out of estate)"
    for pattern, label in LAYER_HINTS:
        if re.search(pattern, hay):
            return label
    return "unclassified"


def load_scenario(sid: str) -> tuple[dict, pathlib.Path]:
    matches = sorted((ROOT / "scenarios").glob(f"{sid}-*.yaml"))
    if not matches:
        sys.exit(f"no scenario record found for id {sid} in scenarios/")
    path = matches[0]
    return yaml.safe_load(path.read_text()), path


def load_overlay(sid: str, org: str) -> dict | None:
    path = ROOT / "coverage" / org / f"{sid}.yaml"
    if not path.exists():
        sys.exit(f"no overlay at {path.relative_to(ROOT)}")
    return yaml.safe_load(path.read_text())


def resolve_rows(rec: dict, overlay: dict | None) -> dict[int, dict]:
    """Row level resolution, exactly as docs/04-measurement.md defines it: a step takes
    the overlay row when one exists and is not inherit, otherwise the reference row."""
    rows = {r["step"]: dict(r) for r in rec.get("telemetry", [])
            if r.get("kind", "attack-step") == "attack-step"}
    if not overlay:
        return rows
    for orow in overlay.get("telemetry", []):
        step = orow.get("step")
        if step not in rows or orow.get("inherit"):
            continue
        merged = dict(rows[step])
        for k, v in orow.items():
            if k not in ("step", "inherit"):
                merged[k] = v
        rows[step] = merged
    return rows


def readiness(rec: dict, rows: dict[int, dict], path: pathlib.Path) -> list[str]:
    """Mechanical half of the readiness gate. The judgment half (is a step concrete
    enough to execute, is it safe, can the lab stand it up) comes from the readiness
    prompt in docs/12-agent-testing.md and arrives as JSON. Both halves must pass."""
    blockers = []
    if rec.get("status") != "published":
        blockers.append(
            f"status is '{rec.get('status')}', not published. A draft's scores are not a "
            "claim anyone has stood behind, so there is nothing to falsify.")

    steps = {s["step"] for s in rec.get("attack_path", [])}
    missing = sorted(steps - set(rows))
    if missing:
        blockers.append(f"attack path steps {missing} have no attack-step evidence row.")

    for step in sorted(rows):
        row = rows[step]
        cov = derive_coverage(row.get("dettect"))
        if cov is None:
            blockers.append(
                f"step {step} is unscored. An unscored row is None, not Blind, so it "
                "predicts nothing and cannot be tested.")
            continue
        if cov != row.get("coverage"):
            blockers.append(
                f"step {step} coverage is '{row.get('coverage')}' but the scores derive "
                f"'{cov}'. Run ./liszt validate before emitting.")
        if cov in ("Have", "Collectable") and not row.get("source"):
            blockers.append(
                f"step {step} is {cov} with no named source. The observer would not know "
                "which system to look in, so the claim is not checkable.")

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


def build_environment(rec: dict, rows: dict[int, dict], pipeline: str) -> dict:
    """What the lab must reproduce. Derived from the record, so it is a requirement list
    rather than a wish list, and every entry traces to a step that needs it."""
    by_layer: dict[str, list[int]] = {}
    components: list[dict] = []

    for step in rec.get("attack_path", []):
        layer = guess_layer(step)
        by_layer.setdefault(layer, []).append(step["step"])

    # Execution components, one per step, seeded from the step's own words.
    for step in rec.get("attack_path", []):
        n = step["step"]
        components.append({
            "name": f"Target for step {n}: {step.get('layer', 'unspecified')}",
            "for_steps": [n],
            "fidelity": "equivalent",
            "note": ("Seeded from the step's layer tag. Confirm the fidelity by hand: set "
                     "'exact' where the artifact depends on the specific product or "
                     "version, because that is the assumption that silently breaks "
                     "transfer from lab to estate."),
        })

    # Observation components, the systems the record claims the artifact lands in.
    seen: set[str] = set()
    for n in sorted(rows):
        src = (rows[n].get("source") or "").strip()
        if not src or src in seen:
            continue
        seen.add(src)
        components.append({
            "name": f"Observation source: {src}",
            "for_steps": [k for k in sorted(rows) if rows[k].get("source") == src],
            "fidelity": "exact" if pipeline == "mirrored" else "equivalent",
            "note": ("In mirrored mode this must be the real collector and the real "
                     "detection content, or the detection claim is not being tested. In "
                     "scratch mode an equivalent collector can still test whether the "
                     "artifact exists and where it lands."),
        })

    required_sources = [rows[n]["source"] for n in sorted(rows) if rows[n].get("source")]

    notes = []
    if pipeline == "scratch":
        notes.append(
            "Scratch pipeline: the lab collects with its own tooling, so this run can "
            "test whether an artifact exists and which system class it lands in, and "
            "cannot test whether OUR detection fires. Every detection claim is recorded "
            "unscoreable rather than assumed.")
    elif pipeline == "none":
        notes.append(
            "No collection: this run can only demonstrate that the technique executes. "
            "It says nothing about our estate and must not be scored as if it did.")
    else:
        notes.append(
            "Mirrored pipeline: the lab ships to the same collectors, parsers and "
            "detection content as the estate being scored. This is the only mode in which "
            "a detection claim is genuinely under test, and the only mode whose Blind "
            "results transfer.")
    notes.append(
        "Any source named on an evidence row but absent from the lab makes that row's "
        "source claim unscoreable. Record it as unscoreable in the run; do not infer it.")

    return {
        "layers": [{"layer": k, "steps": sorted(v)} for k, v in sorted(by_layer.items())],
        "components": components,
        "telemetry_pipeline": {
            "mode": pipeline,
            "required_sources": required_sources,
            "note": ("These are the exact systems the record names. The run record lists "
                     "which of them actually existed."),
        },
        "fidelity_notes": notes,
    }


def scoreable_for(row: dict, pipeline: str) -> list[str]:
    """Which claims a run in this pipeline mode is ALLOWED to score. The scorer enforces
    this, which is what stops a cheap lab from producing a confident wrong number."""
    if pipeline == "none":
        return []
    cov = derive_coverage(row.get("dettect"))
    # Signal presence is always under test, including on a Blind row: "nothing is
    # emitted" is a claim, and the run can falsify it by finding something.
    out = ["signal-presence"]
    # Source attribution only exists where a source is claimed. A Blind row names no
    # system to look in, so asserting one would invent a claim the record never made.
    if cov != "Blind":
        out.append("source-attribution")
    if pipeline == "mirrored" and cov == "Have":
        out.append("detection-fires")
    return out


def build_procedure(rec: dict, rows: dict[int, dict], pipeline: str) -> tuple[list, list]:
    procedure, excluded = [], []
    for step in rec.get("attack_path", []):
        n = step["step"]
        row = rows.get(n)
        if row is None:
            excluded.append({"step": n, "class": "not-scored",
                             "reason": "no evidence row, so nothing is predicted for it"})
            continue

        cov = derive_coverage(row.get("dettect"))
        layer = guess_layer(step)
        external = layer.startswith("External")

        techniques = {}
        if step.get("attack"):
            techniques["attack"] = list(step["attack"])
        if step.get("atlas"):
            techniques["atlas"] = list(step["atlas"])

        actions = [
            f"Reproduce the behavior described by the step, against the allowlisted "
            f"target for {step.get('layer', 'this layer')}, using a published emulation "
            f"of {', '.join(techniques.get('attack', [])) or 'the mapped technique'}.",
            "Resolve the concrete emulation from the adapter's library at run time by "
            "technique id. The spec carries no payload by design.",
            "Record the wall clock time of the action so artifact latency can be measured.",
        ]
        if not techniques:
            actions[0] = (
                "Reproduce the behavior described by the step against the allowlisted "
                "target. No framework technique is mapped to this step, so there is no "
                "library emulation to resolve: the action set has to be written by hand "
                "and reviewed before it runs.")

        entry = {
            "step": n,
            "intent": step.get("text", ""),
            "layer": layer,
            "techniques": techniques,
            "actions": actions,
            "expected_artifacts": [row.get("signal", "unspecified signal")],
            "observation": {
                "source": row.get("source") or "no source named; nothing to observe",
                "scoreable": scoreable_for(row, pipeline),
            },
            "safety": {
                "destructive": False,
                "reversible": True,
                "requires_human": bool(external) or not techniques,
                "note": ("Seeded conservatively. Confirm by hand before approval: the "
                         "emitter cannot tell whether an action is destructive in your "
                         "environment."),
            },
        }
        if row.get("evidence"):
            entry["observation"]["detection_artifact"] = row["evidence"]
        if row.get("detection_opportunity"):
            entry["observation"]["query_hint"] = row["detection_opportunity"]
        if cov == "Blind":
            entry["observation"]["query_hint"] = (
                (entry["observation"].get("query_hint", "") + " ").strip() +
                " | Blind is a prediction too: search broadly, because the useful result "
                "here is finding an artifact the record says does not exist.")
        if external:
            entry["out_of_scope"] = [
                "The scenario reaches a third party at this step. The run substitutes a "
                "local stand-in inside the lab boundary. Nothing outside the allowlist is "
                "touched, and the result speaks to our own visibility only."]
        if step.get("control_held"):
            entry["out_of_scope"] = entry.get("out_of_scope", []) + [
                "The record marks a control as having held at this step. Reproduce the "
                "attempt, not a bypass of that control, and record whether it held again."]
        procedure.append(entry)
    return procedure, excluded


def build_prediction(rec: dict, rows: dict[int, dict], procedure: list, pipeline: str,
                     spec_id: str, sealed_by: str, date: str, org: str | None) -> dict:
    pred_rows = []
    for entry in procedure:
        n = entry["step"]
        row = rows[n]
        d = row.get("dettect") or {}
        cov = derive_coverage(d)
        vis, det = d.get("visibility"), d.get("detection")
        claims = {
            "signal_present": vis >= 1,
            "signal": row.get("signal", ""),
            "source": row.get("source", ""),
            "detection_fires": det >= 1,
        }
        if row.get("evidence"):
            claims["detection_artifact"] = row["evidence"]

        testable = {
            "signal_present": "not-testable" if pipeline == "none" else "lab",
            "source": "not-testable" if pipeline == "none" else "lab",
            "detection_fires": ("pipeline" if claims["detection_fires"]
                                else "not-testable"),
        }
        if claims["detection_fires"] and pipeline != "mirrored":
            testable["detection_fires"] = "pipeline"

        rationale = (
            f"visibility {vis} and detection {det} derive {cov}. "
            + ("Nothing is claimed to be emitted, so finding any artifact falsifies this row."
               if cov == "Blind" else
               f"The artifact is claimed to land in {row.get('source','an unnamed system')}"
               + (f", and {row['evidence']} is claimed to fire." if cov == "Have" and row.get("evidence")
                  else ", and nothing is claimed to alert on it.")))

        pred_rows.append({
            "step": n,
            "predicted_coverage": cov,
            "predicted_visibility": vis,
            "predicted_detection": det,
            "claims": claims,
            "testable_in": testable,
            "rationale": rationale,
        })

    return {
        "prediction_version": 1,
        "spec_id": spec_id,
        "scenario": rec["id"],
        "baseline": rec["framework_mapping"]["baseline"],
        "sealed": date,
        "sealed_by": sealed_by,
        "spec_digest": "0" * 64,          # filled after the spec is written
        "assessment": "org" if org else "reference",
        **({"org_id": org} if org else {}),
        "rows": pred_rows,
        "expectations": {
            # Deliberately absent rather than null: the schema takes an integer, and an
            # absent field reads as "not yet judged" where a null reads as "judged, zero".
            "note": ("Add expected_surprises (an integer) before committing. Predicting "
                     "zero surprises is itself a claim, and usually a wrong one."),
        },
    }


def render_markdown(spec: dict, pred: dict) -> str:
    """The spec in the spec-driven agent convention. GENERATED from spec.yaml; the yaml
    is the source of truth, so this is regenerated rather than edited."""
    a = spec["authorization"]
    L = []
    L.append(f"# {spec['spec_id']}: {spec.get('scenario_title', '')}".rstrip())
    L.append("")
    L.append(f"> Generated by `{spec['generated_by']}` from scenario "
             f"`{spec['scenario']}` at baseline `{spec['baseline']}` on {spec['generated']}. "
             f"Do not edit; regenerate.")
    L.append("")
    L.append("## Purpose")
    L.append("")
    L.append("Test whether the evidence map for this scenario is right. The agent reproduces "
             "the mapped behavior; the observer checks whether each artifact appeared, in the "
             "system the record names, and whether the named detection fired. The claims "
             "under test are sealed in `prediction.yaml` and must not be read before the "
             "observations are recorded.")
    L.append("")
    L.append("## Authorization")
    L.append("")
    L.append(f"- **Autonomy rung**: `{a['autonomy']}`")
    L.append(f"- **Rungs enabled in this deployment**: {', '.join(f'`{r}`' for r in a.get('enabled_rungs', []))}")
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
    L.append(f"Telemetry pipeline mode: **`{e['telemetry_pipeline']['mode']}`**. "
             "This decides which claims may be scored, and it is the difference between a "
             "result that transfers to the estate and one that does not.")
    L.append("")
    L.append("| Layer | Steps |")
    L.append("|---|---|")
    for row in e["layers"]:
        L.append(f"| {row['layer']} | {', '.join(str(s) for s in row['steps'])} |")
    L.append("")
    L.append("| Component | For steps | Fidelity |")
    L.append("|---|---|---|")
    for c in e["components"]:
        L.append(f"| {c['name']} | {', '.join(str(s) for s in c['for_steps'])} | `{c['fidelity']}` |")
    L.append("")
    for n in e.get("fidelity_notes", []):
        L.append(f"- {n}")
    L.append("")
    L.append("## Requirements")
    L.append("")
    for entry in spec["procedure"]:
        n = entry["step"]
        prow = next((p for p in pred["rows"] if p["step"] == n), {})
        tech = entry.get("techniques", {})
        tech_s = ", ".join(f"`{t}`" for t in tech.get("attack", []) + tech.get("atlas", [])) or "_none mapped_"
        L.append(f"### Requirement: Step {n} — {entry['intent']}")
        L.append("")
        L.append(f"Techniques: {tech_s}. Layer: {entry.get('layer','')}.")
        L.append("")
        L.append(f"The agent SHALL reproduce this behavior against an allowlisted target, and "
                 f"SHALL NOT take any action outside the action set below.")
        L.append("")
        for act in entry["actions"]:
            L.append(f"- {act}")
        L.append("")
        scoreable = entry["observation"].get("scoreable", [])
        if "signal-presence" in scoreable:
            L.append(f"#### Scenario: The artifact is produced")
            L.append("")
            L.append(f"- **WHEN** the step {n} action set completes")
            verb = "SHALL" if prow.get("claims", {}).get("signal_present") else "SHALL NOT"
            L.append(f"- **THEN** an artifact matching _{entry['expected_artifacts'][0]}_ {verb} be observable")
            L.append(f"- **AND** the observer SHALL record the artifact latency in seconds")
            L.append("")
        if "source-attribution" in scoreable:
            L.append(f"#### Scenario: The artifact lands where the record says")
            L.append("")
            L.append(f"- **WHEN** an artifact is observed for step {n}")
            L.append(f"- **THEN** it SHALL be found in `{entry['observation']['source']}`")
            L.append(f"- **AND** if it is found elsewhere the observer SHALL record where, "
                     f"because a right answer from the wrong system is a separate defect")
            L.append("")
        if "detection-fires" in scoreable:
            art = entry["observation"].get("detection_artifact", "the named detection")
            L.append(f"#### Scenario: The detection fires")
            L.append("")
            L.append(f"- **WHEN** the artifact for step {n} reaches the detection pipeline")
            L.append(f"- **THEN** `{art}` SHALL fire")
            L.append("")
        if not scoreable:
            L.append(f"#### Scenario: Not scoreable in this environment")
            L.append("")
            L.append(f"- **WHEN** the step {n} action set completes")
            L.append(f"- **THEN** the observer SHALL record `unscoreable` and SHALL NOT infer a result")
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
        L.append("Kept visible so the exclusion appears on the scorecard rather than "
                 "silently shrinking the denominator.")
        L.append("")
        for x in spec["excluded_steps"]:
            L.append(f"- Step {x['step']} ({x.get('class','other')}): {x['reason']}")
        L.append("")
    L.append("## Scoring")
    L.append("")
    L.append("After the run, record observations in a run record and score it:")
    L.append("")
    L.append("```bash")
    L.append(f"python3 tools/score_run.py runs/RUN-{spec['scenario']}-YYYY-MM-DD-01.yaml")
    L.append("```")
    L.append("")
    L.append("The scorer refuses to score a claim outside the venue this spec allows, and "
             "refuses entirely if the prediction on disk no longer matches the digest the "
             "run was bound to.")
    L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenario", help="scenario id, for example 021")
    ap.add_argument("--pipeline", choices=["mirrored", "scratch", "none"], default="scratch",
                    help="telemetry pipeline fidelity of the lab. Default scratch, the "
                         "honest default for a first environment.")
    ap.add_argument("--org", help="apply this org's coverage overlay before predicting")
    ap.add_argument("--sealed-by", default=None, help="the human who stands behind the prediction")
    ap.add_argument("--date", default=None, help="ISO date to stamp; defaults to today")
    ap.add_argument("--check", action="store_true", help="run the readiness gate and stop")
    ap.add_argument("--out", default=None, help="output directory (default specs/)")
    args = ap.parse_args()

    rec, path = load_scenario(args.scenario)
    overlay = load_overlay(args.scenario, args.org) if args.org else None
    rows = resolve_rows(rec, overlay)

    blockers = readiness(rec, rows, path)
    if blockers:
        print(f"NOT READY: scenario {args.scenario} cannot be emitted as a test spec.\n")
        for b in blockers:
            print(f"  - {b}")
        print("\nThe mechanical gate is only half of readiness. Run the readiness prompt in "
              "docs/12-agent-testing.md for the judgment half before emitting.")
        return 1
    print(f"readiness: {args.scenario} passes the mechanical gate "
          f"({len(rows)} scored rows, status {rec.get('status')})")
    if args.check:
        print("--check given, nothing written.")
        return 0

    if not args.sealed_by:
        sys.exit("--sealed-by is required: a prediction with no name against it is not a "
                 "prediction. Accountability does not transfer to the emitter.")

    import datetime
    date = args.date or datetime.date.today().isoformat()
    sid = rec["id"]
    spec_id = f"ST-{sid}"
    outdir = pathlib.Path(args.out) if args.out else SPECS / f"{spec_id}-{rec['slug']}"
    outdir.mkdir(parents=True, exist_ok=True)

    procedure, excluded = build_procedure(rec, rows, args.pipeline)
    spec = {
        "spec_version": 1,
        "spec_id": spec_id,
        "scenario": sid,
        "scenario_title": rec.get("title", ""),
        "baseline": rec["framework_mapping"]["baseline"],
        "generated": date,
        "generated_by": "tools/emit_testspec.py",
        "source_digest": sha256_bytes(path.read_bytes()),
        "status": "draft",
        "authorization": {
            "autonomy": "lab-only",
            "enabled_rungs": ["lab-only"],
            "targets": [],
            "time_box": "PT2H",
            "egress": "deny-all",
            "stop_conditions": [
                "Any interaction with an address or account outside authorization.targets.",
                "Any credential that resolves outside the lab boundary.",
                "Any action not present in this spec's procedure.",
                "Time box expiry, whether or not the procedure has finished.",
                "Loss of the observer's ability to read the telemetry pipeline, since the "
                "run stops producing evidence at that moment.",
            ],
            "teardown_required": True,
            "prohibited": PROHIBITED,
        },
        "environment": build_environment(rec, rows, args.pipeline),
        "procedure": procedure,
        "readiness": {
            "verdict": "ready",
            "validated_by": args.sealed_by,
            "validated": date,
            "checks": [
                "status is published",
                "every attack path step has a scored evidence row",
                "derived coverage matches the recorded tag on every row",
                "every Have and Collectable row names a source",
                "the record declares a framework baseline",
            ],
        },
    }
    if excluded:
        spec["excluded_steps"] = excluded

    dump = lambda o: yaml.safe_dump(o, sort_keys=False, default_flow_style=False,
                                    width=100, allow_unicode=True)

    spec_path = outdir / "spec.yaml"
    spec_path.write_text(dump(spec))
    spec_digest = sha256_bytes(spec_path.read_bytes())

    pred = build_prediction(rec, rows, procedure, args.pipeline, spec_id,
                            args.sealed_by, date, args.org)
    pred["spec_digest"] = spec_digest
    pred_path = outdir / "prediction.yaml"
    pred_path.write_text(dump(pred))

    (outdir / "spec.md").write_text(render_markdown(spec, pred))

    rel = outdir.relative_to(ROOT)
    print(f"\nwrote {rel}/spec.yaml       {spec_digest[:16]}.")
    print(f"wrote {rel}/spec.md         (generated from spec.yaml)")
    print(f"wrote {rel}/prediction.yaml  sealed by {args.sealed_by}")
    print(f"\npipeline mode: {args.pipeline}")
    scoreable = {c for e in procedure for c in e['observation']['scoreable']}
    print(f"claims this environment may score: {', '.join(sorted(scoreable)) or 'none'}")
    if args.pipeline != "mirrored":
        print("detection claims are NOT under test in this mode. The scorer will record "
              "them unscoreable rather than let the run imply an answer.")
    print("\nNEXT, in order, and the order matters:")
    print("  1. Assign authorization.targets. An empty allowlist refuses to run.")
    print("  2. Confirm component fidelity and the safety flags by hand.")
    print("  3. Fill expectations.expected_surprises in prediction.yaml.")
    print("  4. COMMIT prediction.yaml before the run. The commit is the seal.")
    print("  5. Run, record observations, then score.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
