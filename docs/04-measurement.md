# 04 · Measurement

**Audience:** whoever implements the rollup, and whoever has to defend a number in front of someone who does not want to hear it.
**Authority:** `derive_coverage()` in `tools/validate.py` is the derivation rule. `schema/scenario.schema.json` defines every field read here. `frameworks/baseline-YYYY.MM.yaml` pins the taxonomy the numbers are computed against. If this doc disagrees with any of them, they win and this doc is wrong, file it.

**What this doc is for.** The program lead named coverage, exposure and maturity in one breath. They are three different metrics, with three different formulas, three different audiences and three different failure modes. Conflating them produces a single number that is wrong for everyone. This doc separates them and makes each precise enough to implement.

**Compute the numbers, never read them off.** `tools/coverage.py` implements everything defined here and is the only supported way to produce these figures. Counting Blind rows by eye, or asking a model to count them, produces a plausible number nobody downstream can check. Run the tool, and run `python tools/validate.py` first so the tree the numbers came from is known-good. If you need a cut the tool does not produce, change `tools/coverage.py` rather than computing it by hand, and never write a second implementation of the derivation rule: it lives in `tools/validate.py::derive_coverage()` and `tools/coverage.py` imports it. A metric you cannot express as a script that returns the same answer every run is not a metric.

---

## 1 · The derivation rule

One rule converts a judgment call into an evidence-backed determination. It is implemented in `tools/validate.py::derive_coverage()` and nowhere else. The validator recomputes it on every row and **errors** on mismatch, so `telemetry[].coverage` in a record is a cache, not an input.

```python
def derive_coverage(dettect: dict | None) -> str | None:
    if not dettect:
        return None
    vis, det = dettect.get("visibility"), dettect.get("detection")
    if vis is None or det is None:
        return None
    if vis == 0:
        return "Blind"
    return "Have" if det >= 1 else "Collectable"
```

As a table:

| `dettect.visibility` (0 to 4) | `dettect.detection` (-1.5) | Derived `coverage` | Meaning |
|---|---|---|---|
| `0` (None) | any | **Blind** | Nothing produces this signal today |
| `>= 1` | `-1` (None) | **Collectable** | The source exists; nothing consumes it |
| `>= 1` | `0` (Forensics/context only) | **Collectable** | The source exists and is *logged*; nothing alerts on it |
| `>= 1` | `>= 1` (Basic . Excellent) | **Have** | A control emits it **and** it is wired to detection |
| absent / partial | absent / partial | **`None`** | Unscored. Not a value. See section 4 |

**Visibility dominates.** `visibility == 0` returns `Blind` regardless of the detection score, because a detection maturity claimed over a data source that does not exist is incoherent. A record carrying `visibility: 0, detection: 3` is a scoring error, not a coverage state.

### Why `detection == 0` maps to Collectable, not Have

In DeTT&CT's scale (`frameworks/baseline-2026.07.yaml` → `frameworks.dettect.scales.detection`), `0` is **"Forensics/context only"**, the data is retained and an analyst can pull it during an investigation, but nothing fires on it. `-1` is "None" and `1` is "Basic". So `0` sits between "we do not have it" and "something alerts".

The Have/Collectable boundary is placed at `detection >= 1` because the entire purpose of the tag is to separate *we would notice* from *we could reconstruct afterward*. Those are different security properties with different costs:

- **Have** means the signal participates in detection. A step covered by Have is one where the attack path can be interrupted.
- **Collectable** means the signal exists in a log somewhere. A step covered by Collectable is one you can write up after the fact. The instrumentation is already paid for; the detection work is not.

Collapsing `detection == 0` into Have is the single most attractive way to make a coverage number look good, because it costs nothing, the data is already being collected, so it feels like coverage. It is exactly the case the tag exists to expose. **A `Collectable` row is the cheapest `Have` available**: the data is landing, the gap is a rule and an owner, and that is what `backlog_ref` on the row is for.

### Consequences the implementation must honor

