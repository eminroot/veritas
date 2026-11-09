import { manat, type Qapik } from "@/lib/money";
import { organisationOf, raisedOf, type Milestone, type Project } from "./projects";

/**
 * SAMPLE DATA: the proof behind each sample milestone and the donors' votes on it, made up
 * from the sample projects the same way every time, so the portfolio pages and their
 * exports have something true-to-life to show before the API serves them (backend:
 * GET /v1/projects/{id}/evidence and GET /v1/projects/{id}/ballots).
 *
 * The shapes follow the backend's. An evidence bundle is the site photos with the capture
 * manifest signed on the field team's phone, the contractor's invoice and its e-kassa
 * receipt. Its fingerprint (SHA-256) is recorded on-chain, and 11 checks run on it: five
 * automatic today, six read by the officer until the AI and document checks arrive
 * (Phase 7). Photos are published only as copies with faces and number plates blurred;
 * the invoice and the receipt stay private, and only their fingerprints are public.
 * A vote opens when the officer approves a milestone, for 72 hours, one receipt one vote.
 */

export type CheckHow = "automatic" | "officer";
export type CheckState = "passed" | "running" | "waiting";
export type Check = { number: number; title: string; how: CheckHow; state: CheckState };

/** The backend's 11 checks (evidence/checks/base.py), in plain words. */
export const CHECKS: { number: number; title: string; how: CheckHow }[] = [
  { number: 1, title: "Every file matches its fingerprint, and the phone's signature is valid", how: "automatic" },
  { number: 2, title: "Taken inside the site's boundary, from a real location", how: "automatic" },
  { number: 3, title: "Taken while the day's challenge code was valid, in the milestone's window", how: "automatic" },
  { number: 4, title: "The challenge code can be read in a photo", how: "officer" },
  { number: 5, title: "No photo was used before, here or on any other project", how: "automatic" },
  { number: 6, title: "Content credentials, and no sign of an AI-made image", how: "officer" },
  { number: 7, title: "The photos show the promised work", how: "officer" },
  { number: 8, title: "The invoice's totals, dates and VÖEN", how: "officer" },
  { number: 9, title: "The e-kassa receipt is real, with the same seller, date and amount", how: "officer" },
  { number: 10, title: "The contractor's VÖEN matches the Passport and is active", how: "officer" },
  { number: 11, title: "Everything on the milestone's proof checklist is there", how: "automatic" },
];

export type ProofDoc = {
  kind: "photos" | "manifest" | "invoice" | "receipt" | "chain" | "decision" | "payment";
  title: string;
  detail: string;
  /** SHA-256 of the file, or of the whole bundle for the on-chain record. */
  fingerprint: string;
  /** The blurred public copies' folder on IPFS. */
  cid?: string;
  /** The Polygon transaction that recorded the fingerprint. */
  tx?: string;
  date: string;
  public: boolean;
};

export type Decision = {
  state: "approved" | "reviewing" | "waiting";
  officer: string;
  firm: string;
  at?: string;
  reason?: string;
};

export type MilestoneProof = {
  milestone: number;
  submittedAt: string;
  photos: number;
  docs: ProofDoc[];
  checks: Check[];
  decision: Decision;
};

export type Ballot = {
  id: string;
  project: string;
  milestone: number;
  question: string;
  opened: string;
  closes: string;
  yes: number;
  no: number;
  /** Receipts that may vote: one receipt is one vote. */
  eligible: number;
  state: "open" | "passed";
};

/** The officers the sample Passports name: independent reviewers from audit firms. */
const OFFICERS = [
  ["Nigar Əliyeva", "Caspian Audit Partners"],
  ["Rauf Quliyev", "Absheron Assurance"],
  ["Səbinə Məmmədova", "Kür Audit"],
  ["Elvin Həsənov", "Ganja Review Group"],
] as const;

/** A stable stand-in for a hash: the same seed always gives the same hex. */
export function sampleHex(seed: string, length = 64): string {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  let out = "";
  while (out.length < length) {
    h ^= h << 13;
    h ^= h >>> 17;
    h ^= h << 5;
    out += (h >>> 0).toString(16).padStart(8, "0");
  }
  return out.slice(0, length);
}

function sampleCid(seed: string): string {
  const alphabet = "abcdefghijklmnopqrstuvwxyz234567";
  const hex = sampleHex(seed, 104);
  let out = "bafybei";
  for (let i = 0; i + 1 < hex.length && out.length < 59; i += 2) out += alphabet[parseInt(hex.slice(i, i + 2), 16) % 32];
  return out;
}

