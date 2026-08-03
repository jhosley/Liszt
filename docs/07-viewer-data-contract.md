# 07 · Viewer data contract

**Audience:** whoever is putting the library behind another application's interface.
**Scope:** the shape of `liszt-data.json`, the stable projection of the record library, and what may be relied on in it.

`tools/build_viewer.py` writes two files:

| File | What it is |
|---|---|
| `liszt-viewer.html` | A self-contained page. One reference implementation of how to present the library. No server, no build step, no network requests. |
| `liszt-data.json` | The same data as a standalone document. **This is the integration seam.** |

**If you are integrating the scenario library into an existing application, consume
`liszt-data.json` and build your own presentation.** Do not scrape the HTML and do not
parse the YAML records directly. The JSON is a stable, documented projection of the
library that already carries the computed metrics, so no consumer has to reimplement the
coverage derivation and risk disagreeing with the rest of the program.

---

## 1 · Generating it

```bash
python3 tools/build_viewer.py                      # published records only
python3 tools/build_viewer.py --include-drafts     # everything
python3 tools/build_viewer.py --org platform-eng   # apply one org's coverage overlay
python3 tools/build_viewer.py --out /path/to/dir
```

Regenerate on every publish. Both outputs are build artifacts. Never hand-edit either
one, and never treat either as a source of truth.

The generator has no network dependency, so it runs unchanged in a restricted
environment.

---

## 2 · Top-level shape

```jsonc
{
  "data_version": 1,              // bump = breaking change. Pin on this.
  "generated_by": "tools/build_viewer.py",
  "view":       { "org": "..", "includes_drafts": false },
  "baseline":   { .. },          // framework versions these IDs speak
  "library":    { .. },          // library-wide metrics
  "owasp_names":{ "LLM03": "Supply Chain".. },
  "scenarios":  [ .. ],          // the records, plus computed metrics
  "use_cases":  [ .. ],          // operational use case records, as committed
  "incidents":  { "<slug>": { .. } },
  "frameworks": { "attack": { "T1190": ["021"].. }.. }
}
```

### `data_version`

The only compatibility guarantee. Within a version, fields are added but never removed
or repurposed. A consumer should read `data_version` and refuse to render on a version
it does not know, rather than silently mis-displaying.

### `view`

What this file represents. `org` is either an organization name or
`"reference assessment"`. `includes_drafts` says whether unreviewed records are present.
**Surface both in any UI you build.** A coverage figure that silently includes drafts, or
silently shows one org's assessment, is a number people will act on incorrectly.

### `baseline`

The framework versions every identifier in the file is expressed in. Identifiers are not
comparable across baselines. Show the baseline anywhere you show framework IDs.

### `library`

| Field | Meaning |
|---|---|
| `records` | Scenarios in this view |
| `published` | How many are reviewed and published |
| `scored` | How many have at least one scored evidence row (a row of the `telemetry` array) |
| `unscored_ids` | Scenario IDs contributing nothing to the figures |
| `mean_have` | Mean Have proportion **across scored scenarios only**, or `null` |
| `exposed` | NOW-priority scenarios with at least one Blind step |
| `full_maturity` | Scenarios passing all seven process gates |

---

## 3 · A scenario object

Every field of the underlying record, plus two computed additions.

```jsonc
{
  "id": "021", "slug": "..", "title": "..", "one_liner": "..",
  "status": "published",
  "classification":    { "priority": "NOW", "evidence": "seen-in-the-wild".. },
  "framework_mapping": { "baseline": "2026.07", "attack": [..], "mapping_confidence": "editorial".. },
  "attack_path":       [ { "step": 1, "layer": "..", "text": "..", "control_held": true } ],
  "telemetry":         [ { "step": 1, "signal": "..", "emitted_at": "..",
                           "source": "..",            // the exact system, named
                           "coverage": "Blind",
                           "dettect": { "visibility": 0, "detection": -1, "quality": {..} },
                           "owner": "..", "evidence": "..", "backlog_ref": ".." } ],
  "commentary": {..}, "scaled_up": "..", "hardening": [..],
  "incidents": ["<slug>"], "provenance": {..},

  "counts":  { "Have": 3, "Collectable": 2, "Blind": 1, "Unscored": 0 },
  "metrics": { .. },
  "use_case_ids": ["UC-001"]
}
```

`counts`, `metrics` and `use_case_ids` are computed by the generator. Everything else
is the record as committed. Field-by-field definitions of the record itself are in
`schema/scenario.schema.json`, which carries a description on every field.

### `metrics`