1. `coverage` is never authored. If a proposed row's tag disagrees with its scores, the scores are the truth and the tag is fixed.
2. A row with no `dettect` block has **no coverage value**. Not `Blind`. See section 4.
3. The five `dettect.quality` dimensions (each 0 to 5) do **not** enter the derivation. They qualify a `Have`, a `Have` with `retention: 0` is a detection that fires on data you cannot go back to. Report quality alongside coverage; never fold it into the tag.

---

## 2 · The three metric families

### Preliminaries, the sets every formula reads

| Symbol | Definition |
|---|---|
| `L` | The reporting library: records with `status: published`. `draft` and `in-review` are excluded (incomplete by definition); `retired` is excluded from current metrics and retained for history (schema: *"retired scenarios stay in the repo forever"*) |
| `A(s)` | The **attack-step** evidence rows (the telemetry map) of scenario `s`: `[r for r in s.telemetry if r.get("kind", "attack-step") == "attack-step"]` |
| `C(s)` | The **control** rows: `kind == "control"`. **Excluded from every coverage denominator and numerator.** A control row is a verification signal, not an answer to a step; counting them lets you pad the numerator by adding rows |
| `S(s)` | The **scored** subset of `A(s)`: rows where `derive_coverage(r["dettect"])` is not `None` |
| `cov(r)` | `derive_coverage(r["dettect"])` |
| `org` | An organization identifier. Coverage is always evaluated for exactly one org, see section 6 |

The validator already guarantees `|A(s)| == len(s.attack_path)` for a published record (it errors on a step with no row), so `|A(s)|` is the step count.

---

### 2a · Coverage

**Definition.** The proportion of scenario steps that are adequately instrumented, where "adequately" is `derive_coverage() == "Have"` and nothing else.

**Formulas.**

```
# per scenario, per org
coverage_have(s)        = |{ r in S(s) : cov(r) == "Have"        }| / |S(s)|
coverage_collectable(s) = |{ r in S(s) : cov(r) == "Collectable" }| / |S(s)|
coverage_blind(s)       = |{ r in S(s) : cov(r) == "Blind"       }| / |S(s)|
completeness(s)         = |S(s)| / |A(s)|          # what fraction of steps were assessed at all

# aggregate. STEP-WEIGHTED, not the mean of per-scenario rates
coverage_have(L) = sum_{s in L} |{ r in S(s) : cov(r)=="Have" }|  /  sum_{s in L} |S(s)|
completeness(L)  = sum_{s in L} |S(s)|  /  sum_{s in L} |A(s)|
```

Step-weighted is mandatory for the aggregate. A mean of per-scenario percentages weights a 3-step scenario the same as a 6-step one, which makes splitting a scenario a lever on the number (section 7).

**Fields read.** `status`, `telemetry[].kind`, `telemetry[].dettect.visibility`, `telemetry[].dettect.detection`, `attack_path[].step`.

**Reported as.** Three proportions summing to 1 over `|S(s)|`, **always accompanied by `completeness`**. A coverage figure published without its completeness figure is not interpretable: 100% Have over 1 of 6 assessed steps and 100% Have over 6 of 6 are the same number and different worlds.

**What it does not tell you.**
- Not whether the covered steps are the *important* ones. Coverage is step-count arithmetic and is indifferent to which step in the chain is instrumented. A chain with Have on steps 5 and 6 only is 33% covered and effectively uncovered, by the time you see it, it has happened.
- Not how good the data is. That is `dettect.quality`, reported separately.
- Not whether the detection works. `detection: 1` is "Basic". Coverage says a rule exists, not that it fires on the real thing.
- Nothing about risk. A 40%-covered BACKLOG scenario may matter less than a 90%-covered NOW one.

**Audience.** Detection engineering and data owners. This is the work queue: `Collectable` rows are the cheap wins, `Blind` rows are the instrumentation asks.

---

### 2b · Exposure

**Definition.** Which NOW-priority scenarios have Blind steps. This is the risk view, it joins the coverage arithmetic to the human priority judgment in `classification.priority`.

**Formulas.**

