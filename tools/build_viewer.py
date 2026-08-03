#!/usr/bin/env python3
"""
Build the Liszt static viewer: a searchable, filterable browser over the scenario
library, plus the coverage dashboard.

    python3 tools/build_viewer.py                      # published records
    python3 tools/build_viewer.py --include-drafts     # everything
    python3 tools/build_viewer.py --org platform-eng   # apply a coverage overlay
    python3 tools/build_viewer.py --out /path/to/dir

Writes two files:

    liszt-viewer.html   one self-contained page. No server, no build step, no
                        network access. Open it from disk, email it, or drop it
                        on SharePoint. Works air-gapped.

                        Includes SESSION MODE: during a tabletop, capture the
                        coverage scores, the exact source a signal comes from,
                        the owner and the ticket, live, on the projected page,
                        and propose a scenario the library does not have yet.
                        Export the result and apply it with
                        tools/apply_session.py.

    liszt-data.json     the same data as a standalone document.

THE JSON IS THE INTEGRATION SEAM. The HTML page is a reference implementation of
one way to present this data, not the only way. A team integrating the library
into an existing web application should consume liszt-data.json and build their
own presentation; its shape is documented in docs/07-viewer-data-contract.md and
is stable within a schema_version.

Regenerate on every publish. Never hand-edit either output.
"""
from __future__ import annotations

import argparse
import collections
import html
import json
import pathlib
import sys

try:
    import yaml
except ImportError:
    sys.exit("pip install pyyaml")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from validate import derive_coverage          # one source of truth for the rule
from coverage import load_records, apply_overlay, scenario_metrics, QUALITY_DIMS

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_VERSION = 1


def jsonable(o):
    """YAML parses unquoted dates into date objects; JSON has no date type."""
    import datetime
    if isinstance(o, (datetime.date, datetime.datetime)):
        return o.isoformat()
    raise TypeError(f"not JSON serializable: {type(o).__name__}")


# ── data ────────────────────────────────────────────────────────────────────

def build_data(include_drafts: bool, org: str | None) -> dict:
    records = load_records(include_drafts)
    if org:
        records = [apply_overlay(r, org) for r in records]

    incidents = {p.stem: (yaml.safe_load(p.read_text(encoding="utf-8")) or {})
                 for p in (ROOT / "incidents").glob("*.yaml")}

    # Use case records travel whole, like scenarios: the page is one presentation
    # of them, and a JSON consumer gets the same record the validator checked.
    use_cases = [uc for p in sorted((ROOT / "use-cases").glob("*.yaml"))
                 if not p.name.startswith("_")
                 and (uc := yaml.safe_load(p.read_text(encoding="utf-8")))]
    covered_by: dict[str, list[str]] = collections.defaultdict(list)
    for uc in use_cases:
        for c in uc.get("covers", []) or []:
            sid = str(c.get("scenario"))
            if uc.get("id") and uc["id"] not in covered_by[sid]:
                covered_by[sid].append(uc["id"])

    baselines = sorted((ROOT / "frameworks").glob("baseline-*.yaml"))
    baseline = yaml.safe_load(baselines[-1].read_text(encoding="utf-8")) if baselines else {}
    fw = baseline.get("frameworks", {})

    scenarios, framework_index = [], collections.defaultdict(lambda: collections.defaultdict(list))
    for rec in records:
        m = scenario_metrics(rec)
        rows = rec.get("telemetry", [])
        counts = collections.Counter(
            derive_coverage(r.get("dettect")) or "Unscored" for r in rows)
        scenarios.append({
            **{k: rec.get(k) for k in ("id", "slug", "title", "one_liner", "status",
                                       "attack_path", "telemetry", "commentary",
                                       "scaled_up", "hardening", "incidents",
                                       "framework_mapping", "classification",
                                       "provenance")},
            "metrics": m,
            "counts": dict(counts),
            "use_case_ids": covered_by.get(rec["id"], []),
        })
        fmm = rec.get("framework_mapping", {})
        for key in ("attack", "atlas", "owasp_llm", "owasp_agentic"):
            for fid in fmm.get(key, []) or []:
                framework_index[key][fid].append(rec["id"])

    scored = [s for s in scenarios if s["metrics"]["completeness"] > 0]
    exposed = [s for s in scenarios if s["metrics"]["exposed"]]
    full_maturity = [s for s in scenarios if s["metrics"]["maturity"]["score"] == "7/7"]

    return {
        "data_version": DATA_VERSION,
        "generated_by": "tools/build_viewer.py",
        "view": {"org": org or "reference assessment",
                 "includes_drafts": bool(include_drafts)},
        "baseline": {
            "id": baseline.get("baseline"),
            "attack": f"{fw.get('attack', {}).get('version', '?')}",
            "attack_spec": fw.get("attack", {}).get("spec_version"),
            "atlas": fw.get("atlas", {}).get("version"),
            "atlas_format": fw.get("atlas", {}).get("format_version"),
            "owasp_llm": fw.get("owasp_llm", {}).get("edition"),
            "owasp_agentic": fw.get("owasp_agentic", {}).get("edition"),
            "dettect": fw.get("dettect", {}).get("version"),
        },
        "library": {
            "records": len(scenarios),
            "published": sum(1 for s in scenarios if s["status"] == "published"),
            "scored": len(scored),
            "unscored_ids": [s["id"] for s in scenarios if s["metrics"]["completeness"] == 0],
            # mean Have across SCORED scenarios only. An unscored record is absent,
            # not zero, and is never averaged in.
            "mean_have": (round(sum(s["metrics"]["have"] or 0 for s in scored) / len(scored), 4)
                          if scored else None),
            "exposed": len(exposed),
            "full_maturity": len(full_maturity),
        },
        "owasp_names": {**fw.get("owasp_llm", {}).get("ids", {}),
                        **fw.get("owasp_agentic", {}).get("ids", {})},
        "scenarios": scenarios,
        "use_cases": use_cases,
        "incidents": incidents,
        "frameworks": {k: dict(v) for k, v in framework_index.items()},
    }


# ── page ────────────────────────────────────────────────────────────────────
# Status palette. Validated with the dataviz palette validator against a light
# surface: lightness band, chroma floor, CVD separation (worst adjacent pair
# protan dE 8.2), normal-vision floor and contrast all pass. Every use is
# accompanied by its text label, so state is never carried by color alone.

