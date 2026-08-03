#!/usr/bin/env python3
"""
The source for the two Liszt diagrams: generates them as SVG and rasterizes them to PNG.

    python3 docs/diagrams/make_diagrams.py

Outputs, next to this script:
    liszt-architecture.svg / .png     what Liszt is, and where the outputs go
    liszt-session.svg / .png          the one hour scenario session

The diagrams are embedded in the operating manual, so rebuild it after a change:
node tools/manual/build_manual.js.

Colors match the scenario deck so every artifact reads as one program.
"""
from __future__ import annotations

import pathlib

INK = "#1F2D38"
BLUE = "#2C6E8F"
RED = "#B0463B"
GREEN = "#2F7D57"
AMBER = "#B5852B"
GRAY = "#5B6B78"
RULE = "#D4D9DE"
PALE = "#EFF2F5"
PALEB = "#E7EEF3"
PALER = "#FBEEEC"
PALEG = "#EAF2ED"
PALEA = "#FAF3E2"
WHITE = "#FFFFFF"

SANS = "Calibri, Segoe UI, Helvetica, Arial, sans-serif"
MONO = "Consolas, Menlo, monospace"

HERE = pathlib.Path(__file__).resolve().parent


def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def text(x, y, s, size=15, color=INK, weight="normal", anchor="start",
         font=SANS, spacing=0):
    ls = f' letter-spacing="{spacing}"' if spacing else ""
    return (f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" '
            f'fill="{color}" font-weight="{weight}" text-anchor="{anchor}"{ls}>'
            f'{esc(s)}</text>')


def lines(x, y, items, size=14, color=INK, lh=20, weight="normal", font=SANS):
    return "".join(text(x, y + i * lh, s, size, color, weight, font=font)
                   for i, s in enumerate(items))


def box(x, y, w, h, fill=WHITE, stroke=RULE, rx=6, sw=1.5):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')


def arrow(x1, y1, x2, y2, color=BLUE, w=2.2):
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
            f'stroke-width="{w}" marker-end="url(#head)"/>')


DEFS = f'''<defs>
  <marker id="head" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6"
          markerHeight="6" orient="auto-start-reverse">
    <path d="M 0 0 L 10 5 L 0 10 z" fill="{BLUE}"/>
  </marker>
  <marker id="headg" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6"
          markerHeight="6" orient="auto-start-reverse">
    <path d="M 0 0 L 10 5 L 0 10 z" fill="{GRAY}"/>
  </marker>
</defs>'''


# ═════════════════════════════════════════════════════════════════════════════
# DIAGRAM 1 - architecture
# ═════════════════════════════════════════════════════════════════════════════

