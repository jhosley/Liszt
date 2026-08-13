# Liszt: Product Requirements for a Production Version

**Document type:** Product requirements document for evaluating development teams
**Ground truth:** github.com/jhosley/Liszt, branch main, commit 2711e4f at time of writing
**Status of this document:** Draft for developer evaluation

---

## 1. Purpose and reading guide

This document defines what a production version of Liszt must do. It is written for a development team that will evaluate the working prototype and propose a production ready system. It answers four questions in order: what must remain true for the result to still be Liszt (section 4), what the baseline delivery is (section 5), what comes after baseline (section 6), and where the product is heading (section 7).

One thing to settle before anything else: **the architecture is deliberately open.** The repository at the commit above is a working prototype and the reference implementation of every behavior described here. It is not the design. A production team may replace the file-per-record YAML store with a database, the static viewer with a served application, the copy and paste prompt workflow with governed API calls, and the Python CLI tools with services, provided every invariant in section 4 survives the replacement. Where this document cites a file or a function, it is citing the authoritative statement of a behavior, not prescribing that the behavior stay in a file or a function.

Suggested reading order for a first pass: sections 2 and 4, then the prototype's own `README.md` and `docs/01-methodology.md`, then sections 3 and 5 of this document with the schemas in `schema/` open beside them. Section 9 lists the prototype's known defects so nobody rediscovers them.

Terminology note: the program's display word for the per-step observability data is "evidence"; the stored field and JSON key is `telemetry`, kept for compatibility. This document uses "evidence row" in prose and `telemetry` when naming the field.

## 2. Product summary and the problem

Liszt is a system of record for AI attack and failure scenarios, and for the observability facts attached to them. Each scenario is one coherent attack or failure chain, expressed as 3 to 6 ordered steps. Each step carries exactly one evidence row saying what signal that step would emit, where it would land, and, once scored against the DeTT&CT scales, whether the organization would actually see it. From those records the tooling computes coverage, exposure, and maturity reporting; renders slides and a web viewer; and, in the newest part of the loop, emits sealed test specifications so the claims in the records can be checked by a run rather than trusted.

The problem it exists to solve is simple to state. **A coverage percentage on a slide can be authored. A verdict computed from two scores, revalidated on every row, cannot.** Most security programs report coverage as an opinion with a number attached: someone believed the estate could see something and wrote 80 percent. Liszt makes the coverage tag on every row a derived value, computed by one rule from a visibility score and a detection score, recomputed by the validator on every run, with an error on any mismatch. An analyst who wants a better number has to change the scores, and the scores demand evidence a third party can re-run. That single inversion, from asserted to derived, is what the whole product protects.

The three metric families exist because three different audiences ask three different questions, and one number cannot answer them all:

| Metric family | The question it answers | Audience |
|---|---|---|
| Coverage | How much of each attack chain can we actually see, and how much is merely logged | Engineering: detection engineers and data source owners |
| Exposure | Which NOW-priority scenarios still have Blind steps, and how early in the chain | Risk: whoever allocates instrumentation budget and answers "what would we not see" |
| Maturity | Is the process itself working: reviewed, scored, owned, evidenced, ticketed | Program: whoever must defend the numbers to audit or leadership |

They are reported side by side and never composited, because the most dangerous state, high coverage with low maturity, meaning confident numbers with nothing behind them, is exactly what a composite hides.

**Library state at this commit:** 21 scenarios, of which 4 are published (001, 005, 017, 021) and the rest are drafts; 12 use case records; 6 incident records. Scenarios 001, 003, 005, 009, and 017 carry illustrative scores, labeled as such in their notes; scenario 021 is the fully worked, fully scored reference record. Production planning should treat the library as young and the discipline as the asset.

## 3. Domain model

This section describes every record type a production system must store, with the load bearing fields and constraints taken from the schemas in `schema/` and the formats defined in the docs. The schemas are the authority; this is the orientation.

### 3.1 Scenario

The central record (`schema/scenario.schema.json`). One YAML file per scenario today; one record per scenario in any design.

