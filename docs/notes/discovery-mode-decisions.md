# Discovery mode: decisions before code

**Audience:** whoever wrote the discovery mode brief, and the developer implementing it.
**Authority:** the brief (`liszt-discovery-mode-brief.md`) states the intent. This note records what the repository at `ac84622` actually permits, and the decisions taken where the two disagree. Once implemented, `schema/discovery-run.schema.json` and `tools/emit_discovery.py` win over this note.

**Status:** decided 2026-09-03. Nothing below is implemented yet.

---

## 1. Why this note exists

The brief section 4 lists four decisions to surface rather than resolve. Reading the repository answers three of them outright, and turns up four more the brief did not see. This note settles all of them so the implementation is written once against a fixed contract instead of twice.

The brief is accurate on every line count, line number, blocker count, and file it names. Two details are corrected in section 4.

---

## 2. Decisions the repository had already made

### 2.1 Discovery does not require `status: published`

The brief asks us to check what `./liszt publish` demands. That command is `tools/publish_library.py`, a Markdown renderer. It filters on status and never sets or gates it. The publication gate is `./liszt publishable`, which runs `validate.py --publishable --strict`, and under that gate a published record must carry zero errors. `validate.py` raises a missing DeTT&CT block from a warning to an error the moment status is `published`.

So an unscored record cannot be published, and discovery mode exists to produce the first scores. Requiring `published` would make the mode impossible to use. The commit this work builds on says the same thing in its own words: the four published records "return to draft, because a published record with unscored rows is a contradiction the validator rightly refuses."

**Decision.** Discovery accepts `draft` and `in-review`. It refuses `retired`, because there is nothing left to learn about a record the library has abandoned. The source record's status is stamped into `discovery.yaml` so nobody reading the spec mistakes an unbacked draft for a claim someone has stood behind. The honesty control moves from status to provenance (section 3.2).

### 2.2 MCP lands in L3

Scenario 014, *Malicious / vulnerable tool & connector (MCP)*, is classified `L3 · Orchestration & Agent`. The library has already placed MCP. No sixth enum value, no schema change.

### 2.3 One discovery record per run

`runs/` holds one immutable file per run. A correction is a new run. Discovery follows the same convention: `runs/DISC-<id>-<date>-<NN>.yaml`, one scenario per file. A multi-scenario agent run produces several files.

The hand-written sample record the acceptance criteria call for lives in `runs/` with the same `WORKED EXAMPLE` banner comment the two `RUN-021-*` files already carry. It is invented data and must say so in the first line, or it recreates the failure `ac84622` was cleaning up.

---

## 3. Decisions the brief left open, now taken

### 3.1 `observed_layer` is an array of one or two enum values, plus a flag

The brief describes two layer vocabularies in conflict. There are three.

- `schema/scenario.schema.json` `$defs/aiLayer`: five values with middle dots. It governs only `classification.ai_infrastructure_layer`, a **scenario-level** field.
- `LAYER_HINTS` in `tools/emit_testspec.py`: five different strings plus `External (out of estate)`, with `unclassified` as the fallback.
- `attack_path[].layer` in the records themselves: unconstrained free text, and across 21 scenarios it holds 37 distinct values. The most common are `Model` (11), `Impact` (11), `App` (11), `Agent` (10), `External` (8), `Data` (6), `Various` (4). Composites like `App → Model`, `Model / Agent`, `Host / CI` are routine.

`Impact` is not a layer, it is a kill chain phase. `External` is an estate boundary. Neither has a legal value in the five-value enum, and a composite step has two. The brief asks a per-step observation to use a per-scenario vocabulary that cannot express what the steps actually are.

**Decision.** The five enum values remain the only layer vocabulary in the repository. `observed_layer` is an array of one or two of them, exact strings, and a sibling boolean `out_of_estate` records that the artifact (or its absence) belongs to a third party. Practical categories map as follows: agent response and MCP server to L3; LLM or model response to L2; retrieval and data to L1; app surface to L4; host, cloud, network to L0. A step that straddles two layers names both. This departs from the brief's literal wording (a single value) and the reason is the data above.

### 3.2 Provenance is a new optional per-row field, `score_provenance`

The brief asks for two things that the repository as it stands cannot do together: reuse `apply_session.py` as the only writer into scenario YAML, and carry provenance through to the record. The telemetry row schema is `additionalProperties: false`, and so is the nested `dettect` object, so there is no legal slot for a marker. `apply_session.py` writes only the eight keys in its `FIELDS` allowlist.

**Decision.** Add one optional field to the telemetry row: `score_provenance`, enum `human-session | agent-proposed`. Absent means human, so all 21 existing records stay valid without edits. The field is added to `apply_session.py`'s `FIELDS`. The bridge always sets it to `agent-proposed`; a human accepting a proposal as their own judgment edits it to `human-session` in the same commit that accepts the number, which keeps the two acts visible in the diff.

