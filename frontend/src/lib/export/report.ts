import { PdfDoc, TrueType, type Rgb } from "./pdf";
import { workbook, type Cell, type Sheet } from "./xlsx";
import { currentMilestone } from "@/data/projects";
import { STATUS, fmtDate } from "@/components/donate/bits";
import { fmtCount, manat, type Qapik } from "@/lib/money";
import type { MilestoneLine, Portfolio, ProjectFile } from "@/lib/portfolio";

/**
 * A portfolio as files: a PDF report designed for reading and printing, and an Excel
 * workbook with every figure as a number, one sheet per kind of record. Both say when
 * they were made and, for sample data, that the figures are illustrative.
 */

export type ReportFonts = { regular: Uint8Array; medium: Uint8Array };

const INK: Rgb = [36, 36, 38];
const INK75: Rgb = [91, 91, 92];
const INK50: Rgb = [146, 146, 147];
const LINE: Rgb = [229, 229, 231];
const SOFT: Rgb = [242, 244, 248];
const DARK: Rgb = [53, 54, 59];
const LIME: Rgb = [217, 255, 92];
const LIME_DEEP: Rgb = [199, 240, 63];
const CLAY: Rgb = [224, 197, 182];
const MIST: Rgb = [201, 211, 224];
const WHITE: Rgb = [255, 255, 255];
const ON_DARK: Rgb = [196, 197, 201];

type Tone = "plain" | "lime" | "warn" | "ok" | "dark" | "stop";
const TAGS: Record<Tone, [Rgb, Rgb]> = {
  plain: [SOFT, INK75],
  lime: [LIME, INK],
  warn: [[246, 236, 222], [154, 100, 32]],
  ok: [[232, 241, 228], [74, 124, 51]],
  dark: [DARK, WHITE],
  stop: [[247, 231, 229], [164, 67, 58]],
};

const WHERE = { released: "Released", escrow: "In escrow", refunded: "Refunded" } as const;

