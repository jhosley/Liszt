#!/usr/bin/env python3
"""
Validate every record type against its schema AND the quality bar: scenarios, use cases,
incidents, framework baselines and per-org coverage overlays.

    python tools/validate.py                       # everything
    python tools/validate.py scenarios/021-*.yaml  # one record
    python tools/validate.py use-cases/UC-001*.yaml # one use case record
    python tools/validate.py incidents/*.yaml        # incident records
    python tools/validate.py coverage/acme/*.yaml    # one org's overlays
    python tools/validate.py --strict               # warnings become errors (use in CI)
    python tools/validate.py --publishable          # only check records with status: published

Two classes of finding:
  ERROR    the record is structurally wrong, or violates a rule that must hold
  WARN     the record is legal but falls short of the quality bar in docs/02

Publication gate: a record with status 'published' must have ZERO errors and
ZERO warnings. A draft may carry warnings, that is what draft means.

Exit codes: 0 clean, 1 errors present, 2 warnings present under --strict.
"""
from __future__ import annotations

import argparse
import collections
import glob
import pathlib
import re
import sys

try:
    import yaml
    from jsonschema import Draft202012Validator
except ImportError:
    sys.exit("pip install pyyaml jsonschema")

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "schema" / "scenario.schema.json"
UC_SCHEMA = ROOT / "schema" / "use-case.schema.json"
INC_SCHEMA = ROOT / "schema" / "incident.schema.json"
BASE_SCHEMA = ROOT / "schema" / "framework-baseline.schema.json"
OV_SCHEMA = ROOT / "schema" / "coverage-overlay.schema.json"

# Slide geometry limits, measured against the rendered template. Exceeding these
# does not corrupt the deck -- it produces text that overflows its shape, which is
# the single most common visual defect. Enforced here so it is caught before render.
LIMITS = {
    "telemetry.source": 160,
    "attack_path.text": 125,
    "telemetry.signal": 55,
    "telemetry.emitted_at": 60,
    "telemetry.detection_opportunity": 95,
    "priority_rationale": 130,
    "one_liner": 420,
    "scaled_up": 480,
    "commentary.already_see": 420,
    "commentary.blind": 420,
    "commentary.how_detect": 560,
}

BANNED = [
    (re.compile(r"\bunprecedented\b", re.I),
     "'unprecedented', only usable if a primary source says it, and then quote them"),
    (re.compile(r"\bTBD\b|\bTODO\b|\bXXX\b|\[insert", re.I),
     "placeholder text left in a field"),
    (re.compile(r"\bwe (?:think|believe|feel)\b", re.I),
     "hedging verb, state the claim or mark it as an inference"),
]


class Findings:
    def __init__(self):
        self.errors: list[tuple[str, str]] = []
        self.warns: list[tuple[str, str]] = []

    def err(self, where, msg):
        self.errors.append((where, msg))

    def warn(self, where, msg):
        self.warns.append((where, msg))


def derive_coverage(dettect: dict | None) -> str | None:
    """
    The ONE derivation rule for the Have/Collectable/Blind tag.

    Blind        no usable visibility                      visibility == 0
    Collectable  the source exists but nothing detects on it  visibility >= 1 and detection <= 0
    Have         a control emits it AND it is wired to detection
                                                            visibility >= 1 and detection >= 1

    Note detection == 0 means "logged for forensics/context only" in DeTT&CT, which is
    exactly Collectable, not Have. This distinction is the whole point of the tag.
    """
    if not dettect:
        return None
    vis, det = dettect.get("visibility"), dettect.get("detection")
    if vis is None or det is None:
        return None
    if vis == 0:
        return "Blind"
    return "Have" if det >= 1 else "Collectable"


def load_scenario_steps() -> dict[str, list[int]]:
    """
    Scenario id -> the attack path step numbers it actually has. Read from disk
    every run so a use case is always checked against the scenarios as they are,
    not as they were when the use case was written.
    """
    out: dict[str, list[int]] = {}
    for p in sorted((ROOT / "scenarios").glob("*.yaml")):
        if p.name.startswith("_"):
            continue
        try:
            rec = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue          # the unparseable file gets its own finding when validated
        if rec.get("id"):
            out[str(rec["id"])] = [s.get("step") for s in rec.get("attack_path", [])
                                   if isinstance(s, dict) and isinstance(s.get("step"), int)]
    return out


