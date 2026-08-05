# 12. Agent testing: proving the evidence map

**Audience:** the developers building the testing path, and the analyst who runs the first test.
**Authority:** `schema/test-spec.schema.json`, `schema/prediction.schema.json` and `schema/run-record.schema.json` define the records. `tools/emit_testspec.py` and `tools/score_run.py` are the implementation. If this document disagrees with any of them, they win and this document is wrong; file it.

**Status:** prototype. The `lab-only` rung is the only one enabled. The production rungs are fully specified and switched off.

---

## 1. What this is for, stated plainly

Liszt has been making falsifiable claims since the first scenario was scored, and has never checked one. Every evidence row says something like this:

> Step 2 emits egress from a sandboxed workload, it lands in the Palo Alto NGFW traffic logs at `index=net_egress`, and `NET-EGRESS-ANOM-07` fires on it.

That is a prediction with three separable claims in it, and a run can settle all three. The testing agent is the instrument that goes and looks. It is not the product.

**The calibration loop is the product.** The question this phase answers is not "does the attack work." It is "is our map of what we would see actually right, and if it is wrong, is it wrong in a direction that should worry us." A program that reports coverage it does not have gets believed and then surprised, and there has been no way to detect that from inside the library. Now there is.

Three consequences follow, and they shape everything below.

- **The prediction is frozen before the run.** Otherwise hindsight quietly rewrites it and the calibration number measures nothing.
- **Which claims a run may score is decided by the environment, not by ambition.** A lab that does not carry the real detection pipeline cannot test a detection claim, however much anyone wants a number.
- **Nothing writes itself back into a record.** The scorer proposes; a human applies, with the run id as the backlog reference.

---

## 2. The flow

```
scenario record
      |
      |  (a) readiness validation, prompt driven, JSON back
      v
   ready?  ------ blocked ------> fix the record, or exclude the step, and say so
      |
      |  (b) python3 tools/emit_testspec.py NNN --sealed-by "Name"
      v
specs/ST-NNN-slug/
   spec.yaml         what the agent does, and what it may not do
   spec.md           the same, in the spec-driven agent convention
   prediction.yaml   what we claim it will find
      |
      |  (c) COMMIT prediction.yaml. The commit is the seal.
      |  (d) assign targets, approve, run
      v
runs/RUN-NNN-DATE-NN.yaml     observations, authored before reading the prediction
      |
      |  (e) python3 tools/score_run.py runs/RUN-...yaml --write
      v
scorecard + feedback  ->  proposed rescores, method findings, lab findings
```

Step (c) is not administrative. It is the step that makes the rest honest.

---

## 3. The readiness validation

Two halves, and both must pass. The mechanical half is recomputed by the emitter every time, so it cannot be skipped. The judgment half is a prompt: paste it into a context window with the scenario record, get JSON back, and import it the same way the intake journeys work.

### 3a. The mechanical half, enforced by the emitter

| Check | Why it blocks |
|---|---|
| `status: published` | A draft's scores are not a claim anyone has stood behind, so there is nothing to falsify. |
| Every attack path step has an attack-step evidence row | A step with no row predicts nothing. |
| Every row is scored | An unscored row is None, not Blind. It has no prediction in it. |
| Derived coverage matches the recorded tag | If these disagree the record is broken; run `./liszt validate` first. |
| Every Have and Collectable names a `source` | The observer would not know which system to look in, so the claim is not checkable. |
| The record declares a `framework_mapping.baseline` | The spec would not know which pinned vocabulary its technique ids speak. |
| `mode` is not `failure` | Failure scenarios have no adversary to emulate. They are tested by fault injection, which this spec does not cover. |
| `evidence` is not `doomsday` | These records exist to reason about an attack nobody has run. Emulating one is a different decision and needs its own approval. |

Run it alone with `python3 tools/emit_testspec.py NNN --check`.

### 3b. The judgment half, as a prompt

Paste the scenario record after this prompt. Bring the JSON back and store it under `readiness` in the spec.

```text
You are validating whether a mapped attack scenario is ready to be tested by an
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
```

A `blocked` verdict is a normal outcome, not a failure. Most scenarios in a young library are not testable yet, and knowing which ones and why is itself a finding.

---

## 4. The methodology

### 4a. What the agent does

The agent reproduces the mapped behavior, one step at a time, against a target from an explicit allowlist, and stops. It does not improvise, it does not pursue an objective, and it does not carry payloads.

