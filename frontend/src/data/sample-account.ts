import type { Qapik } from "@/lib/money";

/**
 * SAMPLE DATA for the signed-in console: a portfolio every account sees until it has
 * donations of its own on the API (backend: GET /v1/donations, GET /v1/receipts,
 * GET /v1/pledges), so the dashboard has something real-looking to show. It spans every
 * stage: raising, checking, a donor vote, approved, paid out, and a stopped project's
 * refund. Pages that show it say so. Money is integer qəpik.
 *
 * A donation is split across the project's milestones. The part for milestones already
 * paid is "released", the part for milestones not paid yet is "in escrow", and money
 * returned to the card after a project stopped is "refunded"; the three always add up
 * to the amount given.
 */
export type DonationKind = "card" | "pay_on_proof";

export type SampleDonation = {
  id: string;
  projectId: string;
  date: string;
  kind: DonationKind;
  amount: Qapik;
  released: Qapik;
  inEscrow: Qapik;
  refunded: Qapik;
  /** The receipt token's id on-chain, shortened for display. */
  receipt: string;
};

const m = (manat: number): Qapik => manat * 100;

export const SAMPLE_DONATIONS: SampleDonation[] = [
  // First, so the finished project with all its proof on show heads the dashboard's list.
  { id: "d-1013", projectId: "ganja-school-7", date: "2026-04-21", kind: "card", amount: m(80), released: m(80), inEscrow: 0, refunded: 0, receipt: "0x3e7c…b14d" },
  { id: "d-1012", projectId: "baku-ukrainian-families", date: "2026-11-04", kind: "card", amount: m(30), released: 0, inEscrow: m(30), refunded: 0, receipt: "0x6d21…f0a8" },
  { id: "d-1011", projectId: "kharkiv-hospital-power", date: "2026-10-12", kind: "card", amount: m(60), released: 4260, inEscrow: m(60) - 4260, refunded: 0, receipt: "0xc3e5…19b7" },
  { id: "d-1010", projectId: "aghdam-returning-homes", date: "2026-09-21", kind: "card", amount: m(75), released: m(23), inEscrow: m(52), refunded: 0, receipt: "0x41aa…8d3c" },
  { id: "d-1009", projectId: "gazakh-heating", date: "2026-10-26", kind: "card", amount: m(40), released: 0, inEscrow: m(40), refunded: 0, receipt: "0x8f3a…41c2" },
  { id: "d-1008", projectId: "shaki-school-roof", date: "2026-08-20", kind: "card", amount: m(50), released: 990, inEscrow: m(50) - 990, refunded: 0, receipt: "0x2b77…9e10" },
  { id: "d-1007", projectId: "baku-shelter", date: "2026-09-09", kind: "card", amount: m(25), released: m(11), inEscrow: m(14), refunded: 0, receipt: "0xa410…07fd" },
  { id: "d-1006", projectId: "sabirabad-homes", date: "2026-06-11", kind: "card", amount: m(100), released: m(48), inEscrow: m(52), refunded: 0, receipt: "0x5c09…b3e8" },
  { id: "d-1005", projectId: "agdash-water", date: "2026-08-25", kind: "pay_on_proof", amount: m(20), released: m(20), inEscrow: 0, refunded: 0, receipt: "0x77de…2a61" },
  { id: "d-1004", projectId: "guba-recycling", date: "2026-05-02", kind: "card", amount: m(30), released: m(30), inEscrow: 0, refunded: 0, receipt: "0x19b4…cc05" },
  { id: "d-1003", projectId: "irpin-school-windows", date: "2026-05-18", kind: "card", amount: m(45), released: m(45), inEscrow: 0, refunded: 0, receipt: "0x9b02…e7c4" },
  { id: "d-1002", projectId: "zaqatala-footbridge", date: "2026-03-24", kind: "card", amount: m(35), released: 630, inEscrow: 0, refunded: m(35) - 630, receipt: "0x2f6e…a915" },
];

/** A Pay-on-Proof pledge: the card is charged this much each time a milestone is approved. */
export const SAMPLE_PLEDGES = [
  { id: "p-31", projectId: "agdash-water", perMilestone: m(10), charged: m(20), status: "active" as const },
];

export type VerificationStep = { key: string; label: string; done: boolean; at?: string };

/** An organisation that has applied and is waiting for Veritas to verify it. */
export const SAMPLE_ORG_REVIEW: VerificationStep[] = [
  { key: "details", label: "Organisation details", done: true, at: "2026-11-02" },
  { key: "documents", label: "Registration documents and the director's ID", done: true, at: "2026-11-02" },
  { key: "bank", label: "Bank account (IBAN)", done: true, at: "2026-11-03" },
  { key: "review", label: "Veritas review", done: false },
  { key: "verified", label: "Verified: you can publish projects", done: false },
];