def load_use_case_covers() -> dict[str, set[int]]:
    """
    Scenario id -> the set of attack path steps that at least one use case covers.
    Built from every record in use-cases/, whatever subset is being validated, so
    the scenario-side check always sees the whole library.
    """
    covered: dict[str, set[int]] = {}
    for p in sorted((ROOT / "use-cases").glob("*.yaml")):
        if p.name.startswith("_"):
            continue
        try:
            rec = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        for c in rec.get("covers", []) or []:
            if isinstance(c, dict):
                covered.setdefault(str(c.get("scenario")), set()).update(
                    s for s in (c.get("steps") or []) if isinstance(s, int))
    return covered


def check_lengths(rec: dict, f: Findings) -> None:
    def over(field, value, cap):
        if isinstance(value, str) and len(value) > cap:
            f.err(field, f"{len(value)} chars, cap {cap}, will overflow the slide")

    over("one_liner", rec.get("one_liner", ""), LIMITS["one_liner"])
    over("scaled_up", rec.get("scaled_up", ""), LIMITS["scaled_up"])
    for k, v in (rec.get("commentary") or {}).items():
        over(f"commentary.{k}", v, LIMITS.get(f"commentary.{k}", 500))
    for i, r in enumerate(rec["classification"].get("priority_rationale", [])):
        over(f"priority_rationale[{i}]", r, LIMITS["priority_rationale"])
    for s in rec.get("attack_path", []):
        # the rendered line carries "N  [layer]  " ahead of the text
        rendered = len(s.get("text", "")) + len(s.get("layer", "")) + 7
        if rendered > LIMITS["attack_path.text"]:
            f.err(f"attack_path[{s.get('step')}]",
                  f"rendered line {rendered} chars incl. prefix, cap {LIMITS['attack_path.text']}")
    # Table cells auto-grow, so an overrun wraps to a second line rather than
    # spilling out of the shape. Untidy, not broken -> warning, not error.
    for r in rec.get("telemetry", []):
        for key in ("signal", "emitted_at", "detection_opportunity"):
            val, cap = r.get(key, ""), LIMITS[f"telemetry.{key}"]
            if len(val) > cap:
                f.warn(f"telemetry[{r.get('step')}].{key}",
                       f"{len(val)} chars over {cap}, the cell will wrap to two lines; "
                       "shorten it if you want the table to stay on one line per row")