- **It works from the procedure in the spec**, which is a bounded action set derived from the scenario step and its framework identifiers. Anything not in the procedure is a stop condition.
- **The actions are abstract, and the spec is engine agnostic.** A step says "reproduce this behavior using a published emulation of T1611," and an adapter resolves that to a concrete test from an emulation library at run time, by technique id. Specs outlive runners, and an abstract action set is also the only form that can be reviewed for safety before anyone picks a tool.
- **It records wall clock time for each action**, so the observer can measure artifact latency. A Have that arrives an hour late is a different control from one that arrives in ten seconds, and the DeTT&CT timeliness dimension has no way to learn that otherwise.
- **It is not the observer.** Whoever checks the logs records observations independently, and does it before opening the prediction.

The guardrails are not decoration. They are what would make a production rung approvable later, so they are load bearing from the first lab run.

| Guardrail | Rule |
|---|---|
| Target allowlist | Explicit, with no wildcard and no default. An empty list means the run refuses to start. |
| Autonomy rung | `lab-only`, `production-observe`, `production-active`. The same ladder the use case record uses, earned the same way, one rung at a time, with a promotion block carrying measured evidence, blast radius, reversibility, a named approver, a review loop and an off switch. |
| Time box | The agent stops when it expires, finished or not. An unfinished run is a data point; an unbounded run is an incident. |
| Egress | `deny-all` by default. An allowlist requires the destinations named and justified. |
| Stop conditions | Any address or account outside the allowlist, any credential resolving outside the lab, any action not in the procedure, time box expiry, or loss of the observer's ability to read telemetry. A triggered stop condition is a successful guardrail, not a failed run. |
| Teardown | Required and asserted on every ephemeral target. Unconfirmed teardown is an operational finding in its own right. |
| Prohibited, always | No exploit development or unpublished vulnerability research. No action against anything not in targets. No persistence surviving teardown. No movement of real data, synthetic canaries only. |

### 4b. What is being tested, by layer and component

The spec derives this from the record rather than from a wish list, so every requirement traces to a step that needs it. Two kinds of component come out, and confusing them is the usual cause of a lab that runs and proves nothing.

- **Execution components** are what a step acts on: the workload, the cluster, the data pipeline, the agent runtime. Needed for the step to happen at all.
- **Observation components** are the systems the evidence rows name. Needed for the result to mean anything about us.

Each carries a fidelity level, and this is the field to argue about:

| Fidelity | Meaning | When to insist |
|---|---|---|
| `exact` | Same product and version as production | The artifact depends on the product. Any observation component in a mirrored run. |
| `equivalent` | Any implementation of the same class | The artifact depends on the behavior, not the vendor. |
| `stub` | A stand-in that only has to accept the interaction | The component is a destination, not a subject. |

The emitter seeds these conservatively and says so. Setting an observation component to `equivalent` when the parser is what produces the field you are looking for is the cheapest way to get a wrong answer that looks right.

### 4c. What the lab must replicate

Everything in 4b, plus the one thing that decides what the run can settle.

**The telemetry pipeline is the whole game.** A lab that reproduces the target but not the logging path can tell you whether an artifact *can* exist. It cannot tell you whether *we* would see it. So the pipeline has a declared mode, and the mode decides which claims may be scored:

| Mode | What it means | What may be scored |
|---|---|---|
| `mirrored` | The lab ships to the same collectors, parsers and detection content as the estate being scored | Everything. Signal presence, source attribution, and whether the detection fires. |
| `scratch` | The lab collects with its own tooling | Signal presence and source attribution only. Detection claims are recorded unscoreable. |
| `none` | No collection | Nothing about our estate. Only that a technique executes. |

The consequence is worth saying out loud, because it sets expectations for the lab build: **in a scratch lab, only a Blind row can be fully scored.** Have and Collectable both make a claim about whether our detection fires, and a scratch lab does not contain our detection. So a cheap lab is a Blind hunting instrument. That is genuinely worth having, since a Blind row that turns out to emit something is free coverage the library did not know it had, and the worked example finds exactly that. It is not a detection test, and the scorer will not let it be reported as one.

### 4d. The results prediction

`prediction.yaml` is emitted alongside the spec, and it is a separate file so that committing it is a discrete, timestamped act. Git is the notary. The run record binds to it by sha256, and the scorer refuses to score if the digest has moved.

Each row decomposes the coverage tag into separately falsifiable claims, because they fail for different reasons and are testable in different places:

| Claim | Derived from | Testable in |
|---|---|---|
| `signal_present` | visibility >= 1 | any lab with collection |
| `source` | the row's `source` field | a lab containing that system |
| `detection_fires` | detection >= 1 | only where the real pipeline runs |

Every value is derived from the evidence row, never invented, so a wrong prediction is a wrong record rather than a wrong guess. That is the point: the record is what is on trial.

Two fields to fill by hand before sealing:

