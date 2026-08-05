# Fix: step layers, and a step count the schema rejects

One file changes: `tools/build_viewer.py`. Apply on top of the previous update.

## Three defects, all in the attack_path steps

**1. The prompts asked for more steps than the schema allows.** Both said "4-7 distinct
steps". `attack_path` has `maxItems: 6`. A 7 step import was invalid the moment it landed.

**2. Canonical layer strings do not fit the step field.** `attack_path[].layer` is a short
free-text reading aid capped at 18 characters. Two of the five canonical strings are longer:

| String | Length | Against the 18 char cap |
|---|---|---|
| `L0 · Infrastructure` | 19 | rejected |
| `L3 · Orchestration & Agent` | 26 | rejected |
| `L1 · Data`, `L2 · Model`, `L4 · Application` | 9, 10, 16 | pass |

So a chain tagged with canonical strings failed validation on most of its steps.

**3. The step layer had no stated format at all.** The prompt said only "the stack layer
this move lands on", so the model reached for the nearest controlled vocabulary it had been
given. The previous fix made those five strings prominent, which made that likelier. The
house style is a short seam tag: `Data → Host`, `Host / net`, `Agent / eval`, `Host / Cloud`.

## What changed

- `shortenStepLayer()` maps a canonical string in a step to its short form
  (`L0 · Infrastructure` becomes `Infrastructure`), truncates anything else to 18, and flags
  either case for rewriting.
- Imports are capped at 6 steps, and dropping any is flagged loudly rather than silently.
- Steps are renumbered 1..n so a dropped step cannot leave a gap.
- Both prompts now say 3 to 6 steps with six as a hard ceiling.
- Both prompts now specify the step layer explicitly: a different field from
  `ai_infrastructure_layer`, 18 characters, with house-style examples, plus the rule that
  decides most of these calls: **tag where the move operates, not who is performing it. An
  agent escalating privilege on a node is a host move, not an agent move.**
- The shape examples now model the house style instead of describing it.

## Verified

Running the seven step import through the fixed normalizer yields six schema-valid steps,
every shortened layer flagged, and the dropped step flagged. `tools/validate.py` still
reports 0 errors.
