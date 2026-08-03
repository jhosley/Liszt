# 09 · The air-gapped environment

**Audience:** whoever is standing Liszt up where there is no internet, and whoever has to review that design.
**Good for:** everything downstream of retrieval, analysis, framework mapping, DeTT&CT scoring, record authoring, validation, slide generation, coverage rollup, tabletop prep. All of it runs offline with no loss of fidelity.
**Not good for:** anything that needs to touch a primary source. You cannot retrieve a post-mortem, confirm a CVE exists, check a fixed build number, or notice that a vendor issued a correction last Tuesday.
**This works because the air gap falls cleanly between those two halves.** This document is about making that seam explicit, auditable, and boring.

---

## 1 · The separation principle

The program has exactly one internet-dependent step: **getting the primary sources**. Everything the program actually produces, the scenario record, the two slides, the coverage numbers, the tabletop pack, is computation over material that is already in hand.

That is not a lucky accident of this program's design; it is a consequence of the schema. `scenarios/*.yaml` is the system of record. Its `provenance.sources[]` array is a list of *references*, not a live feed. Once you have the bytes those references point at, every other field in the record, `attack_path`, `telemetry`, `framework_mapping`, `classification`, `commentary`, `hardening`, is derived by an analyst reading those bytes against the pinned framework data. No network call is involved in that derivation.

So this is not a reduced version of the program. It is the same program with one stage moved to the other side of a boundary, plus a defined artifact crossing that boundary.

Two consequences worth stating up front:

- **The pinned-baseline discipline the program already imposes makes the air-gapped environment cheaper, not more expensive.** `frameworks/baseline-2026.07.yaml` exists so that year-over-year metrics are comparable; a side effect is that the framework data the program depends on is *supposed* to be frozen for a full cycle. An air-gapped copy that is 10 months stale is not a degradation, it is the intended state. See section 3.
- **The gap is bidirectional and the outbound direction is the dangerous one.** Sources flow in; unanswered questions flow out. Inbound is a content-inspection problem. Outbound is an exfiltration problem, and it is governed by your cross-domain policy, not by this document. section 7 covers how to keep the outbound channel narrow.

---

## 2 · The split

| Stage | Where it runs | Why |
|---|---|---|
| Candidate scan, what happened this week worth a scenario | Internet-side | Requires discovery |
| Scope decision, which incident(s), which date range, which parties | Internet-side (human) | Cheap, and it determines what gets retrieved |
| Primary source retrieval, read the full documents, not snippets | Internet-side | The only genuinely network-bound step |
| Verification. CVE IDs exist, fixed build vs branch, dates against the repo not the press | Internet-side | Needs registries. Cannot be redone in the air-gapped environment at any confidence |
| Bundle assembly, manifest, hashes, negative findings | Internet-side |  |
| **Cross-domain transfer** | **Boundary** | Your guard/diode process, not ours |
| Bundle intake, rehash, register, quarantine-read | air-gapped |  |
| Scenario drafting, `title`, `one_liner`, `attack_path`, `scaled_up` | air-gapped | Reading and writing over material in hand |
| Framework mapping. ATT&CK / ATLAS / OWASP IDs against the pinned baseline | air-gapped | Pinned data is local (section 3) |
| Telemetry rows, `signal`, `emitted_at`, `detection_opportunity` | air-gapped | Needs your estate knowledge, which is *inside* the air-gapped environment |
| Coverage + DeTT&CT scoring, with the data owners | air-gapped | Same. This is arguably better in the air-gapped environment than out of it |
| `hardening[]` ranking | air-gapped | Needs your control inventory |
| Validation, schema + house rules | air-gapped | Pure local computation |
| Slide render, the two PowerPoint slides | air-gapped | Pure local computation |
| Coverage rollup and metrics | air-gapped | Pure local computation |
| Tabletop pack, injects, facilitator notes | air-gapped | Pure local computation |
| Walkthrough session | air-gapped | Where the audience is |