- **`confidence`** per row, optional, which turns the scorecard from a hit rate into a calibration curve.
- **`expectations.expected_surprises`**, which is a claim in its own right. Predicting zero surprises is usually wrong, and finding that out is cheap.

### 4e. The comparison, the score, and the feedback

Predicted coverage against observed outcome is a three by three matrix. Rank both (`Blind` 0, `Collectable` 1, `Have` 2 against `absent` 0, `logged-only` 1, `detected` 2) and the delta names the verdict.

| Predicted | Observed | Verdict | What it means |
|---|---|---|---|
| Have | detected | confirmed | The row is right. |
| Have | logged-only | **overestimate** | We thought we would catch it. We would only have recorded it. |
| Have | absent | **severe overestimate** | A control everyone believed in does not exist. |
| Collectable | logged-only | confirmed | |
| Collectable | absent | overestimate | |
| Collectable | detected | underestimate | Something alerts that the record does not credit. |
| Blind | absent | confirmed | A confirmed gap is a real result. |
| Blind | logged-only or detected | **underestimate** | Good news, and still a wrong map. |

Four numbers come out, and the second one matters most.

- **Exact match rate.** Confirmed over scored. How often the map was exactly right.
- **Optimism index.** Mean predicted rank minus mean observed rank. Positive means we systematically believe we see more than we do. This is more useful than the hit rate, because a program can be accurate on average and dangerous in one direction, and only this number shows it.
- **Source precision.** Of the artifacts that appeared, the share that appeared in the system the record named. Being right about visibility while naming the wrong system is a distinct defect: it sends an investigator to an empty index on the day it matters.
- **Surprise count.** Signals found that nobody predicted. The cheapest coverage in the program.

All of them are reported next to `scored`, for the same reason coverage is always reported next to completeness. A rate over two rows is a data point, not a trend, and the tool says so.

The feedback block turns the score into work, as **proposals only**:

- **Proposed rescores** name the row, the field in dispute, and the direction. Applying one is a deliberate act, and it must cite the run id as its `backlog_ref` so the change lands in the snapshot's `ids_rescored_this_period`. A coverage change driven by evidence should be visible as evidence, not as improvement.
- **Method findings** are what the run says about how we *predict*, rather than about the estate. This is the tuning signal: which layers and techniques we are worst at, and which recurring assumption keeps being wrong.
- **Lab findings** are requirements for the next environment.
- **New sources found** are systems that produced useful artifacts and are on no record.

---

## 5. The worked example

Scenario 021 is the only fully scored published record, so it is the example. Both runs carry **identical observations** and differ in one field, the pipeline mode, which is the fastest way to see how much the environment decides.

```bash
python3 tools/emit_testspec.py 021 --pipeline mirrored --sealed-by "Your Name"
python3 tools/score_run.py runs/RUN-021-2026-08-05-01.yaml   # mirrored
python3 tools/score_run.py runs/RUN-021-2026-08-05-02.yaml   # scratch, same observations
```

The mirrored run scores 5 of 6 rows: 2 confirmed, 2 overestimates, 1 underestimate, optimism index `+0.2`, source precision 67 percent. Read the three findings it produces, because they are the three shapes this loop exists to surface:

1. **Step 1 was scored Blind and something was emitting all along.** The eval harness started writing a run manifest with the safeguard profile after the row was scored. Nobody knew. That is free coverage and a rescore.
2. **Step 3 was right about visibility and wrong about the source.** The artifact exists, in the container runtime log rather than the application log the row names. An investigator following that row would have searched an empty index and concluded Blind.
3. **Step 5 was scored Collectable on an assumption that does not hold.** The row assumed the Kubernetes audit log captures a pod reading the instance metadata service. It does not, because that read never reaches the API server. The row conflated two different events.

None of those three is discoverable by reading the record more carefully. That is the argument for the whole phase.

The scratch run, on the same observations, scores 1 of 6. Every Have and Collectable goes unscoreable, because their truth depends on a detection pipeline the scratch lab does not have. It still finds the step 1 surprise.

---

## 6. What is deliberately not here

- **No runner.** The spec binds to an emulation library through an adapter at run time. Writing the adapter is the next build step, and the choice of library is deliberately reversible.
- **No production execution.** Only `lab-only` is enabled. `production-observe` is the rung that would let detection claims be tested against the real pipeline without a lab that mirrors it, and it needs an approval path defined before it is turned on.
- **No lab.** The environment requirements are emitted per spec, and the accumulated notes are in `docs/notes/lab-environment-considerations.md`, which is the input to that piece of work.
- **No automatic write back.** Every finding is a proposal. This is the same doctrine as the session file: the tool captures, a human commits.