This is a change to the core record schema. Its consumers are `validate.py`, `coverage.py`, `build_viewer.py` (and the viewer data contract in `docs/07`, with a `DATA_VERSION` bump), `render_slides.py`, and `publish_library.py`. It is the largest single item in the work and the brief lists it as a paragraph. It goes first.

### 3.3 Proposed scores are excluded from every average

**Decision.** `coverage.py` treats an `agent-proposed` row the way it treats an unscored row: it does not count, it is not zero, it is absent from the ratio. A new `proposed` count per scenario appears in the rollup beside `scored` and `unscored`, so the existence of proposals is visible without their numbers being averaged. `gaming_checks()` gains a check that flags any `agent-proposed` row on a `published` record, since publication is the moment a human is supposed to have stood behind every number.

### 3.4 `LAYER_HINTS` stays as it is

The brief asks that `LAYER_HINTS` be reconciled to the enum. It should not be, and here is why.

`build_procedure()` computes `external = layer.startswith("External")`, and `external` drives `safety.requires_human` and the `out_of_scope` note on third-party steps. The enum has no `External` value. Reconciling the strings would silently switch off the human approval gate on every step that reaches outside the estate. `unclassified`, the fallback, has no enum value either.

`LAYER_HINTS` answers a different question from `observed_layer`. One says *which lab component do I need to stand up*; the other says *which layer did the evidence actually come from*. They are allowed to use different words because they are not the same field.

**Decision.** Leave `LAYER_HINTS` unchanged. Document the reason in a comment beside it. The scoring emitter's behavior does not move.

---

## 4. Corrections to the brief

- The session JSON row shape is `{dettect: {visibility, detection, quality?}, source, owner, evidence, backlog_ref, notes, research_needed}`. Visibility and detection nest under `dettect`; they are not siblings of `source`.
- `run-record.schema.json` caps `observations[].step` at 6. The scenario schema allows telemetry rows up to 8, for control rows. The discovery run schema caps at 6 to match the run record, since discovery reproduces attack steps only.
- `coverage/<org>/*.yaml` overlays are also outside the validator, alongside `runs/` and `specs/`. The brief counts two unvalidated types; there are three. Overlays are out of scope for this work but are noted so the count is right.

---

## 5. Two places the brief's guidance would produce wrong code

Recorded so the implementer does not have to rediscover them.

**Do not reuse `build_procedure()` wholesale.** Its `observation` block is prediction machinery. On an unscored row `derive_coverage()` returns `None`, and `scoreable_for()` tests `cov != "Blind"`, which is true for `None`, so it appends `source-attribution` to a row that names no source. The "Blind is a prediction too, search broadly" hint never fires because `cov == "Blind"` is never true, and discovery wants broad search as the default. `observation.source` degrades to `no source named; nothing to observe`, when in discovery finding the source is the whole task. Reuse the `actions` list, `PROHIBITED`, and the stop conditions. Build the observation block fresh.

**Do not add a discovery flag to `emit_testspec.py`.** The brief already says this; the reason is that `readiness()` is imported by `build_viewer.py` at build time as the single mechanical gate, and any conditional inside it is a conditional inside the viewer's truth.

---

## 6. Order of work

1. `schema/scenario.schema.json`: add `score_provenance`. `validate.py`: accept it, flag it on published records. Run the validator; the bar is zero errors.
2. `schema/discovery-run.schema.json`. `validate.py`: learn `runs/DISC-*.yaml`, which means replacing the two-validator directory dispatch with a small table.
3. `tools/discovery_to_session.py`: the bridge. Reads an accepted discovery record, writes session JSON, sets `score_provenance: agent-proposed` on every row. `apply_session.py`: add the field to `FIELDS`.
4. Sample `runs/DISC-021-*.yaml` with banner. Round trip: validate, bridge, `apply_session.py --dry-run`.
5. `tools/emit_discovery.py`, writing `specs/DISC-<id>-<slug>/discovery.yaml` and `discovery.md`. No `prediction.yaml`.
6. `coverage.py`: proposed count, exclusion, gaming check.
7. `build_viewer.py`: discovery readiness beside testing readiness; discovery as a selectable action in the scenario section.
8. `liszt` and `liszt.cmd`: `discover` and `emit`.
9. `docs/13-discovery-mode.md`, in the register of `docs/12`.
10. Cheap fixes folded in where touched: the hardcoded `verdict: ready` at `emit_testspec.py:638`, and `score_run.py --write` moving from `yaml.safe_dump` to ruamel.

The stale `build_viewer.py` and `validate.py` at the repository root, and `liszt-step-layer-fix/`, are not touched. Removing them is a separate commit for a separate day.