Note where the center of gravity sits. The internet-side half is a research errand. The air-gapped half is the program.

---

## 3 · The handoff artifact: the source bundle

One bundle per scenario (or per incident, if several scenarios draw on one incident, the schema allows `incidents[]` to be many-to-many). A bundle is a directory, it is immutable once transferred, and it is committed into the air-gapped environment alongside the record it produced.

### Layout

```
bundles/
  2026-08-04-hugging-face-openai-agent-intrusion/
    manifest.yaml
    SHA256SUMS               # over everything in raw/ and text/
    raw/
      s01-hf-security-incident-july-2026.html
      s02-hf-agent-intrusion-technical-timeline.html
      s03-openai-hf-model-evaluation-security-incident.html
      s04-cve-2026-XXXXX.json          # CVE Program record, raw JSON
      s05-jfrog-release-notes-7.161.15.html
    text/                    # normalized plain-text/markdown extraction of each raw file
      s01-hf-security-incident-july-2026.md
      .
    search_log.md            # queries run, and what they returned
```

`raw/` is what the retriever actually received. `text/` is a mechanical extraction, no summarizing, no reordering. Ship both: `raw/` is the evidentiary copy, `text/` is what the air-gapped side harness reads, and having both means an analyst in the air-gapped environment can tell "the extractor dropped a table" from "the source never said that."

### Manifest

```yaml
bundle_id: 2026-08-04-hugging-face-openai-agent-intrusion
scope_line: >
  July 2026 Hugging Face intrusion. 2026-07-09 to 2026-07-31.
  Parties: Hugging Face (victim), OpenAI (responsible party), JFrog (affected vendor).
retrieved_by: <named human>
retrieval_window: [2026-08-03, 2026-08-04]
harness: <what did the retrieval, model/orchestrator, version>
baseline: "2026.07"          # the framework pin this bundle is intended to be analyzed against

entries:
  - ref: s01
    tier: "0"                 # matches schema provenance.sources[].tier
    url: https://huggingface.co/blog/security-incident-july-2026
    final_url: https://huggingface.co/blog/security-incident-july-2026
    title: "Security incident. July 2026"
    publisher: Hugging Face
    published: 2026-07-15
    retrieved_at: 2026-08-03T14:22:00Z
    http_status: 200
    capture_method: raw-http-body      # raw-http-body | rendered-dom | pdf | api-json | manual-paste
    content_type: text/html
    bytes: 48213
    sha256_raw: <hex>
    sha256_text: <hex>
    complete: true                     # false if paywalled/gated/partial, say what is missing in note
    note: >
      Initial disclosure. Superseded on the database question by s02.

verification:                          # verdicts from the internet-side verification pass
  - claim: "Three CVEs were assigned in the JFrog batch"
    verdict: CORRECTED
    correct_value: "Four. CVE-2026-XXXXX is credited to a different org and is omitted from most reporting."
    evidence: s04
  - claim: "The agent reached the production database"
    verdict: UNRESOLVED
    detail: "HF and OpenAI directly contradict each other; neither has issued a correction as of retrieval date."
    evidence: [s02, s03]

not_found:                             # negative findings. The air-gapped environment cannot regenerate these
  - searched_for: "Independent forensic report commissioned by Hugging Face"
    result: "None published as of 2026-08-04."
  - searched_for: "CVE for the dataset-config template injection"
    result: "No CVE assigned; vendor treats it as a hardening change."

sources_to_avoid:
  - url: <.>
    reason: "Aggregator; IOC table assembled by scraping news articles; three wrong CVE IDs."
```

### Rules that make this work

