# Notes: verifying the data strategy brief against the repository

**Status:** working notes from the verification pass the brief's section 6 asked for.
Recorded so the model document and the ERD are built from what the repository says, not
from what an earlier conversation remembered. Each item says what the brief claimed, what
the repository shows, and what was done about it.

**Date:** 2026-09-11. **Repository state:** main at ac84622, branch `data-model`.

---

## 1. The library state the brief describes is a month old

The brief and the Cowork primer say four scenarios are published and scenario 021 is the
scored reference record. Commit ac84622 (2026-08-13, "records: ship the library unscored")
removed every score on purpose. As of this pass all 21 scenarios are drafts, none carries a
DeTT&CT block, and the readiness gate reports that no scenario would emit a test spec. The
spec, sealed prediction and two run records for 021 remain as static worked examples. The
spec's `source_digest` is the sha256 of the 021 file as it stood at commit 476e96c; the
current file no longer hashes to it.

The structural argument in the brief still holds: the model is proven by five schemas, a
validator, and 21 records that pass it. The scoring path is not exercised by any record.

## 2. The org scoped fields, and `source`

The brief's open question 5.1 asked whether `source` is org scoped. The three tools that
handle overlays disagreed: `tools/coverage.py` ignored `source`, `tools/emit_testspec.py`
copied every overlay field, and `tools/apply_session.py --org` wrote `source` into the
overlay. The measurement doc listed five org scoped fields; the session tool listed eight.

Resolved as: `source` is org scoped, because one estate runs one product and another runs a
different one. The full list is `dettect`, `coverage`, `source`, `owner`, `evidence`,
`backlog_ref`, `notes`, `research_needed`, now stated in one place
(`schema/coverage-overlay.schema.json`) and used identically by all three tools and the doc.

A second overlay defect: the doc's overlay example used a `rows:` key with a mandatory
`baseline`; the real file and every tool use `telemetry:` and no baseline. The doc now
matches the file, and `baseline` is optional but checked when present.

A third: the doc says an inherited or absent row is unscored for the org; both tools kept
the reference scores instead, so an org that assessed two rows of six was reported as fully
scored. Both tools now follow the doc. The example org's view of 021 reports completeness
0.33, which is the truth.

## 3. Record types that had no schema

| Record | Before | Now |
|---|---|---|
| Incident | Six YAML files, no schema. Validator checked only that a cited slug existed. | `schema/incident.schema.json`, validated. Referential integrity both ways: an incident's `scenarios` must exist, and a scenario that cites an incident is warned when the incident does not list it back. |
| Framework baseline | One YAML file, no schema. | `schema/framework-baseline.schema.json`, validated. Warns while `owner` reads UNASSIGNED and while `frameworks/pinned/` has no checksums. |
| Coverage overlay | One example file, no schema, format described inconsistently. | `schema/coverage-overlay.schema.json`, validated, including the derived coverage tag, step existence, org and filename agreement. |
| Snapshot | Specified in docs/04 section 5; `tools/coverage.py` emitted a smaller, different shape. | `schema/snapshot.schema.json`; the tool now emits the specified shape and validates before writing. |

The validator's default run now covers scenarios, use cases, incidents, baselines and
overlays. CI picks this up with no workflow change.

## 4. The snapshot and the measurement doc

`tools/coverage.py` diverged from docs/04 in four places, all now aligned to the doc:

- The aggregate coverage was a mean of per scenario rates. The doc says step weighted, and
  says why (a mean makes splitting a scenario a lever on the number).
- The seven maturity gates were a different seven from the doc's M1 to M7. The tool now
  computes M1 reviewed, M2 scored in depth, M3 evidenced, M4 owned, M5 closed loop, M6
  remediable, M7 sourced, and only counts scenarios with every row scored.
- The snapshot lacked `snapshot_id`, `repo_commit`, `supersedes`, `retired_this_period`,
  `ids_added_this_period`, `ids_rescored_this_period` and `non_comparable_with`. All present.
  `--prior` fills the period ledgers from the previous snapshot; `--supersedes` records a
  correction.
- The version tuple was read from the baseline file. It is now read from the pinned
  artifacts' checksum lock when that exists, and the snapshot records which source it used.

## 5. Two copies of the derivation rule

`derive_coverage()` existed in `tools/validate.py` and again in `tools/emit_testspec.py`.
Invariant I-1 says exactly one. The emitter now imports it.

## 6. Source tiers were off by one