```
NOW      = { s  in  L : s.classification.priority == "NOW" }
exposed  = { s  in  NOW : there exists r  in  S(s) with cov(r) == "Blind" }

exposure_rate      = |exposed| / |NOW|
exposed_steps(s)   = [ r.step for r in S(s) if cov(r) == "Blind" ]           # ordered
orphaned_steps(s)  = [ r.step for r in S(s) if cov(r) == "Blind" and not r.get("owner") ]
unfunded_steps(s)  = [ r.step for r in S(s) if cov(r) in ("Blind","Collectable")
                                            and not r.get("backlog_ref") ]

# secondary view: a NOW step you can only reconstruct afterward
forensics_only(s)  = [ r.step for r in S(s) if cov(r) == "Collectable" ]
```

Also report, per exposed scenario, the *earliest* Blind step. A Blind step 1 on a NOW scenario is a different problem from a Blind step 6: the first means the chain starts invisibly, the second means it ends invisibly.

**Fields read.** `classification.priority`, `classification.priority_rationale` (for the narrative, not the arithmetic), `telemetry[].dettect`, `telemetry[].owner`, `telemetry[].backlog_ref`, `telemetry[].step`.

**What it does not tell you.**
- Not likelihood. `priority` is an editorial judgment recorded with its rationale; exposure inherits that judgment and does not validate it.
- Not impact or blast radius. `scaled_up` is prose and is explicitly hypothetical.
- Not that a non-NOW scenario is safe. BACKLOG scenarios with Blind steps exist; they are just not this cycle's argument.
- Not that an exposed scenario is exploitable, the chain may be broken by a preventive control recorded in `hardening[]` or by `attack_path[].control_held`, neither of which coverage sees.

**Audience.** Whoever allocates instrumentation budget, and whoever has to answer "what would we not see". `orphaned_steps` is the escalation list: the schema is explicit that an unowned gap is an orphan and will never be closed.

---

### 2c · Maturity

**Definition.** Process capability, is the library being produced to standard. Are scenarios reviewed, scored, owned, evidenced, and closed-looped. **This moves independently of coverage and exposure**, and that independence is the point: an org can be highly mature and badly covered (it knows exactly where it is blind, with owners and tickets) or well covered and immature (good telemetry, no evidence trail, unattributable numbers). Reporting one as a proxy for the other is the most common misuse of this section.

**Eligibility gate.** A scenario enters the maturity population only if `completeness(s) == 1`, every attack-step row is scored. Otherwise it is **not counted at all**, in either the numerator or the denominator. See section 4.

```
eligible = { s  in  L : completeness(s) == 1 }
```

**The seven gates.** Each is binary per scenario. All are computed from fields the schema already carries; none require a new field.

| Gate | Passes when | Fields |
|---|---|---|
| **M1 · reviewed** | `provenance.reviewed_by` is present and `!= provenance.authored_by` | `provenance` |
| **M2 · scored in depth** | every row in `S(s)` also carries all five `dettect.quality` dimensions | `telemetry[].dettect.quality` |
| **M3 · evidenced** | every `Have` row has a non-empty `evidence` | `telemetry[].evidence` |
| **M4 · owned** | every `Blind` or `Collectable` row has a non-empty `owner` | `telemetry[].owner` |
| **M5 · closed loop** | every `Blind` or `Collectable` row has a `backlog_ref` | `telemetry[].backlog_ref` |
| **M6 · remediable** | `hardening[]` is non-empty and every item's `breaks_step` resolves to an existing step | `hardening[]`, `attack_path[].step` |
| **M7 · sourced** | `provenance.sources[]` non-empty **and** contains a `tier: '0'` source. Waived when `classification.evidence == "doomsday"` | `provenance.sources`, `classification.evidence` |

```
maturity(s) = (# gates passed) / 7                       # s  in  eligible only
maturity(L) = sum_{s  in  eligible} maturity(s) / |eligible|
assessed(L) = |eligible| / |L|                           # ALWAYS reported alongside
```

**Reported as.** `maturity(L)` and `assessed(L)` together, plus a per-gate pass rate across `eligible`, the per-gate breakdown is the actionable part. A library at 0.71 maturity where the only failing gate is M5 has one problem (nobody is filing tickets), not a general quality issue.