1. **Hash on the retrieval side, rehash on intake.** If your cross-domain guard sanitizes or re-encodes HTML/PDF, many do, the post-transfer hash will not match, and that is not a failure, it is a fact you need recorded. Store `sha256_raw` as the provenance hash (what the retriever received) and record a separate `sha256_transferred` at intake if it differs, with the guard's name. Do not silently re-hash and overwrite; that destroys the only thing the hash was for.
2. **A record authored in the air-gapped environment may only cite URLs that appear in a bundle manifest.** This is checkable offline and the validator should enforce it. It is the single rule that keeps `provenance.sources[]` from filling up with half-remembered URLs the model produced from training data. Treat a citation with no manifest entry as a validation error, not a warning.
3. **Analysis in the air-gapped environment may downgrade a verification verdict, never upgrade it.** If the internet-side pass returned UNRESOLVED, an analyst in the air-gapped environment cannot make it CONFIRMED. They can add UNRESOLVED items. This asymmetry is the whole reason the verification block travels with the bundle.
4. **Negative findings are payload, not commentary.** `not_found` is the most perishable thing in the bundle, because it is the one thing the air-gapped environment absolutely cannot reconstruct. An analyst who does not know that nobody published a forensic report will write around the gap instead of recording it.
5. **Bundles are immutable.** A correction arriving next week is a *new* bundle with a `supersedes:` key, transferred again. Do not edit a transferred bundle in place; you lose the ability to say which version of the record the walkthrough saw.
6. **Bundle content is untrusted input.** This program's own scenario 001 is indirect prompt injection to data exfiltration, and scenario 013 is memory and context poisoning. You are about to feed attacker-adjacent web content into a model that has filesystem and git write access. The air gap removes the exfiltration channel; it does not remove the injection. Keep the harness's writes scoped to `scenarios/` and `bundles/`, never let a bundle's contents reach the MCP config or the harness prompt files, and treat any instruction-shaped text inside `text/` as data. If your air-gapped orchestrator supports a content/instruction separation marker, use it here.

---

## 4 · Pre-staging the framework data

`frameworks/baseline-2026.07.yaml` already tells you to do this, the migration rules say *"Vendor the pinned files into `frameworks/pinned/` with checksums. This doubles as the air-gapped copy."* This section is the mechanics.

### Layout

```
frameworks/
  baseline-2026.07.yaml
  pinned/
    2026.07/
      SOURCES.yaml           # same shape as a bundle manifest: url, retrieved, sha256, retriever
      SHA256SUMS
      attack/enterprise-attack-19.1.json
      atlas/ATLAS-2026.07.yaml
      owasp/OWASP-Top-10-for-LLMs-v2025.pdf
      owasp/owasp-top-10-agentic-2026.pdf
      owasp/ids.yaml         # the ID→name maps, extracted by hand from the PDFs
      dettect/               # repo snapshot at v2.2.0, or just scales.yaml (see below)
```

### Per-framework obtainability

| Framework | What to stage | How | Offline quality |
|---|---|---|---|
| **ATT&CK 19.1** | `enterprise-attack-19.1.json` from `mitre-attack/attack-stix-data` | `git clone` the repo if you want every versioned bundle (worth it, migration diffs need the previous pin too); otherwise fetch the single pinned file. Never fetch `enterprise-attack.json`, it floats. | Excellent. Complete, machine-readable, self-contained STIX. Includes the deprecated/revoked objects and the `revoked-by` relationships, so offline ID migration works. |
| **ATLAS 2026.07** | `dist/v6/ATLAS-2026.07.yaml` from `mitre-atlas/atlas-data` | Single file. Clone the repo if you want `v6/` and `legacy/` history for diffing, which you will, because ATLAS has no deprecation mechanism and you must diff releases yourself on `(id, modified-date)`. | Excellent as data. Poor as a change-tracking story, but that is equally true online. |
| **OWASP LLM 2025** | The PDF, plus a hand-maintained `ids.yaml` | PDF download. `machine_readable: none` in the baseline is accurate, there is no official structured release. The ID→name map already in `baseline-2026.07.yaml` *is* your machine-readable form; keep it there and treat `pinned/owasp/ids.yaml` as a copy for tooling. | Fine. Ten IDs and a PDF. Nothing to sync. |
| **OWASP Agentic 2026** | Same | Same. PDF only. | Same. |
| **DeTT&CT 2.2.0** | The scoring rubric | Best case of the four, "fully offline by design". In practice the program only consumes DeTT&CT's *scales* (visibility 0 to 4, detection -1.5, five quality dimensions 0 to 5), and those are already vendored in `baseline-2026.07.yaml`. Stage the repo snapshot if you want the editor UI and the YAML administration files. | Excellent, with one caveat below. |

