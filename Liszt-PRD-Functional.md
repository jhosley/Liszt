# Liszt: AI Attack Observability, the Stakeholder Edition

A functional description for security leaders deciding whether this program deserves attention, participation, and budget.

---

## 1. Executive summary

Liszt answers one question that no dashboard in the security stack currently answers with evidence behind it: **if this attack happened to us, would we actually see it, at which step, and who owns the part we cannot see?**

Every security organization already reports coverage. The problem is where those numbers come from. A coverage percentage on a slide can be authored, and usually is. Someone decides the number, builds the slide, and the number survives because nobody can check it. When the estate changes, the slide does not. When the author changes roles, the reasoning behind the number leaves with them. When an auditor or an incident asks "why did you believe you could see this," there is nothing underneath the percentage but a memory of a meeting.

Liszt inverts that. It is a catalog of attack scenarios against AI systems, currently 21 scenarios and 12 use cases, of which four scenarios have so far been worked through to the full published, fully scored bar, and where every claim about what we can see is computed, not asserted. Each step of each attack chain gets two scores from the people who actually own the systems involved: would we see the signal this step produces, and does anything alert on it. From those two scores, a single rule computes a verdict for the step: **Have** (we would notice, because something alerts), **Collectable** (the data lands in a log, but nothing fires, so we could only reconstruct the attack afterward), or **Blind** (nothing produces the signal at all). Nobody writes the verdict by hand. The validation tooling recomputes it on every check and refuses records where the verdict does not match the scores.

Three properties make the resulting numbers trustworthy in a way slide numbers are not:

- **The verdict is computed from scores given by system owners**, the only people who actually know, and it is recomputed automatically every time the records are checked. There is no place to type in a better-looking answer.
- **Improvement only counts when it carries evidence a third party can re-run**, such as a saved search that returns rows or a detection rule with test results, **and a ticket naming the work that caused the change.** A number that went up without a ticket behind it is reported separately, as a rescore, not as progress.
- **The claims get tested.** The program runs controlled exercises where the predicted verdicts are frozen and committed before the exercise starts, so hindsight cannot rewrite them. The resulting scorecard includes a number called the optimism index, which measures whether the program systematically believes it sees more than it does. That loop has been demonstrated end to end on a real published scenario, and it found three defects in the record that no amount of careful reading would have found.

The catalog is grounded in public frameworks, pinned to specific versions (a baseline labeled 2026.07) so that year-over-year comparisons measure our estate and not a vendor's release schedule. What this document asks of each function, and what each function gets back, is laid out in section 4. The asks at the end are modest: sponsorship, one named owner for the framework baseline, participation of system owners in scoring sessions, and agreement on a pilot scope.

---

## 2. How it works

Liszt runs a loop. Each pass through the loop is plain enough to describe in a paragraph per stage.

**A scenario comes in.** The trigger is a real incident that happened to someone, a piece of threat research, or an analyst's hypothesis about our own environment. Each record is labeled honestly by the strength of its evidence: seen in the wild, seen in research, or a hypothetical worst case that has never been observed, kept deliberately as a stress test. A hypothesis is never dressed up as an observed event.

**It becomes an attack chain.** An analyst works the raw material into three to six ordered moves, where each move follows mechanically from the one before it. For every move, the analyst writes down the observable signal it would produce: not a product name, but the actual thing that would be emitted, such as "egress traffic from a sandboxed workload" or "a workload container created with elevated privileges." A move that produces no observable signal is not a move; it is narration, and it gets cut. An independent reviewer, never the author, must approve the record before it counts.

**The people who own the systems score each signal.** For every signal, the owning team answers two questions on simple numeric scales borrowed from an open method called DeTT&CT (a public framework for scoring detection coverage, used here so the scales mean the same thing everywhere): would we see it (is the data there and usable), and does anything alert on it. These sessions are the heart of the program, because only the owners know the real answers.

**The verdict is computed.** One rule, living in exactly one place in the tooling, turns the two scores into Have, Collectable, or Blind. If the scores and a recorded verdict disagree, the check fails. An unscored row gets no verdict at all; it is treated as "nobody has looked yet," which is deliberately kept distinct from "somebody looked and found nothing."

