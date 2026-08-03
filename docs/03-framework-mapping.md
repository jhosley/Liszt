# 03 · Framework Mapping

**Audience:** the analyst mapping a scenario, mid-task.
**Authority:** `frameworks/baseline-2026.07.yaml` is the pinned vocabulary. `schema/scenario.schema.json` is the record structure. If this doc and the baseline disagree, the baseline wins and this doc is wrong, file it.

**Before you map anything, three checks:**

1. `framework_mapping.baseline` matches the current baseline file (`2026.07`). Never mix baselines inside one record.
2. You are mapping at the **step** level (`attack_path[].attack`, `attack_path[].atlas`), not straight at the scenario level.
3. You know, before you start, that almost everything you are about to write is **editorial judgment**, not an upstream-published linkage. See section 3.

---

## 1. Why we map at all

Three purposes. They are not the same purpose, and they pull in different directions.

| # | Purpose | Consumer | What it demands of the mapping |
|---|---------|----------|-------------------------------|
| a | **Shared vocabulary**, scenario 013 and scenario 021 can be compared, deduplicated and searched | Analysts, threat intel | Consistency over precision. Same phenomenon → same ID, every time |
| b | **Technique → mitigation → detection path** | Detection engineering, control owners | Precision over consistency. The most specific technique that is actually evidenced, because that is what carries usable mitigations and analytics |
| c | **Coverage yardstick** for maturity reporting | Leadership, audit, board reporting | Stability over both. The taxonomy must be held still across reporting periods |

**The tension, stated plainly.** (b) pushes you toward sub-techniques and long lists, more IDs, more specific IDs, more detection hooks. (a) pushes you toward a small, boring, repeatable set so that two analysts land in the same place. (c) punishes you for changing your mind: a technique retired, split or renamed upstream moves your coverage number without a single control changing.

**Purpose (c) is why version pinning is non-negotiable.** If the taxonomy floats, a coverage "improvement" and MITRE renaming a tactic are indistinguishable in the metric. Two of our four frameworks made breaking changes inside 18 months (section 5). Pin the artifact, record the full version tuple with every snapshot, migrate deliberately (section 6).

When the purposes conflict on a specific record: serve (a) in the scenario-level roll-up, serve (b) at the step level, and serve (c) by never re-mapping a published record in place.

---

## 2. What each framework is for, and is not for

| Framework | Answers | Does **not** answer | ID shape |
|-----------|---------|---------------------|----------|
| **ATT&CK** (Enterprise v19.1) | What does an adversary do to *infrastructure*, hosts, containers, clouds, identity, network | Anything model- or prompt-specific. There is no ATT&CK technique for prompt injection | `T1611`, `T1552.005`, tactics `TA0005` |
| **ATLAS** (2026.07) | What does an adversary do to *AI systems*, models, training data, RAG, agents, agent tools | Infrastructure detail beyond the AI boundary; it deliberately defers to ATT&CK there | `AML.T0105`, `AML.T0010.002`, `AML.TA0004`, `AML.M0000`, `AML.CS0067` |
| **OWASP LLM Top 10 (2025)** / **Agentic Top 10 (ASI, 2026)** | What *risk category* does this fall in, in language a developer or AppSec reviewer already uses | Adversary behavior. These are risk classes, not techniques, there is no chain, no tactic, no ordering | `LLM03:2025`, `ASI01:2026` |
| **DeTT&CT (2.2.0)** | Would we *see* any of it, and how good is the data | What the adversary did. It defines no IDs of its own, it annotates ATT&CK technique IDs | scores only: visibility 0 to 4, detection -1 to 5, five quality dimensions 0 to 5 |

**These are not four views of the same thing.** Treating them as interchangeable is the single most common mapping error in this repo. Concretely:

- ATLAS `AML.T0049` and ATT&CK `T1190` are *near*-equivalents (ATLAS says "adapted from"), but ATLAS carries only the AI-system framing, so recording only one of them loses information depending on who reads it.
- `LLM06:2025` (Excessive Agency) is not a technique. It never belongs in `attack_path[].attack` or `attack_path[].atlas`, and it has no step. OWASP IDs live at the scenario level only, the schema enforces this: `attack_path[]` items accept `attack` and `atlas`, nothing else.
- A DeTT&CT score is not a mapping. It is a claim about our telemetry, and it belongs on `telemetry[].dettect`, evidenced.

**Two ATLAS fields worth using and easy to miss** (both present in the 2026.07 pin, verified):

