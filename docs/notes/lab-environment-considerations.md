# Notes: what the testing work implies about the lab environment

**Status:** working notes, not a design. Collected while building the spec emitter, the
prediction format and the scorer, so that the environment work is derived from real
constraints rather than guessed at. Nothing here has been decided.

**Audience:** whoever picks up the contained cloud environment build.

Each note says what forced it, so the reasoning survives even if the conclusion changes.

---

## 1. The pipeline decides what the lab is worth

**Forced by:** the `scoreable` computation in `emit_testspec.py`, and the refusal in `score_run.py`.

This is the finding that should shape the whole build. A lab that reproduces the target
but not the logging path can only prove that an artifact *can* exist. Whether *we* would
see it is a claim about our collectors, our parsers and our detection content, and a lab
that does not contain them cannot test it.

The worked example makes the size of this concrete. The same six observations score 5 of
6 rows in a mirrored lab and 1 of 6 in a scratch lab. Everything else about the two runs
is identical.

**So the first design question is not compute, it is telemetry.** Three options, in
increasing cost and increasing worth:

| Option | What it buys | What it costs |
|---|---|---|
| Scratch collection in the lab | Falsifies Blind rows, finds unrecorded sources, tests source attribution loosely | Cheap. No detection testing at all. |
| Ship lab telemetry to the real platform, into a quarantined index, with production detection content replayed against it | Everything, including detection claims | Needs a data path out of the lab, an index nobody confuses with production, and a way to run real rules against lab data without firing real pages |
| Run the agent in production under `production-observe` | Tests the real pipeline exactly, with no fidelity gap | Needs the approval path that is deliberately not enabled yet |

**Note for the build:** the middle option is probably the target, and its hard part is not
the cluster. It is the quarantined index plus rule replay, and that lands on the detection
platform team rather than on whoever builds the Kubernetes side. Worth scoping early,
because it is the long pole and it is easy to discover late.

---

## 2. Ephemeral by default, and teardown has to be provable

**Forced by:** `authorization.teardown_required`, and `environment.teardown_confirmed` in
the run record being a scored operational finding rather than a checkbox.

Every target in the worked example is `lab-ephemeral`. The run record asserts teardown,
and an unconfirmed teardown is a finding in its own right. That means the environment
needs to *produce evidence* that it was destroyed, not just be destroyed. A namespace
delete that returns success is not evidence; a subsequent query that returns nothing is.

**Note for the build:** whatever spins the environment up should emit a teardown receipt
the run record can cite. Consider making the teardown assertion a real artifact reference
rather than a boolean, in a later schema version.

---

## 3. Egress deny-all breaks the steps that need a network, and that is correct

**Forced by:** step 6 of the worked example, which could not be executed.

The C2 and exfiltration step needs to reach public web services. The spec sets
`egress: deny-all`, so the step did not run, and the run record says so rather than
inventing a result. That is the guardrail working. It is also a standing gap: the same
thing will happen on every scenario whose late steps involve exfiltration, and those are
common.

**So the lab needs internal stand-ins for the external world.** A paste service, a file
drop, a request capture endpoint, a generic "external" host, all inside the boundary and
all resolving through lab DNS. The artifacts that matter (a proxy transaction to an
uncategorized destination, a DLP match on an outbound payload) are produced by the
*attempt*, not by the real destination existing.

**Note for the build:** treat the external stand-in set as a first class, reusable
component, not a per scenario improvisation. It will be needed by most records, and it is
what keeps `deny-all` from making late steps permanently untestable.

---

## 4. The observer needs query access, and losing it stops the run

**Forced by:** the stop condition "loss of the observer's ability to read the telemetry
pipeline," and by `latency_seconds` in the run record.

The run produces nothing of value the moment the observer cannot read the logs, which is
why that is a stop condition rather than an inconvenience. Latency is also recorded per
step, which means the environment has to preserve real ingestion timing. A batch that
flushes on teardown destroys the latency measurement even though the artifacts survive.