**What it does not tell you.**
- Nothing about security. A perfectly mature library can describe a completely blind estate. M-gates measure whether the record is trustworthy, not whether the news is good.
- Not that the scores are accurate. M2 checks the quality dimensions are *present*, not correct. Accuracy is checked by the calibration exercise (`docs/00-outcomes.md` section 2) and by evidence spot-audits (section 7).
- Not throughput. There is no gate for how many scenarios exist, deliberately.

**Audience.** Whoever is accountable for the program's output being defensible, internal audit, and anyone about to hand a number to a third party.

---

## 3 · Reporting the three together

They are reported side by side, never combined into a composite score. A composite hides exactly the case that matters: high coverage, low maturity (numbers with nothing behind them).

| | Coverage | Exposure | Maturity |
|---|---|---|---|
| Unit | evidence row (step) | scenario | scenario |
| Population | `S(s)` over `L` | NOW-priority `L` | `eligible is a subset of L` |
| Moves when | instrumentation or detection changes | priority changes, or a Blind row flips | process discipline changes |
| Can be 100% while the others are 0 | yes | yes | yes |
| Headline companion figure | `completeness(L)` | `orphaned_steps` count | `assessed(L)` |

---

## 4 · Why an unscored row does not count as zero

An unscored row, `dettect` absent, or missing `visibility` or `detection`, makes `derive_coverage()` return `None`. It is excluded from `S(s)`, and any scenario containing one is excluded from the maturity population entirely. It is **not** scored as `Blind`, and **not** counted as a failed maturity gate.

The reason is that zero and unknown are different claims, and the program exists to keep them apart.

- **`visibility: 0` is a finding.** Somebody looked at that step, went to the data owner, and established that nothing produces the signal. It is evidence. It generates an owner, a `backlog_ref`, and an argument for budget.
- **No `dettect` block is an absence of finding.** Nobody looked. There is nothing behind it.

Treating unknown as zero has three specific failure modes:

1. **It manufactures precision.** The denominator implies an assessment that did not happen. A library reported as "22% Have" where half the rows were never scored is not a conservative estimate; it is a fabricated one, and it is indistinguishable from an honest 22%.
2. **It sells the improvement twice.** If unscored counts as zero, the cheapest way to move every metric next period is to score rows you should already have scored. The number rises, nothing about the estate changed, and the delta is attributed to instrumentation work that never happened. Excluding unscored rows means doing the assessment moves `completeness` and `assessed(L)`, which are honest measures of assessment work, and leaves coverage where the evidence puts it.
3. **It destroys the escalation.** A `Blind` row is owned and ticketed (M4, M5). An unscored row is nobody's. Folding the second into the first hides the orphans inside a number that looks like it is being worked.

The validator enforces the same asymmetry: an unscored row is a **warning** on a draft and an **error** on a published record, with the message *"the coverage tag is an opinion until these exist, and the row cannot count toward maturity reporting."* Unscored is a state a record passes through, not a state it reports from.

**Corollary for the rollup implementation:** every published figure carries its own completeness denominator (`completeness(L)` for coverage, `assessed(L)` for maturity). Exclusion is only honest if the size of the exclusion is on the same page as the number.

---

## 5 · The snapshot record

Every metric run emits an immutable snapshot. Without it, a year-over-year delta is uninterpretable, two of the four frameworks made breaking changes inside 18 months (`frameworks/baseline-2026.07.yaml`), and a coverage "drop" caused by MITRE splitting a tactic looks identical to a coverage drop caused by a control being switched off.

The baseline's migration rules already require this: *"Record the FULL version tuple with every metric snapshot."* This is that tuple, plus the library state needed to make the delta attributable.