def architecture() -> str:
    W, H = 1680, 1000
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}"><rect width="{W}" height="{H}" fill="{WHITE}"/>',
         DEFS]

    s.append(text(60, 58, "LISZT", 24, BLUE, "bold", spacing=4))
    s.append(text(60, 92, "What it is, how you use it, and where the output goes",
                  27, INK, "bold", font="Cambria, Georgia, serif"))
    s.append(f'<line x1="60" y1="112" x2="{W-60}" y2="112" stroke="{RULE}" stroke-width="2"/>')

    cols = [
        (60,   "1", "YOU PUT IN"),
        (470,  "2", "LISZT HOLDS"),
        (900,  "3", "LISZT PRODUCES"),
        (1300, "4", "IT GOES HERE"),
    ]
    for x, n, label in cols:
        s.append(text(x, 152, n, 13, WHITE, "bold", anchor="middle"))
        s.append(f'<circle cx="{x+10}" cy="147" r="11" fill="{BLUE}"/>')
        s.append(text(x + 10, 152, n, 13, WHITE, "bold", anchor="middle"))
        s.append(text(x + 32, 153, label, 14, BLUE, "bold", spacing=1.6))

    # ── column 1: inputs ────────────────────────────────────────────────────
    inputs = [
        (PALEB, BLUE, "An analyst", [
            "Writes the scenario record:", "the attack path, the signals,",
            "the framework mapping."]),
        (PALEB, BLUE, "A working group session", [
            "Adds the coverage scores,", "a named owner for every gap,",
            "and a ticket number."]),
        (PALE, GRAY, "Real incidents and research", [
            "One file per incident, cited", "by the scenarios it grounds."]),
        (PALE, GRAY, "Frozen framework files", [
            "MITRE ATT&CK, MITRE ATLAS,", "OWASP, DeTT&CT. Downloaded",
            "once and checksummed."]),
    ]
    y = 190
    for fill, stroke, title, body in inputs:
        h = 42 + len(body) * 19
        s.append(box(60, y, 340, h, fill, stroke))
        s.append(text(78, y + 26, title, 15, INK, "bold"))
        s.append(lines(78, y + 47, body, 13, GRAY, 19))
        s.append(arrow(408, y + h / 2, 462, y + h / 2, GRAY))
        y += h + 22

    # ── column 2: the library ───────────────────────────────────────────────
    s.append(box(470, 190, 360, 470, WHITE, INK, sw=2.5))
    s.append(f'<rect x="470" y="190" width="360" height="46" rx="6" fill="{INK}"/>')
    s.append(f'<rect x="470" y="222" width="360" height="14" fill="{INK}"/>')
    s.append(text(490, 220, "THE LIBRARY", 15, WHITE, "bold", spacing=1.5))
    s.append(text(690, 220, "one git repository", 12, "#9FB3C0"))

    store = [
        ("scenarios/", "One YAML file per scenario.", "This is the record. Edit this."),
        ("incidents/", "One file per real incident,", "cited by the scenarios."),
        ("coverage/<org>/", "Each organization's own view.", "Optional, and stays theirs."),
        ("frameworks/", "The frozen framework files", "plus their checksums."),
    ]
    y = 256
    for name, l1, l2 in store:
        s.append(box(492, y, 316, 74, PALE, RULE, rx=5, sw=1))
        s.append(text(510, y + 24, name, 14, BLUE, "bold", font=MONO))
        s.append(lines(510, y + 44, [l1, l2], 12.5, GRAY, 17))
        y += 84

    # the gate
    s.append(f'<line x1="650" y1="660" x2="650" y2="686" stroke="{RED}" stroke-width="2"/>')
    s.append(box(470, 686, 360, 118, PALER, RED, sw=2))
    s.append(text(492, 716, "THE GATE", 14, RED, "bold", spacing=1.4))
    s.append(lines(492, 740, [
        "schema/ says what a record may contain.",
        "tools/validate.py checks every record against it",
        "and against the quality bar. Nothing is published",
        "until it passes with zero errors and zero warnings.",
    ], 12.5, INK, 17))

    # ── column 3: tools ─────────────────────────────────────────────────────
    tools = [
        (GREEN, PALEG, "tools/render_slides.py", ["Rebuilds the PowerPoint deck",
                                                  "from the records, using your",
                                                  "template for the styling."]),
        (BLUE, PALEB, "tools/coverage.py", ["Computes coverage, exposure",
                                            "and maturity. Never guesses:",
                                            "unscored is absent, not zero."]),
        (AMBER, PALEA, "tools/publish_library.py", ["Writes one readable page per",
                                                    "scenario for search and",
                                                    "wide-audience browsing."]),
    ]
    y = 200
    for stroke, fill, name, body in tools:
        h = 44 + len(body) * 19
        s.append(arrow(838, y + h / 2, 892, y + h / 2, GRAY))
        s.append(box(900, y, 350, h, fill, stroke))
        s.append(text(920, y + 27, name, 14, INK, "bold", font=MONO))
        s.append(lines(920, y + 48, body, 12.5, GRAY, 19))
        s.append(arrow(1258, y + h / 2, 1294, y + h / 2, GRAY))
        y += h + 34

    # ── column 4: destinations ──────────────────────────────────────────────
    dests = [
        (GREEN, "The deck", ["Working group, leadership,",
                             "tabletop material."]),
        (BLUE, "The numbers", ["Risk reporting, the",
                               "instrumentation backlog,",
                               "year over year trend."]),
        (AMBER, "Search pages", ["SharePoint, Copilot, anyone",
                                 "who asks whether we cover X."]),
    ]
    y = 200
    for color, title, body in dests:
        h = 44 + len(body) * 19
        s.append(box(1300, y, 320, h, WHITE, color, sw=2))
        s.append(text(1320, y + 27, title, 15, color, "bold"))
        s.append(lines(1320, y + 48, body, 12.5, GRAY, 19))
        y += h + 34

    # tickets: the output that actually closes a gap
    s.append(box(1300, 572, 320, 100, WHITE, RED, sw=2))
    s.append(text(1320, 601, "Tickets", 15, RED, "bold"))
    s.append(lines(1320, 623, [
        "Every gap leaves the session", "with an owner and a ticket.",
        "This is the point of the work."], 12.5, GRAY, 19))
    s.append(arrow(842, 712, 1294, 646, GRAY))
    s.append(text(866, 748, "owners and ticket numbers are typed", 12, GRAY))
    s.append(text(866, 766, "straight into the record", 12, GRAY))

    # ── footer band ─────────────────────────────────────────────────────────
    s.append(box(60, 840, 1560, 108, PALE, RULE, rx=8))
    s.append(text(84, 872, "THE ONE RULE", 14, INK, "bold", spacing=1.5))
    s.append(text(84, 902, "The record is the truth. The deck, the numbers and the search pages "
                           "are printed from it and can be deleted and rebuilt at any time.",
                  17, INK))
    s.append(text(84, 928, "Editing a slide does not change anything. The next rebuild "
                           "overwrites it.", 15, RED))

    s.append("</svg>")
    return "".join(s)