CSS = """
:root{
  --ink:#1F2D38; --ink-2:#3C4C58; --muted:#5B6B78; --rule:#D9DEE3;
  --surface:#FFFFFF; --surface-2:#F4F6F8; --surface-3:#EBEFF3;
  --brand:#2C6E8F; --brand-ink:#1E5069;
  --have:#1E7F4B; --collectable:#B5852B; --blind:#B0463B; --unscored:#9AA7B1;
  --have-bg:#E9F3EE; --collectable-bg:#FAF3E2; --blind-bg:#FBEEEC;
  --now:#2C6E8F; --near-term:#5E8DA8; --backlog:#8FA3B0;
  --radius:8px; --shadow:0 1px 2px rgba(31,45,56,.06),0 4px 12px rgba(31,45,56,.05);
  --sans:"Segoe UI",Calibri,-apple-system,BlinkMacSystemFont,Roboto,Helvetica,Arial,sans-serif;
  --serif:Cambria,Georgia,"Times New Roman",serif;
  --mono:Consolas,"SF Mono",Menlo,monospace;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{font-family:var(--sans);color:var(--ink);background:var(--surface-2);
     font-size:14px;line-height:1.55;-webkit-font-smoothing:antialiased}
a{color:var(--brand)}
.wrap{max-width:1500px;margin:0 auto;padding:0 24px}

/* one focus treatment everywhere. Keyboard users get the same brand ring on
   tabs, cards, chips and buttons; text fields get an inset ring on any focus. */
:focus-visible{outline:2px solid var(--brand);outline-offset:2px}
input:focus-visible,select:focus-visible,
.filters input:focus,.filters select:focus{outline:2px solid var(--brand);
  outline-offset:-1px;border-color:var(--brand)}
.sessionbar :focus-visible{outline-color:#fff}

/* header ------------------------------------------------------------------ */
header{background:var(--surface);border-bottom:1px solid var(--rule);
       position:sticky;top:0;z-index:40}
.hd{display:flex;align-items:baseline;gap:18px;padding:16px 0 14px}
.logo{font-weight:700;letter-spacing:.22em;color:var(--brand);font-size:13px}
h1{font-family:var(--serif);font-size:22px;font-weight:700;margin:0}
.hd .meta{margin-left:auto;color:var(--muted);font-size:12px;text-align:right}
nav{display:flex;gap:2px;padding-bottom:0}
nav button{appearance:none;border:0;background:none;font:inherit;cursor:pointer;
  padding:9px 16px;color:var(--muted);border-bottom:2px solid transparent;font-weight:600}
nav button:hover{color:var(--ink);background:var(--surface-2)}
nav button[aria-current="page"]{color:var(--brand);border-bottom-color:var(--brand)}
/* the session switch is an action, not a tab: give it a button shape */
nav .navact{margin:4px 0 8px auto;border:1px solid var(--rule);border-radius:6px;
  padding:5px 13px;color:var(--brand);font-weight:600;border-bottom-width:1px}
nav .navact:hover{border-color:var(--brand);background:#F3F7FA;color:var(--brand-ink)}

/* stat tiles -------------------------------------------------------------- */
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
       gap:12px;margin:20px 0}
.tile{background:var(--surface);border:1px solid var(--rule);border-radius:var(--radius);
      padding:14px 16px}
.tile .n{font-size:30px;font-weight:700;line-height:1.1;font-variant-numeric:tabular-nums}
.tile .l{font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);
         font-weight:700;margin-top:5px}
.tile .s{font-size:12px;color:var(--muted);margin-top:3px}

/* filters ----------------------------------------------------------------- */
.filters{display:flex;flex-wrap:wrap;gap:8px;align-items:center;
  background:var(--surface);border:1px solid var(--rule);border-radius:var(--radius);
  padding:10px 12px;margin-bottom:16px}
.filters input[type=search]{flex:1 1 240px;min-width:200px;font:inherit;padding:7px 10px;
  border:1px solid var(--rule);border-radius:6px;background:var(--surface)}
.filters select{font:inherit;padding:7px 8px;border:1px solid var(--rule);
  border-radius:6px;background:var(--surface);color:var(--ink)}
.filters .clear{margin-left:auto;font:inherit;border:1px solid var(--rule);background:var(--surface);
  border-radius:6px;padding:7px 12px;cursor:pointer;color:var(--muted)}
.filters .clear:hover{color:var(--ink);border-color:var(--muted)}
.count{color:var(--muted);font-size:12px;padding:0 4px}

/* layout ------------------------------------------------------------------ */
.split{display:grid;grid-template-columns:minmax(340px,420px) 1fr;gap:16px;
       align-items:start;padding-bottom:48px}
@media(max-width:1000px){.split{grid-template-columns:1fr}}
.list{display:flex;flex-direction:column;gap:8px;max-height:calc(100vh - 300px);
      overflow:auto;padding-right:4px}

/* scenario card ----------------------------------------------------------- */
.card{background:var(--surface);border:1px solid var(--rule);border-radius:var(--radius);
      padding:12px 14px;cursor:pointer;text-align:left;font:inherit;color:inherit;width:100%}
.card:hover{border-color:var(--brand)}
.card[aria-selected="true"]{border-color:var(--brand);box-shadow:0 0 0 1px var(--brand)}
.card .top{display:flex;align-items:center;gap:8px;margin-bottom:5px}
.card .id{font-family:var(--mono);font-size:12px;color:var(--muted)}
.card .t{font-weight:600;line-height:1.35;margin:2px 0 8px}
.card .sub{font-size:12px;color:var(--muted);display:flex;gap:10px;flex-wrap:wrap;margin-top:7px}

/* chips ------------------------------------------------------------------- */
.chip{display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:700;
  letter-spacing:.03em;padding:2px 8px;border-radius:999px;white-space:nowrap}
.chip.now{background:#E7EEF3;color:#1E5069}
.chip.near-term{background:#EDF2F5;color:#3F6E88}
.chip.backlog,.chip.muted{background:var(--surface-3);color:var(--muted)}
.chip.draft{background:var(--surface-3);color:var(--muted)}
.chip.published{background:var(--have-bg);color:var(--have)}
.chip.wild{background:var(--blind-bg);color:var(--blind)}
.chip.research{background:var(--collectable-bg);color:#8A6318}
.chip.doomsday{background:#3B2730;color:#fff}
.chip.Have{background:var(--have-bg);color:var(--have)}
.chip.Collectable{background:var(--collectable-bg);color:#8A6318}
.chip.Blind{background:var(--blind-bg);color:var(--blind)}
.chip.Unscored{background:var(--surface-3);color:var(--muted)}
.dot{width:8px;height:8px;border-radius:2px;flex:none}
.dot.Have{background:var(--have)}.dot.Collectable{background:var(--collectable)}
.dot.Blind{background:var(--blind)}.dot.Unscored{background:var(--unscored)}

/* coverage bar ------------------------------------------------------------ */
/* Segments are separated by a 2px surface gap and the outer ends are rounded,
   per the mark spec. Every segment carries a tooltip; the legend is always
   present, so state is never conveyed by color alone. */
.bar{display:flex;gap:2px;height:10px;border-radius:4px;overflow:hidden;background:var(--surface-3)}
.bar span{display:block;height:100%}
.bar span:first-child{border-radius:4px 0 0 4px}
.bar span:last-child{border-radius:0 4px 4px 0}
.bar span.Have{background:var(--have)}.bar span.Collectable{background:var(--collectable)}
.bar span.Blind{background:var(--blind)}.bar span.Unscored{background:var(--unscored)}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin:10px 0 0}
.legend .k{display:inline-flex;align-items:center;gap:6px}

/* detail ------------------------------------------------------------------ */
.detail{background:var(--surface);border:1px solid var(--rule);border-radius:var(--radius);
        padding:22px 24px;min-height:400px}
.detail h2{font-family:var(--serif);font-size:23px;margin:0 0 4px}
.detail .lede{color:var(--ink-2);margin:10px 0 18px;max-width:76ch}
.detail h3{font-size:12px;letter-spacing:.09em;text-transform:uppercase;color:var(--brand);
  font-weight:700;margin:26px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--rule)}
.kv{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:4px}

.steps{display:flex;flex-direction:column;gap:0}
.step{display:grid;grid-template-columns:26px 1fr;gap:10px;padding:9px 0;
      border-bottom:1px solid var(--surface-3)}
.step:last-child{border-bottom:0}
.step .n{font-weight:700;color:var(--blind);font-variant-numeric:tabular-nums}
.step .layer{font-size:11px;font-weight:700;color:var(--brand);margin-right:6px}
.step .ids{margin-top:5px;display:flex;gap:5px;flex-wrap:wrap}
.held{display:inline-block;font-size:11px;font-weight:700;color:var(--have);
      background:var(--have-bg);border-radius:4px;padding:1px 7px;margin-left:6px}

table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;font-size:11px;letter-spacing:.06em;text-transform:uppercase;
   color:var(--muted);font-weight:700;padding:7px 8px;border-bottom:1px solid var(--rule)}
td{padding:9px 8px;border-bottom:1px solid var(--surface-3);vertical-align:top}
tbody tr:last-child td{border-bottom:0}
td.num{font-variant-numeric:tabular-nums;color:var(--muted);width:26px}
code.mono{font-family:var(--mono);font-size:12px}
.tag{font-family:var(--mono);font-size:11px;background:var(--surface-3);color:var(--ink-2);
     border-radius:4px;padding:1px 6px;white-space:nowrap}
.scores{font-family:var(--mono);font-size:11px;color:var(--muted);white-space:nowrap}
.note{background:var(--surface-2);border:1px solid var(--rule);border-radius:6px;
      padding:12px 14px;color:var(--ink-2);font-size:13px;margin:10px 0}
.empty{color:var(--muted);padding:60px 20px;text-align:center}
ul.plain{margin:0;padding-left:18px}
ul.plain li{margin-bottom:5px}

/* coverage view ----------------------------------------------------------- */
.rowbar{display:grid;grid-template-columns:42px minmax(180px,1fr) 220px 74px;gap:12px;
        align-items:center;padding:8px 0;border-bottom:1px solid var(--surface-3)}
.rowbar:last-child{border-bottom:0}
.rowbar .pct{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
.panel{background:var(--surface);border:1px solid var(--rule);border-radius:var(--radius);
       padding:20px 24px;margin-bottom:16px}
.panel h3{font-family:var(--serif);font-size:19px;margin:0 0 4px;text-transform:none;
  letter-spacing:0;color:var(--ink);border:0;padding:0}
.panel .sub{color:var(--muted);font-size:13px;margin-bottom:16px}
.toggle{font:inherit;font-size:12px;border:1px solid var(--rule);background:var(--surface);
  border-radius:6px;padding:5px 11px;cursor:pointer;color:var(--muted)}
.toggle:hover{color:var(--ink)}
.fw{display:grid;grid-template-columns:130px 1fr;gap:10px;padding:7px 0;
    border-bottom:1px solid var(--surface-3);align-items:start}
.fw:last-child{border-bottom:0}

/* session mode ------------------------------------------------------------ */
.sessionbar{background:var(--brand);color:#fff;font-size:13px}
.sessionbar .wrap{display:flex;align-items:center;gap:14px;padding:8px 24px;max-width:1500px}
.sessionbar strong{font-weight:700;letter-spacing:.06em}
.sessionbar input{font:inherit;font-size:13px;padding:4px 8px;border:0;border-radius:5px;
  background:rgba(255,255,255,.16);color:#fff;width:190px}
.sessionbar input::placeholder{color:rgba(255,255,255,.7)}
.sessionbar .right{margin-left:auto;display:flex;gap:8px;align-items:center}
.sessionbar button{font:inherit;font-size:12px;font-weight:600;border:1px solid rgba(255,255,255,.45);
  background:transparent;color:#fff;border-radius:5px;padding:4px 11px;cursor:pointer}
.sessionbar button:hover{background:rgba(255,255,255,.14)}
.sessionbar .pill{background:#fff;color:var(--brand);border-radius:999px;padding:2px 9px;font-weight:700}
body.session .detail{border-color:var(--brand);box-shadow:0 0 0 1px var(--brand)}

.ec{border:1px solid var(--rule);border-radius:var(--radius);padding:14px 16px;margin-bottom:10px;
    background:var(--surface)}
.ec.changed{border-color:var(--brand);background:#FAFCFD}
.ec .hdr{display:flex;align-items:baseline;gap:10px;margin-bottom:2px}
.ec .hdr .n{font-weight:700;color:var(--blind);font-variant-numeric:tabular-nums;min-width:18px}
.ec .hdr .sig{font-weight:700;font-size:15px}
.ec .hdr .mark{margin-left:auto;font-size:11px;font-weight:700;color:var(--brand)}
.ec .cat{color:var(--muted);font-size:12px;margin:0 0 12px 28px}
.ec .grid{display:grid;grid-template-columns:1fr 1fr auto;gap:12px;align-items:end;margin-left:28px}
@media(max-width:820px){.ec .grid{grid-template-columns:1fr}}
.fld{display:flex;flex-direction:column;gap:4px;margin-left:28px;margin-top:11px}
.fld.inline{margin-left:0;margin-top:0}
.fld label{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;
  color:var(--muted)}
.fld .hint{font-size:11px;color:var(--muted)}
.fld select.fld input{font:inherit;font-size:13px;padding:7px 9px;border:1px solid var(--rule);
  border-radius:6px;background:var(--surface);color:var(--ink);width:100%}
.fld select:focus.fld input:focus{outline:2px solid var(--brand);outline-offset:-1px;border-color:var(--brand)}
.ec .verdict{display:flex;align-items:center;justify-content:center;min-width:118px;
  border-radius:6px;padding:9px 12px;font-weight:700;font-size:14px;text-align:center}
.ec .verdict.Have{background:var(--have-bg);color:var(--have);border:1px solid var(--have)}
.ec .verdict.Collectable{background:var(--collectable-bg);color:#8A6318;border:1px solid var(--collectable)}
.ec .verdict.Blind{background:var(--blind-bg);color:var(--blind);border:1px solid var(--blind)}
.ec .verdict.Unscored{background:var(--surface-3);color:var(--muted);border:1px solid var(--rule)}
.ec .two{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-left:28px;margin-top:11px}
@media(max-width:820px){.ec .two{grid-template-columns:1fr}}

/* proposed new scenarios --------------------------------------------------- */
.prop{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:start;
      padding:9px 0;border-bottom:1px solid var(--surface-3)}
.prop:last-of-type{border-bottom:0}
.prop .t{font-weight:600}
.prop .m{color:var(--muted);font-size:12px;margin-top:2px}
.prop button{font:inherit;font-size:12px;border:1px solid var(--rule);background:var(--surface);
  border-radius:6px;padding:4px 11px;cursor:pointer;color:var(--muted)}
.prop button:hover{color:var(--blind);border-color:var(--blind)}
.err{color:var(--blind);font-size:12px;font-weight:700;margin-top:8px}

/* use cases ---------------------------------------------------------------- */
/* Lifecycle and autonomy chips reuse the established chip pairs; the four
   coverage status colors are untouched. Every chip carries its text label, so
   state is never carried by color alone. */
.chip.proposed{background:var(--surface-3);color:var(--muted)}
.chip.built{background:#E7EEF3;color:#1E5069}
.chip.tuned{background:var(--have-bg);color:var(--have)}
.chip.retired{background:var(--surface-3);color:var(--muted)}
.chip.notify{background:var(--surface-3);color:var(--ink-2)}
.chip.assisted{background:var(--collectable-bg);color:#8A6318}
.chip.autonomous{background:var(--blind-bg);color:var(--blind)}
.chip.uclink{text-decoration:none;background:#E7EEF3;color:#1E5069}
.chip.uclink:hover{background:var(--brand);color:#fff}
.uc{background:var(--surface);border:1px solid var(--rule);border-radius:var(--radius);
    padding:18px 20px;margin-bottom:14px}
.uc.sel{border-color:var(--brand);box-shadow:0 0 0 1px var(--brand)}
.uc .hdr{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:4px}
.uc .hdr .id{font-family:var(--mono);font-size:12px;color:var(--muted)}
.uc h4{font-family:var(--serif);font-size:18px;margin:2px 0 10px}
.ucrow{display:grid;grid-template-columns:118px 1fr;gap:10px;padding:7px 0;
       border-bottom:1px solid var(--surface-3);align-items:start}
.ucrow:last-of-type{border-bottom:0}
.ucrow .k{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);
          font-weight:700;padding-top:2px}
.ucrow .src{color:var(--muted);font-size:12px}
.role{display:inline-block;font-size:11px;font-weight:700;color:var(--brand-ink);
      background:#E7EEF3;border-radius:4px;padding:1px 7px;margin-right:6px}
.uc .limits{background:var(--surface-2);border-left:3px solid var(--collectable);
            border-radius:0 6px 6px 0;padding:10px 14px;color:var(--ink-2);font-size:13px;
            margin-top:12px}
.uc .limits .k{font-size:11px;letter-spacing:.06em;text-transform:uppercase;
               color:var(--muted);font-weight:700;display:block;margin-bottom:4px}

.rb{border-left:3px solid var(--brand);padding:2px 0 2px 14px;margin-bottom:16px}
.rb h4{margin:0 0 6px;font-size:15px}
.rb .line{font-size:13px;color:var(--ink-2);padding:3px 0}
.rb .was{color:var(--muted)}
.danger{border-color:var(--blind) !important;color:var(--blind) !important}

footer{color:var(--muted);font-size:12px;padding:24px 0 40px;border-top:1px solid var(--rule);
       margin-top:8px}
[hidden]{display:none !important}
"""

