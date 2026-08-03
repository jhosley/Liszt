// Build the Liszt Installation and Operating Manual (.docx).
//
//   node tools/manual/build_manual.js
//
// Writes docs/Liszt-Installation-and-Operating-Manual.docx. Uses the docx
// npm library. All paths are resolved from this file, so the cwd does not
// matter.
//

const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle, PageOrientation,
  LevelFormat, convertInchesToTwip, TableOfContents, Footer, PageNumber, ImageRun,
} = require("docx");

const ROOT = path.resolve(__dirname, "..", "..");
const DIAGRAM = (f) => path.join(ROOT, "docs", "diagrams", f);
const OUT = path.join(ROOT, "docs", "Liszt-Installation-and-Operating-Manual.docx");

const INK="1F2D38", BLUE="2C6E8F", RED="B0463B", GREEN="2F7D57", AMBER="B5852B",
      GRAY="5B6B78", RULE="D4D9DE", PALE="EFF2F5", PALEB="E7EEF3", PALER="FBEEEC",
      PALEG="EAF2ED", PALEA="FAF3E2";
const SERIF="Cambria", SANS="Calibri", MONO="Consolas";

const CONTENT_W = 9360;      // portrait, 6.5in of text width
const LAND_W    = 14400;     // landscape, 10in of text width

// -- helpers -----------------------------------------------------------------
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: true,
  spacing: { before: 0, after: 200 },
  children: [new TextRun({ text: t, font: SERIF, size: 34, bold: true, color: INK })] });

const H1N = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1,
  spacing: { before: 0, after: 200 },
  children: [new TextRun({ text: t, font: SERIF, size: 34, bold: true, color: INK })] });

const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2,
  spacing: { before: 300, after: 130 }, keepNext: true, keepLines: true,
  children: [new TextRun({ text: t, font: SERIF, size: 25, bold: true, color: BLUE })] });

const H3 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_3,
  spacing: { before: 220, after: 95 }, keepNext: true, keepLines: true,
  children: [new TextRun({ text: t, font: SANS, size: 22, bold: true, color: INK })] });

const P = (t, o = {}) => new Paragraph({ spacing: { after: o.after ?? 125, line: 282 },
  children: [new TextRun({ text: t, font: SANS, size: 21, color: o.color || INK,
                           italics: o.italics, bold: o.bold })] });

const RP = (parts, o = {}) => new Paragraph({ spacing: { after: o.after ?? 125, line: 282 },
  children: parts.map(([text, q = {}]) => new TextRun({ text, font: q.mono ? MONO : SANS,
    size: q.mono ? 19 : 21, bold: q.bold, italics: q.italics, color: q.color || INK })) });

const BULLET = (t, lvl = 0) => new Paragraph({ numbering: { reference: "bullets", level: lvl },
  spacing: { after: 75, line: 278 },
  children: [new TextRun({ text: t, font: SANS, size: 21, color: INK })] });

const RBULLET = (parts, lvl = 0) => new Paragraph({ numbering: { reference: "bullets", level: lvl },
  spacing: { after: 75, line: 278 },
  children: parts.map(([text, q = {}]) => new TextRun({ text, font: q.mono ? MONO : SANS,
    size: q.mono ? 19 : 21, bold: q.bold, italics: q.italics, color: q.color || INK })) });

const NUM = (t, inst = 0) => new Paragraph({ numbering: { reference: "numbers", level: 0, instance: inst },
  spacing: { after: 75, line: 278 },
  children: [new TextRun({ text: t, font: SANS, size: 21, color: INK })] });

const STEP = (n, t) => new Paragraph({ spacing: { before: 280, after: 110 },
  keepNext: true, keepLines: true,
  children: [
    new TextRun({ text: `STEP ${n}    `, font: SANS, size: 19, bold: true, color: BLUE }),
    new TextRun({ text: t, font: SANS, size: 23, bold: true, color: INK })] });

const CODE = (ls, o = {}) => new Table({
  width: { size: o.w || CONTENT_W, type: WidthType.DXA }, columnWidths: [o.w || CONTENT_W],
  borders: { top:{style:BorderStyle.SINGLE,size:2,color:RULE}, bottom:{style:BorderStyle.SINGLE,size:2,color:RULE},
             left:{style:BorderStyle.SINGLE,size:2,color:RULE}, right:{style:BorderStyle.SINGLE,size:2,color:RULE},
             insideHorizontal:{style:BorderStyle.NONE}, insideVertical:{style:BorderStyle.NONE} },
  rows: [new TableRow({ cantSplit: true, children: [new TableCell({
    width: { size: o.w || CONTENT_W, type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, fill: PALE },
    margins: { top: 130, bottom: 130, left: 160, right: 160 },
    children: ls.map((l, i) => new Paragraph({ spacing: { after: i === ls.length-1 ? 0 : 40, line: 250 },
      children: [new TextRun({ text: l, font: MONO, size: 18, color: INK })] })) })] })] });

const CALLOUT = (label, ls, kind) => {
  const m = { warn:[RED,PALER], ok:[GREEN,PALEG], info:[BLUE,PALEB], note:[AMBER,PALEA] };
  const [c, fill] = m[kind] || m.info;
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: [CONTENT_W],
    borders: { top:{style:BorderStyle.SINGLE,size:2,color:c}, bottom:{style:BorderStyle.SINGLE,size:2,color:c},
               left:{style:BorderStyle.SINGLE,size:2,color:c}, right:{style:BorderStyle.SINGLE,size:2,color:c},
               insideHorizontal:{style:BorderStyle.NONE}, insideVertical:{style:BorderStyle.NONE} },
    rows: [new TableRow({ cantSplit: true, children: [new TableCell({
      width: { size: CONTENT_W, type: WidthType.DXA },
      shading: { type: ShadingType.CLEAR, fill },
      margins: { top: 145, bottom: 145, left: 175, right: 175 },
      children: [
        new Paragraph({ spacing: { after: 65 },
          children: [new TextRun({ text: label, font: SANS, size: 20, bold: true, color: c })] }),
        ...ls.map((l, i) => new Paragraph({ spacing: { after: i === ls.length-1 ? 0 : 65, line: 272 },
          children: Array.isArray(l)
            ? l.map(([text, q = {}]) => new TextRun({ text, font: q.mono ? MONO : SANS,
                size: q.mono ? 18 : 20, bold: q.bold, italics: q.italics, color: q.color || INK }))
            : [new TextRun({ text: l, font: SANS, size: 20, color: INK })] }))] })] })] });
};

const GAP = (h = 130) => new Paragraph({ spacing: { after: h }, children: [] });

const TABLE = (headers, rows, widths, o = {}) => {
  const total = widths.reduce((a,b)=>a+b,0), full = o.w || CONTENT_W;
  const w = widths.map(x => Math.round(x * full / total));
  const cell = (text, i, q = {}) => new TableCell({
    width: { size: w[i], type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, fill: q.fill || "FFFFFF" },
    margins: { top: 88, bottom: 88, left: 128, right: 128 },
    children: [new Paragraph({ spacing: { after: 0, line: 258 },
      children: [new TextRun({ text, font: q.mono ? MONO : SANS, size: q.mono ? 17 : 19,
        bold: q.bold, color: q.color || INK })] })] });
  return new Table({
    width: { size: full, type: WidthType.DXA }, columnWidths: w,
    borders: { top:{style:BorderStyle.SINGLE,size:2,color:RULE}, bottom:{style:BorderStyle.SINGLE,size:2,color:RULE},
               left:{style:BorderStyle.NONE}, right:{style:BorderStyle.NONE},
               insideHorizontal:{style:BorderStyle.SINGLE,size:2,color:RULE}, insideVertical:{style:BorderStyle.NONE} },
    rows: [
      new TableRow({ tableHeader: true, children: headers.map((h,i)=>cell(h,i,{bold:true,fill:INK,color:"FFFFFF"})) }),
      ...rows.map((r,ri)=>new TableRow({ children: r.map((c,i)=>{
        const mono = typeof c === "object"; return cell(mono ? c.t : c, i, { fill: ri%2 ? PALE : "FFFFFF", mono }); }) }))] });
};

