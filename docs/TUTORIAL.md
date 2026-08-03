# Tutorial, what this is, and what to do with it

Read this first. It assumes you have never seen the repo and covers, in order: the one
idea everything rests on, a guided tour by following a single scenario through every file
that touches it, your first hour at a keyboard, what a working session actually looks
like, and what to hand to whom.

Every command below is real and every output shown is real output from this repo.

---

# Part 1 · The one idea

**Before:** a scenario lived in two PowerPoint slides. The slides *were* the record.

**Now:** a scenario lives in one YAML file. The slides are *printed from* it.

That is the whole change, and everything else in the repo follows from it.

```
                    +--------------------------+
                    |  scenarios/021-..yaml    |   <- the record. The truth.
                    |  (one file per scenario) |      Edit this.
                    +-----------+--------------+
                                |
          +---------------------+---------------------+
          v                     v                     v
   two PowerPoint         coverage /            Markdown for
   slides, styled         exposure /            SharePoint &
   exactly as today       maturity numbers      Copilot search
   (render_slides.py)     (coverage.py)         (publish_library.py)
```

**Why it matters, concretely.** With slides as the record you cannot answer "show me every
scenario where we are blind at step 3 and the priority is NOW" without a human reading 42
slides. You cannot diff this quarter against last. You cannot merge two orgs' work. And
when the person who made the deck moves teams, the reasoning leaves with them.

With a record you can do all of it, and the slides still look exactly the same, the
renderer clones your existing template and replaces the text, so it inherits every font
and color without knowing what they are.

**The second idea, which surprises people.** The Have / Collectable / Blind tag is no
longer something an analyst types. It is *computed* from two DeTT&CT scores by one rule,
and the validator recomputes it and errors if you disagree with it:

```python
if visibility == 0:      Blind          # nothing produces this
elif detection >= 1:     Have           # emitted AND something alerts on it
else:                    Collectable    # emitted, but nothing alerts on it
```

That is the difference between a maturity trend line and a measure of analyst optimism.
Everything in `tools/validate.py` exists to stop the numbers drifting away from reality.

---

# Part 2 · Guided tour, following one scenario

Rather than list directories, follow scenario 021 (the Hugging Face one) through every
file that touches it. That teaches the layout by use.

### 1. The record, `scenarios/021-agent-sandbox-escape-to-autonomous-intrusion.yaml`

The one file that matters. Open it. It has seven blocks:

| Block | What it holds | Appears on |
|---|---|---|
| header | `id`, `title`, `status`, `one_liner` | both slides |
| `classification` | priority, evidence tier, layer, why-this-priority | attack-path slide, index |
| `framework_mapping` | ATT&CK / ATLAS / OWASP IDs + the honesty note | attack-path slide |
| `attack_path` | the numbered steps, max 6 | attack-path slide |
| `telemetry` | the evidence (the telemetry map), one row per step: signal, source, coverage, detection | evidence slide |
| `commentary` + `scaled_up` | the prose boxes | both slides |
| `hardening` + `provenance` | remediation and sourcing | neither, this is for humans and tickets |

`status: published` is the important field. Only published records render into the deck
and count in the metrics. Everything else is a draft.

### 2. The rules it must obey, `schema/scenario.schema.json`

Machine-readable definition of every field: what is required, what values are legal, how
long a string may be. You will rarely read it directly; the validator reads it for you.

### 3. The checker, `tools/validate.py`

Two classes of finding. **ERROR** means structurally wrong. **warn** means legal but below
the quality bar. A `published` record must have zero of both; a draft may have warnings, that is what draft means.

```
$ ./liszt validate scenarios/021-agent-sandbox-escape-to-autonomous-intrusion.yaml

1 scenario record(s) · 0 use case record(s) · 0 error(s) · 0 warning(s)
clean
```

Compare to an imported draft:

```
$ ./liszt validate scenarios/002-model-supply-chain-compromise.yaml

scenarios/002-model-supply-chain-compromise.yaml
  warn   telemetry[1]: no DeTT&CT visibility/detection scores, the coverage tag is an
                       opinion until these exist, and the row cannot count toward
                       maturity reporting
  warn   telemetry[1]: 'Have' with no evidence, a Have claim needs a query, rule ID or
                       ticket behind it
  warn   telemetry[5]: 'Blind' with no owner, an unowned gap is an orphan and will
                       never be closed
  .
```

**That output is your work list.** It is not a complaint; it is precisely what stands
between scenario 002 and being publishable.

### 4. The frameworks it maps to, `frameworks/`

`baseline-2026.07.yaml` pins the exact versions: ATT&CK 19.1, ATLAS 2026.07, OWASP LLM
2025, OWASP Agentic 2026, DeTT&CT 2.2.0. Every record names one baseline, and all its IDs
speak that baseline's vocabulary.