JS = r"""
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const pct = (v) => v == null ? "n/a" : (v * 100).toFixed(0) + "%";
const ORDER = ["Have", "Collectable", "Blind", "Unscored"];
const EV = { "seen-in-the-wild": ["wild", "Seen in the wild"],
             "seen-in-research": ["research", "Seen in research"],
             "doomsday": ["doomsday", "Doomsday"] };

const state = { view: "scenarios", sel: null, q: "", priority: "", evidence: "",
                layer: "", status: "", cov: "", table: false };

/* ---------- session capture ----------
   Everything typed during a session is held here, never written over the record.
   Export produces a session file; tools/apply_session.py writes it into the YAML
   with the validator in the loop. The page itself is never a system of record. */
const SKEY = "liszt.session.v1";
const session = { active: false, facilitator: "", recorded: "", changes: {}, newScenarios: [] };

/* A scenario the room says is missing. Captured as a few plain answers, never as a
   record: tools/apply_session.py turns each one into a draft record with the next free
   id and the right filename, and an analyst does the work from there. */
const NEW_MODES = [["attack", "attack, somebody is driving it"],
                   ["failure", "failure, nobody is driving it and something breaks on its own"]];
const NEW_LAYERS = ["L0 · Infrastructure", "L1 · Data", "L2 · Model",
                    "L3 · Orchestration & Agent", "L4 · Application"];
const NEW_PRIORITIES = [["NOW", "NOW, this is the cycle we spend on it"],
                        ["NEAR-TERM", "NEAR-TERM, the cycle after this one"],
                        ["BACKLOG", "BACKLOG, real but not now"]];
let proposeOpen = false;

const VIS = [[0, "0  None. Nothing produces this"], [1, "1  Minimal. One aspect visible"],
             [2, "2  Medium. Several aspects visible"], [3, "3  Good. Almost all aspects"],
             [4, "4  Excellent. All aspects visible"]];
const DET = [[-1, "-1  None. Nothing looks at it"], [0, "0  Logged only. No alert is raised"],
             [1, "1  Basic. Simple rule, noisy"], [2, "2  Fair. Correlation rule"],
             [3, "3  Good. Real-time analytics"], [4, "4  Very good. Few false negatives"],
             [5, "5  Excellent. All aspects covered"]];

function loadSession() {
  try {
    const raw = localStorage.getItem(SKEY);
    if (raw) Object.assign(session, JSON.parse(raw));
  } catch (e) { /* private mode or file:// restrictions. Held in memory instead. */ }
  // A session saved before proposals existed has no list. Absent means empty, not broken.
  if (!Array.isArray(session.newScenarios)) session.newScenarios = [];
}
function saveSession() {
  try { localStorage.setItem(SKEY, JSON.stringify(session)); }
  catch (e) { markVolatile(); }
}
let warnedVolatile = false;
function markVolatile() {
  if (warnedVolatile) return;
  warnedVolatile = true;
  const el = document.getElementById("volatile");
  if (el) el.hidden = false;
}

const chg = (sid) => (session.changes[sid] ||= { telemetry: {}, notes: "", use_case_note: "" });
function setRow(sid, step, key, value) {
  const c = chg(sid);
  (c.telemetry[step] ||= {})[key] = value;
  session.recorded = session.recorded || new Date().toISOString().slice(0, 10);
  saveSession();
}
function rowChange(sid, step) {
  return ((session.changes[sid] || {}).telemetry || {})[step] || {};
}
/* The row as it currently stands: the record, with anything captured this session
   laid over it. Every view uses this, so the bars and the figures move as the room
   talks. */
function effRow(sid, row) {
  const u = rowChange(sid, row.step);
  return { ...row, ...u, dettect: u.dettect || row.dettect };
}
function effCoverage(sid, row) {
  const d = effRow(sid, row).dettect;
  if (!d || d.visibility == null || d.detection == null) return "Unscored";
  return d.visibility === 0 ? "Blind" : (d.detection >= 1 ? "Have" : "Collectable");
}
function effCounts(s) {
  const c = {};
  (s.telemetry || []).forEach(r => { const k = effCoverage(s.id, r); c[k] = (c[k] || 0) + 1; });
  return c;
}
function effHave(s) {
  const rows = (s.telemetry || []).filter(r => effCoverage(s.id, r) !== "Unscored");
  if (!rows.length) return null;
  return rows.filter(r => effCoverage(s.id, r) === "Have").length / rows.length;
}
const changedCount = () => Object.values(session.changes)
  .reduce((n, c) => n + Object.keys(c.telemetry || {}).length + (c.notes ? 1 : 0)
                      + (c.use_case_note ? 1 : 0), 0);
const changedScenarios = () => Object.keys(session.changes)
  .filter(k => Object.keys(session.changes[k].telemetry || {}).length || session.changes[k].notes
               || session.changes[k].use_case_note)
  .sort();

/* ---------- shared pieces ---------- */
function bar(counts, total) {
  if (!total) return '<div class="bar"></div>';
  return '<div class="bar">' + ORDER.filter(k => counts[k]).map(k =>
    `<span class="${k}" style="width:${(counts[k] / total * 100).toFixed(2)}%" ` +
    `title="${k}: ${counts[k]} of ${total} step${total === 1 ? "" : "s"}"></span>`).join("") + "</div>";
}
const legend = () => '<div class="legend">' + ORDER.map(k =>
  `<span class="k"><i class="dot ${k}"></i>${k}</span>`).join("") +
  '<span class="k" style="margin-left:auto">Coverage is calculated from the DeTT&amp;CT scores, never entered directly.</span></div>';

/* ---------- filtering ---------- */
function matches(s) {
  const q = state.q.trim().toLowerCase();
  if (q) {
    const hay = [s.id, s.title, s.one_liner, ...(s.attack_path || []).map(a => a.text), ...(s.telemetry || []).map(t => `${t.signal} ${t.emitted_at} ${t.detection_opportunity}`), ...Object.values(s.framework_mapping || {}).flat().filter(v => typeof v === "string"),
    ].join(" ").toLowerCase();
    if (!hay.includes(q)) return false;
  }
  if (state.priority && s.classification.priority !== state.priority) return false;
  if (state.evidence && s.classification.evidence !== state.evidence) return false;
  if (state.layer && s.classification.ai_infrastructure_layer !== state.layer) return false;
  if (state.status && s.status !== state.status) return false;
  if (state.cov === "blind" && !s.metrics.blind_steps.length) return false;
  if (state.cov === "exposed" && !s.metrics.exposed) return false;
  if (state.cov === "unscored" && s.metrics.completeness > 0) return false;
  if (state.cov === "orphan" && !s.metrics.orphaned_gaps.length) return false;
  return true;
}

/* ---------- list ---------- */
function renderList() {
  const rows = DATA.scenarios.filter(matches);
  $("#count").textContent = `${rows.length} of ${DATA.scenarios.length}`;
  $("#list").innerHTML = rows.length ? rows.map(s => {
    const total = (s.telemetry || []).length;
    const [ecls, elabel] = EV[s.classification.evidence] || ["", s.classification.evidence];
    return `<button class="card" data-id="${s.id}" aria-selected="${state.sel === s.id}">
      <div class="top"><span class="id">${esc(s.id)}</span>
        <span class="chip ${s.classification.priority.toLowerCase()}">${s.classification.priority}</span>
        <span class="chip ${ecls}">${esc(elabel)}</span>
        ${s.status !== "published" ? `<span class="chip draft">${esc(s.status)}</span>` : ""}</div>
      <div class="t">${esc(s.title)}</div>
      ${bar(effCounts(s), total)}
      <div class="sub"><span>${esc(s.classification.ai_infrastructure_layer)}</span>
        <span>${total} step${total === 1 ? "" : "s"}</span>
        ${effHave(s) != null ? `<span>${pct(effHave(s))} Have</span>`
                            : "<span>not scored</span>"}</div>
    </button>`;
  }).join("") : '<div class="empty">No scenario matches these filters.</div>';
  $$("#list .card").forEach(b => b.onclick = () => select(b.dataset.id));
}

/* ---------- detail ---------- */
function renderDetail() {
  const s = DATA.scenarios.find(x => x.id === state.sel);
  const el = $("#detail");
  if (!s) {
    el.innerHTML = '<div class="empty">Select a scenario.</div>';
    return;
  }
  const fm = s.framework_mapping || {}, total = (s.telemetry || []).length;
  const idTags = (a) => (a || []).map(v => `<span class="tag">${esc(v)}</span>`).join(" ");
  const fwRow = (label, ids) => ids && ids.length
    ? `<div class="fw"><div style="color:var(--muted);font-size:12px">${label}</div>
         <div>${idTags(ids)}</div></div>` : "";

  el.innerHTML = `
    <div class="kv">
      <span class="chip ${s.classification.priority.toLowerCase()}">${s.classification.priority}</span>
      <span class="chip ${(EV[s.classification.evidence] || [""])[0]}">${esc((EV[s.classification.evidence] || ["", s.classification.evidence])[1])}</span>
      <span class="chip ${s.status === "published" ? "published" : "draft"}">${esc(s.status)}</span>
      <span class="chip muted">${esc(s.classification.ai_infrastructure_layer)}</span>
    </div>
    <h2>Scenario ${esc(s.id)} &middot; ${esc(s.title)}</h2>
    <p class="lede">${esc(s.one_liner)}</p>

    <h3>Why this priority</h3>
    <ul class="plain">${(s.classification.priority_rationale || []).map(r => `<li>${esc(r)}</li>`).join("")}</ul>

    <h3>Attack path</h3>
    <div class="steps">${(s.attack_path || []).map(a => `
      <div class="step"><div class="n">${a.step}</div><div>
        <span class="layer">[${esc(a.layer)}]</span>${esc(a.text)}
        ${a.control_held ? '<span class="held">a control held here</span>' : ""}
        ${(a.attack || a.atlas || []).length ? `<div class="ids">${idTags([...(a.attack || []), ...(a.atlas || [])])}</div>` : ""}
      </div></div>`).join("")}</div>

    <h3>Evidence (telemetry) and detection map</h3>
    ${telemetryBlock(s)}
    ${session.active ? ucNoteCard(s) : ""}
    ${bar(effCounts(s), total)}${legend()}

    ${(s.use_case_ids || []).length ? `<h3>Operational use cases</h3>
      <div class="kv">${s.use_case_ids.map(uid => {
        const u = (DATA.use_cases || []).find(x => x.id === uid);
        return `<a class="chip uclink" href="#/usecase/${esc(uid)}"
          title="${esc(u ? u.title : "")}">${esc(uid)}</a>`;
      }).join("")}</div>
      <div style="color:var(--muted);font-size:12px;margin-top:6px">
        What is done with these signals, who receives the result, and what it cannot
        tell you. Open the Use cases tab for the full records.</div>` : ""}

    ${s.commentary ? `<h3>Analysis</h3>
      ${s.commentary.already_see ? `<div class="note"><strong>What we can already see.</strong> ${esc(s.commentary.already_see)}</div>` : ""}
      ${s.commentary.blind ? `<div class="note"><strong>Where we are blind.</strong> ${esc(s.commentary.blind)}</div>` : ""}
      ${s.commentary.how_detect ? `<div class="note"><strong>How we detect it.</strong> ${esc(s.commentary.how_detect)}</div>` : ""}` : ""}

    ${s.scaled_up ? `<h3>If this scaled up</h3><div class="note"><em>Hypothetical, not observed.</em> ${esc(s.scaled_up)}</div>` : ""}

    ${(s.hardening || []).length ? `<h3>Hardening, ranked by leverage</h3>
      <table><thead><tr><th>Action</th><th>Breaks step</th><th>Leverage</th><th>Owner</th><th>Ticket</th></tr></thead>
      <tbody>${s.hardening.map(h => `<tr><td>${esc(h.action)}</td>
        <td class="mono">${(h.breaks_step || []).join(", ")}</td><td>${esc(h.leverage || "")}</td>
        <td style="color:var(--muted)">${esc(h.owner || "")}</td>
        <td>${h.backlog_ref ? `<span class="tag">${esc(h.backlog_ref)}</span>` : ""}</td></tr>`).join("")}</tbody></table>` : ""}

    <h3>Framework mapping</h3>
    ${fwRow("MITRE ATT&amp;CK", fm.attack)}${fwRow("MITRE ATLAS", fm.atlas)}
    ${fwRow("OWASP LLM", fm.owasp_llm)}${fwRow("OWASP Agentic", fm.owasp_agentic)}
    ${fm.mapping_confidence === "editorial"
      ? `<div class="note" style="border-color:var(--collectable);background:var(--collectable-bg)">
           <strong>This mapping is our own judgment, not upstream-endorsed.</strong>
           ${fm.mapping_notes ? " " + esc(fm.mapping_notes) : ""}</div>` : ""}

    ${(s.incidents || []).length ? `<h3>Grounded in</h3><ul class="plain">${s.incidents.map(sl => {
      const i = DATA.incidents[sl] || {};
      return `<li><strong>${esc(i.title || sl)}</strong>${i.what_happened ? " " + esc(i.what_happened) : ""}
        ${i.source ? `<span style="color:var(--muted)"> (${esc(i.source)})</span>` : ""}</li>`;
    }).join("")}</ul>` : ""}

    ${(s.provenance && s.provenance.sources || []).length ? `<h3>Sources</h3><ul class="plain">${
      s.provenance.sources.slice().sort((a, b) => (a.tier > b.tier ? 1 : -1)).map(src =>
        `<li><span class="tag">Tier ${esc(src.tier)}</span>
          <a href="${esc(src.url)}" target="_blank" rel="noopener">${esc(src.title || src.url)}</a>
          ${src.note ? `<span style="color:var(--muted)"> ${esc(src.note)}</span>` : ""}</li>`).join("")}</ul>` : ""}

    <h3>Record</h3>
    <div style="color:var(--muted);font-size:13px">
      <code>scenarios/${esc(s.id)}-${esc(s.slug)}.yaml</code><br>
      Authored by ${esc(s.provenance.authored_by || "not recorded")},
      reviewed by ${esc(s.provenance.reviewed_by || "not yet reviewed")},
      last updated ${esc(s.provenance.last_updated || "not recorded")}.
      Framework baseline ${esc((s.framework_mapping || {}).baseline || "")}.
    </div>`;
  el.scrollTop = 0;
  if (session.active) wireEditors(s);
}

/* ---------- telemetry: read mode and session mode ---------- */
function telemetryBlock(s) {
  const rows = s.telemetry || [];
  if (!session.active) {
    return `<table><thead><tr><th>#</th><th>Signal emitted</th><th>Where it is emitted</th>
      <th>Exact source</th><th>Collected</th><th>Detection opportunity</th><th>Owner</th></tr></thead>
      <tbody>${rows.map(t => {
        const e = effRow(s.id, t), c = effCoverage(s.id, t);
        const sc = e.dettect ? `v${e.dettect.visibility} d${e.dettect.detection}` : "not scored";
        return `<tr><td class="num">${t.kind === "control" ? "c" : t.step}</td>
          <td><strong>${esc(t.signal)}</strong>${e.evidence ? `<div style="color:var(--muted);font-size:12px;margin-top:3px">${esc(e.evidence)}</div>` : ""}</td>
          <td style="color:var(--muted)">${esc(t.emitted_at)}</td>
          <td class="mono" style="color:var(--ink-2)">${esc(e.source || "")}</td>
          <td><span class="chip ${c}"><i class="dot ${c}"></i>${c}</span>
              <div class="scores">${sc}</div></td>
          <td>${esc(t.detection_opportunity)}</td>
          <td style="color:var(--muted)">${esc(e.owner || "")}${e.backlog_ref ? `<div class="tag" style="margin-top:4px">${esc(e.backlog_ref)}</div>` : ""}</td></tr>`;
      }).join("")}</tbody></table>`;
  }
  return rows.map(t => editCard(s, t)).join("");
}

function editCard(s, t) {
  const e = effRow(s.id, t), c = effCoverage(s.id, t);
  const u = rowChange(s.id, t.step), touched = Object.keys(u).length > 0;
  const v = e.dettect ? e.dettect.visibility : "";
  const d = e.dettect ? e.dettect.detection : "";
  const opt = (list, cur) => list.map(([val, label]) =>
    `<option value="${val}" ${String(val) === String(cur) ? "selected" : ""}>${esc(label)}</option>`).join("");

  return `<div class="ec ${touched ? "changed" : ""}" data-step="${t.step}">
    <div class="hdr"><span class="n">${t.kind === "control" ? "c" : t.step}</span>
      <span class="sig">${esc(t.signal)}</span>
      ${touched ? '<span class="mark">captured this session</span>' : ""}</div>
    <div class="cat">${esc(t.emitted_at)}${t.detection_opportunity ? " &middot; would alert on: " + esc(t.detection_opportunity) : ""}</div>

    <div class="grid">
      <div class="fld inline"><label>Would we see it</label>
        <select data-k="visibility"><option value="">not scored</option>${opt(VIS, v)}</select></div>
      <div class="fld inline"><label>Does anything alert on it</label>
        <select data-k="detection"><option value="">not scored</option>${opt(DET, d)}</select></div>
      <div class="verdict ${c}">${c}</div>
    </div>

    <div class="fld"><label>Where exactly does it come from</label>
      <input data-k="source" value="${esc(e.source || "")}"
        placeholder="the product, log source, index, table or endpoint by name">
      <span class="hint">Example: CrowdStrike Falcon ProcessRollup2, index=edr_main.
        A Have nobody can point at is not verifiable. A Collectable nobody can point at cannot be wired up.</span></div>

    <div class="fld"><label>Evidence that it actually fires</label>
      <input data-k="evidence" value="${esc(e.evidence || "")}"
        placeholder="the saved search, rule ID or ticket that proves it">
      <span class="hint">Required for a Have. Without it the claim cannot be checked
        later, and a Have that nobody can check is the fastest way to make these
        figures worthless.</span></div>

    <div class="two">
      <div class="fld inline"><label>Owner</label>
        <input data-k="owner" value="${esc(e.owner || "")}" placeholder="the team that owns that source"></div>
      <div class="fld inline"><label>Ticket</label>
        <input data-k="backlog_ref" value="${esc(e.backlog_ref || "")}" placeholder="required for a Blind or Collectable row"></div>
    </div>

    <div class="fld"><label>Notes</label>
      <input data-k="notes" value="${esc(e.notes || "")}"
        placeholder="anything the room said that the next reader needs"></div>
  </div>`;
}

/* Record-level capture: one line naming the use case these signals should feed.
   Stored beside the row edits and applied to the record's notes on apply, so the
   thought is not lost between the session and the use-cases/ record it becomes. */
function ucNoteCard(s) {
  const note = (session.changes[s.id] || {}).use_case_note || "";
  return `<div class="ec ${note ? "changed" : ""}" data-uc-note="1">
    <div class="hdr"><span class="n">&raquo;</span>
      <span class="sig">Proposed use case</span>
      ${note ? '<span class="mark">captured this session</span>' : ""}</div>
    <div class="cat">For the whole scenario, not one row.</div>
    <div class="fld"><label>Proposed use case</label>
      <input data-k="use_case_note" value="${esc(note)}"
        placeholder="the decision these signals should compose into, and who would receive it">
      <span class="hint">Free text, one line. Applied to this record's notes by
        tools/apply_session.py; an analyst turns it into a record in use-cases/ later.</span></div>
  </div>`;
}

function wireEditors(s) {
  $$("#detail .ec").forEach(card => {
    const step = Number(card.dataset.step);
    $$("select,input", card).forEach(el => {
      const k = el.dataset.k;
      const handler = () => {
        if (k === "use_case_note") {
          chg(s.id).use_case_note = el.value;
          session.recorded = session.recorded || new Date().toISOString().slice(0, 10);
          saveSession();
          if (el.value) card.classList.add("changed");
          updateSessionCount();
        } else if (k === "visibility" || k === "detection") {
          const cur = effRow(s.id, (s.telemetry || []).find(r => r.step === step)) || {};
          const base = cur.dettect || {};
          const vv = k === "visibility" ? el.value : (base.visibility ?? "");
          const dd = k === "detection" ? el.value : (base.detection ?? "");
          if (vv === "" || dd === "") {
            setRow(s.id, step, "dettect", null);
          } else {
            const q = base.quality;
            setRow(s.id, step, "dettect",
              { visibility: Number(vv), detection: Number(dd), ...(q ? { quality: q } : {}) });
          }
          renderDetail(); renderList(); wireEditors(s);
          const again = $(`#detail .ec[data-step="${step}"] [data-k="${k}"]`);
          if (again) again.focus();
        } else {
          setRow(s.id, step, k, el.value);
          card.classList.add("changed");
          updateSessionCount();
        }
      };
      el.onchange = handler;
      if (el.tagName === "INPUT") el.onblur = handler;
    });
  });
}

/* ---------- proposing a scenario the library does not have ---------- */
function proposalForm() {
  const opt = (list, cur) => list.map(([v, label]) =>
    `<option value="${esc(v)}"${v === cur ? " selected" : ""}>${esc(label)}</option>`).join("");
  return `<div class="ec changed" id="proposeform">
    <div class="hdr"><span class="n">+</span><span class="sig">A scenario we do not have</span></div>
    <div class="cat">Captured with the session, not written to the library from this page.</div>

    <div class="fld"><label>What would you call it</label>
      <input id="np-title" placeholder="the way it should read on a slide">
      <span class="hint">Required. Example: poisoned vector store in a shared index.</span></div>

    <div class="two">
      <div class="fld inline"><label>Is this an attack or a failure</label>
        <select id="np-mode">${opt(NEW_MODES, "attack")}</select></div>
      <div class="fld inline"><label>How urgent is the work on it</label>
        <select id="np-priority">${opt(NEW_PRIORITIES, "BACKLOG")}</select></div>
    </div>

    <div class="fld"><label>Which layer does it mostly happen at</label>
      <select id="np-layer">${NEW_LAYERS.map(l =>
        `<option${l.startsWith("L3") ? " selected" : ""}>${esc(l)}</option>`).join("")}</select></div>

    <div class="fld"><label>What happens, in one line</label>
      <input id="np-oneliner" placeholder="what you would say to someone who has never heard of it">
      <span class="hint">One or two plain sentences, forty characters or more. It becomes the
        plain terms paragraph on the new record, so write it for a reader who is not in this room.</span></div>

    <div class="fld"><div style="display:flex;gap:8px">
        <button class="toggle" id="np-add">Add this proposal</button>
        <button class="toggle" id="np-cancel">Cancel</button></div>
      <div class="err" id="np-err" hidden>Give it a title first. Everything else has a sensible default.</div></div>
  </div>`;
}

function proposalsPanel() {
  const list = session.newScenarios || [];
  return `<div class="panel"><h3>Proposed new scenarios (${list.length})</h3>
    <div class="sub">Scenarios the room says are missing. Applying the session file writes a
      draft record for each one, with the next free id and the filename already right, and an
      analyst works it from there. Remove any you do not want before you export.</div>
    ${list.length ? list.map((p, i) => `<div class="prop"><div>
        <div class="t">${esc(p.title)}</div>
        <div class="m">${esc(p.mode)} &middot; ${esc(p.layer)} &middot; ${esc(p.priority)}
          ${p.one_liner ? "<br>" + esc(p.one_liner) : ""}</div>
      </div><button data-drop="${i}">Remove</button></div>`).join("")
    : '<div style="color:var(--muted)">None yet.</div>'}
    <div style="margin-top:14px">${proposeOpen ? proposalForm()
      : '<button class="toggle" id="propose">Propose a new scenario</button>'}</div></div>`;
}

function openProposal() {
  proposeOpen = true;
  if (state.view !== "session") setView("session"); else renderSession();
  const t = $("#np-title");
  if (t) t.focus();
}

function wireProposals() {
  const open = $("#propose");
  if (open) open.onclick = openProposal;
  $$("#sessionview .prop button[data-drop]").forEach(b => b.onclick = () => {
    session.newScenarios.splice(Number(b.dataset.drop), 1);
    saveSession(); renderSession(); updateSessionCount();
  });
  const add = $("#np-add");
  if (!add) return;
  add.onclick = () => {
    const title = $("#np-title").value.trim();
    if (!title) { $("#np-err").hidden = false; $("#np-title").focus(); return; }
    session.newScenarios.push({
      title, mode: $("#np-mode").value, layer: $("#np-layer").value,
      priority: $("#np-priority").value, one_liner: $("#np-oneliner").value.trim() });
    session.recorded = session.recorded || new Date().toISOString().slice(0, 10);
    proposeOpen = false;
    saveSession(); renderSession(); updateSessionCount();
  };
  $("#np-cancel").onclick = () => { proposeOpen = false; renderSession(); };
}

/* ---------- session review and export ---------- */
function updateSessionCount() {
  const n = changedCount(), p = (session.newScenarios || []).length;
  const el = $("#scount");
  if (!el) return;
  const parts = [];
  if (n) parts.push(`${n} change${n === 1 ? "" : "s"} across ${changedScenarios().length} scenario${changedScenarios().length === 1 ? "" : "s"}`);
  if (p) parts.push(`${p} proposed scenario${p === 1 ? "" : "s"}`);
  el.textContent = parts.length ? parts.join(" · ") : "nothing captured yet";
}

function renderSession() {
  const ids = changedScenarios();
  const head = `<div class="panel"><h3>Session readback</h3>
    <div class="sub">Read this aloud at the end of the hour. Confirm every owner accepts
      their gap and every ticket number is right, while the room is still together.</div>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button class="toggle" id="export">Export session file</button>
      <button class="toggle" id="import">Import a session file</button>
      <button class="toggle danger" id="wipe">Discard everything captured</button>
    </div>
    <input type="file" id="file" accept="application/json" hidden>
    <div class="sub" style="margin:14px 0 0">Exporting writes
      <code>liszt-session-&lt;date&gt;.json</code>. Apply it with
      <code>python3 tools/apply_session.py &lt;file&gt;</code>, then review the diff,
      run the validator, and commit. This page never writes to the records itself.</div></div>`;

  const body = ids.length ? ids.map(sid => {
    const s = DATA.scenarios.find(x => x.id === sid);
    const c = session.changes[sid];
    const lines = Object.keys(c.telemetry).sort((a, b) => a - b).map(step => {
      const row = (s.telemetry || []).find(r => String(r.step) === String(step)) || {};
      const u = c.telemetry[step], out = [];
      if ("dettect" in u) {
        const was = row.dettect ? `v${row.dettect.visibility} d${row.dettect.detection}` : "unscored";
        const now = u.dettect ? `v${u.dettect.visibility} d${u.dettect.detection}` : "unscored";
        out.push(`scores <span class="was">${was}</span> to <strong>${now}</strong>,
          coverage now <strong>${effCoverage(sid, row)}</strong>`);
      }
      ["source", "evidence", "owner", "backlog_ref", "notes"].forEach(k => {
        if (k in u && u[k] !== (row[k] || "")) {
          const label = { source: "source", evidence: "evidence", owner: "owner",
                          backlog_ref: "ticket", notes: "notes" }[k];
          out.push(`${label} <strong>${esc(u[k] || "(cleared)")}</strong>`);
        }
      });
      return out.length ? `<div class="line"><strong>Step ${step}</strong>
        ${esc(row.signal || "")} &middot; ${out.join("; ")}</div>` : "";
    }).join("");
    return `<div class="panel"><div class="rb">
      <h4><a href="#/scenario/${sid}">${esc(sid)} ${esc(s ? s.title : "")}</a></h4>
      ${lines || '<div class="line was">no field changes</div>'}
      ${c.notes ? `<div class="line">record note: <strong>${esc(c.notes)}</strong></div>` : ""}
      ${c.use_case_note ? `<div class="line">proposed use case: <strong>${esc(c.use_case_note)}</strong></div>` : ""}
    </div></div>`;
  }).join("")
    : ((session.newScenarios || []).length ? ""
      : `<div class="panel"><div style="color:var(--muted)">Nothing captured yet.
          Turn on session mode, open a scenario, and work down the evidence rows.</div></div>`);

  $("#sessionview").innerHTML = head + proposalsPanel() + body;
  wireProposals();

  $("#export").onclick = () => {
    const date = session.recorded || new Date().toISOString().slice(0, 10);
    /* new_scenarios is an addition, not a change: session_format stays 1, every existing
       field means what it always meant, and a reader that does not know the key ignores it. */
    const blob = new Blob([JSON.stringify({
      session_format: 1, recorded: date,
      facilitator: session.facilitator || "",
      org: DATA.view.org, baseline: DATA.baseline.id,
      changes: session.changes,
      new_scenarios: (session.newScenarios || []).map(p => ({
        title: p.title, mode: p.mode, layer: p.layer,
        priority: p.priority, one_liner: p.one_liner || "" }))
      }, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `liszt-session-${date}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };
  $("#import").onclick = () => $("#file").click();
  $("#file").onchange = (ev) => {
    const f = ev.target.files[0];
    if (!f) return;
    const rd = new FileReader();
    rd.onload = () => {
      try {
        const d = JSON.parse(rd.result);
        if (d.session_format !== 1) throw new Error("unsupported session_format");
        session.changes = d.changes || {};
        session.newScenarios = Array.isArray(d.new_scenarios) ? d.new_scenarios : [];
        session.facilitator = d.facilitator || session.facilitator;
        session.recorded = d.recorded || session.recorded;
        saveSession(); renderSession(); renderList(); renderDetail(); updateSessionCount();
      } catch (e) { alert("Could not read that session file: " + e.message); }
    };
    rd.readAsText(f);
  };
  $("#wipe").onclick = () => {
    if (!confirm("Discard everything captured in this session, including any proposed "
      + "scenarios? This cannot be undone, and anything not exported is lost.")) return;
    session.changes = {}; session.newScenarios = []; proposeOpen = false; saveSession();
    renderSession(); renderList(); renderDetail(); updateSessionCount();
  };
}

function toggleSession(on) {
  session.active = on;
  document.body.classList.toggle("session", on);
  $("#sessionbar").hidden = !on;
  $("#sessionnav").hidden = !on;
  session.recorded = session.recorded || new Date().toISOString().slice(0, 10);
  saveSession();
  renderDetail(); renderList(); updateSessionCount();
}

/* ---------- coverage view ---------- */
function renderCoverage() {
  const rows = DATA.scenarios.filter(matches);
  const scored = rows.filter(s => s.metrics.completeness > 0);
  const sorted = rows.slice().sort((a, b) =>
    (b.metrics.have ?? -1) - (a.metrics.have ?? -1) || a.id.localeCompare(b.id));

  const chart = `<div class="panel">
    <h3>Coverage by scenario</h3>
    <div class="sub">Proportion of steps at each coverage level. Sorted by Have.
      Scenarios with no scores are shown as unscored and are excluded from every average.</div>
    <button class="toggle" id="tbl">${state.table ? "Show chart" : "Show as table"}</button>
    <div style="margin-top:14px" id="covbody"></div>${legend()}</div>`;

  const bars = sorted.map(s => {
    const total = (s.telemetry || []).length;
    return `<div class="rowbar"><span class="mono" style="color:var(--muted)">${esc(s.id)}</span>
      <span>${esc(s.title)}</span>${bar(s.counts, total)}
      <span class="pct">${s.metrics.have != null ? pct(s.metrics.have) : "n/a"}</span></div>`;
  }).join("");

  const table = `<table><thead><tr><th>#</th><th>Scenario</th><th>Priority</th>
      <th>Scored</th><th>Have</th><th>Collectable</th><th>Blind</th><th>Maturity</th></tr></thead>
    <tbody>${sorted.map(s => `<tr><td class="mono">${esc(s.id)}</td><td>${esc(s.title)}</td>
      <td>${esc(s.classification.priority)}</td>
      <td>${s.metrics.scored}/${s.metrics.rows}</td>
      <td>${pct(s.metrics.have)}</td><td>${pct(s.metrics.collectable)}</td>
      <td>${pct(s.metrics.blind)}</td><td>${esc(s.metrics.maturity.score)}</td></tr>`).join("")}</tbody></table>`;

  const exposedRows = rows.filter(s => s.metrics.exposed);
  const orphanRows = rows.filter(s => s.metrics.orphaned_gaps.length);

  $("#coverage").innerHTML = chart + `
    <div class="panel"><h3>Exposure</h3>
      <div class="sub">NOW-priority scenarios that still have a Blind step. This is the risk view.</div>
      ${exposedRows.length ? `<ul class="plain">${exposedRows.map(s =>
        `<li><a href="#/scenario/${s.id}"><strong>${esc(s.id)} ${esc(s.title)}</strong></a>
          blind at step ${s.metrics.blind_steps.join(", ")}</li>`).join("")}</ul>`
        : '<div style="color:var(--muted)">No NOW-priority scenario has a Blind step in this view.</div>'}</div>

    <div class="panel"><h3>Unowned gaps</h3>
      <div class="sub">Blind or Collectable rows with no owner recorded. A gap with no owner is not assigned to anyone.</div>
      ${orphanRows.length ? `<ul class="plain">${orphanRows.map(s =>
        `<li><a href="#/scenario/${s.id}">${esc(s.id)} ${esc(s.title)}</a>
          steps ${s.metrics.orphaned_gaps.join(", ")}</li>`).join("")}</ul>`
        : '<div style="color:var(--muted)">Every gap in this view has an owner.</div>'}</div>

    <div class="panel"><h3>How these are calculated</h3>
      <div class="sub" style="margin:0">
        <strong>Blind</strong> when visibility is 0. <strong>Collectable</strong> when visibility is 1 or more
        and detection is 0 or less, which means the data is recorded but no alert is raised.
        <strong>Have</strong> when visibility is 1 or more and detection is 1 or more.
        The label is always calculated from those two scores and is never entered directly.
        A row with no scores is absent from the figures, not counted as zero.
        Mean Have is taken across the ${scored.length} scored scenario${scored.length === 1 ? "" : "s"} only.
      </div></div>`;

  $("#covbody").innerHTML = state.table ? table : bars;
  const t = $("#tbl");
  if (t) t.onclick = () => { state.table = !state.table; renderCoverage(); };
}

/* ---------- use cases view ---------- */
function renderUseCases() {
  const ucs = DATA.use_cases || [];
  const scLink = (sid, steps) => {
    const sc = DATA.scenarios.find(x => x.id === sid);
    const label = `${esc(sid)}${sc ? " " + esc(sc.title) : ""} &middot; step${steps.length === 1 ? "" : "s"} ${steps.join(", ")}`;
    return sc ? `<a href="#/scenario/${esc(sid)}">${label}</a>`
              : `<span style="color:var(--muted)">${label} (not in this view)</span>`;
  };
  $("#usecases").innerHTML = `
    <div class="panel"><h3>Operational use cases</h3>
      <div class="sub">A scenario says what evidence should exist. A use case says what gets
        done with it: what triggers it, what other evidence it composes and in what role, how
        the evidence is delivered, what it produces, who receives that, and what it is allowed
        to do on its own. Coverage says we can see it; a use case says we do something with it.
        Records live in <code>use-cases/</code>; this page is a build artifact.</div></div>` +
    (ucs.length ? ucs.map(u => `
    <div class="uc" id="uc-${esc(u.id)}">
      <div class="hdr"><span class="id">${esc(u.id)}</span>
        <span class="chip ${esc(u.status)}">${esc(u.status)}</span>
        <span class="chip ${esc((u.outcome || {}).autonomy || "")}"
          title="who acts: notify, an operator; assisted, automation prepares and an operator acts; autonomous, a bounded action runs first and is reviewed after">${esc((u.outcome || {}).autonomy || "")}</span></div>
      <h4>${esc(u.title)}</h4>

      <div class="ucrow"><div class="k">Covers</div><div>
        ${(u.covers || []).map(c => `<div>${scLink(String(c.scenario), c.steps || [])}</div>`).join("")}</div></div>

      <div class="ucrow"><div class="k">Trigger</div><div>
        <strong>${esc((u.trigger || {}).signal || "")}</strong>
        <div class="src">${esc((u.trigger || {}).source || "")}</div></div></div>

      <div class="ucrow"><div class="k">Composes</div><div>
        ${(u.composes || []).length ? (u.composes || []).map(cx => `
          <div style="margin-bottom:6px"><span class="role">${esc(cx.role)}</span>
            <strong>${esc(cx.signal)}</strong>
            <div class="src">${esc(cx.source)}</div></div>`).join("")
          : '<span style="color:var(--muted)">nothing; a single signal use case</span>'}</div></div>

      <div class="ucrow"><div class="k">Pipeline</div><div>
        <span class="tag">${esc((u.pipeline || {}).strategy || "")}</span>
        &rarr; ${esc((u.pipeline || {}).destination || "")}
        <div class="src">owned by ${esc((u.pipeline || {}).owner || "")}</div></div></div>

      <div class="ucrow"><div class="k">Outcome</div><div>
        <span class="tag">${esc((u.outcome || {}).kind || "")}</span>
        to <strong>${esc((u.outcome || {}).consumer || "")}</strong>
        <div style="margin-top:4px">${esc((u.outcome || {}).action || "")}</div>
        ${u.promotion ? `<div class="src" style="margin-top:4px">promoted from ${esc(u.promotion.from)},
          approved by ${esc(u.promotion.approved_by)} on ${esc(u.promotion.approved)}</div>` : ""}</div></div>

      <div class="limits"><span class="k">What it cannot tell you</span>${esc(u.limits || "")}</div>
    </div>`).join("")
      : `<div class="panel"><div style="color:var(--muted)">No use case records yet.
          Copy <code>use-cases/_TEMPLATE.yaml</code> to start one.</div></div>`);
}

/* ---------- frameworks view ---------- */
function renderFrameworks() {
  const names = { attack: "MITRE ATT&CK", atlas: "MITRE ATLAS",
                  owasp_llm: "OWASP Top 10 for LLM Applications",
                  owasp_agentic: "OWASP Top 10 for Agentic Applications" };
  const b = DATA.baseline;
  $("#frameworks").innerHTML = `
    <div class="panel"><h3>Framework baseline ${esc(b.id || "")}</h3>
      <div class="sub">Every identifier below is expressed in this baseline's vocabulary.
        Identifiers are not comparable across baselines.</div>
      <table><tbody>
        <tr><td>MITRE ATT&amp;CK</td><td class="mono">${esc(b.attack)}${b.attack_spec ? ` (spec ${esc(b.attack_spec)})` : ""}</td></tr>
        <tr><td>MITRE ATLAS</td><td class="mono">${esc(b.atlas)}${b.atlas_format ? ` (format ${esc(b.atlas_format)})` : ""}</td></tr>
        <tr><td>OWASP LLM</td><td class="mono">${esc(b.owasp_llm)}</td></tr>
        <tr><td>OWASP Agentic</td><td class="mono">${esc(b.owasp_agentic)}</td></tr>
        <tr><td>DeTT&amp;CT</td><td class="mono">${esc(b.dettect)}</td></tr>
      </tbody></table></div>` +
    Object.entries(names).map(([key, label]) => {
      const idx = DATA.frameworks[key] || {};
      const ids = Object.keys(idx).sort();
      if (!ids.length) return "";
      return `<div class="panel"><h3>${label}</h3>
        <div class="sub">${ids.length} identifier${ids.length === 1 ? "" : "s"} used across the library.</div>
        ${ids.map(id => `<div class="fw"><div><span class="tag">${esc(id)}</span>
          ${DATA.owasp_names[id.split(":")[0]] ? `<div style="color:var(--muted);font-size:12px;margin-top:4px">${esc(DATA.owasp_names[id.split(":")[0]])}</div>` : ""}</div>
          <div>${idx[id].map(sid => {
            const sc = DATA.scenarios.find(x => x.id === sid);
            return `<a href="#/scenario/${sid}" style="margin-right:12px">${esc(sid)} ${esc(sc ? sc.title : "")}</a>`;
          }).join("")}</div></div>`).join("")}</div>`;
    }).join("") + `
    <div class="panel"><h3>On the reliability of these mappings</h3>
      <div class="sub" style="margin:0">There is no authoritative crosswalk between OWASP and either
        MITRE framework, in either direction. The ATLAS to ATT&amp;CK linkage is partial. Every
        cross-framework mapping in this library is the program's own editorial judgment, is recorded
        as such on each record, and must not be presented as upstream-endorsed.</div></div>`;
}

/* ---------- shell ---------- */
function select(id) {
  state.sel = id;
  location.hash = `#/scenario/${id}`;
  renderList(); renderDetail();
}
function setView(v) {
  state.view = v;
  $$("nav button").forEach(b => b.setAttribute("aria-current", b.dataset.view === v ? "page" : "false"));
  $("#scenarios").hidden = v !== "scenarios";
  $("#coverage").hidden = v !== "coverage";
  $("#usecases").hidden = v !== "usecases";
  $("#frameworks").hidden = v !== "frameworks";
  $("#sessionview").hidden = v !== "session";
  if (v === "coverage") renderCoverage();
  if (v === "usecases") renderUseCases();
  if (v === "frameworks") renderFrameworks();
  if (v === "session") renderSession();
}
function route() {
  const m = (location.hash || "").match(/^#\/scenario\/(\d{3})$/);
  if (m && DATA.scenarios.some(s => s.id === m[1])) {
    state.sel = m[1];
    if (state.view !== "scenarios") setView("scenarios");
    renderList(); renderDetail();
  }
  const u = (location.hash || "").match(/^#\/usecase\/(UC-\d{3})$/);
  if (u && (DATA.use_cases || []).some(x => x.id === u[1])) {
    if (state.view !== "usecases") setView("usecases");
    $$("#usecases .uc").forEach(el => el.classList.toggle("sel", el.id === "uc-" + u[1]));
    const el = document.getElementById("uc-" + u[1]);
    if (el) el.scrollIntoView({ block: "start" });
  }
}
function refresh() {
  renderList();
  if (state.view === "coverage") renderCoverage();
}

document.addEventListener("DOMContentLoaded", () => {
  const uniq = (f) => [...new Set(DATA.scenarios.map(f))].sort();
  $("#f-layer").innerHTML = '<option value="">Any layer</option>' +
    uniq(s => s.classification.ai_infrastructure_layer).map(v => `<option>${esc(v)}</option>`).join("");
  $("#f-status").innerHTML = '<option value="">Any status</option>' +
    uniq(s => s.status).map(v => `<option>${esc(v)}</option>`).join("");

  $("#q").oninput = (e) => { state.q = e.target.value; refresh(); };
  ["priority", "evidence", "layer", "status", "cov"].forEach(k => {
    $(`#f-${k}`).onchange = (e) => { state[k] = e.target.value; refresh(); };
  });
  $("#clear").onclick = () => {
    Object.assign(state, { q: "", priority: "", evidence: "", layer: "", status: "", cov: "" });
    $("#q").value = ""; ["priority", "evidence", "layer", "status", "cov"]
      .forEach(k => $(`#f-${k}`).value = "");
    refresh();
  };
  $$("nav button").forEach(b => b.onclick = () => setView(b.dataset.view));
  window.addEventListener("hashchange", route);

  loadSession();
  $("#facilitator").value = session.facilitator || "";
  $("#facilitator").onchange = (e) => { session.facilitator = e.target.value; saveSession(); };
  $("#sessiontoggle").onclick = () => {
    toggleSession(!session.active);
    $("#sessiontoggle").textContent = session.active ? "Leave session mode" : "Start session mode";
  };
  $("#endsession").onclick = () => setView("session");
  $("#proposenav").onclick = openProposal;

  renderList(); renderDetail(); setView("scenarios"); route();
  if (session.active) {
    document.body.classList.add("session");
    $("#sessionbar").hidden = false; $("#sessionnav").hidden = false;
    $("#sessiontoggle").textContent = "Leave session mode";
    renderDetail();
  }
  updateSessionCount();
  window.addEventListener("beforeunload", (e) => {
    if (changedCount() || (session.newScenarios || []).length) {
      e.preventDefault(); e.returnValue = "";
    }
  });
});
"""