def check_quality_bar(rec: dict, f: Findings, incidents: set[str],
                      uc_covered: dict[str, set[int]]) -> None:
    published = rec.get("status") == "published"
    steps = rec.get("attack_path", [])
    rows = rec.get("telemetry", [])
    prov = rec.get("provenance", {})

    # --- step / row alignment ------------------------------------------------
    step_nums = [s["step"] for s in steps]
    if step_nums != list(range(1, len(steps) + 1)):
        f.err("attack_path", f"steps must be 1.N with no gaps, got {step_nums}")

    attack_rows = [r for r in rows if r.get("kind", "attack-step") == "attack-step"]
    ctrl_rows = [r for r in rows if r.get("kind") == "control"]

    if len(attack_rows) != len(steps):
        f.warn("telemetry", f"{len(attack_rows)} attack-step rows for {len(steps)} steps")
    if ctrl_rows:
        nums = [r["step"] for r in ctrl_rows]
        if len(set(nums)) != len(nums) or any(n <= len(steps) for n in nums):
            f.warn("telemetry", f"control rows numbered {nums}, number them after the "
                                f"attack steps (from {len(steps) + 1}) so the slide reads in order")

    unknown = sorted({r["step"] for r in attack_rows} - set(step_nums))
    if unknown:
        f.err("telemetry", f"attack-step rows reference steps that do not exist: {unknown}. "
                           "If these are control or verification signals, set kind: control")
    missing = sorted(set(step_nums) - {r["step"] for r in attack_rows})
    if missing:
        f.err("telemetry", f"attack steps with no telemetry row: {missing}, every step must be "
                           "answered, even if the answer is Blind")

    # --- coverage derivation -------------------------------------------------
    for r in rows:
        d = derive_coverage(r.get("dettect"))
        if r.get("research_needed") and d is not None:
            f.warn(f"telemetry[{r['step']}]",
                   "scored but still flagged research_needed. The flag means the room could "
                   "not answer; a scored row has been answered, so clear the flag")
        if d is None:
            (f.err if published else f.warn)(
                f"telemetry[{r['step']}]",
                "no DeTT&CT visibility/detection scores, the coverage tag is an opinion until "
                "these exist, and the row cannot count toward maturity reporting")
        elif d != r.get("coverage"):
            f.err(f"telemetry[{r['step']}]",
                  f"coverage is '{r.get('coverage')}' but DeTT&CT scores derive '{d}' "
                  f"(visibility={r['dettect'].get('visibility')}, "
                  f"detection={r['dettect'].get('detection')})")

        if r.get("coverage") in ("Have", "Collectable") and not r.get("source"):
            (f.err if published else f.warn)(
                f"telemetry[{r['step']}]",
                f"'{r.get('coverage')}' with no source named. Record the exact system, log "
                "or index it comes from. A Have that cannot be pointed at is not verifiable, "
                "and a Collectable that cannot be pointed at cannot be wired up")

        if r.get("coverage") == "Have" and not r.get("evidence"):
            (f.err if published else f.warn)(
                f"telemetry[{r['step']}]",
                "'Have' with no evidence, a Have claim needs a query, rule ID or ticket behind it")

        if r.get("coverage") in ("Blind", "Collectable") and not r.get("owner"):
            (f.err if published else f.warn)(
                f"telemetry[{r['step']}]",
                f"'{r.get('coverage')}' with no owner, an unowned gap is an orphan and will "
                "never be closed")

        for dc in r.get("data_components", []):
            if dc.startswith("DS"):
                f.err(f"telemetry[{r['step']}]",
                      f"{dc} is an ATT&CK data SOURCE, retired in v18. Use a DCxxxx data component")

    # --- over-decomposition: several steps answered by one source ------------
    # A step is one adversary move that produces its own observable. When several
    # attack-step rows name the SAME source, the chain has usually been split into the
    # internal control flow of a single move, and one control then appears to cover
    # several steps. That inflates every coverage denominator the record feeds, which is
    # the "evidence reuse" and "splitting the denominator" pair in docs/04-measurement.md
    # section 7. It can be legitimate, so it warns rather than errors, but it should be
    # answered rather than ignored.
    by_source: dict[str, list[int]] = {}
    for r in rows:
        src = " ".join((r.get("source") or "").lower().split())
        if src:
            by_source.setdefault(src, []).append(r["step"])
    for src, steps_hit in by_source.items():
        if len(steps_hit) > 1:
            f.warn("telemetry",
                   f"steps {steps_hit} all name the same source. If those moves would be seen "
                   f"in the same log line they are one step, and splitting them makes one "
                   f"control look like coverage of {len(steps_hit)}. Merge them, or say in "
                   f"mapping_notes why the same source answers each separately "
                   f"(source: {(r.get('source') or src)[:60]})")

    # --- use case coverage ---------------------------------------------------
    # A row that claims detection maturity says something alerts. The use case
    # record is where that alert's customer and their action live. On a published
    # record, a detection with no use case is a claim with no receiver.
    if published:
        covered = uc_covered.get(str(rec.get("id")), set())
        for r in attack_rows:
            det = (r.get("dettect") or {}).get("detection")
            if det is not None and det >= 1 and r["step"] not in covered:
                f.warn(f"telemetry[{r['step']}]",
                       f"detection scored {det} but no use case in use-cases/ covers this step, "
                       "a detection claim should trace to a use case that says who receives it "
                       "and what they do")

    # --- framework mapping ---------------------------------------------------
    fm = rec.get("framework_mapping", {})
    if fm.get("mapping_confidence") == "editorial" and not fm.get("mapping_notes"):
        (f.err if published else f.warn)(
            "framework_mapping",
            "editorial mapping with no mapping_notes, an editorial mapping must state its "
            "reasoning and name anything a reasonable analyst would dispute")
    failure_mode = rec["classification"].get("mode") == "failure"
    if not any(fm.get(k) for k in ("attack", "atlas", "owasp_llm", "owasp_agentic")):
        if failure_mode:
            f.warn("framework_mapping",
                   "no framework IDs, expected for a failure scenario, but say so in "
                   "mapping_notes so a reader knows it is deliberate")
        else:
            (f.err if published else f.warn)("framework_mapping", "no framework IDs at all")

    agentic = not failure_mode and (
        rec["classification"].get("ai_infrastructure_layer", "").startswith("L3")
        or rec["classification"].get("primary_layer_component") == "Agent")
    if agentic and not fm.get("owasp_agentic"):
        f.warn("framework_mapping",
               "agent-layer scenario with no OWASP Agentic (ASI) mapping, agentic scenarios "
               "usually carry both an LLM and an ASI ID")

    # --- R1: step-level and roll-up mappings must agree -----------------------
    # Roll-up is the union of the step mappings. A technique that appears in a step
    # but not the roll-up is invisible to coverage queries; one in the roll-up but no
    # step cannot be traced to anything that happened.
    for key in ("attack", "atlas"):
        step_ids = {i for s in steps for i in s.get(key, [])}
        roll_ids = set(fm.get(key, []))
        orphan_step = sorted(step_ids - roll_ids)
        orphan_roll = sorted(roll_ids - step_ids)
        if orphan_step:
            f.warn(f"framework_mapping.{key}",
                   f"mapped on a step but missing from the roll-up: {orphan_step}")
        if orphan_roll and step_ids:
            f.warn(f"framework_mapping.{key}",
                   f"in the roll-up but on no step: {orphan_roll}, every roll-up ID should "
                   "trace to a step, or the mapping cannot be defended")

    # --- provenance and review ----------------------------------------------
    if published:
        if not prov.get("reviewed_by"):
            f.err("provenance.reviewed_by", "published without a reviewer")
        elif prov.get("reviewed_by") == prov.get("authored_by"):
            f.err("provenance.reviewed_by", "reviewer is the author, review must be independent")
        if not prov.get("sources"):
            f.err("provenance.sources", "published with no sources")
        elif rec["classification"]["evidence"] != "doomsday" and \
                not any(s.get("tier") == "0" for s in prov["sources"]):
            f.warn("provenance.sources",
                   "no Tier 0 primary source, allowed only when the scenario is genuinely "
                   "hypothetical")

    # --- evidence tier consistency ------------------------------------------
    ev = rec["classification"]["evidence"]
    if ev == "doomsday" and rec["classification"]["priority"] == "NOW":
        f.warn("classification", "doomsday scenario marked NOW, a never-observed scenario is "
                                 "rarely this cycle's instrumentation priority")
    if ev != "doomsday" and not failure_mode and not rec.get("incidents"):
        f.warn("incidents", f"evidence is '{ev}' but no incident is referenced, what is the claim "
                            "grounded in?")
    for slug in rec.get("incidents", []):
        if incidents and slug not in incidents:
            # A draft may reference an incident whose record has not been written yet.
            # A published record may not -- that is a dangling citation.
            (f.err if published else f.warn)(
                "incidents", f"'{slug}' has no record in incidents/")

    # --- hardening -----------------------------------------------------------
    for i, h in enumerate(rec.get("hardening", [])):
        bad = [s for s in h.get("breaks_step", []) if s not in step_nums]
        if bad:
            f.err(f"hardening[{i}]", f"breaks_step references non-existent steps {bad}")
    if published and not rec.get("hardening"):
        f.warn("hardening", "no hardening items, a scenario with no proposed remediation cannot "
                            "feed a backlog, which is the point of the exercise")

    # --- language ------------------------------------------------------------
    blob = yaml.safe_dump(rec, allow_unicode=True)
    for pattern, why in BANNED:
        if pattern.search(blob):
            f.warn("language", why)

    if rec.get("scaled_up") and re.search(r"\b(did|was observed|has happened)\b",
                                          rec["scaled_up"], re.I):
        f.warn("scaled_up", "reads as observed fact, this box is always hypothetical")


