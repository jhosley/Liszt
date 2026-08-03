# 06 · Keeping current

**Audience:** the framework baseline owner, and anyone proposing a change to the schema, the validator or the docs.
**Scope:** how new framework releases, new threats and new practice reach this repository, and how a change to the methodology itself gets made.

The frameworks change. New attack classes appear. Your own analysts learn things. Without
a procedure, a methodology quietly rots: the docs describe a process nobody follows any
more, the framework IDs drift out of date, and the numbers stop meaning what they meant.

This is that procedure. It is deliberately small, three input streams, one change process,
one drift detector.

---

## 1 · The three input streams

Everything that should change this methodology arrives through one of three doors.

| Stream | What arrives | Lands in | Who watches it |
|---|---|---|---|
| **Frameworks** | ATT&CK, ATLAS, OWASP, DeTT&CT releases | `frameworks/baseline-*.yaml` | Baseline owner |
| **Threat landscape** | New incidents, published research, new attack classes | `incidents/` and new `scenarios/` | Whoever runs the walkthroughs |
| **Our own practice** | Things we learned doing this | `docs/` and `schema/` | The reviewer pool |

Anything that does not fit one of these three is probably not a methodology change. Do
not let the docs accumulate opinions.

---

## 2 · Stream 1, framework releases

### What to watch, and how often

| Framework | Cadence | Action |
|---|---|---|
| **MITRE ATT&CK** | ~April and October | The trigger for an annual re-baseline. Watch the April release. |
| **MITRE ATLAS** | ~monthly | **Do not chase it.** Fold into the annual re-baseline. |
| **OWASP LLM Top 10** | irregular | Watch. A new edition renumbers everything, see below. |
| **OWASP Agentic** | irregular, new list | Watch. |
| **DeTT&CT** | irregular, follows ATT&CK | Upgrade with ATT&CK. |

Set a calendar reminder for **1 April** and **1 October**. Two entries, both owned by the
baseline owner named in the current `frameworks/baseline-*.yaml`.

### The re-baseline procedure

Do this once a year, not every time something ships.

1. **Cut a new baseline file.** Copy `frameworks/baseline-2026.07.yaml` to
   `frameworks/baseline-<new>.yaml`. Mark the old one `status: superseded`; never delete
   it, historical metrics are only defensible while the baseline they were computed
   against still exists.
2. **Update the version block** for each framework: version, spec/format version, release
   date, pinned artifact filename, pinned URL.
3. **Read the release notes for breaking changes** and record them in
   `breaking_changes_since_prior_baseline`. Two real examples of what to look for: ATT&CK
   v18 retired data sources for data components, and v19 split Defense Evasion into two
   tactics. Either would silently corrupt a year-over-year comparison.
4. **Vendor the artifacts:** `python tools/pin_frameworks.py --baseline <new>`.
5. **Migrate the records.** For ATT&CK this is partly automatable, walk the `revoked-by`
   relationships in the STIX bundle to remap renamed IDs. For ATLAS and both OWASP lists
   there is nothing automatable; diff the releases by hand on `(id, modified-date)`.
6. **Dual-report for one full cycle.** Publish metrics against both the old and the new
   pin. This is what makes a year-over-year delta attributable to your controls rather
   than to framework churn. Skipping this is the most common way a program loses the
   ability to defend its own numbers.
7. **Switch.** Update `framework_mapping.baseline` in every record, re-validate, snapshot.

### When OWASP publishes a new edition

OWASP IDs are edition-scoped and the slots get reshuffled. `LLM03:2025` and `LLM03:2028`
are different risks. This is why every OWASP ID in this repo carries its edition.

Do **not** bulk find-and-replace. Read the new edition's "what changed" section, remap by
meaning rather than by number, and record the remap in the new baseline file. Where OWASP
does not publish a complete old→new crosswalk, and historically it has not, your remap
is your own editorial work. Label it as such.

### When a genuinely new framework appears

If something new becomes load-bearing, a NIST AI framework, a regulator's control set,
an internal control catalog, add it as a new key under `frameworks:` in the baseline
and a new array in the schema's `framework_mapping`. Two rules:

- **Add the array; do not overload an existing one.** Cramming a NIST control into the
  `attack` array destroys every query.
- **Bump `schema_version` and write the migration note.** See section 4.

Resist adding frameworks that nobody will actually use for a decision. Every framework you
add is a column somebody has to fill in forever.

---

## 3 · Stream 2, new threats and emerging methods

### Where candidates come from

- Published incidents and post-mortems
- Vendor and academic research
- Your own red team, or a finding from a real internal incident
- A tabletop that surfaced something the library does not cover
- A new capability your organization adopted, a new agent platform, a new model gateway,
  a new data pipeline. **New capability is the most commonly missed source.** The estate
  changing is as much a trigger as the threat landscape changing.

### The intake test, is it a new scenario?

Ask three questions in order:

1. **Is it already covered?** Search the library. If an existing scenario's attack path
   already describes this chain, it is not new, it is a revision. Update that record.