| Field group | Load bearing content |
|---|---|
| Identity | `id` (three digits, zero padded, quoted, immutable, never reused even after retirement), `slug` (kebab-case, max 60, stable forever), `title` (8 to 70 chars), `one_liner` (40 to 420 chars, readable by a non-specialist) |
| `status` | `draft`, `in-review`, `published`, `retired`. Retired records stay forever, with `retired.date`, `retired.reason`, and optional `superseded_by` |
| `classification` | `primary_layer_component` (where the scenario operates), `ai_infrastructure_layer` (the controlled five-layer enum, below), `evidence` tier (`seen-in-the-wild`, `seen-in-research`, `doomsday`), `priority` (`NOW`, `NEAR-TERM`, `BACKLOG`) with 2 to 4 `priority_rationale` lines of which at least one must name the organization's own exposure, and `mode` (`attack` or `failure`; failure relaxes the adversary-shaped validator checks) |
| `framework_mapping` | `baseline` (pointer to the pinned framework baseline; never mixed within a record), `attack`, `attack_tactics`, `atlas`, `owasp_llm`, `owasp_agentic` (all edition or version qualified), `mapping_confidence` (`authoritative` or `editorial`), `mapping_notes` |
| `attack_path` | 3 to 6 ordered steps, hard ceiling 6. Each step: `step` number, `layer` (free text seam tag, 18 character cap), `text` (25 to 125 chars, one adversary move, mechanical present tense), optional per-step `attack` and `atlas` IDs, optional `control_held` boolean (present only when a control was actually tested) |
| `telemetry` | 3 to 8 rows. One `attack-step` row per attack path step, mandatory; `control` rows numbered after the steps and excluded from all coverage arithmetic. Row fields in 3.2 |
| Supporting | `commentary` (three analysis paragraphs), `scaled_up` (always hypothetical), `incidents[]` (slugs with referential integrity into the incident library), `hardening[]` (each item must name the step or steps it breaks), `provenance` (`authored_by`, `reviewed_by`, dates, tiered `sources[]`), `notes` |

**The five AI layers.** `classification.ai_infrastructure_layer` is a controlled enum of five values: L0 Infrastructure, L1 Data, L2 Model, L3 Orchestration & Agent, L4 Application. Data contract fact, stated once: in the stored strings the layer code and the layer name are joined by the character U+00B7 with a space on each side, so the stored form of the Model layer is exactly "L2 · Model", and consumers must match on the full stored string, not on a reconstruction of it. The step-level `layer` field is deliberately not this enum: it is a free text reading aid with an 18 character cap and a working vocabulary of 17 tags, which includes "Model / store", added to tag the model artifact at rest.

### 3.2 Evidence row

Each row in `telemetry` answers one step. Fields: `step`, `kind`, `signal` (a noun phrase naming what is emitted, not a sentence, not a tool), `emitted_at` (the category of layer or control that emits it), `source` (the exact named system, index, table, or topic; required in practice on every Have and Collectable), `data_components` (ATT&CK `DCxxxx` only; `DSxxxx` is retired and invalid), `coverage` (derived, cached, recomputed by the validator), `dettect` (the scores, 3.2.1), `detection_opportunity` (the outcome to alert on, not the product), `owner` (the team that would accept the ticket; required on every Blind and Collectable), `evidence` (a re-runnable artifact; required on every published Have), `backlog_ref` (the ticket that closes the loop), `notes`.

**3.2.1 The scales and the derivation rule.** DeTT&CT visibility runs 0 to 4. Detection runs -1 to 5, and a detection of 0 means forensics only: the data is retained, nothing alerts on it. The five quality dimensions (device completeness, data field completeness, timeliness, consistency, retention) each run 0 to 5, qualify a Have, and never enter the derivation. The coverage rule, `derive_coverage()` in `tools/validate.py`, is the single source of truth:

| Condition | Coverage |
|---|---|
| No `dettect` block, or visibility or detection missing | None. The row is unscored. Absent, never zero |
| visibility equals 0 | Blind |
| visibility at least 1 and detection at least 1 | Have |
| anything else scored (visibility at least 1, detection 0 or -1) | Collectable |

Have means the chain can be interrupted; Collectable means it can be written up afterward; Blind means nothing produces the signal today; unscored means nobody has looked, and it is excluded from every average.

### 3.3 Use case

`schema/use-case.schema.json`. A scenario says what evidence should exist; a use case says what gets done with it. Separate records because one use case serves several scenarios, and because its lifecycle moves on an engineering clock, not a review clock.