**DeTT&CT caveat, flagged as uncertain.** The DeTT&CT CLI resolves ATT&CK content through `attackcti`, which speaks TAXII to `attack-taxii.mitre.org`. That is a network call, and it is the one place in the offline framework story that will bite you. Before assuming DeTT&CT tooling runs in the air-gapped environment, verify how your version resolves ATT&CK data and whether it can be pointed at a local STIX bundle. If it cannot, you lose nothing this program needs: the program stores DeTT&CT scores as integers on `telemetry[].dettect`, and the rubric for assigning them is prose. Use DeTT&CT as a scoring standard, not as a running tool, and note that in the record's `notes`.

### Verification and refresh

- `SHA256SUMS` is generated internet-side, travels with the files, and is verified at intake and again in CI on every air-gapped side pipeline run. A framework file that changed under you is a serious event; make it loud.
- `SOURCES.yaml` records who fetched what, when, and from which URL. Same discipline as a bundle manifest, the point is that an analyst in the air-gapped environment asking "where did this ATT&CK bundle come from" gets an answer without leaving the room.
- **Refresh cadence is annual, not continuous.** Aligned to the ATT&CK April release, per the baseline's migration rules. Do not chase ATLAS's monthly cadence; the baseline explicitly says not to, and in the air-gapped environment the temptation is lower anyway.
- **Migration requires staging two pins at once.** The rule "publish one cycle of metrics against BOTH pins" means `frameworks/pinned/` will hold `2026.07/` and `2027.04/` simultaneously for a full reporting cycle. Size your transfer window accordingly, this is the one framework sync per year that is not small.

---

## 5 · The analyst harness on opencode + MCP

Liszt itself is YAML, Markdown and Python, and it needs no assistant at all. This section is for teams that want an assistant to draft inside the boundary anyway. It describes the shape; it is not part of the tooling this repository ships.

### The shape in the air-gapped environment

An assistant harness in the air-gapped environment needs three things, whatever the product calls them: project-level instructions, per-agent prompts with a narrow brief each, and a tool policy. opencode holds configuration in `opencode.json` at the repository root plus markdown agent definitions, and project-level instructions in `AGENTS.md`. **Verify the exact paths and frontmatter keys against the opencode version in your air-gapped build before you commit to a layout**, this has moved between releases, so treat the shape below as the shape and not as guaranteed field names.

| Piece | Where it goes (opencode) | Notes |
|---|---|---|
| House rules, quality bar, style | `AGENTS.md` | The same rules the human analysts work to, in `docs/01-methodology.md` and `docs/02-quality-bar.md`. Do not fork them into a second wording. |
| Per-agent prompt | `.opencode/agent/<name>.md` | Frontmatter carries `mode`, `model` and `tools`; the body is the prompt. |
| Recurring commands, the weekly ritual | `.opencode/command/<name>.md` | One per step of the cadence in section 8. |
| Format rules the agents share | Fold into `AGENTS.md` or into an agent body | Keep one copy. Two copies drift silently. |
| File, search and shell tools | The built-in set, plus MCP | See the tool policy below. |
| Web fetch and web search | **Absent, by design** | Do not stub them. A stub that returns "no network" invites the model to answer from training data, which is exactly the failure the bundle exists to prevent. Remove the tool and say why in `AGENTS.md`. |

### Keeping the prompts identical

The prompts are the asset. If an internet-side harness and an air-gapped one each hold their own copy, they drift, and the drift is invisible until a record authored in the air-gapped environment reads differently from an internet-side one.

