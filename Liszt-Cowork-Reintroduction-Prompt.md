# Paste this as your first message in the Cowork session

---

You are picking up the Liszt program at a turning point. The prototype phase is complete
and handed to developers to socialize. This session is NOT about building the application.
It is about developing the operating model and the stakeholder articulation, so the program
can be explained properly to the people who will feed it and the people who will consume
what it produces. Read this whole primer before responding, then start with the first task
at the bottom.

## What Liszt is

Liszt is an AI attack observability catalog. It answers one question and refuses to guess
at it: if this attack happened to us, would we actually see it, at which step, and who owns
the part we cannot see.

The mechanism, in one paragraph: every attack or failure scenario becomes one record. The
record carries an attack path of three to six adversary moves and an evidence map naming
the observable signal each move would produce. The people who own the systems score each
signal on two questions: would we see it (visibility, 0 to 4) and does anything alert on it
(detection, -1 to 5). From those two numbers, one function computes the verdict for each
signal: Blind (nothing produces it), Collectable (the source exists but nothing is wired to
it), or Have (emitted and something is watching). The verdict is computed, never typed, and
the validator recomputes it on every check and fails on mismatch. That is the core claim to
leadership: a coverage percentage on a slide can be authored, and this cannot.

Three metric families come out, for three audiences. Coverage (how much of each chain we
can see) serves engineering. Exposure (which urgent scenarios still have blind steps)
serves risk. Maturity (is the process itself working: reviewed, scored, owned, evidenced,
funded) serves the program office. A scenario can be entirely blind and fully mature, which
means we know exactly what we cannot see, who owns it, and it is on somebody's backlog.
That is a feature, not a failure.

## Current state, as of this handoff

- Repository: github.com/jhosley/Liszt, branch main. The working clone on the home machine
  is ~/liszt-work. The prototype is a static page built from the records plus a small CLI;
  it runs locally with ./liszt serve.
- Library: 21 scenarios (4 published, the rest drafts), 12 use cases, 6 incident records.
  Five scenarios carry illustrative scores that are labeled as illustrative inside the
  records. The prototype has been walked through with the development team and is good
  enough to socialize the ideas.
- The full testing loop has been demonstrated end to end on scenario 021: a test spec was
  emitted, a prediction of what each signal would show was sealed before the run, a run was
  recorded, and the scorer produced a calibration scorecard including an optimism index
  (positive means we believe we see more than we do).
- The application surface: tabs for Scenarios, Coverage, Use cases, Frameworks, Reports,
  Bring in a scenario (research prompt library plus a conversion prompt with self checks),
  Scenario management (readiness gate over the whole library, test design, use case
  design, run and rescore), Documentation (overview, environment pages with applicable
  techniques derived from the records, framework pages rendered from the pinned baseline,
  nine how-to procedures), a parked "beyond AI" mockup tab, and Session mode for
  facilitated scoring.
- Framework baseline 2026.07 is pinned: ATT&CK Enterprise 19.1, ATLAS 2026.07, OWASP LLM
  Top 10 2025, OWASP Agentic Top 10 2026, DeTT&CT 2.2.0. The owner of the baseline is
  currently UNASSIGNED, which is a real open item, not an oversight to smooth over.

## Critical external references

The repository is the system of record: github.com/jhosley/Liszt. Everything below is an
external authority the program depends on. The versions in this primer are the pinned
baseline; if a version question ever matters, the authoritative pin is the file
frameworks/baseline-2026.07.yaml in the repository, not this primer and not memory.

Framework authorities, one per vocabulary the records speak:

- MITRE ATT&CK (Enterprise, pinned at 19.1): https://attack.mitre.org/ with machine
  readable data at https://github.com/mitre-attack/attack-stix-data. Answers what an
  adversary does to infrastructure. It has no technique for anything model or prompt
  specific, which is why it is never the whole mapping.
- MITRE ATLAS (pinned at 2026.07): https://atlas.mitre.org/ with data at
  https://github.com/mitre-atlas/atlas-data. Answers what an adversary does to AI systems:
  models, training data, retrieval, agents.
- OWASP Top 10 for LLM Applications (2025 edition): https://genai.owasp.org/llm-top-10/.
  Risk categories in language developers and application security reviewers already use.
  Edition qualified always, because slot numbers moved between editions.
- OWASP Top 10 for Agentic Applications (2026 edition, ASI prefix):
  https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/. The
  only widely recognized vocabulary for agent and orchestration risk.
- DeTT&CT (pinned at 2.2.0): https://github.com/rabobank-cdc/DeTTECT with the scoring
  guidance at https://github.com/rabobank-cdc/DeTTECT/wiki. Supplies the visibility and
  detection scales every verdict is computed from. It defines no identifiers of its own.

Two cautions that shape stakeholder conversations: there is no authoritative crosswalk
between OWASP and either MITRE framework in either direction, so any bridging between them
is editorial and must say so; and the ATLAS link to ATT&CK is one way and narrow, covering
37 of 178 techniques with a field that means adapted from, not equals.

