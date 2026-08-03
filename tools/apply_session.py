#!/usr/bin/env python3
"""
Apply a session file recorded in the viewer back into the scenario records.

    python3 tools/apply_session.py liszt-session-2026-08-02.json
    python3 tools/apply_session.py session.json --dry-run
    python3 tools/apply_session.py session.json --org platform-eng

This closes the loop. The viewer captures coverage scores, the exact source a signal
comes from, owners and ticket numbers while the people who own those systems are still
in the room. This writes them into the YAML records, preserving every comment.

A session can also propose a scenario the library does not have. Each proposal in the
session file's "new_scenarios" list becomes a draft record here, built from the template
by tools/new_scenario.py, so the id, the slug and the filename are right and every
teaching comment survives. The record is a starting point, not a finished scenario.

Nothing is committed automatically. Review the diff, run the validator, then commit.

    git diff
    python3 tools/validate.py
    git add -A && git commit -m "Session 2026-08-02: scenarios 021, 004"

WITH --org, the changes are written to coverage/<org>/<id>.yaml as an overlay instead of
to the scenario records. Use that when the session assessed one organization's estate
rather than the reference assessment. Coverage is a property of an estate, not of a
scenario, and mixing the two is how a shared library becomes unusable.
"""
from __future__ import annotations

import argparse
import io
import json
import pathlib
import sys

try:
    from ruamel.yaml import YAML
    from ruamel.yaml.comments import CommentedMap
except ImportError:
    sys.exit("pip install ruamel.yaml   (it preserves the comments in the records; "
             "PyYAML does not)")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
# One place builds a record, and it is not this file. Importing it means a scenario
# proposed in a session and one started at the keyboard come out identical.
from new_scenario import ScaffoldError, create_scenario, next_scenario_id

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIELDS = ("dettect", "coverage", "source", "owner", "evidence", "backlog_ref", "notes")

yaml = YAML()
yaml.preserve_quotes = True
yaml.width = 120        # keep one-line step text on one line
yaml.indent(mapping=2, sequence=4, offset=2)   # match the library's style


def flow(d: dict) -> "CommentedMap":
    """Keep the quality block on one line, as the library writes it by hand."""
    m = CommentedMap(d)
    m.fa.set_flow_style()
    return m


def derive(d: dict | None) -> str | None:
    if not d:
        return None
    v, det = d.get("visibility"), d.get("detection")
    if v is None or det is None:
        return None
    if v == 0:
        return "Blind"
    return "Have" if det >= 1 else "Collectable"


def record_path(sid: str) -> pathlib.Path | None:
    hits = list((ROOT / "scenarios").glob(f"{sid}-*.yaml"))
    return hits[0] if hits else None


