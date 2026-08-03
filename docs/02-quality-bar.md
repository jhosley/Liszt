# 02 · Quality Bar

**Audience:** the analyst deciding whether a record is finished, and the reviewer deciding whether it is publishable.
**Authority:** `tools/validate.py` is the machine-checkable bar; `schema/scenario.schema.json` is the structure; `docs/01-methodology.md` is the procedure that produces the record; `docs/03-framework-mapping.md` owns the mapping rules. If this doc disagrees with any of them, they win and this doc is wrong, file it.

This is the definition of done and the reviewer's instrument. Two audiences, one bar: **an analyst self-applies section 2 before handing over; a reviewer works section 3 and reports findings under section 4.**

The worked standard is `scenarios/021-agent-sandbox-escape-to-autonomous-intrusion.yaml`, with the judgment calls narrated in `reference/021-worked-example/README.md`.

---

## 1 · What review is for

**The reviewer's job is to find what is wrong, not to approve.** A review that returns "looks good" has produced no information. If you genuinely find nothing, write down what you checked and what would have changed your mind, that is a finding too, and it is the only evidence the review happened.

**Review is independent, and the validator enforces it.** `provenance.reviewed_by` must be present and must differ from `provenance.authored_by` before `status` may become `published`; the validator errors on both conditions. If you drafted the record, or the same pipeline that drafted it also called you to review it, say so and stop. **A drafting tool that both drafts and reviews has performed one pass, not two.**

**The validator passing is necessary and not sufficient.** It checks structure, arithmetic and length. The proof is in the library: the reference record, the one held up as what good looks like, passes with **zero errors and zero warnings**, and at one point still carried a `framework_mapping` written from memory that disagreed with its own worked analysis in `docs/03-framework-mapping.md` section 7. Some of that was machine-findable (R1 warns in both directions); the part that mattered was not, `T1606` was a well-formed, existing, non-deprecated ID, carried consistently on the step and in the roll-up, and wrong. Nothing caught that but a human re-deriving each ID against the pin.

### What a machine cannot catch

| Defect class | Why the validator is blind to it | What catches it |
|---|---|---|
| **A plausible but wrong attack path** | The structure is valid; the claim is about the world | Reading the Tier 0 sources and checking that step N+1 could actually follow from step N |
| **An optimistic score** | Any integer in range is legal, and `derive_coverage()` will faithfully derive `Have` from wrong inputs | Running the `evidence`. The calibration exercise (section 5) catches systematic optimism |
| **A mapping defensible in isolation but incoherent with the library** | The validator sees one file at a time | Comparing against how the same phenomenon was mapped in other records |
| **A detection opportunity nobody could implement** | It is a string of legal length | Asking the detection engineer who would have to build it |
| **Invented precision** | A sub-technique ID is well-formed whether or not the source supports it | Quoting the clause of `attack_path[].text` or the incident record that evidences each ID |
| **Evidence that does not resolve** | Presence is checked; truth is not | Running the query. A `Have` whose evidence returns nothing is downgraded |
| **A merged step hiding a `Blind` half** | One row per step is satisfied | Asking what the second mechanism's row would have said |
| **A hypothetical dressed as observed** | The banned-word check catches `did`, `was observed`, `has happened` in `scaled_up` only | Reading `one_liner` and the step text against `classification.evidence` and the sources |
| **A record that is honest, conforming and useless** | Every field is populated and legal | The five questions in `docs/00-outcomes.md` section 1, asked of someone who was not in the room |

**The one-line version:** the validator tells you the record is *conforming*. Only a second human tells you it is *true*.

---

## 2 · The definition of done

An analyst self-applies this before handing over. Every item is binary. If you cannot tick it, it is not done, say so in the handover rather than ticking it anyway.

### Scope and framing

- [ ] The scope line exists and was written before any source was opened.
- [ ] The record is one coherent chain, not a theme. Removing any step breaks it.
- [ ] `attack_path` is 3 to 6 steps and nothing was compressed to fit; if two mechanisms share a step, the merge is declared.
- [ ] `title` is 8 to 70 chars with no `Scenario NN · ` prefix; `slug` is stable; the filename is exactly `<id>-<slug>.yaml`.
- [ ] `primary_layer_component` names where the scenario *operates*, not where the damage lands.
- [ ] `classification.evidence` was chosen before research and matches what the sources support.
- [ ] `priority_rationale` has 2 to 4 items, each <=130 chars, **at least one about our own exposure**.
- [ ] `one_liner` is readable by a non-specialist executive: every acronym expanded, no framework IDs.

