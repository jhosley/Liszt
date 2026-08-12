# 00 · Outcomes

**Audience:** anyone deciding whether this program is worth the cycles, and anyone about to change it.
**Authority:** this doc defines what "working" means. `schema/scenario.schema.json` and `tools/validate.py` define what "conforming" means. They are different things, and a record can conform without the program working.

**The rule this doc enforces on itself and on everything downstream: every outcome names the observable that would tell you it is true.** An outcome without an observable is a slogan, unfalsifiable, un-arguable, and therefore useless for deciding what to cut when time is short. If you add an outcome to this program, you owe it an observable in the same edit.

Four tiers, narrowest to widest. They compound: the aggregate outcome is impossible if the per-scenario outcome is not being hit, and the portability outcome is impossible if the capability outcome depends on one person.

---

## 1 · Per-scenario outcome

**After one walkthrough, the team can answer five questions about that scenario:**

| # | Question | Where the answer lives |
|---|----------|------------------------|
| 1 | What is the path? | `attack_path[]`, 3 to 6 ordered steps, each <=125 rendered chars |
| 2 | Where would we see each step? | `telemetry[]`, one `attack-step` row per step, `signal` + `emitted_at` |
| 3 | Where are we blind? | `telemetry[].coverage` = `Blind`, derived from `telemetry[].dettect`, not asserted |
| 4 | What is the single highest-leverage fix? | `hardening[]` with `leverage: high` and a `breaks_step` that resolves |
| 5 | Does that fix have an owner? | `hardening[].owner`, and `telemetry[].owner` on every Blind/Collectable row |

Question 5 is the one that gets dropped, and dropping it is what turns the exercise into theater. The schema says it directly: *a Blind row with no owner is an orphan and will never be fixed.*

**Observable.** Someone who was not in the room reads the record and reconstructs the reasoning without asking the author anything. Not "understands the scenario", *reconstructs the reasoning*, including why a disputed framework ID was resolved the way it was and which control held.

**Why this and not the nearby tempting one.** The tempting outcome is "the team understands the attack path." Understanding is in people's heads, it decays, and it is unobservable, you cannot tell a room that understood from a room that nodded. Reconstructability is a property of the artifact, which persists and can be tested by handing it to a stranger.

**What it explicitly does not claim.** Not that the path is complete, not that the fix will be built, not that the coverage assessment is correct. It claims the record is *self-contained and falsifiable*, that a reader can find the load-bearing judgment and disagree with it precisely.

**Cheap check.** Hand a published record to someone outside the working group. Ask for the five answers and for one thing in it they would dispute. If they have to ask the author a question to get any of the five, the record failed. If they cannot name a disputable claim, the record is probably hedged into uselessness, `mapping_notes` exists to name at least one.

---

## 2 · Capability outcome

**Any competent engineer, handed a scenario they have never seen, produces a defensible attack path and telemetry map to the same standard, without the program lead in the loop.**

**Observable, the calibration exercise.** Two analysts independently work the same scenario from the same source bundle and land in substantially the same place. Substantially the same means:

| Dimension | Agreement bar |
|-----------|---------------|
| Attack path | Same number of steps +/-1; the same mechanism at each step, allowing for different wording |
| Framework mapping | ATT&CK/ATLAS ID sets overlap; every non-overlapping ID is one the other analyst can see the argument for |
| Telemetry rows | Same `signal` per step in substance; `coverage` tag identical on >=80% of rows |
| Disputes | Both flagged at least one disputable mapping, and the disputes are recognizably about the same ambiguity |

Divergence is the finding, not the failure. Two analysts diverging on the same row twice means the guidance for that row is underspecified, fix the guidance, not the analysts.

**Why this and not the nearby tempting one.** The tempting outcome is "the team is trained." Training is an input. It is measured by attendance, which is the purest vanity metric available. Independent reproduction is an output, and it is the only evidence that the method lives in the documents rather than in one person's judgment.

**What it explicitly does not claim.** Not that both analysts are right. Two analysts can converge on the same wrong answer, and a calibration exercise will not catch it, that is what independent review (`reviewed_by` != `authored_by`) and primary sources are for. Convergence proves the method is transmissible, not that it is correct.

**Cheap check.** Run one scenario twice, blind, once. Diff the two records field by field. The diff is the whole instrument. Do not average the two, pick one, and record what the other saw in `notes`.

---

## 3 · Aggregate outcome

**At any moment, with evidence, three questions have answers:**

| # | Question | The metric family that answers it |
|---|----------|-----------------------------------|
| 1 | Where are we blind in a way that matters? | **Exposure**. NOW-priority scenarios with Blind steps |
| 2 | What changed since last time? | **Deltas between snapshots**, with the framework version tuple attached so churn is separable from progress |
| 3 | What did we get for the instrumentation we paid for? | **Rows that moved Blind/Collectable → Have**, joined to the `backlog_ref` that paid for the move |

