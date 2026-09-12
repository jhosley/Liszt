# Liszt data model: the entity list

**Status:** for confirmation, one line per entity, nothing expanded yet. This is step 2 of
the build sequence. Every line should be one you can say back in your own words. Mark
each line keep, cut, or reword. Nothing below gets attributes, keys or a diagram until
this list is agreed.

**Where each line comes from:** the schemas under `schema/`, the records they govern, and
the tools that derive from them, on branch `data-model` as of 2026-09-11.

**The pattern every family follows:** a person writes a record, a tool derives something
from it, and the derived thing is never hand edited.

---

## Family 1. Reference: vocabularies that are pinned or controlled

Small tables that change rarely and on purpose. Everything else points at them.

| # | Entity | One line |
|---|---|---|
| 1 | Framework | One external body of knowledge: ATT&CK, ATLAS, OWASP LLM Top 10, OWASP Agentic Top 10, DeTT&CT. Each has its own release rhythm. |
| 2 | Framework Baseline | A named snapshot of all five frameworks at one moment, such as 2026.07. Has an owner, a status of current or superseded, and a list of what broke since the last one. Never deleted. |
| 3 | Pinned Artifact | The exact file a baseline froze for one framework, with its checksum. The proof behind the version number. |
| 4 | Technique Reference | One identifier in one framework at one baseline, with its name and whether it is current, deprecated, or revoked and by what. Includes ATT&CK T ids, ATLAS AML.T ids, and the OWASP slots. |
| 5 | Tactic | An ATT&CK or ATLAS tactic identifier at one baseline. Derived onto a scenario from its techniques, never chosen by hand. |
| 6 | Data Component | An ATT&CK DC identifier at one baseline, naming a kind of evidence. The old DS data sources are retired and rejected. |
| 7 | Mitigation | An ATLAS mitigation identifier at one baseline. Indexed today, cited by no record yet. |
| 8 | AI Infrastructure Layer | The five canonical strings, L0 Infrastructure through L4 Application. Where an attack achieves its objective. |
| 9 | Layer Component | A second, twelve value vocabulary for where a scenario mainly operates, such as Data, Model, Agent, or a pair like App / Model. Drives the index slide. |
| 10 | Step Seam Tag | A short free text tag on each attack step saying where the move operates, such as Host / net. Capped at 18 characters. Deliberately not a controlled list. |
| 11 | Scoring Scale | The DeTT&CT scales every row is scored on: visibility 0 to 4, detection minus 1 to 5, five quality dimensions 0 to 5. Pinned in the baseline so a scale change is a baseline event. |
| 12 | Organization | The estate a coverage assessment belongs to. Today just a directory name under coverage/. |

## Family 2. Authored: written by people

The records a person stands behind. These are what the contractor prices.

| # | Entity | One line |
|---|---|---|
| 13 | Scenario | The unit of the library. One attack or failure story with a title, a plain language summary, a classification, a priority with reasons, and a status that moves draft, in review, published, retired. |
| 14 | Attack Step | One ordered adversary move in a scenario, three to six per scenario. Has a seam tag, one line of text, its own framework mappings, and optionally a note that a control held. The number is its position, not its identity. |
| 15 | Evidence Row | What one step would make observable: the signal, the category of system that emits it, the data components, and what you would alert on. One per step, always. Shared across every organization. The field is still called telemetry. |
| 16 | Control Row | An extra evidence row for a standing condition rather than a move, such as a signature check at import. Has no step and is left out of every coverage number. |
| 17 | Coverage Assessment | One organization's answer for one evidence row: the two scores, the quality dimensions, the exact source system, the owner, the evidence, the ticket. The scenario's own values are the reference organization's assessment and sit here like everyone else's. |
| 18 | Assessment Header | Who assessed a scenario for an organization and when. The cover sheet of a set of coverage assessments. Today the top of an overlay file. |
| 19 | Hardening Action | A countermeasure, which steps it breaks, its leverage, its owner, optionally a ticket. Includes controls that held in the source incident. |
| 20 | Incident | A real world event written once and cited by every scenario that draws on it. What happened, when, who said so. |
| 21 | Contested Claim | A point two parties disagree about inside an incident, holding each party's words and a status. Recorded, never resolved by the analyst. |
| 22 | Source Citation | A URL with a tier of 0 first party, 1 secondary, 2 press, a title, and a note. One shape, three parents: scenario provenance, use case sources, incident references. |
| 23 | Provenance | Who authored a record, who reviewed it, the dates, and whether the data is illustrative. The reviewer must differ from the author before publication. |
| 24 | Use Case | A record of one decision: what triggers it, what evidence it pulls in, how the evidence is delivered, what it produces, who receives it, and how much it may do on its own. Has both an engineering phase and an operating status. |
| 25 | Use Case Coverage | The join from a use case to the scenario steps whose evidence rows it actually reads. Both ends are checked. |
| 26 | Composed Signal | One piece of evidence a use case pulls once its trigger fires, with its role of enrichment, corroboration, or scoping. The trigger itself is the same shape with no role. |
| 27 | Promotion | The authorization to run above the lowest rung: measured evidence, blast radius, reversibility, a named approver, a review loop, an off switch. One shape for both ladders, the use case ladder and the test spec ladder, differing only in what counts as evidence. |
| 28 | Test Spec | The instruction set for testing one scenario at one baseline, generated from the scenario and carrying a digest of it. Never hand edited, regenerated instead. |
| 29 | Authorization | The safety envelope on a test spec: which rung, which targets, the time box, the egress rule, the stop conditions, the prohibitions, whether teardown is required. |
| 30 | Procedure Step | One step of a test spec: the intent, the techniques to emulate, the expected artifacts, where to look, which claims can be scored here, and the safety flags. No payloads. |
| 31 | Excluded Step | A step deliberately not tested, with a reason and a class such as unsafe or third party. |
| 32 | Environment Definition | A versioned description of the infrastructure a run executes against: its lifetime, its telemetry pipeline mode, its targets, its components, how teardown is proven. Whether it is a disposable build or the estate is not encoded. A run cites one by id and version. Any change a result could depend on is a new version. |
| 33 | Target | A named thing a run may act on, belonging to an environment. A spec's allowlist is drawn from these. |
| 34 | Environment Component | One thing an environment reproduces: a target, an observation source, or a stand-in for the outside world, with how faithful it is and the product version deployed. |
| 35 | Prediction | What we claim a run will find, sealed before the run and bound to the spec by digest. Scoped to the reference assessment or to one organization. |
| 36 | Prediction Row | Per step: the predicted coverage and scores, plus the claim broken into three separately testable parts, signal present, source named, detection fires, each with the venue that can test it. |

