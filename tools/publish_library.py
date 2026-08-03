#!/usr/bin/env python3
"""
Publish the scenario library as one Markdown file per scenario, for indexing.

    python tools/publish_library.py                    # published records -> published/
    python tools/publish_library.py --out /mnt/sharepoint/scenario-library
    python tools/publish_library.py --include-drafts   # clearly banner-marked

Why this exists: YAML is the right capture format and the wrong retrieval format.
SharePoint, Graph and Copilot index prose well and structured data poorly, and when
they index it badly they do so silently, which is worse. Publishing Markdown means the
wide audience (working-group members, other orgs, leadership asking "do we have a
scenario covering X?") can find things, while the library keeps a single source of truth.

Regenerate on every publish. Never hand-edit the output. It is a build artifact, and
an edit here is a divergence nobody will notice until the numbers disagree.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

try:
    import yaml
except ImportError:
    sys.exit("pip install pyyaml")

ROOT = pathlib.Path(__file__).resolve().parent.parent

EVIDENCE = {"seen-in-the-wild": "Seen in the wild",
            "seen-in-research": "Seen in research",
            "doomsday": "DOOMSDAY, hypothetical, never observed"}


def render(rec: dict, incidents: dict, baseline: dict) -> str:
    c = rec["classification"]
    fm = rec["framework_mapping"]
    L = []

    L.append(f"# Scenario {rec['id']} · {rec['title']}\n")

    if rec.get("status") != "published":
        L.append(f"> **DRAFT, status `{rec.get('status')}`.** Not reviewed. Do not cite this "
                 "in a decision or a report. It appears here only so work in progress is "
                 "visible.\n")
    if rec.get("status") == "retired":
        r = rec.get("retired", {})
        L.append(f"> **RETIRED {r.get('date','')}**, {r.get('reason','')}"
                 + (f" Superseded by scenario {r['superseded_by']}." if r.get("superseded_by") else "")
                 + "\n")

    L.append(f"**In plain terms.** {rec['one_liner']}\n")

    L.append("## At a glance\n")
    L.append("| | |\n|---|---|")
    L.append(f"| Priority | **{c['priority']}** |")
    L.append(f"| Evidence | {EVIDENCE.get(c['evidence'], c['evidence'])} |")
    L.append(f"| Mode | {c.get('mode', 'attack')} |")
    L.append(f"| Layer | {c['ai_infrastructure_layer']} |")
    L.append(f"| Primary component | {c['primary_layer_component']} |")
    L.append(f"| Framework baseline | {fm['baseline']} |")
    L.append(f"| Last updated | {rec['provenance'].get('last_updated','')} |\n")

    L.append(f"**Why this priority.**\n")
    for r in c["priority_rationale"]:
        L.append(f"- {r}")
    L.append("")

    L.append("## Attack path\n")
    for s in rec["attack_path"]:
        held = "  *(a control held at this step)*" if s.get("control_held") else ""
        L.append(f"**{s['step']}. [{s['layer']}]** {s['text']}{held}")
        ids = (s.get("attack", []) or []) + (s.get("atlas", []) or [])
        if ids:
            L.append(f"   <br>`{'` `'.join(ids)}`")
        L.append("")

    L.append("## Telemetry and detection map\n")
    L.append("| # | Signal emitted | Where it's emitted | Collected? | Detection opportunity | Owner |")
    L.append("|---|---|---|---|---|---|")
    for r in rec["telemetry"]:
        tag = "control" if r.get("kind") == "control" else r["step"]
        L.append(f"| {tag} | {r['signal']} | {r['emitted_at']} | **{r['coverage']}** | "
                 f"{r['detection_opportunity']} | {r.get('owner',', ')} |")
    L.append("")
    L.append("`Have` = a control emits it and it is wired to detection. "
             "`Collectable` = the source exists but nothing detects on it. "
             "`Blind` = nothing produces it today. "
             "These are derived from DeTT&CT scores, not asserted, see docs/04-measurement.md.\n")

    com = rec.get("commentary") or {}
    if com:
        L.append("## Analysis\n")
        for key, label in (("already_see", "What we can already see"),
                           ("blind", "Where we're blind"),
                           ("how_detect", "How we detect it")):
            if com.get(key):
                L.append(f"**{label}.** {com[key]}\n")

    if rec.get("scaled_up"):
        L.append("## If this scaled up\n")
        L.append(f"*Hypothetical, not observed.* {rec['scaled_up']}\n")

    if rec.get("hardening"):
        L.append("## Hardening, ranked by leverage against this chain\n")
        L.append("| Action | Breaks step | Leverage | Owner | Ticket |")
        L.append("|---|---|---|---|---|")
        for h in rec["hardening"]:
            L.append(f"| {h['action']} | {', '.join(str(s) for s in h['breaks_step'])} | "
                     f"{h.get('leverage',', ')} | {h.get('owner',', ')} | {h.get('backlog_ref',', ')} |")
        L.append("")

    L.append("## Framework mapping\n")
    names = {"attack": "MITRE ATT&CK", "atlas": "MITRE ATLAS",
             "owasp_llm": "OWASP Top 10 for LLM Applications",
             "owasp_agentic": "OWASP Top 10 for Agentic Applications"}
    for key, label in names.items():
        if fm.get(key):
            L.append(f"- **{label}**, `{'` `'.join(fm[key])}`")
    fwv = baseline.get("frameworks", {})
    L.append(f"\nExpressed in baseline **{fm['baseline']}**: ATT&CK "
             f"{fwv.get('attack',{}).get('version','?')}, ATLAS "
             f"{fwv.get('atlas',{}).get('version','?')}, OWASP LLM "
             f"{fwv.get('owasp_llm',{}).get('edition','?')}, OWASP Agentic "
             f"{fwv.get('owasp_agentic',{}).get('edition','?')}.\n")
    if fm.get("mapping_confidence") == "editorial":
        L.append("> **This mapping is editorial, our judgment, not upstream-endorsed.** "
                 "There is no authoritative crosswalk between OWASP and either MITRE framework.\n")
    if fm.get("mapping_notes"):
        L.append(f"{fm['mapping_notes']}\n")

    if rec.get("incidents"):
        L.append("## Grounded in\n")
        for slug in rec["incidents"]:
            inc = incidents.get(slug, {})
            L.append(f"- **{inc.get('title', slug)}**, {inc.get('what_happened','')} "
                     f"*({inc.get('source','source not recorded')})*")
        L.append("")

    prov = rec["provenance"]
    if prov.get("sources"):
        L.append("## Sources\n")
        for s in sorted(prov["sources"], key=lambda s: s["tier"]):
            note = f", {s['note']}" if s.get("note") else ""
            L.append(f"- **Tier {s['tier']}** [{s.get('title', s['url'])}]({s['url']}){note}")
        L.append("")

    L.append("---\n")
    L.append(f"*Record `{rec['id']}-{rec['slug']}.yaml`. "
             f"Authored by {prov.get('authored_by',', ')}, "
             f"reviewed by {prov.get('reviewed_by','not yet reviewed')}"
             ". Generated by `tools/publish_library.py`, do not edit this file; "
             "edit the record and republish.*")
    return "\n".join(L) + "\n"


def index(records: list[dict]) -> str:
    L = ["# Scenario library\n",
         "Every scenario worked as an attack path plus a telemetry and detection map. "
         "Generated from the record library, do not edit.\n",
         "| # | Scenario | Layer | Evidence | Priority | Status |",
         "|---|---|---|---|---|---|"]
    for r in records:
        c = r["classification"]
        L.append(f"| {r['id']} | [{r['title']}]({r['id']}-{r['slug']}.md) | "
                 f"{c['ai_infrastructure_layer']} | {EVIDENCE.get(c['evidence'], c['evidence'])} | "
                 f"**{c['priority']}** | {r.get('status')} |")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "published")
    ap.add_argument("--include-drafts", action="store_true")
    args = ap.parse_args()

    incidents = {p.stem: (yaml.safe_load(p.read_text()) or {})
                 for p in (ROOT / "incidents").glob("*.yaml")}
    baselines = sorted((ROOT / "frameworks").glob("baseline-*.yaml"))
    baseline = yaml.safe_load(baselines[-1].read_text()) if baselines else {}

    records = []
    for p in sorted((ROOT / "scenarios").glob("*.yaml")):
        if p.name.startswith("_"):
            continue
        rec = yaml.safe_load(p.read_text(encoding="utf-8"))
        if rec.get("status") != "published" and not args.include_drafts:
            continue
        records.append(rec)

    if not records:
        sys.exit("nothing published yet. Pass --include-drafts to publish work in progress "
                 "(it will be banner-marked as unreviewed).")

    args.out.mkdir(parents=True, exist_ok=True)
    for rec in records:
        path = args.out / f"{rec['id']}-{rec['slug']}.md"
        path.write_text(render(rec, incidents, baseline), encoding="utf-8")
        print(f"  {path.name}")
    (args.out / "index.md").write_text(index(records), encoding="utf-8")

    print(f"\n{len(records)} scenario(s) + index published to {args.out}")
    print("Point your SharePoint or intranet knowledge source at this directory, and "
          "regenerate it on every publish.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
