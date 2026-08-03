# Liszt

A repeatable discipline for working attack and failure scenarios into two artifacts, an **attack path** and a **telemetry & detection map**, and rolling those up into
coverage, exposure and maturity reporting.

This repo is the **system of record**. PowerPoint is a build artifact you can delete and
regenerate. That inversion is the single most important design decision here: a scenario
that lives only in a slide cannot be queried, rolled up, diffed over time, or merged
across organizations, and a program built on slides quietly dies when its author
changes roles.

---

## Start here

**Start with [`docs/TUTORIAL.md`](docs/TUTORIAL.md).** It explains the one idea everything
rests on, tours the layout by following a single scenario through it, and tells you
exactly what to do in your first hour. About twenty minutes, and it assumes no prior
experience.

[`docs/QUICKREF.md`](docs/QUICKREF.md) is the one-page card to print and keep.

`tools/manual/build_manual.js` generates the same material as a Word installation and
operating manual, both system diagrams included, for readers who would rather have a
document than a repository.

| If you are | Read, in this order |
|---|---|
| **Anyone, first time** | [`docs/TUTORIAL.md`](docs/TUTORIAL.md) |
| **The two system diagrams** | [`docs/diagrams/`](docs/diagrams/) |
| **An analyst about to work your first scenario** | [`docs/01-methodology.md`](docs/01-methodology.md) → [`reference/021-worked-example/`](reference/021-worked-example/) → [`scenarios/021-agent-sandbox-escape-to-autonomous-intrusion.yaml`](scenarios/021-agent-sandbox-escape-to-autonomous-intrusion.yaml) |
| **Reviewing someone else's scenario** | [`docs/02-quality-bar.md`](docs/02-quality-bar.md) |
| **Mapping frameworks** | [`docs/03-framework-mapping.md`](docs/03-framework-mapping.md) |
| **Asked for the numbers** | [`docs/04-measurement.md`](docs/04-measurement.md) |
| **Standing this up in a corporate environment** | [`docs/05-environments.md`](docs/05-environments.md) → [`docs/09-air-gapped.md`](docs/09-air-gapped.md) |
| **Deciding whether this is working at all** | [`docs/00-outcomes.md`](docs/00-outcomes.md) |
| **Keeping it current as frameworks and threats change** | [`docs/06-keeping-current.md`](docs/06-keeping-current.md) |
| **Integrating the library into another web app** | [`docs/07-viewer-data-contract.md`](docs/07-viewer-data-contract.md) |
| **Asking what Liszt is not responsible for** | [`docs/08-boundaries.md`](docs/08-boundaries.md) |

The fastest way to understand the discipline is to read the reference scenario and its
walkthrough. People learn a process by copying a good example far faster than by reading
a procedure, that is why scenario 021 is carried end to end with its mistakes intact.

---

## Layout

```
docs/           the discipline: outcomes, methodology, quality bar, framework mapping,
                measurement, environments, keeping current, the viewer contract,
                boundaries, and running with no internet
schema/         the capture format. The JSON Schema every record is checked against
scenarios/      the library itself: one YAML record per scenario, and _TEMPLATE.yaml
incidents/      one record per real incident, described once and cited by every scenario
                that draws on it
coverage/<org>/ per-org coverage overlays. What a given organization can see, kept apart
                from the scenario, which is org-independent
frameworks/     the pinned framework baseline, and the vendored artifacts with checksums
                that make an ID verifiable offline
reference/      scenario 021 carried gate by gate, mistakes intact. The teaching example
use-cases/      one YAML record per operational use case, and _TEMPLATE.yaml
docs/diagrams/  the two system diagrams, and the script that draws them
tools/          the Python that reads the records: validate · render · coverage · viewer ·
                serve · doctor · session · pin · publish
tools/manual/   the generator for the Word installation and operating manual
install.sh · install.ps1 · liszt · liszt.cmd   the installer, and the dispatcher every
                command runs through
```

---

## Quick start

Install once. On macOS or Linux:

```bash
bash install.sh            # core packages; add --with-deck for the slide tools,
                           # or --offline to install from a local wheel directory
```

On Windows, in PowerShell:

```powershell
./install.ps1              # -WithDeck and -Offline work the same way
```

The installer creates a virtual environment inside this folder. It needs no
administrator rights and changes nothing outside the repository. After it finishes,
every command runs through the dispatcher (`./liszt` on macOS and Linux, `liszt` on
Windows):

```bash
./liszt doctor            # check the machine and report anything missing in one line each
./liszt validate          # schema and quality-bar check across the whole library
./liszt coverage          # the coverage, exposure and maturity rollup
./liszt viewer            # build the static web viewer and the JSON data file
./liszt serve             # host the viewer at a local address for a working session
./liszt session <file>    # write a captured session back into the records
```

Each dispatcher command is a thin wrapper over `python3 tools/<name>.py`, which still
works directly if you prefer it.

Working a new scenario is: run `./liszt new` (or copy `scenarios/_TEMPLATE.yaml` to the
next free id by hand), fill it in against `docs/01-methodology.md`, and run
`./liszt validate` on it. An automated drafting step can produce the first version, and
**a human analyst always reviews and owns the result.** Nothing here is designed to
publish without a person in the loop.