def validate_file(path: pathlib.Path, validator, incidents: set[str],
                  uc_covered: dict[str, set[int]]) -> Findings:
    f = Findings()
    try:
        rec = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        f.err("yaml", f"unparseable: {e}")
        return f
    if not isinstance(rec, dict):
        f.err("yaml", "top level is not a mapping")
        return f

    for e in sorted(validator.iter_errors(rec), key=lambda e: list(e.path)):
        f.err("/".join(str(p) for p in e.path) or "(root)", e.message)
    if f.errors:
        return f              # structural errors make the rest unreliable

    if path.stem != f"{rec['id']}-{rec['slug']}":
        f.err("filename", f"should be {rec['id']}-{rec['slug']}.yaml")

    check_lengths(rec, f)
    check_quality_bar(rec, f, incidents, uc_covered)
    return f


def validate_use_case_file(path: pathlib.Path, validator,
                           scenario_steps: dict[str, list[int]]) -> Findings:
    f = Findings()
    try:
        rec = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        f.err("yaml", f"unparseable: {e}")
        return f
    if not isinstance(rec, dict):
        f.err("yaml", "top level is not a mapping")
        return f

    for e in sorted(validator.iter_errors(rec), key=lambda e: list(e.path)):
        f.err("/".join(str(p) for p in e.path) or "(root)", e.message)
    if f.errors:
        return f              # structural errors make the rest unreliable

    # --- covers must point at real scenarios and real steps ------------------
    # This is the join to the scenario library. A dangling reference here is a
    # use case serving a behavior nobody recorded, which cannot be reviewed.
    for i, c in enumerate(rec.get("covers", [])):
        sid = str(c.get("scenario"))
        if sid not in scenario_steps:
            f.err(f"covers[{i}]", f"scenario '{sid}' does not exist in scenarios/")
            continue
        steps = scenario_steps[sid]
        bad = sorted(s for s in c.get("steps", []) if s not in steps)
        if bad:
            f.err(f"covers[{i}]",
                  f"steps {bad} are not in scenario {sid}'s attack path, which has "
                  f"steps {steps}. A covered step must be one the scenario records")

    # --- autonomy above notify must carry its authorization ------------------
    # Autonomy is earned, not declared. The promotion block is the evidence and
    # the approval; without it, an assisted or autonomous setting is a claim
    # with nothing behind it.
    autonomy = (rec.get("outcome") or {}).get("autonomy")
    promo = rec.get("promotion")
    if autonomy in ("assisted", "autonomous") and not promo:
        f.err("promotion",
              f"outcome.autonomy is '{autonomy}' with no promotion block, autonomy above "
              "notify has to be demonstrated with evidence collected at a lower level, "
              "and the promotion block is that demonstration")
    if autonomy in ("assisted", "autonomous") and promo:
        vol = (promo.get("evidence") or {}).get("volume")
        if isinstance(vol, int) and vol < 1:
            f.err("promotion.evidence",
                  f"volume is {vol}, a promotion needs at least one observed fire behind "
                  "its rate, or the rate is a projection, not evidence")

    # --- language ------------------------------------------------------------
    blob = yaml.safe_dump(rec, allow_unicode=True)
    for pattern, why in BANNED:
        if pattern.search(blob):
            f.warn("language", why)
    return f


