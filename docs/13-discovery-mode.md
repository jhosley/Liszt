# 13. Discovery mode: establishing the evidence map

**Audience:** the analyst deciding how to get a first score onto a record, and the developer building the discovery path.
**Authority:** `schema/discovery-run.schema.json` defines the record. `tools/emit_discovery.py`, `tools/discovery_to_session.py` and the `score_provenance` field in `schema/scenario.schema.json` are the implementation. If this document disagrees with any of them, they win and this document is wrong; file it.

**Status:** prototype, same rung as the testing path. The `lab-only` rung is the only one enabled. Nothing executes a run yet; the worked example in `runs/` is authored by hand and says so.

---

## 1. What this is for, stated plainly

Document 12 describes a loop that checks claims. It needs a claim to check: a published record, every row scored, a source named on every Have. Then it seals a prediction, runs the scenario, and scores the difference. That loop is the product, and it is honest because the prediction is frozen before the answer is known.

The loop has a starting problem. Every record in the library is a draft with no scores, and the validator will not let an unscored record be published. Nothing can be predicted, so nothing can be tested, so nothing gets scored. The way out until now was a room: people who own the systems, in session mode, answering the two questions per row. That remains the right way when the people are available.

Discovery mode is the other way. It asks an agent to run the scenario against an unscored record, look everywhere, and come back with what it saw, where, from which layer, and what numbers it would propose. Then a person accepts or rejects each proposal. The agent establishes a first claim; it does not get to make one.

Two things follow, and they are the whole design.

- **There is no prediction and no scorecard.** Nothing was claimed, so nothing is sealed and nothing is confirmed or overestimated. A discovery run that emitted an empty `prediction.yaml` would manufacture the appearance of a claim nobody made. The emitter does not write one, and the run record schema has no field for a verdict.
- **A proposal is marked as one, forever, until a person changes that.** Every score that reaches a record through this path carries `score_provenance: agent-proposed`. It is listed in the coverage rollup and counted in no average. Publication refuses it. Accepting it is an edit a person makes, in a commit, to `human-session`.

## 2. Which door

| You have | Use | Because |
|---|---|---|
| A published record, scores on every row | **Scoring path**, `./liszt emit` (document 12) | There is a claim to falsify. Seal it and test it. |
| A draft with no scores, and the system owners in a room | **Session mode** in the viewer, then `./liszt session` | People who know the estate answer faster and better than a lab. |
| A draft with no scores, and no room | **Discovery mode**, `./liszt discover` | Something has to produce a first number, and this produces one a person can then stand behind or reject. |
| A record where you dispute an existing score | **Scoring path** | Discovery proposes first numbers. It does not argue with a measurement; the bridge refuses a row a person has scored. |

The two emitters are separate programs on purpose. `emit_testspec.readiness()` is imported by the viewer as the single mechanical gate for the scoring path, and a discovery flag inside it would be a flag inside the viewer's truth. Discovery is a second door, not a wider one.

## 3. The flow

```
unscored scenario record (draft or in-review)
      |
      |  (a) ./liszt discover NNN --check          mechanical gate, write nothing
      |      readiness prompt in docs/12 section 3b  the judgment half, a person's call
      v
      |  (b) ./liszt discover NNN                  specs/DISC-NNN-slug/discovery.yaml + .md
      |                                            no prediction.yaml, deliberately
      v
   run it (lab-only)
      |
      |  (c) runs/DISC-NNN-YYYY-MM-DD-NN.yaml       the agent's answer, one file per run, immutable
      |      ./liszt validate                       schema plus consistency between observed and proposed
      v
   a person reads the proposals
      |
      |  (d) python3 tools/discovery_to_session.py runs/DISC-... --accepted-by "Name" [--steps 2,4]
      |                                            a session file, nothing applied
      v
      |  (e) ./liszt session runs/DISC-....session.json --dry-run, then without
      |                                            scores land with score_provenance: agent-proposed
      v
   later, having looked at the evidence, a person edits score_provenance to human-session
```

Step (e) uses `tools/apply_session.py`, the only tool that writes into a scenario record. The bridge does not touch records and does not call the writer for you; its last line is the command to run next.

## 4. The gate

`emit_discovery.discovery_readiness()` refuses:

