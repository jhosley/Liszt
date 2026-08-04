# Prototype workflow: a scenario into Liszt, from an incident or a hypothesis

This is the fast, prototype-only path that gets two of the journeys running today. Both end the
same way: a draft scenario you can open, score with the system owners, and export, without
hand-writing a record.

- **Path A, a published incident.** Something that really happened to someone else.
- **Path B, an analyst hypothesis.** An attack nobody has run yet, proposed by the AI Threat
  Modeler. Liszt tags these so they read differently from a real incident.

Every path is: a prompt produces scenario JSON, and you paste that JSON into the viewer. The JSON
is a faithful subset of the real scenario record, so anything you bring in this way can later
become a permanent `scenarios/NNN-*.yaml` record with no rework.

> **What this path does and does not do.** It gets a structured, framework-tagged draft into the
> library in minutes. It does **not** score coverage. Scoring is the job of the system owners in a
> session, on the two questions Liszt asks, and the verdict is computed from those scores. The
> prompts below deliberately never guess a score.

---

# Path A — a published incident

## Step A1 — Find published incidents (discovery prompt)

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

## Step A2 — Map one incident into Liszt scenario JSON (mapping prompt)

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

## Step A3 — Add it to Liszt

See **"Adding any scenario to Liszt"** at the end of this document. It is the same for both paths.

---

# Path B — an analyst hypothesis

This is the hypothesis journey: an attack nobody has run yet. The analyst has an idea; this prompt
turns that idea into the same structured, framework-tagged scenario the system works with, and
marks it as proposed by the AI Threat Modeler so it never gets mistaken for a real incident.

## Step B1 — Turn a hypothesis into Liszt scenario JSON (mapping prompt)

Write your hypothesis in plain language where marked. It can be a sentence or a paragraph. Then
run this in any LLM. It returns **only JSON**, ready to paste into the viewer.

```
You are an AI threat modeler. Take the analyst hypothesis below, an attack that has NOT
happened yet, and turn it into a rigorous Liszt scenario. Output a SINGLE JSON object and
NOTHING else. No prose, no code fence, just the JSON.

THE HYPOTHESIS:
<<< write your hypothesis here, in plain language. What is the attacker trying to do, and
    what makes you worried it could work against us? >>>

Your job is to sharpen the idea, not to judge it. Break it into concrete moves, and for each
move name the observable signal a defender would look for. Do not soften a real concern and do
not inflate a weak one.

Produce JSON with exactly this shape:

{
  "origin": "hypothesis",
  "proposed_by": "AI Threat Modeler",
  "title": "short scenario title in attacker-goal phrasing",
  "one_liner": "2-3 plain sentences about OUR environment ('our', 'we'): what the attacker does and why it would hurt.",
  "classification": {
    "ai_infrastructure_layer": "the one layer it mostly happens at, chosen from exactly: L0 · Infrastructure | L1 · Data | L2 · Model | L3 · Orchestration & Agent | L4 · Application",
    "evidence": "seen-in-research",
    "priority": "NOW, NEAR-TERM, or BACKLOG, the analyst's best judgment of urgency",
    "priority_rationale": ["3 short bullets on why it rates that priority. It is honest to say 'nobody has run this yet, but ...' here."]
  },
  "attack_path": [
    { "step": 1, "layer": "the stack layer this move lands on, using the five-layer vocabulary or a short 'A -> B' form", "text": "one move of the attack, in plain language" }
  ],
  "telemetry": [
    { "step": 1, "signal": "the observable event this move WOULD produce if it happened", "emitted_at": "where that event would be emitted from, named generically", "detection_opportunity": "what a detection could look for here" }
  ],
  "framework_mapping": {
    "baseline": "2026.07",
    "attack": ["ATT&CK v19.1 IDs that apply; [] if none"],
    "atlas": ["ATLAS 2026.07 IDs that apply; [] if none"],
    "owasp_llm": ["OWASP LLM 2025 IDs; [] if none"],
    "owasp_agentic": ["OWASP Agentic 2026 IDs; [] if none"]
  }
}

Rules:
  - Keep "origin": "hypothesis" and "proposed_by": "AI Threat Modeler" exactly as written, so
    Liszt tags this as a threat-modeler scenario. If a specific analyst wants their name on it,
    they may replace the proposed_by value with their own.
  - One telemetry entry per attack_path step, sharing the same step number.
  - DO NOT include any coverage, visibility, detection, or score field. The owners score it later.
    You only identify the signal that WOULD exist.
  - Keep attack_path to 4-7 distinct moves.
  - Use real framework identifiers only where you are confident. A hypothesis may map to nothing
    in the catalogs yet; an empty list is a fine and honest answer.
  - Output valid JSON only. No trailing commas. No commentary.
```

## Step B2 — Add it to Liszt

Same as any scenario, below. Once imported, it shows a purple **Threat modeler** tag in the list
and a **Threat modeler hypothesis** tag on the record, so anyone can see at a glance that it is a
proposed attack, not one seen in the wild.

---

# Adding any scenario to Liszt

1. Run `./liszt serve` and open the page.
2. Click **Start session mode** (top right), then **Readback and export**.
3. In the **Imported scenarios, from an incident** panel, click **Import a scenario from JSON**.
4. Paste the JSON and click **Add to the library**.

It appears in the Scenarios list right away as a draft, with a generated id like `IMP-1`. Open it
and you will see the attack path and the evidence rows. In session mode, score each row with the
owners the same way you score any scenario; the coverage verdict computes from those scores.
Hypothesis scenarios carry the threat-modeler tag through all of this.

### How it persists

Imported scenarios live in the browser session (they survive a reload) and in the file that
**Export session file** produces. That keeps the prototype simple and keeps the records clean:
nothing is written to `scenarios/` automatically. When an imported scenario has earned its place,
an analyst turns it into a permanent `scenarios/NNN-*.yaml` record. The JSON shape here is a subset
of that record, so it is a copy-and-fill, not a rewrite.

You can paste a single scenario object or a JSON array of several at once, and you can mix
incident and hypothesis scenarios in one array.