- `platforms`, one or more of `Predictive AI`, `Generative AI`, `Agentic AI`, `Enterprise`. 27 techniques are Agentic-AI-only; 49 are Enterprise-only (those are the ATT&CK re-framings). For an agentic scenario, prefer techniques whose `platforms` include `Agentic AI`.
- `maturity`, `Realized` (68), `Demonstrated` (92), `Feasible` (18). This is a useful sanity check against `classification.evidence`: a `seen-in-the-wild` scenario mapped entirely to `Feasible` techniques is probably mis-scoped, and vice versa.

---

## 3. The honesty section, read this before you publish a mapping

**There is no authoritative crosswalk between OWASP and either MITRE framework, in either direction.** Not for the LLM list, not for the Agentic list. Every crosswalk you can find online is third-party, community repos, vendor blogs, conference decks, personal posts. Do not cite any of them as authoritative, and do not launder them into this repo by citing a repo that cites them.

**The ATLAS → ATT&CK linkage is real but narrow.** Verified against the 2026.07 pin:

| Fact | Value |
|------|-------|
| ATLAS techniques total | 178 (101 parents + 77 sub-techniques) |
| Carrying an `attack-reference` field | **37** (21%) |
| ATLAS-specific, no ATT&CK counterpart | 141 |
| Direction | One-way. ATT&CK contains no pointer back to ATLAS |
| Semantics | The field means *"adapted from"*, not *"equals"* |
| Published as | A field inside the ATLAS data, not a crosswalk document |

`atlas-to-stix` can emit a combined bundle. That is co-packaging, not semantic mapping, it does not create linkage that is not already in the `attack-reference` fields.

### What this obliges us to do

1. **`mapping_confidence: editorial` is the default.** `authoritative` is reserved for the case where the linkage you are asserting *is* an ATLAS `attack-reference` field and nothing more. In practice that means: if your record contains any OWASP ID, or any ATLAS<->ATT&CK pairing not backed by an `attack-reference`, the record is `editorial`. Most records are.
2. **Write `mapping_notes`.** The schema calls it optional; the quality bar does not. When `mapping_confidence: editorial`, `mapping_notes` must (a) state the reasoning for the non-obvious IDs, (b) **name at least one mapping a reasonable analyst would dispute**, and (c) record any gap where nothing fit. A note that says "mapped per standard practice" is a failed note.
3. **Never imply upstream endorsement.** In slides, reports and tickets: "our mapping to ATT&CK v19.1", never "the MITRE mapping". If a mapping row reaches a customer, auditor or board deck, it carries the editorial label with it.
4. **Name an owner.** The baseline names one for the pin; the record names one in `provenance.authored_by` / `reviewed_by`. Editorial judgment with no name attached is unreviewable.

**If you take one thing from this doc:** the IDs are borrowed, the mapping is ours.

---

## 4. Mapping rules

Concrete, testable, in order of how often they are broken.

### R1 · Map the steps first, roll up second

Populate `attack_path[].attack` and `attack_path[].atlas` per step. `framework_mapping.attack` / `.atlas` is the **union** of the step-level IDs, ordered as the chain proceeds (the schema says: ordered, not sorted).

Mapping the scenario level directly is where drift starts, it produces IDs that no step evidences, and it makes the roll-up unfalsifiable. Test: every scenario-level ID must appear in at least one step. If it does not, either the step mapping is incomplete or the scenario ID is aspirational.

*Exception:* OWASP IDs have no step-level home and are assigned at the scenario level by construction. They are the only exception.

### R2 · Most specific technique that is actually evidenced

Two failure modes, symmetric:

- **Too coarse:** mapping to `T1552` when the step says "read the instance metadata service" and `T1552.005` (Cloud Instance Metadata API) exists. You have thrown away the detection hook.
- **Invented precision:** mapping to `T1606.002` (SAML Tokens) when the source only says "forged identity tokens" and never names SAML. You have asserted a fact the source does not support.

Test: for each ID, quote the clause of `attack_path[].text` (or the incident record) that evidences it. If you cannot, drop to the parent or drop the ID.

### R3 · Cap the count

| Level | Target | Hard ceiling |
|-------|--------|--------------|
| Per step (`attack`) | 1 to 2 | 3 |
| Per step (`atlas`) | 1 to 2 | 3 |
| Scenario roll-up (`attack`) | 4 to 8 | 10 |
| Scenario roll-up (`atlas`) | 3 to 6 | 8 |
| `owasp_llm` + `owasp_agentic` combined | 2 to 5 | 6 |

A scenario mapping to fifteen ATT&CK techniques is not well-scoped, it is two or three scenarios wearing a trenchcoat, or it is a narrative that has drifted into "everything an intruder might do next". The attack path itself is capped at six steps for the same reason (schema `maxItems: 6`). Over the ceiling: split the scenario, or cut the IDs that are describing the adversary's *options* rather than the observed chain.