# ═════════════════════════════════════════════════════════════════════════════
# DIAGRAM 2 - the one hour session
# ═════════════════════════════════════════════════════════════════════════════

def session() -> str:
    W, H = 1680, 1000
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}"><rect width="{W}" height="{H}" fill="{WHITE}"/>',
         DEFS]

    s.append(text(60, 58, "LISZT", 24, BLUE, "bold", spacing=4))
    s.append(text(60, 92, "The one hour scenario session", 27, INK, "bold",
                  font="Cambria, Georgia, serif"))
    s.append(f'<line x1="60" y1="112" x2="{W-60}" y2="112" stroke="{RULE}" stroke-width="2"/>')
    s.append(text(60, 140, "Two roles. The analyst writes the record. The reviewer, a different "
                           "person, decides whether it is finished.", 15, GRAY))

    # ── before ──────────────────────────────────────────────────────────────
    s.append(box(60, 176, 300, 300, PALE, GRAY))
    s.append(text(80, 208, "BEFORE", 14, GRAY, "bold", spacing=1.6))
    s.append(text(80, 234, "Analyst, about 45 min", 15, INK, "bold"))
    s.append(lines(80, 262, [
        "Copy the record template.",
        "Work gates 0 through 6 of the",
        "methodology: scope, research,",
        "verify, attack path, telemetry",
        "map, first-pass scores, mapping.",
        "",
        "Run the validator. Fix what you",
        "can on your own. Bring the rest",
        "into the room.",
    ], 13, INK, 19))
    s.append(box(80, 428, 260, 28, WHITE, RULE, rx=4, sw=1))
    s.append(text(92, 447, "python3 tools/validate.py ..", 12, BLUE, font=MONO))

    s.append(arrow(368, 326, 418, 326, GRAY))

    # ── the hour ────────────────────────────────────────────────────────────
    s.append(box(426, 176, 800, 560, WHITE, INK, sw=2.5))
    s.append(f'<rect x="426" y="176" width="800" height="46" rx="6" fill="{INK}"/>')
    s.append(f'<rect x="426" y="208" width="800" height="14" fill="{INK}"/>')
    s.append(text(448, 206, "THE SESSION", 15, WHITE, "bold", spacing=1.5))
    s.append(text(1140, 206, "60 minutes", 14, "#9FB3C0", "bold"))

    blocks = [
        (BLUE, PALEB, "0:00", "0:10", "Set the scene",
         ["The analyst states the scenario in one sentence, the evidence tier,",
          "and the proposed priority. No debate yet. Everyone reads the draft."]),
        (BLUE, PALEB, "0:10", "0:25", "Analyze the attack path as a team",
         ["Is this how the chain actually runs? Is a step missing, or are two",
          "steps really one? Did any control hold? Record what held."]),
        (RED, PALER, "0:25", "0:50", "Work the telemetry map, one row at a time",
         ["For every row, in this order:",
          "   1.  Would we actually see this?",
          "   2.  Does anything alert on it, or is it only logged?",
          "   3.  Who owns that source, and is the gap worth fixing?"]),
        (GREEN, PALEG, "0:50", "1:00", "Assign and confirm",
         ["Every Blind and Collectable row gets an owner and a ticket number,",
          "typed into the record while everyone is still in the room."]),
    ]
    y = 240
    for color, fill, t0, t1, title, body in blocks:
        h = 40 + len(body) * 18
        s.append(box(448, y, 756, h, fill, color, rx=5))
        s.append(text(468, y + 25, f"{t0} - {t1}", 12.5, color, "bold", font=MONO))
        s.append(text(556, y + 25, title, 15, INK, "bold"))
        s.append(lines(556, y + 46, body, 12.5, GRAY, 18))
        y += h + 16

    s.append(text(448, 716, "The team analyzes each step together and records what it "
                            "finds. Disagreement is a finding, not a fight: write it into "
                            "the record.", 13.5, GRAY))

    s.append(arrow(1234, 456, 1284, 456, GRAY))

    # ── after ───────────────────────────────────────────────────────────────
    s.append(box(1292, 176, 328, 280, PALE, GRAY))
    s.append(text(1312, 208, "AFTER", 14, GRAY, "bold", spacing=1.6))
    s.append(text(1312, 234, "Reviewer, about 15 min", 15, INK, "bold"))
    s.append(lines(1312, 262, [
        "Check the record against the",
        "quality bar. Report findings as",
        "blocker, should-fix or note.",
        "",
        "Do not edit the record. Hand the",
        "findings back to the analyst.",
        "",
        "When it is clean, set the record",
        "to published and sign it.",
    ], 13, INK, 19))

    # ── outputs row ─────────────────────────────────────────────────────────
    s.append(text(60, 800, "WHAT THE SESSION PRODUCES, AND WHERE IT GOES", 14, BLUE,
                  "bold", spacing=1.6))
    outs = [
        (60, GREEN, "An updated record", ["Committed to the repository.",
                                          "This is the deliverable."]),
        (460, RED, "Owned gaps with tickets", ["Into your ticket system.",
                                               "This is what actually closes."]),
        (860, BLUE, "Two rebuilt slides", ["Into the deck, on the next",
                                           "render. Not hand edited."]),
        (1260, AMBER, "Moved numbers", ["Into coverage, exposure and",
                                        "maturity reporting."]),
    ]
    for x, color, title, body in outs:
        s.append(box(x, 820, 360, 96, WHITE, color, sw=2))
        s.append(text(x + 20, 848, title, 15, color, "bold"))
        s.append(lines(x + 20, 870, body, 12.5, GRAY, 18))

    s.append(text(60, 962, "The measure of this work is not how many scenarios exist. "
                           "It is how many rows move from Blind to Have, with evidence "
                           "behind them and a ticket that closed.", 15, INK, "bold"))

    s.append("</svg>")
    return "".join(s)


def main() -> int:
    import cairosvg
    for name, svg in (("liszt-architecture", architecture()),
                      ("liszt-session", session())):
        (HERE / f"{name}.svg").write_text(svg, encoding="utf-8")
        cairosvg.svg2png(bytestring=svg.encode("utf-8"),
                         write_to=str(HERE / f"{name}.png"),
                         output_width=2520)
        print(f"  {name}.svg  {name}.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
