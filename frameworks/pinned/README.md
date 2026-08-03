# Pinned framework artifacts

Immutable copies of the exact framework releases named in `frameworks/baseline-<version>.yaml`,
with checksums. Populate with `python tools/pin_frameworks.py`, then commit.

Two reasons this directory exists, and both matter:

**Verifiability.** No framework ID in this repo may be confirmed from memory. In an
internet-connected environment you could re-fetch; in the air-gapped environment you cannot. These files are the
only offline authority.

**Auditability.** "We reported Q3 coverage against ATT&CK 19.1" is a claim. A sha256 that
still matches a year later is evidence. When the numbers are questioned, and on a
multi-year program they will be, this is what settles it.

```
frameworks/pinned/
  2026.07/
    CHECKSUMS.json                      generated; commit it
    enterprise-attack-19.1.json         ~53 MB, fetched
    ATLAS-2026.07.yaml                  fetched
    OWASP-Top-10-for-LLMs-2025.pdf      fetched
    OWASP-Top-10-Agentic-2026.pdf       download by hand
    DeTTECT-2.2.0/                      git clone --branch v2.2.0
```

`python tools/pin_frameworks.py --verify` makes no network calls. Run it in CI and in the air-gapped environment.
A hash mismatch means a pinned artifact changed under you. Stop and investigate before
reporting any metric against it.

**Size note.** The ATT&CK bundle is large. If your git host objects, use Git LFS or an
internal artifact store and keep `CHECKSUMS.json` in the repo regardless. The checksums are
the important part, not the bytes.

Never delete a superseded baseline's directory. Historical metrics are only defensible
while the artifacts they were computed against still exist.