2. **Is it one coherent chain, or a theme?** "Agentic attacks" is a theme. "An agent
   escapes its sandbox and pivots into production" is a scenario. If it needs more than
   six steps, it is a theme, split it.
3. **Would the telemetry map differ from an existing scenario's?** This is the sharpest
   test. If the signals, sources and detection opportunities would be substantially the
   same as an existing record, you are duplicating. The telemetry map is the deliverable;
   two scenarios that produce the same map are one scenario.

If it passes all three, it is a new scenario. Work it with `docs/01-methodology.md`.

If it fails test 1, it is a **revision**: update the existing record, bump
`provenance.last_updated`, and have it re-reviewed. A revision to a published record needs
the same review as a new one.

### Retiring a scenario

Scenarios go stale. A technique gets designed out; a platform is decommissioned; a
scenario turns out to be a duplicate.

Set `status: retired` and fill the `retired` block with the date, the reason, and
`superseded_by` if another record now covers it. **Never delete the file.** Retired
records are excluded from current metrics but preserve the history, and a deleted record
takes its reasoning with it.

Review the library for retirement candidates once a year, at the re-baseline.

---

## 4 · Stream 3, changing the methodology itself

This is the stream people forget, and it is the one that keeps the docs honest.

### What counts as a methodology change

- A new or changed field in `schema/scenario.schema.json`
- A new or changed rule in `tools/validate.py`
- A change to a gate in `docs/01-methodology.md` or a check in `docs/02-quality-bar.md`
- A change to the coverage derivation rule, the scoring scales, or a metric definition

### How a change gets made

Everything here is in git, so use git. There is no separate process to build.

1. **Someone proposes it**, in writing, with the problem it solves. A methodology change
   without a named problem is a preference.
2. **Branch, change, and update everything it touches.** A change is not done until the
   schema, the validator, the docs and the reference record agree. The single most common
   failure is changing the docs and not the validator, or vice versa, after which the
   written rule and the enforced rule diverge and nobody notices for months.
3. **Run `./liszt validate`.** Zero errors. If a schema change makes existing records invalid,
   that is a migration, not a change, see below.
4. **A second person reviews it.** Same independence rule as scenario review.
5. **Merge.** The git history is the change log; you do not need another one.

### Rules that keep changes cheap

- **A rule you cannot check is not a rule.** If you write it into `docs/02-quality-bar.md`,
  either the validator enforces it or the reviewer's checklist has a question for it. Prose
  that is neither is decoration.
- **Prefer adding a check to writing a paragraph.** The validator is read every day; the
  docs are read twice.
- **Optional first.** New fields start optional and warned-on, and become required only
  after enough records carry them. A required field added on day one invalidates the whole
  library.

### Schema migrations

If a change makes existing records invalid, it is a migration:

1. Bump `schema_version` in the schema.
2. Write `schema/CHANGELOG.md`, what changed, why, and how to convert an old record.
3. Ship a conversion script in `tools/` if more than a handful of records are affected.
4. Convert everything and re-validate before merging. **Never leave the library in a state
   where some records are on one schema version and some on another.**

---

## 5 · The drift detector

The three streams above tell you when the world changed. This tells you when *you* changed
without noticing.

**Run the two-analyst calibration exercise** from `docs/02-quality-bar.md`:

- Whenever a new analyst joins
- Whenever a second organization starts contributing
- Whenever two orgs' records start looking noticeably different
- Once a year regardless

Two analysts independently work the same scenario without conferring, then compare.
Agreement on the attack path should be high. **Agreement on coverage scoring is where drift
shows**, that is the number that feeds every report, and it is the most subjective.

When divergence is wider than you can defend, the fix is almost never "try harder". It is
a missing rule: something the methodology leaves to judgment that should be specified.
Write the rule, add the check, and re-run.

---

## 6 · The annual review, one checklist

Once a year, aligned to the ATT&CK April release. Half a day.

- [ ] Framework baseline owner is a named individual, not a team, and still works here
- [ ] Cut the new baseline; mark the old one superseded
- [ ] Record breaking changes since the last baseline
- [ ] Re-vendor pinned artifacts; `./liszt verify-pin` is clean
- [ ] Migrate framework IDs in every record; re-validate
- [ ] Publish one cycle of dual-pin metrics before switching
- [ ] Review every published record for retirement
- [ ] Run the calibration exercise
- [ ] Read `docs/01` and `docs/02` end to end and fix anything that no longer describes
      what people actually do
- [ ] Confirm every rule in the docs is either validator-enforced or on the reviewer's
      checklist; delete or implement the rest
- [ ] Re-read `docs/00-outcomes.md`. Are the observables still the right ones?
- [ ] Take a dated snapshot and archive it

---

## 7 · What good looks like a year in

- The baseline has been cut once, deliberately, with a dual-report cycle behind it.
- Nobody has bulk-replaced a framework ID.
- No published record cites a framework version that is not pinned.
- At least one scenario has been retired, and its file is still there.
- At least one methodology change was made because two analysts disagreed and the
  disagreement turned out to be a missing rule.
- `docs/01` still describes what people actually do. If it does not, the docs lost and
  the practice won, fix the docs, not the people.
