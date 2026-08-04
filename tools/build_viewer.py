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
.chip.modeler{background:#F1ECFA;color:#5A3B9C}
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

/* reports ----------------------------------------------------------------- */
.rmenu{display:flex;gap:6px;flex-wrap:wrap;margin:2px 0 10px}
.rmenu button{font:inherit;font-size:13px;font-weight:600;border:1px solid var(--rule);
  background:var(--surface);color:var(--muted);border-radius:8px;padding:8px 15px;cursor:pointer}
.rmenu button:hover{border-color:var(--brand);color:var(--brand-ink)}
.rmenu button[aria-current="page"]{background:var(--brand);color:#fff;border-color:var(--brand)}
.rstamp{font-family:var(--mono);font-size:11px;color:var(--unscored);margin:0 0 4px}
.rh{font-family:var(--serif);font-size:22px;font-weight:700;color:var(--ink);margin:0}
.rsub{color:var(--muted);font-size:13px;margin:2px 0 14px}
.rk{font-size:11px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);margin:16px 0 8px}
.distbar{display:flex;height:42px;border-radius:8px;overflow:hidden;margin:4px 0 6px}
.distbar span{display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:13px}
.rank{display:flex;gap:10px;align-items:center;flex-wrap:wrap;border:1px solid var(--rule);
  border-radius:8px;padding:10px 12px;margin-bottom:8px;background:var(--surface)}
.rank .rnum{width:26px;height:26px;border-radius:50%;background:var(--now);color:#fff;font-weight:700;
  display:flex;align-items:center;justify-content:center;font-size:13px;flex:none}
.rank .rtitle{font-weight:700;color:var(--ink);flex:1;min-width:200px}
.rank .rown{color:var(--muted);font-size:11px;text-align:right;line-height:1.3}
.pillx{font-size:10px;font-weight:700;color:#fff;border-radius:5px;padding:4px 9px;white-space:nowrap;letter-spacing:.03em}
.tagx{font-size:10px;font-weight:700;border-radius:5px;padding:4px 9px;white-space:nowrap;border:1px solid var(--rule);color:var(--muted)}
.strip{border-radius:8px;padding:10px 14px;font-size:12.5px;line-height:1.45;margin-top:10px}
.rbanner{background:var(--brand-ink);color:#fff;border-radius:8px;padding:13px 18px;font-weight:600;
  text-align:center;margin-top:16px;font-size:14px;line-height:1.45}
.meterwrap{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.meter{position:relative;height:36px;flex:1;min-width:260px;background:var(--surface-3);border-radius:8px;overflow:visible}
.meter .fill{height:100%;background:var(--have);border-radius:8px 0 0 8px}
.meter .target{position:absolute;top:-6px;bottom:-6px;width:2px;background:var(--ink)}
.meter .tlab{position:absolute;top:-20px;transform:translateX(-50%);font-size:10px;font-weight:700;color:var(--ink)}
.trend{display:flex;gap:18px;align-items:flex-end;height:120px;padding:6px 0}
.trend .tb{display:flex;flex-direction:column;align-items:center;gap:5px;font-size:11px;color:var(--muted)}
.trend .tbar{width:44px;background:var(--have);border-radius:3px}
.fwcard{border:1px solid var(--rule);border-radius:8px;padding:12px 14px;background:var(--surface)}
.fwcard .p{font-size:26px;font-weight:700;color:var(--ink)}
.pbarwrap{height:12px;background:var(--surface-3);border-radius:6px;overflow:hidden;margin:6px 0}
.pbarwrap span{display:block;height:100%}
.rgrid3{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.rgrid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.kc{overflow-x:auto;padding-bottom:6px}
.kcgrid{display:grid;gap:5px;min-width:940px}
.kc .kchead{font-size:10px;font-weight:700;text-align:center;color:var(--ink);padding:2px;line-height:1.15}
.kc .cell{border-radius:6px;padding:12px 4px;text-align:center;font-weight:700;font-size:15px;color:#fff}
.kc .rl{font-size:10px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);
  display:flex;align-items:center}
.kc .flag{outline:2px dashed var(--blind);outline-offset:2px;border-radius:8px}
.slrow{display:flex;gap:12px;align-items:center;flex-wrap:wrap;border:1px solid var(--rule);
  border-radius:8px;padding:10px 12px;margin-bottom:8px;background:var(--surface)}
.mtile{border:1px solid var(--rule);border-radius:8px;padding:12px 14px;background:var(--surface)}
.mtile .n{font-size:26px;font-weight:700;color:var(--ink)}
.deltachip{font-weight:700;border-radius:6px;padding:2px 9px;font-size:12px}
.rcard{border:1px solid var(--rule);border-radius:8px;padding:14px;background:var(--surface)}
.rcard h4{margin:0 0 8px;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.rcard li{margin-bottom:6px;font-size:12.5px;line-height:1.4}
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
.jrow{display:flex;gap:8px;flex-wrap:wrap;margin-top:6px}
.jbtn{font:inherit;font-size:12.5px;font-weight:600;border:1px solid var(--rule);background:var(--surface);
  color:var(--brand-ink);border-radius:8px;padding:9px 14px;cursor:pointer;text-align:left;max-width:220px}
.jbtn:hover{border-color:var(--brand);background:#F3F7FA}
.jbtn .jb{display:block;color:var(--muted);font-weight:400;font-size:11px;margin-top:3px;line-height:1.35}
.jsteps{margin:8px 0 2px;padding-left:18px;color:var(--ink-2);font-size:12.5px;line-height:1.55}
.pbox{margin:12px 0}
.pbox .ph{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}
.pbox .ph .pt{font-size:11px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--muted)}
.copybtn{font:inherit;font-size:11px;border:1px solid var(--rule);background:var(--surface);
  border-radius:6px;padding:3px 11px;cursor:pointer;color:var(--brand)}
.copybtn:hover{border-color:var(--brand)}
.pbox pre{margin:0;background:#131A30;color:#F2F5FC;border-radius:8px;padding:12px;overflow:auto;
  max-height:230px;white-space:pre-wrap;word-break:break-word;font-size:11px;line-height:1.45;
  font-family:ui-monospace,Menlo,Consolas,monospace}

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
const session = { active: false, facilitator: "", recorded: "", changes: {}, newScenarios: [], importedScenarios: [] };

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
  if (!Array.isArray(session.importedScenarios)) session.importedScenarios = [];
  mergeImported();
}
/* Imported scenarios live in the session only. Lay them over the built-in library so
   they render in every view, without ever being written to a record. */
function mergeImported() {
  (session.importedScenarios || []).forEach(sc => {
    if (!DATA.scenarios.some(x => x.id === sc.id)) DATA.scenarios.push(sc);
  });
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
        ${s.status !== "published" ? `<span class="chip draft">${esc(s.status)}</span>` : ""}
        ${s.origin === "hypothesis" ? '<span class="chip modeler">Threat modeler</span>' : ""}</div>
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
      ${s.origin === "hypothesis" ? '<span class="chip modeler">Threat modeler hypothesis</span>' : ""}
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
  const v = u.pending_v ?? (e.dettect ? e.dettect.visibility : "");
  const d = u.pending_d ?? (e.dettect ? e.dettect.detection : "");
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
          const held = rowChange(s.id, step);
          const vv = k === "visibility" ? el.value
                   : (held.pending_v ?? (base.visibility ?? ""));
          const dd = k === "detection" ? el.value
                   : (held.pending_d ?? (base.detection ?? ""));
          if (vv === "" || dd === "") {
            // Half a pair. Hold what was picked so it survives the redraw,
            // and stay Unscored until the other half arrives.
            setRow(s.id, step, "dettect", null);
            setRow(s.id, step, "pending_v", vv === "" ? null : vv);
            setRow(s.id, step, "pending_d", dd === "" ? null : dd);
          } else {
            const q = base.quality;
            setRow(s.id, step, "pending_v", null);
            setRow(s.id, step, "pending_d", null);
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

/* ---------- import a scenario from a journey: incident, research feeds, hypothesis ---------- */
/* The prompts live here so they open right next to the paste box, no doc-hunting.
   They mirror docs/PROTOTYPE-SCENARIO-INTAKE.md; keep the two in step if you edit. */
const P_MAP =
`You are mapping ONE incident into a Liszt scenario. Research it from the source(s) I give you,
then output a SINGLE JSON object and NOTHING else. No prose, no code fence, just JSON.

THE INCIDENT:
<<< paste the incident name and its source URL here >>>

JSON shape:
{
  "title": "short scenario title, attacker-goal phrasing",
  "one_liner": "2-3 plain sentences about OUR environment ('our', 'we'): what the attacker does and the damage.",
  "classification": {
    "ai_infrastructure_layer": "one layer, exactly one of: L0 · Infrastructure | L1 · Data | L2 · Model | L3 · Orchestration & Agent | L4 · Application",
    "evidence": "seen-in-the-wild for a real incident, or seen-in-research for a proof of concept",
    "priority": "NOW, NEAR-TERM, or BACKLOG",
    "priority_rationale": ["3 short plain-sentence bullets"]
  },
  "attack_path": [
    { "step": 1, "layer": "the stack layer this move lands on", "text": "one move of the attack, plainly" }
  ],
  "telemetry": [
    { "step": 1, "signal": "the observable event this move produces", "emitted_at": "where it is emitted from, named generically", "detection_opportunity": "what a detection could look for" }
  ],
  "framework_mapping": {
    "baseline": "2026.07",
    "attack": ["ATT&CK v19.1 IDs; [] if none"],
    "atlas": ["ATLAS 2026.07 IDs; [] if none"],
    "owasp_llm": ["OWASP LLM 2025 IDs; [] if none"],
    "owasp_agentic": ["OWASP Agentic 2026 IDs; [] if none"]
  },
  "incidents": [ { "title": "source title", "url": "source URL", "tier": "1, 2, or 3" } ]
}

Rules:
  - One telemetry entry per attack_path step, same step number.
  - DO NOT include any coverage, visibility, detection or score field. Owners score it later; you
    only identify the signal that WOULD exist.
  - Real framework IDs only where you are confident; a short defensible list beats a long guess.
  - 4-7 distinct steps. Valid JSON only, no trailing commas, no commentary.`;

const P_INCIDENT =
`You are a threat-intelligence researcher building a list of PUBLISHED, real-world incidents that
involve AI INFRASTRUCTURE. Use web search and cite a source URL for every item.

Include incidents touching any of: model supply chain (tampered/backdoored models, malicious
models on public hubs, typosquatted model or package names); inference and serving (exploited
inference servers, model-load code execution, exposed model endpoints and AI gateways); data
(training-data or RAG poisoning, exposed vector stores); orchestration and agents (agent tool
abuse, prompt-injection with real impact, malicious MCP servers); MLOps (compromised pipelines,
leaked AI credentials); guardrail bypasses that caused a real incident.

For each item give: 1) short name  2) date  3) who disclosed it  4) one sentence on what happened
5) the single layer it most affects (L0 · Infrastructure | L1 · Data | L2 · Model | L3 · Orchestration & Agent | L4 · Application)
6) source URL  7) source tier (1 first-party, 2 reputable press/research, 3 community)  8) why it matters.

Rules: prefer confirmed incidents over demos (label any notable demo "research, not in the wild");
prefer first-party and tier-1 sources; no marketing; do not speculate; spread across the layers.
Return the 12 most relevant items as a table, most recent and most severe first.`;

const P_RESEARCH =
`You are a threat-intelligence researcher. Search these SPECIFIC sources for published incidents
and technical writeups about attacks on AI systems and AI infrastructure, and cite a link for each:
  - Wiz research (wiz.io/blog and their research team posts)
  - JFrog security research (jfrog.com, malicious-package and model findings)
  - Mandiant / Google Threat Intelligence (cloud.google.com/security, Mandiant blog)
  - The AI Incident Database (incidentdatabase.ai), a public community record of AI harms

Focus on AI infrastructure: malicious or backdoored models, poisoned hubs and packages, compromised
ML pipelines, exposed model endpoints and vector stores, agent and MCP tool abuse, prompt-injection
with real impact, leaked AI credentials.

For each item give: 1) short name  2) date  3) source (Wiz, JFrog, Mandiant, or AI Incident Database)
and a link  4) one sentence on what happened  5) the single layer it most affects (L0 · Infrastructure
| L1 · Data | L2 · Model | L3 · Orchestration & Agent | L4 · Application)  6) source tier (1 first-party,
2 reputable research, 3 community).

Rules: only these four sources; if one has nothing relevant, say so and move on; prefer confirmed
incidents and concrete technical findings over opinion; mark unknown details "unknown".
Return the 12 most relevant items as a table, most recent and most severe first.

Then, once I pick one, use the mapping prompt to turn it into scenario JSON.`;

const P_HYP =
`You are an AI threat modeler. Take the analyst hypothesis below, an attack that has NOT happened
yet, and turn it into a rigorous Liszt scenario. Output a SINGLE JSON object and NOTHING else.

THE HYPOTHESIS:
<<< write your hypothesis here: what is the attacker trying to do, and what makes you worried it
    could work against us? >>>

Sharpen the idea, do not judge it. Break it into concrete moves; for each, name the observable
signal a defender would look for.

JSON shape:
{
  "origin": "hypothesis",
  "proposed_by": "AI Threat Modeler",
  "title": "short scenario title, attacker-goal phrasing",
  "one_liner": "2-3 plain sentences about OUR environment: what the attacker does and why it would hurt.",
  "classification": {
    "ai_infrastructure_layer": "one of: L0 · Infrastructure | L1 · Data | L2 · Model | L3 · Orchestration & Agent | L4 · Application",
    "evidence": "seen-in-research",
    "priority": "NOW, NEAR-TERM, or BACKLOG",
    "priority_rationale": ["3 short bullets; it is honest to say 'nobody has run this yet, but ...'"]
  },
  "attack_path": [ { "step": 1, "layer": "stack layer this move lands on", "text": "one move, plainly" } ],
  "telemetry": [ { "step": 1, "signal": "the event this move WOULD produce", "emitted_at": "where it would be emitted from", "detection_opportunity": "what a detection could look for" } ],
  "framework_mapping": {
    "baseline": "2026.07",
    "attack": ["[] if none"], "atlas": ["[] if none"],
    "owasp_llm": ["[] if none"], "owasp_agentic": ["[] if none"]
  }
}

Rules:
  - Keep "origin": "hypothesis" and "proposed_by": "AI Threat Modeler" exactly, so Liszt tags it.
    A specific analyst may replace proposed_by with their own name.
  - One telemetry entry per step. DO NOT include any coverage, visibility, detection or score field.
  - 4-7 distinct steps. A hypothesis may map to no framework IDs yet; an empty list is a fine answer.
  - Valid JSON only, no trailing commas, no commentary.`;

const JOURNEYS = [
  { key: "incident", label: "Published incident", origin: "incident",
    blurb: "Something that really happened to someone else. Find it, then map it.",
    steps: ["Run the first prompt in an LLM with web access and pick an incident from the list.",
            "Run the second prompt on the one you picked.",
            "Paste the JSON it returns into the box below and add it."],
    prompts: [ {title:"1 · Find incidents", body: P_INCIDENT}, {title:"2 · Map the one you picked", body: P_MAP} ] },
  { key: "research", label: "Threat-research feeds", origin: "incident",
    blurb: "Search Wiz, JFrog, Mandiant and the AI Incident Database.",
    steps: ["Run the first prompt in an LLM with web access; it searches those four sources.",
            "Pick an incident, then run the second prompt on it.",
            "Paste the JSON into the box below and add it."],
    prompts: [ {title:"1 · Search the feeds", body: P_RESEARCH}, {title:"2 · Map the one you picked", body: P_MAP} ] },
  { key: "hypothesis", label: "Analyst hypothesis", origin: "hypothesis",
    blurb: "An attack nobody has run yet. Tagged as Threat modeler proposed.",
    steps: ["Write your hypothesis into the prompt where marked, and run it in any LLM.",
            "Paste the JSON into the box below and add it. It arrives tagged Threat modeler."],
    prompts: [ {title:"Turn a hypothesis into JSON", body: P_HYP} ] }
];
let importJourney = null;

/* Take whatever the mapping prompt produced and make it safe to render: fill the
   fields the views read, force draft status, and never trust a coverage the file
   claims, because coverage is computed from scores captured with the owners. */
function normalizeImported(raw) {
  const s = (raw && typeof raw === "object") ? raw : {};
  const cls = s.classification || {};
  const out = {
    schema_version: 1, imported: true, status: "draft",
    origin: s.origin === "hypothesis" ? "hypothesis" : "incident",
    proposed_by: String(s.proposed_by || (s.origin === "hypothesis" ? "AI Threat Modeler" : "")).trim(),
    id: String(s.id || "").trim(),
    slug: String(s.slug || "").trim(),
    title: String(s.title || "").trim(),
    one_liner: String(s.one_liner || "").trim(),
    classification: {
      primary_layer_component: cls.primary_layer_component || "",
      ai_infrastructure_layer: cls.ai_infrastructure_layer || "L2 \u00b7 Model",
      evidence: EV[cls.evidence] ? cls.evidence
                : (s.origin === "hypothesis" ? "seen-in-research" : "seen-in-the-wild"),
      priority: ["NOW", "NEAR-TERM", "BACKLOG"].includes(cls.priority) ? cls.priority : "NEAR-TERM",
      priority_rationale: Array.isArray(cls.priority_rationale) ? cls.priority_rationale : []
    },
    framework_mapping: s.framework_mapping || {
      baseline: DATA.baseline.id, attack: [], atlas: [], owasp_llm: [], owasp_agentic: [] },
    attack_path: Array.isArray(s.attack_path) ? s.attack_path.map((a, i) => ({
      step: a.step || i + 1, layer: a.layer || "", text: a.text || "",
      attack: Array.isArray(a.attack) ? a.attack : [],
      atlas: Array.isArray(a.atlas) ? a.atlas : [] })) : [],
    telemetry: Array.isArray(s.telemetry) ? s.telemetry.map((t, i) => ({
      step: t.step || i + 1, signal: t.signal || "", emitted_at: t.emitted_at || "",
      source: t.source || "", detection_opportunity: t.detection_opportunity || "",
      owner: t.owner || "" })) : [],
    incidents: Array.isArray(s.incidents) ? s.incidents : [],
    provenance: s.provenance || {}
  };
  if (!out.title) throw new Error("the scenario needs a title");
  if (!out.id || DATA.scenarios.some(x => x.id === out.id)) {
    let n = 1; while (DATA.scenarios.some(x => x.id === "IMP-" + n)) n++;
    out.id = "IMP-" + n;
  }
  if (!out.slug) out.slug = out.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  if (!out.one_liner) out.one_liner = out.title;
  return out;
}
function addImported(raw, originFallback) {
  const obj = (raw && typeof raw === "object") ? { ...raw } : {};
  if (!obj.origin && originFallback) obj.origin = originFallback;
  const sc = normalizeImported(obj);
  session.importedScenarios.push(sc);
  DATA.scenarios.push(sc);
  session.recorded = session.recorded || new Date().toISOString().slice(0, 10);
  saveSession();
  return sc;
}
function dropImported(i) {
  const sc = session.importedScenarios[i];
  if (!sc) return;
  session.importedScenarios.splice(i, 1);
  const j = DATA.scenarios.findIndex(x => x.id === sc.id);
  if (j >= 0) DATA.scenarios.splice(j, 1);
  saveSession();
}

function importPanel() {
  const list = session.importedScenarios || [];
  const listHtml = list.length ? list.map((p, i) => `<div class="prop"><div>
      <div class="t">${esc(p.id)} &middot; ${esc(p.title)}</div>
      <div class="m">${p.origin === "hypothesis" ? "threat-modeler hypothesis" : "from incident"} &middot;
        ${esc(p.classification.ai_infrastructure_layer)} &middot;
        ${(p.attack_path || []).length} steps &middot; ${(p.telemetry || []).length} signals</div>
    </div><button data-dropimp="${i}">Remove</button></div>`).join("")
    : '<div style="color:var(--muted)">None yet.</div>';

  let body;
  if (!importJourney) {
    body = `<div class="sub" style="margin-bottom:6px">Bring in a scenario. Pick how you are sourcing
      it, and the directions, the prompts and the paste box open right here.</div>
      <div class="jrow">${JOURNEYS.map(j => `<button class="jbtn" data-open="${j.key}">${esc(j.label)}
        <span class="jb">${esc(j.blurb)}</span></button>`).join("")}</div>`;
  } else {
    const j = JOURNEYS.find(x => x.key === importJourney) || JOURNEYS[0];
    const prompts = j.prompts.map((p, i) => `<div class="pbox">
      <div class="ph"><span class="pt">${esc(p.title)}</span>
        <button class="copybtn" data-jkey="${j.key}" data-pidx="${i}">Copy prompt</button></div>
      <pre>${esc(p.body)}</pre></div>`).join("");
    body = `<button class="toggle" id="imp-back">&larr; all journeys</button>
      <div class="sub" style="margin:10px 0 2px"><strong>${esc(j.label)}.</strong> ${esc(j.blurb)}</div>
      <ol class="jsteps">${j.steps.map(t => `<li>${esc(t)}</li>`).join("")}</ol>
      ${prompts}
      <div class="fld" style="margin-top:12px"><label>Paste the JSON the prompt produced</label>
        <textarea id="imp-json" rows="8" placeholder="paste the scenario JSON here"
          style="width:100%;box-sizing:border-box;font-family:ui-monospace,Menlo,monospace;font-size:12px"></textarea>
        <span class="hint">One scenario object, or an array of them. It needs at least a title;
          every other field fills in with a sensible default.</span></div>
      <div style="display:flex;gap:8px">
        <button class="toggle" id="imp-add">Add to the library</button>
        <button class="toggle" id="imp-cancel">Cancel</button></div>
      <div class="err" id="imp-err" hidden></div>`;
  }
  return `<div class="panel"><h3>Bring in a scenario (${list.length} imported)</h3>
    ${listHtml}
    <div style="margin-top:14px">${body}</div></div>`;
}


function wireImport() {
  $$("#sessionview .jbtn[data-open]").forEach(b => b.onclick = () => {
    importJourney = b.dataset.open; renderSession();
  });
  const back = $("#imp-back");
  if (back) back.onclick = () => { importJourney = null; renderSession(); };
  const cancel = $("#imp-cancel");
  if (cancel) cancel.onclick = () => { importJourney = null; renderSession(); };
  $$("#sessionview .copybtn").forEach(b => b.onclick = () => {
    const j = JOURNEYS.find(x => x.key === b.dataset.jkey);
    const pr = j && j.prompts[Number(b.dataset.pidx)];
    if (!pr) return;
    const done = () => { const t = b.textContent; b.textContent = "Copied"; setTimeout(() => b.textContent = t, 1200); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(pr.body).then(done).catch(() => { b.textContent = "Press Cmd-C"; });
    } else { b.textContent = "Press Cmd-C"; }
  });
  $$("#sessionview .prop button[data-dropimp]").forEach(b => b.onclick = () => {
    dropImported(Number(b.dataset.dropimp));
    renderSession(); renderList(); renderDetail(); updateSessionCount();
  });
  const add = $("#imp-add");
  if (!add) return;
  add.onclick = () => {
    const err = $("#imp-err");
    let raw;
    try { raw = JSON.parse($("#imp-json").value); }
    catch (e) { err.textContent = "That is not valid JSON: " + e.message; err.hidden = false; return; }
    try {
      const j = JOURNEYS.find(x => x.key === importJourney);
      (Array.isArray(raw) ? raw : [raw]).forEach(o => addImported(o, j ? j.origin : undefined));
      importJourney = null;
      renderSession(); renderList(); renderDetail(); updateSessionCount();
    } catch (e) { err.textContent = e.message; err.hidden = false; }
  };
}


/* ---------- session review and export ---------- */
function updateSessionCount() {
  const n = changedCount(), p = (session.newScenarios || []).length, im = (session.importedScenarios || []).length;
  const el = $("#scount");
  if (!el) return;
  const parts = [];
  if (n) parts.push(`${n} change${n === 1 ? "" : "s"} across ${changedScenarios().length} scenario${changedScenarios().length === 1 ? "" : "s"}`);
  if (p) parts.push(`${p} proposed scenario${p === 1 ? "" : "s"}`);
  if (im) parts.push(`${im} imported scenario${im === 1 ? "" : "s"}`);
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

  $("#sessionview").innerHTML = head + proposalsPanel() + importPanel() + body;
  wireProposals(); wireImport();

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
        priority: p.priority, one_liner: p.one_liner || "" })),
      imported_scenarios: session.importedScenarios || []
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
        session.importedScenarios = Array.isArray(d.imported_scenarios) ? d.imported_scenarios : [];
        mergeImported();
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
    (session.importedScenarios || []).forEach(sc => {
      const j = DATA.scenarios.findIndex(x => x.id === sc.id);
      if (j >= 0) DATA.scenarios.splice(j, 1);
    });
    session.changes = {}; session.newScenarios = []; session.importedScenarios = [];
    proposeOpen = false; importJourney = null; saveSession();
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
  $("#reports").hidden = v !== "reports";
  $("#sessionview").hidden = v !== "session";
  if (v === "coverage") renderCoverage();
  if (v === "usecases") renderUseCases();
  if (v === "frameworks") renderFrameworks();
  if (v === "reports") renderReports();
  if (v === "session") renderSession();
}

/* ---------- reports (illustrative mock) ---------- */
const LAYERCOL = { App:"#566DB2", Agent:"#5A3B9C", Model:"#277885", Data:"#9A6B08", Infra:"#63707B" };
function reportHead(t, sub) {
  return `<div class="rstamp">generated by liszt from ${DATA.scenarios.length} scenario records, pinned `
    + `ATT&CK v19.1 and ATLAS 2026.07 · illustrative figures</div>`
    + `<div class="rh">${esc(t)}</div><div class="rsub">${esc(sub)}</div>`;
}
const covc = (p) => p >= 70 ? "var(--have)" : (p >= 40 ? "var(--collectable)" : "var(--blind)");
const covbg = (p) => p >= 70 ? "var(--have-bg)" : (p >= 40 ? "var(--collectable-bg)" : "var(--blind-bg)");

function reportPosture() {
  const tiles = [["21","scenarios","15 from real incidents, 6 hypotheses","var(--ink)"],
    ["96","scored moves","across the five stack layers","var(--ink)"],
    ["14","blind moves","every one owned and ticketed","var(--blind)"]];
  const rows = [
    {n:1,l:"Model",lc:LAYERCOL.Model,t:"The model’s decision path leaves no record",v:"Blind",vc:"var(--blind)",ev:"4 scenarios, 3 incidents",dl:"No use case yet",dc:"var(--blind)",db:"var(--blind-bg)",o:"AI engineering",k:"OBS-1203"},
    {n:2,l:"Data",lc:LAYERCOL.Data,t:"Documents reach our people with no inspection",v:"Blind",vc:"var(--blind)",ev:"3 scenarios, 2 incidents",dl:"No use case yet",dc:"var(--blind)",db:"var(--blind-bg)",o:"Data platform",k:"OBS-1198"},
    {n:3,l:"Agents",lc:LAYERCOL.Agent,t:"Agent tool calls are logged but never watched",v:"Collectable",vc:"var(--collectable)",ev:"5 scenarios, 3 incidents",dl:"UC-015 in build",dc:"var(--collectable)",db:"var(--collectable-bg)",o:"Observability",k:"OBS-1201"},
    {n:4,l:"Agents",lc:LAYERCOL.Agent,t:"Shared prompt template edits go unreviewed",v:"Collectable",vc:"var(--collectable)",ev:"1 scenario, hypothesis",dl:"UC-014 active",dc:"var(--have)",db:"var(--have-bg)",o:"Platform eng.",k:"OBS-1195"}];
  return reportHead("The Posture Report","How worried should I be, and what do I prioritize, answered from the records.")
    + `<div class="rk">Coverage, across every scored move</div>`
    + `<div class="distbar"><span style="width:62%;background:var(--have)">Have 62%</span>`
      + `<span style="width:23%;background:var(--collectable)">Collectable 23%</span>`
      + `<span style="width:15%;background:var(--blind)">Blind 15%</span></div>`
    + `<div class="tiles">${tiles.map(([n,l,sub,c])=>`<div class="tile"><div class="n" style="color:${c}">${n}</div>`
      + `<div class="l">${l}</div><div class="s">${sub}</div></div>`).join("")}</div>`
    + `<div class="rk">What to prioritize, ranked from the records</div>`
    + rows.map(r=>`<div class="rank"><span class="rnum">${r.n}</span>`
      + `<span class="pillx" style="background:${r.lc}">${r.l.toUpperCase()}</span>`
      + `<span class="rtitle">${esc(r.t)}</span>`
      + `<span class="pillx" style="background:${r.vc}">${r.v.toUpperCase()}</span>`
      + `<span class="tagx">${esc(r.ev)}</span>`
      + `<span class="tagx" style="color:${r.dc};background:${r.db};border-color:${r.dc}">${esc(r.dl)}</span>`
      + `<span class="rown">${esc(r.o)}<br>${esc(r.k)}</span></div>`).join("")
    + `<div class="strip" style="background:var(--surface-2);color:var(--ink-2)">The order is computed: blind outranks collectable, incidents outrank hypotheses, more scenarios outrank fewer, undefended outranks defended. Nobody hand-sorts this list.</div>`
    + `<div class="rbanner">How worried is never an adjective here. It is a distribution, a ranked list, and an owner on every line, all generated from the records.</div>`;
}

function reportScoreboard() {
  const trend = [["Q3 25",48],["Q4 25",54],["Q1 26",58],["Q2 26",62],["restated",58]];
  const fw = [["MITRE ATT&CK","v19.1",65,"#566DB2","52 of 96 moves"],
    ["MITRE ATLAS","2026.07",58,"#277885","31 of 96 moves"],
    ["OWASP LLM & Agentic","2025 / 2026",62,"#5A3B9C","13 of 96 moves"]];
  const d=[["+4","var(--have)","instrumentation we built"],["-8","var(--blind)","techniques the new release added"],["-4","var(--now)","net restatement, every point named"]];
  return reportHead("The Scoreboard","Where we stand against the pinned standards, whether the 80 percent goal is met, and why the number moved.")
    + `<div class="rk">The goal, on the pinned ruler</div>`
    + `<div class="meterwrap"><div style="font-size:30px;font-weight:700;color:var(--ink)">62%</div>`
      + `<div class="meter"><div class="fill" style="width:62%"></div>`
        + `<div class="target" style="left:80%"></div><div class="tlab" style="left:80%">TARGET 80%</div></div>`
      + `<span class="deltachip" style="background:var(--have-bg);color:var(--have)">+4 this quarter</span></div>`
    + `<div class="rsub" style="margin-top:8px">18 points to go, and the ruler cannot move under us.</div>`
    + `<div class="rk">The trend, same ruler the whole way</div>`
    + `<div class="trend">${trend.map(([l,v])=>`<div class="tb"><div style="font-weight:700;color:var(--ink)">${v}</div>`
      + `<div class="tbar" style="height:${(v-30)/40*90}px;${l==="restated"?"background:transparent;border:2px dashed var(--have)":""}"></div>`
      + `<div>${l}</div></div>`).join("")}</div>`
    + `<div class="rsub">The dashed bar is Q2 26 restated under the next release, both positions kept.</div>`
    + `<div class="rk">By framework, at the pinned version</div>`
    + `<div class="rgrid3">${fw.map(([n,ver,pc,c,sub])=>`<div class="fwcard">`
      + `<div style="display:flex;justify-content:space-between;align-items:center"><strong>${n}</strong>`
      + `<span class="pillx" style="background:${c}">${ver}</span></div>`
      + `<div class="p">${pc}%</div><div class="pbarwrap"><span style="width:${pc}%;background:${c}"></span></div>`
      + `<div class="s" style="color:var(--muted);font-size:12px">${sub}</div></div>`).join("")}</div>`
    + `<div class="rk">The two ways to count, both on the page</div>`
    + `<div class="rgrid2">`
      + `<div class="rcard"><h4 style="color:var(--have)">Posture, where the 80 percent lives</h4>`
        + `<div style="font-size:12.5px;color:var(--ink-2)">62 percent of the 96 scored moves in our threat model are at Have. Depth, against the attacks we have mapped.</div></div>`
      + `<div class="rcard"><h4>Breadth, a different claim</h4>`
        + `<div style="font-size:12.5px;color:var(--ink-2)">Our scenarios exercise 47 techniques across the pinned catalogs. Adding scenarios grows this; the goal only moves when scored moves reach Have.</div></div></div>`
    + `<div class="strip" style="background:var(--collectable-bg);color:#8A5B08"><strong>Every movement named &nbsp;</strong>`
      + d.map(([n,c,t])=>`<span class="deltachip" style="background:${c};color:#fff;margin-right:6px">${n}</span>${t}. `).join("")+`</div>`
    + `<div class="rbanner">A goal only means something on a fixed ruler. This page names the ruler, shows both ways to count, and explains every point of movement.</div>`;
}

function reportKillChain() {
  const KC=[["Reconnaissance",6,0,33,false],["Initial Access",14,3,79,false],["Execution",16,4,75,false],
    ["Persistence",8,1,69,false],["Defense Evasion",11,0,27,true],["Credential Access",7,2,71,false],
    ["Discovery",9,0,33,true],["Collection",12,2,75,false],["Exfiltration",9,2,78,false],["Impact",4,0,50,false]];
  const mcol=(n)=>n>=14?"#22357A":n>=10?"#5E76BD":n>=7?"#9AABD8":"#CBD3EA";
  const ucol=(n,f)=>f?"var(--blind-bg)":n>=4?"#1E7F4B":n>=1?"#A9CDBB":"var(--surface-3)";
  const cols=`grid-template-columns:120px repeat(10,1fr)`;
  const heads=`<div class="rl"></div>`+KC.map(k=>`<div class="kchead" style="${k[4]?"color:var(--blind)":""}">${k[0]}</div>`).join("");
  const r1=`<div class="rl">Scenario moves</div>`+KC.map(k=>`<div class="cell" style="background:${mcol(k[1])};color:${k[1]>=7?"#fff":"#1F2A63"}">${k[1]}</div>`).join("");
  const r2=`<div class="rl">Use cases</div>`+KC.map(k=>`<div class="cell" style="background:${ucol(k[2],k[4])};color:${(k[2]>=1&&!k[4])?"#fff":k[4]?"var(--blind)":"var(--muted)"}">${k[2]}</div>`).join("");
  const r3=`<div class="rl">Coverage</div>`+KC.map(k=>`<div class="cell" style="background:${covbg(k[3])};color:${covc(k[3])};font-size:13px">${k[3]}%</div>`).join("");
  return reportHead("The Kill Chain Map","Where attacks travel and where defenses stand, stage by stage, in the tactic vocabulary we already pin.")
    + `<div class="kc"><div class="kcgrid" style="${cols}">${heads}${r1}${r2}${r3}</div></div>`
    + `<div class="strip" style="background:var(--surface-2);color:var(--ink-2)">A stage is flagged when eight or more moves land there and nothing defends it. <strong style="color:var(--blind)">Defense Evasion</strong> (11 moves, 0 use cases) and <strong style="color:var(--blind)">Discovery</strong> (9 moves, 0 use cases) are the busiest undefended stages. Four stages with no scenario traffic are omitted.</div>`
    + `<div class="rbanner">Per-scenario reports can look healthy while a whole stage sits undefended. The empty column is where the next use case comes from.</div>`;
}

function reportStack() {
  const L=[["Application","#566DB2",16,22,17,4,1,4,77,false],
    ["Agents","#5A3B9C",14,24,13,9,2,4,54,false],
    ["Model","#277885",12,18,8,4,6,1,44,true],
    ["Data","#9A6B08",11,14,8,3,3,2,57,false],
    ["Infrastructure","#63707B",13,18,14,2,2,3,78,false]];
  const rows=L.map(([name,c,sc,mv,hv,cl,bl,uc,pct,flag])=>{
    const dist=`<div class="bar" style="height:16px;flex:1;min-width:160px"><span class="Have" style="width:${hv/mv*100}%"></span>`
      +`<span class="Collectable" style="width:${cl/mv*100}%"></span><span class="Blind" style="width:${bl/mv*100}%"></span></div>`;
    return `<div class="slrow"${flag?' style="border-color:var(--blind)"':''}>`
      +`<span class="pillx" style="background:${c};min-width:110px;text-align:center">${name.toUpperCase()}</span>`
      +`<span style="font-weight:700;font-size:15px;color:var(--ink);width:34px;text-align:center">${sc}</span>`
      +`<span style="font-weight:700;font-size:15px;color:var(--ink);width:34px;text-align:center">${mv}</span>`
      +dist
      +`<span style="font-weight:700;color:${covc(pct)};width:44px;text-align:center">${pct}%</span>`
      +`<span style="font-weight:700;font-size:15px;color:var(--ink);width:34px;text-align:center">${uc}</span>`
      +`<span class="tagx" style="${flag?"color:var(--blind);background:var(--blind-bg);border-color:var(--blind)":"color:var(--have);background:var(--have-bg);border-color:var(--have)"}">${flag?"Underdefended":"Keeping pace"}</span></div>`;
  }).join("");
  return reportHead("The Stack Layer Report","Every layer of the AI stack, its attack traffic, its coverage, and whether defense is keeping pace.")
    + `<div class="rsub" style="font-size:11px;letter-spacing:.05em;text-transform:uppercase">Layer · scenarios · moves · coverage (have / collectable / blind) · at have · use cases · verdict</div>`
    + rows
    + `<div class="strip" style="background:var(--surface-2);color:var(--ink-2)">A layer is flagged when eight or more exposed moves outrun its defenses at more than five per use case. <strong style="color:var(--blind)">Model</strong> flags: 10 exposed moves, 1 use case, six of our fourteen blind moves live here. Scenario counts sum past 21 because one attack crosses several layers.</div>`
    + `<div class="rbanner">The busiest layer is not the riskiest layer. Traffic, coverage and defense sit side by side, and the imbalance is where the next quarter of work goes.</div>`;
}

function reportMovement() {
  const tiles=[["Coverage at Have","62%","+4",true,"from 58"],["Scenarios","21","+3",true,"from 18"],
    ["Scored moves","96","+12",true,"from 84"],["Blind moves","14","-2",true,"from 16"],["Use cases","14","+3",true,"from 11"]];
  const cards=[
    ["What entered, by front door",["+2 from the incident journey: an ATLAS case study and a vendor writeup","+1 from the hypothesis journey: the poisoned template, SC-022","1 disclosed breach record revised as the postmortem landed"]],
    ["Scores that moved, and why",["4 moves rescored up after instrumentation shipped","2 moves rescored down: a session corrected an optimistic log-depth assumption","Every rescore carries who, when and why"]],
    ["Gaps closed and opened",["3 closed: two by new emit, one by a rescore that proved coverage","1 opened: the new hypothesis exposed unreviewed template edits","Net blind moves, 16 down to 14"]],
    ["Use cases and the ladder",["3 built: UC-013 and UC-014 active, UC-015 in build","First promotion: UC-009, notify to assisted, block attached","Nothing runs autonomous, and nothing asked to"]]];
  return reportHead("The Movement Report","What changed since last quarter and why, line by line. The other four pages are snapshots. This is the pulse.")
    + `<div class="tiles" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr))">`
      + tiles.map(([l,n,dl,good,was])=>`<div class="mtile"><div class="l" style="font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)">${l}</div>`
        + `<div style="display:flex;align-items:center;gap:8px"><span class="n">${n}</span>`
        + `<span class="deltachip" style="background:${good?"var(--have-bg)":"var(--blind-bg)"};color:${good?"var(--have)":"var(--blind)"}">${dl}</span></div>`
        + `<div class="s" style="font-size:11px;color:var(--muted);font-style:italic">${was}</div></div>`).join("")+`</div>`
    + `<div class="rgrid2">${cards.map(([h,items])=>`<div class="rcard"><h4>${esc(h)}</h4><ul style="margin:0;padding-left:16px">`
      + items.map(i=>`<li>${esc(i)}</li>`).join("")+`</ul></div>`).join("")}</div>`
    + `<div class="strip" style="background:var(--surface-2);color:var(--ink-2)"><strong>The standards watch &nbsp;</strong>One release landed late in the quarter. The adoption playbook ran, the scoreboard carries both positions (62 and 58 restated), and the evidence was not retouched.</div>`
    + `<div class="rbanner">The other four reports are photographs. This one is the pulse: what entered, what moved, what closed, who earned trust, every line traceable to a record change.</div>`;
}

function renderReports() {
  const REPORTS=[["posture","Posture"],["scoreboard","Scoreboard"],["killchain","Kill chain map"],["stack","Stack layers"],["movement","Movement"]];
  if (!state.report) state.report = "posture";
  const menu=`<div class="rmenu">${REPORTS.map(([k,l])=>`<button data-report="${k}" aria-current="${state.report===k?"page":"false"}">${l}</button>`).join("")}</div>`;
  const build={posture:reportPosture,scoreboard:reportScoreboard,killchain:reportKillChain,stack:reportStack,movement:reportMovement}[state.report]||reportPosture;
  $("#reports").innerHTML = `<div class="panel">${menu}${build()}</div>`;
  $$("#reports .rmenu button").forEach(b => b.onclick = () => { state.report=b.dataset.report; renderReports(); });
}

function route() {
  const m = (location.hash || "").match(/^#\/scenario\/([A-Za-z0-9-]+)$/);
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
    if (changedCount() || (session.newScenarios || []).length || (session.importedScenarios || []).length) {
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
    <button data-view="reports" aria-current="false">Reports</button>
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
  <section id="reports" hidden></section>
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