**Every gap gets an owner and a ticket.** A Blind or Collectable step must name the team that would accept the work, and a backlog reference once the work is accepted. The program's documentation is blunt about why: an unowned gap never closes, because a gap is closed by appearing on somebody's roadmap, not by appearing on a slide.

**Use cases turn signals into decisions.** A use case is a record describing how signals from one or more scenarios compose into something a person acts on: what triggers it, what corroborating evidence arrives with it, who receives it, what the first decision is, and, stated just as plainly, what its limits are and what it will never catch.

**Tests check whether we believed our own claims.** For a scenario that is ready, the tooling emits a test specification and a prediction file stating exactly what we claim would be seen at each step. The prediction is committed to the repository before the test runs; the commit timestamp is the seal. A controlled exercise then reproduces the attack behaviors in a bounded lab, an independent observer records what actually appeared, and a scorer compares observation to prediction.

**The record improves attributably.** Test findings and closed tickets flow back into the records as proposed changes that a person reviews and applies, each one citing the run or ticket that caused it. Next quarter's numbers can therefore be traced, change by change, to the work that moved them.

---

## 3. The three numbers, and who they serve

Liszt reports three metric families. They are always reported side by side and never blended into one composite score, because a composite hides exactly the case that matters: good-looking coverage with nothing behind it.

**Coverage, for engineering.** How much of each attack chain we can actually see, computed step by step. Have, Collectable, and Blind proportions, always accompanied by a completeness figure saying how many steps were assessed at all. For a detection engineering team this is a work queue: Collectable rows are the cheap wins, since the data is already landing and only a rule is missing, and Blind rows are the instrumentation asks.

**Exposure, for risk.** Which scenarios marked as current priorities still have Blind steps, and where in the chain those blind steps sit. A blind first step means the attack starts invisibly; a blind last step means it ends invisibly. Those are different problems. Exposure also reports the escalation lists that matter to a risk owner: gaps with no owner, and gaps with no ticket.

**Maturity, for the program office.** Whether the process itself is working: are records independently reviewed, fully scored, owned, evidenced, and connected to funded work. Maturity moves independently of the other two, on purpose. A scenario can be entirely Blind and fully mature; that combination means we know precisely what we cannot see, a named team owns it, and it is on a backlog. That is not a failure state. Unowned blindness is the failure state.

Three honesty properties are built into the arithmetic, and leaders should treat them as features they are buying:

- **An unscored row is never averaged in.** Scoring nothing and scoring badly must never produce the same number. If half the steps were never assessed, the coverage figure says so next to itself, rather than silently treating the unknown as zero and manufacturing precision that was never earned.
- **Predictions are frozen before tests.** The prediction file is committed before a test runs, so a wrong claim stays visibly wrong. Hindsight cannot quietly rewrite what the program said it would see.
- **The test scorecard reports an optimism index.** This is the average difference between what we predicted and what was observed, signed. A positive value means the program systematically believes it sees more than it does. For a leader, this is the single number that says whether the program believes its own press. A program can be accurate on average and still dangerous in one direction, and only this number shows it.

---

## 4. Stakeholders: what each function gives, and what each function gets

This is the heart of the document. Liszt only produces trustworthy numbers because the people who own the systems supply the inputs, so every function below is either contributing something only it can contribute, receiving something it cannot get elsewhere, or both.

### 4.1 Cybersecurity operations: the security operations center (SOC) and detection engineering

**They contribute.** The two scores on every signal their systems emit, and the exact source names: which index, which log, which rule. Only the operators of the detection stack know whether a rule really fires and where the data really lands, and the program is explicit that a score produced without them is provisional until they confirm it.

**They receive.** Use cases with a named trigger, composed corroborating evidence, stated limits, and a delivery phase, instead of lone alerts nobody triages. The companion use case to the reference scenario is the model: when the strongest detection in the chain fires, the operator receives one case holding that detection, the egress history of the workload that produced it, and any outbound transfers already recorded, instead of three alerts in three queues. Every use case also states plainly what it will never catch, so the SOC is never asked to defend a claim the record does not make.

**What changes in practice.** Detection work stops being reactive rule-writing against whatever arrived this week. The Collectable list is a ranked queue of detections where the data is already flowing and only the rule is missing, each one tied to a specific step of a specific attack the organization has decided matters.