Keep the bodies in a harness-neutral directory and generate the per-target wrappers:

```
harness/
  prompts/
    scenario-drafter.md          # body only, no frontmatter
    framework-mapper.md
    telemetry-analyst.md
    record-validator.md
    tabletop-writer.md
    coverage-reporter.md
  targets/
    internet.yaml                # frontmatter per agent for this target
    air-gapped.yaml
  render_harness.py              # emits each target's agent files from one set of bodies
```

A renderer like that is twenty lines of yaml plus string concatenation, has no network dependency, and runs in CI on both sides. Check the generated files in so reviewers see the diff, and have CI fail if regeneration produces a change. Harness formats do not support include directives, so generation is the only way to get one source of truth.

### The agent roster

One narrow brief per agent, and two of them live on the *other* side of the gap.

| Agent | Brief | Side |
|---|---|---|
| Source Retriever | Fetch primary sources in full; build `raw/`, `text/`, `search_log.md` | Internet |
| Verification Analyst | CVE existence, credits, fixed build vs branch, dates against the repo | Internet |
| Scenario Drafter | Bundle → `title`, `slug`, `one_liner`, `attack_path[]` (3 to 6 steps, <=125 chars each, layer tags), `scaled_up`, `classification.evidence` | air-gapped |
| Framework Mapper | Assign ATT&CK/ATLAS/OWASP IDs against `frameworks/pinned/2026.07/`; set `mapping_confidence`; write `mapping_notes` naming every mapping a reasonable analyst would dispute | air-gapped |
| Telemetry Analyst | One row per attack-path step; `signal`, `emitted_at`, `detection_opportunity`; propose `coverage`; leave `dettect` for the data owners | air-gapped |
| Record Validator | Schema conformance plus house rules the schema cannot express (step/row parity, `coverage` recomputed from `dettect`, citation-in-manifest, `reviewed_by` != `authored_by`) | air-gapped |
| Tabletop Writer | Injects and facilitator notes from `attack_path[]` + `hardening[]` | air-gapped |
| Coverage Reporter | Narrative around the generated rollup, never the arithmetic itself | air-gapped |

Each air-gapped agent's brief opens with a line stating that its evidence universe is `bundles/<id>/` and `frameworks/pinned/<baseline>/`, and that anything it cannot support from those two directories is either marked as inference or sent to the outbound queue as a question.

### MCP servers

| Server | Scope | Why |
|---|---|---|
| **filesystem** | read-write: `scenarios/`, `incidents/`, `coverage/`, `bundles/<current>/`; read-only: `frameworks/pinned/`, `schema/`, `harness/prompts/` | The whole job. Read-only on the pinned frameworks is not paranoia, a model that "fixes" a STIX bundle to match its expectation silently corrupts every future metric. |
| **git** | branch, diff, log, status, commit; **no remote operations** | Provenance. Every record change should be a reviewable commit. Push happens through your normal air-gapped git server, by a human. |
| **framework-lookup** (local, recommend building) | Read-only query over `frameworks/pinned/` | See below. Highest-leverage thing on this list. |
| ~~web fetch / web search~~ |  | Not present. Not stubbed. |
| ~~any remote MCP~~ |  | Not present. If your air-gapped opencode build supports remote MCP transports at all, the harness config should explicitly declare none, and that config should be reviewed like code, because an MCP server *is* code. |

**On the framework-lookup server.** `enterprise-attack-19.1.json` is tens of megabytes of STIX. It must never enter the model's context wholesale, you will burn the window and get worse mapping, not better. A thin local MCP server exposing four tools solves this cleanly:

- `attack_lookup(id)` → name, tactics, description, deprecated/revoked status, `revoked_by` if any
- `attack_search(text)` → candidate technique IDs
- `attack_data_components(technique_id)` → the `DCxxxx` set (v18+ replaced data sources with data components; the schema enforces `DCxxxx`)
- `atlas_lookup(id)` → name, tactic, `attack-reference` if present (the only *authoritative* cross-framework link the program has)

