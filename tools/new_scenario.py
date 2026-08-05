#!/usr/bin/env python3
"""
Start a new record from the template, with the id, the slug and the filename already right.

    python3 tools/new_scenario.py                       # ask the questions, then write it
    python3 tools/new_scenario.py --title "Poisoned vector store in a shared index" \
            --mode attack --layer L3 --priority NEAR-TERM --author "the platform analyst"
    python3 tools/new_scenario.py --use-case            # start a use case record instead

With no arguments it asks five plain questions and writes the record. With --title it asks
nothing, so it can be scripted or called from another tool.

What it does that a copy of the template does not:

  * takes the next free id, one past the highest in the library. Ids are never reused, not
    even from a retired record, so it counts from the top rather than filling gaps.
  * builds the slug from the title and names the file "<id>-<slug>.yaml", which is the
    exact name tools/validate.py insists on.
  * keeps every teaching comment in the template, because the comments are most of what
    the template is for.
  * stops if a record with a very similar slug already exists. A duplicate is the most
    common way this library goes wrong. Pass --force when you have looked and it really is
    a different scenario.
  * runs the validator on what it wrote, so the warnings you are expected to clear are on
    screen before you start.

Nothing is committed. The record is born at status draft and stays there until a human
reviewer publishes it.

The record-writing parts are importable: next_scenario_id(), slugify(), create_scenario()
and create_use_case(). tools/apply_session.py calls them when a session file carries
proposed scenarios, so the two paths cannot drift apart.
"""
from __future__ import annotations

import argparse
import datetime
import io
import pathlib
import re
import subprocess
import sys
from typing import Iterable

try:
    from ruamel.yaml import YAML
    from ruamel.yaml.scalarstring import FoldedScalarString, SingleQuotedScalarString
except ImportError:
    sys.exit("pip install ruamel.yaml   (it preserves the comments in the template; "
             "PyYAML does not)")

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCENARIOS = ROOT / "scenarios"
USE_CASES = ROOT / "use-cases"

MODES = ("attack", "failure")
PRIORITIES = ("NOW", "NEAR-TERM", "BACKLOG")
LAYERS = ("L0 · Infrastructure", "L1 · Data", "L2 · Model",
          "L3 · Orchestration & Agent", "L4 · Application")
# Where the scenario operates decides which component it is filed under. Set together so a
# scaffolded record is not internally inconsistent on its first day. Change either by hand.
COMPONENT_FOR_LAYER = {"L0": "Infrastructure", "L1": "Data", "L2": "Model",
                       "L3": "Agent", "L4": "Application"}
SLUG_CAP = 60           # schema/scenario.schema.json caps the slug at 60 characters
ONE_LINER_MIN = 40      # schema/scenario.schema.json minimum for one_liner
TITLE = (8, 70)         # schema/scenario.schema.json title length
UC_TITLE = (8, 90)      # schema/use-case.schema.json title length

# Words that carry no meaning in a slug. Two titles that differ only in these are the same
# scenario wearing a different hat, which is what the near-duplicate check is looking for.
FILLER = {"a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "from", "with",
          "via", "by", "at", "into", "our", "we", "us", "that", "this", "it", "its",
          "is", "are", "be", "new", "using", "through"}

_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.width = 120        # keep one-line step text on one line
_yaml.indent(mapping=2, sequence=4, offset=2)   # match the library's style

_safe = YAML(typ="safe")


class ScaffoldError(Exception):
    """Something that stops a record being written, worded so a person can act on it."""


# ── ids, slugs and the near-duplicate check ─────────────────────────────────

def slugify(title: str, cap: int = SLUG_CAP) -> str:
    """
    Title to slug: lower case, every run of anything that is not a letter or a digit
    becomes one hyphen, no hyphen at either end. Cut to the cap at a word boundary, never
    in the middle of a word, because half a word in a filename reads like a typo forever.
    """
    flat = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    if not flat:
        raise ScaffoldError("the title has no letters or numbers in it, so there is "
                            "nothing to build a slug from")
    if len(flat) <= cap:
        return flat
    kept: list[str] = []
    used = 0
    for word in flat.split("-"):
        cost = len(word) + (1 if kept else 0)
        if used + cost > cap:
            break
        kept.append(word)
        used += cost
    # One word longer than the whole cap: there is no boundary to cut at, so cut it short.
    return "-".join(kept) or flat[:cap].strip("-")