| Field | Meaning |
|---|---|
| `rows`, `scored` | Evidence rows present, and how many carry scores |
| `completeness` | `scored / rows`. **Gates everything else.** A scenario scored on 2 of 6 rows is mostly unmeasured, not mostly covered |
| `have`, `collectable`, `blind` | Proportions **of scored rows**, or `null` when nothing is scored |
| `quality` | Mean of the five DeTT&CT quality dimensions, normalized 0 to 1 |
| `blind_steps` | Step numbers that are Blind |
| `exposed` | True when priority is NOW and at least one step is Blind |
| `orphaned_gaps` | Steps that are Blind or Collectable with no owner |
| `unfunded_gaps` | Steps that are Blind or Collectable with no ticket |
| `maturity` | Seven booleans plus a `score` string such as `"7/7"` |

---

## 3a · The `telemetry` key and the word evidence

The program's display word for this data is **evidence**: each row records what a
step would emit and whether we would see it, and that is evidence about the
estate. The JSON key stays **`telemetry`**, and so does the YAML field it is read
from. Renaming a key is a breaking change for every existing record, overlay,
session file and consumer, and it buys no meaning, so the name is kept for
compatibility. Keep reading the `telemetry` key; say "evidence" in anything you
show a person.

---

## 3b · Use case records

`use_cases` is a top-level array carrying the operational use case records from
`use-cases/`, in id order, exactly as committed. A scenario says what evidence should
exist; a use case says what gets done with it: what triggers it, what other evidence it
composes and in what role, how the evidence is delivered, what it produces, who receives
that, and what it is allowed to do on its own.

```jsonc
{
  "id": "UC-001", "title": "..",
  "status": "proposed",            // proposed | built | tuned | retired
  "covers":  [ { "scenario": "001", "steps": [2, 3, 4] } ],
  "trigger": { "signal": "..", "source": ".." },
  "composes": [ { "signal": "..", "source": "..",
                  "role": "enrichment" } ],   // enrichment | corroboration | scoping
  "pipeline": { "strategy": "collect-centrally",   // or instrument-at-source |
                                                   //    evaluate-at-platform
                "destination": "..", "owner": ".." },
  "outcome":  { "kind": "alert",       // the artifact produced
                "autonomy": "notify",  // who acts; a separate axis on purpose
                "consumer": "..", "action": ".." },
  "promotion": { .. },             // present only when autonomy is above notify
  "limits": "..",                  // what this use case cannot tell you
  "notes": "..", "provenance": {..}
}
```

Field-by-field definitions are in `schema/use-case.schema.json`, which carries a
description on every field. Three things a consumer should know:

**The join runs both ways.** `covers` on a use case names scenario ids and attack path
steps; each scenario object carries the computed `use_case_ids` of the use cases that
cover it. Join on those, and join defensively: `use_cases` always carries every record
in `use-cases/` whatever its status, while `scenarios` respects the view's draft filter,
so a use case may reference a scenario that is not present in this file.

**Show `status` and `autonomy` wherever you show a use case.** A proposed use case is a
plan, not a running control, and an autonomy above `notify` means a machine acts before
a person looks. Hiding either misleads the reader in a way they cannot detect.

**Show `limits`.** It states what the use case cannot tell you. A presentation that
drops it invites exactly the over-trust the field exists to prevent.

The stability promise is the same as everywhere else in this file: within
`data_version` 1, fields are added but never removed or repurposed. `data_version`
stays 1 for this addition because the change is additive; a consumer that ignores
unknown keys keeps working unchanged, and a consumer reading an older file should treat
a missing `use_cases` key as an empty list, not an error.

---

## 4 · Rules a consumer must not break

These are not style preferences. Breaking them produces numbers that disagree with the
rest of the program, which is worse than showing nothing.

**Never recompute the coverage label.** It is derived from two DeTT&CT scores by one rule
in `tools/validate.py:derive_coverage()`, and the generator has already applied it. If you
must implement it, this is the rule and there are no other cases:

```
visibility == 0                        -> "Blind"
visibility >= 1 and detection >= 1     -> "Have"
otherwise                              -> "Collectable"
```

A `detection` of 0 means the data is retained for later investigation only. That is
Collectable. Treating it as Have overstates coverage, and the overstatement is invisible
in every downstream report.

**Never average an unscored row as zero.** `have` is `null`, not `0`, when nothing is
scored. Scoring nothing and scoring badly must not produce the same figure. Exclude
unscored scenarios from averages and state how many were excluded.

**Never present a cross-framework mapping as authoritative.** Where
`framework_mapping.mapping_confidence` is `"editorial"`, the mapping is the program's own
judgment. Display that, and display `mapping_notes` where present.

