const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  ImageRun, Header, Footer, AlignmentType, HeadingLevel,
  BorderStyle, WidthType, ShadingType, PageNumber, LevelFormat,
} = require("./node_modules/docx");
const fs = require("fs");
const path = require("path");

const ROOT    = path.resolve(__dirname, "..");
const OUT     = path.join(ROOT, "docs", "IOLA_Open_Problem_Statement.docx");
const LOGO    = path.join(ROOT, "client", "iola-logo-space.png");
const logoData = fs.readFileSync(LOGO);

// Palette
const BLACK  = "0D0D0D";
const SPACE  = "0A0A1A";
const ACCENT = "00C07A";
const MUTED  = "5A5A72";
const RULE   = "1E1E3A";
const TBLHDR = "0D1B2A";
const TBLODD = "F4F6FA";

const W = 11906;

// Helpers
function rule() {
  return new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: ACCENT, space: 1 } },
    spacing: { before: 0, after: 200 },
    children: [],
  });
}

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    children: [new TextRun({ text, font: "Arial", bold: true, color: SPACE })],
    spacing: { before: 400, after: 160 },
  });
}

function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    children: [new TextRun({ text, font: "Arial", bold: true, color: RULE })],
    spacing: { before: 320, after: 120 },
  });
}

function body(text, opts = {}) {
  return new Paragraph({
    children: [new TextRun({ text, font: "Arial", size: 22, color: BLACK, ...opts })],
    spacing: { before: 60, after: 100 },
  });
}

function bullet(text) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    children: [new TextRun({ text, font: "Arial", size: 22, color: BLACK })],
    spacing: { before: 40, after: 40 },
  });
}

function space(n = 1) {
  return new Paragraph({
    children: [new TextRun("")],
    spacing: { before: 0, after: n * 100 },
  });
}

function tableRow(cells, isHeader = false) {
  return new TableRow({
    children: cells.map((text, idx) => new TableCell({
      borders: {
        top:    { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" },
        bottom: { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" },
        left:   { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" },
        right:  { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" },
      },
      shading: isHeader
        ? { fill: TBLHDR, type: ShadingType.CLEAR }
        : idx % 2 === 0
          ? { fill: "FFFFFF", type: ShadingType.CLEAR }
          : { fill: TBLODD, type: ShadingType.CLEAR },
      margins: { top: 80, bottom: 80, left: 120, right: 120 },
      children: [new Paragraph({
        children: [new TextRun({
          text,
          font: "Arial",
          size: 20,
          bold: isHeader,
          color: isHeader ? "FFFFFF" : BLACK,
        })],
      })],
    })),
  });
}

function makeTable(headers, rows, colWidths) {
  const totalW = colWidths.reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: totalW, type: WidthType.DXA },
    columnWidths: colWidths,
    rows: [
      tableRow(headers, true),
      ...rows.map(r => tableRow(r, false)),
    ],
  });
}

// Cover page
function coverPage() {
  return [
    space(3),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new ImageRun({
        type: "png",
        data: logoData,
        transformation: { width: 100, height: 100 },
        altText: { title: "IOLA Logo", description: "Ikirere Orbital Labs Africa", name: "logo" },
      })],
    }),
    space(1),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({
        text: "IKIRERE ORBITAL LABS AFRICA",
        font: "Arial", size: 20, color: MUTED, bold: true, characterSpacing: 120,
      })],
    }),
    space(3),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({
        text: "OPEN PROBLEM",
        font: "Arial", size: 56, bold: true, color: SPACE,
      })],
      spacing: { before: 0, after: 160 },
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: ACCENT, space: 1 } },
      children: [new TextRun({
        text: "Real-Time Many-to-Many Conjunction Screening at Orbital Scale",
        font: "Arial", size: 28, color: ACCENT, bold: true,
      })],
      spacing: { before: 0, after: 400 },
    }),
    space(4),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({
        text: "Posed by Ikirere Orbital Labs Africa",
        font: "Arial", size: 22, color: MUTED, italics: true,
      })],
    }),
    space(1),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({
        text: "2026  ·  jason@ikirere.com  ·  ikirere.com",
        font: "Arial", size: 20, color: MUTED,
      })],
    }),
    new Paragraph({ children: [], pageBreakBefore: true }),
  ];
}