```yaml
snapshot_id: 2026-08-01-acme-2026.07
generated: 2026-08-01
generated_by:
  tool: tools/coverage.py           # the rollup tool; `--json` emits this snapshot
  repo_commit: <git sha>            # the library state is the commit; do not summarize it
org: acme                           # exactly one org per snapshot (section 6)
baseline: '2026.07'                 # frameworks/baseline-2026.07.yaml

frameworks:                         # the full version tuple. Read it from the PINNED ARTIFACTS
  attack:                           # once they are vendored into frameworks/pinned/ with
                                    # checksums; until that directory exists, tools/coverage.py
                                    # copies the tuple out of the baseline file and the sha256
                                    # lines below cannot be filled
    version: '19.1'
    spec_version: '3.3.0'           # x_mitre_attack_spec_version off the collection object
    pinned_artifact: enterprise-attack/enterprise-attack-19.1.json
    sha256: <hex>
  atlas:
    content_version: '2026.07'      # content and format versions decoupled since 2026.05
    format_version: '6.0.0'         # record BOTH
    pinned_artifact: dist/v6/ATLAS-2026.07.yaml
    sha256: <hex>
  owasp_llm:
    edition: '2025'
  owasp_agentic:
    edition: '2026'
  dettect:
    version: '2.2.0'
    targets_attack: '18'            # the ATT&CK version DeTT&CT ran against, NOT necessarily
                                    # the ATT&CK version above. This mismatch is the single
                                    # most common source of an unexplained score shift.
library:
  scenarios_total: 21
  by_status: {published: 1, in-review: 0, draft: 20, retired: 0}
  published_ids: ['021']
  retired_this_period: []           # ids + reason + superseded_by; never silently absent (section 7)
  ids_added_this_period: []
  ids_rescored_this_period: []      # a coverage change with no backlog_ref behind it

metrics:
  coverage: {have: 0.500, collectable: 0.333, blind: 0.167, completeness: 1.000, rows_scored: 6, rows_total: 6}
  exposure: {now_total: 1, now_exposed: 1, exposure_rate: 1.000, orphaned_steps: 0, unfunded_steps: 0}
  maturity: {mean: 1.000, eligible: 1, assessed: 1.000, gates: {M1: 1.0, M2: 1.0, M3: 1.0, M4: 1.0, M5: 1.0, M6: 1.0, M7: 1.0}}

non_comparable_with:                # populated at every migration, from the new baseline's
  - snapshot_id: <prior>            # breaking_changes_since_prior_baseline
    reason: <e.g. tactic-level metrics span the v19 Defense Evasion split>
```

**Rules.**

1. **Read the version tuple from the pinned artifacts, not from the baseline YAML.** They can disagree, `docs/03-framework-mapping.md` section  Appendix records a live discrepancy on `attack.spec_version` between the baseline file and the pinned bundle. The snapshot records what the computation actually ran against.
2. **Snapshots are immutable and kept forever.** A correction is a new snapshot with a `supersedes:` key. Editing a snapshot destroys the only evidence of what a past claim was based on.
3. **During a baseline migration, emit two snapshots**, one against each pin, for one full reporting cycle. That dual report is what makes the year-over-year delta attributable to controls rather than framework churn.
4. **`ids_rescored_this_period` is the anti-drift field.** A row whose coverage changed with no `backlog_ref` explaining why is a rescore, not an improvement, and it must be visible as such.

---

## 6 · Multi-org: the coverage overlay

**The scenario library is org-independent. Coverage assessments are per-org.**

An attack path is a property of the technology, not of an estate. `attack_path[]`, `framework_mapping`, `hardening[]`, `incidents[]`, `commentary`, none of these change when a different organization reads the record. What changes is whether *that org* sees each step. So `telemetry[].dettect`, `coverage`, `owner`, `evidence` and `backlog_ref` are org-scoped, and everything else is not.

### The pattern

```
scenarios/021-agent-sandbox-escape-to-autonomous-intrusion.yaml   # library + REFERENCE assessment
coverage/
  acme/021.yaml            # acme's overlay, per-row overrides
  beta-division/021.yaml    # beta's overlay
  _example-org/            # template
```

The scenario record carries a **reference assessment**, the scores the authoring org determined, complete enough that the record is publishable and the slides render standalone. An org overlay overrides it **per row**.

### Overlay format

```yaml
schema_version: 1
org: acme
scenario: '021'
baseline: '2026.07'            # must match the scenario's framework_mapping.baseline
assessed_by: <named individual>
assessed: 2026-08-01
rows:
  - step: 1
    dettect:
      visibility: 1
      detection: 0
      quality: {device_completeness: 2, data_field_completeness: 1, timeliness: 2, consistency: 1, retention: 3}
    coverage: Collectable      # derived; validator recomputes and errors on mismatch
    owner: Platform Engineering
    backlog_ref: ACME-4417
  - step: 3
    inherit: true              # explicitly NOT assessed by this org, see below
```