const kindOf = (p: Portfolio) => (p.focus ? "Project report" : p.view === "org" ? "Organisation report" : "Donor portfolio");
const plural = (n: number, word: string) => `${fmtCount(n)} ${word}${n === 1 ? "" : "s"}`;
const percent = (part: number, of: number) => (of > 0 ? Math.round((part * 100) / of) : 0);
const short = (hex: string, head = 10) => `${hex.slice(0, head)}…${hex.slice(-6)}`;
const day = (iso: string) => fmtDate(iso);
const stamp = (d: Date) =>
  d.toLocaleString("en-GB", { day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" });

function projectState(f: ProjectFile): { label: string; tone: Tone } {
  const p = f.project;
  if (p.status === "completed") return { label: "Completed", tone: "ok" };
  if (p.status === "stopped") return { label: "Stopped", tone: "stop" };
  const s = STATUS[p.milestones[currentMilestone(p)].status];
  return { label: s.label, tone: (s.tone || "plain") as Tone };
}

function checksSummary(m: MilestoneLine): string {
  const pr = m.proof;
  if (!pr) return "";
  const auto = pr.checks.filter((c) => c.how === "automatic");
  const passed = auto.filter((c) => c.state === "passed").length;
  const officer = pr.checks.length - auto.length;
  const decided = pr.decision.state === "approved";
  return (
    `Checks: ${passed} of ${auto.length} automatic checks passed${passed < auto.length ? ", the rest are running" : ""}; ` +
    `the other ${officer} ${decided ? "were passed by the officer" : "are read by the officer next"}.`
  );
}

function officerSummary(m: MilestoneLine): string {
  const d = m.proof?.decision;
  if (!d) return "";
  const who = `${d.officer} (${d.firm})`;
  if (d.state === "approved") return `Approved by ${who}${d.at ? ` on ${day(d.at)}` : ""}: “${d.reason}”`;
  if (d.state === "reviewing") return `With the officer now: ${who}.`;
  return `The officer, ${who}, reviews it once the checks finish.`;
}

function voteSummary(m: MilestoneLine): string {
  const b = m.ballot;
  if (!b) return "";
  const cast = b.yes + b.no;
  return (
    `Donor vote, ${day(b.opened)} to ${day(b.closes)}: ${b.state === "open" ? "open" : "passed"} with ${fmtCount(b.yes)} yes and ` +
    `${fmtCount(b.no)} no; ${fmtCount(cast)} of ${fmtCount(b.eligible)} receipts voted (${percent(cast, b.eligible)}%).`
  );
}

function yourVote(m: MilestoneLine): string {
  if (!m.ballot || !m.canVote) return "";
  if (m.ballot.state === "open") return `You can vote in the Veritas app until ${day(m.ballot.closes)}.`;
  return m.vote ? `You voted ${m.vote}.` : "You did not vote.";
}

/* ------------------------------------------------------------------ the PDF */

const H = 841.89;
const M = 48;
const W = 595.28 - 2 * M;
const BOTTOM = H - 64;

type Font = "regular" | "medium";
type Line = { text: string; size?: number; font?: Font; color?: Rgb };
type Col = { label: string; width: number; align?: "left" | "right" };
type CellSpec = Line[] | { tag: string; tone: Tone } | null;

class Report {
  readonly doc: PdfDoc;
  private y = 0;

  constructor(
    private readonly p: Portfolio,
    fonts: ReportFonts
  ) {
    this.doc = new PdfDoc({
      regular: new TrueType(fonts.regular, "Roboto-Regular"),
      medium: new TrueType(fonts.medium, "Roboto-Medium"),
    });
  }

  private text(x: number, y: number, text: string, size: number, o: { font?: Font; color?: Rgb; align?: "left" | "right" | "center"; spacing?: number } = {}) {
    this.doc.text(x, y, text, { size, font: o.font ?? "regular", color: o.color ?? INK, align: o.align, spacing: o.spacing });
  }

  private width(text: string, size: number, font: Font = "regular") {
    return this.doc.measure(text, { size, font });
  }

  private fit(text: string, width: number, size: number, font: Font = "regular") {
    return this.doc.fit(text, width, { size, font });
  }

  private mark(x: number, y: number, size: number) {
    this.doc.rect(x, y, size, size, { fill: LIME, radius: size * 0.28 });
    this.text(x + size / 2, y + size * 0.72, "V", size * 0.62, { font: "medium", align: "center" });
  }

  private tag(x: number, y: number, label: string, tone: Tone, align: "left" | "right" = "left"): number {
    const [bg, ink] = TAGS[tone];
    const w = this.width(label, 7.5, "medium") + 11;
    const left = align === "right" ? x - w : x;
    this.doc.rect(left, y, w, 13, { fill: bg, radius: 6.5 });
    this.text(left + 5.5, y + 9.1, label, 7.5, { font: "medium", color: ink });
    return w;
  }

  private page() {
    this.doc.addPage();
    this.mark(M, 30, 14);
    this.text(M + 20, 41.5, "Veritas", 10.5, { font: "medium" });
    const who = this.p.focus ? this.p.projects[0]?.project.title ?? this.p.owner : this.p.owner;
    this.text(M + W, 41.5, this.fit(`${kindOf(this.p)} · ${who}`, 330, 8), 8, { color: INK50, align: "right" });
    this.doc.line(M, 54, M + W, 54, { color: LINE });
    this.y = 82;
  }

  private need(height: number) {
    if (this.y + height > BOTTOM) this.page();
  }

  private paragraph(text: string, size: number, color: Rgb, x = M, width = W, lead = size * 1.42) {
    for (const line of this.doc.wrap(text, width, { size })) {
      this.need(lead);
      this.text(x, this.y + size, line, size, { color });
      this.y += lead;
    }
  }

  /** A heading, kept on the same page as at least `keep` points of what follows it. */
  private section(title: string, sub?: string, keep = 96) {
    this.need(keep);
    this.text(M, this.y + 13, title, 13, { font: "medium" });
    if (sub) this.text(M, this.y + 28, this.fit(sub, W, 8.5), 8.5, { color: INK50 });
    this.y += sub ? 42 : 28;
  }

  private head(cols: Col[]) {
    let x = M;
    for (const c of cols) {
      this.text(c.align === "right" ? x + c.width : x, this.y + 9, c.label, 7.5, { color: INK50, align: c.align });
      x += c.width;
    }
    this.y += 15;
    this.doc.line(M, this.y, M + W, this.y, { color: [205, 205, 208] });
  }

  private row(cols: Col[], cells: CellSpec[], height: number, fill?: Rgb) {
    if (this.y + height > BOTTOM) {
      this.page();
      this.head(cols);
    }
    if (fill) this.doc.rect(M, this.y, W, height, { fill });
    let x = M;
    cells.forEach((cell, i) => {
      const c = cols[i];
      const pad = c.align === "right" ? 0 : 6;
      if (cell && !Array.isArray(cell)) {
        const t = cell as { tag: string; tone: Tone };
        this.tag(c.align === "right" ? x + c.width : x, this.y + height / 2 - 6.5, t.tag, t.tone, c.align);
      } else if (Array.isArray(cell)) {
        let base = this.y + (height - (cell.length - 1) * 11) / 2 + 3;
        for (const line of cell) {
          const size = line.size ?? 8.5;
          const font = line.font ?? "regular";
          const text = this.fit(line.text, c.width - pad - 2, size, font);
          this.text(c.align === "right" ? x + c.width : x, base, text, size, { font, color: line.color ?? INK, align: c.align });
          base += 11;
        }
      }
      x += c.width;
    });
    this.y += height;
    this.doc.line(M, this.y, M + W, this.y, { color: LINE });
  }

  /** Start a new page before the last row when the total would not fit under it. */
  private keepWithTotal(cols: Col[], rowHeight: number) {
    if (this.y + rowHeight + 26 > BOTTOM) {
      this.page();
      this.head(cols);
    }
  }

  private cover() {
    const p = this.p;
    const focus = p.focus ? p.projects[0] : undefined;
    this.doc.addPage();
    this.mark(M, 40, 22);
    this.text(M + 30, 56.5, "Veritas", 16, { font: "medium" });
    this.text(M + W, 50, `Generated ${stamp(p.generatedAt)}`, 8, { color: INK50, align: "right" });
    if (p.sample) this.tag(M + W, 57, "Sample data", "lime", "right");

    this.y = 100;
    this.text(M, this.y, kindOf(p).toUpperCase(), 8, { font: "medium", color: INK50, spacing: 1.1 });
    this.y += 10;
    for (const line of this.doc.wrap(focus ? focus.project.title : p.owner, W, { size: 24, font: "medium" })) {
      this.text(M, this.y + 24, line, 24, { font: "medium" });
      this.y += 30;
    }
    this.y += 4;
    const sub = focus
      ? p.view === "donor"
        ? `Prepared for ${p.owner}: your money in this project, milestone by milestone, the proof behind every payment and how the donors voted.`
        : `Prepared for ${p.owner}: what this project raised, milestone by milestone, the proof behind every payment and how the donors voted.`
      : p.view === "donor"
        ? "Where every manat you gave is now: released to the builders, waiting in escrow for proof, or back with you. Each project shows the proof behind every payment and how its donors voted."
        : "Your projects, the money each one raised, the proof behind every payment to a contractor and how donors voted on it.";
    this.paragraph(sub, 10.5, INK75, M, W * 0.86, 15);
    if (p.sample) {
      this.y += 6;
      this.paragraph("The organisations, projects and figures in this report are illustrative samples until Veritas launches.", 8.5, INK50);
    }
    this.y += 16;
    this.stats();
  }

  private stats() {
    const p = this.p;
    const t = p.totals;
    const donor = p.view === "donor";
    const cards: { label: string; value: string; foot: string; fill: Rgb; ink: Rgb; sub: Rgb }[] = donor
      ? [
          { label: "Given", value: manat(t.given), foot: `${plural(p.projects.length, "project")} · ${plural(p.donations.length, "donation")}`, fill: DARK, ink: WHITE, sub: ON_DARK },
          { label: "Released", value: manat(t.released), foot: "Paid to builders on proof", fill: SOFT, ink: INK, sub: INK50 },
          { label: "In escrow", value: manat(t.inEscrow), foot: "Waiting for proof", fill: LIME, ink: INK, sub: INK75 },
          { label: "Refunded", value: manat(t.refunded), foot: "From stopped projects", fill: SOFT, ink: INK, sub: INK50 },
        ]
      : [
          { label: "Raised", value: manat(t.raised), foot: `of a ${manat(t.goal)} goal`, fill: DARK, ink: WHITE, sub: ON_DARK },
          { label: "Released", value: manat(t.released), foot: "Paid to contractors on proof", fill: SOFT, ink: INK, sub: INK50 },
          { label: "In escrow", value: manat(t.inEscrow), foot: "Waiting for proof", fill: LIME, ink: INK, sub: INK75 },
          { label: "Donors", value: fmtCount(t.donors), foot: plural(p.projects.length, "project"), fill: SOFT, ink: INK, sub: INK50 },
        ];
    const cw = (W - 3 * 8) / 4;
    cards.forEach((c, i) => {
      const x = M + i * (cw + 8);
      this.doc.rect(x, this.y, cw, 66, { fill: c.fill, radius: 10 });
      this.text(x + 12, this.y + 19, c.label, 8.5, { color: c.sub });
      this.text(x + 12, this.y + 42, this.fit(c.value, cw - 24, 18, "medium"), 18, { font: "medium", color: c.ink });
      this.text(x + 12, this.y + 56, this.fit(c.foot, cw - 24, 7.5), 7.5, { color: c.sub });
    });
    this.y += 84;

    const parts: [Qapik, Rgb, string][] = donor
      ? [
          [t.released, DARK, "Released"],
          [t.inEscrow, LIME_DEEP, "In escrow"],
          [t.refunded, CLAY, "Refunded"],
        ]
      : [
          [t.released, DARK, "Released"],
          [t.inEscrow, LIME_DEEP, "In escrow"],
          [t.refunded, CLAY, "Returned"],
          [Math.max(0, t.goal - t.released - t.inEscrow - t.refunded), MIST, "Still to raise"],
        ];
    const total = parts.reduce((s, [v]) => s + v, 0) || 1;
    const top = this.y;
    this.doc.clip(M, top, W, 9, 4.5, () => {
      this.doc.rect(M, top, W, 9, { fill: SOFT });
      let x = M;
      for (const [v, color] of parts) {
        const w = (W * v) / total;
        this.doc.rect(x, top, w, 9, { fill: color });
        x += w;
      }
    });
    this.y += 25;
    let x = M;
    for (const [v, color, label] of parts) {
      this.doc.rect(x, this.y - 7, 7, 7, { fill: color, radius: 2 });
      this.text(x + 11, this.y, label, 8.5, { color: INK75 });
      const lw = this.width(label + " ", 8.5);
      this.text(x + 11 + lw, this.y, manat(v), 8.5, { font: "medium" });
      x += 11 + lw + this.width(manat(v), 8.5, "medium") + 18;
    }
    this.y += 30;
  }

  private projectsTable() {
    const p = this.p;
    const donor = p.view === "donor";
    if (donor) {
      this.section("Projects you support", "Your money in each project and where it is now. Every project is set out in full further on.");
      const cols: Col[] = [
        { label: "Project", width: W - 64 - 4 * 62 },
        { label: "Status", width: 64 },
        { label: "You gave", width: 62, align: "right" },
        { label: "Released", width: 62, align: "right" },
        { label: "In escrow", width: 62, align: "right" },
        { label: "Refunded", width: 62, align: "right" },
      ];
      this.head(cols);
      p.projects.forEach((f, i) => {
        const s = projectState(f);
        if (i === p.projects.length - 1) this.keepWithTotal(cols, 30);
        this.row(
          cols,
          [
            [
              { text: f.project.title, font: "medium", size: 8.5 },
              { text: `${f.project.place}${f.project.country ? `, ${f.project.country}` : ""} · ${f.org?.name ?? ""}`, size: 7.5, color: INK50 },
            ],
            { tag: s.label, tone: s.tone },
            [{ text: manat(f.mine.given) }],
            [{ text: manat(f.mine.released) }],
            [{ text: manat(f.mine.inEscrow) }],
            [{ text: manat(f.mine.refunded) }],
          ],
          30
        );
      });
      const t = p.totals;
      this.row(
        cols,
        [[{ text: "All projects", font: "medium" }], null, ...[t.given, t.released, t.inEscrow, t.refunded].map((v) => [{ text: manat(v), font: "medium" as Font }])],
        26,
        SOFT
      );
    } else {
      this.section("Your projects", "What each project raised, and where that money is now. Every project is set out in full further on.");
      const cols: Col[] = [
        { label: "Project", width: W - 60 - 4 * 60 - 46 },
        { label: "Status", width: 60 },
        { label: "Goal", width: 60, align: "right" },
        { label: "Raised", width: 60, align: "right" },
        { label: "Released", width: 60, align: "right" },
        { label: "In escrow", width: 60, align: "right" },
        { label: "Donors", width: 46, align: "right" },
      ];
      this.head(cols);
      p.projects.forEach((f, i) => {
        const s = projectState(f);
        if (i === p.projects.length - 1) this.keepWithTotal(cols, 30);
        this.row(
          cols,
          [
            [
              { text: f.project.title, font: "medium", size: 8.5 },
              { text: `${f.project.place}${f.project.country ? `, ${f.project.country}` : ""} · published ${day(f.project.publishedAt)}`, size: 7.5, color: INK50 },
            ],
            { tag: s.label, tone: s.tone },
            [{ text: manat(f.goal) }],
            [{ text: manat(f.raised) }],
            [{ text: manat(f.released) }],
            [{ text: manat(f.inEscrow) }],
            [{ text: fmtCount(f.project.donors) }],
          ],
          30
        );
      });
      const t = p.totals;
      this.row(
        cols,
        [
          [{ text: "All projects", font: "medium" }],
          null,
          ...[t.goal, t.raised, t.released, t.inEscrow].map((v) => [{ text: manat(v), font: "medium" as Font }]),
          [{ text: fmtCount(t.donors), font: "medium" }],
        ],
        26,
        SOFT
      );
    }
    this.y += 26;
  }

  private donationsTable() {
    const rows = [...this.p.donations].sort((a, b) => b.date.localeCompare(a.date));
    if (!rows.length) return;
    this.section(this.p.focus ? "Your donations to it" : "Your donations", "Each gift, its receipt on the blockchain, and where its money is now.");
    const cols: Col[] = [
      { label: "Date", width: 70 },
      { label: "Project", width: W - 70 - 74 - 62 - 92 },
      { label: "Kind", width: 74 },
      { label: "Amount", width: 62, align: "right" },
      { label: "Receipt", width: 92, align: "right" },
    ];
    this.head(cols);
    for (const d of rows) {
      this.row(
        cols,
        [
          [{ text: day(d.date) }],
          [{ text: d.projectTitle }],
          [{ text: d.kind === "pay_on_proof" ? "Pay on proof" : "Card", color: INK75 }],
          [{ text: manat(d.amount) }],
          [{ text: d.receipt ?? "", size: 7.5, color: INK50 }],
        ],
        24
      );
    }
    this.y += 26;
  }

  private projectSection(f: ProjectFile) {
    const p = f.project;
    const donor = this.p.view === "donor";
    this.need(190);
    const s = projectState(f);
    const tagWidth = this.width(s.label, 7.5, "medium") + 11;
    const meta = `${f.org?.name ?? ""} · ${p.place}${p.country ? `, ${p.country}` : ""} · built by ${p.contractor.name}`;
    if (this.p.focus) {
      // The cover already names the project: say only who runs and builds it.
      this.text(M, this.y + 9, this.fit(meta, W - 20 - tagWidth, 9), 9, { color: INK50 });
      this.tag(M + W, this.y, s.label, s.tone, "right");
      this.y += 22;
    } else {
      this.doc.rect(M, this.y, W, 52, { fill: SOFT, radius: 10 });
      this.text(M + 14, this.y + 21, this.fit(p.title, W - 44 - tagWidth, 12, "medium"), 12, { font: "medium" });
      this.text(M + 14, this.y + 38, this.fit(meta, W - 44 - tagWidth, 8), 8, { color: INK50 });
      this.tag(M + W - 14, this.y + 19.5, s.label, s.tone, "right");
      this.y += 64;
    }

    const sentence = donor
      ? `You gave ${manat(f.mine.given)} in ${plural(f.donations.length, "donation")}: ${manat(f.mine.released)} released to ${p.contractor.name} on proof, ` +
        `${manat(f.mine.inEscrow)} waiting in escrow${f.mine.refunded ? `, ${manat(f.mine.refunded)} back with you` : ""}. ` +
        `The project has raised ${manat(f.raised)} of ${manat(f.goal)} from ${plural(p.donors, "donor")}.`
      : `Raised ${manat(f.raised)} of ${manat(f.goal)} from ${plural(p.donors, "donor")}: ${manat(f.released)} released to ${p.contractor.name} on proof, ` +
        `${manat(f.inEscrow)} waiting in escrow${f.returned ? `, ${manat(f.returned)} returned to donors` : ""}.`;
    this.paragraph(sentence, 9, INK75, M, W, 13);
    this.y += 8;

    const cols: Col[] = [
      { label: "#", width: 16 },
      { label: "Milestone", width: W - 16 - 62 - 62 - 14 - 90 - 92 },
      { label: "Status", width: 62 },
      { label: donor ? "Yours" : "Raised", width: 62, align: "right" },
      { label: "", width: 14 },
      { label: "Proof", width: 90 },
      { label: "Donor vote", width: 92 },
    ];
    this.head(cols);
    for (const m of f.milestones) {
      const proof = m.proof
        ? [
            { text: `${m.proof.photos} photos, invoice`, size: 8 },
            {
              text:
                m.proof.decision.state === "approved"
                  ? "All 11 checks passed"
                  : m.proof.checks.some((c) => c.state === "running")
                    ? "Checks running"
                    : "With the officer",
              size: 7.5,
              color: INK50,
            },
          ]
        : [{ text: m.status === "stopped" ? "—" : "Not yet", size: 8, color: INK50 }];
      const b = m.ballot;
      const vote = b
        ? [
            {
              text: b.state === "open" ? `Open to ${fmtDate(b.closes, { day: "numeric", month: "short" })}` : `Passed, ${percent(b.yes, b.yes + b.no)}% yes`,
              size: 8,
              font: "medium" as Font,
              color: (b.state === "open" ? INK : TAGS.ok[1]) as Rgb,
            },
            {
              text: donor && m.canVote ? (b.state === "open" ? "Vote in the app" : m.vote ? `You voted ${m.vote}` : "You did not vote") : `${fmtCount(b.yes + b.no)} of ${fmtCount(b.eligible)} voted`,
              size: 7.5,
              color: INK50,
            },
          ]
        : [{ text: m.status === "checked" ? "After approval" : "—", size: 8, color: INK50 }];
      const money = donor
        ? [{ text: m.mine ? manat(m.mine) : "—" }, ...(m.where ? [{ text: WHERE[m.where], size: 7.5, color: INK50 }] : [])]
        : [{ text: manat(m.funded) }];
      this.row(
        cols,
        [
          [{ text: String(m.index + 1), color: INK50 }],
          [
            { text: m.title, size: 8.5, font: "medium" },
            { text: `${manat(m.budget)} budget · ${m.paidAt ? `paid ${day(m.paidAt)}` : `due ${day(m.due)}`}`, size: 7.5, color: INK50 },
          ],
          { tag: STATUS[m.status].label, tone: (STATUS[m.status].tone || "plain") as Tone },
          money,
          null,
          proof,
          vote,
        ],
        32
      );
    }
    this.y += 16;

    for (const m of f.milestones) if (m.proof || m.ballot) this.proofBlock(m);
    if (p.stop) {
      this.need(40);
      const text =
        `Stopped on ${day(p.stop.at)}: ${p.stop.reason} ${manat(p.stop.refunded)} was refunded to donors' cards and ` +
        `${manat(p.stop.redirected)} moved to other projects by the donors who chose that.`;
      const top = this.y;
      this.paragraph(text, 8.5, INK75, M + 12, W - 12, 12);
      this.doc.rect(M, top, 3, this.y - top, { fill: CLAY, radius: 1.5 });
      this.y += 8;
    }
    this.y += 22;
  }

  private proofBlock(m: MilestoneLine) {
    const pr = m.proof;
    const officer = officerSummary(m);
    const officerLines = officer ? this.doc.wrap(officer, W - 24, { size: 8 }).length : 0;
    const height = 20 + (pr ? pr.docs.length * 12 + 13 + officerLines * 11 : 0) + (m.ballot ? 12 + (yourVote(m) ? 11 : 0) : 0) + 6;
    this.need(Math.min(height, 260));
    const top = this.y;
    this.text(M + 12, this.y + 9, `Milestone ${m.index + 1}: ${m.title}`, 9, { font: "medium" });
    this.y += 22;
    if (pr) {
      for (const d of pr.docs) {
        const ident = d.cid ? `IPFS ${short(d.cid, 14)}` : d.tx ? `Polygon tx ${short(d.tx, 10)}` : `SHA-256 ${short(d.fingerprint)}`;
        const identWidth = this.width(ident, 7.5);
        this.text(M + 12, this.y, d.title, 8, { font: "medium" });
        const x = M + 12 + this.width(d.title, 8, "medium") + 6;
        this.text(x, this.y, this.fit(d.detail, M + W - identWidth - 12 - x, 8), 8, { color: INK75 });
        this.text(M + W, this.y, ident, 7.5, { color: INK50, align: "right" });
        this.y += 12;
      }
      this.text(M + 12, this.y + 1, this.fit(checksSummary(m), W - 12, 8), 8, { color: INK75 });
      this.y += 13;
      for (const line of this.doc.wrap(officer, W - 24, { size: 8 })) {
        this.text(M + 12, this.y + 1, line, 8, { color: INK75 });
        this.y += 11;
      }
    }
    if (m.ballot) {
      const b = m.ballot;
      const cast = b.yes + b.no || 1;
      const barTop = this.y - 5;
      this.doc.clip(M + 12, barTop, 54, 6, 3, () => {
        this.doc.rect(M + 12, barTop, 54, 6, { fill: CLAY });
        this.doc.rect(M + 12, barTop, (54 * b.yes) / cast, 6, { fill: DARK });
      });
      this.text(M + 74, this.y + 1, this.fit(voteSummary(m), W - 74, 8), 8, { color: INK75 });
      this.y += 12;
      const mine = yourVote(m);
      if (mine) {
        this.text(M + 74, this.y + 1, mine, 8, { font: "medium" });
        this.y += 11;
      }
    }
    this.doc.rect(M, top, 3, this.y - top, { fill: m.ballot?.state === "open" ? LIME_DEEP : m.proof?.decision.state === "approved" ? DARK : MIST, radius: 1.5 });
    this.y += 12;
  }

  private footers() {
    const n = this.doc.pageCount;
    const who = this.p.focus ? this.p.projects[0]?.project.title ?? this.p.owner : this.p.owner;
    for (let i = 0; i < n; i++) {
      this.doc.onPage(i);
      this.doc.line(M, H - 46, M + W, H - 46, { color: LINE });
      this.text(M, H - 32, this.fit(`Veritas · ${kindOf(this.p)} · ${who}`, W - 80, 7.5), 7.5, { color: INK50 });
      this.text(M + W, H - 32, `Page ${i + 1} of ${n}`, 7.5, { color: INK50, align: "right" });
      this.text(
        M,
        H - 21,
        this.p.sample
          ? "Sample data: the organisations, projects and figures are illustrative until Veritas launches."
          : "Every fingerprint here can be checked against the public record on Polygon.",
        7,
        { color: INK50 }
      );
    }
  }

  build() {
    this.cover();
    if (!this.p.focus) this.projectsTable();
    if (this.p.view === "donor") this.donationsTable();
    this.section(this.p.focus ? "Milestone by milestone" : "Project by project", "Each milestone's money, the proof behind it and the donors' vote.", 240);
    for (const f of this.p.projects) this.projectSection(f);
    this.footers();
  }
}

export async function pdfReport(p: Portfolio, fonts: ReportFonts): Promise<Blob> {
  const report = new Report(p, fonts);
  report.build();
  const who = p.focus ? p.projects[0]?.project.title ?? p.owner : p.owner;
  return report.doc.toBlob({ title: `${kindOf(p)}: ${who}`, author: "Veritas", subject: p.sample ? "Sample data" : undefined });
}

/* ------------------------------------------------------------------ the workbook */

const azn = (q: Qapik): Cell => ({ v: q / 100, t: "money" });

export function xlsxReport(p: Portfolio): Blob {
  const donor = p.view === "donor";
  const t = p.totals;
  const who = p.focus ? p.projects[0]?.project.title ?? p.owner : p.owner;
  const summary: Sheet = {
    name: "Summary",
    table: false,
    columns: [
      { header: "", width: 30 },
      { header: "", width: 64 },
    ],
    rows: [
      [{ v: `Veritas · ${kindOf(p)}`, t: "title" }],
      [{ v: who, t: "bold" }],
      ...(p.focus ? [["Prepared for", p.owner] as Cell[]] : []),
      ["Generated", stamp(p.generatedAt)],
      ...(p.sample ? [[{ v: "Sample data", t: "bold" }, "The organisations, projects and figures are illustrative until Veritas launches."] as Cell[]] : []),
      [],
      ...(donor
        ? ([
            ["Given (AZN)", azn(t.given)],
            ["Released to builders (AZN)", azn(t.released)],
            ["In escrow (AZN)", azn(t.inEscrow)],
            ["Refunded (AZN)", azn(t.refunded)],
            ["Projects", { v: p.projects.length, t: "int" }],
            ["Donations", { v: p.donations.length, t: "int" }],
          ] as Cell[][])
        : ([
            ["Goal (AZN)", azn(t.goal)],
            ["Raised (AZN)", azn(t.raised)],
            ["Released to contractors (AZN)", azn(t.released)],
            ["In escrow (AZN)", azn(t.inEscrow)],
            ["Returned to donors (AZN)", azn(t.refunded)],
            ["Donors", { v: t.donors, t: "int" }],
            ["Projects", { v: p.projects.length, t: "int" }],
          ] as Cell[][])),
      [],
      [{ v: "Money is in manat (AZN). Each sheet has filters on its header row.", t: "muted" }],
      [{ v: "Fingerprints are SHA-256; anything marked public can be checked against IPFS and the Polygon record.", t: "muted" }],
    ],
  };

  const projects: Sheet = donor
    ? {
        name: "Projects",
        columns: [
          { header: "Project", width: 44 },
          { header: "Organisation", width: 30 },
          { header: "Place", width: 16 },
          { header: "Status", width: 12 },
          { header: "You gave (AZN)", width: 15, type: "money" },
          { header: "Released (AZN)", width: 15, type: "money" },
          { header: "In escrow (AZN)", width: 15, type: "money" },
          { header: "Refunded (AZN)", width: 15, type: "money" },
          { header: "Project goal (AZN)", width: 17, type: "money" },
          { header: "Project raised (AZN)", width: 18, type: "money" },
          { header: "Donors", width: 9, type: "int" },
          { header: "Contractor", width: 26 },
        ],
        rows: p.projects.map((f) => [
          f.project.title,
          f.org?.name ?? "",
          f.project.country ? `${f.project.place}, ${f.project.country}` : f.project.place,
          projectState(f).label,
          azn(f.mine.given),
          azn(f.mine.released),
          azn(f.mine.inEscrow),
          azn(f.mine.refunded),
          azn(f.goal),
          azn(f.raised),
          f.project.donors,
          f.project.contractor.name,
        ]),
      }
    : {
        name: "Projects",
        columns: [
          { header: "Project", width: 44 },
          { header: "Place", width: 16 },
          { header: "Status", width: 12 },
          { header: "Published", width: 13, type: "date" },
          { header: "Goal (AZN)", width: 14, type: "money" },
          { header: "Raised (AZN)", width: 14, type: "money" },
          { header: "Released (AZN)", width: 15, type: "money" },
          { header: "In escrow (AZN)", width: 15, type: "money" },
          { header: "Returned (AZN)", width: 15, type: "money" },
          { header: "Donors", width: 9, type: "int" },
          { header: "Contractor", width: 26 },
        ],
        rows: p.projects.map((f) => [
          f.project.title,
          f.project.country ? `${f.project.place}, ${f.project.country}` : f.project.place,
          projectState(f).label,
          f.project.publishedAt,
          azn(f.goal),
          azn(f.raised),
          azn(f.released),
          azn(f.inEscrow),
          azn(f.returned),
          f.project.donors,
          f.project.contractor.name,
        ]),
      };

  const donations: Sheet = {
    name: "Donations",
    columns: [
      { header: "Date", width: 13, type: "date" },
      { header: "Project", width: 44 },
      { header: "Kind", width: 13 },
      { header: "Amount (AZN)", width: 14, type: "money" },
      { header: "Released (AZN)", width: 15, type: "money" },
      { header: "In escrow (AZN)", width: 15, type: "money" },
      { header: "Refunded (AZN)", width: 15, type: "money" },
      { header: "Receipt", width: 16 },
    ],
    rows: [...p.donations]
      .sort((a, b) => b.date.localeCompare(a.date))
      .map((d) => [d.date, d.projectTitle, d.kind === "pay_on_proof" ? "Pay on proof" : "Card", azn(d.amount), azn(d.released), azn(d.inEscrow), azn(d.refunded), d.receipt ?? ""]),
  };

  const each = (fn: (f: ProjectFile, m: MilestoneLine) => Cell[][]) => p.projects.flatMap((f) => f.milestones.flatMap((m) => fn(f, m)));

  const milestones: Sheet = {
    name: "Milestones",
    columns: [
      { header: "Project", width: 40 },
      { header: "#", width: 5, type: "int" },
      { header: "Milestone", width: 36 },
      { header: "Status", width: 11 },
      { header: "Due", width: 13, type: "date" },
      { header: "Paid on", width: 13, type: "date" },
      { header: "Budget (AZN)", width: 14, type: "money" },
      { header: "Raised (AZN)", width: 14, type: "money" },
      ...(donor
        ? [
            { header: "Your share (AZN)", width: 16, type: "money" as const },
            { header: "Your share is", width: 13 },
          ]
        : []),
      { header: "Photos", width: 9, type: "int" },
      { header: "Officer", width: 34 },
      { header: "Officer's decision", width: 17 },
      { header: "Decided on", width: 13, type: "date" },
    ],
    rows: each((f, m) => [
      [
        f.project.title,
        m.index + 1,
        m.title,
        STATUS[m.status].label,
        m.due,
        m.paidAt ?? "",
        azn(m.budget),
        azn(m.funded),
        ...(donor ? [azn(m.mine), m.where ? WHERE[m.where] : ""] : []),
        m.proof ? m.proof.photos : "",
        m.proof ? `${m.proof.decision.officer}, ${m.proof.decision.firm}` : "",
        m.proof ? { approved: "Approved", reviewing: "Reviewing", waiting: "After the checks" }[m.proof.decision.state] : "",
        m.proof?.decision.at ?? "",
      ],
    ]),
  };

  const proof: Sheet = {
    name: "Proof",
    columns: [
      { header: "Project", width: 40 },
      { header: "#", width: 5, type: "int" },
      { header: "Milestone", width: 32 },
      { header: "Document", width: 34 },
      { header: "About it", width: 52 },
      { header: "Public", width: 8 },
      { header: "SHA-256 fingerprint", width: 68 },
      { header: "IPFS folder (blurred copies)", width: 62 },
      { header: "Polygon transaction", width: 68 },
      { header: "Date", width: 13, type: "date" },
    ],
    rows: each((f, m) =>
      (m.proof?.docs ?? []).map((d) => [f.project.title, m.index + 1, m.title, d.title, d.detail, d.public ? "Yes" : "No", d.fingerprint, d.cid ?? "", d.tx ?? "", d.date])
    ),
  };

  const checks: Sheet = {
    name: "Checks",
    columns: [
      { header: "Project", width: 40 },
      { header: "#", width: 5, type: "int" },
      { header: "Milestone", width: 32 },
      { header: "Check", width: 7, type: "int" },
      { header: "What it checks", width: 66 },
      { header: "Done by", width: 12 },
      { header: "Result", width: 12 },
    ],
    rows: each((f, m) =>
      (m.proof?.checks ?? []).map((c) => [
        f.project.title,
        m.index + 1,
        m.title,
        c.number,
        c.title,
        c.how === "automatic" ? "Automatic" : "The officer",
        { passed: "Passed", running: "Running", waiting: "Next" }[c.state],
      ])
    ),
  };

  const votes: Sheet = {
    name: "Votes",
    columns: [
      { header: "Project", width: 40 },
      { header: "#", width: 5, type: "int" },
      { header: "Milestone", width: 32 },
      { header: "Question", width: 62 },
      { header: "Opened", width: 13, type: "date" },
      { header: "Closes", width: 13, type: "date" },
      { header: "Result", width: 10 },
      { header: "Yes", width: 8, type: "int" },
      { header: "No", width: 8, type: "int" },
      { header: "Votes cast", width: 11, type: "int" },
      { header: "Receipts that could vote", width: 22, type: "int" },
      { header: "Turnout", width: 10, type: "pct" },
      ...(donor ? [{ header: "Your vote", width: 16 }] : []),
    ],
    rows: each((f, m) => {
      const b = m.ballot;
      if (!b) return [];
      const cast = b.yes + b.no;
      return [
        [
          f.project.title,
          m.index + 1,
          m.title,
          b.question,
          b.opened,
          b.closes,
          b.state === "open" ? "Open" : "Passed",
          b.yes,
          b.no,
          cast,
          b.eligible,
          b.eligible ? cast / b.eligible : 0,
          ...(donor ? [!m.canVote ? "Not in this vote" : b.state === "open" ? "Not yet" : m.vote === "yes" ? "Yes" : m.vote === "no" ? "No" : "Did not vote"] : []),
        ],
      ];
    }),
  };

  const sheets = [summary, projects, ...(donor ? [donations] : []), milestones, proof, checks, votes];
  return workbook(sheets, { title: `${kindOf(p)}: ${who}`, author: "Veritas" });
}
