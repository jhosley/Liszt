#!/usr/bin/env python3
"""
Score a run against its sealed prediction, and say what the result should change.

    python3 tools/score_run.py runs/RUN-021-2026-08-05-01.yaml
    python3 tools/score_run.py runs/RUN-021-2026-08-05-01.yaml --write
    python3 tools/score_run.py runs/RUN-021-2026-08-05-01.yaml --json

WHAT IS BEING SCORED. Not the attack, and not the estate. The evidence map. Every row of
a scenario is a falsifiable claim about what our systems would emit and whether we would
notice, and this compares that claim to what a run actually found. The output is a
calibration number for the PROCESS, which is the only way to find out whether the library
is describing the estate or describing our optimism.

THE THREE REFUSALS. This tool refuses to score:

  1. against a prediction whose digest no longer matches the file on disk, because a
     prediction edited after the run is not a prediction;
  2. a claim outside the venue the environment can test, because a scratch lab that
     scores detection claims produces a confident wrong number;
  3. a coverage tag whose truth depends on the detection pipeline when no pipeline was
     mirrored. A scratch lab can fully falsify a Blind row and cannot fully confirm a
     Have one, and pretending otherwise is the failure this whole exercise exists to
     catch.

That third refusal is the useful one to say out loud: a cheap lab is a Blind hunting
instrument. That is worth having, and it is not the same as a detection test.
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

RANK = {"Blind": 0, "Collectable": 1, "Have": 2}
OBS_RANK = {"absent": 0, "logged-only": 1, "detected": 2}
STOP = {"the", "and", "for", "with", "from", "log", "logs", "index", "source", "event",
        "events", "a", "an", "of", "in", "to", "it", "would", "have", "come", "that"}


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (s or "").lower())
            if len(t) >= 3 and t not in STOP}


def source_match(predicted: str, observed: str) -> tuple[bool | None, str]:
    """Did the artifact turn up in the system the record named? Fuzzy by necessity: the
    source field is prose written by an analyst, not an identifier. A clear overlap is
    a match, no overlap is a miss, and the middle is handed back to a human rather than
    guessed, because this number feeds a metric people will quote."""
    if not observed:
        return None, "nothing observed, so nothing to attribute"
    p, o = tokens(predicted), tokens(observed)
    if not p or not o:
        return None, "one side has no distinctive tokens; confirm by hand"
    overlap = len(p & o) / max(1, min(len(p), len(o)))
    if overlap >= 0.5:
        return True, f"token overlap {overlap:.2f}"
    if overlap == 0:
        return False, "no overlap: the artifact appeared somewhere the record does not name"
    return None, (f"token overlap {overlap:.2f} is ambiguous; a human decides. "
                  "Do not let an ambiguous match quietly count as a hit.")


def load(path: pathlib.Path) -> dict:
    if not path.exists():
        sys.exit(f"no such file: {path}")
    return yaml.safe_load(path.read_text())


def find_prediction(run: dict) -> tuple[dict, pathlib.Path, dict]:
    spec_id = run["spec_id"]
    hits = sorted((ROOT / "specs").glob(f"{spec_id}-*/prediction.yaml"))
    if not hits:
        sys.exit(f"no prediction found for {spec_id} under specs/")
    spec_file = hits[0].parent / "spec.yaml"
    spec = load(spec_file) if spec_file.exists() else {}
    return load(hits[0]), hits[0], spec


def score(run: dict, pred: dict, spec: dict) -> dict:
    pipeline = run.get("environment", {}).get("telemetry_pipeline", "none")
    mirrored = pipeline == "mirrored"

    prows = {r["step"]: r for r in pred["rows"]}
    layers = {e["step"]: e.get("layer", "unclassified")
              for e in spec.get("procedure", [])}
    rows, caveats = [], []
    cls = {k: {"scored": 0, "correct": 0} for k in
           ("signal_presence", "source_attribution", "detection_fires")}
    by_layer: dict[str, dict] = {}
    proposed, method, lab, new_sources = [], [], [], []

    for obs in run.get("observations", []):
        step = obs["step"]
        p = prows.get(step)
        if p is None:
            caveats.append(f"step {step} was observed but is not in the prediction; ignored")
            continue

        predicted = p["predicted_coverage"]
        claims = p.get("claims", {})
        entry = {"step": step, "predicted_coverage": predicted,
                 "observed": obs.get("observed")}

        if not obs.get("executed", True):
            entry["verdict"] = "not-executed"
            entry["note"] = obs.get("not_executed_reason", "not executed")
            rows.append(entry)
            continue
        if obs.get("observed") == "unscoreable":
            entry["verdict"] = "unscoreable"
            entry["note"] = obs.get("notes", "recorded unscoreable by the observer")
            rows.append(entry)
            continue

        observed = obs.get("observed")
        present = observed in ("detected", "logged-only")

        # ---- claim 1: signal presence. Always under test wherever collection exists.
        sig_ok = (present == bool(claims.get("signal_present")))
        cls["signal_presence"]["scored"] += 1
        cls["signal_presence"]["correct"] += int(sig_ok)

        # ---- claim 2: source attribution. Only where a source was claimed.
        smatch, snote = (None, "no source claimed")
        if predicted != "Blind" and present:
            smatch, snote = source_match(claims.get("source", ""), obs.get("observed_source", ""))
            if smatch is not None:
                cls["source_attribution"]["scored"] += 1
                cls["source_attribution"]["correct"] += int(smatch)
        entry["source_match"] = smatch

        # ---- claim 3: detection. Pipeline only, never inferred from a scratch lab.
        if mirrored and claims.get("detection_fires") is not None:
            fired = obs.get("detection_fired")
            if fired is not None:
                cls["detection_fires"]["scored"] += 1
                cls["detection_fires"]["correct"] += int(bool(fired) == bool(claims["detection_fires"]))

        # ---- headline coverage verdict, only where the venue supports the whole claim.
        depends_on_pipeline = predicted in ("Have", "Collectable")
        if depends_on_pipeline and not mirrored:
            entry["verdict"] = "unscoreable"
            entry["note"] = (
                f"predicted {predicted} depends on whether our detection fires, and the "
                f"pipeline was '{pipeline}'. The signal half was still scored: "
                f"{'correct' if sig_ok else 'WRONG'}.")
            rows.append(entry)
            continue

        delta = OBS_RANK[observed] - RANK[predicted]
        entry["delta"] = delta
        if delta == 0:
            entry["verdict"] = "confirmed"
        elif delta > 0:
            entry["verdict"] = "underestimate"
        elif delta == -2:
            entry["verdict"] = "severe-overestimate"
        else:
            entry["verdict"] = "overestimate"

        # ---- feedback, generated as proposals only.
        if entry["verdict"] == "underestimate" and predicted == "Blind":
            proposed.append({
                "step": step, "from": "Blind", "to": "Collectable" if observed == "logged-only" else "Have",
                "field": "visibility",
                "reason": (f"the record says nothing is emitted, and the run found an artifact in "
                           f"{obs.get('observed_source') or 'an unrecorded source'}. Free coverage "
                           f"the library did not know it had."),
            })
            if obs.get("observed_source"):
                new_sources.append(f"step {step}: {obs['observed_source']}")
        if entry["verdict"] in ("overestimate", "severe-overestimate"):
            proposed.append({
                "step": step, "from": predicted,
                "to": "Collectable" if observed == "logged-only" else "Blind",
                "field": "detection" if observed == "logged-only" else "visibility",
                "reason": (f"the record claims {predicted} and the run observed {observed}. "
                           f"Rescoring is a deliberate act: cite this run id as the backlog "
                           f"reference so the change appears in ids_rescored_this_period."),
            })
        if smatch is False:
            proposed.append({
                "step": step, "from": claims.get("source", ""),
                "to": obs.get("observed_source", ""), "field": "source",
                "reason": ("right about visibility, wrong about which system. The row would "
                           "have sent an investigator to the wrong log."),
            })

        rows.append(entry)

        b = by_layer.setdefault(layers.get(step, "unclassified"),
                                {"scored": 0, "confirmed": 0})
        b["scored"] += 1
        b["confirmed"] += int(entry["verdict"] == "confirmed")

    # ---- totals
    scored = [r for r in rows if r["verdict"] in
              ("confirmed", "overestimate", "severe-overestimate", "underestimate")]
    confirmed = [r for r in scored if r["verdict"] == "confirmed"]
    over = [r for r in scored if r["verdict"] == "overestimate"]
    severe = [r for r in scored if r["verdict"] == "severe-overestimate"]
    under = [r for r in scored if r["verdict"] == "underestimate"]
    deltas = [r["delta"] for r in scored]
    surprises = sum(len(o.get("surprises", []) or []) for o in run.get("observations", []))

    sm = [r["source_match"] for r in rows if r.get("source_match") is not None]

    totals = {
        "rows": len(rows),
        "scored": len(scored),
        "unscoreable": len([r for r in rows if r["verdict"] == "unscoreable"]),
        "not_executed": len([r for r in rows if r["verdict"] == "not-executed"]),
        "confirmed": len(confirmed),
        "overestimates": len(over),
        "severe_overestimates": len(severe),
        "underestimates": len(under),
        "exact_match_rate": round(len(confirmed) / len(scored), 3) if scored else None,
        # Positive means we believe we see more than we do. This is the number that
        # matters most: a program can be accurate on average and dangerous in one
        # direction, and only this field shows it.
        "optimism_index": round(-sum(deltas) / len(deltas), 3) if deltas else None,
        "source_precision": round(sum(1 for x in sm if x) / len(sm), 3) if sm else None,
        "surprise_count": surprises,
    }

    for k in cls:
        c = cls[k]
        c["rate"] = round(c["correct"] / c["scored"], 3) if c["scored"] else None
    if not mirrored:
        cls["detection_fires"]["note"] = (
            f"not under test: the pipeline was '{pipeline}'. Detection claims are only "
            "testable where our real collectors, parsers and detection content run.")
        caveats.append(
            f"Pipeline was '{pipeline}', so no detection claim was scored and every "
            "predicted Have or Collectable is unscoreable at the coverage level. What this "
            "run CAN settle is whether the artifacts exist and where they land.")
    for d in run.get("environment", {}).get("deviations", []) or []:
        caveats.append(f"environment deviation: {d}")
    if not run.get("environment", {}).get("teardown_confirmed", True):
        caveats.append("teardown was not confirmed: an operational finding in its own right.")

    # ---- method findings, the tuning signal
    if scored and len(scored) < 3:
        method.append(
            f"Only {len(scored)} row(s) were scoreable, so the rates above are a data "
            "point and not a trend. Report the counts, not the percentages, until the "
            "denominator is worth a percentage.")
    if totals["optimism_index"] is not None and len(scored) >= 3 and totals["optimism_index"] > 0:
        method.append(
            f"Optimism index {totals['optimism_index']:+}. Across the rows this run could "
            "score, the map claims more coverage than exists. Optimism is the failure mode "
            "that gets a program believed and then surprised; treat it as the headline.")
    elif totals["optimism_index"] is not None and len(scored) >= 3 and totals["optimism_index"] < 0:
        method.append(
            f"Optimism index {totals['optimism_index']:+}. The map is conservative here: "
            "real coverage the library is not claiming. Cheaper to fix than the other "
            "direction, and it still means the reporting is wrong.")
    if severe:
        method.append(
            f"{len(severe)} severe overestimate(s): a row predicted Have and produced "
            "nothing at all. Find out whether the control was never there, was removed, or "
            "was never verified after it was scored, because those are three different "
            "process failures.")
    if cls["source_attribution"]["scored"] and (cls["source_attribution"]["rate"] or 0) < 1:
        method.append(
            "At least one artifact appeared somewhere other than the system named on the "
            "row. The visibility judgment was right and the source field was wrong, which "
            "sends an investigator to the wrong log on the day it matters. Worth a look at "
            "whether sources are being captured with the system owner in the room.")
    if surprises:
        method.append(
            f"{surprises} unpredicted signal(s) recorded. These are the cheapest coverage "
            "in the program: sources that already work and are on no record.")
    if not scored:
        method.append(
            "Nothing was scoreable at the coverage level. That is a finding about the "
            "environment, not about the library; see the lab findings.")

    if not mirrored:
        lab.append(
            f"Pipeline mode '{pipeline}' capped what this run could prove. To test "
            "detection claims the lab has to ship to the same collectors and detection "
            "content as the estate being scored.")
    missing = [c for c in caveats if "deviation" in c]
    if missing:
        lab.append("Environment deviations were recorded; each one is a candidate "
                   "requirement for the next lab build.")

    return {
        "scorecard": {
            "computed": run.get("executed"),
            "computed_by": "tools/score_run.py",
            "rows": rows,
            "totals": totals,
            "by_class": cls,
            "by_layer": by_layer,
            "caveats": caveats,
        },
        "feedback": {
            "proposed_rescores": proposed,
            "method_findings": method,
            "lab_findings": lab,
            "new_sources_found": new_sources,
        },
    }


def report(run: dict, out: dict) -> None:
    sc, fb = out["scorecard"], out["feedback"]
    t = sc["totals"]
    W = 78
    print("=" * W)
    print(f"  {run['run_id']}   scenario {run['scenario']}   spec {run['spec_id']}")
    print(f"  environment {run['environment']['kind']}, pipeline "
          f"{run['environment']['telemetry_pipeline']}, autonomy {run['autonomy_used']}")
    print("=" * W)
    print()
    print(f"  {'step':<5}{'predicted':<13}{'observed':<14}{'verdict':<21}{'source'}")
    print("  " + "-" * (W - 4))
    for r in sc["rows"]:
        sm = r.get("source_match")
        smt = "match" if sm is True else ("MISS" if sm is False else "-")
        print(f"  {r['step']:<5}{r.get('predicted_coverage','') or '':<13}"
              f"{str(r.get('observed') or ''):<14}{r['verdict']:<21}{smt}")
    print()
    print(f"  scored {t['scored']} of {t['rows']} rows "
          f"({t['unscoreable']} unscoreable, {t['not_executed']} not executed)")
    if t["exact_match_rate"] is not None:
        print(f"  exact match rate   {t['exact_match_rate']:.0%}   "
              f"({t['confirmed']} confirmed, {t['overestimates']} over, "
              f"{t['severe_overestimates']} severe, {t['underestimates']} under)")
        thin = "  (too few rows to read as a trend)" if t["scored"] < 3 else ""
        print(f"  optimism index     {t['optimism_index']:+.3f}   "
              f"{'we claim more than exists' if t['optimism_index'] > 0 else ('we claim less than exists' if t['optimism_index'] < 0 else 'balanced')}{thin}")
    if t["source_precision"] is not None:
        print(f"  source precision   {t['source_precision']:.0%}")
    print(f"  unpredicted signals {t['surprise_count']}")
    print()
    print("  claim class            scored  correct  rate")
    for k, v in sc["by_class"].items():
        rate = f"{v['rate']:.0%}" if v.get("rate") is not None else "n/a"
        print(f"  {k:<22} {v['scored']:>5}  {v['correct']:>7}  {rate:>5}"
              + ("   (not under test)" if v.get("note") else ""))
    print()
    if sc["caveats"]:
        print("  CAVEATS")
        for c in sc["caveats"]:
            print(f"    - {c}")
        print()
    if fb["method_findings"]:
        print("  WHAT THIS SAYS ABOUT HOW WE PREDICT")
        for f in fb["method_findings"]:
            print(f"    - {f}")
        print()
    if fb["proposed_rescores"]:
        print("  PROPOSED RESCORES (proposals, not writes)")
        for p in fb["proposed_rescores"]:
            print(f"    - step {p['step']} {p['field']}: {p['from']!r} -> {p['to']!r}")
            print(f"      {p['reason']}")
        print()
    if fb["new_sources_found"]:
        print("  SOURCES FOUND THAT ARE ON NO RECORD")
        for s in fb["new_sources_found"]:
            print(f"    - {s}")
        print()
    if fb["lab_findings"]:
        print("  FOR THE LAB BUILD")
        for f in fb["lab_findings"]:
            print(f"    - {f}")
        print()
    print("  Nothing here has been written to a record. Applying a rescore is a deliberate")
    print(f"  act: cite {run['run_id']} as the backlog reference so the change is visible in")
    print("  the snapshot's ids_rescored_this_period rather than looking like improvement.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", help="path to the run record")
    ap.add_argument("--write", action="store_true",
                    help="write the scorecard and feedback back into the run record")
    ap.add_argument("--json", action="store_true", help="emit the scorecard as JSON")
    args = ap.parse_args()

    run_path = pathlib.Path(args.run)
    run = load(run_path)
    pred, pred_path, spec = find_prediction(run)

    actual = sha256_bytes(pred_path.read_bytes())
    if actual != run.get("prediction_digest"):
        print("REFUSING TO SCORE.\n")
        print(f"  the run is bound to prediction digest {run.get('prediction_digest','')[:16]}.")
        print(f"  the prediction on disk hashes to     {actual[:16]}.")
        print("\n  The prediction changed after the run was bound to it. Either the file was")
        print("  edited, or the run cites the wrong prediction. A prediction revised after")
        print("  the answer is known is not a prediction, and scoring it would launder that")
        print("  edit into a calibration number. Resolve it in git before scoring.")
        return 1

    out = score(run, pred, spec)
    if args.json:
        print(json.dumps(out, indent=2))
        return 0
    report(run, out)
    if args.write:
        run.update(out)
        run_path.write_text(yaml.safe_dump(run, sort_keys=False, default_flow_style=False,
                                           width=100, allow_unicode=True))
        print(f"\n  scorecard written into {run_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