### Sources and facts

- [ ] Every source in `provenance.sources[]` was opened in full and carries a `note` saying why it earns its tier.
- [ ] At least one Tier 0 source, unless `evidence: doomsday`.
- [ ] The prior-art question is answered in writing, found with a reference, or not found with the searches recorded.
- [ ] Every count, date, version string and identifier has a CONFIRMED / CORRECTED / UNRESOLVED verdict behind it.
- [ ] Every negative finding is recorded as a finding, and its lookup was control-tested.
- [ ] Every conflict between parties is recorded with both claims, unresolved.

### The chain

- [ ] Every step names a mechanism, not a principle or a conclusion.
- [ ] Every rendered line satisfies `len(text) + len(layer) + 7 <= 125`, counted rather than estimated.
- [ ] `control_held` was considered at every step and set where the source says a control blocked or degraded it; the key is omitted, never `false`, where nothing was tested.

### Evidence (the telemetry map) and scoring

- [ ] One `attack-step` row per step, numbers matching, no gaps.
- [ ] Every `signal` is a noun phrase; every `detection_opportunity` is an outcome and survives the two-vendor test.
- [ ] No row's only detection opportunity is an atomic indicator against ephemeral infrastructure.
- [ ] Every row carries `dettect.visibility`, `dettect.detection` and all five `quality` dimensions, or is deliberately unscored and flagged as such.
- [ ] `coverage` on every row equals `derive_coverage()`; no tag was authored.
- [ ] Every `Have` carries `evidence` a third party could run without you.
- [ ] Every `Blind`/`Collectable` carries an `owner` who would accept the ticket, and a `backlog_ref` where the gap has been accepted.
- [ ] Every provisional score, owner or evidence artifact is marked provisional in `notes` with the confirming session named.
- [ ] Any escalation problem is written as a hardening item, not scored as a detection gap.

### Mapping and hardening

- [ ] Every step-level ID appears in the roll-up; every roll-up ID traces to at least one step.
- [ ] Every ID was looked up in the pinned artifact named by `framework_mapping.baseline`, not recalled.
- [ ] `mapping_confidence: editorial` unless every linkage is an ATLAS `attack-reference`.
- [ ] `mapping_notes` names at least one mapping a reasonable analyst would dispute, with the counter-position, plus every gap and every rejected candidate with its reason.
- [ ] Every `hardening[]` item's `breaks_step` resolves to an existing step; nothing generic survived.
- [ ] Any `control_held: true` appears as a hardening item.

### Hygiene and handover

- [ ] `python tools/validate.py <absolute path>` returns zero errors; every remaining warning has a written reason.
- [ ] `grep -n PLACEHOLDER` is clean; `id` is not `'000'`.
- [ ] `authored_by` is a human.
- [ ] `status: draft`; `reviewed_by` absent.
- [ ] `notes` carries the disagreements, the open questions and anything the next author needs. It is never rendered, use it.
- [ ] The handover block covers all seven items in `docs/01-methodology.md` Gate 7.

---

## 3 · The reviewer's checklist

Work it in this order, sources first, because a defect there invalidates everything downstream. Every item is a question with a stated pass condition. **V** = the validator also checks this, so a failure here means the author did not run it. **J** = judgment; the validator is blind.

Run the validator first, on an absolute path, and paste its output into the findings. Publication bar: **zero errors and zero warnings at `status: published`.**

### 3.1 · Sources and provenance

| | Question | Passes when |
|---|---|---|
| J | Does every Tier 0 source say what the record says it says? | You opened each one and the load-bearing claims are there, in those words |
| J | Is `evidence: seen-in-the-wild` backed by a Tier 0 source describing it happening to a real organization? | Yes. A vendor blog summarizing a researcher's demo is `seen-in-research` |
| J | Are the tiers honest? | No aggregator or derivative post is at Tier 0 or 1. Tier 2 is cited only to evidence that a claim is circulating |
| J | Was every source read in full? | The `note` on each source describes something only a full read reveals |
| J | Is the prior-art question answered? | Either a reference, or the searches that found nothing |
| J | Are counts, credits, version strings and dates the verified values? | Spot-check one at random against the primary. Batch CVE credits checked per row; branch, last-vulnerable and fixed build distinguished |
| J | Are contested facts left standing? | Both parties' claims present, `status: unresolved`, not smoothed into one narrative |
| V | Is `reviewed_by` present and different from `authored_by`? | Present at publication, and it is not you |
| V | Do all `incidents[]` slugs resolve to files in `incidents/`? | Every one. No invented slug clearing a warning |
| J | Is `authored_by` a human? | Yes. A tool name in that field is a finding: accountability does not transfer |
| J | Does `notes` show the review left a trace? | Disagreements and open questions are in the record, not in chat |

