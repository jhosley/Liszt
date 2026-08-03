#!/usr/bin/env python3
"""
Vendor the pinned framework artifacts into frameworks/pinned/<baseline>/ with checksums.

    python tools/pin_frameworks.py                       # fetch and record
    python tools/pin_frameworks.py --verify              # re-check existing files, no network
    python tools/pin_frameworks.py --baseline 2026.07

Run this ONCE per baseline, in an internet-connected environment, then commit the
result. Two things follow from that:

  1. Framework IDs become verifiable offline. Nothing in this repo should ever
     confirm an ID from memory, and in an air-gapped environment there is no
     alternative but these files.
  2. The checksums make the pin auditable. "We reported Q3 against ATT&CK 19.1"
     is a claim; a sha256 that still matches is evidence.

--verify makes no network calls and is safe to run in the air-gapped environment or in CI.

Artifacts that cannot be fetched programmatically (the OWASP PDFs are the usual
case) are reported, not silently skipped. Download them by hand into the same
directory and re-run --verify to record their checksums.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import urllib.error
import urllib.request

try:
    import yaml
except ImportError:
    sys.exit("pip install pyyaml")

ROOT = pathlib.Path(__file__).resolve().parent.parent


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def targets(base: dict) -> list[dict]:
    fw = base["frameworks"]
    out = [
        {"key": "attack", "filename": "enterprise-attack-19.1.json",
         "url": fw["attack"].get("pinned_url"),
         "version": f"{fw['attack']['version']} (spec {fw['attack']['spec_version']})"},
        {"key": "atlas", "filename": f"ATLAS-{fw['atlas']['version']}.yaml",
         "url": fw["atlas"].get("pinned_url"),
         "version": f"{fw['atlas']['version']} (format {fw['atlas']['format_version']})"},
        {"key": "owasp_llm", "filename": "OWASP-Top-10-for-LLMs-2025.pdf",
         "url": fw["owasp_llm"].get("pdf"),
         "version": fw["owasp_llm"]["edition"]},
        {"key": "owasp_agentic", "filename": "OWASP-Top-10-Agentic-2026.pdf",
         "url": None,   # download by hand from the resource page in the baseline
         "version": fw["owasp_agentic"]["edition"],
         "manual": fw["owasp_agentic"]["site"]},
        {"key": "dettect", "filename": "DeTTECT-2.2.0/",
         "url": None,
         "version": fw["dettect"]["version"],
         "manual": f"git clone --branch v{fw['dettect']['version']} {fw['dettect']['repo']}"},
    ]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baseline", default="2026.07")
    ap.add_argument("--verify", action="store_true", help="no network; re-check what is on disk")
    args = ap.parse_args()

    bpath = ROOT / "frameworks" / f"baseline-{args.baseline}.yaml"
    if not bpath.exists():
        sys.exit(f"no such baseline: {bpath}")
    base = yaml.safe_load(bpath.read_text())

    dest = ROOT / "frameworks" / "pinned" / args.baseline
    dest.mkdir(parents=True, exist_ok=True)
    lock_path = dest / "CHECKSUMS.json"
    lock = json.loads(lock_path.read_text()) if lock_path.exists() else {}

    manual, failed = [], []
    for t in targets(base):
        path = dest / t["filename"]

        if t["url"] is None and not path.exists():
            manual.append(t)
            continue

        if not args.verify and t["url"] and not path.exists():
            print(f"  fetching {t['filename']} .", flush=True)
            try:
                with urllib.request.urlopen(t["url"], timeout=120) as r, path.open("wb") as fh:
                    fh.write(r.read())
            except (urllib.error.URLError, OSError) as e:
                print(f"    FAILED: {e}")
                failed.append(t)
                continue

        if not path.exists():
            manual.append(t)
            continue

        digest = sha256(path) if path.is_file() else "directory"
        prior = lock.get(t["key"], {}).get("sha256")
        if prior and prior != digest and digest != "directory":
            print(f"  MISMATCH {t['filename']}")
            print(f"    recorded {prior}")
            print(f"    on disk  {digest}")
            print("    A pinned artifact changed. Either the file was replaced, or the pin is "
                  "not immutable. Investigate before reporting any metric against it.")
            failed.append(t)
            continue

        lock[t["key"]] = {"filename": t["filename"], "version": t["version"],
                          "url": t["url"], "sha256": digest,
                          "bytes": path.stat().st_size if path.is_file() else None}
        print(f"  ok {t['filename']:<40} {digest[:16]}.")

    lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")

    if manual:
        print("\nFetch these by hand into "
              f"{dest.relative_to(ROOT)}/ then re-run with --verify:")
        for t in manual:
            print(f"  {t['filename']:<40} {t.get('manual') or t.get('url')}")

    if failed:
        print(f"\n{len(failed)} artifact(s) failed. The pin is incomplete, do not treat "
              "framework IDs as verifiable offline until this is clean.")
        return 1

    print(f"\npin recorded in {lock_path.relative_to(ROOT)}")
    print("Commit it. --verify re-checks these hashes with no network access, which is "
          "what makes the pin usable in an air-gapped environment and assertable in CI.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