Why bother: ATT&CK v18 retired data sources and replaced them with data components; v19
split Defense Evasion into two tactics. Without pinning, a coverage "drop" next year is
indistinguishable from MITRE renaming something.

`pinned/` is where the actual framework files get vendored with checksums, so an ID can
be verified offline, including in the air-gapped environment, where re-fetching is not an option.

### 5. The incidents it cites, `incidents/`

One file per real incident. Scenario 021 cites three. This is what feeds the "Real-world
incidents behind these scenarios" appendix slide, and it means an incident cited by five
scenarios is described once.

### 6. The slides, `tools/render_slides.py`

```
$ ./liszt render --template deck.pptx --out build/deck.pptx --only 021
  021  Agent sandbox escape → autonomous intrusion
1 scenario(s) rendered to build/deck.pptx
```

Pixel-identical to what you have today. It clones a slide pair from your template and
rewrites the text runs, so it cannot lose your styling.

### 7. The numbers, `tools/coverage.py`

```
$ ./liszt coverage

SCENARIO LIBRARY · reference assessment · 1 record(s)

  id  pri         cmp  have  coll blind  qual   mat  coverage
 021  NOW        1.00  0.50  0.33  0.17  0.53   7/7  █████████·········

COVERAGE   mean Have across 1 scored scenario(s): 50.0%

EXPOSURE   1 NOW-priority scenario(s) with a Blind step
           021 Agent sandbox escape → autonomous intrusion  blind at step(s) [1]

MATURITY   1/1 scenario(s) pass all seven process gates
```

Read the columns: `cmp` is completeness (what fraction of rows are actually scored, this
gates everything), then the three coverage proportions, `qual` is mean data quality, `mat`
is how many of seven process gates the record passes.

Run it with `--include-drafts` and you see the honest picture:

```
COVERAGE   mean Have across 1 scored scenario(s): 50.0%
           20 scenario(s) contribute nothing because they are unscored: 001, 002.
           Unscored is not zero. It is absent. Do not average it in.
```

### 8. The teaching material, `docs/` and `reference/`

| File | When you open it |
|---|---|
| `docs/01-methodology.md` | Working a scenario. Seven gates, each with its test and its most common failure. |
| `docs/02-quality-bar.md` | Reviewing someone's scenario. |
| `docs/03-framework-mapping.md` | Mapping IDs, and what to do when nothing fits. |
| `docs/04-measurement.md` | Someone asked for the numbers. |
| `docs/00-outcomes.md` | Deciding whether this is working at all. |
| `docs/06-keeping-current.md` | Frameworks or threats changed, or the methodology needs updating. |
| `docs/05-environments.md` + `docs/09-air-gapped.md` | Standing it up in a corporate or air-gapped environment. |
| `reference/021-worked-example/` | **Start here.** 021 carried gate by gate, mistakes intact. |

### 9. Where an assistant fits

Nothing in the repo requires one. Where a drafting tool is available, the useful split is
the one in `docs/05-environments.md`: judgment over text can be drafted, and reproducible
computation belongs to the Python in `tools/`. A draft is a draft. **A human reviews and
owns the result**, and `status: published` and `reviewed_by` are a person's act, never a
tool's.

### 10. The companion record, `use-cases/UC-001-correlated-prompt-injection-with-data-movement.yaml`

The tour so far followed a scenario. There is a second kind of record that sits next to
it. A scenario says what evidence *should* exist. A **use case** says what gets *done*
with that evidence. They are separate files on purpose: one use case can serve several
scenarios, and copying it into each is how a library rots.

Open UC-001, the worked example. It reads as a short pipeline:

| Block | What it answers |
|---|---|
| `trigger` | the one signal that starts it (here, a model guardrail policy violation) |
| `composes` | the other evidence it then pulls, each tagged with its role: enrichment, corroboration, or scoping |
| `pipeline` | how that evidence is delivered, and which team owns building it |
| `outcome` | what it produces (alert, report, trend), who receives it, and their next move |
| `limits` | what it cannot tell you, stated plainly |

Two rules keep it honest. First, **`autonomy` above `notify` requires a `promotion`
block** with measured evidence: the true positive rate, the window it was measured over,
and how many times it actually fired. You cannot declare that a use case may act on its
own. You have to show the numbers it earned that on, and a named person has to approve it.
Second, **a detection claim on a published scenario should trace to a use case.** If a
telemetry row says something alerts, some use case has to name who receives that alert and
what they do with it, or the signal is firing into a queue nobody watches. The validator
warns when a published detection has no use case covering it.