def page(data: dict) -> str:
    lib, b = data["library"], data["baseline"]
    tile = lambda n, label, sub, color=None: (
        f'<div class="tile"><div class="n"{f" style=color:{color}" if color else ""}>{n}</div>'
        f'<div class="l">{label}</div><div class="s">{html.escape(sub)}</div></div>')

    tiles = "".join([
        tile(lib["records"], "Scenarios", f'{lib["published"]} published'),
        tile(f'{lib["mean_have"] * 100:.0f}%' if lib["mean_have"] is not None else "n/a",
             "Mean Have", f'across {lib["scored"]} scored scenario'
             f'{"" if lib["scored"] == 1 else "s"}', "var(--have)"),
        tile(lib["exposed"], "Exposed",
             "NOW priority with a Blind step", "var(--blind)"),
        tile(lib["full_maturity"], "Fully mature", "pass all seven process gates"),
        tile(len(lib["unscored_ids"]), "Not scored",
             "absent from the figures, not zero", "var(--muted)"),
    ])

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Liszt scenario library</title>
<style>{CSS}</style></head><body>
<header><div class="wrap">
  <div class="hd"><span class="logo">LISZT</span><h1>Scenario library</h1>
    <div class="meta">{html.escape(data["view"]["org"])}
      &middot; framework baseline {html.escape(str(b["id"]))}<br>
      {"drafts included" if data["view"]["includes_drafts"] else "published records only"}</div></div>
  <nav>
    <button data-view="scenarios" aria-current="page">Scenarios</button>
    <button data-view="coverage" aria-current="false">Coverage</button>
    <button data-view="usecases" aria-current="false">Use cases</button>
    <button data-view="frameworks" aria-current="false">Frameworks</button>
    <button data-view="session" aria-current="false" id="sessionnav" hidden>Session</button>
    <button style="margin-left:auto;color:var(--brand)" id="sessiontoggle">Start session mode</button>
  </nav>