- `status: published`. A published record is scored; that is the scoring path.
- `status: retired`. Nothing left to learn.
- A step with no evidence row. A proposal needs a row to land in; add the row, even empty.
- No `framework_mapping.baseline`.
- `classification.mode: failure`. No adversary to emulate.
- `classification.evidence: doomsday`. Emulating one is a separate decision.

It does not require scores and does not check the coverage tag. Producing scores is what it is for. A row that already carries a person's scores is excluded from the procedure and listed under `excluded_steps` as `already-scored`, so the exclusion is visible.

`./liszt emit NNN --check` continues to return every blocker it returned before. The scoring gate did not move.

## 5. What the agent reports, per step

The run record mirrors `run-record.schema.json` where the concepts are shared, and the `observed` vocabulary is identical: `detected`, `logged-only`, `absent`, `unscoreable`. New in discovery:

- **`observed_layer`**: one or two values from the scenario schema's `aiLayer` enum, exact strings, middle dots included. Agent behavior and MCP servers are `L3 · Orchestration & Agent`. Model output is `L2 · Model`. Retrieval and data stores are `L1 · Data`. App surface is `L4 · Application`. Hosts, cloud and network are `L0 · Infrastructure`. Two values when the artifact sits on a seam, for example an app log line carrying the model's output.
- **`out_of_estate`**: true when the step reached a third party and the lab used a stand-in. A third party is not a layer of ours, so it is a flag and not a sixth value. The validator refuses to run if the discovery schema's copy of the enum drifts from the scenario schema's.
- **`proposed_visibility`**, **`proposed_detection`**, **`proposal_rationale`**: the numbers and the reasoning a reviewer can disagree with. Required whenever the step executed and the observation is not `unscoreable`. Forbidden otherwise.

The validator holds the observation and the proposal to the same story. `absent` with visibility above 0, `logged-only` with detection at or above 1, `detected` with detection below 1, a proposal on an unexecuted or unscoreable step, or a detection proposal above -1 from a scratch pipeline: each is an error, not a warning, because a record that says two things is not a judgment call.

The step-level `layer` in `attack_path` stays free text, and `LAYER_HINTS` in the scoring emitter stays as it is. They answer a different question (which lab component to stand up), and the `External` value the emitter derives from them drives the `requires_human` safety flag on third-party steps, which the enum cannot express.

## 6. Provenance in the rollup

`tools/coverage.py` treats an `agent-proposed` row as it treats an unscored one: absent from every ratio. A `prop` column shows how many such rows each scenario carries, and a `PROPOSED` line names them, so the existence of proposals is visible and their numbers are not. `--gaming` flags a published record carrying any. The validator errors on the same condition, so `./liszt publishable` cannot pass with a proposal on board.

In a scratch or no-collection pipeline the bridge writes scores and notes only. The observed source is the lab's stand-in, not the estate's system, and overwriting a human statement about our systems with a machine statement about a lab is the failure this whole path is built to avoid. In a mirrored pipeline the source and the artifact pointers are carried, because they are the estate's.

## 7. The worked example

`runs/DISC-021-2026-09-03-01.yaml` is invented and says so in its first line. Read it beside `runs/RUN-021-2026-08-05-02.yaml`: same lab shape, same scenario, opposite question. The scratch-lab scored run checked a prediction. This one had none and proposes first numbers, every detection proposal at -1 because the lab carried no detection content. Step 6 did not execute; the stop condition fired, and the record carries no proposal for it. Step 3 turned up a drift between the record's row 3 and its step 3, which is what a discovery run is for.

The round trip is the acceptance test:

```
./liszt validate runs/DISC-021-2026-09-03-01.yaml
python3 tools/discovery_to_session.py runs/DISC-021-2026-09-03-01.yaml --accepted-by "Name"
./liszt session runs/DISC-021-2026-09-03-01.session.json --dry-run
```

## 8. What is deliberately not here

- **A runner.** Same gap as document 12. The spec is engine agnostic and nothing binds it yet.
- **Auto-acceptance.** Nothing writes itself. The bridge needs a name on `--accepted-by`, and the number still says `agent-proposed` afterwards.
- **A second layer vocabulary.** The five values are the vocabulary. MCP is L3, as scenario 014 already records.
- **A discovery scorecard.** `confirmed` and `overestimate` are defined against a prediction. Discovery has none, so the words do not apply, and the schema has no field to put them in.