### 4.2 Purple teams

Purple teams are the joint exercises where offensive and defensive staff work together to test whether attacks are seen. They are primarily contributors here.

**They contribute.** Scenario authoring from exercise experience, test design, and the runs themselves.

**They receive.** A library where every exercise lands as a permanent, comparable record instead of a slide deck that ages in a shared drive, and a sealed prediction loop that turns an exercise into a calibration number. Today, a purple team exercise produces findings; whether those findings change anything depends on who is in the room. Under Liszt, the exercise starts from a committed prediction of what will be seen, and ends with a scorecard: exact match rate, the optimism index, how often we named the right source system, and the count of signals nobody predicted. The demonstrated exercise on the reference scenario surfaced exactly the kinds of findings this loop exists for: a step scored Blind that was quietly emitting a usable signal all along, a step where the visibility claim was right but the named source system was wrong (an investigator following the record would have searched an empty index), and a step whose score rested on an assumption about a logging system that turned out to be false.

**What changes in practice.** Exercises stop being events and become measurements. Two exercises a year apart are comparable, because the records, the scoring rule, and the framework versions underneath them are the same.

### 4.3 Penetration testers

**They contribute.** Findings that become scenarios, and test execution at the currently enabled rung of the autonomy ladder (explained under Legal, below; today that means contained lab environments only).

**They receive.** Scoped, authorized test specifications with explicit target allowlists, time boxes, and stop conditions, generated from the record rather than negotiated from scratch each time. An empty allowlist means the run refuses to start. And they get something the trade rarely gets: a place where a finding changes a number instead of aging in a report. A pentest finding that becomes a scenario gets scored, gets owners, gets tickets, and shows up in next quarter's delta.

**What changes in practice.** Less time spent re-litigating scope and authorization per engagement, because the guardrails are structural, and a durable answer to the perennial question of what happened to last year's findings.

### 4.4 Infrastructure owners and engineers, including tools engineers for web application firewall (WAF) and endpoint platforms

This group spans cloud platform, data platform, network, identity, endpoint, and the engineers who operate security tooling such as web application firewalls and endpoint detection platforms. They are both contributors and beneficiaries, and the program does not work without them.

**They contribute.** The two scores and the source names, which only they know. Whether the Kubernetes audit log actually captures a particular event, whether a proxy log retains the field an investigation would need, whether a rule has ever produced a true positive: these facts live with the owning teams and nowhere else. The scoring sessions are where that knowledge enters the record.

**They receive.** An owned, ticketed gap list for their own systems, instead of a generic finding addressed to everyone and therefore no one. Each gap names the step of the attack it corresponds to, the signal that is missing, and the specific fix. And when their instrumentation investment lands, the record shows the tag move, with their ticket attached. That is evidence, presentable upward, that the spend produced the visibility it promised. In the reference scenario, each of the three gaps carries a named platform team and a specific backlog item; when the first of those tickets lands, coverage on that scenario moves from one half to two thirds and the change is attributable to that team and that ticket.

**What changes in practice.** Instrumentation requests arrive with a reason attached: this specific attack, this specific step, this specific blindness. Requests can be prioritized on evidence, and delivered work is visibly credited.

### 4.5 Global risk and compliance

**They receive.** Four things dashboards do not provide.

First, exposure reporting tied to named scenarios and named steps: not "coverage is 74 percent" but "these priority scenarios have blind steps, here is which step, here is who owns each one." Second, a maturity view that shows whether the process itself is healthy, independent of whether the current news is good. Third, an audit trail: every record carries who authored it, who independently reviewed it, when, and why each change happened, and metric snapshots are immutable, so the basis of any past claim survives. Fourth, a pinned framework vocabulary. The catalog maps to public frameworks: MITRE ATT&CK (the standard public catalog of attacker techniques, version 19.1), MITRE ATLAS (its counterpart for attacks on AI systems, version 2026.07), the OWASP lists of top risks for large language model applications (2025 edition) and for agentic AI systems (2026 edition), and DeTT&CT (version 2.2.0) for the scoring scales. All five are pinned to those versions in a recorded baseline, because two of these frameworks made breaking changes within the last eighteen months, and without pinning, a coverage change caused by a vendor renaming things is indistinguishable from a real change in the estate. Pinning is what makes numbers comparable year over year.