### 3.2 · Classification and framing

| | Question | Passes when |
|---|---|---|
| J | Does `primary_layer_component` name where the scenario operates? | Yes, and the alternative reading is wrong for a stated reason |
| J | Does at least one `priority_rationale` item name **our own exposure**? | Yes. Three lines about someone else is the single most common rejection |
| V | Are the rationale items <=130 chars, 2 to 4 of them? | Validator errors on length |
| J | Does the rationale actually support NOW/NEAR-TERM/BACKLOG, or was the priority inherited from a deck? | The rationale, the `Blind` rows and the backlog ticket point at the same thing |
| J | Can a non-specialist read `one_liner` without stopping? | Hand it to someone outside security. Unexpanded acronyms, framework IDs and jargon are findings |
| V/J | Does `scaled_up` assert anything as observed? | No. Always hypothetical, always about us, always at a scale we have not seen |
| V | Is a `doomsday` scenario marked `NOW`? | Only with an exposure line strong enough to carry it alone |

### 3.3 · The attack path

| | Question | Passes when |
|---|---|---|
| J | Does each step's `text` describe a **mechanism**? | No principles, no conclusions, no intent, no tool names |
| J | Do the steps chain? | Read backwards: each step consumes something the previous one produced. Nothing arrives from nowhere |
| J | Is any single step doing two distinct things? | Legitimate under the six-step ceiling, **only if declared** in `mapping_notes` or `notes` |
| J | Would the merged halves have different coverage answers? | If yes, the merge is hiding a `Blind` and the scenario should split |
| J | Six steps and still truncated? | Then it is too broad. Propose the split explicitly |
| J | Is `control_held` recorded where a control blocked or degraded a step? | Yes. **Its absence is a finding**, this is the most commonly omitted field in the schema |
| J | Was `false` used to mean "I did not check"? | It must not be. The key is omitted when nothing was tested |
| V | Is every rendered line <=125 (`len(text)+len(layer)+7`)? | Validator errors otherwise |
| V | Do steps run 1.N with no gaps? | Validator errors otherwise |

### 3.4 · Evidence

| | Question | Passes when |
|---|---|---|
| V | Is there one `attack-step` row per step, same numbers? | Every step answered, even if the answer is `Blind` |
| V | Are control rows tagged `kind: control` and numbered after the last attack step? | Yes, otherwise the validator reads them as rows pointing at steps that do not exist |
| J | Is each `signal` a noun phrase naming what is emitted? | Not a sentence, not a rule name, not a product |
| J | Is `emitted_at` something we own or could own? | No naming of products we do not have |
| J | Is `detection_opportunity` an **outcome** rather than a tool? | Two-vendor test: two different vendors' products could both satisfy it. Engineer test: a rule could be written from it without asking the author a question |
| J | Are behavioral and correlation detections preferred where the actor leaves no durable artifacts? | Sequence, ancestry, rate, first-seen, identity churn, not IPs, domains and hashes against paste sites and throwaway identities |
| J | Is an atomic indicator the only opportunity on a row? | Never. Atomic indicators belong only to durable, versioned artifacts |
| J | Is a detection failure being confused with an escalation failure? | A signal that fires and goes nowhere stays `Have`, with the routing problem as a hardening item. More log sources do not fix routing |
| V | Are `data_components` `DCxxxx`? | `DSxxxx` is a retired data source and errors |
| J | Do those components actually belong to the technique on that step? | Walked DET → AN → DC in the pinned bundle, not guessed from the name |
| V | Is there an `owner` on every `Blind`/`Collectable` row? | Yes, and **J**: it is a team that would accept the ticket, not merely the team that emits the data |
| J | Is there a `backlog_ref` on every accepted gap? | Yes. A gap with no ticket is a slide |

### 3.5 · Scoring