Load bearing fields: `id` (`UC-NNN`, immutable, never reused); `status` (`proposed`, `built`, `tuned`, `retired`, earned in order); `covers` (scenario ids plus the exact attack path steps whose rows the use case consumes, both ends validated); `trigger` (exactly one signal with an exact named source; two possible triggers means two use cases); `composes` (additional evidence, each entry carrying a `role` of `enrichment`, `corroboration`, or `scoping`; an empty list is a recorded answer, not a skipped question); `pipeline` (`strategy` of `collect-centrally`, `instrument-at-source`, or `evaluate-at-platform`, plus named `destination` and building `owner`); `outcome` (`kind` of the artifact produced, and `autonomy` as a deliberately separate axis: `notify`, `assisted`, `autonomous`, plus `consumer` and `action`); `promotion` (required whenever autonomy is above notify: measured true positive rate with window and volume, blast radius, reversibility, a named approver and date, a standing review loop, and an off switch); `limits` (what the use case cannot tell you, mandatory); `phase` (engineering progress from `in-scoping` to `in-production`, deliberately separate from `status` so neither axis has to lie about the other); `pipeline.owner` as the engineering owner and `operates` as the operating owner, distinct on purpose; `provenance` with an `illustrative` flag for records carrying demonstration data.

### 3.4 Incident

One record per real world incident, described once and cited by every scenario that draws on it (`incidents/`, slug-keyed). Carries the tiered sources and, where the parties disagree, a `contested` block holding both claims verbatim with `status: unresolved`. Referential integrity from `scenarios[].incidents` is enforced by the validator, so a guessed slug is a build failure.

### 3.5 Framework baseline

`frameworks/baseline-2026.07.yaml` pins the vocabulary every mapping speaks. The 2026.07 pin: ATT&CK Enterprise 19.1 (spec version 3.3.0), ATLAS 2026.07 (format version 6.0.0), OWASP LLM Top 10 2025, OWASP Agentic Top 10 2026 (ID prefix ASI), DeTT&CT 2.2.0. The file records id-stability characteristics, breaking changes since the prior baseline, crosswalk honesty (no authoritative OWASP to MITRE crosswalk exists in either direction; the ATLAS to ATT&CK linkage is 37 of 178 techniques, one way, meaning "adapted from"), and the migration rules including a one cycle dual report at every migration. **Open item a production team inherits: the baseline owner field is literally UNASSIGNED in the file.** The migration procedure assumes a named individual owner, and the first migration cannot be run until the program names one.

### 3.6 Test loop records

Three schemas define the agent testing loop (`docs/12-agent-testing.md`).

**OpenSpec** (`schema/test-spec.schema.json`): the generated test specification, `spec.yaml` plus a `spec.md` rendering in EARS style. Engine agnostic and payload free by design: each procedure step says "reproduce this behavior using a published emulation of technique X," and an adapter binds the technique id to a concrete test from an emulation library at run time. Carries a `source_digest` of the scenario it was emitted from (a changed scenario makes the spec stale), the full authorization guardrail block (autonomy rung, explicit target allowlist with no wildcard and no default, time box, egress policy defaulting to deny-all, stop conditions, teardown, prohibited actions, and a promotion block required above lab-only), and the declared environment including the telemetry pipeline mode.

**Prediction** (`schema/prediction.schema.json`): what the run is claimed to find, sealed before the run. Committing the file is the seal; git is the notary. The run record binds to it by sha256, and the scorer refuses to score if the digest has moved. Each row decomposes the coverage tag into separately falsifiable claims: `signal_present` (derived from visibility at least 1), `source` (the named system), `detection_fires` (derived from detection at least 1, testable only where the real pipeline runs). Every value derives from the evidence row, never invented, so a wrong prediction is a wrong record. Optional per-row `confidence` turns the scorecard into a calibration curve; `expectations.expected_surprises` is itself a claim.

**Run record** (`schema/run-record.schema.json`): observations authored by a human before opening the prediction, per step: `executed`, `observed` (`detected`, `logged-only`, `absent`, `unscoreable`), `observed_source`, latency, re-runnable artifacts, and surprises. The scorecard block is computed only, by `tools/score_run.py`, producing four numbers: exact match rate; optimism index (mean predicted rank minus mean observed rank; positive means the program systematically believes it sees more than it does); source precision (of the artifacts that appeared, the share that appeared in the system the record named); and surprise count. The environment's declared pipeline mode, not ambition, decides which claims may be scored: `mirrored` scores everything, `scratch` scores signal presence and source only, `none` scores nothing about the estate.

### 3.7 Session file

The viewer's export format (`docs/07-viewer-data-contract.md` section 4b). `session_format: 1`, facilitator, org context, per-scenario per-row changes (scores, source, evidence, owner, backlog ref, notes), and `new_scenarios[]` proposals of five plain answers each. Applied by `tools/apply_session.py`, which preserves comments, recomputes the coverage tag from the scores rather than trusting the file, and commits nothing; a human reads the diff.

### 3.8 Org overlay

