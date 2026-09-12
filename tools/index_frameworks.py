#!/usr/bin/env python3
"""
Build the framework reference index from the pinned artifacts.

    python tools/index_frameworks.py                  # baseline 2026.07
    python tools/index_frameworks.py --baseline 2026.07

Reads frameworks/pinned/<baseline>/ and writes frameworks/pinned/<baseline>/index/:

    attack-techniques.json      T-ids: name, tactics, sub-technique flag, revoked, deprecated,
                                revoked_by (the replacement id, walked from the bundle)
    attack-tactics.json         TA-ids: name, shortname
    attack-data-components.json DC-ids: name, deprecated, how many detection strategies cite it
    atlas-techniques.json       AML.T ids: name, maturity, attack-reference (the 37 that have one)
    atlas-tactics.json          AML.TA ids: name
    atlas-mitigations.json      AML.M ids: name
    owasp.json                  LLMnn:edition and ASInn:edition: name, from the baseline file
    INDEX.json                  what was indexed, from which artifact, with its sha256

Why this exists. The records carry framework identifiers, and the doctrine says no
identifier is ever confirmed from memory. The pinned bundles are the authority, and the
ATT&CK bundle is 53 MB of STIX that no validator should parse on every run. The index is
the small, committed, offline projection of the pins: enough to resolve an id to a name,
to know whether it is current, revoked or deprecated, and to walk a revoked id to its
replacement at migration time. Every id in the index traces to an artifact whose sha256
is recorded alongside, so the index is as auditable as the pin.

For the relational model these six files are the seed of the Technique Reference,
Tactic and Data Component tables, one row per identifier per baseline.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import sys

try:
    import yaml
except ImportError:
    sys.exit("pip install pyyaml")

ROOT = pathlib.Path(__file__).resolve().parent.parent


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ext_id(obj: dict, source: str = "mitre-attack") -> str | None:
    for ref in obj.get("external_references", []) or []:
        if ref.get("source_name") == source and ref.get("external_id"):
            return ref["external_id"]
    return None


def index_attack(bundle: pathlib.Path) -> tuple[dict, dict, dict, dict]:
    data = json.loads(bundle.read_text(encoding="utf-8"))
    objs = data["objects"]
    by_stix = {o["id"]: o for o in objs}

    tactics = {}
    short_to_id = {}
    for o in objs:
        if o["type"] == "x-mitre-tactic":
            tid = ext_id(o)
            tactics[tid] = {"name": o["name"], "shortname": o.get("x_mitre_shortname")}
            short_to_id[o.get("x_mitre_shortname")] = tid

    revoked_by = {}
    for o in objs:
        if o["type"] == "relationship" and o.get("relationship_type") == "revoked-by":
            src, tgt = by_stix.get(o["source_ref"]), by_stix.get(o["target_ref"])
            if src and tgt and src["type"] == "attack-pattern":
                revoked_by[ext_id(src)] = ext_id(tgt)

    techniques = {}
    for o in objs:
        if o["type"] != "attack-pattern":
            continue
        tid = ext_id(o)
        if not tid:
            continue
        techniques[tid] = {
            "name": o["name"],
            "tactics": sorted({short_to_id.get(p["phase_name"], p["phase_name"])
                               for p in o.get("kill_chain_phases", []) or []
                               if p.get("kill_chain_name") == "mitre-attack"}),
            "subtechnique": bool(o.get("x_mitre_is_subtechnique")),
            "revoked": bool(o.get("revoked")),
            "deprecated": bool(o.get("x_mitre_deprecated")),
            "revoked_by": revoked_by.get(tid),
            "domains": o.get("x_mitre_domains", []),
        }

    strategy_refs = collections.Counter()
    for o in objs:
        if o["type"] == "x-mitre-analytic":
            for ref in o.get("x_mitre_log_source_references", []) or []:
                strategy_refs[ref.get("x_mitre_data_component_ref")] += 1
    components = {}
    for o in objs:
        if o["type"] == "x-mitre-data-component":
            cid = ext_id(o)
            components[cid] = {"name": o["name"], "deprecated": bool(o.get("x_mitre_deprecated")),
                               "analytics_citing": strategy_refs.get(o["id"], 0)}
    retired_sources = {ext_id(o): o["name"] for o in objs if o["type"] == "x-mitre-data-source"}

    coll = next(o for o in objs if o["type"] == "x-mitre-collection")
    meta = {"version": coll.get("x_mitre_version"),
            "spec_version": coll.get("x_mitre_attack_spec_version"),
            "techniques": len(techniques), "tactics": len(tactics),
            "data_components": len(components),
            "retired_data_sources": len(retired_sources),
            "revoked": sum(1 for t in techniques.values() if t["revoked"]),
            "deprecated": sum(1 for t in techniques.values() if t["deprecated"])}
    return techniques, tactics, components, meta


def index_atlas(path: pathlib.Path) -> tuple[dict, dict, dict, dict]:
    d = yaml.safe_load(path.read_text(encoding="utf-8"))
    techniques = {tid: {"name": t["name"], "maturity": t.get("maturity"),
                        "subtechnique": "." in tid[len("AML.T0000"):],
                        "attack_reference": (t.get("attack-reference") or {}).get("id"),
                        "modified": str(t.get("modified-date")), "uuid": t.get("uuid")}
                  for tid, t in d["techniques"].items()}
    tactics = {tid: {"name": t["name"]} for tid, t in d["tactics"].items()}
    mitigations = {mid: {"name": m["name"]} for mid, m in d["mitigations"].items()}
    meta = {"content_version": str(d["collection"].get("version")),
            "format_version": str(d.get("format-version")),
            "techniques": len(techniques), "tactics": len(tactics),
            "mitigations": len(mitigations),
            "with_attack_reference": sum(1 for t in techniques.values() if t["attack_reference"])}
    return techniques, tactics, mitigations, meta


def index_owasp(base: dict) -> dict:
    fw = base["frameworks"]
    out = {}
    for key, prefix in (("owasp_llm", "LLM"), ("owasp_agentic", "ASI")):
        ed = str(fw[key]["edition"])
        for slot, name in fw[key]["ids"].items():
            out[f"{slot}:{ed}"] = {"name": name, "framework": key, "edition": ed}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baseline", default="2026.07")
    args = ap.parse_args()

    base = yaml.safe_load((ROOT / "frameworks" / f"baseline-{args.baseline}.yaml").read_text())
    pinned = ROOT / "frameworks" / "pinned" / args.baseline
    out = pinned / "index"
    out.mkdir(parents=True, exist_ok=True)
    fw = base["frameworks"]
    manifest = {"baseline": args.baseline, "sources": {}}

    attack_path = pinned / pathlib.Path(fw["attack"]["pinned_artifact"]).name
    if not attack_path.exists():
        sys.exit(f"{attack_path.relative_to(ROOT)} is not vendored. Run tools/pin_frameworks.py")
    techniques, tactics, components, meta = index_attack(attack_path)
    if str(meta["version"]) != str(fw["attack"]["version"]):
        sys.exit(f"pinned bundle is ATT&CK {meta['version']}, baseline says {fw['attack']['version']}")
    (out / "attack-techniques.json").write_text(json.dumps(techniques, indent=1, sort_keys=True))
    (out / "attack-tactics.json").write_text(json.dumps(tactics, indent=1, sort_keys=True))
    (out / "attack-data-components.json").write_text(json.dumps(components, indent=1, sort_keys=True))
    manifest["sources"]["attack"] = {"artifact": attack_path.name, "sha256": sha256(attack_path), **meta}

    atlas_path = pinned / pathlib.Path(fw["atlas"]["pinned_artifact"]).name
    if not atlas_path.exists():
        sys.exit(f"{atlas_path.relative_to(ROOT)} is not vendored. Run tools/pin_frameworks.py")
    a_t, a_ta, a_m, a_meta = index_atlas(atlas_path)
    if a_meta["content_version"] != str(fw["atlas"]["version"]):
        sys.exit(f"pinned ATLAS is {a_meta['content_version']}, baseline says {fw['atlas']['version']}")
    (out / "atlas-techniques.json").write_text(json.dumps(a_t, indent=1, sort_keys=True))
    (out / "atlas-tactics.json").write_text(json.dumps(a_ta, indent=1, sort_keys=True))
    (out / "atlas-mitigations.json").write_text(json.dumps(a_m, indent=1, sort_keys=True))
    manifest["sources"]["atlas"] = {"artifact": atlas_path.name, "sha256": sha256(atlas_path), **a_meta}

    owasp = index_owasp(base)
    (out / "owasp.json").write_text(json.dumps(owasp, indent=1, sort_keys=True))
    manifest["sources"]["owasp"] = {"artifact": f"baseline-{args.baseline}.yaml",
                                    "ids": len(owasp), "note": "OWASP publishes no machine "
                                    "readable artifact; the slot names are transcribed in the "
                                    "baseline file and indexed from there"}

    (out / "INDEX.json").write_text(json.dumps(manifest, indent=2))
    for k, v in manifest["sources"].items():
        print(f"  {k:<8} " + ", ".join(f"{kk} {vv}" for kk, vv in v.items()
                                       if kk not in ("sha256", "note")))
    print(f"\nindex written to {out.relative_to(ROOT)}/. Commit it; it is the offline "
          "authority for every framework id in the records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
