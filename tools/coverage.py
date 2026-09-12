#!/usr/bin/env python3
"""
Coverage, exposure and maturity rollup. Implements docs/04-measurement.md.

    python tools/coverage.py                        # published records, reference assessment
    python tools/coverage.py --org platform-eng     # apply a coverage/<org>/ overlay
    python tools/coverage.py --include-drafts       # see the whole library, drafts included
    python tools/coverage.py --json out/snap.json   # immutable snapshot for trend reporting
    python tools/coverage.py --json out/snap.json --prior out/last.json   # fill the period ledgers
    python tools/coverage.py --gaming               # run the anti-gaming checks only

Three metric families, deliberately kept apart because they answer different
questions for different audiences:

  COVERAGE  proportion of attack steps adequately instrumented.   Engineering.
  EXPOSURE  which NOW-priority scenarios still have Blind steps.  Risk.
  MATURITY  is the PROCESS working: reviewed, scored, owned,      Program.
            evidenced, funded. Moves independently of the other two.

The cardinal rule: an unscored row does not count as zero, it does not count at
all. Scoring nothing and scoring badly must not produce the same number.

The same rule, one step on: a row whose scores are agent-proposed (score_provenance
from a discovery run, see docs/13-discovery-mode.md) is listed, and counted nowhere.
A proposal a person has not accepted is not a measurement, and a rollup that averaged
it in would read as measured when nothing had been. Proposed rows appear in their
own column so their existence is visible and their numbers are not.

The snapshot this writes is the shape schema/snapshot.schema.json defines, which is the
shape docs/04-measurement.md section 5 specifies. It is validated before it is written.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import pathlib
import subprocess
import sys

try:
    import yaml
    from jsonschema import Draft202012Validator
except ImportError:
    sys.exit("pip install pyyaml jsonschema")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from validate import derive_coverage  # single source of truth for the derivation

ROOT = pathlib.Path(__file__).resolve().parent.parent
QUALITY_DIMS = ("device_completeness", "data_field_completeness",
                "timeliness", "consistency", "retention")

# The organization scoped fields of an evidence row, docs/04-measurement.md section 6.
# Everything else on a row is a property of the attack and may not be overridden.
ORG_FIELDS = ("dettect", "coverage", "source", "owner", "evidence", "backlog_ref",
              "notes", "research_needed", "score_provenance")


def load_records(include_drafts: bool) -> list[dict]:
    out = []
    for p in sorted((ROOT / "scenarios").glob("*.yaml")):
        if p.name.startswith("_"):
            continue
        rec = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        if rec.get("status") == "retired":
            continue
        if rec.get("status") != "published" and not include_drafts:
            continue
        out.append(rec)
    return out


def load_retired() -> list[dict]:
    """Retired records, for the snapshot ledger. Never silently absent."""
    out = []
    for p in sorted((ROOT / "scenarios").glob("*.yaml")):
        if p.name.startswith("_"):
            continue
        rec = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        if rec.get("status") == "retired":
            out.append(rec)
    return out


def apply_overlay(rec: dict, org: str) -> dict:
    """
    Per-org coverage overlay. The scenario library is org-independent; a given
    org's instrumentation is not. An org may adopt the library without ever
    publishing its coverage -- which is what makes the library politically portable.

    Resolution, docs/04-measurement.md section 6: a row takes the overlay entry with
    the matching step when one exists and is not `inherit`. A row absent from the
    overlay, or marked inherit, is UNSCORED for this org. The reference assessment is
    not evidence about this estate, so its scores are cleared rather than borrowed;
    the row keeps its attack-side fields (signal, emitted_at, data_components,
    detection_opportunity) because those are properties of the attack, not the estate.
    """
    path = ROOT / "coverage" / org / f"{rec['id']}.yaml"
    merged = json.loads(json.dumps(rec))          # cheap deep copy
    ov = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path.exists() else {}
    rows = {r.get("step"): r for r in ov.get("telemetry", [])}
    for row in merged.get("telemetry", []):
        for k in ORG_FIELDS:
            row.pop(k, None)
        o = rows.get(row["step"])
        if not o or o.get("inherit"):
            continue
        for k in ORG_FIELDS:
            if k in o:
                row[k] = o[k]
    merged["_overlay"] = org
    merged["_overlay_present"] = path.exists()
    return merged


def scenario_metrics(rec: dict) -> dict:
    rows = [r for r in rec.get("telemetry", []) if r.get("kind", "attack-step") == "attack-step"]
    # A proposed row has numbers and is still not scored. It leaves this list here,
    # once, and every metric below inherits the exclusion.
    proposed = [r for r in rows if derive_coverage(r.get("dettect")) is not None
                and r.get("score_provenance") == "agent-proposed"]
    scored = [r for r in rows if derive_coverage(r.get("dettect")) is not None
              and r not in proposed]
    tally = collections.Counter(derive_coverage(r["dettect"]) for r in scored)
    n = len(scored)

    quals = [q for r in scored if (q := (r.get("dettect") or {}).get("quality"))]
    qmean = (sum(sum(q.get(d, 0) for d in QUALITY_DIMS) / len(QUALITY_DIMS) for q in quals)
             / len(quals) / 5) if quals else None

    blind_steps = [r["step"] for r in scored if derive_coverage(r["dettect"]) == "Blind"]
    gaps = [r for r in scored if derive_coverage(r["dettect"]) in ("Blind", "Collectable")]

    return {
        "id": rec["id"],
        "title": rec["title"],
        "status": rec.get("status"),
        "mode": rec["classification"].get("mode", "attack"),
        "priority": rec["classification"]["priority"],
        "evidence": rec["classification"]["evidence"],
        # completeness gates everything: a scenario scored on 2 of 6 rows is not
        # 'mostly covered', it is mostly unmeasured.
        "rows": len(rows),
        "scored": n,
        "proposed": len(proposed),
        "proposed_steps": [r["step"] for r in proposed],
        "completeness": round(n / len(rows), 3) if rows else 0.0,
        "have": round(tally["Have"] / n, 3) if n else None,
        "collectable": round(tally["Collectable"] / n, 3) if n else None,
        "blind": round(tally["Blind"] / n, 3) if n else None,
        "quality": round(qmean, 3) if qmean is not None else None,
        "counts": {"Have": tally["Have"], "Collectable": tally["Collectable"],
                   "Blind": tally["Blind"]},
        "blind_steps": blind_steps,
        "earliest_blind_step": min(blind_steps) if blind_steps else None,
        "forensics_only_steps": [r["step"] for r in scored
                                 if derive_coverage(r["dettect"]) == "Collectable"],
        "exposed": bool(blind_steps) and rec["classification"]["priority"] == "NOW",
        "orphaned_gaps": [r["step"] for r in scored
                          if derive_coverage(r["dettect"]) == "Blind" and not r.get("owner")],
        "unfunded_gaps": [r["step"] for r in gaps if not r.get("backlog_ref")],
        "maturity": maturity_gates(rec, rows, scored),
    }


def maturity_gates(rec: dict, rows: list, scored: list) -> dict:
    """
    The seven process gates of docs/04-measurement.md section 2c, M1 to M7. Maturity
    asks 'is the process working', not 'are we well instrumented'. A scenario can be
    100% Blind and fully mature: it means we know exactly what we cannot see, who owns
    it, and it is funded.

    A scenario is ELIGIBLE for the maturity population only when every attack-step row
    is scored. The gates are still computed for an ineligible record, so a reader can
    see what it owes, but it enters no library level maturity figure.
    """
    prov = rec.get("provenance", {})
    steps = {s["step"] for s in rec.get("attack_path", [])}
    gaps = [r for r in scored if derive_coverage(r["dettect"]) in ("Blind", "Collectable")]
    haves = [r for r in scored if derive_coverage(r["dettect"]) == "Have"]
    hardening = rec.get("hardening") or []
    g = {
        "M1_reviewed": bool(prov.get("reviewed_by"))
                       and prov.get("reviewed_by") != prov.get("authored_by"),
        "M2_scored_in_depth": bool(scored) and all(
            all(d in ((r.get("dettect") or {}).get("quality") or {}) for d in QUALITY_DIMS)
            for r in scored),
        "M3_evidenced": all(r.get("evidence") for r in haves),
        "M4_owned": all(r.get("owner") for r in gaps),
        "M5_closed_loop": all(r.get("backlog_ref") for r in gaps),
        "M6_remediable": bool(hardening) and all(
            h.get("breaks_step") and all(s in steps for s in h["breaks_step"])
            for h in hardening),
        "M7_sourced": (rec["classification"].get("evidence") == "doomsday") or (
            bool(prov.get("sources"))
            and any(s.get("tier") == "0" for s in prov.get("sources") or [])),
    }
    g["eligible"] = bool(rows) and len(scored) == len(rows)
    g["score"] = f"{sum(1 for k, v in g.items() if k.startswith('M') and v is True)}/7"
    return g


def gaming_checks(records: list[dict], metrics: list[dict]) -> list[str]:
    """
    These numbers can be made to look good dishonestly. Each check below
    corresponds to one way of doing it. Run them every time you report.
    """
    out = []
    for rec, m in zip(records, metrics):
        tag = f"{m['id']}"
        if m["completeness"] < 1.0 and m["have"] is not None:
            out.append(f"{tag}: coverage reported on {m['scored']}/{m['rows']} rows, "
                       "partial scoring inflates the ratio")
        if rec.get("status") == "published" and m["proposed"]:
            out.append(f"{tag}: published with agent-proposed scores at steps "
                       f"{m['proposed_steps']}, a published number must have a person "
                       "behind it")
        for r in rec.get("telemetry", []):
            d = r.get("dettect") or {}
            if derive_coverage(d) == "Have" and not r.get("evidence"):
                out.append(f"{tag} step {r['step']}: Have without evidence")
            if d.get("visibility", 0) >= 3 and not (d.get("quality") or {}):
                out.append(f"{tag} step {r['step']}: visibility {d['visibility']} claimed with no "
                           "quality dimensions scored, high visibility is the easiest number to "
                           "overstate")
        if len(rec.get("attack_path", [])) <= 3 and m["have"] == 1.0:
            out.append(f"{tag}: 100% Have on a {len(rec['attack_path'])}-step chain, check the "
                       "scenario has not been narrowed to what we already see")
        if m["orphaned_gaps"]:
            out.append(f"{tag}: gaps with no owner at steps {m['orphaned_gaps']}")
    # evidence reuse: one artifact cited across unrelated scenarios
    by_evidence: dict[str, set[str]] = collections.defaultdict(set)
    for rec in records:
        for r in rec.get("telemetry", []):
            if derive_coverage(r.get("dettect")) == "Have" and r.get("evidence"):
                by_evidence[" ".join(r["evidence"].lower().split())].add(rec["id"])
    for ev, ids in by_evidence.items():
        if len(ids) > 2:
            out.append(f"evidence {ev[:50]!r} backs Have rows in {sorted(ids)}; one artifact "
                       "claiming to see everything should be run against each of those steps")
    ids = [m["id"] for m in metrics]
    if len(ids) != len(set(ids)):
        out.append("duplicate scenario ids in the library")
    return out


def aggregate(metrics: list[dict]) -> dict:
    """Library level figures, docs/04-measurement.md sections 2a to 2c. Step weighted."""
    rows_total = sum(m["rows"] for m in metrics)
    rows_scored = sum(m["scored"] for m in metrics)
    have = sum(m["counts"]["Have"] for m in metrics)
    coll = sum(m["counts"]["Collectable"] for m in metrics)
    blind = sum(m["counts"]["Blind"] for m in metrics)
    coverage = {
        "have": round(have / rows_scored, 3) if rows_scored else None,
        "collectable": round(coll / rows_scored, 3) if rows_scored else None,
        "blind": round(blind / rows_scored, 3) if rows_scored else None,
        "completeness": round(rows_scored / rows_total, 3) if rows_total else None,
        "rows_scored": rows_scored,
        "rows_total": rows_total,
    }
    now = [m for m in metrics if m["priority"] == "NOW"]
    exposed = [m for m in now if m["exposed"]]
    exposure = {
        "now_total": len(now),
        "now_exposed": len(exposed),
        "exposure_rate": round(len(exposed) / len(now), 3) if now else None,
        "orphaned_steps": sum(len(m["orphaned_gaps"]) for m in metrics),
        "unfunded_steps": sum(len(m["unfunded_gaps"]) for m in metrics),
    }
    eligible = [m for m in metrics if m["maturity"]["eligible"]]
    gate_keys = [k for k in ("M1_reviewed", "M2_scored_in_depth", "M3_evidenced", "M4_owned",
                             "M5_closed_loop", "M6_remediable", "M7_sourced")]
    gates = {k.split("_")[0]: (round(sum(1 for m in eligible if m["maturity"][k]) / len(eligible), 3)
                               if eligible else None) for k in gate_keys}
    maturity = {
        "mean": (round(sum(sum(1 for k in gate_keys if m["maturity"][k]) / 7 for m in eligible)
                       / len(eligible), 3) if eligible else None),
        "eligible": len(eligible),
        "assessed": round(len(eligible) / len(metrics), 3) if metrics else None,
        "gates": gates,
    }
    return {"coverage": coverage, "exposure": exposure, "maturity": maturity}


def framework_tuple(base: dict) -> dict:
    """The version tuple. Read from the pinned artifacts' checksum lock when it has been
    populated, so the snapshot records what the computation actually ran against; from
    the baseline file otherwise, and says so."""
    fw = base["frameworks"]
    lock_path = ROOT / "frameworks" / "pinned" / base["baseline"] / "CHECKSUMS.json"
    lock = json.loads(lock_path.read_text()) if lock_path.exists() else {}
    sha = lambda key: (lock.get(key) or {}).get("sha256")
    return {
        "tuple_source": "pinned-artifacts" if lock else "baseline-file",
        "attack": {"version": str(fw["attack"]["version"]),
                   "spec_version": str(fw["attack"]["spec_version"]),
                   "pinned_artifact": fw["attack"]["pinned_artifact"], "sha256": sha("attack")},
        "atlas": {"content_version": str(fw["atlas"]["version"]),
                  "format_version": str(fw["atlas"]["format_version"]),
                  "pinned_artifact": fw["atlas"]["pinned_artifact"], "sha256": sha("atlas")},
        "owasp_llm": {"edition": str(fw["owasp_llm"]["edition"]), "sha256": sha("owasp_llm")},
        "owasp_agentic": {"edition": str(fw["owasp_agentic"]["edition"]),
                          "sha256": sha("owasp_agentic")},
        "dettect": {"version": str(fw["dettect"]["version"]),
                    "targets_attack": str(fw["dettect"]["targets_attack"])},
    }


def repo_state() -> tuple[str | None, bool]:
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                      stderr=subprocess.DEVNULL, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT,
                                             stderr=subprocess.DEVNULL, text=True).strip())
        return sha, dirty
    except (subprocess.CalledProcessError, OSError):
        return None, False


def period_ledgers(records: list[dict], prior: dict | None) -> dict:
    """What changed since the prior snapshot. Without a prior snapshot the ledgers are
    empty lists, which is a statement (nothing to compare) rather than an omission."""
    added, rescored = [], []
    if prior:
        prior_ids = {s["id"] for s in prior.get("scenarios", [])}
        prior_rows = {(s["id"], r["step"]): r for s in prior.get("scenarios", [])
                      for r in s.get("row_coverage", [])}
        for rec in records:
            if rec["id"] not in prior_ids:
                added.append(rec["id"])
                continue
            for r in rec.get("telemetry", []):
                if r.get("kind", "attack-step") != "attack-step":
                    continue
                before = prior_rows.get((rec["id"], r["step"]))
                now = derive_coverage(r.get("dettect"))
                # A first scoring is not a rescore: unscored to scored moves completeness,
                # which is where it belongs. A rescore is a scored tag that changed with
                # no ticket behind it.
                if before is not None and before.get("coverage") is not None \
                        and before.get("coverage") != now and not r.get("backlog_ref"):
                    rescored.append({"id": rec["id"], "step": r["step"],
                                     "from": before.get("coverage"), "to": now,
                                     "backlog_ref": None})
    return {"ids_added_this_period": added, "ids_rescored_this_period": rescored}


def snapshot(records, metrics, org, include_drafts, prior=None, supersedes=None) -> dict:
    baselines = sorted((ROOT / "frameworks").glob("baseline-*.yaml"))
    base = yaml.safe_load(baselines[-1].read_text())
    today = datetime.date.today().isoformat()
    commit, dirty = repo_state()
    org_id = org or "reference"
    # Per row coverage travels with the snapshot so the next one can compute the
    # rescore ledger without re-reading history.
    for rec, m in zip(records, metrics):
        m["row_coverage"] = [{"step": r["step"], "coverage": derive_coverage(r.get("dettect")),
                              "backlog_ref": r.get("backlog_ref")}
                             for r in rec.get("telemetry", [])
                             if r.get("kind", "attack-step") == "attack-step"]
    snap = {
        "snapshot_id": f"{today}-{org_id}-{base['baseline']}",
        "generated": today,
        "generated_by": {"tool": "tools/coverage.py", "repo_commit": commit, "dirty": dirty},
        "org": org_id,
        "baseline": base["baseline"],
        "frameworks": framework_tuple(base),
        "library": {
            "scenarios_total": len(records),
            "by_status": dict(collections.Counter(r.get("status") for r in records)),
            "published_ids": [r["id"] for r in records if r.get("status") == "published"],
            "includes_drafts": bool(include_drafts),
            "retired_this_period": [
                {"id": r["id"], "reason": (r.get("retired") or {}).get("reason", ""),
                 **({"superseded_by": r["retired"]["superseded_by"]}
                    if (r.get("retired") or {}).get("superseded_by") else {})}
                for r in load_retired()
                if not prior or r["id"] not in {s["id"] for s in prior.get("scenarios", [])}
                or True],
            **period_ledgers(records, prior),
        },
        "metrics": aggregate(metrics),
        "scenarios": metrics,
        "gaming": gaming_checks(records, metrics),
        "non_comparable_with": [],
    }
    if supersedes:
        snap["supersedes"] = supersedes
    schema = json.loads((ROOT / "schema" / "snapshot.schema.json").read_text())
    errs = sorted(Draft202012Validator(schema).iter_errors(snap), key=lambda e: list(e.path))
    if errs:
        for e in errs:
            print(f"  snapshot schema: {'/'.join(str(p) for p in e.path)}: {e.message}")
        sys.exit("refusing to write a snapshot that does not match schema/snapshot.schema.json")
    return snap


def bar(v, width=18):
    return "" if v is None else "█" * round(v * width) + "·" * (width - round(v * width))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--org")
    ap.add_argument("--include-drafts", action="store_true")
    ap.add_argument("--json", type=pathlib.Path)
    ap.add_argument("--prior", type=pathlib.Path,
                    help="the previous snapshot, to fill ids_added and ids_rescored")
    ap.add_argument("--supersedes", help="snapshot_id this run corrects")
    ap.add_argument("--gaming", action="store_true")
    args = ap.parse_args()

    records = load_records(args.include_drafts)
    if not records:
        sys.exit("no records. Only 'published' records count by default, "
                 "pass --include-drafts to see work in progress.")
    if args.org:
        records = [apply_overlay(r, args.org) for r in records]
        if not any(r.get("_overlay_present") for r in records):
            sys.exit(f"no overlays found under coverage/{args.org}/. An org with no overlay "
                     "has assessed nothing, and there is nothing to report.")

    metrics = [scenario_metrics(r) for r in records]

    if args.gaming:
        issues = gaming_checks(records, metrics)
        print("\n".join(f"  {i}" for i in issues) if issues else "  no gaming signals")
        return 0

    print(f"\nSCENARIO LIBRARY · {args.org or 'reference assessment'}"
          f" · {len(records)} record(s)\n")
    print(f"{'id':>4}  {'pri':<9} {'cmp':>5} {'prop':>4} {'have':>5} {'coll':>5} {'blind':>5} "
          f"{'qual':>5} {'mat':>5}  coverage")
    for m in metrics:
        print(f"{m['id']:>4}  {m['priority']:<9} "
              f"{m['completeness']:>5.2f} "
              f"{m['proposed'] or '':>4} "
              f"{m['have'] if m['have'] is not None else float('nan'):>5.2f} "
              f"{m['collectable'] if m['collectable'] is not None else float('nan'):>5.2f} "
              f"{m['blind'] if m['blind'] is not None else float('nan'):>5.2f} "
              f"{m['quality'] if m['quality'] is not None else float('nan'):>5.2f} "
              f"{m['maturity']['score']:>5}  {bar(m['have'])}")

    agg = aggregate(metrics)
    cov = agg["coverage"]
    if cov["have"] is not None:
        print(f"\nCOVERAGE   Have {cov['have']:.1%} · Collectable {cov['collectable']:.1%} · "
              f"Blind {cov['blind']:.1%}   step weighted over {cov['rows_scored']} scored rows")
        print(f"           completeness {cov['completeness']:.1%} "
              f"({cov['rows_scored']} of {cov['rows_total']} attack step rows scored)")
    else:
        print(f"\nCOVERAGE   nothing scored. {cov['rows_total']} attack step rows, 0 assessed.")
    unscored = [m["id"] for m in metrics if m["completeness"] == 0]
    if unscored:
        print(f"           {len(unscored)} scenario(s) contribute nothing because they are "
              f"unscored: {', '.join(unscored)}")
        print("           Unscored is not zero. It is absent. Do not average it in.")
    with_prop = [m for m in metrics if m["proposed"]]
    if with_prop:
        n_rows = sum(m["proposed"] for m in with_prop)
        where = ", ".join(f"{m['id']} steps {m['proposed_steps']}" for m in with_prop)
        print(f"\nPROPOSED   {n_rows} agent-proposed row(s) on {len(with_prop)} scenario(s), "
              f"listed here and counted nowhere: {where}")
        print("           A proposal is not a measurement until a person sets "
              "score_provenance to human-session.")

    ex = agg["exposure"]
    print(f"\nEXPOSURE   {ex['now_exposed']} of {ex['now_total']} NOW-priority scenario(s) "
          f"with a Blind step · {ex['orphaned_steps']} orphaned · {ex['unfunded_steps']} unfunded")
    for m in metrics:
        if m["exposed"]:
            print(f"           {m['id']} {m['title'][:52]}  blind at step(s) {m['blind_steps']}"
                  f", earliest {m['earliest_blind_step']}")

    mat = agg["maturity"]
    print(f"\nMATURITY   {mat['eligible']}/{len(metrics)} scenario(s) eligible (every row scored)"
          + (f" · mean {mat['mean']:.2f}" if mat["mean"] is not None else ""))
    for k, v in mat["gates"].items():
        if v is not None and v < 1:
            print(f"           {k} pass rate {v:.0%}")

    issues = gaming_checks(records, metrics)
    if issues:
        print(f"\nINTEGRITY  {len(issues)} signal(s), run --gaming for the list")

    if args.json:
        prior = json.loads(args.prior.read_text()) if args.prior else None
        snap = snapshot(records, metrics, args.org, args.include_drafts, prior, args.supersedes)
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(snap, indent=2))
        print(f"\nsnapshot {snap['snapshot_id']} written to {args.json}")
        print("Keep it. Snapshots are immutable; a correction is a new snapshot with "
              "--supersedes. Trend lines are only meaningful against snapshots that carry "
              "the framework version tuple.")
        if snap["frameworks"]["tuple_source"] == "baseline-file":
            print("NOTE the version tuple came from the baseline file because "
                  "frameworks/pinned/ has no checksums yet. Run tools/pin_frameworks.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