| | Question | Passes when |
|---|---|---|
| V | Does `coverage` equal `derive_coverage(dettect)` on every row? | Validator errors on mismatch. The tag is a cache, never an input |
| J | Are the **scores** defensible, not merely arithmetically consistent? | The visibility score matches what we actually collect, established with the data owner |
| J | Is `detection: 0` being used to mean "a bit of detection"? | It means forensics/context only, and derives `Collectable`. This is the cheapest way to inflate a coverage number |
| J | Any row with `visibility: 0` and `detection >= 1`? | That is a scoring error, not a coverage state |
| V | Are all rows scored on a published record? | Unscored is a warning on a draft and an error at publication. Unscored is not `Blind` |
| J | Was `visibility: 0` used to mean "nobody looked"? | Zero is a finding somebody established; absent `dettect` is the honest way to say nobody looked |
| V/J | Does every `Have` carry `evidence`? | Present (V) **and** it resolves: **open it, run it**. A `Have` whose query returns nothing is downgraded |
| J | Has the rule behind a `Have` ever fired on anything real? | If not, `detection: 1` at most, and the evidence says so |
| J | Are provisional scores marked as provisional? | Every unconfirmed score, owner and evidence artifact named in `notes` with the session that must confirm it |
| J | Are all five `quality` dimensions present and plausible? | Present is maturity gate M2; plausible is your call. A `Have` with `retention: 0` fires on data nobody can go back to |

### 3.6 · Framework mapping

Against `docs/03-framework-mapping.md`.

| | Question | Passes when |
|---|---|---|
| V | Does every step-level ID appear in the roll-up, and every roll-up ID on a step? | R1. Validator warns in both directions; OWASP IDs are the sole exception |
| J | For each ID, can you quote the clause that evidences it? | If not: too coarse, or invented precision. Drop to the parent or drop the ID |
| J | Are a sub-technique and its parent both recorded? | Never. R8, the parent is implied and recording both double-counts every downstream metric |
| J | Are OWASP IDs edition-qualified, and re-derived rather than translated? | `LLM03:2025`, `ASI01:2026`. A bare number inherited from an old deck must have been re-derived from the text |
| J | Are the counts inside the R3 ceilings? | At the ceiling is a signal the scenario is too broad, and you are entitled to push back and propose a split |
| J | Is `mapping_confidence` honest? | `editorial` if there is any OWASP ID or any ATLAS<->ATT&CK pairing not backed by an `attack-reference`. `authoritative` claimed anywhere else is a finding |
| V/J | Does `mapping_notes` exist and do its job? | Present (V) **and** it names at least one mapping **you** would dispute with the counter-position, plus every gap and every rejected candidate with its reason. "Mapped per standard practice" is a failed note |
| J | Was a genuine gap recorded, or a near-miss ID forced in to avoid an empty array? | An empty array is a finding, not an omission |
| J | Were IDs verified against the pin, or recalled? | The record says how they were checked. Absent that, treat every ID as unverified |
| J | Is this phenomenon mapped the same way it is mapped elsewhere in the library? | Consistency across records is the whole point of purpose (a) in `docs/03` section 1. Divergence is either a finding here or a defect in the other record |
| V | Is a `baseline` mixed within one record? | One baseline per record, always |

### 3.7 · Hardening

| | Question | Passes when |
|---|---|---|
| V | Does every item's `breaks_step` resolve to an existing step? | Validator errors otherwise |
| J | Does every item break a step at all? | An item that breaks no step is generic best practice and does not belong |
| J | Is the ranking against **this** chain or a generic maturity model? | Earliest break, outright break over degradation, more steps broken, then cost |
| J | Is the control that HELD recorded as a hardening item? | Yes, it is the only item in the list with demonstrated effect behind it |
| J | Do the items have owners, and tickets where the work is accepted? | Otherwise they are proposals, and proposals are free |
| V | Is `hardening[]` empty on a published record? | It must not be, a scenario with no remediation cannot feed a backlog, which is the point |

### 3.8 · Record hygiene