### Resolution rules

1. **Row-level, not record-level.** For scenario `s` and org `o`, row `r` resolves to the overlay row with the matching `step` if one exists, otherwise to the scenario's reference row.
2. **`inherit: true` marks a row this org has not assessed.** An inherited row is excluded from that org's `S(s)`, it is unscored *for that org* even though the reference record has numbers. This falls straight out of section 4: the reference org's assessment is not evidence about your estate. Inherited rows show up in `completeness`, which is exactly where they belong.
3. **A row silently absent from the overlay resolves to the reference row and is treated as inherited.** Explicit `inherit: true` is preferred because it records that someone looked and deferred, rather than that someone forgot.
4. **The same derivation rule applies to overlays.** `derive_coverage()` is not org-configurable. This is the one thing that must not be negotiable, because it is what makes two orgs' numbers mean the same thing.
5. **The overlay may not change anything outside the org-scoped fields.** An overlay that redefines `attack_path` is a fork, not an overlay, split the scenario in the library instead.
6. **One snapshot per org.** There is no cross-org aggregate coverage number, because there is no such estate. Cross-org comparison is a table of per-org figures with their completeness values, side by side.

### Why this matters politically

The program will span multiple organizations. **An org can adopt the scenario library without publishing its coverage.** The library lives in a shared repo; `coverage/<org>/` can live in that org's own repo, its own branch, or behind its own access control, and nothing in the pipeline breaks, the scenario record stands alone and renders alone.

That decoupling is what makes adoption cheap. Adopting the library costs a team nothing politically: it is a shared description of how attacks work. Publishing your coverage is an admission of where you are blind, and no team will do that as the price of entry. Coupling the two would guarantee that the second requirement kills the first.

The second-order benefit: because the derivation rule and the record are shared, a team that later *chooses* to publish its coverage produces numbers that aggregate on day one. No retrofit. That is the portability outcome in `docs/00-outcomes.md` section 4, and this overlay pattern is the mechanism behind it.

---

## 7 · Anti-gaming

These numbers will eventually be used to judge someone. Name the attacks now, while nobody has an incentive.