const CHECK = (t) => new Paragraph({ spacing: { after: 68, line: 272 },
  indent: { left: convertInchesToTwip(0.15) },
  children: [ new TextRun({ text: "☐   ", font: SANS, size: 22, color: BLUE }),
              new TextRun({ text: t, font: SANS, size: 20, color: INK })] });

// Image sized for a landscape page. The landscape text width is 10in, so a
// 9.5in wide image fits with room to spare. Height keeps the native aspect
// ratio (the source images are 2520 x 1500, an aspect ratio of 1.68).
const IMG = (file, wIn) => new Paragraph({ alignment: AlignmentType.CENTER,
  spacing: { before: 60, after: 100 },
  children: [new ImageRun({ type: "png", data: fs.readFileSync(file),
    transformation: { width: Math.round(wIn * 96), height: Math.round(wIn * (1500/2520) * 96) } })] });

const FOOT = () => new Footer({ children: [new Paragraph({ alignment: AlignmentType.RIGHT,
  children: [ new TextRun({ text: "Liszt  Installation and Operating Manual        ", font: SANS, size: 16, color: GRAY }),
              new TextRun({ children: [PageNumber.CURRENT], font: SANS, size: 16, color: GRAY })] })] });

// ============================================================================
// FRONT: cover, contents, purpose
// ============================================================================
const front = [];
front.push(
  GAP(2500),
  new Paragraph({ spacing: { after: 90 }, children: [new TextRun({ text: "L I S Z T",
    font: SANS, size: 22, bold: true, color: BLUE, characterSpacing: 90 })] }),
  new Paragraph({ spacing: { after: 190 }, children: [new TextRun({
    text: "Installation and Operating Manual", font: SERIF, size: 54, bold: true, color: INK })] }),
  new Paragraph({ spacing: { after: 460 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: RULE, space: 12 } },
    children: [new TextRun({ text: "Attack path and telemetry coverage analysis",
      font: SERIF, size: 28, italics: true, color: GRAY })] }),
  P("This manual covers two goals. Goal 1 stands up Liszt, the software that runs the process, on your machine. Goal 2 defines the process the team follows to review scenarios and run the sessions that produce results.", { color: GRAY }),
  P("No prior experience with the command line, source control, or YAML (YAML Ain't Markup Language) is required. Section 3 defines every term used."),
  GAP(500),
  P("Perform the steps in the order given. Do not skip a verification step.", { italics: true, color: GRAY }),
  P("The Linux install path in this manual was tested on this build. The macOS and Windows steps were worked out from the install scripts and are marked \"verify on first run\" where that applies.", { italics: true, color: GRAY }),
);
front.push(new Paragraph({ pageBreakBefore: true, spacing: { after: 220 },
  children: [new TextRun({ text: "Contents", font: SERIF, size: 34, bold: true, color: INK })] }));