// Document body - problem only, no implementation details
const children = [
  ...coverPage(),

  // THE PROBLEM
  h1("The Problem"),
  rule(),
  new Paragraph({
    children: [new TextRun({
      text: "Given a catalog of 15,000+ actively tracked orbital objects, " +
            "compute all pairwise conjunction risks - including cascade-weighted " +
            "orbital shell density - in under 100 milliseconds on commodity CPU hardware.",
      font: "Arial", size: 26, bold: true, color: SPACE,
    })],
    spacing: { before: 80, after: 240 },
  }),

  // WHY IT MATTERS
  h1("Why It Matters"),
  rule(),

  h2("The Kessler Cascade"),
  body(
    "In 1978 Donald Kessler and Burton Cour-Palais described a cascade failure scenario " +
    "that has since become the defining existential risk of orbital infrastructure. A collision " +
    "in Low Earth Orbit generates debris. Each fragment strikes other satellites. More debris, " +
    "more collisions - until the orbital shell becomes self-sustaining in its own destruction."
  ),
  space(),
  body(
    "This is not theoretical. The 2009 Iridium-Cosmos collision and the 2021 Cosmos-1408 ASAT test " +
    "each generated thousands of fragments still in orbit today. The LEO shell between 400 and 600 km " +
    "is approaching critical density.",
    { italics: true }
  ),
  space(),

  h2("The Scale of the Problem"),
  body("The pair count is not fixed. It grows with the catalog, which grows continuously:"),
  space(),
  makeTable(
    ["Catalog", "Raw Pairs", "Est. Year"],
    [
      ["15,447 active objects (today)", "119,267,631 pairs", "2026"],
      ["27,000 all tracked objects", "364,486,500 pairs", "2026"],
      ["50,000+ (megaconstellations + growth)", "1,249,975,000 pairs", "~2030"],
    ],
    [3800, 3000, 2560]
  ),
  space(),
  body(
    "SpaceX has regulatory approval for 42,000 Starlinks alone. " +
    "A solution that works today must be designed to scale to the 2030 catalog."
  ),
  space(),

  h2("Why Current Systems Are Insufficient"),
  makeTable(
    ["System", "Performance"],
    [
      ["Space-Track (USSPACECOM)", "8-hour screening cadence"],
      ["LeoLabs", "Under 30 seconds (proprietary, undisclosed)"],
      ["GPU-accelerated propagation (Cambridge, 2026)", "4ms propagation only - not the full pipeline"],
      ["Full pipeline on CPU at <100ms", "Unsolved"],
    ],
    [5200, 4160]
  ),
  space(),
  body(
    "GPU at sub-100ms is within reach for propagation. " +
    "CPU at <100ms for the full pipeline - including pairwise geometry, " +
    "time of closest approach computation, and cascade-weighted risk scoring - " +
    "is an open problem. No publicly verifiable implementation exists."
  ),
  space(),
  new Paragraph({
    border: { left: { style: BorderStyle.SINGLE, size: 12, color: ACCENT, space: 180 } },
    indent: { left: 360 },
    children: [new TextRun({
      text: "Why CPU matters: A CPU solution runs on any ground station, any laptop, any operator " +
            "anywhere in the world. GPU requires expensive specialised hardware unavailable to most " +
            "satellite operators, university labs, and researchers in emerging markets. " +
            "CPU is the democratising result.",
      font: "Arial", size: 22, color: MUTED, italics: true,
    })],
    spacing: { before: 120, after: 200 },
  }),

  // WHAT A SOLUTION MUST DO
  new Paragraph({ children: [], pageBreakBefore: true }),
  h1("What a Solution Must Do"),
  rule(),
  body("For a catalog of n orbital objects, a valid solution must:"),
  space(),
  bullet(
    "Screen all pairs where altitude difference is below a configurable threshold " +
    "(eliminating geometrically impossible conjunctions)"
  ),
  bullet("Compute the time of closest approach (TCA) and minimum separation for surviving pairs"),
  bullet("Produce a risk score per pair that accounts for: geometric proximity, relative velocity, " +
         "time urgency, positional uncertainty, and orbital shell population density"),
  bullet("Return results ranked by risk, highest first"),
  bullet("Complete the full pipeline in under 100 milliseconds on a modern CPU"),
  bullet("Scale to 50,000+ objects without architectural changes"),
  space(),
  body("Accuracy requirements:", { bold: true }),
  bullet("TCA accurate to within 2 seconds"),
  bullet("Miss distance accurate to within 1 km for LEO objects"),
  bullet("All pairs within the altitude threshold must appear in the output - no false negatives"),
  space(),

  // THE GAP
  h1("The Gap to Close"),
  rule(),
  body(
    "The naive approach - serial pair evaluation with sequential propagation - " +
    "takes approximately 2 hours for 15,000 satellites on a CPU. " +
    "The target is 100 milliseconds. That is a 72,000x improvement."
  ),
  space(),
  body(
    "Three distinct computational problems must be solved simultaneously in a single pass, " +
    "without inter-stage data transfers that would dominate the latency budget:"
  ),
  space(),
  bullet("Propagation for N satellites across M future time steps"),
  bullet("Pairwise geometry for all surviving pairs (up to millions) simultaneously"),
  bullet("Per-pair risk scoring incorporating a whole-catalog density metric"),
  space(),

  // CONTACT
  h1("If You Are Working on This"),
  rule(),
  body(
    "We are looking for researchers, engineers, and collaborators who are working on - " +
    "or interested in - this class of problem. " +
    "If you have solved a component, have relevant work, or want to collaborate, reach out."
  ),
  space(2),
  makeTable(
    ["", ""],
    [
      ["Name", "Jason Quist, Founder and CEO"],
      ["Organisation", "Ikirere Orbital Labs Africa"],
      ["Email", "jason@ikirere.com"],
      ["Website", "ikirere.com"],
      ["Recognition", "Deep Learning Indaba 2025 Winner"],
      ["Fellowship", "INSEAD AI Venture Lab Fellow"],
      ["Programs", "Google and NVIDIA Inception"],
    ],
    [2800, 6560]
  ),
  space(3),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    children: [new TextRun({
      text: "Software first.  Hardware second.  Space third.",
      font: "Arial", size: 22, color: ACCENT, bold: true, italics: true,
    })],
    spacing: { before: 400 },
  }),
];