| Attack | How it looks | Control |
|---|---|---|
| **Optimistic scoring**, inflating `visibility`/`detection` to move rows into Have | Coverage rises with no ticket and no rule change | `derive_coverage()` is not negotiable; `evidence` is mandatory on Have and must be a re-runnable artifact (a saved search that returns rows, a rule ID, a ticket), the validator errors on a published Have with no evidence. Spot-audit a random sample of Have rows per snapshot by *actually running the evidence*; a Have whose evidence returns nothing is downgraded and the downgrade is recorded in `ids_rescored_this_period`. The calibration exercise (`docs/00-outcomes.md` section 2) catches systematic optimism across analysts. |
| **`detection: 0` counted as Have**, the most attractive version of the above, because the data really is being collected | Rows move to Have with no detection work | Hard-coded in the rule (section 1). `detection: 0` is Collectable by definition, and Collectable is reported as its own line, never merged into Have in any rendering. |
| **Splitting scenarios to inflate the denominator**, one 6-step scenario becomes two 4-step ones, both mostly instrumented | Scenario count rises, aggregate coverage rises | Aggregate coverage is **step-weighted** (section 2a), so splitting is close to neutral by construction. Scenario count is explicitly not a metric (`docs/00-outcomes.md` section 5). A split is a schema event: IDs are immutable and never reused, and the old record must be `retired` with `superseded_by` pointing at the replacement, so every split is visible in `retired_this_period`. Splits driven by the R3 mapping ceiling (`docs/03-framework-mapping.md`) are legitimate and look identical, which is why the control is visibility, not prohibition. |
| **Padding with control rows**, adding `kind: control` rows that look like coverage | Row counts rise, Have proportion rises | Control rows are excluded from every coverage numerator and denominator (section 2 preliminaries). The validator also warns when control rows are numbered inside the attack-step range. |
| **Marking Have without evidence** | A record passes review with confident tags and no artifacts | Validator error at `status: published`. Beyond that: evidence must be re-runnable by a third party, and evidence goes stale, re-verify at `provenance.review_date`. Evidence that no longer resolves downgrades the row rather than being refreshed with a note. |
| **Quietly retiring inconvenient scenarios**, the ones with Blind NOW steps | Exposure falls without anything improving | Retired records **stay in the repo forever** (schema) and require `retired.date` and `retired.reason`. `retired_this_period` is a mandatory snapshot field and is never empty-by-omission. Report exposure both including and excluding retirements for the period they occur. Retiring a NOW scenario with Blind steps is its own reportable line, not a silent denominator change. Snapshots are immutable, so the prior number survives the retirement. |
| **Not scoring the hard rows**, leaving the ugly steps unscored so they drop out of the population | Coverage looks good over a small `S(s)` | `completeness(L)` and `assessed(L)` are mandatory companions to every figure (section 4). A rising coverage number against a falling completeness number is the signature, and it should be plotted on the same axis. Published records cannot carry unscored rows at all, that is a validator error. |
| **Framework churn laundering**, attributing a movement caused by an upstream taxonomy change to your own controls | A delta that nobody can explain, in your favor | The full version tuple on every snapshot (section 5), plus one cycle of dual reporting at every migration, plus `non_comparable_with`. Tactic-level figures spanning the v19 Defense Evasion split are flagged non-comparable by rule. |
| **Rescoring without work**, moving numbers at review time and calling it improvement | Coverage rises between snapshots with no backlog activity | `ids_rescored_this_period` captures every coverage change with no `backlog_ref` behind it. `docs/00-outcomes.md` section 5 states the real metric as a tag flip *with evidence and a backlog ref*; a flip missing either is reported as a rescore. |
| **Merging steps**, folding a Blind step into its neighbor so the row disappears | A record's step count drops between snapshots and its Have proportion rises | A merge removes a row from the numerator and the denominator at once, so it is invisible in a percentage. Diff `len(attack_path)` per record between snapshots and report every drop. A merge is legitimate only when it is declared (`docs/01-methodology.md`, Gate 3) and never when the two halves have different coverage answers. |
| **Evidence reuse**, one rule or saved search cited as the evidence behind many unrelated Have rows | The evidence rate is 100% and one artifact appears all over the library | Group Have rows by their `evidence` string every snapshot. One artifact backing rows across unrelated scenarios is a claim that one control sees everything; run that query against each of those steps and downgrade the rows it does not answer. |
| **Backlog churn without closure**, tickets that appear and vanish while the row stays where it was | `backlog_ref` values disappear between snapshots with no coverage movement | Diff the `backlog_ref` set between snapshots. A ticket that closed without moving a score closed nothing, and it belongs in the report as churn rather than as progress. |

**The general principle:** every one of these controls works by making the movement visible next to its cost, not by forbidding the movement. Prohibition invites argument about intent. A snapshot that shows coverage up 12 points, completeness down 20, and zero closed backlog items settles the argument without anyone having to accuse anyone. For the same reason, **report absolute counts next to every percentage**: a rising percentage over a shrinking denominator is not progress, and it is only visible when both numbers are on the page.

---

## 8 · Worked calculation, scenario 021

`scenarios/021-agent-sandbox-escape-to-autonomous-intrusion.yaml`, `status: published`, `baseline: '2026.07'`, `classification.priority: NOW`. Six attack-path steps, six `attack-step` evidence rows, no control rows. Numbers below are read straight out of the record.

### Derivation, row by row

| Step | `visibility` | `detection` | Rule branch | Derived | Recorded | Match |
|---|---|---|---|---|---|---|
| 1 | 0 | -1 | `vis == 0` | **Blind** | Blind | yes |
| 2 | 3 | 2 | `vis >= 1`, `det >= 1` | **Have** | Have | yes |
| 3 | 2 | 0 | `vis >= 1`, `det == 0` → forensics only | **Collectable** | Collectable | yes |
| 4 | 4 | 3 | `vis >= 1`, `det >= 1` | **Have** | Have | yes |
| 5 | 2 | 0 | `vis >= 1`, `det == 0` | **Collectable** | Collectable | yes |
| 6 | 3 | 2 | `vis >= 1`, `det >= 1` | **Have** | Have | yes |