def apply_to_record(path: pathlib.Path, changes: dict, dry: bool) -> list[str]:
    doc = yaml.load(path.read_text(encoding="utf-8"))
    log = []
    rows = {int(r["step"]): r for r in doc.get("telemetry", [])
            if r.get("kind", "attack-step") == "attack-step"}

    for step_s, upd in (changes.get("telemetry") or {}).items():
        row = rows.get(int(step_s))
        if row is None:
            log.append(f"    step {step_s}: NO SUCH ROW, skipped")
            continue
        for key in FIELDS:
            if key not in upd:
                continue
            new = upd[key]
            if new in ("", None):
                continue
            old = row.get(key)
            if key == "dettect":
                old_s = f"v{(old or {}).get('visibility')} d{(old or {}).get('detection')}" if old else "unscored"
                new_s = f"v{new.get('visibility')} d{new.get('detection')}"
                if old_s == new_s:
                    continue
                # Mutate in place where the row already has scores. Replacing the map
                # would drop ruamel's record of the original formatting, and the quality
                # block would flip from flow style to block style for no reason.
                if old is not None:
                    # An inline comment on a score described the OLD value. Leaving it
                    # in place next to a new number is worse than losing it, so drop it
                    # and say so.
                    for k in ("visibility", "detection"):
                        if int(new[k]) != old.get(k) and k in getattr(old, "ca", None).items:
                            del old.ca.items[k]
                            log.append(f"    step {step_s}: dropped a stale inline comment on {k}")
                    old["visibility"] = int(new["visibility"])
                    old["detection"] = int(new["detection"])
                    if new.get("quality") and not old.get("quality"):
                        old["quality"] = flow(new["quality"])
                else:
                    row["dettect"] = CommentedMap(
                        [("visibility", int(new["visibility"])),
                         ("detection", int(new["detection"]))]
                        + ([("quality", flow(new["quality"]))] if new.get("quality") else []))
                # coverage is derived, never taken from the session file
                d = derive(row["dettect"])
                if d:
                    row["coverage"] = d
                log.append(f"    step {step_s}: scores {old_s} -> {new_s}, coverage {d}")
            elif key == "coverage":
                continue          # always derived, never written directly
            elif old != new:
                row[key] = new
                shown = (str(old)[:40] + "..") if old and len(str(old)) > 40 else old
                log.append(f"    step {step_s}: {key} {shown or '(empty)'} -> {str(new)[:60]}")

    if changes.get("notes"):
        prior = doc.get("notes", "")
        stamp = changes.get("recorded", "session")
        doc["notes"] = (prior + "\n\n" if prior else "") + f"[{stamp}] {changes['notes']}"
        log.append("    record notes appended")

    # A proposed use case captured in the room lands in the record's notes, so the
    # thought survives until an analyst turns it into a record in use-cases/. The
    # session file never writes use-cases/ directly; those records go through the
    # same authoring and review path as everything else.
    if changes.get("use_case_note"):
        prior = doc.get("notes", "")
        stamp = changes.get("recorded", "session")
        doc["notes"] = (prior + "\n\n" if prior else "") + \
            f"[{stamp}] Proposed use case: {changes['use_case_note']}"
        log.append("    proposed use case appended to notes")

    if log and not dry:
        buf = io.StringIO()
        yaml.dump(doc, buf)
        path.write_text(buf.getvalue(), encoding="utf-8")
    return log


def apply_to_overlay(sid: str, changes: dict, org: str, meta: dict, dry: bool) -> list[str]:
    out_dir = ROOT / "coverage" / org
    path = out_dir / f"{sid}.yaml"
    doc = yaml.load(path.read_text(encoding="utf-8")) if path.exists() else {
        "scenario": sid, "org": org,
        "assessed_by": meta.get("facilitator", "session"),
        "assessed": meta.get("recorded", ""), "telemetry": []}

    rows = {int(r["step"]): r for r in doc.get("telemetry", [])}
    log = []
    for step_s, upd in (changes.get("telemetry") or {}).items():
        step = int(step_s)
        row = rows.get(step)
        if row is None:
            row = {"step": step}
            doc.setdefault("telemetry", []).append(row)
            rows[step] = row
        for key in FIELDS:
            if key in upd and upd[key] not in ("", None) and key != "coverage":
                row[key] = upd[key]
        if row.get("dettect"):
            d = derive(row["dettect"])
            if d:
                row["coverage"] = d
        row.pop("inherit", None)
        log.append(f"    step {step}: overlay updated")

    doc["assessed"] = meta.get("recorded", doc.get("assessed", ""))
    if meta.get("facilitator"):
        doc["assessed_by"] = meta["facilitator"]

    if log and not dry:
        out_dir.mkdir(parents=True, exist_ok=True)
        buf = io.StringIO()
        yaml.dump(doc, buf)
        path.write_text(buf.getvalue(), encoding="utf-8")
    return log