// Build
const doc = new Document({
  styles: {
    default: {
      document: { run: { font: "Arial", size: 22, color: BLACK } },
    },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run:       { size: 36, bold: true, font: "Arial", color: SPACE },
        paragraph: { spacing: { before: 400, after: 160 }, outlineLevel: 0 },
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run:       { size: 28, bold: true, font: "Arial", color: RULE },
        paragraph: { spacing: { before: 280, after: 100 }, outlineLevel: 1 },
      },
    ],
  },
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{
        level: 0, format: LevelFormat.BULLET, text: "·",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } },
      }],
    }],
  },
  sections: [{
    properties: {
      page: {
        size:   { width: W, height: 16838 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
      },
    },
    headers: {
      default: new Header({
        children: [
          new Paragraph({
            border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: ACCENT, space: 1 } },
            children: [
              new TextRun({ text: "IOLA  ·  Open Problem  ·  2026", font: "Arial", size: 18, color: MUTED }),
              new TextRun({ text: "\t" }),
              new ImageRun({
                type: "png", data: logoData,
                transformation: { width: 26, height: 26 },
                altText: { title: "IOLA", description: "IOLA", name: "hdr-logo" },
              }),
            ],
            tabStops: [{ type: "right", position: 8640 }],
          }),
        ],
      }),
    },
    footers: {
      default: new Footer({
        children: [
          new Paragraph({
            border: { top: { style: BorderStyle.SINGLE, size: 4, color: ACCENT, space: 1 } },
            children: [
              new TextRun({ text: "ikirere.com  ·  jason@ikirere.com", font: "Arial", size: 16, color: MUTED }),
              new TextRun({ text: "\t" }),
              new TextRun({ text: "Page ", font: "Arial", size: 16, color: MUTED }),
              new TextRun({ children: [PageNumber.CURRENT], font: "Arial", size: 16, color: MUTED }),
            ],
            tabStops: [{ type: "right", position: 8640 }],
          }),
        ],
      }),
    },
    children,
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(OUT, buf);
  console.log("Written:", OUT);
});
