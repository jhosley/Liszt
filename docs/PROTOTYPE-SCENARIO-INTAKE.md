# Prototype workflow: bringing a scenario into Liszt

This is the fast, prototype-only path that gets a scenario into the viewer without
hand-writing a record. It lives in the viewer under **Bring in a scenario**, a top-level
tab, and it is one section with three panes behind a small menu:

1. **Research library.** A short library of research prompts. Pick one, run it in an LLM
   with web access, and choose the finding you want to bring in.
2. **Convert to JSON.** One conversion prompt turns any finding, a published incident or
   an analyst hypothesis, into scenario JSON. It checks its own output before it emits.
3. **Paste and add.** Paste the JSON. The viewer checks it again on the way in, and it
   appears in the Scenarios list immediately as a draft.

> **The live prompt text lives in the viewer, not here.** `tools/build_viewer.py` is the
> source of truth for every prompt this page shows; each one has a Copy button next to the
> paste box. This document describes the flow and the rules the prompts enforce. When the
> two disagree, the viewer is right, and this document has the bug.

The JSON the conversion prompt produces is a faithful subset of the real scenario record,
so anything brought in this way can later become a permanent `scenarios/NNN-*.yaml` record
by copy and fill, not rework.

> **What this path does and does not do.** It gets a structured, framework-tagged draft
> into the library in minutes. It does **not** score coverage. Scoring is the job of the
> system owners in a session, on the two questions Liszt asks, and the verdict is computed
> from those scores. The prompts deliberately never guess a score.

---

# The research library

Three prompts ship with the viewer. Each is one way of sourcing a scenario, and every one
of them feeds the same conversion prompt afterward.

- **Published incidents.** Searches the open web for published, real-world
  AI-infrastructure incidents and returns twelve candidates as a table: name, date,
  discloser, what happened, the layer it most affects, source URL, and a source tier.
- **Threat-research feeds.** The same intent, restricted to four vetted sources: Wiz,
  JFrog, Mandiant / Google Threat Intelligence, and the AI Incident Database.
- **Analyst hypothesis.** For an attack nobody has run yet. It sharpens a worry about our
  own environment into an objective, a chain of concrete moves, and the signal each move
  would produce, without writing any JSON. Its output goes into the conversion prompt's
  hypothesis block, and the record arrives tagged as threat-modeler work.

**Adding a prompt.** The library pane has a form for adding a research prompt. Added
prompts are session-only, like imports: they live in the browser and in the exported
session file, and are never written to the repo. To make one permanent, it goes into the
repository the same way a scenario does, as a deliberate change an analyst commits.

# The conversion prompt

One prompt converts any finding into scenario JSON. It replaces the two mapping prompts
the earlier journeys carried, which had duplicated the same rules and drifted.

The input is a two-block switch: fill in the **published incident** block or the **analyst
hypothesis** block. Which block is filled decides the provenance fields and nothing else:

- An incident sets `classification.evidence: "seen-in-the-wild"` and fills `incidents`,
  where `tier` grades the source, 1 first party, 2 reputable secondary, 3 press.
- A hypothesis adds top-level `origin: "hypothesis"` and `proposed_by: "AI Threat
  Modeler"`, sets `classification.evidence: "seen-in-research"`, and omits `incidents`.
  Those two strings are how Liszt tags the record so it can never be mistaken for a real
  incident; a named analyst may put their own name in `proposed_by`.

The rules the prompt enforces, which are also the rules the importer and the validator
check:

- `classification.ai_infrastructure_layer` is exactly one of the five layer strings,
  chosen by the LAYER RULE: the layer where the attacker achieves the objective, not where
  they got in and not who performed the move. The prompt carries the full decision
  procedure and the anti-patterns we have actually seen.
- `attack_path[].layer` is a different field: a short seam tag from a closed vocabulary,
  18 characters at most, tagging where the move operates. It includes `Model / store`, the
  model artifact at rest, so model-weight theft lands on L2 without contortion.
- One step is one adversary move that produces its own distinct observable. Three to six
  steps; six is a hard ceiling enforced by the schema. One telemetry row per step.
- No coverage, visibility, detection, or score field anywhere. Owners score it later.
- Framework values are real identifiers or an empty list; placeholders are discarded on
  import.

Before emitting, the prompt runs three self-checks on its own draft and records the result
in a `_check` block: the layer lands on the chain, the steps are one move each and fit the
render budgets, and the fields are right for the kind of input. `_check` also carries the
model's stated reason for the layer, the runner-up it nearly chose, anything it merged,
and its confidence. `_check` is not part of the record; the importer surfaces it to the
reviewer and then it is dropped.

# Paste and add

Paste one scenario object, or an array of them, and add it. The importer normalizes and
re-checks everything mechanical: it canonicalizes the layer, drops placeholder framework
values, caps the chain at six steps, checks the claimed layer against the seam tags of the
chain, and coerces source tiers. Anything questionable arrives as a `needs_review` note on
the draft rather than being silently corrected, because in most of those cases a
legitimate answer exists in both directions and only a person can tell which.

Open the imported scenario like any other; score it with the owners in a session the same
way you score any scenario.

### How it persists

Imported scenarios live in the browser session and in the file that **Export session
file** produces. Nothing is written to `scenarios/` automatically. When an imported
scenario has earned its place, an analyst turns it into a permanent
`scenarios/NNN-*.yaml` record; the JSON shape is a subset of that record, so it is a copy
and fill, not a rewrite. Apply the exported session with `tools/apply_session.py`, which
recomputes rather than trusts, and keeps the validator in the loop.

# Testing a scenario

Bringing a scenario in is the front half of the loop; checking whether its claims are true
is the back half, and it has its own tab, **Scenario testing**. Readiness, test design, and
the run-and-rescore sequence live there. See `docs/12-agent-testing.md`.