## Family 3. Observed: what a run actually saw

Written by a person or an agent after execution, before anyone reads the prediction.

| # | Entity | One line |
|---|---|---|
| 37 | Run Record | One execution of a test spec: who ran it, in which environment, with what agent, bound to the prediction by digest, and when imported from the platform, which orchestrator run and traces it came from. Immutable once committed. A correction is a new run. |
| 38 | Observation | Per step of a run: whether it executed, what was observed, in which system it actually turned up, the latency, the artifacts with pointers into the tracing platform, and any surprises. |
| 39 | Stop Condition Triggered | A guardrail that fired during a run, at which step. A successful guardrail, not a failed run. |
| 40 | Agent Build | The adapter, build, and model that drove a run. Part of the experimental setup, because changing the runner can move a result. |
| 41 | Discovery Run | An agent's exploration of an unscored scenario. Same shape as a run where the concepts overlap, but no prediction and no scorecard, because nothing was predicted. |
| 42 | Discovery Observation | Per step of a discovery run: what was seen, in which layers, plus the scores the agent proposes and its reasoning. A proposal a person accepts or rejects. |

## Family 4. Computed: derived by a tool, never written by hand

| # | Entity | One line |
|---|---|---|
| 43 | Coverage Tag | Have, Collectable, or Blind, from the two scores by one rule. Stored as a cache, recomputed on every check, an error on mismatch. |
| 44 | Framework Roll-up | The union of a scenario's step level mappings. Enforced today, a candidate to become purely derived. |
| 45 | Scorecard | The comparison of a run against its prediction: a verdict per row, the totals, the rates by claim class and by layer, the caveats. Written into the run file today, its own thing in the model. |
| 46 | Proposed Rescore | What a run says an evidence row got wrong, as a proposal with a reason. Applied deliberately by a person citing the run. |
| 47 | Score Provenance | On each coverage assessment, whether a person or an agent produced the scores. Agent proposed rows are listed and counted nowhere. |
| 48 | Snapshot | The immutable record of one metrics run: the full framework version tuple with artifact hashes, the library state, the three metric families, and the ledgers of what was added, retired, or rescored. Kept forever. A correction is a new snapshot that says which one it supersedes. |
| 49 | Rollup Metrics | Coverage, exposure, and maturity for a library at one moment, each with its completeness companion. Reported side by side, never combined. An unscored row is absent, not zero. |
| 50 | Readiness Verdict | Per scenario, whether a test spec could be emitted today and, if not, the list of reasons. Computed at build time. |

---

## Family 5. Interfaces: documents that cross a boundary into Liszt

Not stored as state, but the contractor has to build the endpoint that accepts each one, so they are named here.

| # | Entity | One line |
|---|---|---|
| 51 | Agent Run Import | The JSON a single purpose sub-agent hands over after running one scenario on the agentic platform: who produced it, where its traces live, the environment, and per step what was observed, with trace pointers, and in discovery mode the proposed scores. The importer validates it, checks the digests, and writes a run record. Nothing else. |
| 52 | Session File | What the viewer exports during a scoring session with system owners: per row score changes, sources, owners, tickets. A tool applies it to records while a person reads the diff. It carries changes, not state. |

## Not entities, but worth naming so the contractor does not model them

- **The viewer data file.** A read only projection of the library with the computed fields already applied. The closest thing to the API the new application needs.
- **The deck, the published pages, the manual.** Printed from the records. Deleted and rebuilt at will.

## Where the count went up from the brief

The brief estimated about 35. This list has 52 because the verification pass found entities the brief inferred as one: the evidence row splits into a shared row and a per organization assessment with its own header; the environment brought its targets and components; discovery mode brought a run and an observation; the framework index brought tactics, mitigations, and pinned artifacts; three computed views (score provenance, rollup metrics, readiness) were being produced without a name; and the two interface documents were named so the import and session endpoints are in scope.
