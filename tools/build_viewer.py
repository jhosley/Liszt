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
# The mechanical half of the testing readiness gate, imported rather than restated. The
# emitter refuses to write a spec when this returns blockers, so the page must agree with
# it exactly; a second copy of the rule in JavaScript would drift the first time either
# side was edited.
from emit_testspec import readiness as testing_blockers, resolve_rows

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_VERSION = 1

# A parked design mockup, embedded as-is in its own tab. It is not part of the
# record library and nothing in the catalog reads it. If the file is absent the
# tab does not appear and the rest of the page is unaffected.
PARKED_MOCKUP = ROOT / "reference" / "mockups" / "beyond-ai-scenarios.html"


def parked_mockup_b64() -> str:
    """The beyond-AI mockup, base64 encoded, or '' when it is not present.

    Base64 rather than an inlined string: the mockup is a whole HTML document
    with its own script tags, and encoding sidesteps every escaping question
    about nesting one document inside another.
    """
    import base64
    try:
        raw = PARKED_MOCKUP.read_bytes()
    except OSError:
        return ""
    return base64.b64encode(raw).decode("ascii")


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
            # Whether the emitter would write a spec for this record today, and if not,
            # why. A blocked record is a normal and useful answer: knowing which scenarios
            # cannot be tested yet, and what is missing, is the point of showing this.
            "testing": {"blockers": testing_blockers(
                rec, resolve_rows(rec, None),
                ROOT / "scenarios" / f"{rec.get('id')}-{rec.get('slug')}.yaml")},
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
.chip.review{background:#FBEFEC;color:#A93F34;border:1px solid #E3B5AC}
.reviewbox{margin:10px 0;padding:10px 13px;border-left:3px solid #A93F34;background:#FBEFEC;
  border-radius:6px;font-size:13px;color:#6E2921}
.reviewbox ul{margin:6px 0 0;padding-left:18px}
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
.irail{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0 14px}
.ibtn{font:inherit;font-size:12.5px;font-weight:600;border:1px solid var(--rule);background:var(--surface);
  color:var(--brand-ink);border-radius:8px;padding:8px 14px;cursor:pointer}
.ibtn:hover{border-color:var(--brand);background:#F3F7FA}
.ibtn[aria-current="true"]{border-color:var(--brand);color:var(--brand);box-shadow:0 0 0 1px var(--brand)}
.jsteps{margin:8px 0 2px;padding-left:18px;color:var(--ink-2);font-size:12.5px;line-height:1.55}

/* scenario testing ---------------------------------------------------------- */
.tsum{background:var(--surface-2);border-left:3px solid var(--brand);border-radius:0 6px 6px 0;
      padding:10px 14px;font-size:13px;color:var(--ink-2);margin-bottom:12px}
.tlist{border-top:1px solid var(--surface-3)}
.trow{padding:9px 0;border-bottom:1px solid var(--surface-3);display:grid;
      grid-template-columns:1fr auto;gap:8px 12px;align-items:start;font-size:13px}
.trow .tv{justify-self:end}
.trow .tbl{grid-column:1/-1;margin:2px 0 0;padding-left:18px;color:var(--muted);
           font-size:12px;line-height:1.5}
.trow .tbl li{margin:1px 0}
.picker{max-height:300px;overflow-y:auto;border:1px solid var(--surface-3);border-radius:8px;margin-bottom:12px}
.prow{display:grid;grid-template-columns:44px 1fr auto auto;gap:10px;align-items:center;
      width:100%;text-align:left;padding:7px 12px;background:none;border:0;
      border-bottom:1px solid var(--surface-3);cursor:pointer;font-size:12.5px;color:var(--ink)}
.prow:last-child{border-bottom:0}
.prow:hover{background:var(--surface-2)}
.prow.on{background:var(--surface-2);box-shadow:inset 3px 0 0 var(--brand)}
.prow .pid{font-weight:700;color:var(--brand)}
.prow .ptitle{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.prow .pmeta{color:var(--muted);font-size:11px;white-space:nowrap}
.tflow{margin:4px 0}
.tstep{display:grid;grid-template-columns:26px 1fr;gap:10px;padding:10px 0;
       border-bottom:1px solid var(--surface-3);font-size:13px;align-items:start}
.tstep:last-child{border-bottom:0}
.tstep .n{width:22px;height:22px;border-radius:50%;background:var(--surface-2);
          color:var(--brand);font-size:11px;font-weight:700;display:flex;
          align-items:center;justify-content:center}
.tstep code{display:inline-block;margin:3px 0}
.tstep .hint{display:block;margin-top:3px}
.note{background:var(--surface-2);border-left:3px solid var(--collectable);
      border-radius:0 6px 6px 0;padding:10px 14px;margin-top:14px;
      color:var(--ink-2);font-size:12.5px;line-height:1.55}
.pbox{margin:10px 0;border:1px solid var(--rule);border-radius:8px;padding:10px 14px;background:var(--surface)}
.pbox .ph{display:flex;justify-content:space-between;align-items:center;gap:12px}
.pbox .ph .pm{min-width:0}
.pbox .ph .pt{font-size:11px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--brand-ink)}
.pbox .ph .pd{display:block;color:var(--muted);font-size:12px;margin-top:2px;line-height:1.4}
.pbox .ph .pb{display:flex;gap:6px;align-items:center;white-space:nowrap}
.pbox pre{margin-top:10px}
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

.uc .why{background:var(--surface-2);border-left:3px solid var(--brand);border-radius:0 6px 6px 0;
         padding:9px 13px;margin:8px 0 4px;font-size:13px;line-height:1.55;color:var(--ink-2)}
.uc .k2{display:inline-block;min-width:112px;color:var(--muted);font-size:11px;
        text-transform:uppercase;letter-spacing:.04em}
.fwline{margin-top:8px;display:flex;flex-direction:column;gap:4px}
.fwline .tag{margin-right:3px}
.fwline .thin{color:var(--muted);font-size:12px;line-height:1.5;margin-top:4px}
.uc .tier{display:inline-block;font-size:10px;text-transform:uppercase;letter-spacing:.04em;
          color:var(--muted);border:1px solid var(--surface-3);border-radius:3px;padding:0 4px;margin-right:5px}
.chip.ph{background:var(--surface-2);color:var(--ink-2);border:1px solid var(--surface-3)}
.ucedit{margin-top:14px;padding-top:12px;border-top:1px solid var(--surface-3)}
.ucedit .hint{text-transform:none;letter-spacing:0;font-weight:400}
.efields{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:9px;margin:9px 0}
.efields label,label.wide{display:block;font-size:11px;text-transform:uppercase;
        letter-spacing:.04em;color:var(--muted)}
label.wide{margin-top:9px}
.efields input,.efields select,label.wide input,label.wide textarea{width:100%;margin-top:3px;
        padding:5px 7px;border:1px solid var(--surface-3);border-radius:5px;background:var(--surface);
        color:var(--ink);font:inherit;font-size:12.5px;text-transform:none;letter-spacing:0}
.lhead{display:flex;justify-content:space-between;align-items:center;padding:0 2px 8px;
       font-size:12.5px;color:var(--ink-2)}
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

/* beyond-ai tab ------------------------------------------------------------
   A parked idea, shown as-is inside an isolated frame. Nothing in here
   participates in the catalog, and nothing in the catalog depends on it. */
.parked{border:1px solid var(--rule);border-left:3px solid var(--road,#5A3B9C);
        background:var(--surface-2);border-radius:0 6px 6px 0;padding:12px 16px;margin:0 0 14px}
.parked .k{font-size:11px;letter-spacing:.09em;text-transform:uppercase;font-weight:700;
           color:var(--road,#5A3B9C);display:block;margin-bottom:5px}
.parked p{margin:0 0 6px;font-size:13px;color:var(--ink-2);line-height:1.55}
.parked p:last-child{margin-bottom:0}
.parked .open{font:inherit;font-size:12px;color:var(--brand);background:none;border:0;
              padding:0;cursor:pointer;text-decoration:underline}
.frameshell{border:1px solid var(--rule);border-radius:8px;overflow:hidden;
            background:var(--surface);box-shadow:0 1px 3px rgba(0,0,0,.06)}
.frameshell iframe{display:block;width:100%;height:1180px;border:0;background:#F8F7F4}
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
const session = { active: false, facilitator: "", recorded: "", changes: {}, newScenarios: [], importedScenarios: [], userPrompts: [], ucEdits: {}, newUseCases: [] };

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
  if (!Array.isArray(session.userPrompts)) session.userPrompts = [];
  if (!session.ucEdits || typeof session.ucEdits !== "object") session.ucEdits = {};
  if (!Array.isArray(session.newUseCases)) session.newUseCases = [];
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
        ${s.origin === "hypothesis" ? '<span class="chip modeler">Threat modeler</span>' : ""}
        ${s.needs_review ? '<span class="chip review">needs review</span>' : ""}</div>
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
      ${s.needs_review ? `<div class="reviewbox"><strong>Needs review before this record is used.</strong>
        <ul>${s.needs_review.map(r => `<li>${esc(r)}</li>`).join("")}</ul>
        An unresolved layer is left empty on purpose rather than guessed, because a guessed
        layer is indistinguishable from a real one once it is in the library.</div>` : ""}
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

/* ---------- bring in a scenario: research library, one conversion prompt, paste ---------- */
/* The prompts live here so they open right next to the paste box, no doc-hunting.
   This file is the source of truth for the live prompt text;
   docs/PROTOTYPE-SCENARIO-INTAKE.md describes the flow and points here. */
const P_CONVERT =
`You are mapping ONE finding into a Liszt scenario. Your input is EITHER a published
incident (something that has happened, with a source) OR an analyst hypothesis (an attack
nobody has run yet). Read the input, research it from the source if it names one, then
output a SINGLE JSON object and NOTHING else. No prose, no code fence, just JSON.

THE INPUT. Fill in exactly ONE of these two blocks and delete the other.

  PUBLISHED INCIDENT
  <<< paste the incident name and its source URL here >>>

  ANALYST HYPOTHESIS
  <<< write the attack you are worried about: what is the attacker trying to do, and
      what makes you think it could work against us? >>>

  If both blocks contain text, treat the input as a PUBLISHED INCIDENT and note the
  ambiguity in _check. If neither contains text, output nothing at all.

A hypothesis is sharpened, not judged: break it into concrete moves and name the signal
each move would produce, even though none has fired yet.

JSON shape, PUBLISHED INCIDENT form:
{
  "title": "short scenario title, attacker-goal phrasing",
  "one_liner": "2-3 plain sentences about OUR environment ('our', 'we'): what the attacker does and the damage.",
  "classification": {
    "ai_infrastructure_layer": "<<< one of the five, see LAYER RULE below >>>",
    "evidence": "seen-in-the-wild",
    "priority": "NOW, NEAR-TERM, or BACKLOG",
    "priority_rationale": ["3 short plain-sentence bullets, one of them about our own exposure"]
  },
  "attack_path": [
    { "step": 1, "layer": "<<< one seam tag from the list below >>>", "text": "one move of the attack, plainly" }
  ],
  "telemetry": [
    { "step": 1, "signal": "the observable event this move produces", "emitted_at": "where it is emitted from, named generically", "detection_opportunity": "what a detection could look for" }
  ],
  "framework_mapping": {
    "baseline": "2026.07",
    "attack": ["T1190"],
    "atlas": ["AML.T0049"],
    "owasp_llm": ["LLM06:2025"],
    "owasp_agentic": ["ASI10:2026"]
  },
  "incidents": [ { "title": "source title", "url": "source URL", "tier": 1 } ],
  "_check": {
    "layer_reason": "", "layer_runner_up": "", "steps_merged": "", "confidence": "",
    "check_1_layer_lands": "", "check_2_geometry": "", "check_3_fields": ""
  }
}

JSON shape, ANALYST HYPOTHESIS form: the SAME object with exactly these differences, and
no others.
  - Add two keys at the TOP LEVEL (siblings of "title", not inside "classification"):
        "origin": "hypothesis",
        "proposed_by": "AI Threat Modeler",
    "origin" must be exactly "hypothesis". "proposed_by" defaults to "AI Threat Modeler";
    only a named analyst may replace it with their own name. These two strings are how
    Liszt tags the record as threat-modeler work, so it can never be mistaken for a real
    incident.
  - Inside "classification", set  "evidence": "seen-in-research"  (edit it in place; there
    is only ever one evidence field, and it lives inside classification).
  - Remove the "incidents" key entirely. A hypothesis has no source incident.

WORKED EXAMPLE, incident form, shortened. A reference for format and granularity only; do
not copy its content into your answer.
{
  "title": "Poisoned document steers the RAG assistant",
  "one_liner": "An attacker mails us a crafted document. Our assistant ingests it, retrieval surfaces the planted passage, and answers follow the attacker's instruction.",
  "classification": {
    "ai_infrastructure_layer": "L1 · Data",
    "evidence": "seen-in-the-wild",
    "priority": "NOW",
    "priority_rationale": ["Our assistant ingests external mail unfiltered", "Poisoning persists across sessions until the store is cleaned", "Published incidents show this in real use"]
  },
  "attack_path": [
    { "step": 1, "layer": "Data / inbound", "text": "attacker emails a document carrying an embedded instruction to a monitored inbox" },
    { "step": 2, "layer": "Data / store", "text": "the pipeline embeds the document and writes the planted passage to the vector store" },
    { "step": 3, "layer": "Model / infer", "text": "retrieval surfaces the passage and the assistant's answer follows the instruction" }
  ],
  "telemetry": [
    { "step": 1, "signal": "external document accepted for ingestion", "emitted_at": "ingestion pipeline log", "detection_opportunity": "instruction-like content in inbound documents" },
    { "step": 2, "signal": "embedding write from an external source", "emitted_at": "vector store audit log", "detection_opportunity": "provenance tag on writes from unauthenticated senders" },
    { "step": 3, "signal": "answer citing the planted passage", "emitted_at": "inference gateway log", "detection_opportunity": "responses whose citations trace to recent external ingests" }
  ],
  "framework_mapping": { "baseline": "2026.07", "attack": ["T1566"], "atlas": [], "owasp_llm": ["LLM06:2025"], "owasp_agentic": [] },
  "incidents": [ { "title": "Vendor writeup of a RAG poisoning incident", "url": "https://example.com/writeup", "tier": 2 } ],
  "_check": {
    "layer_reason": "The corpus is the asset corrupted; the model behaves as designed on poisoned retrieval",
    "layer_runner_up": "L2 · Model",
    "steps_merged": "",
    "confidence": "high",
    "check_1_layer_lands": "pass, steps 1 and 2 land on L1",
    "check_2_geometry": "pass",
    "check_3_fields": "pass"
  }
}
Note what the example gets right: the chain was written first and the layer read off it;
a model appears in step 3 and the layer is still not L2, because the corrupted asset is
the corpus; the atlas list is empty rather than guessed; and every step names one move
with one observable.

Rules:
  - WORK IN THIS ORDER: understand the finding, write the attack_path, then choose
    ai_infrastructure_layer FROM the chain you wrote, then fill everything else. A layer
    chosen first anchors the chain to it; a chain written first is evidence.
  - ai_infrastructure_layer MUST be exactly ONE of the five strings below, copied from
    THIS list character for character. Do not re-type it from the LAYER RULE prose. The
    separator is "·" (U+00B7) with a space either side, not a hyphen and not a period.
      L0 · Infrastructure
      L1 · Data
      L2 · Model
      L3 · Orchestration & Agent
      L4 · Application
  - The framework_mapping values above are FORMAT EXAMPLES, not answers. Replace them with
    real identifiers, or use an empty list [] where you have none. Any value that is not a
    real identifier is discarded on import, so a placeholder is worse than an empty list.
    A hypothesis may map to no framework IDs yet; an empty list is a fine answer.
  - ONE STEP IS ONE ADVERSARY MOVE that produces its own distinct observable. Do not
    decompose a single request into the code path that handles it: a server parsing a
    config, calling a loader, and then checking authentication is one move, not three.
    The test: if two steps would be seen in the same log line, they are one step. Internal
    mechanism belongs in one_liner, not in the chain. A step in which the adversary does
    nothing is not a step; if a control fires late or fails, that is a telemetry row, not
    an attack step.
  - attack_path[].layer is a DIFFERENT field from ai_infrastructure_layer and it takes a
    DIFFERENT kind of value: a short seam tag, 18 characters maximum. Never put one of the
    five canonical strings here; they are too long and the row will be flagged. Use one of
    these, and only these:
      Data / inbound    Data -> Host      Data / store      Host / net
      Host / Cloud      Cluster / net     Model / infer     Model / Agent
      Model / store     Agent / tools     Agent / memory    Agent / eval
      App / net         App / session     Identity          Supply chain
      External
    Tag where the move OPERATES, not who performs it. Model / store is the model
    artifact at rest (weights on disk or in a bucket), as opposed to Model / infer,
    the live inference call.
  - One telemetry entry per attack_path step, sharing the same step number.
  - DO NOT include any coverage, visibility, detection, or score field. Owners score it
    later; you only identify the signal that WOULD exist. This does NOT mean stripping
    incidents[].tier or classification.priority, which are ordinary schema fields, not
    scores, and must stay.
  - Keep each attack_path step short enough to render on one line: len(text) + len(layer)
    + 7 (the "N  [layer]  " prefix the viewer adds) must be 125 characters or fewer.
    Keep telemetry text within its soft caps too, or the row wraps: signal 55, emitted_at
    60, detection_opportunity 95 characters.
  - 3 to 6 distinct steps. SIX IS A HARD CEILING enforced by the schema; a chain that needs
    more is two scenarios, so split it rather than fusing unlike moves to fit.
  - incidents[].tier grades the SOURCE, not the severity, and is filled only for a published
    incident. Use the number, not a word:
      1  first party. The affected organization's own disclosure, or a research team's
         own technical writeup of work they did themselves.
      2  reputable secondary technical reporting that adds detail: a vendor research team
         analyzing someone else's incident, a national CERT advisory.
      3  press, aggregators and summaries. Good for the fact that it happened, not for
         technical detail. If all you have is a press story, tier 3 is the honest answer.
  - Valid JSON only, one object, no trailing commas, no commentary. Every key except the
    leading-underscore "_check" is a scenario field; "_check" is read by the reviewer and
    dropped on import, so the rest promotes to a permanent record by copy and fill.

LAYER RULE. Read this before you fill in ai_infrastructure_layer. (Copy the exact string
from the five-item list under Rules, not from the names below.)

  What each layer means:
    L0  Infrastructure   compute, nodes, containers, the network, storage, the cloud
                         control plane, CI and build systems. The machinery AI runs ON.
    L1  Data             training sets, fine-tuning data, retrieval corpora, vector
                         stores, and the documents or content the system ingests.
    L2  Model            the model artifact and its weights, the inference call, the
                         system prompt, the guardrails, the decision the model makes.
    L3  Orchestration and Agent
                         agent loops, tool and function calling, planning, memory,
                         handoffs between agents, connector and MCP plumbing.
    L4  Application      the product surface: the user interface, the API the business
                         exposes, session and account handling, output rendering.

  Choose it with this test, in order. Stop at the first line that answers:
    1. At which layer does the attacker ACHIEVE THE OBJECTIVE? Not where they got in,
       and not who performed the move. Where the damage lands.
    2. If the objective spans layers, take the layer of the step that causes the harm.
    3. If it is still even, take the layer that owns the asset the attacker walked away
       with.

  These are all wrong, and each one is a defect we have actually seen:
    - Tagging L3 because an agent appears in the chain. An agent escalating privilege on
      a node is an L0 move. The agent is the ACTOR, the node is the LAYER.
    - Tagging L2 because a model appears in the chain. Nearly every scenario has one.
    - Tagging L0 because you are unsure. An unexplained L0 is the most common defect in
      this whole field. If you are unsure, pick your best answer and say why in _check.
    - Returning the list, returning two layers, or copying the placeholder text.

  Two tie-breakers we have had to make by hand:
    - Identity and account abuse: if the damage is takeover of the PRODUCT account, that
      is L4 (tag the step App / session). Identity as L0 is for the control-plane IAM of
      the infrastructure itself.
    - Model-weight theft is L2 by asset ownership (test 3) even though the bytes leave
      through cloud storage. Tag the exfil step Model / store (the model artifact at rest)
      so the L2 layer lands on the chain, rather than tagging it Host / Cloud and leaning
      on CHECK 1's exception.

SELF-CHECK. Before you emit, run these three tests on your own draft and FIX what fails,
then run them again. Emit only when all three pass. Put a short result of each ("pass", or
what you changed) into "_check".

  CHECK 1. THE LAYER LANDS ON THE CHAIN. Map each step's seam tag to its band:
      L0  Host / net, Host / Cloud, Cluster / net, Identity, Supply chain
      L1  Data / inbound, Data -> Host, Data / store
      L2  Model / infer, Model / Agent, Model / store
      L3  Agent / tools, Agent / memory, Agent / eval
      L4  App / net, App / session
      External belongs to no band and never counts as landing.
    One of these must be true, and you record which in _check.check_1_layer_lands:
      (a) at least one step's band equals the ai_infrastructure_layer you chose; or
      (b) no step lands there because the objective layer legitimately differs from every
          step's operating seam under LAYER RULE test 2 or 3 (a spanning objective, or the
          asset-ownership tie-break such as model-weight theft). Name the test that applies.
    If neither is true, one of three things is wrong and you must fix it, not paper over
    it: the layer is wrong, a step is mis-tagged, or the move that makes the layer true is
    missing. Do NOT relabel an honestly-External move to manufacture a landing. If every
    move is genuinely External, the finding is about a system we do not own; return it for
    re-scoping rather than forcing a layer.

  CHECK 2. THE STEPS ARE ONE MOVE EACH, AND FIT. Steps are numbered 1..N with no gaps and
    every count, length, and one-row-per-step rule above holds. Then check granularity in
    BOTH directions:
      - Over-split: if two steps would be seen in the same log line, or name the same
        emission point, they are one move. Merge them.
      - Under-decomposed: if one step's text names two adversary actions that a defender
        would see at two DIFFERENT sources, it is two steps. Split it. A single telemetry
        row that cannot account for everything its step describes is the tell. If splitting
        would exceed six steps, the finding is two scenarios, not one compressed chain.
    Record the outcome in _check.check_2_geometry.

  CHECK 3. THE FIELDS ARE RIGHT FOR THE KIND. Re-verify the layer-string, framework-ID and
    no-score rules above, character for character for the layer string. Then the branch
    fields:
      - Incident: classification.evidence == "seen-in-the-wild", and incidents is present
        with a real url and a tier of 1, 2, or 3.
      - Hypothesis: top-level origin == "hypothesis", top-level proposed_by is set,
        classification.evidence == "seen-in-research", and there is NO incidents key.
    The output is a single JSON object: no prose, no code fence, no trailing commas. Record
    the outcome in _check.check_3_fields.

Then fill the judgment half of "_check": layer_reason (one sentence, why that layer and not
the neighbor), layer_runner_up (the layer you nearly picked, or ""), steps_merged (if you
merged or split moves to stay within six, which ones, else ""), confidence (high, medium or
low). _check is not part of the record; the reviewer reads it and it is dropped on import.
`;

const P_INCIDENT =
`You are a threat-intelligence researcher building a list of PUBLISHED, real-world incidents that
involve AI INFRASTRUCTURE. Use web search and cite a source URL for every item.

Include incidents touching any of: model supply chain (tampered/backdoored models, malicious
models on public hubs, typosquatted model or package names); inference and serving (exploited
inference servers, model-load code execution, exposed model endpoints and AI gateways); data
(training-data or RAG poisoning, exposed vector stores); orchestration and agents (agent tool
abuse, prompt-injection with real impact, malicious MCP servers); MLOps (compromised pipelines,
leaked AI credentials); guardrail bypasses that caused a real incident.

Return a NUMBERED table with exactly these columns:
  # | Name | Date | Disclosed by | What happened, one sentence | Layer, provisional | Source URL | Tier | Why it matters
Example row:
  1 | Malicious models on a public hub | 2025-03 | JFrog | Backdoored models executed code on load in downstream pipelines | L2 | https://... | 1 | The model supply chain reaches every consumer

Rules:
  - The 12 most relevant items from the last 24 months, most recent and most severe first. If
    the window holds fewer than 12, widen it and say so. Relevance beats layer spread; use
    spread only to break ties between equally relevant items.
  - ONE ROW PER INCIDENT. If several sources cover the same incident, merge them into one row
    and cite the most first-party source.
  - Layer is PROVISIONAL, your quick read: L0 Infrastructure, L1 Data, L2 Model,
    L3 Orchestration and Agent, or L4 Application. The conversion prompt re-derives it with a
    stricter rule, so do not agonize over it.
  - Tier grades the SOURCE: 1 first party, 2 reputable press or research, 3 community.
  - Prefer confirmed incidents over demos, and label any notable demo "research, not in the
    wild"; no marketing; do not speculate; mark unknown details "unknown".

I will pick one row by its number and hand it to the conversion prompt.`;

const P_RESEARCH =
`You are a threat-intelligence researcher. Search these SPECIFIC sources for published incidents
and technical writeups about attacks on AI systems and AI infrastructure:
  - Wiz research (wiz.io/blog and their research team posts)
  - JFrog security research (jfrog.com, malicious-package and model findings)
  - Mandiant / Google Threat Intelligence (cloud.google.com/security, Mandiant blog)
  - The AI Incident Database (incidentdatabase.ai), a public community record of AI harms

Focus on AI infrastructure: malicious or backdoored models, poisoned hubs and packages, compromised
ML pipelines, exposed model endpoints and vector stores, agent and MCP tool abuse, prompt-injection
with real impact, leaked AI credentials.

Return a NUMBERED table with exactly these columns:
  # | Name | Date | Source and link | What happened, one sentence | Layer, provisional | Tier
Example row:
  1 | Exposed vector stores | 2025-06 | Wiz, https://... | Internet-exposed vector databases leaked the documents embedded in them | L1 | 1

Rules:
  - Only these four sources; if one has nothing relevant, say so and move on.
  - The 12 most relevant items from the last 24 months, most recent and most severe first. If
    the four sources yield fewer than 12 in the window, widen it and say so.
  - ONE ROW PER INCIDENT. If two sources cover the same incident, one row naming both, citing
    the more first-party link.
  - Layer is PROVISIONAL, your quick read: L0 Infrastructure, L1 Data, L2 Model,
    L3 Orchestration and Agent, or L4 Application. The conversion prompt re-derives it.
  - Tier grades the SOURCE: 1 first party, 2 reputable research, 3 community. Prefer confirmed
    incidents and concrete technical findings over opinion; mark unknown details "unknown".

I will pick one row by its number and hand it to the conversion prompt.`;

const P_HYP_RESEARCH =
`You are an AI threat modeler helping an analyst sharpen a worry into something concrete
enough to map. The analyst writes a hypothesis below: an attack on our AI infrastructure
that has NOT happened yet.

THE HYPOTHESIS:
<<< write the attack you are worried about: what is the attacker trying to do, and what
    makes you think it could work against us? >>>

Sharpen the idea, do not judge it, and do not write any JSON yet. Return:
  1. The attacker's objective in one sentence: what they walk away with, or what breaks.
  2. The chain of concrete moves, 3 to 6 of them, one line each. One move is one adversary
     action that produces its own distinct observable; internal mechanism is not a move.
  3. For each move, the observable signal a defender would look for, and where it would be
     emitted from, named generically.
  4. What is uncertain: which moves are speculative, and what would have to be true for
     them to work.
  5. Any published research or incident that comes close to this idea, with a link, or
     "none found".

Rules: stay concrete; prefer moves a defender could recognize in a log over abstractions;
it is honest to say nobody has run this yet. Do not soften a real concern and do not
inflate a weak one.

Then take the result to the conversion prompt, fill its ANALYST HYPOTHESIS block with it,
and it becomes scenario JSON.`;

const P_READINESS = String.raw`You are validating whether a mapped attack scenario is ready to be tested by an
emulation agent in a contained lab. You are not being asked whether the attack is
realistic. You are being asked whether each step is concrete enough to execute, safe
enough to execute, and reproducible in a lab.

For each step in attack_path, decide:

1. CONCRETE. Could a competent engineer read this step and know what action to take?
   A step that names a behavior ("reads the instance metadata service") is concrete.
   A step that names an outcome ("gains cluster-admin") is not, unless the mechanism
   is stated.
2. SAFE. Would executing this in a contained lab risk damage that cannot be undone by
   destroying the lab? Flag anything destructive, anything that touches a third party,
   and anything requiring a real credential.
3. REPRODUCIBLE. What would a lab need to contain for this step to be executable at
   all? List the components. If a step depends on a specific vulnerability or a
   specific vendor build, say so: that is usually the step that cannot be tested.
4. OBSERVABLE. The evidence row names a source. Could that source exist in a lab, or
   does it only exist in production? This decides whether the row's claim is testable
   in a lab or only where the real pipeline runs.

Then give an overall verdict.

Return ONLY valid JSON in this shape:

{
  "scenario": "NNN",
  "verdict": "ready" | "ready-with-exclusions" | "blocked",
  "blockers": [
    {"step": 1, "kind": "concrete|safe|reproducible|observable", "detail": "..."}
  ],
  "steps": [
    {
      "step": 1,
      "testable": true,
      "concrete": true,
      "safe": true,
      "lab_components": ["..."],
      "observable_in": "lab" | "pipeline-only" | "neither",
      "reason": "one line"
    }
  ],
  "notes": "anything a reviewer should know before this is approved"
}

Rules. Do not invent framework identifiers. Do not propose exploit code or payloads:
the spec deliberately carries none, and binds to a published emulation library at run
time by technique id. If a step cannot be tested, say so plainly rather than proposing
a weaker substitute test, because a substitute silently changes what the score means.

PASTE THE SCENARIO RECORD BELOW THIS LINE
`;

/* The judgment half of test DESIGN, as opposed to test readiness. The emitter writes the
   spec mechanically from the record; this is the part it cannot do, which is deciding how
   the chain should be broken up, what the environment has to be for a result to mean
   anything, and what a run would not settle. */
const P_TESTPLAN =
`You are designing a TEST PLAN for one Liszt scenario. You are not writing the test spec:
tools/emit_testspec.py emits that, mechanically, from the record. Your job is the judgment
the emitter cannot make: what is worth testing, how the chain should be broken up, what the
environment has to be for a result to mean anything, and what a run would not settle.

PASTE THE SCENARIO RECORD BELOW THE LINE AT THE FOOT OF THIS PROMPT.

Answer in Markdown. A person reads this and decides. Write the PIPELINE line first, then
the sections, then the JSON block, then the self-check.

FIRST LINE OF YOUR ANSWER, BEFORE ANYTHING ELSE

  PIPELINE: <mirrored | scratch | none> (stated in record | assumed scratch, not stated)

  State the pipeline mode as a fact about a lab that exists, not a mode you have chosen.
  The scenario record does not carry this field; it lives in the emitted spec. Unless the
  paste below explicitly states the lab's pipeline mode, you MUST write the plan for
  scratch, which is the emitter's default and the honest default for a first environment,
  and say so on that line. If a mirrored plan would be materially better, that belongs in
  section 7 as NEEDS ENVIRONMENT with what the mirror would have to carry. Never write a
  plan whose value depends on a mode you assumed into existence. Write this line before you
  decide what is worth testing, because it decides what any of it is worth.

THE EXIT CHECK, BEFORE YOU WRITE SECTION 3

  If section 2's verdict is blocked, or the record's classification.mode is "failure", or
  its classification.evidence is "doomsday", or its status is anything other than
  "published", then sections 3, 4 and 5 each consist of exactly one line:
      Not applicable: no run is recommended, see section 7.
  and nothing else. Section 7 then carries the whole answer, and the response is complete
  and correct at four sections. Do not design units for a chain you have just said should
  not run: a unit plan on the page is a unit plan somebody will schedule. A short blocked
  plan is a better artifact than a long one that has to be read carefully to discover it is
  blocked.

WHAT THE ENVIRONMENT DECIDES

  This is the most misread part of the method. Apply it before you recommend anything.

    - telemetry pipeline "mirrored": the lab carries the real detection pipeline. The
      coverage verdict on Have and Collectable rows can be scored, and so can the
      detection-fires claim. This is the only mode in which a Have row can be confirmed.
    - telemetry pipeline "scratch": a standalone lab with its own logging. Two claims are
      still scored on every executed row, and they are worth having: SIGNAL PRESENCE (did
      an artifact appear at all) and SOURCE ATTRIBUTION (did it appear in the system the
      row names). Those produce a real source-precision number, surprises, and proposed
      source corrections. What a scratch lab CANNOT do is confirm a Have or Collectable
      row's coverage claim, to any degree. Not partially, not indicatively, not
      "at the source level", not as early confidence. A scratch lab can falsify a Blind
      row. It cannot confirm a Have row.
    - telemetry pipeline "none": nothing is scoreable. Execution only.

  So do not write off a Have-heavy record as untestable in a cheap lab; say precisely which
  CLAIM goes untested, which is the detection half, and what the run still settles.

WHAT CAN ACTUALLY RUN TODAY

    - lab-only: designated ephemeral lab targets. THE ONLY RUNG ENABLED.
    - production-observe: benign signal generation against production to test the real
      detection pipeline, no state change, no adversary action. SWITCHED OFF, and its
      approval path is not yet defined.
    - production-active: bounded actions against production. SWITCHED OFF.
  The executor must refuse anything above the enabled rung even if a spec asks.

  And two things that gate even lab-only work: there is NO ADAPTER, so nothing binds a
  technique id to a runnable test yet, and there is NO LAB. Every plan is a reviewable
  design and a build target, not a schedule. Say so rather than letting a reader assume
  lab-only means next week.

STANDING CONSTRAINTS, TRUE AT EVERY RUNG

    - No payloads and no exploit code. Actions are abstract and engine agnostic:
      "reproduce this behavior using a published emulation of T1611". An adapter binds the
      technique id to a concrete test at run time.
    - No exploit development and no unpublished vulnerability research.
    - No persistence that survives teardown.
    - No credential use that resolves outside the lab boundary. That is a stop condition,
      not merely a safety concern.
    - Synthetic canaries only. No real data moves.
    - Targets are an explicit allowlist. No wildcard, no default, no category such as
      "the lab"; an empty allowlist correctly refuses to start.
    - Time box, deny-all egress unless a destination is named and justified, asserted
      teardown, and stop conditions. A triggered stop condition is a guardrail working.
    - A step marked control_held: true is one where the real chain stopped because a
      control held. A lab without that control tests a chain that did not happen; a lab
      with it tests the control, not the step. Say which of the two you mean. If the plan
      needs the control removed for the step to proceed, that is not a test of the step
      and it goes under OUT OF SCOPE. If the control stays and the step is expected to
      stop, say the expected result is a stop, and that a stop is the control working.
    - A telemetry row with kind: control is a verification or preventive signal, not a
      step. Its step number is display order and may run past the end of the chain. Control
      rows never appear in the section 2 table, in units, or in excluded steps.

WRITE THE PLAN IN THESE SEVEN SECTIONS

  1. WHAT THIS RUN WOULD SETTLE. Two or three sentences. Name the specific claims in this
     record worth falsifying, and the one you would most expect to be wrong. Name it and
     stop there. Do not say which direction it would move, do not name the tag or number it
     would move to, and do not characterize an existing score as optimistic, generous,
     high, low or unrealistic.
       In scope: "the Have claim on step 4 is the one I would most expect a run to break,
         because the evidence row's source has to carry pod identity for the claim to hold."
       Out of scope: "expect step 4 to drop to Collectable", "visibility 4 looks generous".
     Then state the honest ceiling: the best thing a run could establish at the pipeline
     mode on your first line, and what it will not touch.

  2. READINESS READ. The mechanical gate is computed elsewhere and is not your job. Judge
     the four things only a reader can judge. One row per attack_path step and no others.
       CONCRETE     could a competent engineer read this step and know what action to take?
                    A step naming a behavior is concrete; a step naming an outcome
                    ("gains cluster-admin") is not unless the mechanism is stated.
       SAFE         would running this in a contained lab risk damage that destroying the
                    lab does not undo? Name the specific hazard, never just yes or no.
       REPRODUCIBLE what must the lab contain for this step to run at all? Name the
                    requirement ONLY at the level of specificity the record itself states.
                    If the record names a product, name the product. If it names a version
                    or an advisory id, quote it. NEVER supply a version number, a version
                    boundary, a build id, an advisory or a CVE from your own knowledge, not
                    as an action, not as an environment requirement, not as an aside. A
                    document that says which builds are exploitable is a targeting document
                    whatever section it sits in, and your knowledge of version ranges is
                    stale by construction. If a step needs a specific vulnerable build and
                    the record does not say which, write "record does not name the build"
                    and list the step under NEEDS RECORD WORK.
       OBSERVABLE   the evidence row names a source. Could that source exist in a lab, or
                    only in production? Name the specific source, never just yes or no.
     End with a verdict: ready, ready-with-exclusions, or blocked. Blocked is a NORMAL
     outcome in a young library, not a failure. Sections 6 and 7 must reference the
     REPRODUCIBLE and OBSERVABLE cells here rather than restating them in new words.

  3. THE UNIT PLAN. Break the chain into the smallest units that still mean something. For
     each: the steps it covers, why they belong together, what must already be true, and
     what the unit proves on its own.
     Group by what a defender would see, not by what the attacker does. Two steps that land
     in the same log, or that cannot be told apart by their observable, are one unit.
     A step that only makes sense once an earlier step has established state is NOT
     independently testable. Say which state it needs, then choose exactly one of two and
     name which you chose:
       (a) fold it into the unit that PRODUCES that state, so the test produces the state; or
       (b) declare the step untested.
     You may not have the lab hand a step its precondition as a fixture and still count the
     step as covered: a fixture that supplies the state supplies the answer. Any
     precondition established by fixture rather than by an earlier unit MUST also appear in
     the excluded steps with the reason "state supplied by fixture, step not reproduced",
     and you must write one plain sentence saying what the downstream unit therefore cannot
     show. Before writing any precondition, check it against this record's hardening list:
     if the state you are about to grant is what a listed hardening item exists to prevent,
     granting it makes the unit silent about that control, and the unit text must say so.
     Say plainly which units can run in isolation and which cannot. That is what makes the
     plan usable under change control: an isolated unit fits a narrow window, a dependent
     one does not.

  4. THE FULL-PATH PLAN. Describe running the chain end to end as one exercise: the order,
     the state each step hands the next, the total blast radius. Then answer three
     questions honestly:
       - What does the full path tell you that the units do not? Usually whether the
         handoffs are observable, whether a control effective in isolation is bypassed in
         sequence, and whether the chain leaves a correlatable trail rather than scattered
         unrelated events. The units cannot answer that.
       - What does it cost? A longer window, a larger blast radius, harder attribution when
         something goes wrong, and a failure at step 2 wastes the whole run.
       - Under change management, when is it worth it? Be concrete about the tradeoff.
     Remember the shape this has to take: the agent reproduces the mapped behavior one step
     at a time and stops. It does not improvise and does not pursue an objective. "Full
     path" means every step of the mapped chain reproduced in order in one session, not an
     agent handed a goal. If you are recommending the latter, that is out of scope and you
     must say so.

  5. THE RECOMMENDATION. Pick one and defend it in a short paragraph: units first, full
     path, a named sequence of both, or, where the enabled rung genuinely cannot settle
     anything worth the window, no run today. Whatever you pick MUST be executable at
     lab-only, the only rung switched on. Blocked work is never the recommendation; it goes
     in section 7 in full, and section 5 says in one sentence what it would add if it were
     unblocked. State what has to be true for the recommendation to hold, and what would
     change it.

  6. ENVIRONMENT AND WHAT IT COSTS YOU. The pipeline mode from your first line, and in one
     line each what it makes scoreable and what it forfeits. The lab components: one
     execution target per unit, one observation component per named source in the evidence
     rows, plus any control rows worth corroborating. Describe a component by the ROLE it
     plays, never by the flaw that makes it usable. Name what each stands in for and what
     it deliberately does not reproduce.
     Close section 6 with four labeled lines a reader can carry into change control:
       TARGETS: the named lab systems this plan would put on the allowlist, or the words
         "cannot be derived from the record". Never "the lab", never a category, never a
         wildcard.
       TIME BOX: per unit and for the full path, with the reasoning in half a line.
       EGRESS: deny-all, or each destination named with why the run needs it.
       TEARDOWN AND STOP CONDITIONS: what specifically must be asserted destroyed, and when
         this particular plan should stop early.

  7. BLOCKED AND OUT OF SCOPE. A plain list. Everything you recommended that cannot run
     today, each with what it needs and who would have to decide. Labels:
       NEEDS RUNG PROMOTION   requires production-observe or production-active. State the
                              promotion block it would need: the rung it promotes from,
                              clean runs at the lower rung, the window, the
                              environment-fault count read aloud, the blast radius, whether
                              it is reversible, and the off switch. Do NOT name an approver,
                              a role, a team or a review body, and do not invent a review
                              cadence or an approval date. Write exactly: "Approver and
                              review loop: undefined. The approval path for this rung does
                              not exist yet; defining it is part of what this item asks for."
       NEEDS ENVIRONMENT      requires a mirrored pipeline, a lab component that does not
                              exist, a published emulation that may not exist, or the
                              adapter and the lab themselves, neither of which is built.
       NEEDS RECORD WORK      the scenario is not ready: unscored rows, draft status, a step
                              with no evidence row, a build the record does not name.
       OUT OF SCOPE           exploit development, unpublished vulnerability research,
                              anything needing real data or a real credential, anything
                              needing an agent to improvise toward an objective, and any
                              step that would require removing a control that held.
     A long list is the honest answer and it is useful. Do not shorten it by quietly
     downgrading a recommendation.

THEN THE JSON BLOCK, IN A FENCE

The prose is for the reader. This block is the decision record a person applies by hand.
Only "pipeline" corresponds to an emitter flag today (--pipeline); the rest is carried by a
human. Keep it minimal and do not restate the plan in it.

\`\`\`json
{
  "scenario": "NNN",
  "verdict": "ready | ready-with-exclusions | blocked",
  "run_recommended": true,
  "pipeline": "mirrored | scratch | none",
  "pipeline_stated": true,
  "pipeline_reason": "one line on what this mode can and cannot score for this record",
  "recommended": "none | units | full-path | units-then-full-path",
  "units": [ { "unit": 1, "steps": [1, 2], "independent": true, "needs": "what must already be true", "emulation_known": false } ],
  "excluded_steps": [ { "step": 4, "class": "unsafe | untestable-in-lab | third-party | not-scored | other", "reason": "one line" } ],
  "targets": ["named lab system, or the single string cannot-derive"],
  "time_box": { "per_unit": "ISO8601", "full_path": "ISO8601" },
  "egress": "deny-all | named destinations",
  "stop_conditions": ["one line each, specific to this plan"],
  "blocked": [ { "item": "what you recommended", "label": "NEEDS RUNG PROMOTION | NEEDS ENVIRONMENT | NEEDS RECORD WORK | OUT OF SCOPE", "needs": "what would unblock it" } ]
}
\`\`\`

If verdict is blocked, run_recommended MUST be false, recommended MUST be "none", and units
MUST be []. Never emit a unit list you have just argued should not be run: the prose is read
once by a person, the JSON is carried forward, and they must not disagree. excluded_steps may
contain every step; that is a legitimate answer. Copy "scenario" exactly as the record's id
reads; if the record has no id, or it is not three digits, do not supply one, write "MISSING"
and say so in section 7 as NEEDS RECORD WORK.

SELF-CHECK. Run these three on your own answer before you finish, fix what fails, and add
one line at the very end reading "Self-check: pass" or naming what you corrected.

  CHECK 1. THE JSON AGREES WITH THE PROSE. verdict matches section 2. recommended matches
    section 5. Every unit in section 3 appears in units and no others. Every item in section
    7 appears in blocked with the same label. If verdict is blocked, run_recommended is
    false, recommended is "none", units is [], and sections 3 to 5 are the one-line form.

  CHECK 2. NOTHING WAS INVENTED. No version number, build id, advisory or CVE that the
    record does not state. No approver, role, review body or approval date. No coverage tag
    or DeTT&CT number proposed for after the run. No pipeline mode assumed without saying so
    on the first line. No detection rule, saved search, index or product named inside a unit
    unless the pipeline is mirrored.

  CHECK 3. NOTHING WAS LAUNDERED. No unit is described as partially confirming, giving early
    confidence in, validating at the source level, sanity-checking, de-risking, or being a
    first step toward confirming a Have or Collectable claim. No step counted as covered
    whose precondition was supplied by a fixture. No weaker substitute proposed for a step
    that cannot be tested.

RULES FOR THE WHOLE ANSWER

  - Do not invent framework identifiers, and do not propose exploit code, payloads, or a
    specific vulnerability to weaponize. Bind by technique id and let the adapter resolve it.
    When you bind a unit to a technique id, say on the same line whether a published
    emulation is known to exist. If you do not know, write "emulation availability
    unverified"; do not treat the adapter as a guarantee. A unit whose technique has no
    published emulation is NEEDS ENVIRONMENT, not a ready unit. Never let it resolve to a
    neighboring technique that does have one: a near-neighbor emulation exercises a
    different behavior against the same evidence row and produces a confident number about
    the wrong thing.
  - Do not propose a weaker substitute when a step cannot be tested. Say it cannot be tested.
    A substitute silently changes what the score means, which is worse than a visible gap.
  - Do not guess or propose coverage, visibility, or detection scores. This includes
    restating, comparing, or reasoning forward from the DeTT&CT numbers already in the
    record, and includes coverage tags, which are derived from those numbers. Quote a row's
    existing tag only where you need it to say what a pipeline mode can score. Never propose
    the tag a row should have after the run. The run produces evidence; the owners rescore.
    Recommending a score in advance corrupts the calibration this method exists to produce.
  - Where an evidence row has no DeTT&CT block it has NO coverage determination. Do not infer
    one from the name of the source, from the presence of an evidence field, or from how
    mature the row sounds. Write "unscored" in the section 2 table, exclude the row from any
    statement about what the run can settle, and list it under NEEDS RECORD WORK. Unscored
    rows also fail the mechanical gate, so a plan that reads around them is planning a run
    that cannot be emitted at all. Say that plainly.
  - Before recommending any production rung anywhere, say in the same paragraph what can be
    run at lab-only today, even if the answer is "nothing worth the window".
  - Where the record is thin, say what is missing rather than filling it in.
  - Plain language. A reader who does not know DeTT&CT should still follow the plan.

PASTE THE SCENARIO RECORD BELOW THIS LINE
`;

/* The other thing a scenario is good for. The record says what evidence should exist;
   a use case says what gets done with it, which is the difference between coverage and
   a program that acts on what it sees. These two run in sequence: propose candidates,
   then stub the one that was picked. */
const P_USECASES =
`You are proposing OPERATIONAL USE CASES for one Liszt scenario. A scenario record says what
evidence should exist. A use case says what gets DONE with it: which signal starts a
decision, what other evidence is pulled in behind it, and what a person or system then does.

Coverage says we can see it. A use case says we do something intelligent with it. A program
can reach high coverage where every detection is a lone signal firing into a queue nobody
triages, and the coverage number looks fine the whole way down. Your job is to propose the
compositions that would stop that happening here.

PASTE THE SCENARIO RECORD BELOW THE LINE AT THE FOOT OF THIS PROMPT.

Return between FOUR and TEN candidates as a numbered Markdown list, then the short summary
block described at the end. These are for a person to read and choose from, not for a
machine to consume, so keep each one to the shape below and no longer.

THE SHAPE OF ONE CANDIDATE

  N. TITLE. Name the DECISION, not the tool. "Correlated prompt injection with data
     movement" is a decision. "Guardrail alerting" is a tool.

     When <the trigger signal> fires in <the exact source the row names>, pull
     <the other evidence> so that <what the receiver can now decide that they could not
     decide from the trigger alone>.

     Reads steps: <the attack_path step numbers whose evidence rows this actually uses>
     Buildable today: <yes, or what has to exist first>
     Cannot tell you: <the blind spot this specific composition has>

RULES THAT DECIDE WHETHER A CANDIDATE IS ANY GOOD

  - ONE TRIGGER EACH. If two different signals could each independently start it, that is
    two use cases, not one. Split them.
  - EVERY SIGNAL AND SOURCE MUST COME FROM A ROW IN THIS RECORD. Read the evidence table and
    quote the row's signal and its source. Do not invent a signal, do not invent a log
    source, and do not import a product name the record does not mention. If you find
    yourself naming a tool the record never names, you have left the record.
  - MATCH STEPS ROW BY ROW. The step numbers you list must be steps whose evidence rows this
    composition actually reads. Do not list the whole chain because the use case is "about"
    the scenario.
  - THE COMPOSITION IS THE POINT. A candidate whose only content is "alert on the trigger"
    is a lone signal, which is the failure this record type exists to make visible. Either
    name what else gets pulled and why, or say plainly that this one is a single signal and
    that a single signal is the honest answer here.
  - EACH PIECE OF PULLED EVIDENCE PLAYS ONE OF THREE ROLES, and you should be able to say
    which:
      enrichment     adds context to the thing that fired
      corroboration  independently supports or contradicts it
      scoping        answers how far it goes, how long it has been happening, what else is
                     affected
  - BUILDABLE TODAY. Look at the coverage tag on each row you read.
      A row tagged Have or Collectable has a source that exists, so the composition can be
      built from signals that are already there.
      A row tagged Blind has nothing producing it. A use case that reads a Blind row is a
      REQUEST TO BUILD COLLECTION FIRST, not a detection anyone can build this quarter. Say
      so in "Buildable today" and name what collection is missing.
    IMPORTANT CAVEAT you must apply: if a row has no DeTT&CT visibility and detection scores
    behind it, its coverage tag is an opinion, not a measurement. Where the rows you read are
    unscored, write "buildability unverified, the rows this reads are unscored" rather than
    asserting it is buildable. Do not treat an unscored tag as a fact.
  - COVER THE CHAIN, NOT JUST THE LOUDEST STEP. Across your four to ten candidates, try to
    read every step that has an evidence row. If some step is never worth reading, say which
    and why in the summary block.
  - DO NOT PROPOSE OR REVISE ANY SCORE. No coverage tag, no visibility number, no detection
    number, not for now and not for after the use case is built. Owners score rows; you are
    proposing work, not grading it.
  - NO NAMES. Never name a person, and do not invent a team, an owner, a queue, or an
    approver. Where a receiver is implied, describe them by the decision they make, for
    example "whoever decides if this is an incident", and leave naming to the engineer.
  - PLAIN LANGUAGE. A reader who does not know DeTT&CT should follow every line.

ORDER AND SPREAD

  Lead with the candidate that would change a decision most, not the one that is easiest to
  build. Then order the rest so that the ones buildable from existing signals come before the
  ones that need collection built first. If a candidate is only worth having once another one
  exists, say which.

THEN THE SUMMARY BLOCK, LAST

  COVERED STEPS: the step numbers at least one candidate reads.
  UNREAD STEPS: the step numbers no candidate reads, each with one line on why not.
  NEEDS COLLECTION FIRST: the candidate numbers that depend on a row nothing currently
    produces.
  SINGLE SIGNAL: the candidate numbers that are honestly one signal with nothing to compose.
  UNSCORED: whether the rows in this record carry DeTT&CT scores. If they do not, say in one
    line that every buildability judgment above is provisional for that reason.

SELF-CHECK, BEFORE YOU FINISH

  1. Every signal and every source in every candidate appears in this record's evidence
     table. Nothing was imported from your own knowledge of security products.
  2. Every candidate has exactly one trigger, and every step number listed is a step whose
     row that candidate actually reads.
  3. No score of any kind is proposed, and no person, team, owner or approver is named.
  4. Every candidate that reads a row with nothing producing it says so under
     "Buildable today".
  Add one final line reading "Self-check: pass" or naming what you corrected.

PASTE THE SCENARIO RECORD BELOW THIS LINE
`;

const P_UCRECORD =
`You are turning ONE chosen use-case candidate into a Liszt use-case record STUB, ready for
an engineer to finish. You are not finishing it. Several fields can only be filled by
somebody who knows the organization, and inventing them is the one way this goes wrong.

PASTE TWO THINGS BELOW THE LINE AT THE FOOT OF THIS PROMPT: the scenario record, and the
one candidate you picked from the use-case list.

Output YAML and nothing else. No prose, no code fence, no commentary.

WHAT YOU FILL, AND WHAT YOU MUST LEAVE FOR THE ENGINEER

  You fill these, because they are derivable from the scenario record:
    title, covers, trigger, composes, limits
  You leave these as a TODO line, because they are decisions about an organization you
  cannot see:
    id, pipeline.owner, pipeline.destination, outcome.consumer, provenance.authored_by
  Every field you leave MUST literally begin with "TODO:". That word is what the validator
  flags, so a stub that reaches the catalog half-finished announces itself. Never write
  PLACEHOLDER: the validator does not catch it and the record would pass while unfinished.

THE STUB

id: UC-000                        # TODO: assign the next free UC number, three digits
title: <name the DECISION this makes, not the tool. 8 to 90 characters>
status: proposed

covers:
  - scenario: "NNN"               # quoted, three digits, zero padded
    steps: [ ]                    # only steps whose evidence rows this use case reads

trigger:
  signal: <the one signal that starts this, quoted from the row. 8 to 80 characters>
  source: <that row's exact named source. 5 to 160 characters>

composes:
  - signal: <another row's signal>
    source: <that row's exact source>
    role: <enrichment | corroboration | scoping>

pipeline:
  strategy: <collect-centrally | instrument-at-source | evaluate-at-platform>
  destination: TODO: where the evidence has to land for this decision to be made
  owner: TODO: the role or team that builds and runs this, never a person

outcome:
  kind: <alert | report | trend | dashboard | enrichment | response>
  autonomy: notify
  consumer: TODO: the role or team that receives this, never a person
  action: <what the consumer actually does when it arrives. At least 20 characters>

limits: <what this use case cannot tell you, stated plainly. At least 30 characters>

provenance:
  authored_by: TODO: your name

RULES

  - EVERY signal and source must be quoted from an evidence row in the scenario record. Do
    not invent one, and do not name a security product the record does not name.
  - steps must be the attack path steps whose rows this use case actually reads, matched row
    by row, each between 1 and 6. Not the whole chain because the use case is about the
    scenario.
  - ONE trigger. It is a single object, never a list. If the candidate really has two
    independent starting signals, it is two use cases and you should stub the stronger one
    and say nothing about the other.
  - composes may be an empty list, written as [], and that is a real answer meaning the
    composition question was asked and this is honestly a single signal. It is not the same
    as leaving it out, and the key must always be present.
  - role is exactly one of enrichment, corroboration, scoping.
  - autonomy is ALWAYS notify in a stub. Raising it to assisted or autonomous requires a
    promotion block carrying a measured true positive rate, a window, a volume, a blast
    radius, a named approver, a review loop and an off switch. None of that exists yet, and
    a promotion block on a notify record passes the validator silently, which is exactly the
    kind of thing that gets found out later. So DO NOT emit a promotion block at all.
  - Do not add a slug field. The record has no such field and the schema rejects unknown
    keys, even though the file on disk is named UC-NNN-slug.yaml.
  - Do not include any coverage, visibility or detection score anywhere.
  - limits is required and it is not a formality. Name the blind spot this specific
    composition has: a step it does not read, an actor it cannot distinguish, a case where it
    would stay silent.

BEFORE YOU EMIT, CHECK

  1. Every signal and source appears in the pasted scenario record.
  2. Every field in the leave-for-the-engineer list begins with "TODO:", and the word
     PLACEHOLDER appears nowhere.
  3. trigger is one object, composes is a list with a role on every entry, autonomy is
     notify, and there is no promotion block.
  4. The YAML parses, and no key outside the shape above is present.

PASTE THE SCENARIO RECORD AND YOUR CHOSEN CANDIDATE BELOW THIS LINE
`;

/* The research prompt library. Each entry is one way of SOURCING a scenario; every one of
   them feeds the same single conversion prompt, P_CONVERT, which is what turns a finding
   into scenario JSON. Prompts added in the browser live in session.userPrompts and are
   session-only, like imports: promotion to the repo is a human act. */
const RESEARCH_PROMPTS = [
  { key: "incident", title: "Published incidents",
    asks: "Search the open web for published, real-world AI infrastructure incidents and return twelve candidates as a table.",
    body: P_INCIDENT },
  { key: "research", title: "Threat-research feeds",
    asks: "Search Wiz, JFrog, Mandiant and the AI Incident Database, and return twelve candidates as a table.",
    body: P_RESEARCH },
  { key: "hypothesis", title: "Analyst hypothesis",
    asks: "Sharpen a worry about our own environment into concrete moves and candidate signals, ready to convert. Arrives tagged Threat modeler.",
    body: P_HYP_RESEARCH }
];
function allResearchPrompts() {
  return RESEARCH_PROMPTS.concat((session.userPrompts || []).map((p, i) => ({
    key: "user-" + i, title: p.title, asks: p.asks || "", body: p.body, userIdx: i })));
}
/* Which pane of the intake section is open: library, convert, or paste. */
let intakeStep = "library";

/* The five layers, exactly as schema/scenario.schema.json enumerates them. The separator
   is U+00B7 with spaces. Everything that reaches a record has to be one of these strings. */
const AI_LAYERS = ["L0 · Infrastructure", "L1 · Data", "L2 · Model",
                   "L3 · Orchestration & Agent", "L4 · Application"];
const LAYER_COMPONENT = { L0:"Infrastructure", L1:"Data", L2:"Model", L3:"Agent", L4:"Application" };

/* Canonicalize whatever a model returned into one of the five, or return "" .

   Why "" rather than a default: guessing is what put this bug in the library. Every other
   controlled field here is validated and corrected; the layer was not, so a near miss
   ("L0 - Infrastructure" with a hyphen) or a first-option artifact rode straight into the
   record and then failed to match anything downstream. An unresolved layer is now unknown
   and visibly flagged, which is the same rule the coverage derivation already follows:
   unknown is not a value, and it is never quietly filled in. */
function resolveLayer(value) {
  const raw = String(value == null ? "" : value).trim();
  if (!raw) return "";
  /* An echoed instruction string lists several options; that is not a choice. */
  if ((raw.match(/L[0-4]/g) || []).length > 1) return "";
  for (const l of AI_LAYERS) if (raw === l) return l;
  const m = raw.match(/\bL\s*([0-4])\b/i);          /* "L3", "l3", "L 3", "L3 - anything" */
  if (m) return AI_LAYERS[Number(m[1])];
  /* Fall back to the name, so "Orchestration and Agent" or "Model" still resolve. */
  const norm = raw.toLowerCase().replace(/&/g, "and").replace(/[^a-z]+/g, "");
  for (let i = 0; i < AI_LAYERS.length; i++) {
    const nameOnly = AI_LAYERS[i].slice(5).toLowerCase().replace(/&/g, "and").replace(/[^a-z]+/g, "");
    if (norm === nameOnly) return AI_LAYERS[i];
  }
  return "";
}

/* attack_path[].layer is a SHORT free-text reading aid capped at 18 characters, not the
   controlled scenario-level field. Two of the five canonical strings are longer than the
   cap ("L0 · Infrastructure" is 19, "L3 · Orchestration & Agent" is 26), so a model that
   copies them into a step produces a record the validator rejects. Map them to the short
   form and flag it, because the good value is a seam tag like "Data → Host" that says
   where the move lands, and only a human can write that well. */
const STEP_LAYER_SHORT = { "L0": "Infrastructure", "L1": "Data", "L2": "Model",
                           "L3": "Agent", "L4": "Application" };
const STEP_LAYER_CAP = 18;

/* The seam tags the intake prompts offer. A model is free to invent one, and sometimes does,
   so anything outside this list is kept but flagged: the reviewer decides whether it is a
   real seam we should add or a slip we should correct. The component prefix is what the
   layer cross-check below reads, which is why the vocabulary is closed rather than free. */
const SEAM_TAGS = ["Data / inbound", "Data -> Host", "Data / store", "Host / net",
                   "Host / Cloud", "Cluster / net", "Model / infer", "Model / Agent",
                   "Model / store", "Agent / tools", "Agent / memory", "Agent / eval",
                   "App / net", "App / session", "Identity", "Supply chain", "External"];
/* Which of the five layers each seam tag belongs to, for the consistency check.
   Model / store is the model artifact at rest, weights on disk or in a bucket, as opposed
   to Model / infer, the live call. Without it, model-weight theft, an L2 objective by
   asset ownership, had no step tag that landed on L2 and always tripped the cross-check. */
const SEAM_LAYER = { "Data / inbound":"L1", "Data -> Host":"L1", "Data / store":"L1",
                     "Host / net":"L0", "Host / Cloud":"L0", "Cluster / net":"L0",
                     "Model / infer":"L2", "Model / Agent":"L2", "Model / store":"L2",
                     "Agent / tools":"L3", "Agent / memory":"L3", "Agent / eval":"L3",
                     "App / net":"L4", "App / session":"L4",
                     "Identity":"L0", "Supply chain":"L0", "External":"" };

function canonSeam(raw) {
  const k = String(raw || "").trim().replace(/→/g, "->").replace(/\s+/g, " ");
  for (const tag of SEAM_TAGS) if (tag.toLowerCase() === k.toLowerCase()) return tag;
  return "";
}

function shortenStepLayer(value) {
  const raw = String(value == null ? "" : value).trim();
  if (!raw) return { layer: "", note: "", seam: "" };
  const seam = canonSeam(raw);
  if (seam) return { layer: seam, note: "", seam: seam };
  /* A canonical layer string in this field is the confusion the two fields invite, so it is
     named as such whether or not it happens to fit inside the cap. */
  const asLayer = resolveLayer(raw);
  if (asLayer) return { layer: STEP_LAYER_SHORT[asLayer.slice(0, 2)],
    note: "step tag \"" + raw + "\" is a stack layer, not a seam. This field says where the "
        + "move lands, not which layer the scenario belongs to. Replace it with a seam tag "
        + "such as \"Data -> Host\".", seam: "" };
  if (raw.length <= STEP_LAYER_CAP) return { layer: raw, note:
    "\"" + raw + "\" is not one of the offered seam tags. Keep it if it names a real seam, "
    + "otherwise pick the closest from the list in the intake prompt.", seam: "" };
  const canon = resolveLayer(raw);
  if (canon) return { layer: STEP_LAYER_SHORT[canon.slice(0, 2)],
    note: "a canonical layer string was used as a step tag; shortened to fit the 18 character "
        + "cap. Replace it with a seam tag such as \"Data -> Host\" that says where the move lands",
    seam: "" };
  return { layer: raw.slice(0, STEP_LAYER_CAP).trim(),
           note: "truncated to 18 characters; rewrite it as a short seam tag", seam: "" };
}

/* Source tiers grade the sourcing, not the severity: 1 first party, 2 reputable secondary
   technical reporting, 3 press and aggregators. Models return these as words, as strings,
   or as the placeholder "1, 2, or 3", so everything is coerced and anything unreadable is
   surfaced rather than defaulted quietly. */
function normalizeTier(v) {
  const raw = String(v == null ? "" : v).trim().toLowerCase();
  if (!raw) return { tier: 0, note: "no source tier given" };
  const m = raw.match(/^[^0-9]*([123])(?![0-9])/);
  if (m && !/,|or\b/.test(raw)) return { tier: Number(m[1]), note: "" };
  if (/first[- ]?party|vendor own|own disclosure/.test(raw)) return { tier: 1, note: "" };
  if (/secondary|research|cert|advisory/.test(raw))          return { tier: 2, note: "" };
  if (/press|news|aggregat|summary|blog post/.test(raw))     return { tier: 3, note: "" };
  return { tier: 0, note: "source tier \"" + String(v).slice(0, 40) + "\" is not 1, 2 or 3" };
}

/* Framework IDs, shaped exactly as the schema defines them. A model handed a JSON skeleton
   will sometimes return the placeholder text as data, so anything that is not ID shaped is
   dropped rather than carried into the record. */
const FW_SHAPE = {
  attack:        /^T[0-9]{4}(\.[0-9]{3})?$/,
  attack_tactics:/^TA[0-9]{4}$/,
  atlas:         /^AML\.(TA[0-9]{4}|T[0-9]{4}(\.[0-9]{3})?|M[0-9]{4}|CS[0-9]{4})$/,
  owasp_llm:     /^LLM(0[1-9]|10):[0-9]{4}$/,
  owasp_agentic: /^ASI(0[1-9]|10):[0-9]{4}$/
};
function sanitizeFramework(fm) {
  const src = (fm && typeof fm === "object" && !Array.isArray(fm)) ? fm : {};
  const out = { baseline: DATA.baseline.id }, dropped = [];
  for (const key of Object.keys(FW_SHAPE)) {
    const arr = Array.isArray(src[key]) ? src[key] : [];
    const keep = [];
    for (const v of arr) {
      /* Identifiers are uppercase by convention in all four catalogs, so case is a typo
         to fix rather than a reason to discard a real id. */
      const id = String(v == null ? "" : v).trim().toUpperCase();
      if (!id) continue;
      if (FW_SHAPE[key].test(id)) { if (!keep.includes(id)) keep.push(id); }
      else dropped.push(key + ": " + id);
    }
    out[key] = keep;
  }
  /* The baseline is always ours. A model does not get to declare which pinned vocabulary
     the library speaks, and a record that names a baseline we do not hold is unverifiable. */
  return { mapping: out, dropped };
}

/* Take whatever the mapping prompt produced and make it safe to render: fill the
   fields the views read, force draft status, and never trust a coverage the file
   claims, because coverage is computed from scores captured with the owners. */
function normalizeImported(raw) {
  const s = (raw && typeof raw === "object") ? raw : {};
  const cls = s.classification || {};
  const layer = resolveLayer(cls.ai_infrastructure_layer);
  const fw = sanitizeFramework(s.framework_mapping);
  const rawSteps = Array.isArray(s.attack_path) ? s.attack_path : [];
  const stepLayers = rawSteps.slice(0, 6).map(a => shortenStepLayer(a && a.layer));
  const review = [];
  if (rawSteps.length > 6) review.push("attack_path: " + rawSteps.length +
    " steps supplied, and the schema caps a chain at 6. The extra step(s) were dropped; " +
    "merge the moves that belong together rather than losing the tail of the chain.");
  stepLayers.forEach((sl, i) => { if (sl.note)
    review.push("attack_path step " + (i + 1) + " layer: " + sl.note); });
  if (!layer) review.push("ai_infrastructure_layer: " +
    (cls.ai_infrastructure_layer ? "could not be matched to one of the five layers ("
      + String(cls.ai_infrastructure_layer).slice(0, 60) + ")" : "not supplied"));

  /* The layer is a claim about where the attack lands, and the chain is the evidence for
     that claim. When no step in the chain sits on the chosen layer, one of the two is wrong.
     This is the check that catches the failure we kept hitting: a chain that plainly runs on
     hosts, labeled L3 because an agent was the actor. It warns rather than corrects, because
     a legitimate answer exists in both directions and only a person can tell which. */
  if (layer) {
    const chainLayers = stepLayers.map(sl => SEAM_LAYER[sl.seam] || "").filter(Boolean);
    const chosen = layer.slice(0, 2);
    if (chainLayers.length && !chainLayers.includes(chosen)) {
      const seen = Array.from(new Set(chainLayers)).sort().join(", ");
      review.push("ai_infrastructure_layer: the record claims " + chosen + " but no step in "
        + "the chain lands there. The steps sit on " + seen + ". Either the layer is wrong, "
        + "or a step is mis-tagged, or the move that makes " + chosen + " true is missing "
        + "from the chain.");
    }
  }

  /* A model that has been handed a JSON skeleton will sometimes return the skeleton. */
  if (/<<<|>>>|one of the five|see LAYER RULE/i.test(String(cls.ai_infrastructure_layer || "")))
    review.push("ai_infrastructure_layer: the placeholder text came back as the answer, so no "
      + "layer was chosen. Re-run the prompt.");

  /* Whatever the model said about its own choice, put it in front of the reviewer. */
  const chk = (s._check && typeof s._check === "object") ? s._check : {};
  if (chk.layer_reason) review.push("the model's stated reason for the layer: \""
    + String(chk.layer_reason).slice(0, 200) + "\"");
  if (chk.layer_runner_up) review.push("the model nearly chose "
    + String(chk.layer_runner_up).slice(0, 40) + " instead. Worth a second look.");
  if (chk.steps_merged) review.push("moves merged to stay within six steps: "
    + String(chk.steps_merged).slice(0, 160));
  if (String(chk.confidence || "").toLowerCase() === "low")
    review.push("the model reported low confidence in this mapping.");
  if (fw.dropped.length) review.push("framework_mapping: dropped "
    + fw.dropped.length + " value(s) that are not valid identifiers (" + fw.dropped.join("; ").slice(0, 120) + ")");
  const out = {
    schema_version: 1, imported: true, status: "draft",
    origin: s.origin === "hypothesis" ? "hypothesis" : "incident",
    proposed_by: String(s.proposed_by || (s.origin === "hypothesis" ? "AI Threat Modeler" : "")).trim(),
    id: String(s.id || "").trim(),
    slug: String(s.slug || "").trim(),
    title: String(s.title || "").trim(),
    one_liner: String(s.one_liner || "").trim(),
    classification: {
      primary_layer_component: cls.primary_layer_component || LAYER_COMPONENT[layer.slice(0, 2)] || "",
      ai_infrastructure_layer: layer,
      evidence: EV[cls.evidence] ? cls.evidence
                : (s.origin === "hypothesis" ? "seen-in-research" : "seen-in-the-wild"),
      priority: ["NOW", "NEAR-TERM", "BACKLOG"].includes(cls.priority) ? cls.priority : "NEAR-TERM",
      priority_rationale: Array.isArray(cls.priority_rationale) ? cls.priority_rationale : []
    },
    framework_mapping: fw.mapping,
    attack_path: Array.isArray(s.attack_path) ? s.attack_path.slice(0, 6).map((a, i) => ({
      step: i + 1, layer: stepLayers[i].layer, text: a.text || "",
      attack: Array.isArray(a.attack) ? a.attack : [],
      atlas: Array.isArray(a.atlas) ? a.atlas : [] })) : [],
    telemetry: Array.isArray(s.telemetry) ? s.telemetry.map((t, i) => ({
      step: t.step || i + 1, signal: t.signal || "", emitted_at: t.emitted_at || "",
      source: t.source || "", detection_opportunity: t.detection_opportunity || "",
      owner: t.owner || "" })) : [],
    incidents: Array.isArray(s.incidents) ? s.incidents.map((inc, i) => {
      const src = (inc && typeof inc === "object") ? inc : {};
      const tn = normalizeTier(src.tier);
      if (tn.note) review.push("incidents[" + (i + 1) + "] " + tn.note
        + ". Tier grades the sourcing: 1 first party, 2 reputable secondary technical "
        + "reporting, 3 press or aggregator.");
      return { title: String(src.title || "").trim(), url: String(src.url || "").trim(),
               tier: tn.tier || 3 };
    }) : [],
    provenance: s.provenance || {}
  };
  if (!out.title) throw new Error("the scenario needs a title");
  if (!out.id || DATA.scenarios.some(x => x.id === out.id)) {
    let n = 1; while (DATA.scenarios.some(x => x.id === "IMP-" + n)) n++;
    out.id = "IMP-" + n;
  }
  if (!out.slug) out.slug = out.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  if (!out.one_liner) out.one_liner = out.title;
  if (review.length) out.needs_review = review;
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

/* A prompt renders as one summary line, name and what it asks, with the full text behind
   a Read toggle. Copy works without opening it; nobody has to scroll a wall of prompt to
   get on with the work. */
const openPrompts = {};
function promptBox(title, desc, body, copyKey, extra) {
  const open = !!openPrompts[copyKey];
  return `<div class="pbox">
    <div class="ph"><span class="pm"><span class="pt">${esc(title)}</span>
      <span class="pd">${esc(desc)}</span></span>
      <span class="pb">${extra || ""}
        <button class="copybtn" data-read="${esc(copyKey)}">${open ? "Hide" : "Read"}</button>
        <button class="copybtn" data-copy="${esc(copyKey)}">Copy prompt</button></span></div>
    ${open ? `<pre>${esc(body)}</pre>` : ""}</div>`;
}

function intakePanel() {
  const list = session.importedScenarios || [];
  const listHtml = list.length ? list.map((p, i) => `<div class="prop"><div>
      <div class="t">${esc(p.id)} &middot; ${esc(p.title)}</div>
      <div class="m">${p.origin === "hypothesis" ? "threat-modeler hypothesis" : "from incident"} &middot;
        ${esc(p.classification.ai_infrastructure_layer)} &middot;
        ${(p.attack_path || []).length} steps &middot; ${(p.telemetry || []).length} signals</div>
    </div><button data-dropimp="${i}">Remove</button></div>`).join("")
    : '<div style="color:var(--muted)">None yet.</div>';

  const rail = `<div class="irail">${[
      ["library", "1 &middot; Research library"],
      ["convert", "2 &middot; Convert to JSON"],
      ["paste",   "3 &middot; Paste and add"]]
    .map(([k, t]) => `<button class="ibtn" data-istep="${k}"
      aria-current="${intakeStep === k}">${t}</button>`).join("")}</div>`;

  let body;
  if (intakeStep === "library") {
    const prompts = allResearchPrompts().map(p => promptBox(p.title,
      p.asks || "Added this session.", p.body, p.key,
      p.userIdx === undefined ? "" :
        `<button class="copybtn" data-droppr="${p.userIdx}" style="color:var(--muted)">Remove</button> `))
      .join("");
    body = `<div class="sub" style="margin-bottom:6px">Pick a research prompt, run it in an
        LLM with web access, and choose the finding you want to bring in. Every prompt here
        feeds the same conversion prompt in step 2.</div>
      ${prompts}
      <div class="fld" style="margin-top:14px"><label>Add a research prompt</label>
        <input id="up-title" placeholder="short name, e.g. Vendor advisories"
          style="width:100%;box-sizing:border-box;margin-bottom:6px">
        <textarea id="up-body" rows="5" placeholder="the prompt text"
          style="width:100%;box-sizing:border-box;font-family:ui-monospace,Menlo,monospace;font-size:12px"></textarea>
        <span class="hint">Saved in this browser's session only, like imports. To make one
          permanent, it goes into the repo the same way a scenario does.</span></div>
      <div><button class="toggle" id="up-save">Save to the library</button></div>
      <div class="err" id="up-err" hidden></div>`;
  } else if (intakeStep === "convert") {
    body = `<div class="sub" style="margin-bottom:6px">One prompt converts any finding,
        published incident or analyst hypothesis, into scenario JSON. Fill in ONE input
        block, run it, and it checks its own output three ways before it emits.</div>
      <ol class="jsteps">
        <li>Copy the prompt and paste your chosen finding, or your sharpened hypothesis, into the matching input block.</li>
        <li>Run it in any LLM. It self-checks the layer, the step geometry, and the field discipline, then emits one JSON object.</li>
        <li>Take the JSON to step 3 and paste it.</li></ol>
      ${promptBox("Convert a finding to scenario JSON",
        "Turns one chosen finding, incident or hypothesis, into a single self-checked scenario JSON object.",
        P_CONVERT, "convert")}`;
  } else {
    body = `<div class="sub" style="margin-bottom:6px">Paste what the conversion prompt
        produced. It is checked again on the way in; anything questionable arrives flagged
        for review, and everything stays in this session until it is applied to the repo.</div>
      <div class="fld"><label>Paste the JSON the prompt produced</label>
        <textarea id="imp-json" rows="8" placeholder="paste the scenario JSON here"
          style="width:100%;box-sizing:border-box;font-family:ui-monospace,Menlo,monospace;font-size:12px"></textarea>
        <span class="hint">One scenario object, or an array of them. It needs at least a title;
          every other field fills in with a sensible default.</span></div>
      <div><button class="toggle" id="imp-add">Add to the library</button></div>
      <div class="err" id="imp-err" hidden></div>`;
  }
  return `<div class="panel"><h3>Bring in a scenario (${list.length} imported)</h3>
    ${listHtml}
    <div style="margin-top:14px">${rail}${body}</div></div>`;
}

function renderIntake() {
  $("#intake").innerHTML = intakePanel();
  wireIntake();
}

/* ---------- scenario testing: readiness, test design, run and rescore ---------- */
/* Testing is the other half of the loop the catalog exists for. The record claims what a
   defender would see; a run checks whether that claim is true, and the interesting answer
   is the one where it is not. Nothing here executes anything: the browser carries the
   judgment, the repo and the CLI carry the sealing and the scoring. */
let testStep = "readiness";
let ucSel = null;
let pickedScenario = null;

/* One picker, two sorts. What makes a scenario ready to TEST is the emitter's mechanical
   gate, which is a real measurement. There is no equivalent gate for designing a use case,
   and the obvious stand-in, how big the coverage gap looks, is built on sand: a row with no
   DeTT&CT scores behind it carries a coverage tag that the validator itself calls an opinion,
   and almost every row in a young library is in that state. So the use case sort orders by
   what can be known without scores, which is whether anything covers the scenario yet, how
   urgent it is, and how good the evidence for it is. */
const PRIORITY_RANK = { "NOW": 0, "NEAR-TERM": 1, "BACKLOG": 2 };
const EVIDENCE_RANK = { "seen-in-the-wild": 0, "seen-in-research": 1, "doomsday": 2 };

function pickerRows(mode) {
  const all = DATA.scenarios.slice();
  if (mode === "testing") {
    return all.sort((a, b) => (testable(b) - testable(a))
      || String(a.id).localeCompare(String(b.id)));
  }
  return all.sort((a, b) =>
       ((a.use_case_ids || []).length > 0) - ((b.use_case_ids || []).length > 0)
    || (PRIORITY_RANK[(a.classification || {}).priority] ?? 3)
     - (PRIORITY_RANK[(b.classification || {}).priority] ?? 3)
    || (EVIDENCE_RANK[(a.classification || {}).evidence] ?? 3)
     - (EVIDENCE_RANK[(b.classification || {}).evidence] ?? 3)
    || String(a.id).localeCompare(String(b.id)));
}

function scenarioPicker(mode) {
  const rows = pickerRows(mode).map(s => {
    const ucs = (s.use_case_ids || []).length;
    const tag = mode === "testing"
      ? (testable(s) ? `<span class="chip have">would emit</span>`
                     : `<span class="chip blind">blocked</span>`)
      : (ucs ? `<span class="chip have">${ucs} use case${ucs > 1 ? "s" : ""}</span>`
             : `<span class="chip blind">none yet</span>`);
    const meta = mode === "testing"
      ? esc(s.status)
      : `${esc((s.classification || {}).priority || "")} &middot; ${esc((s.classification || {}).evidence || "")}`;
    return `<button class="prow${pickedScenario === s.id ? " on" : ""}" data-pick="${esc(s.id)}">
      <span class="pid">${esc(s.id)}</span>
      <span class="ptitle">${esc(s.title)}</span>
      <span class="pmeta">${meta}</span>
      <span class="ptag">${tag}</span></button>`;
  }).join("");
  const why = mode === "testing"
    ? "Ready first. Ready means the emitter's mechanical gate passes, which is a measurement, not an opinion."
    : "Uncovered first, then by priority and evidence. Designing a use case does not need scores, so every record here is workable today.";
  return `<div class="sub" style="margin:2px 0 8px">${why}</div>
    <div class="picker">${rows}</div>`;
}

function pickedRecord() {
  return DATA.scenarios.find(s => s.id === pickedScenario) || null;
}

/* The record has to reach the prompt somehow, and the honest route is the clipboard: the
   page never had the YAML, only the projection of it, so it hands over what it does have
   and says so. */
function pickedBlock() {
  const s = pickedRecord();
  if (!s) return `<div class="note">Choose a scenario above to see what to paste under the prompt.</div>`;
  const unscored = (s.counts || {}).Unscored || 0;
  return `<div class="tsum"><strong>${esc(s.id)} ${esc(s.title)}</strong><br>
    ${esc((s.classification || {}).priority || "")} &middot;
    ${esc((s.classification || {}).evidence || "")} &middot;
    ${esc(s.status)} &middot; ${(s.attack_path || []).length} steps &middot;
    ${(s.telemetry || []).length} evidence rows
    ${unscored ? ` &middot; <strong>${unscored} unscored</strong>` : ""}
    ${(s.use_case_ids || []).length ? ` &middot; covered by ${s.use_case_ids.map(esc).join(", ")}` : ""}
    <br><button class="copybtn" data-copyrec="${esc(s.id)}">Copy the record</button>
    <span class="hint">Paste it under the prompt. This is the record as the page holds it;
      the file in scenarios/ is the authority.</span></div>`;
}

/* The mechanical gate, computed at build time by importing the emitter's own readiness()
   so the page and the emitter cannot drift. A record with no blockers is one the emitter
   would write a spec for today. */
function testable(s) { return !((s.testing && s.testing.blockers) || []).length; }

function readinessPane() {
  const all = DATA.scenarios.slice().sort((a, b) => String(a.id).localeCompare(String(b.id)));
  const ready = all.filter(testable);
  const rows = all.map(s => {
    const bl = (s.testing && s.testing.blockers) || [];
    return `<div class="trow ${bl.length ? "" : "ok"}">
      <div><a href="#/scenario/${esc(s.id)}">${esc(s.id)}</a> ${esc(s.title)}</div>
      <div class="tv">${bl.length
        ? `<span class="chip blind">blocked</span>`
        : `<span class="chip have">emitter would run</span>`}</div>
      ${bl.length ? `<ul class="tbl">${bl.map(b => `<li>${esc(b)}</li>`).join("")}</ul>` : ""}
    </div>`;
  }).join("");
  return `<div class="sub" style="margin-bottom:10px">The mechanical half of the readiness
      gate, run over the whole library. These are the same checks
      <code>tools/emit_testspec.py</code> recomputes before it writes a spec, so what you
      see here is what the emitter would do. A blocked record is a normal answer in a young
      library, and knowing which ones and why is itself a finding.</div>
    <div class="tsum"><strong>${ready.length} of ${all.length}</strong> scenarios would emit
      a spec today. ${ready.length ? "Ready: " + ready.map(s => esc(s.id)).join(", ") + "." : ""}</div>
    <div class="tlist">${rows}</div>
    <div class="note"><strong>Completing a blocked scenario.</strong> Almost every blocker
      above is one of two things, and both are ordinary work rather than a defect. A record
      still in draft has not been stood behind by anyone yet. A row with no DeTT&amp;CT
      visibility and detection scores carries a coverage tag the validator calls an opinion,
      so it predicts nothing and cannot be tested. To clear both: start session mode, open
      the scenario, score its rows on the two questions Liszt asks, export the session file,
      and apply it with <code>./liszt session</code>. Once the scores are in and the record
      is published, it appears here as ready and the other panes work on it. Designing use
      cases does not wait for any of that.</div>
    <div class="sub" style="margin:14px 0 4px">The judgment half is a person's call and does
      not come from the record. Run this against a scenario that clears the gate above.</div>
    ${promptBox("Readiness, the judgment half",
      "Judges per step whether it is concrete, safe, reproducible and observable enough for a lab run.",
      P_READINESS, "readiness")}`;
}

function designPane() {
  return `<div class="sub" style="margin-bottom:6px">The emitter writes the spec from the
      record mechanically. This is the judgment it cannot make: how the chain should be
      broken into test units, whether the full path is worth running as one exercise, what
      the environment has to be for the answer to mean anything, and what a run would not
      settle. It plans the work you cannot run today as well, and labels it.</div>
    ${scenarioPicker("testing")}
    ${pickedBlock()}
    <ol class="jsteps">
      <li>Copy the prompt and paste the scenario record underneath it.</li>
      <li>Run it in any LLM. It returns a plan in prose, then a small JSON block.</li>
      <li>Read the plan. The JSON carries the pipeline mode, the units, the steps to exclude and what is blocked.</li>
      <li>Take those decisions to the emitter in step 4.</li></ol>
    ${promptBox("Design a test plan",
      "Recommends unit-level and full-attack-path testing, the environment each needs, and what is blocked today.",
      P_TESTPLAN, "testplan")}
    <div class="note"><strong>What can actually run today.</strong> Only the
      <code>lab-only</code> rung is enabled; the executor refuses anything above it even if
      a spec asks. <code>production-observe</code>, the rung that would test the real
      detection pipeline without building a mirror, is specified and switched off, and its
      approval path is not yet defined. There is also no runner: the spec binds to an
      emulation library through an adapter that has not been written. So a plan is a
      reviewable design and a build target, not a schedule.</div>`;
}

function usecasePane() {
  return `<div class="sub" style="margin-bottom:6px">A scenario record says what evidence
      should exist. A use case says what gets DONE with it: which signal starts a decision,
      what else is pulled in behind it, and who acts. Coverage says we can see it; a use case
      says we do something intelligent with it. This does not need scores, so every record in
      the library is workable here today.</div>
    ${scenarioPicker("usecase")}
    ${pickedBlock()}
    <ol class="jsteps">
      <li>Copy the first prompt, paste the record underneath it, and run it. It returns four to ten candidates.</li>
      <li>Pick the one worth building. The candidates are written to be compared, not filed.</li>
      <li>Copy the second prompt, paste the record and your chosen candidate, and run it. It returns a record stub.</li>
      <li>Save the stub as use-cases/UC-NNN-your-slug.yaml, fill in every TODO, then run ./liszt validate.</li></ol>
    ${promptBox("Propose use cases",
      "Returns four to ten candidate compositions for one scenario, each with what it reads and what it cannot tell you.",
      P_USECASES, "usecases")}
    ${promptBox("Draft the use case record",
      "Turns one chosen candidate into a record stub, with every field it cannot know left as a TODO.",
      P_UCRECORD, "ucrecord")}
    <div class="note"><strong>The stub is deliberately unfinished.</strong> The id, the
      owner, the destination, the consumer and the author are decisions about your
      organization, so the prompt leaves each one as a TODO rather than inventing something
      plausible. The validator flags TODO, which is why the stub uses that word and not
      PLACEHOLDER: a record full of PLACEHOLDER passes validation while still being a draft.
      Autonomy is always <code>notify</code> in a stub, because anything higher needs a
      promotion block with a measured true positive rate and a named approver behind it.</div>`;
}

function rescorePane() {
  return `<div class="sub" style="margin-bottom:6px">This half lives in the repository, not
      in the browser, because it is sealed. The prediction is frozen before the run and the
      scorer refuses to score if it moved afterwards. Nothing writes itself back into a
      record.</div>
    <div class="tflow">
      <div class="tstep"><span class="n">1</span><div><strong>Emit the spec and the prediction.</strong>
        <code>python3 tools/emit_testspec.py NNN --sealed-by "your name"</code>
        <span class="hint">Writes <code>specs/ST-NNN-slug/</code>: <code>spec.yaml</code>, the
        engine-agnostic OpenSpec an adapter binds by technique id; <code>spec.md</code>, the same
        thing in the spec-driven agent convention; and <code>prediction.yaml</code>, the claim set.
        Add <code>--check</code> to run only the readiness gate and write nothing.</span></div></div>
      <div class="tstep"><span class="n">2</span><div><strong>Commit the prediction before the run.</strong>
        <span class="hint">A discrete, timestamped act, so git is the notary. A prediction revised
        after the answer is known is not a prediction.</span></div></div>
      <div class="tstep"><span class="n">3</span><div><strong>Run it, and record what you saw.</strong>
        <span class="hint">Author <code>runs/RUN-NNN-YYYY-MM-DD-NN.yaml</code> against
        <code>schema/run-record.schema.json</code>. Observations are written by whoever ran the
        test, from what was seen, <em>before</em> opening the prediction. The observer is not the
        agent.</span></div></div>
      <div class="tstep"><span class="n">4</span><div><strong>Score it.</strong>
        <code>python3 tools/score_run.py runs/RUN-NNN-....yaml</code>
        <span class="hint">Compares predicted against observed and reports four numbers: exact
        match rate, optimism index (positive means we believe we see more than we do, and it is the
        one that matters), source precision, and surprise count. It refuses to score if the
        prediction digest moved, and refuses claims the environment cannot test.</span></div></div>
      <div class="tstep"><span class="n">5</span><div><strong>Apply what it proposes, deliberately.</strong>
        <span class="hint">The scorer only proposes: a direction and a field per row, plus any new
        sources the run found. A person chooses the DeTT&amp;CT numbers, cites the run id as
        <code>backlog_ref</code> so the change is visible as a rescore rather than as improvement,
        and runs <code>./liszt validate</code> before committing.</span></div></div>
    </div>
    <div class="note"><strong>Where the loop is still open.</strong> Two ends are missing and
      it is better to know it. Nothing executes a test yet, so the two records in
      <code>runs/</code> are worked examples a person authored by hand. And the scorer's
      proposals name a direction, <em>Have</em> to <em>Collectable</em>, while records store
      DeTT&amp;CT integers, so applying one is still a hand translation. The source proposals
      are the exception: they are directly applicable today.</div>`;
}

function renderTesting() {
  const rail = `<div class="irail">${[
      ["readiness", "1 &middot; Readiness"],
      ["design",    "2 &middot; Design tests"],
      ["usecase",   "3 &middot; Design use cases"],
      ["rescore",   "4 &middot; Run and rescore"]]
    .map(([k, t]) => `<button class="ibtn" data-tstep="${k}"
      aria-current="${testStep === k}">${t}</button>`).join("")}</div>`;
  const body = testStep === "readiness" ? readinessPane()
             : testStep === "design" ? designPane()
             : testStep === "usecase" ? usecasePane() : rescorePane();
  $("#testing").innerHTML = `<div class="panel"><h3>Scenario management</h3>
    <div class="sub">What a scenario is for once it is in the library. Testing checks whether
      its evidence claims are true, and the useful answer is the one where they are not. Use
      cases turn those claims into something the organization acts on.</div>
    <div style="margin-top:14px">${rail}${body}</div></div>`;
  wireTesting();
}

function wireTesting() {
  $$("#testing .ibtn[data-tstep]").forEach(b => b.onclick = () => {
    testStep = b.dataset.tstep; renderTesting();
  });
  $$("#testing .prow[data-pick]").forEach(b => b.onclick = () => {
    pickedScenario = pickedScenario === b.dataset.pick ? null : b.dataset.pick;
    renderTesting();
  });
  $$("#testing .copybtn[data-copyrec]").forEach(b => b.onclick = () => {
    const s = pickedRecord();
    if (!s) return;
    const text = JSON.stringify(s, null, 2);
    const done = () => { const t = b.textContent; b.textContent = "Copied";
                         setTimeout(() => b.textContent = t, 1200); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(() => { b.textContent = "Press Cmd-C"; });
    } else { b.textContent = "Press Cmd-C"; }
  });
  const bodies = { readiness: P_READINESS, testplan: P_TESTPLAN,
                   usecases: P_USECASES, ucrecord: P_UCRECORD };
  $$("#testing .copybtn[data-read]").forEach(b => b.onclick = () => {
    openPrompts[b.dataset.read] = !openPrompts[b.dataset.read]; renderTesting();
  });
  $$("#testing .copybtn[data-copy]").forEach(b => b.onclick = () => {
    const text = bodies[b.dataset.copy];
    if (!text) return;
    const done = () => { const t = b.textContent; b.textContent = "Copied"; setTimeout(() => b.textContent = t, 1200); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(() => { b.textContent = "Press Cmd-C"; });
    } else { b.textContent = "Press Cmd-C"; }
  });
}

function wireIntake() {
  $$("#intake .ibtn[data-istep]").forEach(b => b.onclick = () => {
    intakeStep = b.dataset.istep; renderIntake();
  });
  const copyBodies = { convert: P_CONVERT, readiness: P_READINESS };
  allResearchPrompts().forEach(p => { copyBodies[p.key] = p.body; });
  $$("#intake .copybtn[data-read]").forEach(b => b.onclick = () => {
    openPrompts[b.dataset.read] = !openPrompts[b.dataset.read];
    renderIntake();
  });
  $$("#intake .copybtn[data-copy]").forEach(b => b.onclick = () => {
    const text = copyBodies[b.dataset.copy];
    if (!text) return;
    const done = () => { const t = b.textContent; b.textContent = "Copied"; setTimeout(() => b.textContent = t, 1200); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(() => { b.textContent = "Press Cmd-C"; });
    } else { b.textContent = "Press Cmd-C"; }
  });
  $$("#intake [data-droppr]").forEach(b => b.onclick = () => {
    session.userPrompts.splice(Number(b.dataset.droppr), 1);
    saveSession(); renderIntake();
  });
  $$("#intake .prop button[data-dropimp]").forEach(b => b.onclick = () => {
    dropImported(Number(b.dataset.dropimp));
    renderIntake(); renderList(); renderDetail(); updateSessionCount();
  });
  const save = $("#up-save");
  if (save) save.onclick = () => {
    const err = $("#up-err");
    const title = $("#up-title").value.trim(), promptBody = $("#up-body").value.trim();
    if (!title || !promptBody) {
      err.textContent = "A prompt needs a name and a body."; err.hidden = false; return;
    }
    session.userPrompts.push({ title: title, asks: "", body: promptBody });
    saveSession(); renderIntake();
  };
  const add = $("#imp-add");
  if (!add) return;
  add.onclick = () => {
    const err = $("#imp-err");
    let raw;
    try { raw = JSON.parse($("#imp-json").value); }
    catch (e) { err.textContent = "That is not valid JSON: " + e.message; err.hidden = false; return; }
    try {
      /* No origin fallback: the conversion prompt writes origin into a hypothesis record
         itself, and everything else is an incident. */
      (Array.isArray(raw) ? raw : [raw]).forEach(o => addImported(o));
      renderIntake(); renderList(); renderDetail(); updateSessionCount();
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
        priority: p.priority, one_liner: p.one_liner || "" })),
      imported_scenarios: session.importedScenarios || [],
      user_prompts: session.userPrompts || [],
      use_case_edits: session.ucEdits || {},
      new_use_cases: session.newUseCases || []
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
        session.userPrompts = Array.isArray(d.user_prompts) ? d.user_prompts : [];
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
    session.userPrompts = [];
    proposeOpen = false; intakeStep = "library"; saveSession();
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
function renderUseCases() { renderUCList(); renderUCDetail(); }

/* Every use case in the session's view of the world: the built-in records with any
   session edits laid over them, plus the ones proposed in the browser this session. */
function allUseCases() {
  const built = (DATA.use_cases || []).map(u => {
    const e = (session.ucEdits || {})[u.id];
    return e ? Object.assign({}, u, e, { _edited: true }) : u;
  });
  return built.concat((session.newUseCases || []).map(u => Object.assign({}, u, { _new: true })));
}

/* Why this use case exists, in framework terms, without storing anything twice. A use
   case names the scenario steps it reads; each of those steps may carry its own ATT&CK and
   ATLAS identifiers, and the scenario carries the OWASP mapping for the record as a whole.
   Walking covers[] into the scenarios is therefore the whole derivation, and it is narrower
   and more honest than copying the scenario's roll-up: it names only the techniques whose
   evidence rows this use case actually consumes. */
function deriveFrameworks(u) {
  const out = { attack: new Set(), atlas: new Set(), owasp_llm: new Set(),
                owasp_agentic: new Set(), scenarios: [], thin: [] };
  (u.covers || []).forEach(c => {
    const sc = DATA.scenarios.find(x => x.id === String(c.scenario));
    if (!sc) return;
    out.scenarios.push(sc);
    const fm = sc.framework_mapping || {};
    (fm.owasp_llm || []).forEach(i => out.owasp_llm.add(i));
    (fm.owasp_agentic || []).forEach(i => out.owasp_agentic.add(i));
    let any = false;
    (sc.attack_path || []).forEach(st => {
      if (!(c.steps || []).includes(st.step)) return;
      (st.attack || []).forEach(i => { out.attack.add(i); any = true; });
      (st.atlas || []).forEach(i => { out.atlas.add(i); any = true; });
    });
    if (!any) out.thin.push(sc.id);
  });
  ["attack", "atlas", "owasp_llm", "owasp_agentic"].forEach(k => { out[k] = [...out[k]].sort(); });
  return out;
}

const UC_PHASES = ["in-scoping", "pending-development", "in-development",
                   "in-testing", "in-production", "on-hold"];
const UC_STATUS = ["proposed", "built", "tuned", "retired"];
const UC_KINDS = ["alert", "report", "trend", "dashboard", "monitoring", "enrichment", "response"];

function renderUCList() {
  const ucs = allUseCases();
  const el = $("#uclist");
  if (!el) return;
  el.innerHTML = `<div class="lhead"><strong>${ucs.length}</strong> use case${ucs.length === 1 ? "" : "s"}
      <button class="toggle" id="uc-add">Add a use case</button></div>` +
    (ucs.length ? ucs.map(u => {
      const ph = (u.phase || {}).value;
      const cov = (u.covers || []).map(c => String(c.scenario)).join(", ");
      return `<button class="card" data-uc="${esc(u.id)}" aria-selected="${ucSel === u.id}">
        <div class="chips"><span class="chip ${esc(u.status)}">${esc(u.status)}</span>
          ${ph ? `<span class="chip ph">${esc(ph)}</span>` : ""}
          ${(u.outcome || {}).kind ? `<span class="tag">${esc(u.outcome.kind)}</span>` : ""}
          ${u._new ? '<span class="chip prop">this session</span>' : ""}
          ${u._edited ? '<span class="chip prop">edited</span>' : ""}</div>
        <div class="t"><span class="id">${esc(u.id)}</span> ${esc(u.title)}</div>
        <div class="meta">serves scenario${(u.covers || []).length === 1 ? "" : "s"} ${esc(cov)}</div>
      </button>`;
    }).join("")
      : `<div class="empty">No use case records yet.</div>`);
  $$("#uclist .card[data-uc]").forEach(b => b.onclick = () => selectUC(b.dataset.uc));
  const add = $("#uc-add");
  if (add) add.onclick = () => { ucSel = "__new__"; renderUCList(); renderUCDetail(); };
}

function ucRow(k, body) { return `<div class="ucrow"><div class="k">${k}</div><div>${body}</div></div>`; }

function renderUCDetail() {
  const el = $("#ucdetail");
  if (!el) return;
  if (ucSel === "__new__") { el.innerHTML = ucNewForm(); wireUCNew(); return; }
  const u = allUseCases().find(x => x.id === ucSel);
  if (!u) { el.innerHTML = '<div class="empty">Select a use case.</div>'; return; }

  const fw = deriveFrameworks(u);
  const chip = (arr, cls) => arr.map(i => `<span class="tag ${cls || ""}">${esc(i)}</span>`).join(" ");
  const scLink = (sid, steps) => {
    const sc = DATA.scenarios.find(x => x.id === sid);
    const label = `${esc(sid)}${sc ? " " + esc(sc.title) : ""} &middot; step${steps.length === 1 ? "" : "s"} ${steps.join(", ")}`;
    return sc ? `<a href="#/scenario/${esc(sid)}">${label}</a>`
              : `<span style="color:var(--muted)">${label} (not in this view)</span>`;
  };
  const ph = u.phase || {};
  const illustrative = (u.provenance || {}).illustrative;

  el.innerHTML = `
    <div class="uc sel">
      <div class="hdr"><span class="id">${esc(u.id)}</span>
        <span class="chip ${esc(u.status)}">${esc(u.status)}</span>
        ${ph.value ? `<span class="chip ph">${esc(ph.value)}</span>` : ""}
        <span class="chip ${esc((u.outcome || {}).autonomy || "")}"
          title="who acts: notify, an operator; assisted, automation prepares and an operator acts; autonomous, a bounded action runs first and is reviewed after">${esc((u.outcome || {}).autonomy || "")}</span>
        <span style="margin-left:auto"><button class="copybtn" id="uc-yaml">Copy YAML</button></span></div>
      <h4>${esc(u.title)}</h4>
      ${illustrative ? `<div class="note" style="margin:8px 0">Illustrative record. The
        content here was written for the prototype walkthrough and has not been assessed.</div>` : ""}

      ${u.rationale ? `<div class="why">${esc(u.rationale)}</div>` : ""}

      ${ucRow("Why it exists", `
        <div style="margin-bottom:6px">Serves ${(u.covers || []).length} scenario${(u.covers || []).length === 1 ? "" : "s"}:</div>
        ${(u.covers || []).map(c => `<div style="margin-bottom:3px">${scLink(String(c.scenario), c.steps || [])}</div>`).join("")}
        <div class="fwline">
          ${fw.attack.length ? `<div><span class="k2">ATT&amp;CK</span> ${chip(fw.attack)}</div>` : ""}
          ${fw.atlas.length ? `<div><span class="k2">ATLAS</span> ${chip(fw.atlas)}</div>` : ""}
          ${fw.owasp_llm.length ? `<div><span class="k2">OWASP LLM</span> ${chip(fw.owasp_llm)}</div>` : ""}
          ${fw.owasp_agentic.length ? `<div><span class="k2">OWASP Agentic</span> ${chip(fw.owasp_agentic)}</div>` : ""}
          ${(!fw.attack.length && !fw.atlas.length && !fw.owasp_llm.length && !fw.owasp_agentic.length)
            ? `<div style="color:var(--muted)">No framework identifiers reach this use case yet.</div>` : ""}
          ${fw.thin.length ? `<div class="thin">Scenario ${fw.thin.map(esc).join(", ")} carries no
            step-level ATT&amp;CK or ATLAS identifiers, so nothing can be derived from the steps
            this use case reads. The mapping above comes from the scenario as a whole where it
            exists at all. Filling in the step-level mapping is what would make this precise.</div>` : ""}
        </div>`)}

      ${ucRow("Trigger", `<strong>${esc((u.trigger || {}).signal || "")}</strong>
        <div class="src">${esc((u.trigger || {}).source || "")}</div>`)}

      ${ucRow("Composes", (u.composes || []).length
        ? (u.composes || []).map(cx => `<div style="margin-bottom:6px">
            <span class="role">${esc(cx.role)}</span> <strong>${esc(cx.signal)}</strong>
            <div class="src">${esc(cx.source)}</div></div>`).join("")
        : '<span style="color:var(--muted)">nothing; a single signal use case</span>')}

      ${ucRow("Delivery", `<span class="tag">${esc((u.pipeline || {}).strategy || "")}</span>
        &rarr; ${esc((u.pipeline || {}).destination || "")}`)}

      ${ucRow("Outcome", `<span class="tag">${esc((u.outcome || {}).kind || "")}</span>
        <div style="margin-top:4px">${esc((u.outcome || {}).action || "")}</div>`)}

      ${ucRow("Who", `
        <div><span class="k2">Builds and tunes</span> ${esc((u.pipeline || {}).owner || "not named")}</div>
        <div><span class="k2">Operates</span> ${esc(u.operates || "not named")}</div>
        <div><span class="k2">Receives</span> ${esc((u.outcome || {}).consumer || "not named")}</div>`)}

      ${(u.sources || []).length ? ucRow("Read more", (u.sources || []).map(sr => `
        <div style="margin-bottom:5px"><span class="tier">tier ${esc(sr.tier)}</span>
          <a href="${esc(sr.url)}" target="_blank" rel="noopener">${esc(sr.title || sr.url)}</a>
          ${sr.note ? `<div class="src">${esc(sr.note)}</div>` : ""}</div>`).join("")) : ""}

      ${ph.since || u.backlog_ref ? ucRow("Delivery state", `
        ${ph.value ? `<strong>${esc(ph.value)}</strong>` : ""}
        ${ph.since ? ` since ${esc(ph.since)}` : ""}
        ${u.backlog_ref ? `<div class="src">tracked as ${esc(u.backlog_ref)}</div>` : ""}`) : ""}

      <div class="limits"><span class="k">What it cannot tell you</span>${esc(u.limits || "")}</div>

      <div class="ucedit">
        <div class="k">Engineering fields <span class="hint">held in this session only; use Copy
          YAML to take them back to the record</span></div>
        <div class="efields">
          <label>Phase<select data-uce="phase">${UC_PHASES.map(v =>
            `<option value="${v}" ${ph.value === v ? "selected" : ""}>${v}</option>`).join("")}</select></label>
          <label>Since<input data-uce="since" type="date" value="${esc(ph.since || "")}"></label>
          <label>Status<select data-uce="status">${UC_STATUS.map(v =>
            `<option value="${v}" ${u.status === v ? "selected" : ""}>${v}</option>`).join("")}</select></label>
          <label>Outcome<select data-uce="kind">${UC_KINDS.map(v =>
            `<option value="${v}" ${(u.outcome || {}).kind === v ? "selected" : ""}>${v}</option>`).join("")}</select></label>
          <label>Operated by<input data-uce="operates" value="${esc(u.operates || "")}"></label>
          <label>Ticket<input data-uce="backlog_ref" value="${esc(u.backlog_ref || "")}"></label>
        </div>
        <label class="wide">Why this exists, in plain language
          <textarea data-uce="rationale" rows="3">${esc(u.rationale || "")}</textarea></label>
        ${(session.ucEdits || {})[u.id] ? `<button class="toggle" id="uc-revert">Discard my edits to this record</button>` : ""}
      </div>
    </div>`;
  wireUCDetail(u);
}

function selectUC(id) {
  ucSel = id;
  location.hash = `#/usecase/${id}`;
  renderUCList(); renderUCDetail();
}

/* Edits are held against the record id and never written through. The viewer has never
   written to use-cases/ and does not start here: the honest handoff is the YAML. */
function ucEdit(id, patch) {
  const cur = (session.ucEdits || {})[id] || {};
  session.ucEdits[id] = Object.assign({}, cur, patch);
  session.recorded = session.recorded || new Date().toISOString().slice(0, 10);
  saveSession();
}

function wireUCDetail(u) {
  $$("#ucdetail [data-uce]").forEach(inp => {
    inp.onchange = () => {
      const k = inp.dataset.uce, v = inp.value;
      const base = allUseCases().find(x => x.id === u.id) || {};
      if (k === "phase" || k === "since") {
        const ph = Object.assign({}, base.phase || {});
        if (k === "phase") ph.value = v; else ph.since = v;
        ucEdit(u.id, { phase: ph });
      } else if (k === "kind") {
        ucEdit(u.id, { outcome: Object.assign({}, base.outcome || {}, { kind: v }) });
      } else {
        ucEdit(u.id, { [k]: v });
      }
      renderUCList(); renderUCDetail();
    };
  });
  const rev = $("#uc-revert");
  if (rev) rev.onclick = () => { delete session.ucEdits[u.id]; saveSession(); renderUCList(); renderUCDetail(); };
  const cp = $("#uc-yaml");
  if (cp) cp.onclick = () => {
    const text = ucToYaml(allUseCases().find(x => x.id === u.id));
    const done = () => { cp.textContent = "Copied"; setTimeout(() => cp.textContent = "Copy YAML", 1200); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(() => { cp.textContent = "Press Cmd-C"; });
    } else { cp.textContent = "Press Cmd-C"; }
  };
}

/* A small YAML writer for one record. Deliberately not a general serializer: it knows the
   use-case shape, emits the keys in schema order, and quotes only what has to be quoted. */
function ucToYaml(u) {
  if (!u) return "";
  const q = v => {
    const s = String(v == null ? "" : v);
    return /^[A-Za-z0-9][A-Za-z0-9 ,.\/&:_()-]*$/.test(s) && !/: |  #/.test(s) ? s : JSON.stringify(s);
  };
  const L = [];
  L.push(`id: ${u.id}`);
  L.push(`title: ${q(u.title)}`);
  L.push(`status: ${u.status}`);
  if (u.phase && u.phase.value) {
    L.push("phase:"); L.push(`  value: ${u.phase.value}`);
    if (u.phase.since) L.push(`  since: ${u.phase.since}`);
  }
  L.push("covers:");
  (u.covers || []).forEach(c => {
    L.push(`  - scenario: "${c.scenario}"`);
    L.push(`    steps: [${(c.steps || []).join(", ")}]`);
  });
  if (u.rationale) L.push(`rationale: >-\n  ${String(u.rationale).replace(/\n+/g, " ").match(/.{1,88}(\s|$)/g).map(x => x.trim()).join("\n  ")}`);
  L.push("trigger:");
  L.push(`  signal: ${q((u.trigger || {}).signal)}`);
  L.push(`  source: ${q((u.trigger || {}).source)}`);
  L.push("composes:" + ((u.composes || []).length ? "" : " []"));
  (u.composes || []).forEach(c => {
    L.push(`  - signal: ${q(c.signal)}`);
    L.push(`    source: ${q(c.source)}`);
    L.push(`    role: ${c.role}`);
  });
  L.push("pipeline:");
  L.push(`  strategy: ${(u.pipeline || {}).strategy}`);
  L.push(`  destination: ${q((u.pipeline || {}).destination)}`);
  L.push(`  owner: ${q((u.pipeline || {}).owner)}`);
  L.push("outcome:");
  L.push(`  kind: ${(u.outcome || {}).kind}`);
  L.push(`  autonomy: ${(u.outcome || {}).autonomy || "notify"}`);
  L.push(`  consumer: ${q((u.outcome || {}).consumer)}`);
  L.push(`  action: ${q((u.outcome || {}).action)}`);
  if (u.operates) L.push(`operates: ${q(u.operates)}`);
  if (u.backlog_ref) L.push(`backlog_ref: ${q(u.backlog_ref)}`);
  if ((u.sources || []).length) {
    L.push("sources:");
    (u.sources || []).forEach(s => {
      L.push(`  - tier: "${s.tier}"`);
      L.push(`    url: ${s.url}`);
      if (s.title) L.push(`    title: ${q(s.title)}`);
      if (s.note) L.push(`    note: ${q(s.note)}`);
    });
  }
  L.push(`limits: ${q(u.limits)}`);
  if (u.notes) L.push(`notes: ${q(u.notes)}`);
  L.push("provenance:");
  const pv = u.provenance || {};
  L.push(`  authored_by: ${q(pv.authored_by || "")}`);
  if (pv.created) L.push(`  created: ${pv.created}`);
  L.push(`  last_updated: ${new Date().toISOString().slice(0, 10)}`);
  if (pv.illustrative) L.push("  illustrative: true");
  return L.join("\n") + "\n";
}

/* Proposing one in the browser. The engineering half only: the composition itself comes
   from reading the scenario, which is what the two prompts under Scenario management are
   for. This form captures the decision and hands back YAML. */
function ucNewForm() {
  const scOpts = DATA.scenarios.slice().sort((a, b) => String(a.id).localeCompare(String(b.id)))
    .map(s => `<option value="${esc(s.id)}">${esc(s.id)} ${esc(s.title)}</option>`).join("");
  return `<div class="uc sel"><div class="hdr"><span class="id">New</span></div>
    <h4>Propose a use case</h4>
    <div class="sub" style="margin-bottom:10px">Captured in this session and handed back as YAML.
      Nothing is written to <code>use-cases/</code> from the browser. For the composition itself,
      the two prompts under Scenario management read a scenario and propose candidates.</div>
    <div class="efields">
      <label class="wide">Title, name the decision not the tool<input id="nu-title"></label>
      <label>Scenario it serves<select id="nu-scenario">${scOpts}</select></label>
      <label>Steps it reads, comma separated<input id="nu-steps" placeholder="2, 3, 4"></label>
      <label>Phase<select id="nu-phase">${UC_PHASES.map(v => `<option>${v}</option>`).join("")}</select></label>
      <label>Outcome<select id="nu-kind">${UC_KINDS.map(v => `<option>${v}</option>`).join("")}</select></label>
      <label>Builds and tunes<input id="nu-owner" placeholder="role or team"></label>
      <label>Operated by<input id="nu-operates" placeholder="role or team"></label>
      <label>Receives<input id="nu-consumer" placeholder="role or team"></label>
      <label>Ticket<input id="nu-ticket" placeholder="optional"></label>
    </div>
    <label class="wide">Trigger signal<input id="nu-trigger"></label>
    <label class="wide">Trigger source, the exact named system<input id="nu-source"></label>
    <label class="wide">Why this exists, in plain language<textarea id="nu-why" rows="3"></textarea></label>
    <label class="wide">What it cannot tell you<textarea id="nu-limits" rows="2"></textarea></label>
    <div style="margin-top:10px"><button class="toggle" id="nu-save">Add to this session</button>
      <button class="toggle" id="nu-cancel">Cancel</button></div>
    <div class="err" id="nu-err" hidden></div></div>`;
}

function wireUCNew() {
  const cancel = $("#nu-cancel");
  if (cancel) cancel.onclick = () => { ucSel = null; renderUCList(); renderUCDetail(); };
  const save = $("#nu-save");
  if (!save) return;
  save.onclick = () => {
    const v = id => (($("#" + id) || {}).value || "").trim();
    const err = $("#nu-err");
    const steps = v("nu-steps").split(",").map(x => parseInt(x.trim(), 10)).filter(n => n >= 1 && n <= 6);
    if (!v("nu-title") || !steps.length || !v("nu-trigger") || !v("nu-source")) {
      err.textContent = "A title, at least one step, and a trigger with its source are the minimum.";
      err.hidden = false; return;
    }
    const used = allUseCases().map(u => parseInt(String(u.id).slice(3), 10)).filter(n => !isNaN(n));
    const next = "UC-" + String(Math.max(0, ...used) + 1).padStart(3, "0");
    session.newUseCases.push({
      id: next, title: v("nu-title"), status: "proposed",
      phase: { value: v("nu-phase"), since: new Date().toISOString().slice(0, 10) },
      covers: [{ scenario: v("nu-scenario"), steps: steps }],
      rationale: v("nu-why"),
      trigger: { signal: v("nu-trigger"), source: v("nu-source") },
      composes: [],
      pipeline: { strategy: "collect-centrally", destination: "to be decided", owner: v("nu-owner") || "not named" },
      outcome: { kind: v("nu-kind"), autonomy: "notify", consumer: v("nu-consumer") || "not named",
                 action: "To be written by the engineer who picks this up." },
      operates: v("nu-operates"), backlog_ref: v("nu-ticket"),
      limits: v("nu-limits") || "Not yet stated. Every use case has a blind side and this one has not been written down.",
      provenance: { authored_by: session.facilitator || "this session",
                    created: new Date().toISOString().slice(0, 10), illustrative: true }
    });
    saveSession();
    selectUC(next);
  };
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

/* ---------- beyond ai, a parked idea ----------
   A whole standalone mockup, shown as-is inside an isolated frame. It shares
   no styles, no script and no data with this page. Rendered once so that
   moving away from the tab and back does not reset where you were in it. */
let parkedDrawn = false;
function parkedHtml() {
  return new TextDecoder().decode(
    Uint8Array.from(atob(PARKED_B64), (c) => c.charCodeAt(0)));
}
function renderBeyond() {
  const el = $("#beyond");
  if (!el || parkedDrawn) return;
  parkedDrawn = true;
  el.innerHTML = `
    <div class="parked">
      <span class="k">Parked idea &middot; not part of the catalog</span>
      <p>Everything else in this viewer describes attacks on our AI stack. This tab asks a
         different question: what would it look like to propose a scenario against something
         that is not AI at all, a web application or a population of endpoints, and still land
         it in the same record shape.</p>
      <p>It is a design mockup and nothing more. No schema changed, no record changed, and
         no number anywhere else in this page comes from it. It is here so the idea can be
         looked at and discussed without anyone having to imagine it.</p>
      <p><button class="open" id="parkedopen">Open it full screen in a new tab</button></p>
    </div>
    <div class="frameshell">
      <iframe title="Beyond AI, proposing a scenario against a described environment"
              sandbox="allow-scripts allow-same-origin" srcdoc=""></iframe>
    </div>`;
  const src = parkedHtml();
  const fr = $("#beyond iframe");
  /* Grow the frame to whatever the mockup needs so there is no scrollbar
     inside a scrollbar. If the browser refuses us a look inside, the fixed
     height in the stylesheet stands and the frame scrolls on its own. */
  fr.addEventListener("load", () => {
    let doc = null;
    try { doc = fr.contentDocument; } catch (e) { return; }
    if (!doc || !doc.body) return;
    const fit = () => {
      const h = Math.max(doc.body.scrollHeight, doc.documentElement.scrollHeight);
      if (h > 200) fr.style.height = (h + 20) + "px";
    };
    fit();
    try { new ResizeObserver(fit).observe(doc.body); } catch (e) { /* older browser */ }
    doc.addEventListener("click", () => setTimeout(fit, 80), true);
  });
  fr.srcdoc = src;
  $("#parkedopen").onclick = () => {
    const url = URL.createObjectURL(new Blob([src], { type: "text/html" }));
    window.open(url, "_blank", "noopener");
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  };
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
  $("#intake").hidden = v !== "intake";
  $("#testing").hidden = v !== "testing";
  $("#sessionview").hidden = v !== "session";
  /* the parked tab is optional and carries its own chrome */
  const parked = $("#beyond");
  if (parked) {
    parked.hidden = v !== "beyond";
    $(".wrap > .tiles").hidden = v === "beyond";
    $(".filters").hidden = v === "beyond";
  }
  if (v === "beyond") renderBeyond();
  if (v === "coverage") renderCoverage();
  if (v === "usecases") renderUseCases();
  if (v === "frameworks") renderFrameworks();
  if (v === "reports") renderReports();
  if (v === "intake") {
    /* Imports ride on the session plumbing: they persist in the session and leave through
       the session export. Opening the intake turns session mode on so that is true from
       the first paste. */
    if (!session.active) {
      toggleSession(true);
      $("#sessiontoggle").textContent = "Leave session mode";
    }
    renderIntake();
  }
  if (v === "testing") renderTesting();
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
  if (u) {
    ucSel = u[1];
    if (state.view !== "usecases") setView("usecases");
    renderUCList(); renderUCDetail();
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

    # The parked mockup is optional. No file, no tab, and every other view is
    # byte for byte what it was.
    parked = parked_mockup_b64()
    parked_nav = ('<button data-view="beyond" aria-current="false">'
                  "New scenarios &middot; beyond AI</button>") if parked else ""
    parked_section = '<section id="beyond" hidden></section>' if parked else ""
    parked_js = f'<script>const PARKED_B64="{parked}";</script>' if parked else ""

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
    <button data-view="intake" aria-current="false">Bring in a scenario</button>
    <button data-view="testing" aria-current="false">Scenario management</button>
    {parked_nav}
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
  <section id="usecases" hidden><div class="split"><div class="list" id="uclist"></div><div class="detail" id="ucdetail"></div></div></section>
  <section id="frameworks" hidden></section>
  <section id="reports" hidden></section>
  <section id="intake" hidden></section>
  <section id="testing" hidden></section>
  {parked_section}
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
{parked_js}
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
