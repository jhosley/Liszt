# 05 · Environments

**Audience:** anyone asking "where does this actually run" before committing a seat, a license or a review cycle.
**Scope:** orientation only. It maps each pipeline stage to the environment that can run it. The air-gapped detail lives in `docs/09-air-gapped.md`.

---

## The load-bearing insight

**Research needs internet. Everything else does not. The air gap falls cleanly between them.**

The program has exactly one internet-dependent step: getting the primary sources and verifying them. Every artifact the program actually produces, the scenario record, the two slides, the coverage numbers, the tabletop pack, is computation over material already in hand. That is not luck; it is a consequence of the schema. `provenance.sources[]` is a list of *references*, not a live feed, and every other field is derived by an analyst reading those bytes against a pinned framework baseline.

So this is not one program running in a degraded mode in the air-gapped environment. It is one program with a single stage on the other side of a boundary, and a defined artifact, the source bundle, crossing it.

**Second thing to say early:** the Python tooling has **zero network dependency**. `validate.py`, `render_slides.py`, `import_from_deck.py` and the rollup read files in the repo and write files in the repo. Not one API call. "AI program" invites the assumption of API calls; pre-empt it or it costs a review cycle. Assert it in CI with sockets disabled so it stays true.

---

## The four environments

| Environment | What it is | Internet | Role here |
|---|---|---|---|
| **The air-gapped environment** | Multi-model, agent orchestration, MCP, opencode | **No** | Where the program runs. Everything from bundle intake onward |
| **High-power internet env** | langfuse / langchain, full network | Yes | Research and verification. The only genuinely network-bound stage |
| **M365 Copilot / Copilot Studio** | Tenant surfaces over SharePoint | Yes (tenant) | Research drafting (Studio) and library distribution (Copilot). Never authoring the final record, never arithmetic |
| **An assistant with repository access** | A coding assistant working on a checkout of this repo, with an exfiltration control around it | Yes | Drafting and repo chores on the research half. It drafts; a human analyst reviews and owns every record |

---

## Pipeline stage → where it runs

| Stage | Where | Why |
|---|---|---|
| Candidate scan, what happened worth a scenario | Internet env · Copilot Studio · an assistant with web access | Requires discovery. Nothing offline can do it |
| Scope decision | Internet-side, human | Cheap, and it determines what gets retrieved |
| Primary source retrieval, full documents, not snippets | Internet env · Copilot Studio · an assistant with web access | The one genuinely network-bound step |
| Verification. CVE exists, fixed build vs branch, dates against the repo | Internet env, with live registries open | Needs live registries. Cannot be redone offline at any confidence |
| Bundle assembly, manifest, hashes, negative findings | Internet-side | The handoff artifact. `docs/09-air-gapped.md` section 3 |
| **Cross-domain transfer** | **Boundary** | Your guard/diode process, not ours |
| Bundle intake, rehash, register, commit | air-gapped | Local |
| Scenario drafting, `one_liner`, `attack_path[]`, `scaled_up` | air-gapped (Studio may draft prose) | Reading and writing over material in hand |
| Framework mapping. ATT&CK / ATLAS / OWASP IDs | air-gapped | Needs the pinned artifacts vendored into `frameworks/pinned/` with checksums, that is the intended location and it is not populated yet, so this step cannot go offline until it is. A local framework-lookup MCP server is the highest-leverage build here |
| Telemetry rows, `signal`, `emitted_at`, `detection_opportunity` | air-gapped | Needs estate knowledge, which is *inside* the air-gapped environment |
| DeTT&CT scoring, `dettect`, `owner`, `evidence`, `backlog_ref` | air-gapped, with the data owners | Human session with the people who own the sources. Arguably better in the air-gapped environment than out of it. No model has the evidence to do this |
| `hardening[]` ranking | air-gapped | Needs the control inventory |
| Validation, schema + house rules | air-gapped, Python | Deterministic, must give the same answer every run, must run in CI |
| Slide render | air-gapped, Python | `python-pptx` into a fixed template with hard geometry |
| Coverage rollup, exposure, maturity, snapshots | air-gapped, Python | Arithmetic against a pinned baseline. A probabilistic step anywhere in this path destroys year-over-year comparability |
| Tabletop pack | air-gapped, Python | Local generation from `attack_path[]` + `hardening[]` |
| Walkthrough | air-gapped | Where the audience is |
| Library Q&A, "do we already cover X?" | M365 Copilot · Copilot Studio | Distribution. Grounded on the published SharePoint view, reading a reviewed artifact |

Note where the center of gravity sits: the internet half is a research errand, the air-gapped half is the program.

---

## The line that decides every one of these

**Judgment over text → an agent. Reproducible computation → Python, in the repo.**

If you are asking a model to count how many rows are `Blind`, you have crossed it, and the answer will be plausible and wrong. Coverage, exposure and maturity are defined in `docs/04-measurement.md` precisely so they can be computed identically every run; `derive_coverage()` in `tools/validate.py` is the rule and it lives in exactly one place.

---

## Two hazards worth flagging here

- **Do not stub `WebFetch`/`WebSearch` in the air-gapped environment.** A stub returning "no network" invites the model to answer from training data, which is the exact failure the bundle exists to prevent. Remove the tool and say why in `AGENTS.md`. Enforce the corollary in the validator: a record authored in the air-gapped environment may only cite URLs present in a bundle manifest.
- **Bundle content is untrusted input.** Scenario 001 is indirect prompt injection to exfiltration; 013 is memory and context poisoning. The air gap removes the exfiltration channel, not the injection. Scope harness writes to `scenarios/` and `bundles/`, keep bundle text away from harness config, treat instruction-shaped text as data. On the internet side, this is what the exfiltration control around the assistant's seat is for.

---

## Where to read next

| Question | Doc |
|---|---|
| How do I run the whole program with no internet? | `docs/09-air-gapped.md`, separation principle, source bundle format, pre-staging framework pins, dependency mirroring, what is genuinely degraded |
| How do I distribute the library to people who never open the repo? | `tools/publish_library.py`, which writes the records out as Markdown pages for a SharePoint or intranet view |
| What do the numbers mean? | `docs/04-measurement.md` |