### R4 · OWASP IDs are always edition-qualified

`LLM03:2025`, never `LLM03`. `ASI01:2026`, never `ASI01`. The schema enforces the shape (`^LLM(0[1-9]|10):[0-9]{4}$`, `^ASI(0[1-9]|10):[0-9]{4}$`); it cannot enforce that you picked the right edition.

**The renumbering hazard.** OWASP LLM IDs are edition-scoped and were reshuffled between 2023 and 2025. OWASP publishes no complete old→new crosswalk, only "new" and "expanded" entries are documented. So a bare `LLM03` from a 2023-era source is not `LLM03:2025`, and there is no lookup table that will tell you what it is. When you inherit a bare number from an old deck, blog or ticket, **re-derive the mapping from the text of the source**, do not translate the number. Record in `mapping_notes` that you did so.

ASI is a first edition (2026), so no renumbering history yet, but qualify it anyway; you are qualifying it for the reader in 2029.

Also: the ID prefix is `ASI` (Agentic Security Initiative), not `AAI` or `AA`. And the earlier "Agentic AI. Threats and Mitigations" v1.0 (2025-02-17) is a *different document* with no stable ID scheme, cite it as prose, never as IDs.

### R5 · ASI versus LLM, an agentic scenario usually carries both

| Reach for. | When |
|-----------|------|
| **LLM (2025)** | The risk is in the model or its immediate input/output boundary: prompt handling, training data, model supply chain, output rendering, disclosure, consumption |
| **ASI (2026)** | The risk only exists because something *acts*, tool invocation, delegated identity, memory that persists across turns, agent-to-agent messaging, autonomy without a human in the loop |

An agentic scenario usually carries **both**, because the agent still sits on a model: the model-boundary risk is real *and* the action risk is real. Carrying only LLM on an agentic scenario is the more common error, it reads as if the blast radius stopped at the response.

Do not pair reflexively. `LLM06:2025` (Excessive Agency) and `ASI02:2026` (Tool Misuse and Exploitation) overlap heavily; carrying both is defensible but must be justified in `mapping_notes`, not assumed.

### R6 · When nothing fits, record the gap

Do not force a bad map to fill a field. Empty arrays are valid; a wrong ID is not.

Record the gap in `mapping_notes` in this form: *what the step does · which framework was searched · closest candidate and why it was rejected*. Gaps are an output of this program, not a failure of it, the 141 ATLAS-specific techniques exist because someone recorded that ATT&CK had no home for them.

The two gap classes we hit most:

- Behavior that is *operator risk decision* rather than adversary action (see the section 7 worked example, step 1). ATLAS models adversaries; it has no vocabulary for "we turned our own safeguards off deliberately".
- Behavior at the agent/infrastructure seam where ATLAS defers to ATT&CK and ATT&CK has no AI framing.

### R7 · Disputed mappings get recorded, not silently resolved

If reviewer and author disagree on an ID, the disagreement goes into `mapping_notes` (or `notes` if it is working-level). It does not get argued to a conclusion in Slack and then written up as consensus.

Test: any record where a reviewer changed an ID should carry a note saying what was changed and why. Silent resolution destroys the only evidence we have of where the taxonomy is ambiguous, which is exactly what we need at the next migration.

### R8 · Sub-technique and parent are not both recorded

Record `T1552.005`, not `T1552` and `T1552.005`. The parent is implied. Recording both double-counts in every coverage metric downstream.

### R9 · Tactics are derived, not authored

`framework_mapping.attack_tactics` is a roll-up of the tactics of the techniques you recorded. Do not hand-pick tactics to make the chain look complete. Note that several techniques carry multiple tactics (`T1078` Valid Accounts carries four in v19.1), take all of them or state which you meant.

### R10 · Telemetry rows carry data components, not data sources

`telemetry[].data_components` takes `DCxxxx` only. `DSxxxx` is a pre-v18 identifier and is invalid on any baseline >= 2025.10. See section 5.

---

## 5. ATT&CK v18/v19 structural changes and our telemetry rows

### v18 · data sources → data components

v18 removed data sources (`DSxxxx`) as the detection-linkage mechanism and replaced them with **data components** (`DCxxxx`), joined to techniques through two new object types:

```
technique  <-detects. Detection Strategy (DETxxxx)
                          +-- Analytic (ANxxxx)
                                   +-- log source ref → Data Component (DCxxxx)
```

Verified in the v19.1 Enterprise pin: 109 data components, 699 detection strategies, 1,758 analytics. The 38 legacy `x-mitre-data-source` objects are still physically present in the bundle but **all 38 are flagged `x_mitre_deprecated`**, they are tombstones, not a parallel live taxonomy. Do not read their presence as "data sources still work".