**What changes in practice.** Risk reporting on AI attack visibility stops depending on interviews and starts being a computation over records that audit can inspect, re-run, and challenge.

### 4.6 Office of the CISO, the chief information security officer

**They receive.** Defensible answers to the questions that only the top of the function gets asked: what can we see, what can we not see, who owns each gap, and what did we get for the instrumentation we paid for. That last question is the one that justifies any security program to whoever holds the budget, and it is answerable here only because the ticket reference is captured on every gap at the time, not reconstructed later. The answer names the ticket and the specific rows whose verdict changed after it landed.

The office also gets a coverage goal that means something. This document proposes a coverage goal of 80 percent. Such a goal is only meaningful if the denominator cannot be quietly reshaped. In Liszt it cannot: aggregate coverage is weighted by attack steps rather than by scenario, so splitting one scenario into two leaves the number essentially unchanged; retiring a scenario is a permanently visible event, never a silent deletion; and every published figure carries its own completeness companion, so coverage rising while assessment work falls is visible on the same page. The proposed 80 percent is a target over a denominator that resists manipulation by construction.

**What changes in practice.** When the board, a regulator, or a post-incident review asks "would you have seen this," the answer is a named scenario, computed verdicts per step, and an evidence trail, rather than an adjective.

### 4.7 Legal and peripheral risk functions

**They receive.** Documented, bounded, approved testing. The test specifications carry no exploit payloads at all; they reference published, reviewable emulation content by technique identifier. Every specification includes an explicit authorization block, an explicit target allowlist with no wildcards and no defaults, a time box, and stop conditions under which the run halts itself. Autonomy is governed by a ladder with three rungs: lab only, production observe, and production active. Only the lab rung is enabled today. The production rungs are fully specified and switched off, and they stay off until an approval path exists, with a named approver, measured evidence from the rung below, a stated blast radius, reversibility, and an off switch. No promotion happens by default or by drift.

They also receive records written to be read by a stranger a year later. The program's own quality bar for every record is that someone who was not in the room can reconstruct the reasoning without asking the author anything. Sources are tiered, conflicts between parties' public accounts are recorded verbatim as unresolved rather than smoothed into one narrative, and facts are verified against registries of record rather than press coverage. For a function that may one day need to produce these records in a dispute, that discipline is the difference between an asset and a liability.

**What changes in practice.** Security testing stops being an activity legal hears about afterward and becomes an activity with structural guardrails legal helped set, evidenced in the artifacts themselves.

### 4.8 The exchange on one screen

| Stakeholder | Gives | Gets |
|---|---|---|
| SOC and detection engineering | Scores and exact source names for detection systems | Use cases with named triggers, composed evidence, stated limits; a ranked queue of cheap detection wins |
| Purple teams | Scenario authoring, test design, runs | A permanent comparable exercise library; a sealed prediction loop that yields a calibration number |
| Penetration testers | Findings as scenarios; test execution in the lab | Scoped, authorized specs with allowlists, time boxes, stop conditions; findings that change a number |
| Infrastructure owners and tools engineers | The two scores and source names only they know | An owned, ticketed gap list per system; visible credit when instrumentation moves a verdict |
| Global risk and compliance | (consumer) | Exposure tied to named scenarios and steps; a process health view; a full audit trail; a pinned vocabulary for year-over-year comparison |
| Office of the CISO | (consumer) | Defensible answers on visibility, ownership, and return on instrumentation spend; a proposed 80 percent goal over a denominator that resists reshaping |
| Legal and peripheral risk | (consumer) | Bounded, payload-free, approved testing with an autonomy ladder; records a stranger can read a year later |

---

## 5. What the organization gets as a whole

Beyond any single function, five things accrue to the organization:

- **One shared vocabulary, pinned to public frameworks**, so that two teams, or two divisions, describing the same attack are describing it the same way, and this year's numbers are comparable with last year's.
- **Reporting that survives audit**, because every figure is a computation over inspectable records with named authors, independent reviewers, and immutable snapshots.
- **Attributable spend.** Instrumentation investment is joined to the specific visibility it bought, ticket by ticket.
- **Claims that get tested.** The organization finds out whether it believes its own coverage story before an incident finds out for it.
- **An honest map of what is unknown.** The unscored, the unassessed, and the unowned are reported as such, never hidden inside an average.