def _stringify_dates(obj):
    """YAML turns an unquoted 2026-07-30 into a date object. The schemas want strings,
    and the records are allowed to leave dates unquoted, so normalize before checking."""
    import datetime
    if isinstance(obj, dict):
        return {k: _stringify_dates(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_stringify_dates(v) for v in obj]
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    return obj


def _load(path: pathlib.Path, f: Findings) -> dict | None:
    try:
        rec = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        f.err("yaml", f"unparseable: {e}")
        return None
    if not isinstance(rec, dict):
        f.err("yaml", "top level is not a mapping")
        return None
    return _stringify_dates(rec)


def validate_incident_file(path: pathlib.Path, validator,
                           scenario_steps: dict[str, list[int]],
                           cited_by: dict[str, set[str]]) -> Findings:
    """An incident is the evidence a scenario stands on. Both ends of the join are
    checked: every scenario it names must exist, and every scenario that cites it
    should name it back, so the join reads the same from either side."""
    f = Findings()
    rec = _load(path, f)
    if rec is None:
        return f
    for e in sorted(validator.iter_errors(rec), key=lambda e: list(e.path)):
        f.err("/".join(str(p) for p in e.path) or "(root)", e.message)
    if f.errors:
        return f
    if path.stem != rec["slug"]:
        f.err("filename", f"should be {rec['slug']}.yaml")
    for sid in rec.get("scenarios", []):
        if sid not in scenario_steps:
            f.err("scenarios", f"'{sid}' does not exist in scenarios/")
    back = cited_by.get(rec["slug"], set())
    forward = set(rec.get("scenarios", []))
    for sid in sorted(back - forward):
        f.warn("scenarios", f"scenario {sid} cites this incident but is not listed here; "
                            "list it so the join reads the same from both sides")
    if not any(r.get("tier") == "0" for r in rec.get("references", [])):
        f.warn("references", "no tier 0 source. An incident grounded only in secondary "
                             "reporting should say so in notes")
    for c in rec.get("contested", []):
        if c.get("status") == "resolved" and not c.get("note"):
            f.warn("contested", "resolved with no note saying how; the resolution is the "
                                "part a reader needs")
    blob = yaml.safe_dump(rec, allow_unicode=True)
    for pattern, why in BANNED:
        if pattern.search(blob):
            f.warn("language", why)
    return f


def validate_baseline_file(path: pathlib.Path, validator) -> Findings:
    """The baseline is the vocabulary every mapping speaks. It has an owner, a status
    and a review date, and the pinned artifacts it names should exist with checksums."""
    f = Findings()
    rec = _load(path, f)
    if rec is None:
        return f
    for e in sorted(validator.iter_errors(rec), key=lambda e: list(e.path)):
        f.err("/".join(str(p) for p in e.path) or "(root)", e.message)
    if f.errors:
        return f
    if path.stem != f"baseline-{rec['baseline']}":
        f.err("filename", f"should be baseline-{rec['baseline']}.yaml")
    if "unassigned" in str(rec.get("owner", "")).lower():
        f.warn("owner", "the baseline owner seat is empty. The migration procedure assumes a "
                        "named individual; name one before the first migration")
    lock = ROOT / "frameworks" / "pinned" / rec["baseline"] / "CHECKSUMS.json"
    try:
        import json as _json
        pinned = _json.loads(lock.read_text()) if lock.exists() else {}
    except ValueError:
        pinned = {}
    if not pinned:
        f.warn("pinned", f"frameworks/pinned/{rec['baseline']}/CHECKSUMS.json is empty; "
                         "framework ids cannot be verified offline and snapshots cannot "
                         "carry artifact hashes. Run tools/pin_frameworks.py")
    if rec.get("status") == "superseded" and not rec.get("superseded_by"):
        f.warn("status", "superseded with no superseded_by")
    return f


def validate_overlay_file(path: pathlib.Path, validator,
                          scenario_rows: dict[str, dict]) -> Findings:
    """An overlay is one org's assessment of one scenario. It may override only the org
    scoped fields, its rows must exist in the scenario, and its coverage tag must derive
    from its scores by the same rule as everyone else's."""
    f = Findings()
    rec = _load(path, f)
    if rec is None:
        return f
    for e in sorted(validator.iter_errors(rec), key=lambda e: list(e.path)):
        f.err("/".join(str(p) for p in e.path) or "(root)", e.message)
    if f.errors:
        return f
    sid = str(rec["scenario"])
    if path.stem != sid:
        f.err("filename", f"should be {sid}.yaml")
    if path.parent.name != rec["org"]:
        f.err("org", f"'{rec['org']}' does not match directory coverage/{path.parent.name}/")
    scen = scenario_rows.get(sid)
    if scen is None:
        f.err("scenario", f"'{sid}' does not exist in scenarios/")
        return f
    if rec.get("baseline") and rec["baseline"] != scen["baseline"]:
        f.err("baseline", f"overlay assessed against {rec['baseline']} but the scenario "
                          f"speaks {scen['baseline']}; re-assess after migration")
    seen = set()
    for r in rec.get("telemetry", []):
        step = r["step"]
        if step in seen:
            f.err(f"telemetry[{step}]", "duplicate step")
        seen.add(step)
        if step not in scen["rows"]:
            f.err(f"telemetry[{step}]", f"scenario {sid} has no telemetry row {step}")
        if r.get("inherit") and len(r) > 2:
            f.warn(f"telemetry[{step}]", "inherit is true but other fields are present; "
                                         "an inherited row carries nothing else")
        d = derive_coverage(r.get("dettect"))
        if d is not None and "coverage" in r and r["coverage"] != d:
            f.err(f"telemetry[{step}]",
                  f"coverage is '{r['coverage']}' but DeTT&CT scores derive '{d}'")
        if d is None and not r.get("inherit") and not r.get("research_needed") \
                and any(k in r for k in ("coverage", "owner", "evidence", "backlog_ref")):
            f.warn(f"telemetry[{step}]", "fields set but no scores; this row is unscored for "
                                         "the org and its coverage tag is an opinion")
        if d in ("Have", "Collectable") and not (r.get("source") or scen["rows"][step].get("source")):
            f.warn(f"telemetry[{step}]", f"{d} with no source named on the overlay or the record")
        if d == "Have" and not r.get("evidence"):
            f.warn(f"telemetry[{step}]", "Have with no evidence")
        if d in ("Blind", "Collectable") and not r.get("owner"):
            f.warn(f"telemetry[{step}]", f"{d} with no owner")
    return f


def load_scenario_rows() -> dict[str, dict]:
    """Scenario id -> baseline and its telemetry rows by step, for overlay checks."""
    out: dict[str, dict] = {}
    for p in sorted((ROOT / "scenarios").glob("*.yaml")):
        if p.name.startswith("_"):
            continue
        try:
            rec = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        if rec.get("id"):
            out[str(rec["id"])] = {
                "baseline": (rec.get("framework_mapping") or {}).get("baseline"),
                "rows": {r.get("step"): r for r in rec.get("telemetry", [])
                         if isinstance(r, dict)},
            }
    return out


def load_incident_citations() -> dict[str, set[str]]:
    """Incident slug -> scenario ids that cite it."""
    out: dict[str, set[str]] = {}
    for p in sorted((ROOT / "scenarios").glob("*.yaml")):
        if p.name.startswith("_"):
            continue
        try:
            rec = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        for slug in rec.get("incidents", []) or []:
            out.setdefault(str(slug), set()).add(str(rec.get("id")))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--strict", action="store_true", help="warnings become failures")
    ap.add_argument("--publishable", action="store_true", help="only records with status: published")
    args = ap.parse_args()

    validator = Draft202012Validator(yaml.safe_load(SCHEMA.read_text()))
    uc_validator = Draft202012Validator(yaml.safe_load(UC_SCHEMA.read_text()))
    inc_validator = Draft202012Validator(yaml.safe_load(INC_SCHEMA.read_text()))
    base_validator = Draft202012Validator(yaml.safe_load(BASE_SCHEMA.read_text()))
    ov_validator = Draft202012Validator(yaml.safe_load(OV_SCHEMA.read_text()))
    incidents = {p.stem for p in (ROOT / "incidents").glob("*.yaml")}
    scenario_steps = load_scenario_steps()
    scenario_rows = load_scenario_rows()
    uc_covered = load_use_case_covers()
    cited_by = load_incident_citations()

    paths = [pathlib.Path(p) for pat in args.paths for p in glob.glob(pat)] or \
            sorted((ROOT / "scenarios").glob("*.yaml")) + \
            sorted((ROOT / "use-cases").glob("*.yaml")) + \
            sorted((ROOT / "incidents").glob("*.yaml")) + \
            sorted((ROOT / "frameworks").glob("baseline-*.yaml")) + \
            sorted((ROOT / "coverage").glob("*/*.yaml"))
    paths = [p for p in paths if not p.name.startswith("_")]

    if args.publishable:
        keep = []
        for p in paths:
            try:
                if (yaml.safe_load(p.read_text()) or {}).get("status") == "published":
                    keep.append(p)
            except yaml.YAMLError:
                keep.append(p)
        paths = keep

    def kind(p: pathlib.Path) -> str:
        parent = p.resolve().parent
        if parent.name == "use-cases":
            return "use case"
        if parent.name == "incidents":
            return "incident"
        if parent.name == "frameworks":
            return "baseline"
        if parent.parent.name == "coverage":
            return "overlay"
        return "scenario"

    n_err = n_warn = 0
    kinds = collections.Counter()
    for path in paths:
        k = kind(path)
        kinds[k] += 1
        if k == "use case":
            f = validate_use_case_file(path, uc_validator, scenario_steps)
        elif k == "incident":
            f = validate_incident_file(path, inc_validator, scenario_steps, cited_by)
        elif k == "baseline":
            f = validate_baseline_file(path, base_validator)
        elif k == "overlay":
            f = validate_overlay_file(path, ov_validator, scenario_rows)
        else:
            f = validate_file(path, validator, incidents, uc_covered)
        n_err += len(f.errors)
        n_warn += len(f.warns)
        if f.errors or f.warns:
            rel = path.resolve()
            print(f"\n{rel.relative_to(ROOT) if ROOT in rel.parents else rel}")
            for where, msg in f.errors:
                print(f"  ERROR  {where}: {msg}")
            for where, msg in f.warns:
                print(f"  warn   {where}: {msg}")

    counted = " · ".join(f"{n} {k} record(s)" for k, n in kinds.items())
    print(f"\n{counted} · {n_err} error(s) · {n_warn} warning(s)")
    if n_err:
        return 1
    if n_warn and args.strict:
        return 2
    if not n_err and not n_warn:
        print("clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
