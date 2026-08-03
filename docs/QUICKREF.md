# Quick reference, one page

Print this. Everything else is elaboration. Full walkthrough: [`TUTORIAL.md`](TUTORIAL.md).

## The model

**One YAML record per scenario. Slides, metrics and search pages are printed from it.**
Edit the record, never the slide.

```
scenarios/NNN-slug.yaml  -->  two PowerPoint slides   (render_slides.py)
                         -->  coverage / exposure / maturity   (coverage.py)
                         -->  Markdown for SharePoint & Copilot (publish_library.py)
```

## Commands

After install (`bash install.sh`), run everything through the dispatcher. `./liszt validate`
is the same as `python3 tools/validate.py`.

| | |
|---|---|
| `./liszt validate` | check every record, schema + quality bar |
| `./liszt publishable` | check only published records, warnings fail |
| `./liszt render --template deck.pptx --out build/deck.pptx` | rebuild the deck into `build/` |
| `./liszt coverage` / `./liszt coverage --org name` | the numbers, optionally per-org |
| `./liszt viewer` | rebuild the static viewer page and `liszt-data.json` |
| `./liszt serve` | rebuild the viewer, then serve it on a local address for a session |
| `./liszt session <file>` | write a viewer session file back into the records |
| `python3 tools/new_scenario.py` | start a record: next free id, slug, filename, template comments kept. Add `--use-case` for a use case |
| `./liszt publish` | YAML → Markdown for SharePoint / Copilot |
| `./liszt pin` / `./liszt verify-pin` | vendor framework artifacts / re-check offline |
| `./liszt doctor` | check this machine and explain anything that is off |
| `./liszt coverage --json out/snapshot-<date>.json` | dated metric snapshot, keep these |

In a session: **Propose a new scenario** in the session bar records a scenario the room says
is missing; `./liszt session <file>` then writes the draft record for it.

## Statuses

`draft` → `in-review` → `published` → (`retired`)

Only **published** records render into the deck and count in the metrics.
A published record must validate at **0 errors, 0 warnings**. Drafts may carry warnings.
Only a **human reviewer** sets `status: published` and `reviewed_by`, and they may not be
the author.

## Use cases (`use-cases/`)

A scenario says what evidence should exist. A use case says what gets done with it.
Separate records, because one use case can serve several scenarios.

- `trigger`: the one signal that starts it. `composes`: the other evidence it then pulls,
  each tagged `enrichment`, `corroboration`, or `scoping`.
- `pipeline`: how it is delivered and who builds it. `outcome`: what it produces, who
  receives it, and their next move.
- `autonomy` ladder `notify` → `assisted` → `autonomous`. Anything above `notify` needs a
  `promotion` block with measured evidence (true positive rate, window, volume) and a named
  approver. Autonomy is earned, never declared.
- A detection claim on a published scenario should trace to a use case, or the alert fires
  into a queue nobody watches. The validator warns when it does not.
- Lifecycle `proposed` → `built` → `tuned`. Worked example: `UC-001`.

## The coverage rule, memorize this

Never typed. Always computed from two DeTT&CT scores:

| | condition | meaning |
|---|---|---|
| **Blind** | `visibility == 0` | nothing produces this signal |
| **Collectable** | `visibility >= 1` and `detection <= 0` | it is emitted, but nothing alerts on it |
| **Have** | `visibility >= 1` and `detection >= 1` | emitted *and* wired to detection |

`detection: 0` means "logged for forensics only", that is **Collectable**, not Have.
A `Have` requires an `evidence` field: a query, a rule ID, or a ticket.
A `Blind` or `Collectable` requires an `owner`, an unowned gap never closes.

## DeTT&CT scales

- **visibility** 0 to 4 · none / minimal / medium / good / excellent
- **detection** -1 to 5 · none / forensics-only / basic / fair / good / very good / excellent
- **quality**, five dimensions, each 0 to 5 · device completeness · data field completeness ·
  timeliness · consistency · retention

## Hard limits

| | |
|---|---|
| attack path | **max 6 steps.** More means the scenario is too broad, split it |
| step line | `len(text) + len(layer) + 7 <= 125` chars, or it overflows the slide |
| evidence (the telemetry map) | one row per step, always. Extra rows need `kind: control` |
| framework IDs | must exist in the **pinned** baseline. Never confirm from memory |
| OWASP IDs | edition-qualified: `LLM03:2025`, `ASI05:2026` |
| ATT&CK data | `DCxxxx` data components. `DSxxxx` data sources were retired in v18 |

## Framework mapping honesty

There is **no authoritative crosswalk** between OWASP and either MITRE framework, in
either direction. ATLAS→ATT&CK is partial, 37 of 178 techniques carry an "adapted from"
field. So:

- `mapping_confidence: editorial` is the default
- `mapping_notes` must name anything a reasonable analyst would dispute
- record a genuine **gap** rather than force a bad map
- never imply upstream endorsement

## Special modes

| Situation | Do this |
|---|---|
| A failure, not an attack | `classification.mode: failure`, relaxes framework and incident checks |
| Nothing to cite | `evidence: seen-in-research` or `doomsday`; ground it in `provenance.sources` |
| Per-org differences | `coverage/<org>/<id>.yaml` overlay; report with `--org` |
| A control **held** | `control_held: true` on the step. Most commonly omitted field |

## The three metric families, keep them apart

| | asks | audience |
|---|---|---|
| **Coverage** | how much of the chain can we see | engineering |
| **Exposure** | which NOW scenarios still have a Blind step | risk |
| **Maturity** | is the *process* working, reviewed, scored, owned, evidenced, funded | program |

A scenario can be 100% Blind and fully mature. That means you know exactly what you
cannot see, who owns it, and it is funded.

**An unscored row is absent, not zero.** Never average it in.

## Success metric

Not scenarios produced. **Tags flipping from Blind to Have, with evidence behind them
and a ticket that closed.**