def create_proposals(proposals: list, author: str, dry: bool) -> int:
    """
    Turn each proposed scenario in the session file into a draft record, and say where each
    one landed. Returns how many were made.

    A proposal with no title is skipped rather than written. A record nobody named is worse
    than no record: somebody has to work out later what it was meant to be, and by then the
    room has gone home.
    """
    made, taken = 0, []
    for i, p in enumerate(proposals, 1):
        title = str((p or {}).get("title") or "").strip() if isinstance(p, dict) else ""
        if not title:
            print(f"  proposal {i}  NO TITLE, skipped, nothing was written for it")
            continue
        try:
            sid = next_scenario_id(taken)
            path = create_scenario(title, mode=p.get("mode"), layer=p.get("layer"),
                                   priority=p.get("priority"), author=author or None,
                                   one_liner=p.get("one_liner"), sid=sid, dry_run=dry)
        except ScaffoldError as e:
            print(f"  proposal {i}  {title}")
            print(f"    NOT CREATED: {e}")
            continue
        taken.append(sid)
        made += 1
        print(f"  {sid}  {path.name}")
        print(f"    {'would be written' if dry else 'written'} from the template, status draft"
              f"{', authored by ' + author if author else ''}")
    return made


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session", type=pathlib.Path)
    ap.add_argument("--org", help="write a coverage overlay instead of editing the records")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.session.exists():
        sys.exit(f"not found: {args.session}")
    data = json.loads(args.session.read_text(encoding="utf-8"))
    if data.get("session_format") != 1:
        sys.exit(f"unsupported session_format: {data.get('session_format')}")

    meta = {"recorded": data.get("recorded", ""), "facilitator": data.get("facilitator", "")}
    changes = data.get("changes") or {}
    # new_scenarios is an addition to session_format 1. A file written before it existed
    # simply has no key, which means no proposals, not an error.
    proposals = data.get("new_scenarios") or []
    if not changes and not proposals:
        sys.exit("the session file records no changes and proposes no scenarios")

    print(f"session recorded {meta['recorded'] or 'date not set'}"
          f"{', facilitated by ' + meta['facilitator'] if meta['facilitator'] else ''}")
    print(f"{'writing overlay for ' + args.org if args.org else 'editing the scenario records'}"
          f"{'  (DRY RUN, nothing written)' if args.dry_run else ''}\n")

    touched = 0
    for sid in sorted(changes):
        path = record_path(sid)
        if path is None:
            print(f"  {sid}  NO SUCH SCENARIO, skipped")
            continue
        # The stamp on any appended note is the session date. It lives at the top
        # of the session file, so hand it down to where the append happens.
        if isinstance(changes[sid], dict) and meta["recorded"]:
            changes[sid].setdefault("recorded", meta["recorded"])
        log = (apply_to_overlay(sid, changes[sid], args.org, meta, args.dry_run)
               if args.org else apply_to_record(path, changes[sid], args.dry_run))
        print(f"  {sid}  {path.name}")
        print("\n".join(log) if log else "    no change")
        touched += bool(log)

    made = 0
    if proposals:
        note = (", written to scenarios/ rather than to the overlay, because a new scenario "
                "belongs to the shared library") if args.org else ""
        print(f"\n{len(proposals)} proposed scenario(s) in this session file{note}")
        made = create_proposals(proposals, meta["facilitator"], args.dry_run)

    summary = f"{touched} scenario(s) changed"
    if proposals:
        summary += (f" · {made} new record(s) "
                    f"{'that would be written' if args.dry_run else 'written'}")
    print("\n" + summary + (" (dry run)" if args.dry_run else ""))
    if not args.dry_run and (touched or made):
        print("\nNothing has been committed. Next:")
        print("  git diff")
        print("  python3 tools/validate.py")
        print("  git add -A && git commit -m \"Session <date>: scenarios <ids>\"")
        if touched:
            print("\nThe coverage label was recomputed from the scores, not taken from the "
                  "session file. If a label in the viewer disagreed with the scores, the "
                  "scores win.")
        if made:
            print("\nEach new record is a draft built from the template, not a finished "
                  "scenario. Open it, replace every PLACEHOLDER, and work the gates in "
                  "docs/01-methodology.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
