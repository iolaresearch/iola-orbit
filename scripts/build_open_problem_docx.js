const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  ImageRun, Header, Footer, AlignmentType, HeadingLevel,
  BorderStyle, WidthType, ShadingType, PageNumber, LevelFormat,
} = require("./node_modules/docx");
const fs = require("fs");
const path = require("path");

const ROOT   = path.resolve(__dirname, "..");
const OUT    = path.join(ROOT, "docs", "IOLA_Open_Problem_Statement.docx");
const LOGO   = path.join(ROOT, "client", "iola-logo-space.png");
const logoData = fs.readFileSync(LOGO);

// ---- Palette ----
const BLACK   = "0D0D0D";
const SPACE   = "0A0A1A";   // near-black navy for headers
const ACCENT  = "00C07A";   // IOLA green (from orbit visualiser LEO colour)
const MUTED   = "5A5A72";   // muted slate for body captions
const RULE    = "1E1E3A";   // dark rule line
const TBLHDR  = "0D1B2A";   // table header bg
const TBLODD  = "F4F6FA";   // table alt row

const W = 11906;  // A4 width
const CONTENT_W = W - 1800; // ~7.17 inches content (1440 margins each side - a bit tight so 900 each)

// ---- Helpers ----
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

function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    children: [new TextRun({ text, font: "Arial", bold: true, color: MUTED })],
    spacing: { before: 240, after: 80 },
  });
}

function body(text, opts = {}) {
  return new Paragraph({
    children: [new TextRun({ text, font: "Arial", size: 22, color: BLACK, ...opts })],
    spacing: { before: 60, after: 100 },
  });
}

function accent_body(text) {
  return new Paragraph({
    children: [new TextRun({ text, font: "Arial", size: 22, color: ACCENT, bold: true })],
    spacing: { before: 80, after: 80 },
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
  return new Paragraph({ children: [new TextRun("")], spacing: { before: 0, after: n * 100 } });
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
          : { fill: TBLODD,   type: ShadingType.CLEAR },
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

// ---- Cover page children ----
function coverPage() {
  return [
    space(2),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new ImageRun({
        type: "png",
        data: logoData,
        transformation: { width: 90, height: 90 },
        altText: { title: "IOLA Logo", description: "Ikirere Orbital Labs Africa", name: "logo" },
      })],
    }),
    space(1),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: "IKIRERE ORBITAL LABS AFRICA", font: "Arial", size: 20, color: MUTED, bold: true, characterSpacing: 120 })],
    }),
    space(2),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: "OPEN PROBLEM STATEMENT", font: "Arial", size: 52, bold: true, color: SPACE })],
      spacing: { before: 0, after: 160 },
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: ACCENT, space: 1 } },
      children: [new TextRun({ text: "Real-Time Many-to-Many Conjunction Screening at Orbital Scale", font: "Arial", size: 28, color: ACCENT, bold: true })],
      spacing: { before: 0, after: 320 },
    }),
    space(3),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: "Status: Open  ·  No publicly verifiable CPU solution exists", font: "Arial", size: 22, color: MUTED, italics: true })],
    }),
    space(1),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: "2026-05-22  ·  jason@ikirere.com  ·  ikirere.com", font: "Arial", size: 20, color: MUTED })],
    }),
    space(1),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: "Deep Learning Indaba 2025 Winner  ·  INSEAD AI Venture Lab Fellow  ·  Google + NVIDIA Inception", font: "Arial", size: 18, color: MUTED })],
    }),
    // Page break after cover
    new Paragraph({ children: [], pageBreakBefore: true }),
  ];
}