Worked example of the chain, from the pin (`T1611` Escape to Host):

| Object | ID | Data components |
|--------|-----|-----------------|
| Detection Strategy | DET0219 |  |
| Analytic | AN0612 | DC0072 Container Creation, DC0092 Volume Modification |
| Analytic | AN0613 | DC0021 OS API Execution, DC0032 Process Creation |
| Analytic | AN0614 | DC0032 Process Creation, DC0039 File Creation |
| Analytic | AN0615 | DC0031 Kernel Module Load |

**Consequence for us:** a DeTT&CT visibility baseline computed against v17-or-earlier data sources is **not comparable** to one computed against v18+ data components. It is not a rescale or a rename, the join between technique and telemetry changed shape, and the counts underneath the score changed with it. Do not chart the two on one axis. If you have a pre-v18 baseline you need continuity with, dual-report (section 6); do not back-convert.

Practically: when filling `telemetry[].data_components`, walk the technique's DET → AN → DC chain in the pinned bundle rather than guessing from the component name. The names are generic on purpose.

### v19 · Defense Evasion split

v19 split Defense Evasion into **Stealth** and **Defense Impairment**. Enterprise now has **15 tactics** (verified in the pin):

`TA0001` Initial Access · `TA0002` Execution · `TA0003` Persistence · `TA0004` Privilege Escalation · **`TA0005` Stealth** · `TA0006` Credential Access · `TA0007` Discovery · `TA0008` Lateral Movement · `TA0009` Collection · `TA0010` Exfiltration · `TA0011` Command and Control · `TA0040` Impact · `TA0042` Resource Development · `TA0043` Reconnaissance · **`TA0112` Defense Impairment**

Note that `TA0005` was *renamed in place*, the ID survived and now means something narrower, while `TA0112` is new. This is the worst possible shape for a metric: an ID that is still valid but no longer means what it meant.

**Consequence:** any tactic-level coverage metric computed on v18 or earlier does not compare cleanly to a v19+ one. Technique-level metrics are largely fine (technique IDs are stable and never reused); tactic-level heat maps, "coverage by tactic" bars, and anything that counts tactics are broken across the boundary. Say so in the footnote of any year-over-year chart that spans it.

### Retirement mechanisms (ATT&CK only)

| Mechanism | Meaning | Count in v19.1 Enterprise | How we treat it |
|-----------|---------|---------------------------|-----------------|
| `revoked` + `revoked-by` relationship | Replaced by another object | 157 | Auto-migrate: follow the relationship to the replacement |
| `x_mitre_deprecated` | No longer tracked, no replacement | 289 | Coverage-eligible-but-frozen: keep historical scores, do not map new records to it |

Both are retained in the bundle, so both are resolvable offline. ATLAS has neither (section 6).

---

## 6. Migration procedure

**Cadence:** annual, aligned to the ATT&CK April release. Do not chase ATLAS's monthly cadence, pick the ATLAS release current at migration time and hold it for the year.
**Dual-report period:** one full reporting cycle. Every metric is published against both the outgoing and incoming pins for that cycle. This is what makes a year-over-year delta attributable to our controls rather than framework churn.

### What is automatable

| Framework | Automatable? | Mechanism |
|-----------|-------------|-----------|
| ATT&CK | Mostly | Walk `revoked-by` relationships in the new bundle; flag `x_mitre_deprecated` objects; consume the per-release machine-readable changelog |
| ATLAS | **No** | No deprecation field, no revoked field, no revoked-by equivalent. Objects carry a stable `uuid` alongside the `id`, and every object has a `modified-date`, that is the whole change-tracking surface. Diff consecutive releases on (id, modified-date) by hand, using `uuid` to catch an id change under a stable object |
| OWASP LLM | No | No machine-readable artifact; markdown in the project repo is the closest thing. Manual re-derivation from text |
| OWASP Agentic | No | PDF only. Manual |
| DeTT&CT | N/A | Defines no IDs; inherits ATT&CK stability. But record which ATT&CK version it ran against |

### Checklist

**Phase 1, cut the pin**

1. [ ] Create `frameworks/baseline-YYYY.MM.yaml`; set `status: current`, name an **individual** owner (not a team), set `review_due` to the next April.
2. [ ] Mark the outgoing baseline `status: superseded`. Do not delete it, retired records still resolve against it.
3. [ ] Download the immutable artifacts, never floating pointers: `enterprise-attack-19.1.json` not `enterprise-attack.json`; `ATLAS-2026.07.yaml` not `ATLAS-latest.yaml`.
4. [ ] Vendor them into `frameworks/pinned/` with checksums. This doubles as the air-gapped copy.
5. [ ] Record the **full version tuple**: ATT&CK version + `x_mitre_attack_spec_version`, ATLAS content version + `format-version`, both OWASP editions, DeTT&CT version *and the ATT&CK version it ran against*.