`coverage/<org>/<scenario-id>.yaml`. The scenario library is organization independent; what differs per org is coverage. An overlay overrides evidence rows per row for one org, carries `assessed_by` and a baseline that must match the scenario's, may mark rows `inherit: true` (explicitly not assessed by this org, excluded from that org's scored set), and may not change anything outside the org-scoped fields. The consequence is political and load bearing: an organization can adopt the whole library without publishing its coverage, and a team that later chooses to publish produces numbers that aggregate on day one.

## 4. Invariants

This is the section that matters most. Each invariant states the rule, why it exists, and what breaks if a production design violates it. A proposal that cannot uphold one of these is a proposal for a different product.

**I-1. Coverage is computed, never typed.** The Have, Collectable, Blind tag is derived from two scores by one rule in one place, and every stored tag is a cache that the validator recomputes and errors on. Why: this is the product's core claim, the difference between an evidence-backed determination and analyst optimism with a number attached. What breaks: any UI with an editable coverage dropdown, any second implementation of the rule that can drift, any import path that trusts an incoming tag. The production system must keep exactly one implementation of the derivation and route every consumer through it or its output.

**I-2. Nothing writes itself back. A human applies every change, with attribution and a backlog reference.** The viewer captures edits in the browser session only; the session file is applied by a tool while a person reads the diff; the run scorer emits proposals, never edits; the conversion prompt emits a draft the importer re-checks. Why: the records get quoted to auditors and boards, and every change must have a person who stands behind it and a ticket that explains it. What breaks: any "sync" feature, any model output that lands directly in a record, any bulk update without per-change attribution. In production, "a human applies" may become "a human approves a change set in a governed workflow," but the approval must be per change set, attributable, and produce the same review artifacts.

**I-3. An author cannot publish their own record; an independent reviewer is required.** `reviewed_by` must exist and differ from `authored_by` before status may become published; the validator errors when they match. Why: independence is the only real control over content quality; the validator checks structure and arithmetic, not truth. What breaks: role models that let one identity hold both ends, bulk publish operations, any workflow where review is a checkbox the author sets.

**I-4. Predictions are sealed before runs.** The prediction is a separate artifact, committed before execution and bound by digest; the scorer refuses a moved digest; observations are authored before the prediction is opened. Why: an editable prediction measures hindsight, and the calibration loop is the product of the testing phase. What breaks: storing predictions and observations as mutable rows in one table with no tamper evidence. Production may replace git as notary, but only with something that gives an equally checkable seal.

**I-5. Unscored is absent, never zero.** A row without scores has no coverage value, is excluded from every numerator and denominator, and pushes its scenario out of maturity reporting; every published figure carries its completeness companion. Why: scoring nothing and scoring badly must never produce the same number; treating unknown as zero manufactures precision, sells the same improvement twice, and hides orphans. What breaks: any aggregation layer, BI export, or dashboard that defaults nulls to zero. This is the invariant most likely to be violated accidentally by a reporting stack.

**I-6. The environment decides what a run can prove.** The pipeline mode recorded on the run, not the spec's request and not anyone's intent, gates which claims are scoreable; a detection claim in a scratch lab is unscoreable, not failed and not passed. Why: a cheap lab producing a confident detection verdict is a wrong number wearing a lab coat. What breaks: schemas or scorers that collapse "unscoreable" into "absent," or reporting that quotes a scratch run as a detection test.

**I-7. The autonomy ladder is enforced by refusal.** Rungs are lab-only, production-observe, production-active. Only lab-only is enabled; the production rungs are fully specified and switched off; the executor must refuse anything above the enabled rung even when a spec asks. Promotion moves one rung at a time with measured evidence, a named approver, a review loop, and an off switch, on both the test loop and the use case ladder (notify, assisted, autonomous). Why: this is what makes a production rung approvable later, and it is the record that gets pulled the day an automated action misbehaves. What breaks: configuration flags that let an operator skip a rung, or promotion blocks filled retroactively.

**I-8. Org overlays keep the library publishable.** The shared record carries everything org independent; coverage lives per org in overlays; there is no cross-org aggregate coverage number because there is no such estate. Why: adopting the library must cost a team nothing politically; coupling adoption to gap disclosure kills adoption. What breaks: multi-tenant designs that store scores on the shared record, or any rollup that averages across orgs.

**I-9. Framework identifiers are pinned to a named baseline, edition qualified, never mixed.** Every record names exactly one baseline; OWASP IDs always carry their edition; migration is deliberate, with a dual report cycle; tactic-level metrics across the ATT&CK v19 split are flagged non-comparable. Why: without pinning, a coverage trend line measures MITRE's release schedule. What breaks: storing bare IDs, auto-updating framework data, or letting two baselines coexist inside one record or one snapshot.