/** A number in [0, 1) from a seed, the same every time. */
function unit(seed: string): number {
  return parseInt(sampleHex(seed, 8), 16) / 2 ** 32;
}

export function addDays(iso: string, days: number): string {
  const d = new Date(iso + "T12:00:00Z");
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

const today = () => new Date().toISOString().slice(0, 10);

export function officerOf(p: Project): { officer: string; firm: string } {
  const [officer, firm] = OFFICERS[Math.floor(unit(p.orgId) * OFFICERS.length)];
  return { officer, firm };
}

/** When the officer approved, for a milestone that is approved or paid. */
function approvedAt(m: Milestone): string | undefined {
  if (m.status === "paid" && m.paidAt) {
    const at = addDays(m.paidAt, -4);
    return m.evidence?.anchoredAt && at < m.evidence.anchoredAt ? m.evidence.anchoredAt : at;
  }
  if (m.status === "approved" && m.evidence?.anchoredAt) return addDays(m.evidence.anchoredAt, 2);
  return undefined;
}

/** The proof behind one milestone, or null when no evidence has come in yet. */
export function proofOf(p: Project, i: number): MilestoneProof | null {
  const m = p.milestones[i];
  if (!m?.evidence) return null;
  const ev = m.evidence;
  const seed = `${p.id}/${i}`;
  const submittedAt = ev.anchoredAt ? addDays(ev.anchoredAt, -1) : addDays(m.due, -4);
  const anchored = Boolean(ev.anchoredAt);
  const { officer, firm } = officerOf(p);
  const at = approvedAt(m);
  const decided = m.status === "approved" || m.status === "paid";

  let automaticLeft = ev.checksPassed;
  const checks: Check[] = CHECKS.map((c) => {
    if (c.how === "automatic") {
      const passed = automaticLeft > 0;
      automaticLeft -= 1;
      return { ...c, state: passed ? "passed" : "running" };
    }
    return { ...c, state: decided ? "passed" : "waiting" };
  });

  const docs: ProofDoc[] = [
    {
      kind: "photos",
      title: `${ev.photos} site photos`,
      detail: anchored
        ? "Public copies on IPFS, with faces and number plates blurred"
        : "Blurred public copies are published once the checks finish",
      fingerprint: sampleHex(`${seed}/photos`),
      cid: anchored ? sampleCid(`${seed}/cid`) : undefined,
      date: submittedAt,
      public: anchored,
    },
    {
      kind: "manifest",
      title: "Capture manifest",
      detail: "Each photo's fingerprint, place and time, signed on the field team's phone",
      fingerprint: sampleHex(`${seed}/manifest`),
      date: submittedAt,
      public: true,
    },
    {
      kind: "invoice",
      title: `Invoice from ${p.contractor.name}`,
      detail: "Kept private; its fingerprint is public",
      fingerprint: sampleHex(`${seed}/invoice`),
      date: submittedAt,
      public: false,
    },
    {
      kind: "receipt",
      title: "e-kassa fiscal receipt",
      detail: "Kept private; its fingerprint is public",
      fingerprint: sampleHex(`${seed}/receipt`),
      date: submittedAt,
      public: false,
    },
  ];
  if (anchored) {
    docs.push({
      kind: "chain",
      title: "Recorded on Polygon",
      detail: "The bundle's fingerprint and its check report",
      fingerprint: sampleHex(`${seed}/bundle`),
      tx: "0x" + sampleHex(`${seed}/tx`),
      date: ev.anchoredAt as string,
      public: true,
    });
  }
  if (decided && at) {
    docs.push({
      kind: "decision",
      title: "The officer's decision",
      detail: `Approved and signed by ${officer}, ${firm}`,
      fingerprint: sampleHex(`${seed}/decision`),
      date: at,
      public: true,
    });
  }
  if (m.status === "paid" && m.paidAt) {
    docs.push({
      kind: "payment",
      title: `Payment to ${p.contractor.name}`,
      detail: "From escrow straight to the contractor's bank account",
      fingerprint: sampleHex(`${seed}/payment`),
      date: m.paidAt,
      public: true,
    });
  }

  const decision: Decision = decided
    ? {
        state: "approved",
        officer,
        firm,
        at,
        reason: `The ${ev.photos} photos were taken inside the site and show the work on the checklist. ${p.contractor.name}'s invoice matches the milestone's budget, and its e-kassa receipt is real.`,
      }
    : { state: m.status === "checked" ? "reviewing" : "waiting", officer, firm };

  return { milestone: i, submittedAt, photos: ev.photos, docs, checks, decision };
}

/** The donors' vote that followed the officer's approval of a milestone, if there was one. */
export function ballotOf(p: Project, i: number): Ballot | null {
  const m = p.milestones[i];
  const opened = m ? approvedAt(m) : undefined;
  if (!m || !opened) return null;
  const seed = `${p.id}/${i}/vote`;
  const raised = raisedOf(p) || 1;
  const eligible = Math.max(12, Math.round((p.donors * m.funded) / raised));
  const votes = Math.max(2, Math.round(eligible * (0.16 + unit(seed + "t") * 0.3)));
  const yes = Math.round(votes * (0.8 + unit(seed + "y") * 0.17));
  const closes = addDays(opened, 3);
  return {
    id: `b-${sampleHex(seed, 6)}`,
    project: p.id,
    milestone: i,
    question: `Release ${manat(m.funded)} for “${m.title}” to ${p.contractor.name}?`,
    opened,
    closes,
    yes,
    no: votes - yes,
    eligible,
    state: m.status === "approved" && closes >= today() ? "open" : "passed",
  };
}

/** How a sample donor voted, when their money was in the milestone: mostly yes, sometimes not at all. */
export function sampleVoteOf(ballot: Ballot, donorSeed: string): "yes" | "no" | null {
  if (ballot.state === "open") return null;
  // The finished project on show: its sample donor voted on every one of its milestones.
  if (ballot.project === SHOWCASE) return unit(`${ballot.id}/${donorSeed}`) < 0.93 ? "yes" : "no";
  const u = unit(`${ballot.id}/${donorSeed}`);
  return u < 0.72 ? "yes" : u < 0.8 ? "no" : null;
}

/* ------------------------------------------------------------------ the proof itself, to open */

/** A site photo, as published: the blurred public copy and what the capture app recorded. */
export type EvidencePhoto = {
  src: string;
  caption: string;
  takenAt: string;
  lat: number;
  lng: number;
  /** GPS accuracy in metres. */
  accuracy: number;
  /** Where the stand-in photo comes from (public/img/README.md has the full credits). */
  credit: string;
};

/** The one sample project whose photos are all here, milestone by milestone. */
export const SHOWCASE = "ganja-school-7";

const DIR = "/img/proof/ganja-school/";
const SHOTS: [file: string, caption: string, credit: string][][] = [
  [
    ["m1-scaffolding.jpg", "Scaffolding up around the classroom block", "U.S. Army photo, public domain"],
    ["m1-old-roof-off.jpg", "The old roof coming off, sheet by sheet", "Muntstraat 20, CC BY-SA 4.0"],
    ["m1-stripped-frame.jpg", "Stripped back to the frame, ready for the new roof", "NPS photo, public domain"],
  ],
  [
    ["m2-new-rafters.jpg", "New timber rafters, from inside", "Tomwsulcer, CC0"],
    ["m2-underlay.jpg", "Underlay and battens going on", "NPS photo, public domain"],
    ["m2-shingles.jpg", "Shingles and gutters being fitted", "NPS photo, public domain"],
    ["m2-finished-roof.jpg", "The finished roof", "NPS photo, public domain"],
  ],
  [
    ["m3-old-windows.jpg", "Before: the old single-glazed windows", "Warren LeMay, CC0"],
    ["m3-new-window.jpg", "A new double-glazed window in place", "WorkerDi, CC BY-SA 4.0"],
    ["m3-window-sill.jpg", "Sealed, with the new sill fitted", "WorkerDi, CC BY-SA 4.0"],
    ["m3-window-joint.jpg", "The corner joint, checked for draughts", "WorkerDi, CC BY-SA 4.0"],
  ],
  [
    ["m4-interior-works.jpg", "Ceilings and walls being redone", "U.S. Army photo, public domain"],
    ["m4-radiators.jpg", "New radiators under the windows", "Gareth.randall, public domain"],
    ["m4-classroom.jpg", "A finished classroom", "Oregon State University, CC BY-SA 2.0"],
    ["m4-first-lessons.jpg", "Desks in, ready for the first lessons", "Mercedes Steph, CC BY-SA 4.0"],
  ],
];

/** The photos to open for a milestone: only the project on show has them. */
export function photosOf(p: Project, i: number): EvidencePhoto[] {
  const shots = p.id === SHOWCASE ? SHOTS[i] : undefined;
  const m = p.milestones[i];
  if (!shots || !m?.evidence) return [];
  const day = m.evidence.anchoredAt ? addDays(m.evidence.anchoredAt, -1) : m.due;
  return shots.map(([file, caption, credit], k) => {
    const minutes = 9 * 60 + 12 + k * 47 + Math.floor(unit(`${p.id}/${i}/${k}/t`) * 20);
    const time = `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
    return {
      src: DIR + file,
      caption,
      takenAt: `${day}T${time}`,
      lat: p.lat + (unit(`${p.id}/${i}/${k}/a`) - 0.5) * 0.0006,
      lng: p.lng + (unit(`${p.id}/${i}/${k}/o`) - 0.5) * 0.0008,
      accuracy: 3 + Math.floor(unit(`${p.id}/${i}/${k}/m`) * 6),
      credit,
    };
  });
}

/** The day's code the field team had to get into a photo: it proves the photos are new. */
export const challengeCode = (p: Project, i: number) =>
  sampleHex(`${p.id}/${i}/code`, 6).toUpperCase().replace(/(...)(...)/, "$1-$2");

export type Party = { name: string; voen: string; place: string; iban?: string };
export type Line = { item: string; amount: Qapik };

const digits = (seed: string, n: number) =>
  sampleHex(seed, n * 2)
    .split("")
    .map((c) => String(parseInt(c, 16) % 10))
    .join("")
    .slice(0, n);

/** "SMPL" marks the bank code as a sample: these accounts do not exist. */
const iban = (seed: string) => `AZ${digits(seed + "/k", 2)}SMPL${digits(seed + "/n", 20)}`;

export function contractorOf(p: Project): Party {
  return { name: p.contractor.name, voen: digits(`${p.contractor.name}/voen`, 10), place: p.place, iban: iban(`${p.contractor.name}/iban`) };
}

export function organisationParty(p: Project): Party {
  const org = organisationOf(p.orgId);
  return { name: org?.name ?? "The organisation", voen: digits(`${p.orgId}/voen`, 10), place: org?.city ?? "" };
}

/** Whole qəpik parts of `total` in these shares, adding up to it exactly. */
function parts(total: Qapik, shares: number[]): Qapik[] {
  const out = shares.map((s) => Math.floor(total * s));
  out[0] += total - out.reduce((a, b) => a + b, 0);
  return out;
}

const SHOWCASE_LINES: [string, number][][] = [
  [
    ["Scaffolding, erected around three sides, 10 weeks' hire", 0.38],
    ["Taking off and disposing of the old roof sheets", 0.42],
    ["Temporary waterproof cover over the top floor", 0.2],
  ],
  [
    ["Timber rafters and battens, treated", 0.36],
    ["Breathable underlay and shingles, 1,140 m²", 0.4],
    ["Gutters and downpipes", 0.08],
    ["Roofers' labour", 0.16],
  ],
  [
    ["Double-glazed PVC windows, 88 units", 0.71],
    ["Sills, seals and finishing", 0.09],
    ["Fitting and taking away the old frames", 0.2],
  ],
  [
    ["Radiators and pipework, two wings", 0.46],
    ["Plaster and paint, 22 classrooms", 0.31],
    ["Ceiling repairs and electrical safety check", 0.23],
  ],
];

export type Invoice = { number: string; date: string; seller: Party; buyer: Party; lines: Line[]; total: Qapik; vat: Qapik };

/** The contractor's invoice for a milestone: its lines add up to the milestone's budget, VAT included. */
export function invoiceOf(p: Project, i: number): Invoice {
  const m = p.milestones[i];
  const shape: [string, number][] =
    p.id === SHOWCASE
      ? SHOWCASE_LINES[i]
      : [
          [`Materials: ${m.title.toLowerCase()}`, 0.58],
          ["Labour", 0.34],
          ["Equipment, transport and site", 0.08],
        ];
  const amounts = parts(m.budget, shape.map(([, s]) => s));
  const day = proofOf(p, i)?.submittedAt ?? m.due;
  return {
    number: `${p.contractor.name.replace(/[^A-Za-zƏəŞşÇçĞğÖöÜüİı]/g, "").slice(0, 2).toUpperCase()}-${day.slice(0, 4)}-${digits(`${p.id}/${i}/inv`, 4)}`,
    date: addDays(day, -1),
    seller: contractorOf(p),
    buyer: organisationParty(p),
    lines: shape.map(([item], k) => ({ item, amount: amounts[k] })),
    total: m.budget,
    vat: Math.round((m.budget * 18) / 118),
  };
}

export type FiscalReceipt = { fiscalId: string; number: string; date: string; time: string; seller: Party; total: Qapik };

/** The e-kassa receipt behind the invoice, as the State Tax Service's register shows it. */
export function receiptOf(p: Project, i: number): FiscalReceipt {
  const inv = invoiceOf(p, i);
  const fiscal = sampleHex(`${p.id}/${i}/fiscal`, 12);
  return {
    fiscalId: fiscal.replace(/[0-9a-f]{3}/g, (s) => s[0].toUpperCase() + s.slice(1)),
    number: digits(`${p.id}/${i}/rcpt`, 6),
    date: inv.date,
    time: `${10 + Math.floor(unit(`${p.id}/${i}/rt`) * 7)}:${String(Math.floor(unit(`${p.id}/${i}/rm`) * 60)).padStart(2, "0")}`,
    seller: inv.seller,
    total: inv.total,
  };
}

export type ManifestFile = { name: string; sha256: string; takenAt: string; lat: number; lng: number; accuracy: number };
export type Manifest = { session: string; code: string; device: string; signature: string; files: ManifestFile[] };

/** The capture app's signed list of the milestone's photos. */
export function manifestOf(p: Project, i: number): Manifest {
  const m = p.milestones[i];
  const shown = photosOf(p, i);
  const count = m.evidence?.photos ?? 0;
  const day = proofOf(p, i)?.submittedAt ?? m.due;
  const files: ManifestFile[] = Array.from({ length: count }, (_, k) => {
    const photo = shown[k];
    const minutes = 9 * 60 + k * 11;
    return {
      name: photo ? photo.src.split("/").pop() ?? `IMG_${k}.jpg` : `IMG_${String(2040 + k).padStart(4, "0")}.jpg`,
      sha256: sampleHex(`${p.id}/${i}/${k}/file`),
      takenAt: photo?.takenAt ?? `${day}T${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`,
      lat: photo?.lat ?? p.lat + (unit(`${p.id}/${i}/${k}/a`) - 0.5) * 0.0006,
      lng: photo?.lng ?? p.lng + (unit(`${p.id}/${i}/${k}/o`) - 0.5) * 0.0008,
      accuracy: photo?.accuracy ?? 3 + Math.floor(unit(`${p.id}/${i}/${k}/m`) * 6),
    };
  });
  return {
    session: `cap-${sampleHex(`${p.id}/${i}/session`, 10)}`,
    code: challengeCode(p, i),
    device: "Veritas Capture on the field team's registered phone",
    signature: "0x" + sampleHex(`${p.id}/${i}/manifest-sig`, 130),
    files,
  };
}

export type Payment = { reference: string; date: string; amount: Qapik; to: Party; purpose: string };

/** The escrow bank's transfer to the contractor, once the vote passed. */
export function paymentOf(p: Project, i: number): Payment | null {
  const m = p.milestones[i];
  if (m.status !== "paid" || !m.paidAt) return null;
  return {
    reference: `ESC-${m.paidAt.replace(/-/g, "")}-${digits(`${p.id}/${i}/pay`, 5)}`,
    date: m.paidAt,
    amount: m.funded,
    to: contractorOf(p),
    purpose: `Veritas: ${p.title}, milestone ${i + 1} (${m.title})`,
  };
}

export type ChainEvent = { name: string; detail: string; tx: string; block: number; date: string };

/** What the milestone left on the public chain, in order. */
export function chainOf(p: Project, i: number): ChainEvent[] {
  const pr = proofOf(p, i);
  const ballot = ballotOf(p, i);
  const m = p.milestones[i];
  if (!pr) return [];
  const base = 14_200_000 + Math.floor(unit(`${p.id}/${i}/block`) * 3_000_000);
  const event = (name: string, detail: string, date: string, k: number): ChainEvent => ({
    name,
    detail,
    tx: "0x" + sampleHex(`${p.id}/${i}/${name}/tx`),
    block: base + k * 31_000 + Math.floor(unit(`${p.id}/${i}/${name}/b`) * 900),
    date,
  });
  const events: ChainEvent[] = [];
  const bundle = pr.docs.find((d) => d.kind === "chain");
  if (bundle) events.push(event("EvidenceAnchored", `Bundle ${bundle.fingerprint.slice(0, 10)}… and its check report`, bundle.date, 0));
  if (pr.decision.state === "approved" && pr.decision.at) events.push(event("MilestoneApproved", `Signed by ${pr.decision.officer}`, pr.decision.at, 1));
  if (ballot && ballot.state === "passed") events.push(event("VoteClosed", `${ballot.yes} yes, ${ballot.no} no`, ballot.closes, 2));
  if (m.status === "paid" && m.paidAt) events.push(event("MilestoneReleased", `${manat(m.funded)} to ${p.contractor.name}`, m.paidAt, 3));
  return events;
}