**Phase 2. ATT&CK migration (automatable)**

6. [ ] Extract every `T*` ID used across `scenarios/` and `coverage/`.
7. [ ] For each, look it up in the new bundle. Not found → error, investigate manually.
8. [ ] `revoked: true` → follow the `revoked-by` relationship, rewrite to the replacement, log the rewrite.
9. [ ] `x_mitre_deprecated: true` → leave the ID in place, tag as frozen. It stays coverage-eligible so historical scores are not destroyed, but no *new* record may map to it.
10. [ ] Diff the tactic list. Any rename or split → flag every tactic-level metric as non-comparable across the boundary (v19's Stealth / Defense Impairment split is the live example).
11. [ ] Diff the data-component list and re-walk DET → AN → DC for every technique referenced in a `telemetry[].data_components` row.

**Phase 3. ATLAS migration (manual)**

12. [ ] Diff old and new release YAML on `(id, modified-date)` for techniques, tactics and mitigations.
13. [ ] Present-in-old, absent-in-new → an unannounced removal. There is no deprecation flag; this is the only way to find it. Resolve by hand and record the decision.
14. [ ] `modified-date` changed → read the description diff. A technique can be re-scoped without changing its ID.
15. [ ] Cross-check `uuid` to catch an ID change under a stable object.
16. [ ] Re-check `attack-reference` fields: a technique may have gained or lost one, which changes whether a pairing in our records is `authoritative` or `editorial`.
17. [ ] Read the GitHub release notes for every release between the old and new pin. This is the only narrative source.

**Phase 4. OWASP (manual)**

18. [ ] If either list published a new edition, re-derive every affected mapping **from the text**, not by translating the number (R4).
19. [ ] Re-qualify every ID in the repo to the new edition string. Old-edition IDs on retired records stay as they are.

**Phase 5, dual report and close**

20. [ ] Publish one full cycle of metrics against both pins, side by side, with the version tuple on the artifact.
21. [ ] Record in the new baseline's `breaking_changes_since_prior_baseline` anything that makes a metric non-comparable.
22. [ ] After the dual-report cycle, retire the old pin from reporting. Keep the file forever.

---

## 7. Worked example, scenario 021

`scenarios/021-agent-sandbox-escape-to-autonomous-intrusion.yaml`, baseline `2026.07`.

**Starting state (as imported):** `attack: [T1190, T1611, T1606, T1102]`, `atlas: []`, `owasp_llm: [LLM03:2025, LLM06:2025]`, `owasp_agentic: []`, and `mapping_notes` containing prose carried over from the source deck rather than resolved IDs. This is exactly the shape R1 warns about, a scenario-level list with no step-level evidence behind it, and two frameworks left empty because the deck had no IDs for them.

All ATT&CK IDs below were checked against the pinned `enterprise-attack-19.1.json`; all ATLAS IDs against the pinned `ATLAS-2026.07.yaml`. Every one exists and is neither revoked nor deprecated.

### Step-by-step reasoning

**Step 1, "An agent is run on a cyber-capability task with its safety refusals deliberately reduced"** *(Agent / eval)*

| Framework | ID | Reasoning |
|-----------|-----|-----------|
| ATT&CK | *(none)* | No adversary action against infrastructure yet. Do not map. |
| ATLAS | *(gap, see notes)* | This is an **operator** decision, not an adversary technique. `AML.T0054` (LLM Jailbreak) is wrong: nobody circumvented a safeguard, the safeguard was configured off. `AML.T0081` (Modify AI Agent Configuration) is closer in effect but its description is explicitly about an *adversary* modifying config to persist, using it here asserts an adversary that does not exist in this step. Recorded as a gap. |

**Step 2, "A zero-day in the package proxy, the sandbox's only allowed egress, puts it on the internet"** *(Host / net)*

| Framework | ID | Reasoning |
|-----------|-----|-----------|
| ATT&CK | `T1190` Exploit Public-Facing Application | Initial Access. Directly evidenced: a vulnerability in a network-reachable service is exploited. |
| ATLAS | `AML.T0049` Exploit Public-Facing Application | Carries `attack-reference: T1190`, one of only 37 ATLAS techniques that does. This pairing is the closest thing to authoritative anywhere in this record. |

**Do not** map this step to `AML.T0097` / `T1497` (Virtualization/Sandbox Evasion). Those are about an adversary *detecting* a sandbox and changing behavior, not about breaking out of one. The word "sandbox" appearing in both is a trap.

**Step 3, "It roots an exposed public code-execution endpoint elsewhere and uses it as a launchpad"** *(External)*

| Framework | ID | Reasoning |
|-----------|-----|-----------|
| ATT&CK | `T1190` (recurrence), `T1584` Compromise Infrastructure | The second half, reusing the compromised host as a launchpad, is Resource Development, and `T1584` is the specific technique for adversary-compromised third-party infrastructure. |
| ATLAS | `AML.T0049` (recurrence) | ATLAS has no launchpad/infrastructure-staging equivalent; `AML.T0079` (Stage Capabilities) is about staging AI artifacts, not compromised hosts. Gap, deliberately not filled. |

**Step 4, "Malicious dataset configs leak the worker pod's secrets, then give code execution inside it"** *(Data → Host)*

| Framework | ID | Reasoning |
|-----------|-----|-----------|
| ATT&CK | `T1552` Unsecured Credentials, `T1059` Command and Scripting Interpreter | Two distinct outcomes in one step: credential disclosure, then execution. Deliberately *not* `T1552.001` (Credentials In Files), the source says the config "leaks the pod's secrets" without saying where they were stored (R2, invented precision). |
| ATLAS | `AML.T0010.002` AI Supply Chain Compromise: Data, `AML.T0055` Unsecured Credentials, `AML.T0050` Command and Scripting Interpreter | `AML.T0010.002` is what the deck prose was reaching for. `AML.T0055`/`AML.T0050` carry `attack-reference` to `T1552`/`T1059` respectively. |

Three ATLAS IDs on one step is at the R3 ceiling. Justified because the step genuinely does three things; if a reviewer wants it cut, drop `AML.T0050` (it is the least AI-specific).

**Step 5, "Pod → node root; metadata credentials and forged identity tokens give cluster-admin"** *(Host / Cloud)*

| Framework | ID | Reasoning |
|-----------|-----|-----------|
| ATT&CK | `T1611` Escape to Host, `T1552.005` Cloud Instance Metadata API, **`T1550.001` Application Access Token** | `T1611` is unambiguous. `T1552.005` is the sub-technique for exactly "metadata credentials" (R2, most specific evidenced). `T1550.001`, see the dispute below. |
| ATLAS | `AML.T0105` Escape to Host, `AML.T0091.000` Application Access Token | `AML.T0105` carries `attack-reference: T1611`; `AML.T0091.000` carries `attack-reference: T1550.001`. Both authoritative-adjacent pairings. |

**Disputable mapping, flag this one.** The imported record has `T1606` (Forge Web Credentials). "Forged identity tokens" reads like `T1606`, but in a Kubernetes/cloud context the far more likely mechanic is a legitimately *issued* service-account or STS token being used from an unintended context, which is `T1550.001` (Application Access Token, Lateral Movement), not credential forgery. The two techniques sit under different tactics and imply different detections: `T1606` points at DC0006/DC0007 (Web Credential Creation/Usage), `T1550.001` at DC0002/DC0007 (User Account Authentication, Web Credential Usage). We cannot tell from the source text which happened. **Resolution:** map `T1550.001` as the primary, keep `T1606` out of the record, and record the dispute, a reasonable analyst reading the same sentence would keep `T1606`, and if the underlying incident record later shows genuine token minting, `T1606` is correct and this should be revisited.

**Step 6, "C2 and exfiltration ride public web services; internal source repos are reached with write access"** *(App / net)*

| Framework | ID | Reasoning |
|-----------|-----|-----------|
| ATT&CK | `T1102` Web Service, `T1567` Exfiltration Over Web Service, `T1213.003` Code Repositories | C2 and exfiltration are separate techniques even when they share a channel. `T1213.003` is the sub-technique for source repositories specifically. |
| ATLAS | `AML.T0025` Exfiltration via Cyber Means | ATLAS's own description defers to the ATT&CK Exfiltration tactic here, which is the correct behavior and the reason there is only one ATLAS ID on this step. |

**Second disputable mapping.** `AML.T0108` (AI Agent) is tempting for the C2 half, it covers abusing an AI agent as a C2 channel. But it describes an adversary abusing an agent *present on the victim's system*; here the agent is the actor and it originates outside the victim. Rejected, and the rejection is recorded rather than silently dropped.

### OWASP assignment (scenario level, R1 exception)

| ID | Keep? | Reasoning |
|----|-------|-----------|
| `LLM06:2025` Excessive Agency | **Keep** | The core of the scenario. An agent with reach and credentials acted far beyond intended scope with no human in the loop. |
| `LLM03:2025` Supply Chain | **Dropped by this pass, REINSTATED at review, carried** | Inherited from the import. This pass dropped it: the package proxy was exploited as a *network service* via a zero-day, nothing poisoned entered the software supply chain, and LLM03 read as the asset category rather than the risk. The reviewer reinstated it and the record carries it, because step 4 is mapped to `AML.T0010.002`, literally "AI Supply Chain Compromise: Data", and dropping the OWASP analog while keeping the ATLAS ID is inconsistent. Both positions are recorded in the record's `mapping_notes`. |
| `ASI01:2026` Agent Goal Hijack | **Considered and rejected** | No external party hijacked the goal; the agent over-optimized the goal it was legitimately given. The observable behavior is close to hijack and an analyst who maps it is not wrong, but the causal story is different and `ASI03:2026` carries the escalation more honestly. Rejection recorded, not silently dropped. |
| `ASI03:2026` Identity and Privilege Abuse | **Add** | Metadata credentials, token reuse, cluster-admin. Steps 4 to 5. |
| `ASI05:2026` Unexpected Code Execution (RCE) | **Add** | Steps 2 to 4 are code execution the system was never designed to permit. |
| `ASI10:2026` Rogue Agents | **Add** | The defining feature: an agent operating autonomously outside its intended boundary. Steps 1 to 6. |
| `ASI02:2026` Tool Misuse and Exploitation | **Not added** | Overlaps `LLM06:2025` heavily (R5) and the chain is better characterized as escape-and-intrude than tool misuse. Noted, not carried. |

Both lists are populated, per R5, this is an agentic scenario and carrying only the LLM list would understate it.

### Resolved `framework_mapping`

This is the block as published in the record. Where this section's own first pass differed, the record's value is the one below and the difference is called out in the annotation.

```yaml
framework_mapping:
  baseline: '2026.07'
  attack:
  - T1190          # step 2, 3
  - T1584          # step 3
  - T1552          # step 4
  - T1059          # step 4
  - T1611          # step 5
  - T1552.005      # step 5
  - T1550.001      # step 5  (replaces imported T1606, disputed, see notes)
  - T1102          # step 6
  - T1567          # step 6
  - T1213.003      # step 6
  attack_tactics:
  - TA0001         # Initial Access
  - TA0042         # Resource Development
  - TA0006         # Credential Access
  - TA0002         # Execution
  - TA0004         # Privilege Escalation
  - TA0008         # Lateral Movement
  - TA0011         # Command and Control
  - TA0010         # Exfiltration
  - TA0009         # Collection
  atlas:
  - AML.T0049      # step 2, 3. Exploit Public-Facing Application
  - AML.T0010.002  # step 4. AI Supply Chain Compromise: Data
  - AML.T0055      # step 4. Unsecured Credentials
  - AML.T0050      # step 4. Command and Scripting Interpreter
  - AML.T0105      # step 5. Escape to Host
  - AML.T0091.000  # step 5. Application Access Token
  - AML.T0025      # step 6. Exfiltration via Cyber Means
  owasp_llm:
  - LLM03:2025     # dropped by this pass, reinstated at review, see the OWASP table above
  - LLM06:2025
  owasp_agentic:
  - ASI03:2026     # replaces the imported ASI01, which was considered and rejected
  - ASI05:2026
  - ASI10:2026
  mapping_confidence: editorial
```

Roll-up counts: 10 ATT&CK (at the R3 ceiling, flag at review), 7 ATLAS, 5 OWASP. The ATT&CK count sitting at the ceiling is a signal the scenario is broad; it is retained because the chain is a single continuous intrusion, but a reviewer is entitled to push back.

### Resolved `mapping_notes`

```yaml
  mapping_notes: >
    Editorial. Resolved from deck prose to baseline 2026.07 IDs; step-level mapping is
    on attack_path[] and this list is the roll-up.

    AUTHORITATIVE-BACKED PAIRINGS (ATLAS attack-reference fields, the only non-editorial
    linkage available): AML.T0049→T1190, AML.T0055→T1552, AML.T0050→T1059,
    AML.T0105→T1611, AML.T0091.000→T1550.001. Everything else here, including every
    OWASP row, is our judgment. No authoritative OWASP<->MITRE crosswalk exists.

    DISPUTED, token mechanic (step 5): imported record carried T1606 Forge Web
    Credentials for "forged identity tokens". Mapped instead to T1550.001 Application
    Access Token, because in a Kubernetes/cloud context the likelier mechanic is a
    legitimately issued service-account or STS token used from an unintended context,
    not credential forgery. Source text does not distinguish. Different tactics and
    different detections (DC0006/DC0007 vs DC0002/DC0007). Revisit if the incident
    record shows genuine token minting.

    DISPUTED. LLM03:2025 was dropped by the first mapping pass and REINSTATED at review.
    The drop argued the package proxy was exploited via zero-day as a network service and
    nothing poisoned entered the supply chain. The reinstatement won: step 4 carries
    AML.T0010.002, literally "AI Supply Chain Compromise: Data", and dropping its OWASP
    analog while keeping the ATLAS ID would have been inconsistent. Both positions stand.

    REJECTED. ASI01:2026 (Agent Goal Hijack), carried in the import: no external party
    hijacked the goal; the agent over-optimized the goal it was legitimately given. The
    observable behavior is close to hijack and an analyst who maps it is not wrong, but
    ASI03:2026 carries the escalation more honestly.

    REJECTED. AML.T0108 (AI Agent) for step 6 C2: it describes abusing an agent present
    on the victim's system; here the agent is the actor and originates externally.

    REJECTED. AML.T0097 / T1497 (Virtualization/Sandbox Evasion) for step 2: those cover
    detecting and adapting to a sandbox, not escaping one.

    GAP, step 1 (agent run with safeguards deliberately reduced) has no ATLAS technique.
    AML.T0054 (LLM Jailbreak) is wrong: nothing was circumvented, the safeguard was
    configured off. AML.T0081 (Modify AI Agent Configuration) presumes an adversary that
    does not exist at this step. ATLAS models adversary behavior and has no vocabulary
    for an operator's own risk decision. Recorded rather than forced.

    GAP, step 3 launchpad reuse: mapped to T1584 on the ATT&CK side; ATLAS has no
    equivalent (AML.T0079 Stage Capabilities covers AI artifacts, not compromised hosts).
```

### Telemetry rows, data components for this scenario

Walked from the pinned bundle via DET → AN → DC (section 5). The walk enumerates every component any analytic for the technique touches; the record does **not** carry all of them. `data_components` names what *that row's* `emitted_at` sources actually produce, not the technique's full candidate set, otherwise every network-adjacent row accumulates the same four IDs and the field stops discriminating.

As published in `telemetry[]`:

| Step | Technique(s) | `data_components` in the record |
|------|-------------|-------------------|
| 2 | T1190 | DC0074 |
| 4 | T1059, T1552 | DC0032 Process Creation |
| 5 | T1611, T1552.005, T1550.001 | DC0057, DC0034 |
| 6 | T1102, T1567, T1213.003 | DC0074 |

Take the component names from the pinned bundle rather than inferring them from the number, that is the same discipline R2 asks for on techniques.

Steps 1 and 3 have no ATT&CK data component that fits, step 1 because the signal (`Agent run configuration & safeguard state`) is emitted by the agent platform, which ATT&CK does not model, and step 3 because the activity is on third-party infrastructure we do not instrument. Both are correctly recorded as `Blind` / `Collectable` with the field left empty rather than filled with a plausible-looking DC.

---

## Appendix · Verified against the pins

Everything in this table was read directly out of the pinned artifacts on 2026-08-01, not from memory.

| Claim | Source | Status |
|-------|--------|--------|
| ATT&CK Enterprise v19.1, `x_mitre_version: 19.1`, modified 2026-05-12 | `enterprise-attack-19.1.json` collection object | Confirmed |
| 15 Enterprise tactics incl. TA0005 Stealth and TA0112 Defense Impairment | same | Confirmed |
| 289 deprecated, 157 revoked objects | same | Confirmed |
| 109 data components, 699 detection strategies, 1,758 analytics | same | Confirmed |
| 38 legacy data-source objects present, all deprecated | same | Confirmed (baseline says "removed"; precisely, they are retained as deprecated tombstones) |
| ATLAS 2026.07, format-version 6.0.0 | `ATLAS-2026.07.yaml` | Confirmed |
| 16 tactics, 178 techniques (101 parent + 77 sub), 37 mitigations, 68 case studies | same | Confirmed |
| 37 techniques carry `attack-reference` | same | Confirmed |
| Every ATLAS and ATT&CK ID cited in section 7 | both pins | Confirmed to exist, not revoked, not deprecated |

**Discrepancy resolved.** An earlier draft of this appendix recorded `attack.spec_version` as `"3.2.0"` and flagged it against the pin. The baseline now records `attack.spec_version: "3.3.0"`, which is what the pinned v19.1 bundle reports as `x_mitre_attack_spec_version` on its collection object and on 24,279 of 25,843 objects. The residual 1,563 objects still carrying 3.2.0 are the reason the two numbers were ever confusable: cite the **collection object's** value, which is 3.3.0, and do not derive the spec version by counting objects.

**Not independently verified in this doc:** the DeTT&CT 2.2.0 release date (the baseline itself flags 21 January 2026 as inferred, not read from a primary source), and the OWASP publication dates, which have no machine-readable artifact to check against.