Rows 3 and 5 are the case section 1 is about. Both signals are *being logged*, untrusted dataset configs at ingestion, K8s and cloud audit for the container escape. Neither alerts. Under a scheme that read "we have the logs" as coverage, this scenario is 83% covered. It is 50%.

### Coverage

```
|A| = 6, |S| = 6                        completeness = 6/6 = 1.000
Have        = |{2,4,6}| / 6 = 0.500
Collectable = |{3,5}|   / 6 = 0.333
Blind       = |{1}|     / 6 = 0.167
```

Quality of the Have rows (`dettect.quality`, 5 dimensions x 0 to 5, max 25):

| Step | dev | field | time | consist | reten | sum | mean |
|---|---|---|---|---|---|---|---|
| 2 | 4 | 3 | 4 | 3 | 4 | 18 | 3.6 |
| 4 | 4 | 4 | 4 | 4 | 3 | 19 | 3.8 |
| 6 | 3 | 3 | 4 | 3 | 4 | 17 | 3.4 |

Have-row quality mean = (18 + 19 + 17) / (3 x 25) = 54/75 = **0.72** (3.6 of 5). Reported next to the 50%, never folded into it. Lowest dimension across the Have rows is `consistency` (3, 4, 3), field naming, not collection.

### Exposure

```
priority = NOW                     → in the NOW population
exposed_steps   = [1]              → EXPOSED
earliest_blind  = 1                → the chain starts invisibly
orphaned_steps  = []               → step 1 owner: AI Platform
unfunded_steps  = []               → step 1 OBS-1041, step 3 OBS-1042, step 5 OBS-1043
forensics_only  = [3, 5]           → secondary view
```

Read plainly: **the first step of a NOW-priority chain is Blind, and the two escalation steps are forensics-only.** The instrumented steps (2, 4, 6) are the infrastructure-generic ones, egress, process execution, C2, which is exactly what `commentary.blind` says: *the AI-specific gaps sit at both ends*. Every gap is owned and ticketed, which is what a well-run exposed scenario looks like. Exposure is not a failure state; unowned exposure is.

### Maturity

Eligible: `completeness == 1.000`, so 021 enters the population.

| Gate | Check against the record | Result |
|---|---|---|
| M1 reviewed | `reviewed_by` present and != `authored_by` | pass |
| M2 scored in depth | all 6 rows carry all five `quality` dimensions | pass |
| M3 evidenced | rows 2, 4, 6 (Have) each carry `evidence`, `NET-EGRESS-ANOM-07`, `EDR-CONT-0113`, `DLP-EGR-22` | pass |
| M4 owned | rows 1, 3, 5 (Blind/Collectable) have owners. AI Platform, Data Platform, Cloud Platform | pass |
| M5 closed loop | rows 1, 3, 5 have `backlog_ref`. OBS-1041/1042/1043 | pass |
| M6 remediable | 8 `hardening[]` items, every `breaks_step` in 1 to 6 | pass |
| M7 sourced | 5 sources, 3 at `tier: '0'`; `evidence: seen-in-the-wild` so no waiver needed | pass |

```
maturity(021) = 7/7 = 1.000
```

### The three numbers together

| Metric | Value | Companion |
|---|---|---|
| Coverage (Have) | **0.500** | completeness 1.000; Have-row quality 0.72 |
| Exposure | **exposed**. Blind at step 1, earliest possible | 0 orphaned, 0 unfunded |
| Maturity | **1.000** | eligible, all 7 gates |

This is the shape the separation in section 2 exists to show. Maturity is perfect and coverage is half. The record is trustworthy, complete, owned and evidenced, *and it says the estate cannot see the start of the chain*. A composite score would average those into something around 0.75 and communicate neither.

Note also what this scenario would look like next period if OBS-1041 lands and step 1 moves to `visibility: 2, detection: 1`: coverage goes 0.500 → 0.667, exposure clears (no Blind rows), maturity stays 1.000. That delta is attributable, because the ticket is on the row.