**I-10. Evidence must be re-runnable by a third party.** A Have claim is backed by an artifact someone else can execute: a saved search that returns rows, a rule id, a ticket. "We have EDR" is not evidence; stale evidence downgrades the row rather than being refreshed with an excuse. Why: an unverified Have is worse than a Blind, because it removes the gap from the backlog without closing it. What breaks: evidence as free text nobody audits; production should make evidence a first class, spot-auditable reference.

**I-11. Specs carry no payloads and bind by technique id.** The test spec is an abstract, engine agnostic action set; an adapter resolves technique ids to a published emulation library at run time; no exploit code anywhere in the records or generated material. Why: an abstract spec is the only form reviewable for safety before a tool is chosen, and specs outlive runners. What breaks: embedding runner commands or payloads in specs, or coupling the spec format to one vendor's test library.

**I-12. Model output is always a proposal; machine checkable facts are recomputed by tooling and never trusted from a model.** The conversion prompt runs three self checks, and the importer re-checks everything mechanically anyway; the readiness prompt's judgment JSON supplements, never replaces, the mechanical gate; no metric is ever produced by asking a model to count. Why: a model's count is plausible and uncheckable; the program's credibility rests on every number being reproducible by a script. What breaks: shipping model-derived fields without a deterministic re-check, or any metric path with a probabilistic step in it.

## 5. Baseline functional requirements

What production v1 must deliver to replace the prototype for daily use. Requirements are numbered B-n for reference. Where a requirement names a prototype tool, the tool defines the behavior to preserve, not the implementation.

### Record store and governance

- **B-1.** Store every record type in section 3 with the constraints of the schemas in `schema/`, including immutable, never reused identifiers and retired records retained forever.
- **B-2.** Multi user operation: concurrent reading and editing of drafts by authenticated users, with per-change attribution (who, when, and the change itself) durable for the life of the record.
- **B-3.** Role separation sufficient to enforce I-3: author, reviewer, and publisher capabilities distinguishable per record, with the author-reviewer identity check enforced by the system, not by convention.
- **B-4.** A complete audit trail: every state transition (draft, in-review, published, retired) and every applied change set is recorded with attribution and, for score changes, the backlog reference that explains it.
- **B-5.** Migration of the existing 21 scenarios, 12 use cases, 6 incidents, the pinned baseline, the specs, and the two run records, without loss of comments, notes, or provenance. Illustrative scores (001, 003, 005, 009, 017) must remain labeled as illustrative.

### Validation service

- **B-6.** Reimplement or wrap the validation behavior of `tools/validate.py` as a service every write path calls: schema conformance, the house rules (filename and id discipline, step and row alignment, length budgets, referential integrity into incidents and use case covers), coverage recomputation with error on mismatch, and the publication bar of zero errors and zero warnings at published status.
- **B-7.** Exactly one implementation of `derive_coverage()` in the production codebase, exercised by every consumer including the reporting layer and any UI badge (I-1).
- **B-8.** The draft versus published asymmetry: findings that warn on a draft error on a published record, including unscored rows, missing owners on gaps, missing evidence on Have, and missing sources on Have and Collectable.

### Scoring sessions

- **B-9.** A facilitated session mode equivalent to the viewer's: per-row editing of scores, source, evidence, owner, backlog reference, and notes; capture of proposed new scenarios; a readback view; export of a session artifact.
- **B-10.** Session changes never write directly to records. They land as a reviewable change set applied through the governed path of B-2 to B-4, preserving the semantics of `tools/apply_session.py`: recompute the coverage tag from the scores rather than trusting the captured tag, and preserve record comments and formatting where the store has them.
- **B-11.** Org-scoped sessions: a session run against one organization's estate produces overlay changes under that org, never edits to the shared record, while new scenario proposals still land in the shared library.

### Intake

- **B-12.** A research library equivalent to the "Bring in a scenario" tab: a managed set of research prompts (three today: published incidents, threat research feeds, analyst hypothesis), extensible by users, each feeding one conversion step.
- **B-13.** The conversion step moves from copy and paste into an external assistant to a governed model API call inside the product, carrying the same conversion prompt contract: it emits exactly one scenario draft and runs the same three self checks the prompt specifies today, which mirror the importer's checks.
- **B-14.** The importer re-check stays, unchanged in principle: every machine checkable property of a converted draft (layer enum, step geometry and budgets, field lengths, id shapes, referential integrity) is re-verified mechanically on intake regardless of what the model claimed (I-12), and corrections are recorded as correction flags.
- **B-15.** Converted drafts enter the library as drafts, attributed to the human who ran the intake, and never carry scores; coverage is scored later by the people who own the systems.