| | Question | Passes when |
|---|---|---|
| V | Zero errors and zero warnings at `status: published`? | Publication bar. A draft may carry warnings |
| J | `grep -n PLACEHOLDER` clean? | The validator flags `TBD`, `TODO`, `XXX`, `[insert`, not `PLACEHOLDER` |
| J | Is `id` `'000'`? | Structurally valid and semantically wrong |
| V | Does the filename equal `<id>-<slug>.yaml`? | Validator errors otherwise |
| J | Were warnings cleared by doing the work or by weakening the record? | Deleting a `Blind` row to clear an owner warning is a suppressed finding |
| J | Can someone outside the working group answer the five questions in `docs/00-outcomes.md` section 1 from the record alone? | Without asking the author anything. And they can name one thing in it they would dispute |

---

## 4 · Severity language for review findings

Three levels. Severity is about **consequence**, not about how strongly you feel.

| Severity | Rule | Examples |
|---|---|---|
| **blocker** | Publication cannot proceed. The finding **falsifies a claim** in the record, or breaks one of the three structural controls, independence, evidence, or the derivation rule. Any validator ERROR is automatically a blocker | A claim the sources do not support · a `Have` whose evidence does not resolve · a framework ID that does not exist in the pin, or that traces to no step · `reviewed_by == authored_by` · a hypothetical presented as observed · a coverage tag that disagrees with its scores · an invented `incidents[]` slug |
| **should-fix** | The record is not falsified but is below the bar: it will mislead a reader or fail to produce work. **Any validator WARNING on a record heading for `published` is a should-fix.** Must be fixed before publication; does not require re-research | Missing `owner` or `backlog_ref` · `priority_rationale` with no exposure line · an undeclared merged step · `control_held` never considered · a `detection_opportunity` naming a product · a hardening item that breaks no step · a dispute resolved silently · `mapping_notes` that names no dispute |
| **note** | Does not block and does not have to be fixed. Wording, tightening, an open question for the next revision, or a choice you would have made differently where the author's is defensible | A tighter phrasing for a step · a mapping you would have argued for but cannot fault · an observation for the next author's `notes` |

Discipline rules for writing findings:

1. **Every finding names the field and one piece of evidence.** `<file>:<field or step>` · what is wrong in one sentence · the source, query or rule that shows it · what the author should do. A finding with no evidence is a **note**, whatever you think of it.
2. **You do not escalate a note to a should-fix because it recurs.** Recurrence is a defect in `docs/01-methodology.md`, the template or `docs/03`, file it there.
3. **You do not downgrade a blocker because the fix is expensive.** A blocker with an expensive fix is what `status: draft` is for.
4. **"We will fix it next revision" is not available for a blocker.** Publication is the claim that it is true now.
5. End with a **publication verdict**: publishable / publishable after the listed fixes / not publishable, plus one line of why, plus the validator's exact output.

**One vocabulary.** These three names are the only severity labels this program uses. Older reviews carry `blocker | major | minor`; read **major == should-fix** and **minor == note**, and use these three names from here on.

---

## 5 · The calibration exercise

**What it tests:** whether the method lives in the documents or in one person's judgment. `docs/00-outcomes.md` section 2 states the outcome; this is how you run it.

### How to run it

1. **Pick a scenario neither analyst has worked.** Prefer one with a contested fact, that is where interpretation shows.
2. **Assemble one source bundle and give both analysts the same bytes.** Different sources means you are measuring research, not method, and the diff becomes uninterpretable.
3. **Both work Gates 0 to 6 independently.** No conferring, no shared channel, no reading each other's file. Identical time box.
4. **Both stop at Gate 7.** Both run the validator. Neither publishes, neither reviews the other.
5. **Diff field by field. The diff is the whole instrument.**
6. **Keep one record; record what the other saw in its `notes`.** **Do not average the two**, an averaged record has no author and nobody can defend its judgment calls.

### What to compare

| Dimension | Agreement bar | Expected |
|---|---|---|
| Step count | Same +/-1 | High |
| Mechanism at each step | The same mechanism, wording may differ | High |
| `signal` per step | The same in substance | High |
| ATT&CK / ATLAS ID sets | Overlap, and every non-overlapping ID is one the other analyst can see the argument for | Medium. R2 and R3 judgment shows here |
| `dettect.visibility` / `detection` | Within 1 on each axis | Medium |
| **`coverage` tag per row** | **Identical on >=80% of rows** | **This is where drift shows** |
| Disputes | Both flagged at least one, and the disputes are recognizably about the same ambiguity | Medium |
| `classification.priority` | Not compared, it is a leadership call, not an analyst output |  |