Use cases live in `use-cases/` and validate right alongside scenarios (`./liszt validate`
checks both). They carry their own lifecycle: `proposed`, then `built`, then `tuned`.

---

# Part 3 · Your first hour

```bash
unzip liszt.zip && cd liszt
bash install.sh          # builds the .venv and installs the packages
                         # Windows: powershell -ExecutionPolicy Bypass -File install.ps1
```

After install, run everything through the dispatcher: `./liszt <command>`. Each one just
runs the matching tool, so `./liszt validate` is the same as `python3 tools/validate.py`.

**1. See that it works.**
```bash
./liszt validate
```
Expect roughly `21 scenario record(s) · 2 use case record(s) · 0 error(s) · 332
warning(s)`. Zero errors means every record is structurally sound. The warnings are the
imported draft backlog, each one telling you what a record still needs. Expect a number
near this rather than an exact one; it falls as drafts get worked.

**2. Read the reference scenario.** Twenty minutes, and it is the whole discipline:
```bash
less reference/021-worked-example/README.md
less scenarios/021-agent-sandbox-escape-to-autonomous-intrusion.yaml
```

**3. Prove the round trip.** Point it at your existing deck:
```bash
./liszt render --template /path/to/AIObservabilityAnalysis_Scenarios.pptx \
        --out build/deck.pptx --include-drafts
```
Open `build/deck.pptx`. It is your deck, regenerated from the YAML. That is the moment
the model clicks.

**4. Vendor the framework pins** (needs internet, once):
```bash
./liszt pin
```

**5. See the numbers.**
```bash
./liszt coverage --include-drafts
```

That is the hour. You now understand the system.

---

# Part 4 · What a working session looks like

One hour, one scenario, two people. This is the loop, repeat it and the program
runs itself.

### Before (analyst, ~45 min)

Pick the scenario. Start the record with the scaffolder:

```bash
python3 tools/new_scenario.py
```

It asks five plain questions (what it is called, attack or failure, which layer, how urgent,
who is writing it) and writes the record for you. It takes the next free id, builds the slug
from the title, names the file the one way the validator accepts, keeps every teaching
comment in the template, stops if a record with a very similar slug already exists (a
duplicate is the most common way this library goes wrong, `--force` overrides it once you
have looked), and runs the validator so the warnings you have to clear are already on
screen.

Scripted, or if you would rather not answer questions:

```bash
python3 tools/new_scenario.py --title "Poisoned vector store in a shared index" \
        --mode attack --layer L3 --priority NEAR-TERM --author "your name"
# a use case record instead:
python3 tools/new_scenario.py --use-case
```

Copying `scenarios/_TEMPLATE.yaml` by hand still works, and then the id, the slug and the
filename are yours to get right.

Work `docs/01-methodology.md` gates 0 to 6. Then:

```bash
./liszt validate scenarios/022-*.yaml
```

Fix what it says. Hand over when the only warnings left are ones you can defend.

### During (the group, ~45 min)

Run `./liszt serve` to build the viewer and open it at a local web address, then drive the
session from there. Serve it rather than opening the built HTML (HyperText Markup Language)
file straight from disk: a file opened directly shares one browser storage area, so two
open copies can overwrite each other's session, and serving it at a local address avoids
that.

Put the **attack path** on screen and analyze the chain as a team. Is that really how it goes? Is a
step missing? Did a control hold anywhere?

Then the **evidence map**, row by row. This is where the value is. For each row:

- Would we actually see this? Who owns that data source?
- Is it merely logged, or does something alert on it? *(That is the Collectable / Have
  line, and it is the one people get wrong.)*
- If we are blind, is it worth fixing, and who takes the ticket?

Every Blind or Collectable row leaves the room with an owner and a ticket number. Type
them into the viewer live; that is what `owner` and `backlog_ref` are for. The viewer
saves the session to a file, and `./liszt session <file>` writes those edits back into the
records, comments and all.

A session almost always turns up a scenario the library does not have. Do not write it on a
sticky note. Press **Propose a new scenario** in the session bar, or the same button in the
Session readback tab, and answer the five questions on screen. Proposals ride along in the
exported session file and are listed with a count in the readback, so you can read them back
and drop any the room decided against. When you apply the file, each surviving proposal
becomes a draft record with the next free id, ready for an analyst to work.

### After (reviewer, ~15 min)

Work `docs/02-quality-bar.md`. Report findings as blocker / should-fix / note. **Do not
edit the record**, hand findings back. When it is clean, the reviewer sets
`status: published` and `reviewed_by`, and commits.

```bash
./liszt publishable      # must be 0 errors 0 warnings
./liszt render --template /path/to/template.pptx --out build/deck.pptx
./liszt coverage
```

### What you actually produced