### Installing where there is no internet

There are no wheel files in this repository, so an offline machine needs the packages
brought to it one of two ways:

- **An internal package mirror.** Point pip at it (`pip config set global.index-url
  <your internal index url>`) and run `bash install.sh` normally.
- **A wheel directory built once and carried across.** On a machine with package index
  access, run:

  ```bash
  pip download -r requirements/base.txt -r requirements/deck.txt \
      --only-binary=:all: \
      --python-version 3.11 --platform manylinux_2_28_x86_64 \
      -d vendor/wheels
  ```

  Use the platform tag of the target machine (`macosx_11_0_arm64` for Apple Silicon,
  `win_amd64` for Windows), move `vendor/wheels` across with the repository, then run
  `bash install.sh --offline`. The installer stops with an explanation if that folder is
  not there. Full procedure: [`docs/09-air-gapped.md`](docs/09-air-gapped.md) section 6.

---

## The five rules that carry the weight

Everything else is elaboration.

**1. The record is the truth; the slide is a rendering.** Never edit a slide and expect
it to survive. Edit the YAML and re-render.

**2. Coverage is derived, never asserted.** The Have / Collectable / Blind tag is
computed from DeTT&CT visibility and detection scores by one rule in
`tools/validate.py:derive_coverage()`. The validator recomputes it and errors on
mismatch. This is what turns an analyst's opinion into an evidence-backed determination,
and it is the difference between a maturity trend line and a measure of analyst optimism.

**3. Every framework mapping is editorial unless proven otherwise.** There is no
authoritative crosswalk between OWASP and either MITRE framework, in either direction.
The ATLAS→ATT&CK linkage is partial, 37 of 178 techniques carry an "adapted from"
field. So `mapping_confidence: editorial` is the default, `mapping_notes` must name
anything a reasonable analyst would dispute, and we never imply upstream endorsement.

**4. Pin the frameworks, or your trend line measures MITRE's release schedule.** Two of
the four frameworks made breaking changes in the last eighteen months. ATT&CK v18
retired data sources for data components, v19 split Defense Evasion into two tactics.
Without pinning, a coverage "drop" is indistinguishable from a rename.

**5. An unscored row is absent, not zero.** Scoring nothing and scoring badly must never
produce the same number. `tools/coverage.py` refuses to average unscored rows in, and
says so out loud.

---

## Multi-organization

The scenario library is **organization-independent**: the attack path, the signals that
would be emitted, and the framework mapping are properties of the scenario, not of
anyone's estate. What differs per org is coverage, org A runs one EDR, org B another,
so "Have" is not a global fact.

That split lives in `coverage/<org>/<scenario-id>.yaml`, which overrides individual
telemetry rows. `./liszt coverage --org <name>` applies it.

The consequence is the point: **an organization can adopt the whole library without
publishing its own coverage.** Contributing to the shared library costs nothing
politically; disclosing your gaps is a separate, later, voluntary decision. If you are
standing this up across teams that do not report to you, do not skip this.

---

## What this program measures

Not scenario count. That is a vanity metric, you can produce fifty and improve nothing.

The real measure is **tags flipping from Blind to Have, with evidence behind them and a
ticket that closed.** `tools/coverage.py` reports three families separately, because
they answer different questions:

- **Coverage**, how much of the chain we can actually see. Engineering audience.
- **Exposure**, which NOW-priority scenarios still have Blind steps. Risk audience.
- **Maturity**, is the *process* working: reviewed, scored, owned, evidenced, funded.
  Program audience. It moves independently of the other two, and a scenario can be
  100% Blind and fully mature, that means we know precisely what we cannot see, who
  owns it, and it is on someone's backlog.

See [`docs/00-outcomes.md`](docs/00-outcomes.md) for the outcomes each of these serves,
and the observable that tells you it is true. An outcome without an observable is a
slogan.

---

## What is deliberately not here

No program charter, cadence, governance model, decision rights or org design. That is
not an omission, it is the design. Those things have to be negotiated with teams that
own their own turf, repeatedly, and anything prescribed here would be a document people
have to push back on.

What is here is what survives that negotiation: the tradecraft, the quality bar, the
capture format, and the outcomes. All four are useful to whoever picks them up, none of
them require anyone to change how they work, and none of them need a central authority
to function.

---

## Honest limits

- **A drafting tool drafts; it does not author.** Expect a good first draft and a
  mandatory review. If the program's credibility depends on the draft being right,
  it will fail publicly at a tabletop.
- **Analyst variance is the top operational risk.** The calibration exercise in
  [`docs/02-quality-bar.md`](docs/02-quality-bar.md) is the control. Run it when a new
  analyst joins and whenever two orgs' records start looking different.
- **Framework mapping is judgment.** Documented as such throughout, and it will still
  be argued about. That is fine, record the argument in `mapping_notes` rather than
  resolving it silently.
- **`tools/render_slides.py` needs a template deck** with at least one scenario slide
  pair to clone. It cannot invent the design, and it should not try.
- **Research needs internet; nothing else does.** The air gap falls cleanly between
  those two halves, see [`docs/09-air-gapped.md`](docs/09-air-gapped.md).