**Agreement on steps is expected to be high. Agreement on coverage scoring is where drift shows**, because the step is a fact about the world and the score is a judgment about our estate. Two analysts reading the same incident rarely disagree about what happened; they routinely disagree about whether we would see it.

### Acceptable divergence

- A different but defensible framework ID for the same step, where each analyst can state the other's argument.
- Different step boundaries producing the same total set of mechanisms, one analyst merged where the other split, and both declared it.
- One coverage tag differing out of six, where the underlying disagreement is about what the data owner would say.
- Different `hardening[]` ordering within the same leverage band.

### Not acceptable, and what each one means

| Divergence | What it actually indicates |
|---|---|
| The same row scored `Blind` by one and `Have` by the other | Not a judgment gap, the two disagree about whether a control **exists**. That is a fact question and both records were guessing. Corrective: the data-owner session, i.e. a Gate 5 failure, not a calibration finding |
| A `derive_coverage()` disagreement | Impossible; it is arithmetic. If it happens, someone authored a tag |
| The two step sets do not describe the same chain | A Gate 0 failure. The scope line was ambiguous enough to admit two scenarios |
| Only one analyst flagged any dispute | The other treated an editorial mapping as settled. A `docs/03` section 3 comprehension gap |

### When the divergence is too wide

Too wide means: below the >=80% coverage-tag bar, or the step sets do not describe the same chain, or the ID sets barely overlap.

1. **Do not adjudicate who was right.** That produces a winner and no change.
2. **Find the sentence** in `docs/01-methodology.md`, `docs/03-framework-mapping.md` or `scenarios/_TEMPLATE.yaml` that both analysts read and applied differently.
3. **Fix that sentence in the same session**, with both analysts present, and record the change.
4. **Re-run only the diverging gate**, not the whole scenario.
5. **If the sentence does not exist, write it.** Divergence is the finding, not the failure. Two analysts diverging on the same row twice means the guidance for that row is underspecified, **fix the guidance, not the analysts.**
6. **If the divergence is a fact question**, does this control exist, does this rule fire, it is not a calibration finding at all. Both records were guessing, and the corrective is the data-owner session.

### When to run it

Frequency-agnostic. Do not put it on a calendar; put it on these triggers:

- **Whenever a new analyst joins.** Their first scenario is a calibration scenario, worked against someone experienced.
- **Whenever two orgs' records start looking different.** The signals: the same phenomenon mapped differently across two records; a coverage distribution that shifts without instrumentation work; a reviewer finding the same class of defect in two orgs' records.
- After any change to `derive_coverage()`, the DeTT&CT scales, or a framework baseline migration, because those change the inputs everyone is calibrating against.

### What it does not prove

**Two analysts can converge on the same wrong answer, and this exercise will not catch it.** Convergence proves the method is transmissible, not that it is correct. Correctness comes from primary sources (Gate 1), verification (Gate 2) and independent review (section 3).

---

## 6 · What the reviewer must not do

**Do not rewrite the record silently.** Report findings anchored to file and field. The author fixes; the author owns. Editing during review destroys the record of what was wrong, which is the input to the next calibration exercise and the next baseline migration. If you need to show what you mean, put the suggested text **in the finding**, not in the file.

**Do not approve your own work.** `reviewed_by` must differ from `authored_by`, and the same rule binds a drafting tool that then reviewed. If the pipeline that produced the record also called you, stop and say so.

**Do not wave through a warning because the author is senior.** The publication bar is zero errors and zero warnings at `status: published`, and it has no seniority clause. If a warning is genuinely wrong, the fix is a reviewed change to `tools/validate.py` with a stated reason, not a verbal exception on one record. An exception granted once becomes the precedent, and the bar erodes from the top of the org chart down.

Also, and for the same reasons:

- **Do not set `status: published` or write `reviewed_by`** until the review actually happened and the fixes have landed. Those are the last two things that happen, not the first.
- **Do not resolve a dispute in chat and write it up as consensus.** R7 in `docs/03-framework-mapping.md`: the disagreement goes into `mapping_notes` or `notes`. Silent resolution destroys the only evidence of where the taxonomy is ambiguous, which is exactly what the next migration needs.
- **Do not approve on the strength of the validator alone.** section 1 lists what it cannot see.
- **Do not accept "we will fix it next revision" for a blocker.** That is what `draft` is for.
- **Do not return "looks good."** Say what you checked and what would have changed your mind.