Not a slide. A row in a coverage table, a set of owned gaps, and tickets that can close.
**The program's success metric is tags flipping from Blind to Have with evidence behind
them**, not scenarios produced.

---

# Part 5 · What to hand to whom

| Person | Give them | Why |
|---|---|---|
| **Your program lead** | This tutorial, then `docs/00-outcomes.md` | Outcomes and observables are what they own. |
| **An analyst** | `docs/01-methodology.md` + `reference/021-worked-example/` | One hour to competence. |
| **A reviewer** | `docs/02-quality-bar.md` | Checklist and severity language. |
| **Whoever runs the tooling** | `README.md` + `tools/` + `.github/workflows/validate.yml` | Plain Python over the records; only the framework pin needs the network. |
| **The air-gapped environment engineers** | `docs/09-air-gapped.md` | The research/authoring split and the source-bundle spec. |
| **A partner org joining later** | `README.md` section  Multi-organization + the whole repo | They adopt the library; their coverage stays theirs. |

**The one thing to say out loud in the first meeting:** *the repo is the record; the deck
is printed from it.* If that lands, everything else is detail. If it does not, someone
will edit a slide and be confused when it vanishes on the next render.

---

# Part 6 · A sequence, not a schedule

Liszt does not prescribe an operating model, so this is dependency order rather than a
calendar. Do each when the previous one is done.

**First.** Name the framework-baseline owner (`frameworks/baseline-2026.07.yaml` currently
says `UNASSIGNED`). Get the repo into your git host. Run `./liszt validate` in CI. Walk one
scenario end to end with the loop in Part 4, use 021, since the answers are already
there and you are practicing the *process*, not the content.

**Then.** Work new scenarios one at a time. Do not try to clear the 20 imported drafts as
a batch, they are a backlog, not a debt, and a scenario is worth publishing only when
someone has actually assessed its coverage. Run the two-analyst calibration exercise in
`docs/02-quality-bar.md` the first time a second person authors one.

**Then.** Take the first metric snapshot (`./liszt coverage --json
out/snapshot-<date>.json`) and keep it. Trend lines need a first point. Stand it up in
the air-gapped environment if that is where it has to run. Publish the library to
SharePoint (`./liszt publish`) so people can find scenarios without asking you.

**Then.** Onboard the second org, `coverage/<org>/` overlays exist for exactly this, and
the fact they can adopt without publishing their gaps is what makes the ask cheap.
Re-baseline the frameworks when ATT&CK ships in April, with one cycle of dual reporting.

---

# Part 7 · Questions you will hit

**"Do I have to use an AI assistant?"** No. The repo is YAML, Markdown and Python, and
only the framework pin touches the network. A drafting tool is an accelerator, never a
requirement. Everything works by hand.

**"Can I just edit the slides?"** No, the next render overwrites you. Edit the record.

**"What are those ~332 warnings?"** Your 20 imported draft scenarios need DeTT&CT scores,
data source owners, and evidence behind their `Have` claims. That is real analytical work
and the warnings are an inventory of it. The exact count drifts as drafts get worked; they
are not errors and nothing is broken.

**"Why does my Have keep flipping to Collectable?"** DeTT&CT `detection: 0` means *logged
for forensics only*. That is Collectable, not Have. Have needs `detection >= 1`, something
actually alerts.

**"We have no incident to cite."** Set `evidence: seen-in-research` or `doomsday`, and put
what grounds it in `provenance.sources`. Doomsday records are exempt from the
incident-reference check.

**"It is a failure, not an attack."** Set `classification.mode: failure`. The validator
stops demanding framework IDs and an incident. The attack path becomes a failure
propagation chain, and the evidence map, where all the value is, is unchanged.

**"Two orgs disagree about a coverage score."** They are both right. Coverage is a property
of an estate, not of a scenario. Put each org's assessment in `coverage/<org>/<id>.yaml`
and report with `--org`.

**"A framework changed."** Do not chase it. Cut a new baseline on a deliberate cadence,
publish one cycle against both pins, then switch. Full procedure in
[`docs/06-keeping-current.md`](06-keeping-current.md).

**"Something new appeared that we do not cover."** Three intake questions decide whether it
is a new scenario, a revision, or a duplicate, [`docs/06-keeping-current.md`](06-keeping-current.md) section 3.

**"Someone wants a scenario with nine steps."** The chain is too broad, split it. The
six-step ceiling is a scoping tool, not a slide constraint.

---

# The five rules, one more time

1. **The record is the truth; the slide is a rendering.**
2. **Coverage is derived, never asserted.**
3. **Every cross-framework mapping is editorial until proven otherwise.**
4. **Pin the frameworks, or your trend line measures MITRE's release schedule.**
5. **An unscored row is absent, not zero.**