Question 3 is the one that justifies the program's existence to anyone holding a budget, and it is the one that is impossible to answer retrospectively if `backlog_ref` was not filled in at the time. Definitions and formulas: `docs/04-measurement.md`.

**Observable.** All three are answerable without a manual reading pass over the archive. The answer comes out of a computation over `scenarios/*.yaml` and `coverage/<org>/*.yaml`; nobody opens twenty files to assemble it. If producing the number requires a human to read records and tally, the outcome is not met regardless of how good the number is.

**Why this and not the nearby tempting one.** The tempting outcome is a coverage dashboard. A dashboard is a rendering; it can be built over data too thin to support it, and it is most persuasive exactly when it is least earned. The outcome here is that the *underlying records* carry enough structure, derived coverage, owners, evidence, backlog refs, a pinned baseline, that any rendering over them is defensible. The dashboard is then a build artifact, like the deck.

**What it explicitly does not claim.** Not that coverage is improving. Not that the blind spots are the important ones, priority is a human judgment recorded in `classification.priority` and `priority_rationale`, and the metric inherits that judgment rather than validating it. It claims only that the current state is *stated*, *attributable* and *comparable to last time*.

**Cheap check.** Ask for question 3 with the numbers. If the answer names an instrumentation ticket and the specific rows whose `coverage` changed after it landed, it holds. If the answer is a percentage with no ticket behind it, the loop is not closed and question 3 is being answered by narrative.

---

## 4 · Portability outcome

**A team arriving in month nine adopts this without renegotiating anything, and contributes output that aggregates with everyone else's.**

"Without renegotiating anything" means: no new schema, no local variant of the coverage tag, no per-team interpretation of what Blind means, no argument about which framework version to map against. Those are settled by `schema/scenario.schema.json`, `derive_coverage()` in `tools/validate.py`, and `frameworks/baseline-YYYY.MM.yaml` respectively, three files, all readable in an afternoon.

**Observable.** Their first scenario is usable without rework. Concretely: it passes `python tools/validate.py --strict` with zero errors and zero warnings at `status: published`, and its rows drop into the coverage, exposure and maturity computations with no translation step and no per-team exception in the code.

**Why this and not the nearby tempting one.** The tempting outcome is "the program is adopted across the organization." Adoption is a count of teams who said yes, which is negotiable, reversible and unrelated to whether anything usable came out. Aggregatable output is a property of the artifact and survives the departure of whoever negotiated the adoption.

**What it explicitly does not claim.** Not that the new team's assessment is comparable to yours in substance, coverage is per-org by construction (`coverage/<org>/<scenario-id>.yaml`), and an org that scores its own estate honestly will land somewhere different from yours for good reasons. Portability is about the *format and the derivation rule* being shared, not the numbers being equal. It also does not claim a team must publish its coverage to use the library; the overlay pattern exists precisely so they need not.

**Cheap check.** Give a team the schema, the reference record (`scenarios/021-*.yaml`), the baseline and the validator, and nothing else, no walkthrough, no onboarding call. Look at what comes back. Every question they had to ask is a defect in those four files; fix it there.

---

## 5 · What this program is not measuring

**Scenario count is a vanity metric.** It goes up on its own, it is trivially inflated by splitting one scenario into two, and it is uncorrelated with whether anyone can see an attack in progress. A library of forty scenarios with no `dettect` scores is worth less than a library of six with scores, owners and evidence. Do not report it as a headline; report it as library state on the snapshot, where it belongs (`docs/04-measurement.md` section  snapshot record).

**The real metric is tags flipping from `Blind` to `Have`, with evidence behind them.** That is: a `telemetry[]` row whose `dettect` scores changed such that `derive_coverage()` returns a better tag, where the new tag carries an `evidence` value that a third party can re-run, and where a `backlog_ref` names the work that caused the change. All three parts are load-bearing, a flip without evidence is a rescore, and a flip without a backlog ref is unattributable.

Also not measured, deliberately:

| Not measured | Why not |
|--------------|---------|
| Number of walkthroughs held | An input. Measures attendance. |
| Slides produced | The deck is a build artifact rendered from the record. Counting artifacts counts renders. |
| Framework IDs mapped | Rewards breadth of mapping, which R3 in `docs/03-framework-mapping.md` explicitly caps. More IDs is usually a worse-scoped scenario. |
| Percentage of scenarios "reviewed" without scores | Review with no `dettect` scores leaves `coverage` an opinion. `derive_coverage()` returns `None` and the row cannot count toward maturity. |
| Hardening items proposed | Proposals are free. `backlog_ref` on the row, and the row's tag later moving, is what is not free. |
| Time-to-record | Optimizing it produces records that fail the section 1 observable. |

**The failure mode this section exists to prevent:** a program that reports growth in everything that is easy to produce and silence on the one number that is hard to move.