**Note for the build:** the environment's lifetime has to exceed the pipeline's ingestion
lag by a comfortable margin. Tearing down at the time box boundary can delete the target
before its own logs have landed. This is a scheduling detail that will bite once and then
be obvious.

---

## 5. Per layer replication cost is very uneven

**Forced by:** the `environment.components` block, which the emitter derives per step.

Rough shape from scenario 021, worth validating against two or three more records before
committing to a platform:

| Layer | Replication difficulty | Note |
|---|---|---|
| L0 Infrastructure | Low to medium | A cluster, nodes, a network. This is the part Kubernetes makes easy, and it is the part everyone thinks the problem is. |
| L1 Data | Medium | Needs a pipeline that actually processes an untrusted artifact, plus synthetic data with canaries. |
| L2 Model | Medium to high | Depends on whether the artifact comes from the model or from the gateway in front of it. A small local model is usually enough when the claim is about the gateway. |
| L3 Orchestration and agent | High | The agent platform and its run manifest are the least standard component in the estate, and step 1 of the worked example shows the record was already out of date about what it emits. |
| L4 Application | Low | Usually a stub. |
| External | Not replicated | See note 3. Stand-ins only. |

**Note for the build:** L3 is the expensive one, and it is also where the interesting
scenarios live. A lab that does L0 beautifully and stubs L3 will test the least
interesting half of the library.

---

## 6. Fidelity is a per component argument, and the cheap answer is usually wrong

**Forced by:** the `fidelity` enum, seeded conservatively by the emitter with a note
telling the author to confirm it by hand.

The failure mode is specific: setting an observation component to `equivalent` when the
*parser* is what produces the field being looked for. The artifact exists, the field does
not, and the run reports a source miss that is an artifact of the lab rather than a defect
in the record. That pollutes the calibration number in the worst way, because it looks
like a finding.

**Note for the build:** the environment should record its own component versions into the
run record automatically, so a fidelity gap shows up as a deviation instead of as a false
finding. Every deviation already becomes a caveat on the scorecard.

---

## 7. Determinism matters more than speed

**Forced by:** the whole premise. A calibration number needs runs to be comparable.

If the same spec produces different observations on Tuesday than on Monday because the
environment drifted, the score measures the lab rather than the library. Reproducibility
is worth more here than provisioning speed, which is an unusual priority for a lab and
worth stating before someone optimizes for the wrong thing.

**Note for the build:** version the environment definition and record its identifier in
the run. Two runs of the same spec against different environment versions are not
comparable, and the run record should make that visible the same way the framework
baseline does for scenarios.

---

## 8. Cost shape

**Forced by:** nothing in the code, but obvious from the flow.

Runs are short, bounded by the time box, and infrequent at first. The expensive thing is
not compute, it is the persistent parts: the telemetry path, the detection content replay,
and the external stand-in set. Those want to be long lived and shared; the targets want to
be ephemeral and disposable.

**Note for the build:** that split, a persistent thin platform plus ephemeral per run
targets, is probably the architecture. Worth testing that assumption early against the
quarantined index question in note 1, because if the telemetry path turns out to be
per run rather than shared, the cost shape inverts.

---

## Open questions for that phase

1. Where does the quarantined index live, and who owns running production detection
   content against it without firing production pages? This is the long pole.
2. Does the lab ship telemetry out, or does the detection content come in? Both work, and
   they have different security reviews.
3. Is one environment definition per scenario, or a small set of archetypes that most
   scenarios map onto? Archetypes are cheaper and less faithful, and the tradeoff should
   be made deliberately rather than by drift.
4. What is the approval path for `production-observe`, and who signs it? Until that exists,
   detection claims can only be tested in a mirrored lab.
5. Should the environment definition become a real record type with a schema, the way the
   spec and the run did? It carries the same kind of weight, and note 7 argues it needs a
   version identifier that runs can cite.