The schema grades sources "0" first party, "1" secondary, "2" press, on every record type.
The intake prompts asked the model for 1, 2, 3, and the importer wrote those numbers straight
into the record, so an imported first party source landed as secondary and an unreadable
tier defaulted to 3, which the schema rejects. The intake doc carried the same 1, 2, 3
scale. All of it now speaks the schema's scale, and an unreadable tier lands as "2" with a
review note rather than being guessed upward.

## 7. Entity inventory corrections for the model document

- Three layer vocabularies, not two: `primary_layer_component` (12 value enum),
  `ai_infrastructure_layer` (5 value enum), and the step `layer` seam tag (free text, 18
  characters).
- Scenario carries a `retired` block: date, reason, optional superseded_by.
- Source citation is one shape with three parents: scenario provenance, use case sources,
  incident references.
- The scorecard is written into the run record file by `score_run.py --write`; the run is
  not immutable in the prototype. In the model, scorecard is a separate computed entity keyed
  to the run.
- Both promotion blocks share a shape and differ only in the evidence fields: use case
  evidence is true positive rate, window, volume; spec evidence is clean runs, window,
  environment faults.
- The viewer's `liszt-data.json` is the read model: scenarios with computed metrics,
  readiness blockers and use case ids, use cases, incidents, and a reverse index from
  technique id to scenario ids.

## 8. Known defects, checked

| Claim in the brief | Result |
|---|---|
| Use case template lists six outcome kinds, schema has seven | Confirmed, fixed |
| Intake doc grades tiers 1, 2, 3 against a schema of 0, 1, 2 | Confirmed, and deeper than the doc (section 6), fixed |
| Architecture diagram undercounts the stores | Confirmed, not yet changed |
| `status` and `phase` on a use case overlap | The schema argues they are deliberately separate axes. A decision to reaffirm, not a defect |
| Baseline owner seat is empty | Confirmed; the validator now says so on every run |

## 9. Decisions taken 2026-09-11, and what was built on them

All four open items were decided by the program lead the same day.

1. **Scenario 021 scores restored.** The record's earlier scored state was restored from
   git history, labeled in its header and its notes as an illustrative reference
   assessment, and returned to `published`. The spec and sealed prediction were re-emitted
   from it on the current code, both run records were re-bound to the new prediction digest
   and re-scored, and the validator, rollup, snapshot and viewer all run against it. It is
   the one record that exercises every path. Its author and reviewer are still placeholders;
   a real person has to stand behind it before it is cited outside the program.
2. **Framework artifacts pinned.** `tools/pin_frameworks.py` vendored ATT&CK 19.1, ATLAS
   2026.07, the OWASP LLM 2025 PDF and the DeTT&CT 2.2.0 tree with checksums. The OWASP
   Agentic PDF has no fetchable URL and is still to be downloaded by hand. A new
   `tools/index_frameworks.py` projects the pins into `frameworks/pinned/2026.07/index/`, a
   small committed set of tables (858 ATT&CK techniques with revoked and deprecated flags and
   the revoked-by walk, 15 tactics, 109 data components, 178 ATLAS techniques with the 37
   attack references, 16 ATLAS tactics, 37 mitigations, 20 OWASP slots). The validator now
   verifies every framework id on every record against the index: unknown and revoked ids
   are errors on a published record, deprecated ids warn. The snapshot reads its version
   tuple and artifact hashes from the pins.
3. **Environment is a record type.** `schema/environment.schema.json`, records under
   `environments/`, an optional `environment.definition` on the run record that the
   validator cross-checks (kind, pipeline and targets must agree). Two illustrative records
   describe the labs the 021 runs cite. The external stand-in set is a component role on the
   definition, as the brief's 5.7 asked.
4. **Discovery mode is in scope.** Branch `v2` was committed and merged. The discovery run
   record and the per row `score_provenance` field are entities in the model.

## 10. Findings for an analyst, not fixed here

- Scenario 021 rows 2 and 6 cite data component `DC0074`, which the pinned bundle names
  "Driver Metadata". Both rows describe network egress; the components that fit are
  `DC0078` Network Traffic Flow, `DC0085` Network Traffic Content, or `DC0082` Network
  Connection Creation. The id exists, so the validator accepts it; the mapping is an
  analyst's call and the record is illustrative.
- Scenario 021 row 5 cites `DC0057`, "Snapshot Creation", on a row about container escape
  and credential use read from Kubernetes audit and CloudTrail. `DC0019` Pod Creation,
  `DC0072` Container Creation or `DC0069` Cloud Service Modification fit better. Same
  status: the id exists, the mapping is an analyst's call.
- Two incidents have no tier 0 source and now say so on every validator run.
- `score_run.py --write` reflows long strings in the run record on rewrite. Comments
  survive; line breaks inside folded scalars do not. Cosmetic, worth knowing before
  reading a diff.