front.push(new TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-2" }));

// -- 1. Purpose --------------------------------------------------------------
front.push(H1("1.  What this is and why"));
front.push(
  H2("1.1  What this program does"),
  P("The security team keeps a library of attack and failure scenarios. Each scenario is written down as two things: an attack path, which is the ordered chain of steps an attacker or a failure follows, and a telemetry and detection map, which states for every step whether the organization would see it happen."),
  P("The purpose of the program is to find and close the places where the organization would not see an attack in progress."),
  GAP(50),
  CALLOUT("The goal, stated exactly", [
    "For every scenario in the library, the organization can state, with evidence, whether each step would be detected, who owns the data source that would show it, and what work is scheduled to close the gaps.",
    [["The measure of success is the number of steps that move from Blind to Have, with evidence recorded and a ticket closed. It is not the number of scenarios written.", { bold: true }]],
  ], "info"),
  H2("1.2  Why the software exists"),
  P("Before Liszt, each scenario existed only as two slides. Slides cannot be searched, counted, compared across quarters, or combined across teams, and the reasoning behind them is lost when the author changes roles."),
  P("Liszt keeps each scenario as a structured record in a source-controlled repository. The slides, the coverage numbers, and the searchable pages are all rebuilt from the record. The record is the master copy."),
  GAP(50),
  CALLOUT("Rule 1", [
    [["The record is the master copy. The deck is rebuilt from it.", { bold: true }]],
    "Changes made directly to a slide are lost the next time the deck is rebuilt. All changes are made to the record.",
  ], "warn"),
  H2("1.3  The two goals of this manual"),
  TABLE(["Goal", "Covered in", "Owner", "Completion test"],
    [["1.  Stand up Liszt as the engine", "Sections 2 to 11", "The program lead, once",
      "The verification checklist in section 11 is complete"],
     ["2.  Run the scenario review sessions", "Sections 12 to 16", "The analysts and reviewers, every session",
      "A session produces an updated record, owned gaps, and tickets"]],
    [30, 16, 22, 32]),
  GAP(120),
  P("Goal 1 is performed once and takes about one hour. Goal 2 repeats for the life of the program."),
  H2("1.4  What is produced"),
  P("Three outputs are rebuilt from the record library. After the install, each is produced through the dispatcher, the single command described in section 6."),
  TABLE(["Output", "Rebuilt by", "Goes to"],
    [["The scenario deck", {t:"./liszt render"}, "Working group, leadership, tabletop material"],
     ["Coverage, exposure, and maturity numbers", {t:"./liszt coverage"}, "Risk reporting and the instrumentation backlog"],
     ["The searchable viewer and web pages", {t:"./liszt serve, publish"}, "Analysts during a session, and any wide audience"],
     ["Tickets for each identified gap", "The session, by hand", "Your organization's ticket system"]],
    [30, 30, 40]),
);

// -- landscape: architecture diagram -----------------------------------------
const diagram1 = [
  H1N("2.  System overview"),
  P("Figure 1 shows what Liszt contains, how a person interacts with it, what it produces, and where each output goes. Read it before performing the installation."),
  IMG(DIAGRAM("liszt-architecture.png"), 9.5),
  P("Figure 1.  Liszt system overview.", { italics: true, color: GRAY }),
];

// ============================================================================
// GOAL 1
// ============================================================================
const goal1 = [];
goal1.push(H1("Goal 1:  Stand up Liszt as the engine"));
goal1.push(P("Sections 3 to 11. Performed once, by one person, in about one hour. On completion, the software is installed inside the repository folder, the dispatcher runs, the machine passes its own health check, the framework data is in place, and the repository is under source control."));

goal1.push(H2("3.  Terms used in this manual"));
goal1.push(P("The following terms appear throughout. Read this section before performing the installation."));
goal1.push(TABLE(["Term", "Definition"],
  [["Terminal", "The window in which commands are typed. Named PowerShell or Windows Terminal on Windows, and Terminal on macOS and Linux. Commands are typed one line at a time and run by pressing Enter."],
   ["cd", "The command that changes the current folder. Example: cd liszt"],
   ["The dispatcher", "The single command you run everything through after the install. Written ./liszt on macOS and Linux, and liszt (or liszt.cmd) on Windows. Example: ./liszt validate. Section 6 lists every command."],
   ["Virtual environment (.venv)", "A private Python setup that the installer builds inside the repository folder, in a folder named .venv. All of Liszt's Python packages go there. Nothing is installed outside the repository folder."],
   ["Wheel file", "A prebuilt Python package, a file ending in .whl. The offline install builds everything from a folder of wheel files at vendor/wheels, with no network."],
   ["Repository", "A folder whose contents are tracked by version-control software, so that every change is recorded with its author and reason, and any earlier version can be restored. The software that does this is called git."],
   ["YAML", "The plain-text format in which scenario records are written. A label, a colon, a value. Spaces (never tab characters) show that an item belongs to the item above it."],
   ["Record", "One scenario, stored as one YAML file in the scenarios folder. The master copy."],
   ["Validate", "To run the check that compares every record against the schema and the quality bar. Command: ./liszt validate"],
   ["Render", "To rebuild the slide deck from the records. Command: ./liszt render"],
   ["Have, Collectable, Blind", "The three coverage labels applied to each step. Defined in section 14.3."]],
  [22, 78]));
goal1.push(GAP(90));
goal1.push(CALLOUT("Watch Out", [
  [["YAML does not accept tab characters for indentation. Only spaces are permitted.", { bold: true }]],
  "A record that will not load is almost always a tab character. Set the text editor to insert spaces in place of tabs before editing any record.",
], "warn"));

goal1.push(H2("4.  Before you begin"));
goal1.push(P("Confirm all six items before starting. Do not begin the installation until every item is available."));
[
 "A computer where you can create files in a folder. No administrator rights are needed.",
 "Python version 3.11 or later. The offline install needs exactly Python 3.11. Confirm by typing: python3 --version (on Windows: py --version). If it reports an older version, install Python 3.11 first: on macOS use brew install python@3.11 or the installer from python.org, and on Debian or Ubuntu use sudo apt install python3.11 python3.11-venv.",
 "The Liszt repository folder already on this machine, from the release archive or a git clone.",
 "For a normal install: the machine can reach the Python package index over the internet. For the air-gapped environment with no network, see Appendix B.",
 "A copy of the existing scenario deck, if you want to confirm the deck rebuilds.",
 "A place to store the repository on your organization's source-control service (for example a hosted git service), if you will put it under source control in section 10.",
].forEach(t => goal1.push(CHECK(t)));

goal1.push(H2("5.  Install the Python packages"));
goal1.push(P("The installer builds the .venv virtual environment inside the repository folder and installs Liszt's Python packages into it. It does not need administrator rights, and it changes nothing outside the repository folder. On macOS and Linux the installer is install.sh. On Windows it is install.ps1."));

goal1.push(H3("5.1  Pick the run mode"));
goal1.push(P("Every platform has the same three run modes. Pick one row, then follow section 5.2 for macOS and Linux or section 5.3 for Windows."));
goal1.push(TABLE(["Run mode", "macOS and Linux", "Windows", "When to use"],
  [["Normal", {t:"bash install.sh"}, {t:"...install.ps1"}, "The machine can reach the package index over the internet."],
   ["Offline", {t:"bash install.sh --offline"}, {t:"...install.ps1 -Offline"}, "No network. Builds from a folder of wheel files at vendor/wheels, which you create first (Appendix B)."],
   ["With deck", {t:"bash install.sh --with-deck"}, {t:"...install.ps1 -WithDeck"}, "Also installs the slide-deck packages, which only the render command needs."]],
  [15, 33, 26, 26]));
goal1.push(GAP(80));
goal1.push(RP([["The flags can be combined. To install offline and add the deck packages: ", {}],
  ["bash install.sh --offline --with-deck", { mono: true }], [" (on Windows, add both switches: ", {}],
  ["-Offline -WithDeck", { mono: true }], [").", {}]]));

goal1.push(H3("5.2  macOS and Linux"));
goal1.push(STEP(1, "Open a terminal in the repository folder"));
goal1.push(CODE(["cd liszt"]));
goal1.push(STEP(2, "Run the installer"));
goal1.push(P("Use the command from the run mode you picked in section 5.1. The normal run is shown here."));
goal1.push(CODE(["bash install.sh"]));
goal1.push(GAP(65));
goal1.push(CALLOUT("Expected result", [
  "The script prints the Python it found, then installs the core packages, then runs a short self test with three lines that each end in ok.",
  [["It finishes with ", {}], ["Done. Next, run:", { mono: true }], [" and points you at ", {}], ["./liszt doctor", { mono: true }], [" and ", {}], ["./liszt serve", { mono: true }], [". Continue to section 6.", {}]],
], "ok"));
goal1.push(GAP(65));
goal1.push(CALLOUT("Watch Out", [
  [["On some Linux systems the virtual environment cannot be created because the virtual-environment package is missing.", { bold: true }]],
  [["The script will say the venv or ensurepip piece is missing. Install the matching package (for example ", {}], ["python3.11-venv", { mono: true }], [" on Debian or Ubuntu), then run the installer again.", {}]],
], "warn"));

goal1.push(H3("5.3  Windows"));
goal1.push(P("The Windows steps below were worked out from install.ps1 and were not tested on this build. Verify on first run."));
goal1.push(STEP(1, "Open PowerShell in the repository folder"));
goal1.push(CODE(["cd liszt"]));
goal1.push(STEP(2, "Run the installer"));
goal1.push(P("Windows PowerShell blocks unsigned scripts by default, so start the installer with the execution-policy bypass shown here. This does not change any machine setting."));
goal1.push(CODE(["powershell -ExecutionPolicy Bypass -File install.ps1"]));
goal1.push(GAP(65));
goal1.push(CALLOUT("Expected result", [
  "The same output as on macOS and Linux: the Python found, the core packages installed, a three-line self test, and a Done message.",
  [["It points you at ", {}], [".\\liszt doctor", { mono: true }], [" and ", {}], [".\\liszt serve", { mono: true }], [". Continue to section 6.", {}]],
], "ok"));
goal1.push(GAP(65));
goal1.push(CALLOUT("If the install fails", [
  "Three failures account for almost every failed install. All three are checked by the doctor command in section 7.",
  [["Certificate error (a company proxy inspects secure web traffic): point ", {}], ["SSL_CERT_FILE", { mono: true }], [" and ", {}], ["PIP_CERT", { mono: true }], [" at your company root certificate bundle, then run the installer again. Or use the offline install (Appendix B).", {}]],
  [["Externally managed Python: delete the ", {}], [".venv", { mono: true }], [" folder and run the installer again so a fresh virtual environment is created.", {}]],
  "Missing virtual-environment package on Linux: install the matching package as described in section 5.2.",
], "info"));

goal1.push(H2("6.  The dispatcher"));
goal1.push(P("After the install, everything runs through one command, the dispatcher. On macOS and Linux type ./liszt. On Windows type liszt (which runs liszt.cmd). Anything you type after the command is passed straight through to the tool it runs."));
goal1.push(RP([["The dispatcher needs the install to be done first. If it reports ", {}],
  ["No virtual environment found at .venv", { mono: true }], [", run the installer from section 5, then try again.", {}]]));
goal1.push(GAP(70));
goal1.push(TABLE(["Command", "What it does"],
  [[{t:"validate"}, "Check every record against the schema and the quality bar."],
   [{t:"strict"}, "Like validate, but warnings count as failures too."],
   [{t:"publishable"}, "Check only the records marked published, strictly."],
   [{t:"coverage"}, "Produce the coverage, exposure, and maturity numbers."],
   [{t:"viewer"}, "Rebuild the static viewer page and its data file, liszt-data.json."],
   [{t:"serve"}, "Rebuild the viewer, then host it at a local address (section 8)."],
   [{t:"session"}, "Apply a saved session file back into the records."],
   [{t:"render"}, "Rebuild the slide deck. Needs the deck packages."],
   [{t:"publish"}, "Write the records out as web pages, in Markdown."],
   [{t:"pin"}, "Download and fix the framework data files. Needs network."],
   [{t:"verify-pin"}, "Re-check the framework file checksums. No network."],
   [{t:"doctor"}, "Check this machine and explain anything that is off (section 7)."],
   [{t:"update"}, "Pull the latest changes, refresh the packages, then validate."],
   [{t:"help"}, "Show the command list."]],
  [24, 76]));
goal1.push(GAP(90));
goal1.push(CALLOUT("Watch Out", [
  [["On Windows, type ", {}], ["liszt", { mono: true }], [" with no leading ", {}], ["./", { mono: true }], [", and use backslashes in file paths. Every command in this manual is shown in the macOS and Linux form.", {}]],
], "note"));

goal1.push(H2("7.  Check the machine"));
goal1.push(RP([["Run the doctor command. It prints one line per check: a pass, or a failure that says what the failure means and what to do about it. The number of failed checks is the exit code, so zero failures means the machine is healthy.", {}]]));
goal1.push(CODE(["./liszt doctor"]));
goal1.push(GAP(70));
goal1.push(TABLE(["Check", "A failure means", "What to do"],
  [["Python version", "Python is older than 3.11", "Install Python 3.11 and run the installer again. On macOS: brew install python@3.11, or the installer from python.org. The installer finds the new version on its own"],
   ["Virtual environment and core packages", "There is no .venv, or the core packages do not import", "Run the installer again. On Linux, a missing virtual-environment package is the usual cause: install the matching one, for example python3.11-venv"],
   ["Deck packages", "The deck packages are present but do not import (not having them at all is fine)", "Run the installer again with the deck flag: bash install.sh --with-deck"],
   ["Externally managed Python", "The system Python is marked externally managed and there is no .venv", "Run the installer, which builds the .venv virtual environment instead of touching the system Python"],
   ["Package index reachable", "The package index did not answer, refused the request, or gave a certificate error", "For a certificate error, point SSL_CERT_FILE and PIP_CERT at your company root certificate bundle. Otherwise use the offline install (Appendix B)"],
   ["Free disk space", "Less than about 500 MB (megabytes) of space is free", "Free some space, then run the installer"],
   ["Serve port free", "The default serve port is already in use", "Run ./liszt serve --port with a different number"],
   ["Wheel folder present (only when the index is unreachable)", "vendor/wheels has no wheel files", "Build one on a machine with package index access, or point pip at an internal package mirror (Appendix B)"],
   ["macOS download quarantine (macOS only, verify on first run)", "macOS marked the files as downloaded from the internet, which can block them", "From the repo folder, run: xattr -dr com.apple.quarantine ."],
   ["PowerShell execution policy (Windows only, verify on first run)", "Not a failure. The policy blocks plain script runs", "Start installs with: powershell -ExecutionPolicy Bypass -File install.ps1"],
   ["Windows long path support (Windows only, verify on first run)", "Not a failure. Off is fine unless a command fails with a path-length error", "Keep the folder near the drive root, or have an administrator turn long path support on"]],
  [26, 36, 38]));
goal1.push(GAP(90));
goal1.push(CALLOUT("Watch Out", [
  [["Three classic install failures are worth knowing before you hit them.", { bold: true }]],
  [["1.  The Python virtual-environment package is missing on some Linux systems, so ", {}], [".venv", { mono: true }], [" cannot be built. Install the matching package (for example ", {}], ["python3.11-venv", { mono: true }], [").", {}]],
  "2.  The system Python is marked externally managed, which blocks direct installs. The installer sidesteps this by building the .venv virtual environment.",
  "3.  Corporate certificate interception breaks the package index. Point SSL_CERT_FILE and PIP_CERT at your company root certificate bundle, or install offline.",
], "warn"));

goal1.push(H2("8.  Run a working session with serve"));
goal1.push(P("During a session, the team works in the viewer page. Do not open that page by double-clicking the HTML (HyperText Markup Language) file. Run the serve command instead."));
goal1.push(CODE(["./liszt serve"]));
goal1.push(GAP(65));
goal1.push(CALLOUT("Why serve exists", [
  "When the viewer page is opened straight from a file on disk, the web browser puts it in one storage area that every other file page on that machine shares. So a second copy of the viewer, open at the same time, can quietly overwrite a session that is still in progress.",
  "One major web browser refuses to keep any storage at all for a page opened from a file, which means a page refresh loses the session entirely.",
  [["Running ", {}], ["./liszt serve", { mono: true }], [" hosts the page at a real local address instead. That gives each person's session its own storage area, keeps every browser working, and lets a refresh survive.", {}]],
], "info"));
goal1.push(GAP(65));
goal1.push(P("The default port is 8700 plus a small number worked out from your user account, so two people on one shared machine land on different ports without thinking about it. Pass --port to choose the port yourself. The server answers on this machine only, at 127.0.0.1, so nobody else on the network can reach it."));
goal1.push(CODE(["./liszt serve --port 8765"]));
goal1.push(GAP(65));
goal1.push(CALLOUT("Watch Out", [
  [["Do not double-click the viewer HTML file to run a real session.", { bold: true }]],
  "A file opened directly from disk shares one storage area with every other file page, so two open copies can overwrite each other's in-progress work, and one browser will not keep the session across a refresh. Always use ./liszt serve for a working session.",
], "warn"));

goal1.push(H3("8.1  Shared machines"));
goal1.push(P("When several people use one machine, each person should run serve on their own port. The default already does this: the port is derived from the user account, so two accounts get two ports and their sessions stay separate. If you set the port by hand, give each person a different number."));
goal1.push(P("If you reach the machine over a remote shell rather than sitting at it, the local address is only reachable on that machine. Forward the port back to your own computer through the remote shell, then open the address there."));

goal1.push(H2("9.  Install the framework data files"));
goal1.push(P("Liszt maps every scenario to published frameworks. A framework is a catalog of attack techniques or risks, each with a permanent identifier, so coverage can be counted the same way every time and compared with other organizations. Five frameworks are used."));
goal1.push(TABLE(["Framework", "What it contains"],
  [["MITRE ATT&CK (Adversarial Tactics, Techniques, and Common Knowledge)", "The catalog of techniques used against enterprise systems. Identifiers look like T1190."],
   ["MITRE ATLAS (Adversarial Threat Landscape for Artificial-Intelligence Systems)", "The matching catalog for attacks against artificial intelligence and machine learning systems. Identifiers look like AML.T0049."],
   ["OWASP (Open Worldwide Application Security Project) Top 10 for LLM (Large Language Model) Applications", "Ten named risks for applications built on large language models. Identifiers look like LLM03."],
   ["OWASP Top 10 for Agentic Applications", "Ten named risks for autonomous agents. Identifiers look like ASI05."],
   ["DeTT&CT (Detect Tactics, Techniques and Combat Threats)", "The scoring method that rates how well a data source supports detection. It supplies the visibility and detection scales."]],
  [42, 58]));
goal1.push(GAP(80));
goal1.push(P("Install the files with the pin command. It downloads what it can over a direct link, records a checksum for each file, and lists any file that must be fetched by hand, with the address for each."));
goal1.push(CODE(["./liszt pin"]));
goal1.push(P("Place any hand-fetched files where pin asks, then confirm every file with the verify command, which makes no network requests."));
goal1.push(CODE(["./liszt verify-pin"]));
goal1.push(GAP(65));
goal1.push(CALLOUT("Expected result", [
  "Each file is listed with the first characters of its checksum. No file is listed as still needing to be fetched.",
  "If verify-pin reports a checksum mismatch, a file was replaced or altered. Fetch it again before continuing.",
  "The exact versions and addresses for all five frameworks are recorded in the framework baseline file under frameworks/. Open it in a text editor to copy them.",
], "ok"));
goal1.push(GAP(65));
goal1.push(CALLOUT("Watch Out", [
  [["Fix the framework versions and record one person as the baseline owner.", { bold: true }]],
  "The frameworks are revised on their own schedules, and a version change can move an identifier without any change to your systems. If the version is not fixed, a reported drop in coverage cannot be told apart from a renaming by the framework author. In the baseline file, replace the owner value, which reads UNASSIGNED, with the name of one person, not a team. That person performs the annual update in section 16.1.",
], "warn"));

goal1.push(H2("10.  Put the repository under source control"));
goal1.push(P("Request an empty repository from whoever administers source control, and obtain its address. Then run the two commands below, substituting that address. The repository already contains its full change history; these two commands only give it a permanent home."));
goal1.push(CODE([
  "git remote add origin https://your-git-host/your-team/liszt.git",
  "git push -u origin main",
]));
goal1.push(GAP(65));
goal1.push(CALLOUT("Expected result", [
  "The command reports that the branch main was pushed and is tracking origin/main.",
  [["Three git commands are used from this point on: ", {}], ["git add", { mono: true }], [", ", {}], ["git commit", { mono: true }], [", and ", {}], ["git push", { mono: true }], [". They appear in section 15.6.", {}]],
], "ok"));

goal1.push(H2("11.  Installation verification"));
goal1.push(P("Confirm every item. The installation is complete when all seven are checked."));
[
 "The installer finished and its three-line self test ended in ok on every line.",
 "./liszt doctor reports every check passed, apart from notes that do not apply to this machine.",
 "./liszt validate runs and reports 0 errors.",
 "./liszt serve opens the viewer at a local address, and a page refresh keeps the session.",
 "All five framework files are present and ./liszt verify-pin reports no missing files and no checksum mismatch.",
 "One person is named as the framework baseline owner.",
 "The repository is pushed to your organization's source-control service.",
].forEach(t => goal1.push(CHECK(t)));
goal1.push(GAP(120));
goal1.push(P("Goal 1 is complete. Proceed to Goal 2.", { bold: true }));

// -- landscape: session diagram ----------------------------------------------
const diagram2 = [
  H1N("12.  The scenario session"),
  P("Figure 2 shows the one-hour session: how it begins, what is done in each block, what it produces, and where each output goes. The procedure follows in sections 13 to 15."),
  IMG(DIAGRAM("liszt-session.png"), 9.5),
  P("Figure 2.  The one-hour scenario session.", { italics: true, color: GRAY }),
];

// ============================================================================
// GOAL 2
// ============================================================================
const goal2 = [];
goal2.push(H1("Goal 2:  Run the scenario review sessions"));
goal2.push(P("Sections 13 to 16. One scenario per session. Each session runs for one hour and needs at least two people."));

goal2.push(H2("13.  Roles"));
goal2.push(TABLE(["Role", "Responsibility", "Performed by"],
  [["Analyst", "Prepares the record before the session. Records what the session decides. Does not mark the record finished.", "One person, named in the record"],
   ["Reviewer", "Checks the completed record against the quality bar. Reports findings. Marks the record finished when it passes.", "A different person, named in the record"],
   ["Participants", "Contribute knowledge of the systems and the telemetry during the session. Accept ownership of gaps.", "Engineers from the affected teams"]],
  [16, 56, 28]));
goal2.push(GAP(90));
goal2.push(CALLOUT("Watch Out", [
  [["The analyst and the reviewer must be different people.", { bold: true }]],
  "The software enforces this. A record cannot be marked finished when the same name appears as both author and reviewer. This is the primary quality control in the process.",
], "warn"));

goal2.push(H2("14.  Preparation, performed by the analyst"));
goal2.push(P("About 45 minutes, completed before the session."));

goal2.push(STEP("14.1", "Create the record"));
goal2.push(P("Copy the template, using the next unused scenario number."));
goal2.push(CODE(["cp scenarios/_TEMPLATE.yaml scenarios/022-scenario-name.yaml"]));
goal2.push(P("The template holds every field, each with a comment stating what belongs in it and the error commonly made with it."));
goal2.push(P("Where an AI coding assistant is available, it can produce a first draft. The draft is reviewed and owned by the analyst in the same way as one written by hand."));

goal2.push(STEP("14.2", "Complete the record"));
goal2.push(RP([["Work through the seven gates defined in ", {}], ["docs/01-methodology.md", { mono: true }], [". The table below summarizes them. The full definition of each gate, including its completion test, is in that document.", {}]]));
goal2.push(GAP(70));
goal2.push(TABLE(["Gate", "Produces", "Completion test"],
  [["0  Scope", "The scenario named precisely, and its evidence tier selected", "It is one chain rather than a theme, and it fits within six steps"],
   ["1  Research", "The sources, read in full", "The primary document was read, not a summary of it"],
   ["2  Verify", "Counts, dates, versions, and identifiers confirmed", "Every figure was taken from the source, not from memory"],
   ["3  Attack path", "The numbered steps", "Each line fits on a slide, and any control that held is recorded"],
   ["4  Telemetry map", "One row for every step", "Every step has a row, including steps that are Blind"],
   ["5  Score", "A visibility score and a detection score for each row", "Rows with unknown status are scored low and marked, not estimated high"],
   ["6  Map and harden", "Framework identifiers, and remediations ranked by leverage", "Every remediation names the step it breaks"]],
  [17, 38, 45]));

goal2.push(STEP("14.3", "Check the record"));
goal2.push(CODE(["./liszt validate scenarios/022-scenario-name.yaml"]));
goal2.push(GAP(65));
goal2.push(CALLOUT("Expected result", [
  "A list of warnings, each naming one item the record requires. Example:",
  [["warn  telemetry[3]: 'Blind' with no owner", { mono: true }]],
  "Resolve every item that can be resolved without the session. Items that need knowledge held by other teams, such as the owner of a data source, are resolved during the session.",
], "ok"));

goal2.push(H3("14.4  The coverage labels"));
goal2.push(P("Each row of the telemetry map carries one of three labels. The label is calculated from two scores. It is never entered directly."));
goal2.push(TABLE(["Label", "Calculated when", "Meaning"],
  [["Blind", "visibility = 0", "No system produces this information"],
   ["Collectable", "visibility is 1 or more, and detection is 0 or less", "The information is recorded, but no alert is raised"],
   ["Have", "visibility is 1 or more, and detection is 1 or more", "The information is recorded and an alert is raised"]],
  [16, 40, 44]));
goal2.push(GAP(90));
goal2.push(CALLOUT("Watch Out", [
  [["A detection score of 0 means the data is kept for later investigation only. That is Collectable, not Have.", { bold: true }]],
  "This is the most frequent scoring error. It overstates coverage, and the overstatement is invisible in every report produced afterward.",
  "Where the correct score is not known, enter the lower score. An estimated high score is worse than an accurate low one, because every figure the program reports is derived from these two numbers.",
], "warn"));

goal2.push(H2("15.  The session"));
goal2.push(P("One hour. The analyst hosts the viewer with ./liszt serve and displays the record. The team analyzes it together and records what it finds."));

goal2.push(H3("15.1  Minutes 0 to 10:  Set the scene"));
goal2.push(P("The analyst states the scenario in one sentence, its evidence tier, and the proposed priority. Participants read the draft record. No discussion of individual steps takes place in this block."));

goal2.push(H3("15.2  Minutes 10 to 25:  Analyze the attack path"));
goal2.push(P("Display the numbered steps. The team addresses three questions in order."));
goal2.push(NUM("Does the chain run in this order, and are the steps stated correctly?", 1));
goal2.push(NUM("Is a step missing, or are two steps in fact one step?", 1));
goal2.push(NUM("Did any control stop or degrade the attack at any step? Where one did, record it.", 1));
goal2.push(GAP(60));
goal2.push(CALLOUT("Note", [
  "Recording a control that held is as valuable as recording a control that failed, and it is the field most frequently left out. It is the only place in the record where a control is credited with working.",
], "note"));

goal2.push(H3("15.3  Minutes 25 to 50:  Analyze the telemetry map"));
goal2.push(P("This block produces the value of the session. Work one row at a time and do not compress it. For each row, the team addresses three questions in this order."));
goal2.push(GAP(60));
goal2.push(CALLOUT("The three questions, in order", [
  [["1.  Would this specific event be visible to us?", { bold: true }], [" Not whether a log exists somewhere, but whether this event would appear in it.", {}]],
  [["2.  Does an alert fire on it, or is it only recorded?", { bold: true }], [" This decides Have against Collectable. A statement that the data is in the log platform means Collectable.", {}]],
  [["3.  Which team owns that data source, and is the gap worth closing?", { bold: true }], [" Where it is, a ticket number is required before the session ends.", {}]],
], "info"));
goal2.push(GAP(80));
goal2.push(CALLOUT("Watch Out", [
  [["Every Blind and every Collectable row leaves the session with a named owner and a ticket number.", { bold: true }]],
  "Enter both into the record while the participants are present. A gap recorded without an owner is not assigned to anyone and will stay open forever. Assigning owners and tickets is the purpose of the session. The slides are a by-product.",
], "warn"));

goal2.push(H3("15.4  Minutes 50 to 60:  Assign and confirm"));
goal2.push(P("Read back every gap, its owner, and its ticket number. Confirm each owner accepts it. Confirm the coverage scores entered during the session. The analyst saves the record."));
goal2.push(RP([["If the session was captured in the viewer, apply it back into the records with ", {}], ["./liszt session <session-file>", { mono: true }], [", then check the result with ", {}], ["./liszt validate", { mono: true }], [".", {}]]));

goal2.push(H3("15.5  Review, performed by the reviewer"));
goal2.push(RP([["About 15 minutes, after the session. Work through ", {}], ["docs/02-quality-bar.md", { mono: true }], [". The reviewer's task is to find defects, not to approve. Report each finding at one of three severities.", {}]]));
goal2.push(GAP(70));
goal2.push(TABLE(["Severity", "Definition", "Effect"],
  [["blocker", "The content is incorrect or cannot be supported", "The record cannot be published until it is resolved"],
   ["should-fix", "The content is weak and a reader would question it", "Resolve before publication unless a reason is recorded"],
   ["note", "An observation for future records", "No action required"]],
  [16, 46, 38]));
goal2.push(GAP(80));
goal2.push(CALLOUT("Watch Out", [
  [["The reviewer does not edit the record.", { bold: true }]],
  "Findings are returned to the analyst, who makes the corrections. A reviewer who makes the corrections directly removes the analyst's chance to learn and attaches the analyst's name to work they did not do.",
  "The reviewer does not review their own record, and does not waive a finding because the author is senior.",
], "warn"));

goal2.push(H3("15.6  Publication"));
goal2.push(P("When the record passes review, the reviewer opens it and changes two values."));
goal2.push(CODE([
  "status: published                 (was: draft)",
  "",
  "provenance:",
  "  reviewed_by: <reviewer name>    (was: blank)",
]));
goal2.push(GAP(70));
goal2.push(P("Then run the following commands in order."));
goal2.push(CODE([
  "./liszt publishable                              # must report 0 errors, 0 warnings",
  "",
  "git add scenarios/022-scenario-name.yaml",
  "git commit -m \"Add scenario 022: <name>\"",
  "git push",
  "",
  "./liszt render --template /path/to/template.pptx --out build/deck.pptx",
  "./liszt coverage",
]));
goal2.push(GAP(70));
goal2.push(CALLOUT("Session outputs", [
  "An updated record, committed to the repository.",
  "One named owner and one ticket number for every gap identified.",
  "Two rebuilt slides, produced on the next render.",
  "Updated coverage, exposure, and maturity figures.",
], "ok"));

goal2.push(H2("16.  Keeping the process current"));
goal2.push(RP([["The frameworks are revised, new attack methods are published, and the team's own practice changes. The full procedure is in ", {}], ["docs/06-keeping-current.md", { mono: true }], [". This section states the operating requirements.", {}]]));
goal2.push(P("Changes reach the process through three routes. Each has an assigned owner."));
goal2.push(GAP(60));
goal2.push(TABLE(["Route", "What arrives", "Recorded in", "Owner"],
  [["Frameworks", "New versions published by the framework authors", {t:"frameworks/"}, "The framework baseline owner"],
   ["Threat landscape", "New incidents, published research, new attack classes, and new systems adopted by the organization", {t:"incidents/, scenarios/"}, "The analyst pool"],
   ["Internal practice", "Findings from running the process", {t:"docs/, schema/"}, "The reviewer pool"]],
  [16, 40, 24, 20]));

goal2.push(H3("16.1  Framework updates"));
goal2.push(P("Update once per year, aligned to the spring release of MITRE ATT&CK. Do not update on each release. Frequent updates stop figures from being compared with earlier figures, which is the reason the versions are fixed."));
goal2.push(P("Create two recurring calendar entries, one in spring and one in fall, assigned to the framework baseline owner. Perform the following in order."));
goal2.push(NUM("Copy the current baseline file to a new one. Mark the previous file superseded. Do not delete it. Figures reported against a baseline are only defensible while that baseline exists.", 2));
goal2.push(NUM("Update the version number, release date, and file name for each framework.", 2));
goal2.push(NUM("Read the release notes and record every change that alters the meaning of an identifier.", 2));
goal2.push(NUM("Run ./liszt pin against the new baseline to fetch and fix the new files, then ./liszt verify-pin.", 2));
goal2.push(NUM("Update the framework identifiers in every record and re-validate.", 2));
goal2.push(NUM("Publish one reporting cycle against both the previous and the new baseline before switching.", 2));
goal2.push(NUM("Switch every record to the new baseline and record a dated snapshot of the figures.", 2));
goal2.push(GAP(60));
goal2.push(CALLOUT("Watch Out", [
  [["Step 6 is not optional.", { bold: true }]],
  "Reporting one cycle against both baselines is what shows that a change in the figures came from your controls rather than from a change made by the framework author. Leaving it out removes the ability to defend the reported figures.",
], "warn"));

goal2.push(H3("16.2  New scenarios"));
goal2.push(P("Before creating a new record, answer three questions in order."));
goal2.push(GAP(60));
goal2.push(TABLE(["Question", "If the answer is yes"],
  [["1.  Is this already covered by an existing scenario?", "It is an update to that record, not a new record"],
   ["2.  Does the chain need more than six steps?", "It is a theme rather than a scenario. Divide it"],
   ["3.  Would its telemetry map be nearly the same as an existing one?", "It duplicates that scenario. Update the existing record instead"]],
  [55, 45]));
goal2.push(GAP(80));
goal2.push(CALLOUT("Note", [
  "Question 3 is the decisive one. The telemetry map is the output of the process. A new scenario that produces the same rows as an existing one adds effort and no information.",
], "note"));

goal2.push(H3("16.3  Retiring a scenario"));
goal2.push(P("Where a technique is designed out, a system is decommissioned, or a scenario is found to duplicate another, set its status to retired and record the date, the reason, and the record that supersedes it. Do not delete the file. Retired records are left out of current figures and keep the history."));
goal2.push(P("Review the library for retirement candidates once per year, during the framework update."));

goal2.push(H3("16.4  Changing the process"));
goal2.push(P("A process change means a new or altered field, a new or altered automatic check, an altered gate, or an altered calculation. Perform the following."));
goal2.push(NUM("Record the problem the change resolves. A change without a stated problem is a preference.", 3));
goal2.push(NUM("Make the change, and update every file it affects: the schema, the automatic checks, the written procedure, and the reference record.", 3));
goal2.push(NUM("Run ./liszt validate and confirm zero errors.", 3));
goal2.push(NUM("Have a second person review the change, under the same independence requirement as record review.", 3));
goal2.push(NUM("Merge. The version-control history is the change log.", 3));
goal2.push(GAP(60));
goal2.push(CALLOUT("Watch Out", [
  [["The most frequent failure is altering the written procedure without altering the automatic check, or the reverse.", { bold: true }]],
  "The written rule and the enforced rule then differ, and the difference is not caught for months. A rule that cannot be checked automatically goes on the reviewer's checklist instead. A rule that is on neither is removed.",
], "warn"));

goal2.push(H3("16.5  Detecting drift between analysts"));
goal2.push(P("Two analysts complete the same scenario on their own, without conferring, and the results are compared. Do this when a new analyst joins, when a second organization begins contributing, when two teams' records begin to differ in character, and once per year regardless."));
goal2.push(P("Agreement on the attack path is expected to be high. Agreement on the coverage scores is where divergence appears, and those scores determine every figure the program reports."));
goal2.push(P("Where divergence is more than can be defended, the fix is a written rule, not more effort. Identify the judgment the procedure leaves open, write the rule, add the check, and repeat the exercise."));

goal2.push(H3("16.6  Annual review"));
goal2.push(P("Half a day, once per year, performed by the program lead."));
[
 "The framework baseline owner is a named person and is still employed.",
 "The new baseline is created and the previous baseline is marked superseded.",
 "Every change since the previous baseline that alters the meaning of an identifier is recorded.",
 "The framework files are fetched again and fixed. ./liszt verify-pin reports no mismatch.",
 "Framework identifiers are updated in every record and the library re-validates.",
 "One reporting cycle was published against both baselines before switching.",
 "Every published record was reviewed for retirement.",
 "The two-analyst comparison was performed.",
 "The methodology and quality bar documents were read in full and corrected where they no longer describe current practice.",
 "Every rule in the documents is either checked automatically or present on the reviewer's checklist. Rules that are neither are removed or implemented.",
 "The stated outcomes were reviewed and confirmed as still measuring the right thing.",
 "A dated snapshot of the figures was taken and archived.",
].forEach(t => goal2.push(CHECK(t)));

// ============================================================================
// FAULT DIAGNOSIS + APPENDICES
// ============================================================================
const back = [];
back.push(H1("17.  Fault diagnosis"));
back.push(TABLE(["Message or symptom", "Cause", "Action"],
  [["No virtual environment found at .venv", "The install did not finish, or you are in the wrong folder", "Run the installer from the repo folder, then try again"],
   ["ModuleNotFoundError, for example on yaml", "The Python packages are not installed", "Run the installer again"],
   ["The render command needs the deck packages", "The slide packages are not installed", "Run the installer with the deck flag: bash install.sh --with-deck"],
   ["certificate verify failed, or SSLError", "A company proxy inspects secure web traffic", "Point SSL_CERT_FILE and PIP_CERT at your company root certificate bundle, or install offline"],
   ["externally-managed-environment", "The system Python blocks direct installs", "Delete the .venv folder and run the installer again so a fresh one is created"],
   ["ensurepip, or No module named venv", "The virtual-environment package is missing on this Linux system", "Install the matching package, for example python3.11-venv, then run the installer again"],
   ["Could not listen on port ... already in use", "Another program holds the serve port", "Run ./liszt serve --port with a different number"],
   ["The session was lost after a refresh, or two people overwrote each other", "The viewer was opened straight from a file", "Use ./liszt serve instead (section 8)"],
   ["vendor/wheels has no wheel files", "The offline install has nothing to build from", "Build the folder on a machine with package index access, or use an internal package mirror (Appendix B)"],
   ["A record will not load", "A tab character is present in the file", "Replace all tab characters with spaces"],
   ["A change made to a slide is missing", "The change was made to a rebuilt file", "Make the change in the record and rebuild"],
   ["The figures fell with no change to the systems", "A framework version changed", "Check the baseline. Fixing the versions prevents this"]],
  [32, 31, 37]));
back.push(GAP(160));
back.push(H2("17.1  Reference documents"));
back.push(TABLE(["Subject", "Document", "Escalate to"],
  [["Completing a record", {t:"docs/01-methodology.md"}, "Any analyst who has completed one"],
   ["Whether a record is publishable", {t:"docs/02-quality-bar.md"}, "The reviewer pool"],
   ["Framework identifiers", {t:"docs/03-framework-mapping.md"}, "The framework baseline owner"],
   ["The reported figures", {t:"docs/04-measurement.md"}, "Whoever produces the reporting"],
   ["Installing with no network", "Appendix B of this manual", "The platform engineering team"],
   ["Keeping the process current", {t:"docs/06-keeping-current.md"}, "The program lead"]],
  [30, 40, 30]));

back.push(H1("Appendix A.  Command reference"));
back.push(H2("A.1  The installer"));
back.push(P("Run once, to stand up the software. On Windows, start each command with powershell -ExecutionPolicy Bypass -File in place of bash."));
back.push(GAP(80));
back.push(TABLE(["macOS and Linux", "Windows", "Function"],
  [[{t:"bash install.sh"}, {t:"install.ps1"}, "Normal install. Needs the package index"],
   [{t:"bash install.sh --offline"}, {t:"install.ps1 -Offline"}, "Install from a local wheel folder. No network"],
   [{t:"bash install.sh --with-deck"}, {t:"install.ps1 -WithDeck"}, "Also install the slide-deck packages"]],
  [34, 30, 36]));
back.push(GAP(120));
back.push(H2("A.2  The dispatcher"));
back.push(P("Run everything through the dispatcher after the install. On Windows, type liszt in place of ./liszt. Anything after the command is passed through to the tool it runs."));
back.push(GAP(80));
back.push(TABLE(["Command", "Function", "Network"],
  [[{t:"./liszt validate"}, "Check every record", "No"],
   [{t:"./liszt strict"}, "Check every record, warnings fail too", "No"],
   [{t:"./liszt publishable"}, "Check only published records, strictly", "No"],
   [{t:"./liszt coverage"}, "Produce the figures", "No"],
   [{t:"./liszt viewer"}, "Rebuild the viewer page and data file", "No"],
   [{t:"./liszt serve"}, "Rebuild the viewer, then host it locally", "No"],
   [{t:"./liszt session <file>"}, "Apply a saved session into the records", "No"],
   [{t:"./liszt render --template t.pptx --out build/deck.pptx"}, "Rebuild the deck. Needs the deck packages", "No"],
   [{t:"./liszt publish"}, "Write the records out as web pages", "No"],
   [{t:"./liszt pin"}, "Download and fix the framework files", "Yes"],
   [{t:"./liszt verify-pin"}, "Re-check the framework checksums", "No"],
   [{t:"./liszt doctor"}, "Check this machine", "Probes the index, unless --offline"],
   [{t:"./liszt update"}, "Pull changes, refresh packages, validate", "Yes"],
   [{t:"./liszt help"}, "Show the command list", "No"]],
  [40, 44, 16]));

back.push(H1("Appendix B.  Installing in the air-gapped environment"));
back.push(P("The air-gapped environment has no internet and no package index, so the Python packages have to reach the machine another way. There are two ways, and either one works. Every command Liszt runs after the install works with no network, so once the software and the framework files are in place, nothing on this machine reaches out."));
back.push(H2("B.1  The two ways to get the packages"));
back.push(P("The first way is an internal package mirror, such as Artifactory, Nexus, or devpi. Point pip at it once with pip config set global.index-url, then run the normal install. This is the cleanest option where the organization already runs a mirror."));
back.push(P("The second way is a wheel folder that you build once on a connected machine and carry across. A wheel file is a prebuilt Python package, so no build step and no network are needed on the far side. The repository ships no wheel files, so this folder does not exist until you create it."));
back.push(H2("B.2  Building the wheel folder"));
back.push(NUM("On a machine with package index access, download the pinned packages into vendor/wheels. Match the Python version and the platform of the air-gapped machine, not of the machine you are standing on.", 4));
back.push(GAP(50));
back.push(CODE([
  "pip download -r requirements/base.txt -r requirements/deck.txt \\",
  "    --only-binary=:all: \\",
  "    --python-version 3.11 --platform manylinux_2_28_x86_64 \\",
  "    -d vendor/wheels",
  "",
  "# platform tags: manylinux_2_28_x86_64 (Linux x86_64),",
  "#                macosx_11_0_arm64 (Apple Silicon), win_amd64 (Windows)",
]));
back.push(NUM("Copy the whole repository, including vendor/wheels, across the boundary.", 4));
back.push(H2("B.3  The procedure on the air-gapped machine"));
back.push(NUM("Open a terminal in the repository folder.", 4));
back.push(NUM("Run the offline install. Add the deck flag if the render command is needed here.", 4));
back.push(GAP(50));
back.push(CODE([
  "bash install.sh --offline",
  "bash install.sh --offline --with-deck     # if the deck is needed here",
  "",
  "# Windows:",
  "powershell -ExecutionPolicy Bypass -File install.ps1 -Offline",
]));
back.push(NUM("Pin the framework files on a connected machine, copy the frameworks/pinned folder across, then confirm them here with ./liszt verify-pin, which makes no network requests.", 4));
back.push(GAP(60));
back.push(CALLOUT("Watch Out", [
  [["The wheel folder has to match the Python version and the platform of this machine.", { bold: true }]],
  "The installer stops and explains itself when vendor/wheels is missing, and it warns when the Python here is not the version the wheels were downloaded for.",
  "Run one pip download per platform you have to support. The pinned versions in requirements/base.txt and requirements/deck.txt are the list to download.",
], "warn"));
back.push(GAP(60));
back.push(CALLOUT("What needs the network, and what does not", [
  "Needs the network: the normal install, ./liszt pin, and ./liszt update.",
  "Needs no network: the offline install, and every other command, including validate, coverage, viewer, serve, session, render, publish, and verify-pin.",
], "info"));

back.push(H1("Appendix C.  Record field reference"));
back.push(P("Every field of a scenario record, what it holds, and the error commonly made with it."));
back.push(GAP(90));
back.push(TABLE(["Field", "Content", "Common error"],
  [["title", "Short name, without the scenario number", "Stating a theme rather than one chain"],
   ["one_liner", "Plain language, readable by a non-specialist", "Jargon and unexpanded acronyms"],
   ["status", "draft, in-review, published, or retired", "The author publishing their own record"],
   ["priority", "NOW, NEXT, or LATER", "Every record marked NOW"],
   ["priority_rationale", "Two to four short lines stating why", "All lines concern the threat and none concerns the organization's own exposure"],
   ["evidence", "seen-in-the-wild, seen-in-research, or doomsday", "Selected after the research in order to justify it"],
   ["attack_path", "Up to six numbered steps", "Nine steps, which indicates two scenarios"],
   ["control_held", "Marks a step at which a control stopped the attack", "Never used. This is the most frequently omitted field"],
   ["telemetry", "One row for every step", "A step with no row, which is an unanswered question"],
   ["signal", "What is emitted, stated as a noun phrase", "Written as a sentence"],
   ["detection_opportunity", "The condition that would raise an alert", "Names a product rather than a behavior"],
   ["dettect.visibility", "0 to 4. How completely the event is visible", "Estimated high"],
   ["dettect.detection", "-1 to 5. A value of 0 means recorded only", "Treating 0 as adequate. It is Collectable, not Have"],
   ["coverage", "Calculated from the two scores. Never entered", "Entered directly and disagreeing with the calculation"],
   ["owner", "The team responsible for that data source", "Left blank on a gap"],
   ["evidence (row)", "The query, rule, or ticket supporting a Have", "A Have recorded with no supporting artifact"],
   ["backlog_ref", "The ticket that closes the gap", "Gaps recorded with no ticket"],
   ["hardening", "Remediations ranked by leverage", "General good practice that breaks no step in this chain"],
   ["framework_mapping", "Identifiers taken from the fixed framework files", "Identifiers written from memory"],
   ["mapping_notes", "Any mapping a reasonable analyst would dispute", "Left blank on an editorial mapping"],
   ["scaled_up", "A hypothetical more severe variant", "Written as though it occurred"],
   ["provenance.sources", "What was read, ranked by tier", "A summary cited in place of the original"],
   ["notes", "Working notes. Never printed", "Not used. This is where the reasoning is retained"]],
  [22, 40, 38]));
back.push(GAP(180));
back.push(H2("C.1  The five operating rules"));
back.push(RBULLET([["The record is the master copy. The deck is rebuilt from it.", { bold: true }]]));
back.push(RBULLET([["Coverage is calculated from two scores. It is never entered directly.", { bold: true }]]));
back.push(RBULLET([["Cross-framework mappings are the program's own judgment. State this in the record.", { bold: true }]]));
back.push(RBULLET([["The framework versions are fixed. Update once per year, with one cycle of dual reporting.", { bold: true }]]));
back.push(RBULLET([["An unscored row is absent, not zero. It is not included in any average.", { bold: true }]]));

// ============================================================================
const portrait = { size: { width: 12240, height: 15840 },
                   margin: { top: 1100, bottom: 1000, left: 1440, right: 1440 } };
// Landscape. The orientation is set inside the size object, not at the page
// level. The docx library swaps width and height for a landscape section
// (createPageSize emits w:w = height, w:h = width), so the portrait Letter
// dimensions below come out as pgSz w=15840 h=12240: the larger number is the
// width, which is what makes the page render landscape and the wide diagrams
// fit. Passing pre-swapped values here would double-swap back to portrait.
const landscape = { size: { width: 12240, height: 15840,
                            orientation: PageOrientation.LANDSCAPE },
                    margin: { top: 900, bottom: 700, left: 720, right: 720 } };

const doc = new Document({
  creator: "Liszt",
  title: "Liszt - Installation and Operating Manual",
  description: "Installation and operating manual for the Liszt attack path and telemetry coverage system",
  styles: { default: { document: { run: { font: SANS, size: 21, color: INK } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: SERIF, size: 34, bold: true, color: INK } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: SERIF, size: 25, bold: true, color: BLUE } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: SANS, size: 22, bold: true, color: INK } }] },
  numbering: { config: [
    { reference: "bullets", levels: [
      { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: convertInchesToTwip(0.3), hanging: convertInchesToTwip(0.18) } } } }] },
    { reference: "numbers", levels: [
      { level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: convertInchesToTwip(0.34), hanging: convertInchesToTwip(0.22) } } } }] }] },
  features: { updateFields: true },
  sections: [
    { properties: { page: portrait },  footers: { default: FOOT() }, children: front },
    { properties: { page: landscape }, footers: { default: FOOT() }, children: diagram1 },
    { properties: { page: portrait },  footers: { default: FOOT() }, children: goal1 },
    { properties: { page: landscape }, footers: { default: FOOT() }, children: diagram2 },
    { properties: { page: portrait },  footers: { default: FOOT() }, children: goal2.concat(back) },
  ],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(OUT, buf);
  console.log("written:", OUT, buf.length, "bytes");
});