---

## 6. The operating model, a sketch

What follows is a sketch, not the operating model. The deep operating model is being developed as a separate piece of work. This section names the roles and cadences that clearly must exist, and then names the questions the operating model work will answer, rather than guessing at answers here.

**Roles that must exist:**

- **Scenario author.** The analyst who works a scenario through the method.
- **Independent reviewer.** Never the author; publication is gated on this separation, and the tooling enforces it.
- **Session facilitator.** Runs the scoring sessions where system owners score the signals.
- **Row owner.** The team accountable for each gap; every Blind and Collectable step must have one.
- **Use case owners, two of them.** An engineering owner who builds the pipeline and correlation, and an operating owner who runs it once it is live: its health, its on-call coverage, and its off switch.
- **Program owner for the framework baseline.** The person who owns the pinned framework versions, watches upstream releases, and runs migrations so that reported trends stay comparable. **This seat is currently unfilled, and filling it is one of the concrete asks of this document.**

**Cadences that must exist:**

- **Scoring sessions**, where system owners put the two scores on rows, confirm provisional scores, and name sources.
- **A periodic snapshot** run of the metrics, producing the immutable record that trend reporting is built on.
- **An annual baseline review**, aligned to the framework release cycle, with dual reporting across any migration so a framework change is never mistaken for a change in the estate.

**Open questions the operating model work will answer:**

1. Who convenes scoring sessions, and how often, given that the sessions need people who do not report to the program.
2. How gaps get funded and tracked against tickets: whose backlog, whose budget line, and what happens when a gap crosses team boundaries.
3. Who approves rung promotions for testing, and what the approval path from lab-only to production-observe looks like.
4. How use cases move from proposed to operating: who accepts the engineering work, and who signs off that the operating team is ready to receive the output.
5. How coverage aggregates when the catalog expands beyond the AI stack: one number for the whole estate, or one per stack. The honest concern is that blending flatters the picture, since strong coverage of familiar infrastructure can mask weak coverage of the AI-specific steps, which is precisely where the current catalog finds the gaps.

---

## 7. What this is not

- **Not a SIEM.** A SIEM (security information and event management platform) is the system that collects, stores, and searches security telemetry. Liszt does none of that. It records what the telemetry systems would show and whether anything alerts.
- **Not ticketing.** Gaps reference tickets in whatever backlog system the owning team already uses. Liszt holds the reference, not the workflow.
- **Not a compliance framework.** It maps to public frameworks; it does not certify against them, and it does not claim endorsement by their publishers.
- **Not autonomous testing.** Only the contained lab rung is enabled. Nothing tests against production, and nothing will until an explicit approval path exists.
- **Never a system that changes its own records.** Every tool in the program proposes; a person applies every change, with the reason attached. Drafts are always reviewed by a human other than the author before they count.

---

## 8. Where it stands, and the asks

The prototype is live and has been demonstrated end to end: a published, independently reviewed reference scenario, scored by the method, with a companion use case; a testing loop that emitted a sealed prediction, scored a run against it, and produced a scorecard with an optimism index and three substantive findings, none of which were discoverable by rereading the record. The catalog stands at 21 scenarios and 12 use cases against the 2026.07 framework baseline. Four scenarios have reached the published, fully scored bar; carrying the rest through it is precisely the work the pilot in ask 4 funds.

The asks:

1. **Sponsorship.** A leader who will state that this is how the organization intends to answer the visibility question.
2. **A named owner for the framework baseline.** One seat, currently empty, without which year-over-year comparability erodes.
3. **Participation of system owners in scoring sessions.** The scores are the program's raw material, and only the owning teams can supply them. For the pilot scope in ask 4, this is hours per quarter, not a reorganization.
4. **Agreement on a pilot scope.** A bounded set of scenarios and one organization's estate, scored end to end, so the first trend line exists by the next reporting cycle.

What is being offered in exchange is described in section 4, function by function. The short version: numbers about our ability to see attacks that are computed rather than authored, tested rather than assumed, and owned rather than orphaned.