// ---- Document body ----
const children = [
  ...coverPage(),

  // THE PROBLEM
  h1("The Problem in One Sentence"),
  rule(),
  new Paragraph({
    children: [new TextRun({
      text: "Given a catalog of 15,000+ actively tracked orbital objects, compute all pairwise conjunction risks — including cascade-weighted orbital shell density — in under 100 milliseconds on commodity CPU hardware.",
      font: "Arial", size: 26, bold: true, color: SPACE,
    })],
    spacing: { before: 80, after: 200 },
  }),

  // BACKGROUND
  h1("Background"),
  rule(),
  h2("The Kessler Cascade"),
  body("In 1978 Donald Kessler and Burton Cour-Palais described a cascade failure scenario that has since become the defining existential risk of orbital infrastructure: a collision in LEO generates debris, each fragment strikes other satellites, more debris, more collisions — until the orbital shell becomes self-sustaining in its own destruction."),
  space(),
  body("This is not theoretical. The 2009 Iridium-Cosmos collision and the 2021 Cosmos-1408 ASAT test each generated thousands of fragments still in orbit today. The LEO shell between 400 and 600 km is approaching critical density."),
  space(),
  body("USSPACECOM currently tracks 27,000+ objects. An estimated 500,000 objects between 1 and 10 cm are untracked. A 1 cm fragment at orbital velocity carries the kinetic energy of a hand grenade.", { italics: true }),
  space(),

  h2("The Screening Bottleneck"),
  body("The pair count is not fixed — it grows with the catalog, which grows continuously:"),
  space(),
  makeTable(
    ["Catalog", "Raw Pairs", "After Altitude Filter (~5%)", "Est. Year"],
    [
      ["15,447 active (today)", "119,267,631", "~5,963,000", "2026"],
      ["27,000 all tracked", "364,486,500", "~18,224,000", "2026"],
      ["50,000 (SpaceX + Kuiper + growth)", "1,249,975,000", "~62,499,000", "~2030"],
    ],
    [3200, 2400, 2200, 1560]
  ),
  space(),
  body("SpaceX has regulatory approval for 42,000 Starlinks. Amazon Kuiper: 3,236. OneWeb: 648. The problem does not stay at 112 million pairs. It reaches 1.25 billion. A solution that works today must be designed to scale to 2030 catalog sizes."),
  space(),
  body("At 1 millisecond per surviving pair on CPU: 5.9 million pairs = 5,900 seconds = 98 minutes. The goal is 100ms total — requiring a 35,000x improvement over naive serial execution."),
  space(),

  h2("Current State of the Art"),
  makeTable(
    ["System", "Performance", "Scope"],
    [
      ["Space-Track (USSPACECOM)", "8-hour cadence", "Full catalog, batch"],
      ["LeoLabs", "<30 seconds", "Custom, proprietary architecture"],
      ["jaxsgp4 (Cambridge, March 2026)", "4ms on A100 GPU", "Propagation only — not full pipeline"],
      ["IOLA (this work)", "~2 hours on CPU", "Full pipeline, CPU, validated 6/6"],
    ],
    [2600, 2200, 4560]
  ),
  space(),
  body("jaxsgp4 (arxiv:2603.27830) solves propagation. Nobody has published the full pipeline — propagation + pairwise geometry + TCA + cascade-weighted risk scoring — at sub-second scale on CPU."),
  space(),

  // FORMAL PROBLEM STATEMENT
  new Paragraph({ children: [], pageBreakBefore: true }),
  h1("Formal Problem Statement"),
  rule(),
  h2("Input"),
  body("A catalog C of n orbital objects, each defined by:"),
  bullet("A Two-Line Element set (TLE): name, line 1, line 2"),
  bullet("Derived state vector at epoch t₀: position r = (x, y, z) km ECI, velocity v = (vx, vy, vz) km/s ECI"),
  bullet("Atmospheric drag coefficient B* (from TLE)"),
  bullet("TLE epoch timestamp"),
  space(),

  h2("Required Output"),
  body("For every pair (i, j) where i < j and |altitude_i - altitude_j| < 200 km:"),
  bullet("Time of Closest Approach (TCA) — UTC timestamp accurate to ±2 seconds"),
  bullet("Miss distance at TCA — in km, accurate to ±1 km for LEO objects"),
  bullet("Composite risk score [0,1] incorporating: miss distance, relative velocity, time urgency, collision probability, TLE age uncertainty, orbital shell density (cascade factor)"),
  bullet("Conjunction Data Message (CDM) — structured advisory, CCSDS 508.0-B-1 mappable"),
  bullet("Ranked list sorted by composite risk score, highest first"),
  space(),

  h2("Performance Requirement"),
  makeTable(
    ["Metric", "Requirement"],
    [
      ["Total screening time", "< 100 milliseconds for n = 15,000"],
      ["TCA accuracy", "±2 seconds"],
      ["Miss distance accuracy", "±1 km for LEO (altitude < 2,000 km)"],
      ["Output completeness", "All pairs with altitude separation < 200 km"],
      ["Hardware", "Commodity CPU — any modern server or laptop"],
    ],
    [4200, 5160]
  ),
  space(),
  new Paragraph({
    border: { left: { style: BorderStyle.SINGLE, size: 12, color: ACCENT, space: 180 } },
    indent: { left: 360 },
    children: [new TextRun({
      text: "Why CPU, not GPU: GPU at sub-100ms is within reach (Cambridge 4ms on A100). GPU access is expensive and unavailable to most satellite operators, university labs, and researchers in emerging markets. A CPU solution runs on any ground station, any laptop, any cloud VM. That is the democratising result.",
      font: "Arial", size: 22, color: MUTED, italics: true,
    })],
    spacing: { before: 120, after: 200 },
  }),

  // WHY IT IS HARD
  new Paragraph({ children: [], pageBreakBefore: true }),
  h1("Why This Is Hard"),
  rule(),
  h3("1. Propagation at Scale"),
  body("Each satellite must be propagated to multiple future time points using SGP4/SDP4. jaxsgp4 (Cambridge, 2026) solves this on GPU. The CPU equivalent — without hardware parallelism — requires vectorised batch evaluation using sgp4_array() and numpy, and has not been done at sub-second scale for 15k+ objects."),
  space(),

  h3("2. Pairwise Geometry at Scale"),
  body("112 million pairs. Even with the 200 km altitude pre-filter (eliminating ~95%), the surviving ~5.6 million pairs each require distance computation and a TCA search across a 72-hour window at 60-second resolution = 4,320 time steps per pair. 5.6M × 4,320 = 24 billion evaluations. This requires fully vectorised execution across all pairs simultaneously."),
  space(),

  h3("3. Novel Risk Scoring at Scale"),
  body("The composite risk score includes an orbital shell density factor — a function of how many objects share the altitude band of the conjunction. Computing this naively requires querying the full catalog for each pair. A histogram pre-computation reduces it to O(n) setup + O(1) lookup per pair. This must be integrated into the same vectorised pass."),
  space(),

  // WHAT EXISTS
  h1("What Exists vs. What Is Unsolved"),
  rule(),
  makeTable(
    ["Component", "Status", "Reference"],
    [
      ["GPU-accelerated SGP4 propagation", "Solved", "jaxsgp4, arxiv:2603.27830"],
      ["CUDA parallel orbit propagation", "Solved", "Advances in Space Research, 2023"],
      ["Browser-based GPU SGP4", "Solved", "sgp4.gl, Kayhan Space, 2025"],
      ["CPU numpy vectorised propagation", "Partial", "sgp4_array() available, not at scale"],
      ["Full pairwise conjunction pipeline on CPU", "Unsolved", "—"],
      ["Cascade-weighted risk scoring at scale", "Unsolved", "—"],
      ["Sub-100ms end-to-end CPU screening 15k+", "Unsolved", "—"],
    ],
    [3400, 1800, 4160]
  ),
  space(),

  // IOLA'S IMPLEMENTATION
  new Paragraph({ children: [], pageBreakBefore: true }),
  h1("IOLA's Current Implementation"),
  rule(),
  body("IOLA has implemented the full conjunction screening pipeline in Python, correctly and with novel risk scoring. Validated 6/6 on real satellite data (2026-05-22T17:04:46Z)."),
  space(),
  h2("Key Validation Results (Real Orbital Data)"),
  bullet("13 real conjunctions found in a 500-satellite sample in 231ms on CPU"),
  bullet("ISS ZARYA vs ISS UNITY: 0.000 km miss distance, CRITICAL — co-orbiting modules correctly identified"),
  bullet("Phase B SGP4 bisection confirmed (tca_refined=True) on real TLE lines"),
  bullet("Shell density factor = 1.0 for LEO conjunctions (Kessler cascade factor working on real data)"),
  bullet("Full production CDM generated for real ISS vs Starlink-1008 pair"),
  space(),
  h2("The Novel IP"),
  bullet("compute_tle_age_uncertainty_km() — bstar-weighted quadratic uncertainty: σ(t) = σ₀ + k × (|B*| / B*_nominal) × age²"),
  bullet("compute_orbital_shell_density() — Kessler cascade factor from live catalog population"),
  bullet("compute_composite_risk_score() — 6-component weighted risk formula including both novel terms"),
  space(),
  body("The gap: ~2 hours (current CPU) to <100ms (target) is a computational architecture problem, not an algorithm problem. The algorithm is correct. It needs vectorisation."),
  space(),

  // RESEARCH CONTRIBUTION
  h1("The Research Contribution"),
  rule(),
  body("A solution would produce:"),
  bullet("A CPU-native conjunction screening pipeline that processes the full LEO catalog in under 100ms — the first publicly verifiable implementation at this scale"),
  bullet("Real-time Kessler cascade risk scoring — not just pairwise Pc (USSPACECOM standard) but cascade-weighted orbital shell risk reflecting true consequence"),
  bullet("A foundation for autonomous orbital coordination — millisecond screening enables onboard real-time conjunction awareness, the prerequisite for IkirereMesh Phase 3"),
  bullet("A research paper targeting ICML, NeurIPS, or IEEE Aerospace Conference"),
  space(),

  // INVITATION
  new Paragraph({ children: [], pageBreakBefore: true }),
  h1("Invitation"),
  rule(),
  body("IOLA is building this system. We are looking for:"),
  space(),
  bullet("Research collaborators — CPU systems researchers, astrodynamicists, ML engineers at the intersection of orbital mechanics and real-time systems"),
  bullet("Compute contributors — access to high-core-count CPU time for benchmarking and validation"),
  bullet("Co-authors — for the research paper targeting ICML/NeurIPS/IEEE Aerospace"),
  space(),
  body("If you have solved a component of this problem, are working on it, or want to reach out:"),
  space(),
  makeTable(
    ["Contact", "Details"],
    [
      ["Name", "Jason Quist — Founder & CEO, Ikirere Orbital Labs Africa"],
      ["Email", "jason@ikirere.com"],
      ["Website", "ikirere.com"],
      ["Recognition", "Deep Learning Indaba 2025 Winner"],
      ["Fellowship", "INSEAD AI Venture Lab Fellow"],
      ["Programs", "Google + NVIDIA Inception"],
    ],
    [2800, 6560]
  ),
  space(2),

  // REFERENCES
  h1("References"),
  rule(),
  bullet("Kessler, D.J. and Cour-Palais, B.G. (1978). Collision Frequency of Artificial Satellites. Journal of Geophysical Research."),
  bullet("jaxsgp4 (2026). GPU-Accelerated SGP4 Propagation. arxiv:2603.27830. Cambridge University."),
  bullet("Hoots, F.R. and Roehrich, R.L. (1980). Models for Propagation of NORAD Element Sets. Spacetrack Report No. 3."),
  bullet("CCSDS 508.0-B-1 (2013). Conjunction Data Message. Consultative Committee for Space Data Systems."),
  bullet("Vallado, D.A. (2013). Fundamentals of Astrodynamics and Applications. 4th ed. Microcosm Press."),
  space(2),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "Software first.  Hardware second.  Space third.", font: "Arial", size: 22, color: ACCENT, bold: true, italics: true })],
    spacing: { before: 400 },
  }),
];

// ---- Build document ----
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
      {
        id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run:       { size: 24, bold: true, font: "Arial", color: MUTED },
        paragraph: { spacing: { before: 200, after: 80 }, outlineLevel: 2 },
      },
    ],
  },
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{
        level: 0, format: LevelFormat.BULLET, text: "•",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } },
      }],
    }],
  },
  sections: [{
    properties: {
      page: {
        size:   { width: W, height: 16838 },   // A4
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
      },
    },
    headers: {
      default: new Header({
        children: [
          new Paragraph({
            border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: ACCENT, space: 1 } },
            children: [
              new TextRun({ text: "IOLA  ·  Open Problem Statement  ·  2026", font: "Arial", size: 18, color: MUTED }),
              new TextRun({ text: "\t", font: "Arial" }),
              new ImageRun({ type: "png", data: logoData, transformation: { width: 28, height: 28 }, altText: { title: "IOLA", description: "IOLA", name: "hdr-logo" } }),
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
              new TextRun({ text: "\t", font: "Arial" }),
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
