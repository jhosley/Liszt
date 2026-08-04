# Prototype workflow: a published incident into a Liszt scenario

This is the fast, prototype-only path for the published-incident journey. It lets you turn
a real incident into a draft scenario you can open, score with the system owners, and export,
without hand-writing a record.

There are three pieces:

1. **Find incidents** — a prompt you run in any LLM with web access to get a good list.
2. **Map one incident** — a second prompt that turns a chosen incident into scenario JSON.
3. **Add it to Liszt** — paste that JSON into the viewer.

The JSON these prompts produce is a faithful subset of the real scenario record, so a scenario
you bring in this way can later become a permanent `scenarios/NNN-*.yaml` record with no rework.

> **What this path does and does not do.** It gets a structured, framework-tagged draft into the
> library in minutes. It does **not** score coverage. Scoring is the job of the system owners in a
> session, on the two questions Liszt asks, and the verdict is computed from those scores. The
> prompts below deliberately never guess a score.

---

## Step 1 — Find published incidents (discovery prompt)

Run this in an LLM that can browse the web. Adjust the count or the time window as you like.

```
You are a threat-intelligence researcher building a list of PUBLISHED, real-world security
incidents that involve AI INFRASTRUCTURE. Use web search and cite a source URL for every item.

Scope "AI infrastructure" broadly. Include incidents that touch any of:
  - Model supply chain: tampered or backdoored models, poisoned weights, malicious models on
    public hubs (Hugging Face and similar), typosquatted model or package names.
  - Inference and serving: exploited inference servers, model-loading / deserialization code
    execution, exposed or unauthenticated model endpoints and AI gateways.
  - Data layer: training-data poisoning, RAG / vector-database poisoning or leakage, exposed
    vector stores.
  - Orchestration and agents: agent tool abuse, prompt-injection that led to real impact,
    malicious or vulnerable MCP servers and tool connectors, agent-to-agent compromise.
  - MLOps and pipelines: compromised training or deployment pipelines, leaked API keys or
    credentials for AI services, exposed notebooks or experiment trackers.
  - Guardrails and safety controls: bypasses that caused a real incident, not lab-only demos.

For each incident, give me a row with:
  1. Short name
  2. Date (or "reported <month year>")
  3. Who disclosed it (vendor, researcher, CISA, press)
  4. One sentence on what actually happened
  5. The single AI infrastructure layer it MOST affects, chosen from exactly:
     L0 · Infrastructure | L1 · Data | L2 · Model | L3 · Orchestration & Agent | L4 · Application
  6. Source URL
  7. Source tier: 1 = first-party (vendor post-mortem, CISA, the affected org),
                  2 = reputable press or named research team,
                  3 = community report or aggregator
  8. One line on why it matters to a defender

Rules:
  - Prefer confirmed incidents over research demonstrations. If you include a notable
    proof-of-concept because it is important, label it clearly as "research, not in the wild."
  - Prefer first-party and tier-1 sources. Do not include vendor marketing.
  - Do not speculate. If a detail is unknown, say "unknown."
  - Spread the list across the layers above; do not return ten of the same kind.

Return the 12 most relevant items as a table, most recent and most severe first.
```

Skim the list, pick one, and move to step 2.

---

## Step 2 — Map one incident into Liszt scenario JSON (mapping prompt)

Paste the discovery row (or the incident's source URL) where marked, then run this. It returns
**only JSON**, ready to paste into the viewer.

```
You are mapping ONE published incident into a Liszt scenario record. Research the incident using
the source(s) I give you, then output a SINGLE JSON object and NOTHING else. No prose, no code
fence, just the JSON.

THE INCIDENT:
<<< paste the incident name and its source URL here >>>

Produce JSON with exactly this shape:

{
  "title": "short scenario title, an attacker-goal phrasing, e.g. 'Poisoned model on a public hub reaches our inference stack'",
  "one_liner": "2-3 plain sentences a non-expert can follow: what the attacker does and what the damage is. Write it about OUR environment ('our', 'we'), not about the specific victim.",
  "classification": {
    "ai_infrastructure_layer": "the one layer it mostly happens at, chosen from exactly: L0 · Infrastructure | L1 · Data | L2 · Model | L3 · Orchestration & Agent | L4 · Application",
    "evidence": "seen-in-the-wild if a real incident occurred, or seen-in-research if it is a demonstrated proof of concept",
    "priority": "NOW, NEAR-TERM, or BACKLOG, your best judgment of urgency for a defender",
    "priority_rationale": ["3 short bullets on why it rates that priority, each a plain sentence"]
  },
  "attack_path": [
    { "step": 1, "layer": "the stack layer this move lands on, using the same five-layer vocabulary or a short 'A -> B' form like 'Data / inbound' or 'Model -> App'", "text": "one move of the attack, in plain language" }
  ],
  "telemetry": [
    { "step": 1, "signal": "the observable event this move would produce", "emitted_at": "where that event would be emitted from, named generically (e.g. 'EDR / container runtime logs', 'AI gateway logs', 'model registry logs')", "detection_opportunity": "what a detection could look for here" }
  ],
  "framework_mapping": {
    "baseline": "2026.07",
    "attack": ["MITRE ATT&CK technique IDs at v19.1 that apply, e.g. T1059; [] if none"],
    "atlas": ["MITRE ATLAS technique IDs at 2026.07 that apply, e.g. AML.T0010; [] if none"],
    "owasp_llm": ["OWASP LLM 2025 IDs like LLM03:2025; [] if none"],
    "owasp_agentic": ["OWASP Agentic 2026 IDs like ASI02; [] if none"]
  },
  "incidents": [
    { "title": "the source's title", "url": "the source URL", "tier": "1, 2, or 3" }
  ]
}

Rules:
  - One telemetry entry per attack_path step, sharing the same step number.
  - DO NOT include any coverage, visibility, detection, or score field anywhere. Coverage is
    scored later by the people who own the systems. You only identify the signal that WOULD exist.
  - Use real framework identifiers only where you are confident. If a mapping is your judgment
    rather than an official crosswalk, still include the ID but keep the list short and defensible.
  - Keep attack_path to 4-7 steps. Every step should be a distinct move.
  - Output valid JSON only. No trailing commas. No commentary.
```

---

## Step 3 — Add it to Liszt

1. Run `./liszt serve` and open the page.
2. Click **Start session mode** (top right), then **Readback and export**.
3. In the **Imported scenarios, from an incident** panel, click **Import a scenario from JSON**.
4. Paste the JSON from step 2 and click **Add to the library**.

It appears in the Scenarios list right away as a draft, with a generated id like `IMP-1`. Open it
and you will see the attack path and the evidence rows. In session mode, score each row with the
owners the same way you score any scenario; the coverage verdict computes from those scores.

### How it persists

Imported scenarios live in the browser session (they survive a reload) and in the file that
**Export session file** produces. That keeps the prototype simple and keeps the records clean:
nothing is written to `scenarios/` automatically. When an imported scenario has earned its place,
an analyst turns it into a permanent `scenarios/NNN-*.yaml` record. The JSON shape here is a subset
of that record, so it is a copy-and-fill, not a rewrite.

You can paste a single scenario object or a JSON array of several at once.