def _index(folder: pathlib.Path) -> list[dict]:
    """
    Every real record in a folder as {path, id, slug}. Templates and anything else starting
    with "_" are skipped, the same rule tools/validate.py uses.

    The id and the slug are read from the file and from the filename, and both are kept.
    A record that will not parse still holds an id, and that id must never be handed out
    again.
    """
    out = []
    for path in sorted(folder.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        rec = {}
        try:
            loaded = _safe.load(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                rec = loaded
        except Exception:
            pass          # the broken file gets its own finding from the validator
        m = re.match(r"^(UC-\d{3}|\d{3})-(.+)$", path.stem)
        out.append({
            "path": path,
            "id": str(rec.get("id") or (m.group(1) if m else "")),
            "file_id": m.group(1) if m else "",
            "slug": str(rec.get("slug") or (m.group(2) if m else path.stem)),
        })
    return out


def _next_number(folder: pathlib.Path, prefix: str, also: Iterable[str]) -> int:
    seen = {0}
    for rec in _index(folder):
        for value in (rec["id"], rec["file_id"]):
            m = re.fullmatch(rf"{prefix}(\d{{3}})", value or "")
            if m:
                seen.add(int(m.group(1)))
    for value in also or ():
        m = re.fullmatch(rf"{prefix}(\d{{3}})", str(value))
        if m:
            seen.add(int(m.group(1)))
    return max(seen) + 1


def next_scenario_id(also: Iterable[str] = ()) -> str:
    """
    The next free scenario id, one past the highest in scenarios/. Never a gap: an id
    belongs to the record that had it, including a retired one, and handing it out twice
    would make two records answer to the same number in every report ever written.

    Pass ids handed out earlier in the same run as 'also' when nothing has been written yet.
    """
    n = _next_number(SCENARIOS, "", also)
    if n > 999:
        raise ScaffoldError("scenario ids are 3 digits and 999 is taken. Widening the id "
                            "is a schema change, not something this tool should decide.")
    return f"{n:03d}"


def next_use_case_id(also: Iterable[str] = ()) -> str:
    """The next free use case id, one past the highest in use-cases/. Same rule as above."""
    n = _next_number(USE_CASES, "UC-", also)
    if n > 999:
        raise ScaffoldError("use case ids are 3 digits and UC-999 is taken. Widening the "
                            "id is a schema change, not something this tool should decide.")
    return f"UC-{n:03d}"


def _shape(slug: str) -> tuple:
    """A slug with the filler words dropped and the rest sorted, so word order stops mattering."""
    return tuple(sorted(w for w in slug.split("-") if w and w not in FILLER))


def similar_records(slug: str, folder: pathlib.Path) -> list[dict]:
    """
    Records whose slug is close enough to be the same scenario. Two tests, both cheap and
    both blunt on purpose: the same words once the filler is dropped, or one slug sitting
    whole inside the other. The hyphens on each end make the containment test respect word
    boundaries, so "rag" does not match "storage".
    """
    shape, padded = _shape(slug), f"-{slug}-"
    hits = []
    for rec in _index(folder):
        other = rec["slug"]
        if not other:
            continue
        if _shape(other) == shape or padded in f"-{other}-" or f"-{other}-" in padded:
            hits.append(rec)
    return hits


def _duplicate_check(slug: str, folder: pathlib.Path, force: bool, what: str) -> None:
    if force:
        return
    hits = similar_records(slug, folder)
    if not hits:
        return
    names = ", ".join(str(h["path"].relative_to(ROOT)) for h in hits)
    raise ScaffoldError(
        f"a {what} with a very similar slug already exists: {names}.\n"
        f"A duplicate is the most common way this library goes wrong. Read that record "
        f"first. If it covers this, amend it instead of writing a second one.\n"
        f"If you have looked and it really is a different {what}, run the same command "
        f"again with --force.")


def _check_title(title: str, limits: tuple, what: str) -> str:
    """
    A title short enough to be a placeholder, or long enough to overflow the slide, cannot
    validate. Catch it here rather than write a record that cannot pass.
    """
    title = (title or "").strip()
    if not title:
        raise ScaffoldError(f"a {what} needs a title")
    low, high = limits
    if not low <= len(title) <= high:
        raise ScaffoldError(f"a {what} title is {low} to {high} characters and that one is "
                            f"{len(title)}, so the record could not validate: {title}")
    return title


def _choice(name: str, value, allowed: tuple, default):
    """One value out of a fixed list, case insensitive, or a message naming the list."""
    if value in (None, ""):
        return default
    for a in allowed:
        if str(value).strip().lower() == a.lower():
            return a
    raise ScaffoldError(f"{name} must be one of: {', '.join(allowed)}. Got: {value}")


def resolve_layer(value):
    """
    The layer, from the full string or from just its number. The full strings carry a middle
    dot that is awkward to type, so "L3" is accepted and means the same thing.
    """
    if value in (None, ""):
        return None
    text = str(value).strip()
    for layer in LAYERS:
        if text.lower() == layer.lower() or text.upper() == layer[:2]:
            return layer
    # Tolerate the near misses a language model actually produces, and canonicalize them,
    # rather than failing an otherwise good record on a separator. The middle dot is easy
    # to lose: "L3 - Orchestration & Agent" and "L3 Orchestration and Agent" mean the layer
    # the author picked. What is NOT tolerated is a string naming several layers, because
    # that is an unanswered question rather than a typo.
    if len(re.findall(r"L[0-4]", text.upper())) > 1:
        raise ScaffoldError(
            "layer names more than one layer, so it is not a choice. Pick one of: "
            + " | ".join(LAYERS) + f". Got: {value}")
    m = re.search(r"\bL\s*([0-4])\b", text, re.I)
    if m:
        return LAYERS[int(m.group(1))]
    squash = lambda x: re.sub(r"[^a-z]+", "", x.lower().replace("&", "and"))
    for layer in LAYERS:
        if squash(text) == squash(layer[5:]):
            return layer
    raise ScaffoldError("layer must be one of: " + " | ".join(LAYERS) +
                        f", or just its number such as L3. Got: {value}")


# ── writing the records ─────────────────────────────────────────────────────

def _dump(doc, path: pathlib.Path, dry_run: bool) -> pathlib.Path:
    if not dry_run:
        buf = io.StringIO()
        _yaml.dump(doc, buf)
        path.write_text(buf.getvalue(), encoding="utf-8")
    return path


def create_scenario(title: str, *, mode=None, layer=None, priority=None, author=None,
                    one_liner=None, force: bool = False, dry_run: bool = False,
                    sid: str | None = None) -> pathlib.Path:
    """
    Write a new scenario record built from scenarios/_TEMPLATE.yaml and return its path.

    Everything not given keeps what the template ships, which is a placeholder the author
    is expected to replace. The record is always born at status draft. Nothing is ever
    overwritten: if the file exists, this raises instead.
    """
    title = _check_title(title, TITLE, "scenario")
    mode = _choice("mode", mode, MODES, "attack")
    layer = resolve_layer(layer)
    priority = _choice("priority", priority, PRIORITIES, None)
    slug = slugify(title)
    sid = sid or next_scenario_id()
    path = SCENARIOS / f"{sid}-{slug}.yaml"
    if path.exists():
        raise ScaffoldError(f"{path.relative_to(ROOT)} already exists. Nothing was written.")
    _duplicate_check(slug, SCENARIOS, force, "scenario")

    doc = _yaml.load((SCENARIOS / "_TEMPLATE.yaml").read_text(encoding="utf-8"))
    doc["id"] = SingleQuotedScalarString(sid)
    doc["slug"] = slug
    doc["title"] = title
    doc["status"] = "draft"

    cls = doc["classification"]
    if "mode" in cls:
        cls["mode"] = mode
    else:
        cls.insert(list(cls.keys()).index("priority") + 1, "mode", mode,
                   comment="attack: somebody drives the chain. "
                           "failure: nobody does, something breaks.")
    if layer:
        cls["ai_infrastructure_layer"] = layer
        cls["primary_layer_component"] = COMPONENT_FOR_LAYER[layer[:2]]
    if priority:
        cls["priority"] = priority
    if one_liner:
        doc["one_liner"] = FoldedScalarString(one_liner.strip())

    today = SingleQuotedScalarString(datetime.date.today().isoformat())
    prov = doc["provenance"]
    if author:
        prov["authored_by"] = author
    prov["created"] = today
    prov["last_updated"] = today
    return _dump(doc, path, dry_run)


def create_use_case(title: str, *, covers=None, author=None, force: bool = False,
                    dry_run: bool = False, uid: str | None = None) -> pathlib.Path:
    """
    Write a new use case record built from use-cases/_TEMPLATE.yaml and return its path.

    Same discipline as a scenario: next free id, slug from the title, filename
    "<id>-<slug>.yaml", template comments kept, nothing overwritten. The record is born at
    status proposed, which is the only status a use case starts at.
    """
    title = _check_title(title, UC_TITLE, "use case")
    if covers not in (None, "") and not re.fullmatch(r"\d{3}", str(covers).strip()):
        raise ScaffoldError("the scenario it covers is a 3 digit id such as 021. "
                            f"Got: {covers}")
    slug = slugify(title)
    uid = uid or next_use_case_id()
    path = USE_CASES / f"{uid}-{slug}.yaml"
    if path.exists():
        raise ScaffoldError(f"{path.relative_to(ROOT)} already exists. Nothing was written.")
    _duplicate_check(slug, USE_CASES, force, "use case")

    doc = _yaml.load((USE_CASES / "_TEMPLATE.yaml").read_text(encoding="utf-8"))
    doc["id"] = uid
    doc["title"] = title
    doc["status"] = "proposed"
    if covers:
        doc["covers"][0]["scenario"] = SingleQuotedScalarString(str(covers).strip())
    if author:
        doc["provenance"]["authored_by"] = author
    return _dump(doc, path, dry_run)


# ── asking the questions ────────────────────────────────────────────────────

def _ask(question: str, hint: str = "", limits: tuple | None = None) -> str:
    """One free text answer. Asks again while the answer is empty or the wrong length."""
    while True:
        print("\n" + question)
        if hint:
            print("  " + hint)
        try:
            answer = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit("\nStopped. Nothing was written.")
        if not answer:
            print("  That one cannot be left empty.")
            continue
        if limits and not limits[0] <= len(answer) <= limits[1]:
            n = len(answer)
            print(f"  That one is {n} character{'' if n == 1 else 's'} long. It has to be "
                  f"between {limits[0]} and {limits[1]}.")
            continue
        return answer


def _ask_choice(question: str, options: list[tuple[str, str]]) -> str:
    """
    One answer out of a numbered list. The number or the value itself is accepted, and a
    wrong answer just asks again.
    """
    while True:
        print("\n" + question)
        for i, (value, label) in enumerate(options, 1):
            print(f"  {i}) {label}")
        try:
            answer = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit("\nStopped. Nothing was written.")
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1][0]
        for value, _ in options:
            if answer.lower() == value.lower():
                return value
        print(f"  Answer with a number from 1 to {len(options)}.")


def _confirm(question: str) -> bool:
    while True:
        try:
            answer = input(f"\n{question} (yes/no)\n> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            sys.exit("\nStopped. Nothing was written.")
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("  Answer yes or no.")


def ask_scenario() -> dict:
    print("\nA few questions, then the record gets written.")
    title = _ask("What is this scenario called?",
                 f"{TITLE[0]} to {TITLE[1]} characters, the way it should read on the slide. "
                 "Example: Poisoned vector store in a shared index", TITLE)
    mode = _ask_choice("Is this an attack or a failure?", [
        ("attack", "attack, somebody is driving it"),
        ("failure", "failure, nobody is driving it and something breaks on its own")])
    layer = _ask_choice("Which layer does it mostly happen at?",
                        [(l, l) for l in LAYERS])
    priority = _ask_choice("How urgent is the work on it?", [
        ("NOW", "NOW, this is the cycle we spend on it"),
        ("NEAR-TERM", "NEAR-TERM, the cycle after this one"),
        ("BACKLOG", "BACKLOG, real but not now")])
    author = _ask("Who is writing it?",
                  "Your name goes on the record. A tool cannot own a record.")
    return {"title": title, "mode": mode, "layer": layer,
            "priority": priority, "author": author}


def ask_use_case() -> dict:
    print("\nA few questions, then the record gets written.")
    title = _ask("What is this use case called?",
                 "Name the decision it makes, not the tool that makes it. "
                 "Example: Correlated prompt injection with data movement", UC_TITLE)
    covers = _ask("Which scenario does it serve?",
                  "The 3 digit id of a record in scenarios/, such as 021.")
    author = _ask("Who is writing it?",
                  "Your name goes on the record. A tool cannot own a record.")
    return {"title": title, "covers": covers, "author": author}


# ── the command ─────────────────────────────────────────────────────────────

def _run_validator(path: pathlib.Path) -> None:
    print("\nWhat the validator says about it now:")
    subprocess.run([sys.executable, str(ROOT / "tools" / "validate.py"), str(path)])


def _report_scenario(path: pathlib.Path, one_liner: str | None) -> None:
    rel = path.relative_to(ROOT)
    print(f"\nWrote {rel}")
    _run_validator(path)
    if one_liner and len(one_liner.strip()) < ONE_LINER_MIN:
        print(f"\nThe plain terms paragraph is {len(one_liner.strip())} characters. The "
              f"record needs at least {ONE_LINER_MIN}, so write it out properly before review.")
    print("\nThose warnings are the work, not a complaint. Next:")
    print(f"  1. Open {rel} and replace every PLACEHOLDER. The validator does not flag "
          "that word, you are the check.")
    print("  2. Work the gates in docs/01-methodology.md.")
    print(f"  3. python3 tools/validate.py {rel}")
    print("\nNothing has been committed, and the record stays a draft until a reviewer "
          "who is not the author publishes it.")


def _report_use_case(path: pathlib.Path, covers: str | None) -> None:
    rel = path.relative_to(ROOT)
    print(f"\nWrote {rel}")
    if covers and not list(SCENARIOS.glob(f"{covers}-*.yaml")):
        print(f"There is no scenario {covers} in scenarios/ yet, so the validator will "
              "say the covered scenario does not exist until there is one.")
    _run_validator(path)
    print("\nThose findings are the work, not a complaint. Next:")
    print(f"  1. Open {rel} and replace every PLACEHOLDER, starting with the steps it covers.")
    print("  2. Read use-cases/UC-001-correlated-prompt-injection-with-data-movement.yaml, "
          "the worked example.")
    print(f"  3. python3 tools/validate.py {rel}")
    print("\nNothing has been committed.")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--title", help="the record title. Given, nothing is asked")
    ap.add_argument("--mode", help="attack or failure. Scenarios only")
    ap.add_argument("--layer", help="the layer, in full or as its number such as L3. "
                                    "Scenarios only")
    ap.add_argument("--priority", help="NOW, NEAR-TERM or BACKLOG. Scenarios only")
    ap.add_argument("--author", help="the person who owns the record")
    ap.add_argument("--one-liner", dest="one_liner",
                    help="the plain terms paragraph. Scenarios only")
    ap.add_argument("--covers", help="the 3 digit id of the scenario a use case serves")
    ap.add_argument("--use-case", action="store_true",
                    help="write a use case record instead of a scenario")
    ap.add_argument("--force", action="store_true",
                    help="write it even though a record with a very similar slug exists")
    args = ap.parse_args()

    scripted = bool(args.title)
    if args.use_case:
        answers = ({"title": args.title, "covers": args.covers, "author": args.author}
                   if scripted else ask_use_case())
    else:
        answers = ({"title": args.title, "mode": args.mode, "layer": args.layer,
                    "priority": args.priority, "author": args.author,
                    "one_liner": args.one_liner}
                   if scripted else ask_scenario())

    force = args.force
    while True:
        try:
            if args.use_case:
                path = create_use_case(answers["title"], covers=answers.get("covers"),
                                       author=answers.get("author"), force=force)
                _report_use_case(path, answers.get("covers"))
            else:
                path = create_scenario(answers["title"], mode=answers.get("mode"),
                                       layer=answers.get("layer"),
                                       priority=answers.get("priority"),
                                       author=answers.get("author"),
                                       one_liner=answers.get("one_liner"), force=force)
                _report_scenario(path, answers.get("one_liner"))
            return 0
        except ScaffoldError as e:
            # Asked the questions, a near-duplicate is a question rather than a wall: the
            # person who just typed the title is the one who can say whether it really is
            # the same thing. Scripted, it stops and says how to override.
            if not scripted and not force and "very similar slug" in str(e):
                print("\n" + str(e))
                if _confirm("Write it anyway?"):
                    force = True
                    continue
                print("\nNothing was written.")
                return 1
            sys.exit(str(e))


if __name__ == "__main__":
    sys.exit(main())