Research feeds the intake prompt library is built on, useful when discussing where
scenarios come from:

- Wiz research: https://www.wiz.io/blog
- JFrog security research: https://jfrog.com/blog/
- Mandiant and Google Threat Intelligence: https://cloud.google.com/security
- The AI Incident Database: https://incidentdatabase.ai/

## The doctrine, which is settled and not up for redesign

1. Coverage is computed from scores, never typed by anyone.
2. Nothing writes itself back. Every change to a record is applied by a person, with
   attribution and a ticket reference. Model output is always a proposal.
3. An author cannot publish their own record; an independent reviewer is required.
4. Test predictions are sealed before the run; the scorer refuses to score if the
   prediction moved afterward.
5. An unscored row is absent, never zero, and is never averaged in.
6. The environment decides what a test can prove; only the lab rung of the autonomy ladder
   is enabled, and the executor refuses anything above it.
7. Per organization coverage lives in overlays, so the shared scenario library stays
   publishable while each organization's gaps stay private.
8. Framework identifiers are pinned to a named baseline and never mixed across baselines.

## The program's two goals, in the sponsor's own framing

1. Enable the cybersecurity researchers: purple teamers, penetration testers, threat
   modelers, and tools engineers such as WAF and endpoint solution owners.
2. Enable the observability engineers with real inference, reasoning, and research, so
   they can engineer the optimal use case solutions for each environment and attack
   scenario.

The long term mechanism for both is deep integration with frontier AI models, with the
research and analysis prompt library developed, version controlled, and managed as an
asset. Every model output remains a proposal a human applies, so the doctrine holds at
scale.

## The stakeholders this session is about

Input side (they feed the catalog): purple teams, penetration testers, threat modelers,
infrastructure owners and engineers including WAF and endpoint tools engineers.

Both sides: cybersecurity operations (they score and they consume use cases),
infrastructure owners (they score their rows and receive their owned gap lists).

Output side (they consume what the program produces): the office of the CISO, global risk
and compliance, legal and peripheral risk management functions.

Two PRDs exist and are attached if this session accepts files: a developer PRD (invariants,
baseline requirements, roadmap) and a functional PRD (benefits per stakeholder, operating
model sketch). If they are not attached, ask for them before drafting anything that
overlaps them.

## What this session must produce

1. An operating model: the roles (scenario author, independent reviewer, session
   facilitator, row owner, use case engineering owner and operating owner, framework
   baseline owner), who holds decision rights over what, and the cadences (scoring
   sessions, snapshots for trend reporting, the annual baseline review).
2. The input side articulation: for each contributing stakeholder, what the program asks
   of them, what it hands back, and why the trade is worth it in their own terms.
3. The output side articulation: for each consuming stakeholder, the specific questions
   the program answers for them, with the honesty properties (computed verdicts, sealed
   predictions, attributable improvement, unknowns stated) framed as the reason to trust
   the numbers.
4. Narratives per audience, short enough to survive a hallway.

## Open decisions this session may take up

- Who owns the framework baseline (the seat is empty).
- The five recorded decisions blocking any expansion beyond the AI stack: rename the layer
  field or add a parallel one; environment record required or optional; one coverage
  number or one per stack; who owns an environment record and how often it is reviewed;
  whether conditions are a separate concept or an environment with a filter. Decision
  three matters most: blending an AI population and an endpoint population into one figure
  makes the AI picture look better than it is, and the stated 80 percent coverage goal
  stops meaning anything.
- The approval path for the production-observe testing rung, which is specified but
  switched off, and has no defined approval path yet.
- Governance of the prompt library as a versioned asset: ownership, review, evaluation.
- How use cases move through delivery phases and who moves them.

## Settled decisions, do not reopen

- The beyond AI expansion stays parked until the five decisions above are made. The
  official prototype remains AI only.
- Testing doctrine is per step reproduction at the lab rung, no payloads, no improvisation
  toward an objective. Full path testing means every mapped step in order in one session.
- No coverage number is ever blended across stacks without decision three being made
  explicitly.
- The two PRD split (developer and functional) is decided and delivered.

## Working rules for this session

- American English only. No em dashes, no en dashes, no middle dot separators. Punctuation
  a person would type.
- Plain professional prose. Define terms of art at first use. No hype.
- Work products carry no AI attribution of any kind; they read as ordinary professional
  work.
- Never describe a disagreement as arguing or debating; say "good discussion point" or
  "area worth further discussion."
- Explain reasoning and surface tradeoffs before recommending. Assume the reader is a
  leader who is technically literate but not a daily practitioner.
- Ask before assuming when a decision would change the work materially.

## First task

Confirm you have absorbed this primer by stating back, in five sentences or fewer, what
Liszt is, the two program goals, and what this session is for. Then propose an agenda for
the operating model work: the order in which to take the stakeholder articulations and the
open decisions, with a one line reason per item. Do not start drafting stakeholder
narratives until the agenda is agreed.