### Scenario management

- **B-16.** A library wide readiness view: for every scenario, whether it would emit a test spec today and the exact blockers otherwise, computed from the same code path as the emitter (the prototype imports `emit_testspec.readiness()` into the viewer build so the page and the emitter cannot disagree; production must preserve that single-source property).
- **B-17.** Test design support: the test plan prompt (how to break a chain into testable units, whether the full path is worth one exercise, what is blocked at the enabled rung) and the readiness judgment prompt, both as governed model calls under the B-13 contract, with the judgment JSON stored against the record and the mechanical gate always recomputed independently.
- **B-18.** Use case design support: the use case proposal prompt and the use case record stub prompt under the same contract, producing proposals and stubs that enter the lifecycle at proposed status with every unknowable field marked as such.

### Use case lifecycle

- **B-19.** Full lifecycle management of use case records: status ladder earned in order, phase axis maintained separately, promotion blocks required and validated whenever autonomy is above notify, and the covers join validated in both directions against the scenario library.
- **B-20.** Surfacing rules preserved everywhere use cases render: status and autonomy always visible, limits always visible.

### Reporting

- **B-21.** The three metric families computed exactly as `docs/04-measurement.md` defines: step-weighted aggregate coverage with completeness always attached; exposure over NOW-priority scenarios with earliest Blind step, orphaned and unfunded step lists; the seven maturity gates over the eligible population with assessed always attached. No composite score.
- **B-22.** Immutable snapshots per metric run, per org, carrying the full framework version tuple read from the pinned artifacts, library state, and the anti-drift fields (`ids_rescored_this_period`, `retired_this_period`); corrections are new snapshots that supersede, never edits.
- **B-23.** The integrity signals reported alongside the families: completeness and assessed denominators, rescore visibility, retirement visibility, and absolute counts next to every percentage.
- **B-24.** Calibration reporting from the test loop once runs exist: exact match rate, optimism index, source precision, and surprise count, always next to the number of rows scored.

### Documentation

- **B-25.** The product's documentation (methodology, quality bar, mapping guide, measurement definitions, and the framework reference) rendered from the pinned baseline and the records rather than maintained as parallel prose, so the docs a user reads cannot disagree with the data. The prototype's Documentation and Frameworks tabs are the reference behavior.

### Authentication and roles

- **B-26.** Real identity: authenticated users, so that `authored_by`, `reviewed_by`, `assessed_by`, `sealed_by`, and approver fields name accountable people, and so the I-3 check is enforceable. Identity provider integration is an open question (section 10), but local accounts are an acceptable v1 floor.

### Deployment posture

- **B-27.** The air gap story is preserved. Today the entire analysis path (validation, coverage rollup, viewer build, slide render, session apply, spec emission, run scoring) has zero network dependency; only research and source verification need the internet, and the boundary between them is a defined artifact. **Production v1 must keep the analysis path fully functional with no network access**, including framework lookups served from vendored pinned artifacts with checksums. Model API calls (B-13, B-17, B-18) belong to the research side of the boundary and must degrade to the copy and paste workflow where no egress exists.
- **B-28.** Deployable in a customer controlled environment. A design that only works as a hosted multi-tenant service fails the population this product serves.

## 6. After baseline

Not required for v1, but the design should not preclude any of it. Numbered A-n.

- **A-1. Test runner and adapter.** The execution half of the testing loop: an adapter that binds spec procedures to a published emulation library by technique id, target provisioning against the allowlist, and enforcement of the guardrail block at run time. The spec format is deliberately runner agnostic; the adapter choice must stay reversible.
- **A-2. The rescore translator.** Scorer output proposes rescores in coverage terms; the records store DeTT&CT integers. The missing piece is the translation from a scorer proposal to concrete visibility and detection values, flowing through the session path so a human applies it with the run id as the backlog reference. This is the prototype's own next gap: only 1 of 21 scenarios is currently testable end to end, and closing the loop from run to record is what makes testing compound.
- **A-3. The production-observe approval path.** The rung is fully specified and switched off. Turning it on requires a defined approval workflow (who signs, on what evidence, with what standing review), after which detection claims can be tested against the real pipeline without a mirrored lab.
- **A-4. SIEM and ticketing integrations.** Read side: verifying that a cited evidence artifact still resolves (a saved search still returns rows) to support evidence spot audits. Ticketing side: resolving `backlog_ref` status so closed loop reporting stops being manual. Both are integrations, not replacements; Liszt does not become the ticket system (section 8).
- **A-5. The beyond-AI generalization.** A parked mockup tab sketches extending the method past AI scenarios. It is explicitly blocked on five recorded decisions: (1) rename the AI layer field or add a parallel field for non-AI stacks; (2) whether an environment record is required or optional; (3) one coverage number or one per stack; (4) who owns an environment record and its review; (5) whether "conditions" are a concept of their own or an environment with a filter. **Decision three is the one that matters most: blending an AI population and an endpoint population into one figure makes the AI picture look better than it is,** because the mature endpoint estate's Have rows dilute the AI blind spots the program exists to expose. Until those five are decided and recorded, the product stays AI only, and v1 should be built without prejudice to either outcome.