This is ~150 lines of Python over the pinned files, has no network dependency, is trivially auditable, and it is the difference between a Framework Mapper that resolves real IDs and one that produces plausible-looking ones. Also expose `attack_lookup` returning "not found" as a distinct result from an error, a model that cannot distinguish "T9999 does not exist" from "the lookup broke" will invent.

### Context management

The air-gapped environment has context management; use it for the thing that actually needs it. The pattern that works: the Scenario Drafter reads `text/` in full (this is the one place you want the whole document in context, the program's own guidance is that most bad analysis is a summary of a summary), then hands a compacted scope line plus the drafted `attack_path[]` forward. Downstream agents get the compaction, not the corpus. The Framework Mapper never needs the source text; it needs the attack path and the lookup server.

---

## 6 · The Python tooling, the easy part

**Only one tool in `tools/` makes a network call, and it is the one that exists to.** `tools/pin_frameworks.py` fetches the framework artifacts once per baseline, and `--verify` re-checks them with no network at all. Everything else reads files in the repo and writes files in the repo: the validator reads YAML and JSON Schema, the renderer reads YAML and writes `.pptx`, the coverage rollup reads YAML and writes YAML and JSON, the viewer builder writes one HTML page and one JSON file, and `tools/import_from_deck.py` reads a `.pptx` and writes YAML.

This is worth saying plainly to whoever is reviewing this design, because "AI program" tends to trigger an assumption of API calls, and the assumption will cost you a review cycle if you do not pre-empt it. Apart from the framework pin, this program would run identically on a laptop in a Faraday cage.

### Dependencies to mirror

| Package | Needed by | Notes |
|---|---|---|
| `pyyaml` | everything | Pure Python. |
| `python-pptx` | `import_from_deck.py`, slide renderer | Pure Python, but pulls `lxml`, `Pillow`, `XlsxWriter`. |
| `lxml` | via python-pptx | **Binary wheel.** Must match the air-gapped platform and Python minor version. |
| `Pillow` | via python-pptx | **Binary wheel.** Same. |
| `XlsxWriter` | via python-pptx | Pure Python. |
| `jsonschema` | validator | Pulls `attrs`, `referencing`, `rpds-py`, `jsonschema-specifications`. |
| `rpds-py` | via jsonschema | **Binary wheel** (Rust extension). The one most likely to be missing from a partial mirror. |
| `pytest` | tests | Dev only, but you want tests running in the air-gapped environment. |

This repository ships no wheel files, so the packages have to reach the air-gapped
machine one of two ways. Pick whichever your organization already runs.

1. **An internal package mirror** (Artifactory, Nexus, devpi). Cleanest, because it is
   somebody else's job to keep it stocked. Point pip at it once and the normal install
   works with no further ceremony:
   ```bash
   pip config set global.index-url <your internal index url>
   bash install.sh                      # add --with-deck for the slide tools
   ```
2. **A wheel directory you build once and carry across.** On a machine with package
   index access, download the pinned dependencies for the exact Python and platform the
   air-gapped machine runs, then move the folder across the boundary with everything
   else:
   ```bash
   pip download -r requirements/base.txt -r requirements/deck.txt \
       --only-binary=:all: \
       --python-version 3.11 --platform manylinux_2_28_x86_64 \
       -d vendor/wheels
   ```
   Then, on the air-gapped machine, `bash install.sh --offline` (or
   `install.ps1 -Offline` on Windows) installs from `vendor/wheels` and touches no
   network. The installer stops with an explanation if that folder is missing, and
   `./liszt doctor` reports whether it is there.

   Use the platform tag that matches the target, `manylinux_2_28_x86_64` for Linux
   x86_64, `macosx_11_0_arm64` for Apple Silicon, `win_amd64` for Windows, and run one
   `pip download` per platform you have to support. Get the `--python-version` and
   `--platform` pair wrong and the binary wheels resolve to the *builder's* platform, so
   the install fails in the air-gapped environment, which is a bad place to discover it.
   Pin with hashes (`--require-hashes`) so the wheel directory is verifiable at intake
   like everything else crossing the boundary.

### Assert the no-network property

Add a CI check that runs the test suite with outbound sockets blocked (`pytest-socket`'s `--disable-socket`, or a network namespace). It costs nothing and it turns "the tooling has no network dependency" from a claim into a test. It also catches the day someone adds a convenience call to fetch the latest ATT&CK bundle.

### Fonts and rendering

`python-pptx` writes OOXML; it does not rasterize, so slide *generation* has no font dependency. Anything that exports to PDF or thumbnails does. If the weekly ritual includes a PDF, the corporate template's fonts must be installed in the air-gapped environment, and this is the kind of thing that is discovered thirty minutes before a walkthrough. Stage the `.potx` and its fonts with the framework data.

---

## 7 · What is genuinely degraded

No hedging here. These are real losses.

| Loss | Impact | Compensation | Residual risk |
|---|---|---|---|
| **No primary-source retrieval** | An analyst in the air-gapped environment cannot open a source. They read the bundle's extraction of it. | `raw/` travels alongside `text/`, so an analyst can at least see whether the extractor mangled a table. | If the retriever missed a source, the air-gapped environment cannot know. Mitigate with an explicit `search_log.md` so at least the *search space* is visible. |
| **No verification** | Cannot confirm a CVE exists, cannot check a fixed build, cannot see a correction issued after retrieval. | Verification runs internet-side and its verdicts ride in the manifest. The air-gapped environment may downgrade a verdict, never upgrade one. | A correction issued between retrieval and walkthrough is invisible. This is the sharpest edge in the whole design. Keep the retrieval-to-walkthrough window short (section 8), and re-retrieve before a record moves to `published`, not before it moves to `draft`. |
| **No "does this exist" check** | The model cannot distinguish a real CVE ID from a well-shaped hallucination. | The framework-lookup server covers ATT&CK/ATLAS/OWASP IDs, those *can* be checked offline against the pinned data, and the validator should reject any ID not in the pin. CVE IDs cannot. | Any CVE ID in a record authored in the air-gapped environment that is not in the bundle is unverifiable. Make the validator reject it outright rather than warn. |
| **No framework updates between syncs** | Pins go stale. | This is the intended state; the baseline is pinned for a full cycle by design. The migration rules already assume a deliberate, scheduled cut-over. | An out-of-band framework change (a data-correction release like 19.1 itself) will not reach the air-gapped environment until the next sync. Accept it, or budget an unscheduled sync for correction releases only. |
| **No incident discovery** | The air-gapped environment does not know what happened this week. | Internet-side weekly scan produces a candidate list; the list crosses the boundary as a one-page artifact even in weeks when no bundle does. | The scan is a human judgment call made outside the room where the estate knowledge lives. Expect to occasionally scope the wrong thing. |
| **Different model set** | The air-gapped environment's models are not the reference implementation's. Prompts that work on one may not transfer. | Golden-set regression: re-author two or three already-published scenarios from their original bundles and diff against the committed records. Do this at every model change in the air-gapped environment, not once at stand-up. | Silent quality drift. The diff is the only instrument you have. |
| **No langfuse/langchain tracing** | The observability stack from the internet-connected environment is not available. | Write harness transcripts into the repo (or an adjacent audit path) as part of the run. Ugly, but it is an auditable record and reviewers accept it. | Aggregate analysis across runs is manual. |
| **Outbound questions are constrained** | You cannot just ask the internet a follow-up. | Question queue (below). | Everything you send out is subject to your cross-domain policy and is a potential leak of internal context. This is a feature, not a bug, and it is why the queue is short. |

### The outbound question queue

When an analyst in the air-gapped environment hits something the bundle cannot answer, it goes in `notes:` on the record and onto a queue for the next internet-side retrieval pass.

Rules:

- **Questions are human-authored and human-reviewed before they leave.** Do not let the harness compose them. A model asked to write a follow-up question will helpfully include the internal context that motivated it, and that context is exactly what must not cross.
- **Questions are generic.** "Did the vendor publish a fixed build number for the package proxy?", not "we run version X of that proxy and need to know if we're exposed."
- **A record may not reach `status: published` while it has an open outbound question.** This is a house rule the validator can enforce by convention (an open question is a `notes:` line with a defined marker). It is what stops an unresolved gap from being laundered into a published metric.

---

## 8 · Recommended weekly split

The cadence is one week, with the retrieval pass running ahead of the analysis pass. The gap between them is set by your transfer window; the table assumes overnight.

| When | Side | Activity | Artifact |
|---|---|---|---|
| Mon AM | Internet | Candidate scan; scope decision with the air-gapped environment lead over whatever comms channel you have | One-page candidate list + a scope line |
| Mon PM. Tue | Internet | Source Retriever runs; Verification Analyst runs; bundle assembled, hashed | `bundles/<id>/` |
| Tue EOD | Boundary | Transfer | Bundle in the air-gapped environment |
| Wed AM | air-gapped | Intake: rehash, verify `SHA256SUMS`, commit the bundle, register it | Commit |
| Wed | air-gapped | Scenario Drafter + Framework Mapper. Produces a `status: draft` record | `scenarios/NNN-slug.yaml` |
| Thu | air-gapped | Telemetry working session with the data owners. This is the session that cannot be automated and should not be, `dettect` scores and `telemetry[].owner` come out of it | Record updated; `backlog_ref` filled for Blind/Collectable rows |
| Thu PM | air-gapped | Validator; fix; validator again | Green build |
| Fri AM | air-gapped | Render the two slides; run the coverage rollup; generate the tabletop pack | `.pptx`, `coverage/<org>/`, tabletop MD |
| Fri PM | air-gapped | The walkthrough | Session notes → `notes:`; questions → outbound queue |
| Following Mon | Internet | Outbound queue becomes retrieval asks alongside the new week's scan |  |

Two things to protect:

- **Thursday's telemetry session is the program.** Everything upstream of it is preparation and everything downstream is packaging. It happens in the air-gapped environment, with the people who own the data sources, and the air gap is irrelevant to it. If the week is compressed, cut Friday's polish, not Thursday.
- **`published` lags `draft` by at least one retrieval cycle.** A record drafted Wednesday from a Tuesday bundle should not be published Friday. Let it sit as `in-review`, let the outbound questions come back, and publish the week after with a fresh verification pass. The schema already requires `reviewed_by` to differ from `authored_by`; the air gap gives you a natural reason to space those apart in time as well.

---

## 9 · Things to verify in your air-gapped build before committing to this

Listed honestly, because each one changes the design if it comes back the wrong way.

1. **opencode's agent/command/MCP config paths and frontmatter keys** in the version you have. section 5 describes the shape; the field names have moved between releases.
2. **Whether opencode in the air-gapped environment can run local (stdio) MCP servers at all**, and what the review process is for adding one. The framework-lookup server is the highest-leverage recommendation here and it is a local MCP server.
3. **How DeTT&CT resolves ATT&CK data** in your version, and whether it can be pointed at a local STIX bundle. Fallback: use the rubric, skip the tool.
4. **What your cross-domain guard does to HTML and PDF.** If it rewrites content, section 3's hash discipline matters more; if it rejects HTML outright, `text/` becomes the primary artifact and `raw/` stays internet-side with only its hash crossing.
5. **Whether the outbound question queue is permitted at all.** Some environments are inbound-only. If yours is, the queue becomes a verbal channel and the "no publish with open questions" rule becomes the whole control.
6. **Binary wheel availability** for `lxml`, `Pillow`, and `rpds-py` on the exact Python in the air-gapped environment. Check before the sync window, not after.
