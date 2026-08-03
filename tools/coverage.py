#!/usr/bin/env python3
"""
Coverage, exposure and maturity rollup. Implements docs/04-measurement.md.

    python tools/coverage.py                        # published records, reference assessment
    python tools/coverage.py --org platform-eng     # apply a coverage/<org>/ overlay
    python tools/coverage.py --include-drafts       # see the whole library, drafts included
    python tools/coverage.py --json out/snap.json   # immutable snapshot for trend reporting
    python tools/coverage.py --gaming               # run the anti-gaming checks only

Three metric families, deliberately kept apart because they answer different
questions for different audiences:

  COVERAGE  proportion of attack steps adequately instrumented.   Engineering.
  EXPOSURE  which NOW-priority scenarios still have Blind steps.  Risk.
  MATURITY  is the PROCESS working: reviewed, scored, owned,      Program.
            evidenced, funded. Moves independently of the other two.

The cardinal rule: an unscored row does not count as zero, it does not count at
all. Scoring nothing and scoring badly must not produce the same number.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

try:
    import yaml
except ImportError:
    sys.exit("pip install pyyaml")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from validate import derive_coverage  # single source of truth for the derivation

ROOT = pathlib.Path(__file__).resolve().parent.parent
QUALITY_DIMS = ("device_completeness", "data_field_completeness",
                "timeliness", "consistency", "retention")


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


def apply_overlay(rec: dict, org: str) -> dict:
    """
    Per-org coverage overlay. The scenario library is org-independent; a given
    org's instrumentation is not. An org may adopt the library without ever
    publishing its coverage -- which is what makes the library politically portable.
    """
    path = ROOT / "coverage" / org / f"{rec['id']}.yaml"
    if not path.exists():
        return rec
    ov = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows = {r.get("step"): r for r in ov.get("telemetry", [])}
    merged = json.loads(json.dumps(rec))          # cheap deep copy
    for row in merged.get("telemetry", []):
        o = rows.get(row["step"])
        if not o or o.get("inherit"):
            continue
        for k in ("dettect", "coverage", "evidence", "owner", "backlog_ref"):
            if k in o:
                row[k] = o[k]
    merged["_overlay"] = org
    return merged


def scenario_metrics(rec: dict) -> dict:
    rows = [r for r in rec.get("telemetry", []) if r.get("kind", "attack-step") == "attack-step"]
    scored = [r for r in rows if derive_coverage(r.get("dettect")) is not None]
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
        "completeness": round(n / len(rows), 3) if rows else 0.0,
        "have": round(tally["Have"] / n, 3) if n else None,
        "collectable": round(tally["Collectable"] / n, 3) if n else None,
        "blind": round(tally["Blind"] / n, 3) if n else None,
        "quality": round(qmean, 3) if qmean is not None else None,
        "blind_steps": blind_steps,
        "exposed": bool(blind_steps) and rec["classification"]["priority"] == "NOW",
        "orphaned_gaps": [r["step"] for r in gaps if not r.get("owner")],
        "unfunded_gaps": [r["step"] for r in gaps if not r.get("backlog_ref")],
        "maturity": maturity_gates(rec, rows, scored),
    }


def maturity_gates(rec: dict, rows: list, scored: list) -> dict:
    """
    Seven binary process gates. Maturity asks 'is the process working', not
    'are we well instrumented'. A scenario can be 100% Blind and fully mature:
    it means we know exactly what we cannot see, who owns it, and it is funded.
    """
    prov = rec.get("provenance", {})
    gaps = [r for r in scored if derive_coverage(r["dettect"]) in ("Blind", "Collectable")]
    haves = [r for r in scored if derive_coverage(r["dettect"]) == "Have"]
    g = {
        "published": rec.get("status") == "published",
        "independently_reviewed": bool(prov.get("reviewed_by"))
                                  and prov.get("reviewed_by") != prov.get("authored_by"),
        "fully_scored": bool(rows) and len(scored) == len(rows),
        "gaps_owned": all(r.get("owner") for r in gaps),
        "haves_evidenced": all(r.get("evidence") for r in haves),
        "gaps_funded": all(r.get("backlog_ref") for r in gaps),
        "hardening_traced": bool(rec.get("hardening"))
                            and all(h.get("breaks_step") for h in rec.get("hardening", [])),
    }
    g["score"] = f"{sum(1 for v in g.values() if v is True)}/7"
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
    ids = [m["id"] for m in metrics]
    if len(ids) != len(set(ids)):
        out.append("duplicate scenario ids in the library")
    return out


def snapshot(records, metrics, org) -> dict:
    base = yaml.safe_load((ROOT / "frameworks" / "baseline-2026.07.yaml").read_text())
    fw = base["frameworks"]
    return {
        # The full version tuple travels with every snapshot. Without it a
        # year-over-year delta cannot be attributed to controls rather than churn.
        "frameworks": {
            "baseline": base["baseline"],
            "attack": f"{fw['attack']['version']} (spec {fw['attack']['spec_version']})",
            "atlas": f"{fw['atlas']['version']} (format {fw['atlas']['format_version']})",
            "owasp_llm": fw["owasp_llm"]["edition"],
            "owasp_agentic": fw["owasp_agentic"]["edition"],
            "dettect": f"{fw['dettect']['version']} against ATT&CK {fw['dettect']['targets_attack']}",
        },
        "library": {
            "org": org or "reference",
            "records": len(records),
            "published": sum(1 for r in records if r.get("status") == "published"),
        },
        "scenarios": metrics,
        "gaming": gaming_checks(records, metrics),
    }


def bar(v, width=18):
    return "" if v is None else "█" * round(v * width) + "·" * (width - round(v * width))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--org")
    ap.add_argument("--include-drafts", action="store_true")
    ap.add_argument("--json", type=pathlib.Path)
    ap.add_argument("--gaming", action="store_true")
    args = ap.parse_args()

    records = load_records(args.include_drafts)
    if not records:
        sys.exit("no records. Only 'published' records count by default, "
                 "pass --include-drafts to see work in progress.")
    if args.org:
        records = [apply_overlay(r, args.org) for r in records]

    metrics = [scenario_metrics(r) for r in records]

    if args.gaming:
        issues = gaming_checks(records, metrics)
        print("\n".join(f"  {i}" for i in issues) if issues else "  no gaming signals")
        return 0

    print(f"\nSCENARIO LIBRARY · {args.org or 'reference assessment'}"
          f" · {len(records)} record(s)\n")
    print(f"{'id':>4}  {'pri':<9} {'cmp':>5} {'have':>5} {'coll':>5} {'blind':>5} "
          f"{'qual':>5} {'mat':>5}  coverage")
    for m in metrics:
        print(f"{m['id']:>4}  {m['priority']:<9} "
              f"{m['completeness']:>5.2f} "
              f"{m['have'] if m['have'] is not None else float('nan'):>5.2f} "
              f"{m['collectable'] if m['collectable'] is not None else float('nan'):>5.2f} "
              f"{m['blind'] if m['blind'] is not None else float('nan'):>5.2f} "
              f"{m['quality'] if m['quality'] is not None else float('nan'):>5.2f} "
              f"{m['maturity']['score']:>5}  {bar(m['have'])}")

    scored = [m for m in metrics if m["completeness"] > 0]
    if scored:
        agg = sum(m["have"] or 0 for m in scored) / len(scored)
        print(f"\nCOVERAGE   mean Have across {len(scored)} scored scenario(s): {agg:.1%}")
        unscored = [m["id"] for m in metrics if m["completeness"] == 0]
        if unscored:
            print(f"           {len(unscored)} scenario(s) contribute nothing because they are "
                  f"unscored: {', '.join(unscored)}")
            print("           Unscored is not zero. It is absent. Do not average it in.")

    exposed = [m for m in metrics if m["exposed"]]
    print(f"\nEXPOSURE   {len(exposed)} NOW-priority scenario(s) with a Blind step")
    for m in exposed:
        print(f"           {m['id']} {m['title'][:52]}  blind at step(s) {m['blind_steps']}")

    full = [m for m in metrics if m["maturity"]["score"] == "7/7"]
    print(f"\nMATURITY   {len(full)}/{len(metrics)} scenario(s) pass all seven process gates")
    failing = collections.Counter()
    for m in metrics:
        for k, v in m["maturity"].items():
            if v is False:
                failing[k] += 1
    for gate, n in failing.most_common():
        print(f"           {n:>3} failing: {gate}")

    issues = gaming_checks(records, metrics)
    if issues:
        print(f"\nINTEGRITY  {len(issues)} signal(s), run --gaming for the list")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(snapshot(records, metrics, args.org), indent=2))
        print(f"\nsnapshot written to {args.json}")
        print("Stamp it with a date and keep it. Trend lines are only meaningful "
              "against snapshots that carry the framework version tuple.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