## 7. Roadmap

The vision is stated with intent: **Liszt becomes a major tool for modeling attack scenarios and facilitating research.** Two goals define the trajectory.

First, enable the cybersecurity researchers: purple teamers, penetration testers, threat modelers, and tools engineers such as WAF and endpoint solution owners. For them Liszt is the place where a technique becomes a mapped, scored, testable chain: research feeds intake, intake produces records, records emit sealed test specs, and runs feed calibrated findings back. The library becomes the shared bench these disciplines work at, instead of each keeping private slideware.

Second, enable observability engineers with real inference, reasoning, and research, so they can engineer the optimal use case solution for each environment and attack scenario. The use case record already captures the decision space (trigger, composition, delivery strategy, outcome, autonomy); the roadmap goal is that the system helps reason over it, grounded in the scenarios, the incidents, the coverage state, and the calibration history of the estate in question.

The mechanism for both is deep integration with frontier AI models, done the way the invariants demand. The research and conversion prompts move from copy and paste into governed in-product workflows. Retrieval over the library grounds the model in the actual records rather than its training data. And every model output remains a proposal that a human applies, so the invariants hold at scale: the same review, attribution, and mechanical re-check discipline, at much higher throughput.

That makes the prompt library a first class managed asset. Today it is eight in-product prompts (three research prompts, the conversion prompt with its three self checks, the readiness judgment prompt, the test plan prompt, the use case proposal prompt, and the use case record stub prompt). In production they are versioned, reviewed, owned, tested against evaluation cases, carrying identifiers and changelogs, pinned and migrated with the same discipline as the framework baseline, because a silently changed prompt moves output quality the way a silently changed taxonomy moves a metric. The importer's correction flags are free telemetry on prompt quality: every field the mechanical re-check had to fix is a measured defect of the prompt version that produced it, and that stream should feed prompt evaluation from day one.

## 8. Non goals for production v1

- **Autonomous execution against production.** Only lab-only runs. The production rungs remain specified, switched off, and refusal enforced.
- **Automatic rescoring.** No score changes without a human applying them; scorer output is proposals.
- **Inventing crosswalks between frameworks.** No authoritative OWASP to MITRE mapping exists, and the product will not manufacture one; editorial mappings stay labeled editorial.
- **Replacing GRC or ticketing systems.** Liszt records the `backlog_ref` and reads status at most; the work lives where the organization tracks work.

## 9. Known defects and honest state

The prototype's own worked examples and code carry defects a production team should know about rather than rediscover.

1. **The two run records in `runs/` are hand authored worked examples.** No agent executed them; they exist to exercise the scorer and teach the format. Treat them as fixtures, not as evidence about any estate.
2. **`tools/score_run.py --write` destroys comments in run records.** It rewrites the file with a PyYAML dump; it should use ruamel round tripping the way `tools/apply_session.py` does.
3. **A stale comment in `tools/emit_testspec.py` claims `score_run.py` imports its RANK constant.** It does not; each file defines its own identical copy. Two copies of a shared constant is exactly the drift pattern I-7 style single sourcing exists to prevent; production should consolidate.
4. **The readiness verdict stored in an emitted spec is hardcoded to "ready"** rather than read from the readiness judgment JSON the prompt produces. The mechanical gate genuinely runs; the judgment half's result is not yet wired into the artifact.

More broadly: 17 of 21 scenarios are drafts; five records carry labeled illustrative scores; only scenario 021 clears the testing readiness gate today; and the framework pins are referenced but the `frameworks/pinned/` vendoring with checksums is specified rather than fully populated. None of this is concealed in the repo, and the honest state is itself a demonstration of the program's reporting discipline.

## 10. Open questions for evaluating teams