<div class="sessionbar" id="sessionbar" hidden><div class="wrap">
  <strong>SESSION MODE</strong>
  <span>Captured here, not written to the records. Export at the end.</span>
  <input id="facilitator" placeholder="facilitator name">
  <div class="right">
    <span class="pill" id="scount">nothing captured yet</span>
    <button id="proposenav">Propose a new scenario</button>
    <button id="endsession">Readback and export</button>
  </div>
</div></div>
<div class="sessionbar" id="volatile" hidden style="background:var(--blind)"><div class="wrap">
  <strong>NOT SAVED LOCALLY</strong>
  <span>This browser will not keep what you type between page loads.
        Export the session file before closing this tab.</span>
</div></div>
</header>

<div class="wrap">
  <div class="tiles">{tiles}</div>

  <div class="filters">
    <input type="search" id="q" placeholder="Search titles, steps, signals and framework IDs">
    <select id="f-priority"><option value="">Any priority</option>
      <option>NOW</option><option>NEAR-TERM</option><option>BACKLOG</option></select>
    <select id="f-evidence"><option value="">Any evidence</option>
      <option value="seen-in-the-wild">Seen in the wild</option>
      <option value="seen-in-research">Seen in research</option>
      <option value="doomsday">Doomsday</option></select>
    <select id="f-layer"></select>
    <select id="f-status"></select>
    <select id="f-cov"><option value="">Any coverage</option>
      <option value="blind">Has a Blind step</option>
      <option value="exposed">Exposed (NOW and Blind)</option>
      <option value="orphan">Has an unowned gap</option>
      <option value="unscored">Not scored</option></select>
    <span class="count" id="count"></span>
    <button class="clear" id="clear">Clear</button>
  </div>

  <section id="scenarios"><div class="split">
    <div class="list" id="list"></div><div class="detail" id="detail"></div>
  </div></section>
  <section id="coverage" hidden></section>
  <section id="usecases" hidden></section>
  <section id="frameworks" hidden></section>
  <section id="sessionview" hidden></section>

  <footer>
    Generated from the Liszt record library by <code>tools/build_viewer.py</code>.
    This page is a build artifact. Edit the records, not this file.<br>
    The accompanying <code>liszt-data.json</code> carries the same data for
    integration into other applications. Its shape is documented in
    <code>docs/07-viewer-data-contract.md</code>.<br>
    Session mode captures into this page only. Export the session file and apply it
    with <code>tools/apply_session.py</code>; the records stay the system of record.
  </footer>
</div>

<script>const DATA = {json.dumps(data, separators=(",", ":"), ensure_ascii=False, default=jsonable)};</script>
<script>{JS}</script>
</body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "build" / "viewer")
    ap.add_argument("--include-drafts", action="store_true")
    ap.add_argument("--org")
    args = ap.parse_args()

    data = build_data(args.include_drafts, args.org)
    if not data["scenarios"]:
        sys.exit("nothing to show. Only published records are included by default; "
                 "pass --include-drafts to preview work in progress.")

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "liszt-data.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=jsonable), encoding="utf-8")
    (args.out / "liszt-viewer.html").write_text(page(data), encoding="utf-8")

    kb = (args.out / "liszt-viewer.html").stat().st_size / 1024
    print(f"  liszt-viewer.html   {kb:.0f} KB, {data['library']['records']} scenario(s)")
    print(f"  liszt-data.json     the integration seam")
    print(f"\nwritten to {args.out}")
    print("The HTML page is self-contained. It makes no network requests and needs "
          "no server.\nHand liszt-data.json to anyone integrating this into "
          "another application.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