**Never carry state by color alone.** Have, Collectable and Blind must be accompanied by
their text label. The reference implementation pairs a colored dot with the word.

**Never write back through this file.** It is a projection. Writes go to the YAML records
through the repository, so that review, validation and history apply. The reference page
captures edits during a session but exports them as a separate session file rather than
writing anything itself, for exactly this reason.

---

## 4a · `emitted_at` against `source`

Two fields, deliberately separate, and the distinction matters.

| Field | Holds | Example |
|---|---|---|
| `emitted_at` | The **category**. Which layer or class of control emits the signal. Appears on the slide. | `EDR / endpoint - container runtime` |
| `source` | The **exact system**, named. The product, log source, index, table, topic or endpoint. | `CrowdStrike Falcon ProcessRollup2, index=edr_main` |

A `Have` whose source nobody can point at is not verifiable. A `Collectable` whose source
nobody can point at cannot be wired up. The validator treats a missing `source` on either
as an error at publication.

The right moment to capture it is during the session, while the people who own the system
are in the room. That is what session mode exists for.

---

## 4b · The session file

Session mode exports `liszt-session-<date>.json`:

```jsonc
{
  "session_format": 1,             // pin on this
  "recorded": "2026-08-02",
  "facilitator": "..",
  "org": "reference assessment",   // which view was open
  "baseline": "2026.07",
  "changes": {
    "021": {
      "telemetry": {
        "1": { "dettect": { "visibility": 2, "detection": 0, "quality": {..} },
               "source": "..", "evidence": "..", "owner": "..",
               "backlog_ref": "..", "notes": ".." }
      },
      "notes": "..",
      "use_case_note": ".."        // "Proposed use case" free text captured in the room;
                                   // appended to the record's notes on apply
    }
  },
  "new_scenarios": [               // scenarios the room says are missing. May be absent.
    { "title": "..",               // required; a proposal with no title is skipped
      "mode": "attack",            // attack | failure
      "layer": "L3 · Orchestration & Agent",
      "priority": "BACKLOG",       // NOW | NEAR-TERM | BACKLOG
      "one_liner": ".." }          // what happens, in plain terms
  ]
}
```

Apply it with `python3 tools/apply_session.py <file>`, which writes into the YAML records
while preserving every comment, recomputes the coverage label from the scores rather than
trusting the file, and commits nothing. Review the diff and run the validator before
committing.

With `--org <name>` it writes a `coverage/<org>/` overlay instead of editing the shared
records. Use that when the session assessed one organization's estate.

### `new_scenarios`

A tabletop turns up scenarios the library does not have. This array is where they land, so
the thought survives the hour it came up in.

Each entry is five plain answers, not a record. On apply, `tools/apply_session.py` calls
`tools/new_scenario.py` to build a real record from `scenarios/_TEMPLATE.yaml` for each
one: the next free id, the slug from the title, the filename the validator insists on, and
every teaching comment in the template kept. The record is born at status `draft` with the
template's placeholders still in it, because a five-field proposal is a starting point and
an analyst still has to do the work. The session file's `facilitator` becomes
`provenance.authored_by` when one is set.

Proposals are written to `scenarios/` even under `--org`, because a new scenario belongs to
the shared library while coverage belongs to an estate.

**`session_format` stays 1, because the change is additive.** Nothing that was in a session
file before means anything different, and every existing field is still read the same way.
A file written before this key existed simply has no `new_scenarios`, which a reader must
treat as an empty list rather than an error. A tool that does not know the key ignores it
and keeps working.

---

## 5 · Color reference

The reference implementation uses these three status colors. They were validated for
contrast and for color-vision-deficiency separation against a white surface, so reuse
them rather than picking your own.

| State | Hex |
|---|---|
| Have | `#1E7F4B` |
| Collectable | `#B5852B` |
| Blind | `#B0463B` |
| Unscored | `#9AA7B1` |

---

## 6 · Notes for a hosted implementation

The reference page is deliberately read-only and static. If you are building something
larger, three things are worth deciding early.

**Keep the repository as the system of record.** A web application that becomes the master
copy recreates the problem this program exists to solve. Reads come from generated data;
writes go to the records through the normal review path.

**Regenerate rather than sync.** The generator is fast and has no dependencies. Running it
in the publish pipeline is simpler and less error-prone than maintaining a live connection
to the library.

**Decide the org question before you build.** Coverage is a property of an estate, not of
a scenario. Either generate one file per org from the overlays, or carry the org in the
request and generate on demand. Mixing assessments in one view without labeling them
produces figures nobody can defend.