Proposals should take a position on each of these.

1. **Storage and concurrency model.** The prototype is files plus git, which supplies history, diff review, and the prediction seal for free. What replaces each of those properties, and what is the merge story for concurrent edits to one record?
2. **Identity provider integration.** SSO against the customer's IdP, local accounts, or both; and how reviewer independence (I-3) maps onto directory identities.
3. **Model API governance and cost.** Which providers, how prompts are pinned and audited, how outputs are logged for the correction flag telemetry, what the cost controls are, and how the air gapped deployment degrades (B-27).
4. **Facilitated sessions and multi user editing.** Does a live session become a shared editing surface, and if so how do the session file semantics (capture, readback, apply as a reviewed change set) survive the move?
5. **Migration of the existing records.** Concretely how the YAML library, with its comments and teaching template, lands in the new store without information loss (B-5), and whether the YAML remains an export format afterward.

## 11. Appendix

### 11.1 Artifact inventory at commit 2711e4f

| Artifact | Location | Role |
|---|---|---|
| Scenario records (21; 4 published) | `scenarios/*.yaml` | The library. `_TEMPLATE.yaml` is the teaching template |
| Use case records (12) | `use-cases/*.yaml` | Operational use cases |
| Incident records (6) | `incidents/*.yaml` | Cited real world incidents |
| Schemas (5) | `schema/*.schema.json` | Scenario, use case, test spec, prediction, run record |
| Framework baseline | `frameworks/baseline-2026.07.yaml` | The pin. Owner UNASSIGNED |
| Pinned artifacts | `frameworks/pinned/` | Vendored framework data with checksums (to be populated) |
| Org overlays | `coverage/<org>/*.yaml` | Per-org coverage assessments |
| Validator | `tools/validate.py` | Schema plus house rules; home of `derive_coverage()` |
| Rollup | `tools/coverage.py` | Coverage, exposure, maturity, snapshots |
| Viewer build | `tools/build_viewer.py` | Emits `liszt-viewer.html` and `liszt-data.json` (the integration seam, `data_version: 1`). Ten tabs: Scenarios, Coverage, Use cases, Frameworks, Reports, Bring in a scenario, Scenario management, Documentation, New scenarios beyond AI (parked mockup), Session |
| Session apply | `tools/apply_session.py` | Applies exported session files, comment preserving, human reviewed |
| Spec emitter | `tools/emit_testspec.py` | Readiness gate plus spec and prediction emission |
| Run scorer | `tools/score_run.py` | Digest check, confusion matrix, scorecard, proposals |
| Specs and runs | `specs/ST-021-...`, `runs/RUN-021-...` | The worked testing example (hand authored runs) |
| Reference walkthrough | `reference/021-worked-example/` | Scenario 021 carried gate by gate, mistakes intact |
| Docs | `docs/00` through `docs/09`, plus `docs/12` | The discipline; `docs/12-agent-testing.md` covers the test loop |

### 11.2 Glossary

| Term | Meaning |
|---|---|
| Attack path | The ordered chain of 3 to 6 steps, one adversary move each, hard ceiling 6 |
| Evidence row | One `telemetry` entry answering one step: signal, where emitted, exact source, scores, derived coverage, owner, evidence, ticket |
| Have / Collectable / Blind | Derived coverage: wired to detection / logged but nothing alerts / nothing produces the signal. Unscored rows have no value at all |
| DeTT&CT scores | Visibility 0 to 4; detection -1 to 5 (0 is forensics only, hence Collectable); five quality dimensions 0 to 5 |
| Coverage, exposure, maturity | The three metric families: engineering, risk, and program views, never composited |
| Baseline | The pinned framework version tuple every mapping speaks; currently 2026.07 |
| Editorial mapping | A cross-framework linkage that is the program's judgment, labeled as such; almost every mapping is |
| Org overlay | A per-organization coverage assessment overriding evidence rows without touching the shared record |
| OpenSpec | The generated, payload free, engine agnostic test specification bound to techniques by id |
| Sealed prediction | The falsifiable claims committed before a run, digest bound, refused by the scorer if moved |
| Pipeline mode | mirrored, scratch, or none; decides which claims a run may score |
| Autonomy rungs | lab-only (enabled), production-observe, production-active (specified, off); the executor refuses above the enabled rung |
| Optimism index | Mean predicted coverage rank minus mean observed rank; positive means the map claims more than exists |
| Session file | The exported capture from a facilitated session, applied by a human with a diff |
| Correction flags | The importer's record of what it had to fix in a converted draft; telemetry on prompt quality |
